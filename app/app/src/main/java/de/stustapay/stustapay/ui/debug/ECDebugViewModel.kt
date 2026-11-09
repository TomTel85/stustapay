package de.stustapay.stustapay.ui.debug


import android.app.Activity
import android.content.Context
import androidx.lifecycle.ViewModel
import com.ionspin.kotlin.bignum.integer.toBigInteger
import dagger.hilt.android.qualifiers.ApplicationContext
import dagger.hilt.android.lifecycle.HiltViewModel
import de.stustapay.libssp.model.NfcTag
import de.stustapay.stustapay.R
import de.stustapay.stustapay.ec.ECPayment
import de.stustapay.stustapay.ec.SumUp
import de.stustapay.stustapay.repository.ECPaymentRepository
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import java.math.BigDecimal
import java.util.UUID
import javax.inject.Inject

@HiltViewModel
class ECDebugViewModel @Inject constructor(
    @ApplicationContext private val context: Context,
    private val sumUp: SumUp,
    private val ecPaymentRepository: ECPaymentRepository,
) : ViewModel() {
    private val _status = MutableStateFlow(context.getString(R.string.ec_debug_status_loading))
    val status = _status.asStateFlow()
    val sumUpState = sumUp.paymentStatus
    private val _ambiguousPaymentId = MutableStateFlow<String?>(null)
    val ambiguousPaymentId = _ambiguousPaymentId.asStateFlow()

    suspend fun refreshAmbiguousPayment() {
        _ambiguousPaymentId.update { ecPaymentRepository.ambiguousPaymentIdForOperator() }
    }

    suspend fun releaseAmbiguousPayment(): Boolean {
        val paymentId = _ambiguousPaymentId.value ?: return false
        if (!ecPaymentRepository.releaseAmbiguousPaymentAfterProviderCheck(paymentId)) return false
        _ambiguousPaymentId.update { null }
        _status.update { context.getString(R.string.card_payment_released, paymentId) }
        return true
    }

    suspend fun openLogin(context: Activity) {
        _status.update { this.context.getString(R.string.ec_debug_status_opening_login) }
        sumUp.login(context)
    }

    suspend fun tokenLogin(context: Activity) {
        _status.update { this.context.getString(R.string.ec_debug_status_token_login) }
        sumUp.tokenLogin(context)
    }

    suspend fun logout(context: Activity) {
        _status.update { this.context.getString(R.string.ec_debug_status_logging_out) }
        sumUp.logout()
    }

    suspend fun openSettingsDeprecated(context: Activity) {
        _status.update { this.context.getString(R.string.ec_debug_status_opening_deprecated_settings) }
        sumUp.settingsOld(context)
    }

    suspend fun openCardReader(context: Activity) {
        _status.update { this.context.getString(R.string.ec_debug_status_opening_card_reader_settings) }
        sumUp.cardReaderSettings(context)
    }

    suspend fun openCheckout(context: Activity) {
        _status.update { this.context.getString(R.string.ec_debug_status_opening_checkout) }
        sumUp.pay(
            context = context,
            payment = ECPayment(
                id = "test ${UUID.randomUUID()}",
                tag = NfcTag(0.toBigInteger(), null),
                amount = BigDecimal(100),
            )
        )
    }
}
