package de.stustapay.stustapay.ui.payinout.topup

import android.app.Activity
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import dagger.hilt.android.lifecycle.HiltViewModel
import de.stustapay.api.models.CompletedTopUp
import de.stustapay.api.models.NewTopUp
import de.stustapay.api.models.PaymentMethod
import de.stustapay.libssp.model.NfcTag
import de.stustapay.libssp.net.Response
import de.stustapay.stustapay.ec.ECPayment
import de.stustapay.stustapay.repository.ECPaymentRepository
import de.stustapay.stustapay.repository.ECPaymentResult
import de.stustapay.stustapay.repository.InfallibleRepository
import de.stustapay.stustapay.repository.TerminalConfigRepository
import de.stustapay.stustapay.repository.TopUpRepository
import de.stustapay.stustapay.repository.UserRepository
import de.stustapay.stustapay.ui.common.TerminalLoginState
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import java.math.BigDecimal
import java.util.UUID
import javax.inject.Inject


enum class TopUpPage(val route: String) {
    Selection("amount"),
    Done("done"),
    Failure("aborted"),
}


data class TopUpState(
    /** desired deposit amount in cents */
    var currentAmount: UInt = 0u,
)


@HiltViewModel
class TopUpViewModel @Inject constructor(
    private val topUpRepository: TopUpRepository,
    private val terminalConfigRepository: TerminalConfigRepository,
    userRepository: UserRepository,
    private val ecPaymentRepository: ECPaymentRepository,
    private val infallibleRepository: InfallibleRepository
) : ViewModel() {
    private val _navState = MutableStateFlow(TopUpPage.Selection)
    val navState = _navState.asStateFlow()

    private val _status = MutableStateFlow("")
    val status = _status.asStateFlow()

    private val _errorMessage = MutableStateFlow<String?>(null)
    val errorMessage = _errorMessage.asStateFlow()

    private val _topUpState = MutableStateFlow(TopUpState())
    val topUpState = _topUpState.asStateFlow()

    // when we finished a sale
    private val _topUpCompleted = MutableStateFlow<CompletedTopUp?>(null)
    val topUpCompleted = _topUpCompleted.asStateFlow()

    val requestActive = infallibleRepository.active

    // configuration infos from backend
    val terminalLoginState = combine(
        userRepository.userState,
        terminalConfigRepository.terminalConfigState
    ) { user, terminal ->
        TerminalLoginState(user, terminal)
    }.stateIn(
        scope = viewModelScope,
        started = SharingStarted.WhileSubscribed(5_000),
        initialValue = TerminalLoginState(),
    )

    // Flag to track if token refresh is active
    private val _tokenRefreshActive = MutableStateFlow(false)
    
    init {
        // Start token refresh job when ViewModel is created
        startTokenRefresh()
    }
    
    private fun startTokenRefresh() {
        viewModelScope.launch {
            _tokenRefreshActive.update { true }
            try {
                while (_tokenRefreshActive.value) {
                    // Check and refresh token if needed
                    terminalConfigRepository.tokenRefresh()
                    // Wait for 2 minutes before checking again
                    delay(2 * 60 * 1000)
                }
            } catch (e: Exception) {
                _status.update { "Token refresh error: ${e.message}" }
            }
        }
    }
    
    // Make sure to stop token refresh when ViewModel is cleared
    override fun onCleared() {
        super.onCleared()
        _tokenRefreshActive.update { false }
    }

    fun setAmount(amount: UInt) {
        _topUpState.update {
            it.copy(currentAmount = amount)
        }
    }

    fun clearDraft() {
        _topUpCompleted.update { null }
        _topUpState.update { TopUpState() }
        _status.update { "ready" }
    }

    fun checkAmountLocal(amount: Double): Boolean {
        val minimum = 1.0
        if (amount < minimum) {
            _status.update { "Mindestbetrag %.2f €".format(minimum) }
            return false
        }
        return true
    }

    /**
     * validates the amount so we can continue to checkout
     */
    private suspend fun checkTopUp(newTopUp: NewTopUp): Boolean {
        // device-local checks
        if (!checkAmountLocal(newTopUp.amount)) {
            return false
        }

        // server-side check
        return when (val response = topUpRepository.checkTopUp(newTopUp)) {
            is Response.OK -> {
                _status.update { "TopUp possible" }
                true
            }

            is Response.Error.Service -> {
                // TODO: if we remember the scanned tag, clear it here.
                _status.update { response.msg() }
                _errorMessage.update { response.msg() }
                false
            }

            is Response.Error -> {
                _status.update { response.msg() }
                false
            }
        }
    }

    /**
     * creates a ec payment with new id for the current selected sum.
     */
    private fun getECPayment(newTopUp: NewTopUp): ECPayment {
        return ECPayment(
            id = newTopUp.uuid.toString(),
            amount = BigDecimal(newTopUp.amount),
            tag = NfcTag(newTopUp.customerTagUid, null),
        )
    }

    /** called from the card payment button */
    suspend fun topUpWithCard(context: Activity, tag: NfcTag) {
        _status.update { "Card TopUp in progress..." }
        // wake the soon-needed reader :)
        // TODO: move this even before the chip scan
        // CashECPay could get a prepareEC callback function for that.
        ecPaymentRepository.wakeup()
        
        // Check and refresh token if needed before payment
        terminalConfigRepository.tokenRefresh()

        val newTopUp = NewTopUp(
            amount = _topUpState.value.currentAmount.toDouble() / 100,
            customerTagUid = tag.uid,
            paymentMethod = PaymentMethod.sumup,
            // we generate the topup transaction identifier here
            uuid = UUID.randomUUID(),
        )

        if (!checkTopUp(newTopUp)) {
            // it already updates the status message
            return
        }

        val payment = getECPayment(newTopUp)

        // pre-register the payment so the backend starts polling sumup
        // if the transaction has completed, but the callback to the POS terminal got missing
        // due to wlan glitches etc.

        if (!registerTopUp("Card", newTopUp)) {
            // already updates status message
            return
        }

        _status.update { "Remove the chip. Starting EC transaction..." }

        // workaround so the sumup activity is not in foreground too quickly.
        // when it's active, nfc intents are no longer captured by us, apparently,
        // and then the system nfc handler spawns the default handler (e.g. stustapay) again.
        // https://stackoverflow.com/questions/60868912
        delay(800)

        // perform ec transaction
        when (val paymentResult = ecPaymentRepository.pay(context, payment)) {
            is ECPaymentResult.Failure -> {
                _status.update { "EC: ${paymentResult.msg}" }
                return
            }

            is ECPaymentResult.Success -> {
                _status.update { "EC: ${paymentResult.result.msg}" }
            }
        }

        // when successful, book the transaction
        // if this doesn't reach the backend, the backend will book the topUp on its own
        // when sumup confirms the payment.
        bookTopUp("Card", newTopUp)
    }

    suspend fun topUpWithCash(tag: NfcTag) {
        _status.update { "Cash TopUp in progress..." }

        val newTopUp = NewTopUp(
            amount = _topUpState.value.currentAmount.toDouble() / 100,
            customerTagUid = tag.uid,
            paymentMethod = PaymentMethod.cash,
            // we generate the topup transaction identifier here
            uuid = UUID.randomUUID(),
        )

        if (!checkTopUp(newTopUp)) {
            // it already updates the status message
            return
        }

        bookTopUp("Cash", newTopUp)
    }

    private suspend fun registerTopUp(topUpType: String, newTopUp: NewTopUp): Boolean {
        _status.update { "Announcing $topUpType TopUp..." }

        when (val response = topUpRepository.registerTopUp(newTopUp)) {
            is Response.OK -> {
                _status.update { "$topUpType TopUp announced!" }
                return true
            }

            is Response.Error -> {
                _status.update { "$topUpType TopUp announce failed: ${response.msg()}" }
                _navState.update { TopUpPage.Failure }
                return false
            }
        }
    }

    private suspend fun bookTopUp(topUpType: String, newTopUp: NewTopUp) {
        _status.update { "Booking $topUpType TopUp..." }
        when (val response = infallibleRepository.bookTopUp(newTopUp)) {
            is Response.OK -> {
                clearDraft()
                _topUpCompleted.update { response.data }
                _status.update { "$topUpType TopUp successful!" }
                _navState.update { TopUpPage.Done }
            }

            is Response.Error -> {
                _status.update { "$topUpType TopUp failed! ${response.msg()}" }
                _navState.update { TopUpPage.Failure }
            }
        }
    }


    fun navigateTo(target: TopUpPage) {
        _navState.update { target }
        
        // When navigating to the selection screen, ensure we have a fresh token
        if (target == TopUpPage.Selection) {
            viewModelScope.launch {
                // Refresh token if needed
                terminalConfigRepository.tokenRefresh()
            }
        }
    }

    /** when a topup was successful and the confirmation was dismissed */
    fun dismissSuccess() {
        // todo: some feedback during this refresh?
        viewModelScope.launch {
            terminalConfigRepository.tokenRefresh()
        }
        navigateTo(TopUpPage.Selection)
    }

    fun dismissFailure() {
        navigateTo(TopUpPage.Selection)
    }

    fun dismissError() {
        _errorMessage.update { null }
    }
}