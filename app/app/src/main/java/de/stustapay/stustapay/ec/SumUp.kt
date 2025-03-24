package de.stustapay.stustapay.ec

import android.app.Activity
import android.os.Bundle
import android.util.Log
import com.sumup.merchant.reader.api.SumUpAPI
import com.sumup.merchant.reader.api.SumUpLogin
import com.sumup.merchant.reader.api.SumUpPayment
import com.sumup.merchant.reader.models.TransactionInfo
import de.stustapay.libssp.util.ActivityCallback
import de.stustapay.stustapay.repository.TerminalConfigRepository
import de.stustapay.stustapay.repository.TerminalConfigState
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import javax.inject.Inject
import javax.inject.Singleton
import com.sumup.merchant.reader.api.SumUpState as SumUpReaderState


data class ECTerminalConfig(
    val name: String,
    val id: String,
    val eventName: String,
)

data class SumUpConfig(
    val affiliateKey: String,
    val apiKey: String,
    val terminal: ECTerminalConfig,
)

sealed interface SumUpConfigState {
    data class OK(val cfg: SumUpConfig) : SumUpConfigState
    data class Error(val msg: String) : SumUpConfigState
}

enum class SumUpAction {
    None, LoginUserPassword, LoginToken, Checkout, OldSettings, CardReader,
}

/** if the action is requested, does it need a login? */
val sumUpActionDependencies: Map<SumUpAction, Boolean> = mapOf(
    Pair(SumUpAction.LoginUserPassword, false),
    Pair(SumUpAction.LoginToken, false),
    Pair(SumUpAction.Checkout, true),
    Pair(SumUpAction.OldSettings, true),
    Pair(SumUpAction.CardReader, true),
)

data class SumUpPaymentState(
    /**
     * since the activity launching returns by callbacks,
     * we need to remember what we wanted to do...
     */
    var targetAction: SumUpAction = SumUpAction.None,
    var config: SumUpConfig? = null,
    var payment: ECPayment? = null,
    var actionsDone: MutableSet<SumUpAction> = mutableSetOf()
)

/**
 * represents the sumup interaction.
 * I'm sorry, but this whole global state machine mess is because all of sumup's state is global.
 */
@Singleton
class SumUp @Inject constructor(
    private val terminalConfigRepository: TerminalConfigRepository,
) {
    // numbers we chose to mark activity result callbacks from the sumup activity.
    private val ecPaymentActivityCallbackId = 50309
    private val ecLoginActivityCallbackId = 50310
    private val ecSettingsActivityCallbackId = 50311
    private val ecCardReaderActivityCallbackId = 50312

    private val _paymentStatus = MutableStateFlow<SumUpState>(SumUpState.None)

    /** payment progress */
    val paymentStatus = _paymentStatus.asStateFlow()

    private val _status = MutableStateFlow("no status")

    /** status message */
    val status = _status.asStateFlow()

    private val _loginStatus = MutableStateFlow<String?>(null)

    /** login username/merchant status */
    val loginStatus = _loginStatus.asStateFlow()
    private var _loginApiKeyUsed: String? = null

    enum class SumUpResultCode(val code: Int) {
        SUCCESSFUL(1),
        ERROR_TRANSACTION_FAILED(2),
        ERROR_GEOLOCATION_REQUIRED(3),
        ERROR_INVALID_PARAM(4),
        ERROR_INVALID_TOKEN(5),
        ERROR_NO_CONNECTIVITY(6),
        ERROR_PERMISSION_DENIED(7),
        ERROR_NOT_LOGGED_IN(8),
        ERROR_DUPLICATE_FOREIGN_TX_ID(9),
        ERROR_INVALID_AFFILIATE_KEY(10),
        ERROR_ALREADY_LOGGED_IN(11),
        ERROR_INVALID_AMOUNT_DECIMALS(12),
        ERROR_API_LEVEL_TOO_LOW(13), ;

        companion object {
            private val map = SumUpResultCode.values().associateBy(SumUpResultCode::code)
            fun fromInt(type: Int) = map[type]
        }
    }

    /**
     * global configuration for our statemachine...
     */
    private var sumUpPaymentState = SumUpPaymentState()

    fun init(activityCallback: ActivityCallback) {
        val activity = activityCallback.context as Activity

        // since sumup spawns its own activity for the checkout,
        // we register the launch and callbacks to our activity.

        SumUpReaderState.init(activity)
        activityCallback.registerHandler(ecPaymentActivityCallbackId) { resultCode, extras ->
            paymentResult(activity, resultCode, extras)
        }
        activityCallback.registerHandler(ecLoginActivityCallbackId) { resultCode, extras ->
            loginResult(activity, resultCode, extras)
        }
        activityCallback.registerHandler(ecSettingsActivityCallbackId) { resultCode, extras ->
            settingsResult(activity, resultCode, extras)
        }
        activityCallback.registerHandler(ecCardReaderActivityCallbackId) { resultCode, extras ->
            cardReaderResult(activity, resultCode, extras)
        }

        updateLoginInfo()

        _status.update { "sumup api initialized" }
    }

    private fun checkResultCode(stage: String, resultCode: Int): Boolean {
        // the activity result code seems to equals the sumup result code
        // and the sumup result codes are custom, hence >= than the first user definable result code.
        // -1 is default success, 0 is aborted, which we both don't expect.
        if (resultCode < Activity.RESULT_FIRST_USER) {
            _paymentStatus.update { SumUpState.Started("bad $stage intent result: $resultCode") }
            return false
        }

        return true
    }


    private fun nextAction(context: Activity) {
        val needsLogin = sumUpActionDependencies[sumUpPaymentState.targetAction]
        if (needsLogin == null) {
            Log.e(
                "TeamFestlichPay",
                "unknown ec action login requirement for ${sumUpPaymentState.targetAction}"
            )
            return
        }

        var nextAction: SumUpAction = sumUpPaymentState.targetAction
        if (nextAction in sumUpPaymentState.actionsDone) {
            return
        }

        val cfg = sumUpPaymentState.config
        if (cfg == null) {
            _paymentStatus.update { SumUpState.Error("no payment state config for next action") }
            return
        }

        // if needed, perform token login.
        if (needsLogin) {
            // logout if we're currently logged in with the wrong api key
            if (_loginApiKeyUsed != cfg.apiKey) {
                SumUpAPI.logout()
            }

            if (!SumUpAPI.isLoggedIn()) {
                nextAction = SumUpAction.LoginToken
            }
        }

        // record the soon-done action.
        sumUpPaymentState.actionsDone.add(
            nextAction
        )

        when (nextAction) {
            SumUpAction.None -> {}
            SumUpAction.LoginUserPassword -> {
                openLogin(context)
            }

            SumUpAction.LoginToken -> {
                openTokenLogin(context)
            }

            SumUpAction.Checkout -> {
                openCheckout(context)
            }

            SumUpAction.CardReader -> {
                openCardReaderPage(context)
            }

            SumUpAction.OldSettings -> {
                openOldSettings(context)
            }
        }
    }


    private fun nextActionIfOk(context: Activity, extras: Bundle?) {
        if (extras == null) {
            _paymentStatus.update { SumUpState.Error("no intent extras") }
            return
        }

        val resultMsg = extras.getString(SumUpAPI.Response.MESSAGE)
        when (val result = SumUpResultCode.fromInt(extras.getInt(SumUpAPI.Response.RESULT_CODE))) {
            SumUpResultCode.SUCCESSFUL -> {
                _paymentStatus.update { SumUpState.Started("done: $resultMsg") }
                nextAction(context)
            }

            else -> {
                _paymentStatus.update { SumUpState.Error("bad sumup result: $result: $resultMsg") }
            }
        }
    }

    private suspend fun setState(target: SumUpAction, payment: ECPayment? = null): Boolean {
        return when (val sumUpConfig = fetchConfig()) {
            is SumUpConfigState.Error -> {
                _paymentStatus.update { SumUpState.Failed("failed fetching sumup configuration: ${sumUpConfig.msg}") }
                false
            }

            is SumUpConfigState.OK -> {
                _paymentStatus.update { SumUpState.None }

                // set up the state machine
                sumUpPaymentState = SumUpPaymentState(
                    targetAction = target,
                    config = sumUpConfig.cfg,
                    payment = payment,
                )
                true
            }
        }
    }


    private suspend fun fetchConfig(): SumUpConfigState {
        val sumUpConfig: SumUpConfig

        when (val terminalConfig = terminalConfigRepository.terminalConfigState.value) {
            is TerminalConfigState.Success -> {
                val cfg = terminalConfig.config
                val secrets = cfg.till?.sumupSecrets
                if (secrets == null) {
                    return SumUpConfigState.Error("no terminal ec secrets in config")
                }
                if (!secrets.sumupAffiliateKey.startsWith("sup_afk")) {
                    return SumUpConfigState.Error("invalid affiliate key: '${secrets.sumupAffiliateKey}'")
                }

                sumUpConfig = SumUpConfig(
                    affiliateKey = secrets.sumupAffiliateKey,
                    apiKey = secrets.sumupApiKey,
                    terminal = ECTerminalConfig(
                        name = cfg.name,
                        id = cfg.id.toString(),
                        eventName = cfg.eventName
                    )
                )
            }

            else -> {
                return SumUpConfigState.Error("no terminal configuration for ec")
            }
        }

        return SumUpConfigState.OK(sumUpConfig)
    }

    fun isLoggedIn(): Boolean {
        return SumUpAPI.isLoggedIn()
    }

    /**
     * open the sumup login screen.
     */
    suspend fun login(
        context: Activity,
    ) {
        if (setState(target = SumUpAction.LoginUserPassword, payment = null)) {
            nextAction(context)
        }
    }

    /**
     * log in via access token
     */
    suspend fun tokenLogin(
        context: Activity,
    ) {
        if (setState(target = SumUpAction.LoginToken, payment = null)) {
            nextAction(context)
        }
    }

    /**
     * logout from sumup account.
     */
    suspend fun logout() {
        SumUpAPI.logout()
        _loginApiKeyUsed = null
        _loginStatus.update { null }
        _status.update { "logged out." }
    }

    /**
     * initiates a ec payment.
     *
     * first, creates the payment definition,
     * then launches the sumup payment activity.
     */
    suspend fun pay(
        context: Activity,
        payment: ECPayment,
    ) {
        if (setState(target = SumUpAction.Checkout, payment = payment)) {
            nextAction(context)
        }
    }

    /**
     * for quicker payments, wake the ec reader in advance.
     */
    suspend fun wakeup() {
        // wake the device for a faster experience
        if (SumUpAPI.isLoggedIn()) {
            SumUpAPI.prepareForCheckout()
        }
    }

    /**
     * show the deprecated settings menu
     */
    suspend fun settingsOld(
        context: Activity
    ) {
        if (setState(target = SumUpAction.OldSettings, payment = null)) {
            nextAction(context)
        }
    }

    /**
     * opens the card reader settings activity.
     */
    suspend fun cardReaderSettings(
        context: Activity
    ) {
        if (setState(target = SumUpAction.CardReader, payment = null)) {
            nextAction(context)
        }
    }


    /**
     * perform login at sumup api.
     * calls back to loginResult.
     */
    private fun openLogin(context: Activity) {
        val cfg = sumUpPaymentState.config
        if (cfg == null) {
            _paymentStatus.update { SumUpState.Error("no config present in login") }
            return
        }

        val sumupLogin = SumUpLogin.builder(cfg.affiliateKey).build()

        SumUpAPI.openLoginActivity(context, sumupLogin, ecLoginActivityCallbackId)
    }

    /**
     * perform login at sumup api.
     * calls back to loginResult.
     */
    private fun openTokenLogin(context: Activity) {
        val cfg = sumUpPaymentState.config
        if (cfg == null) {
            _paymentStatus.update { SumUpState.Error("no config present in login") }
            return
        }
        // remember which api key is currently logged in
        _loginApiKeyUsed = cfg.apiKey

        val sumupLogin = SumUpLogin.builder(cfg.affiliateKey).accessToken(cfg.apiKey).build()

        SumUpAPI.openLoginActivity(context, sumupLogin, ecLoginActivityCallbackId)
    }

    /**
     * called from MainActivity when SumUp Login Activity returns.
     */
    private fun loginResult(context: Activity, resultCode: Int, extras: Bundle?) {
        if (!checkResultCode("login", resultCode)) {
            _paymentStatus.update { SumUpState.Started("bad login intent result: $resultCode") }
            _loginApiKeyUsed = null
            return
        }
        if (extras == null) {
            _paymentStatus.update { SumUpState.Error("no sumup login result intent extras") }
            _loginApiKeyUsed = null
            return
        }

        val resultMsg = extras.getString(SumUpAPI.Response.MESSAGE)
        when (val result = SumUpResultCode.fromInt(extras.getInt(SumUpAPI.Response.RESULT_CODE))) {
            SumUpResultCode.SUCCESSFUL -> {

                updateLoginInfo()

                _paymentStatus.update { SumUpState.Started("sumup login success") }
                nextAction(context)
            }

            SumUpResultCode.ERROR_ALREADY_LOGGED_IN -> {
                nextAction(context)
            }

            SumUpResultCode.ERROR_INVALID_TOKEN -> {
                _loginApiKeyUsed = null
                _paymentStatus.update { SumUpState.Error("sumup login token invalid: $resultMsg") }
            }

            else -> {
                _loginApiKeyUsed = null
                _paymentStatus.update { SumUpState.Error("sumup login result: $result: $resultMsg") }
            }
        }
    }

    /**
     * create a payment.
     * will call back to paymentResult.
     */
    private fun openCheckout(context: Activity) {
        if (!SumUpAPI.isLoggedIn()) {
            _paymentStatus.update { SumUpState.Error("not logged in when checking out") }
            return
        }

        val payment = sumUpPaymentState.payment
        if (payment == null) {
            _paymentStatus.update { SumUpState.Error("no payment status") }
            return
        }

        val cfg = sumUpPaymentState.config
        if (cfg == null) {
            _paymentStatus.update { SumUpState.Error("no payment status") }
            return
        }

        // wake up pin device
        SumUpAPI.prepareForCheckout()

        val sumUpPayment = SumUpPayment.builder()
            // minimum 1.00
            .total(payment.amount).currency(SumUpPayment.Currency.EUR)
            // optional: include a tip amount in addition to the total
            .tip(payment.tip)
            .title("${cfg.terminal.eventName} ${payment.tag.uidHex()} ${payment.id}")
            //.receiptEmail("dummy@sft.lol") // todo: pre-set if the user has provided their email
            //.receiptSMS("+00000000000")
            .addAdditionalInfo("Terminal", cfg.terminal.name)
            .addAdditionalInfo("TerminalID", cfg.terminal.id)
            .addAdditionalInfo("Tag", payment.tag.toString())
            // stustapay order uuid
            .foreignTransactionId(payment.id)
            // optional: skip the success screen
            .skipSuccessScreen()
            // optional: skip the failed screen
            //.skipFailedScreen()
            .build()

        _paymentStatus.update { SumUpState.Started(payment.id) }

        // TODO: use more modern registerForActivityResult
        //       but the sumup sdk has to support it
        // this launches the sumup payment activity
        SumUpAPI.checkout(context, sumUpPayment, ecPaymentActivityCallbackId)
    }

    private fun paymentResult(context: Activity, resultCode: Int, extras: Bundle?) {
        if (!checkResultCode("payment", resultCode)) {
            _paymentStatus.update { SumUpState.Failed("bad payment result: $resultCode") }
            return
        }

        if (extras == null) {
            _paymentStatus.update { SumUpState.Error("no sumup payment result intent extras") }
            return
        }

        val resultMsg = extras.getString(SumUpAPI.Response.MESSAGE)
        when (val result = SumUpResultCode.fromInt(extras.getInt(SumUpAPI.Response.RESULT_CODE))) {
            SumUpResultCode.SUCCESSFUL -> {
                val resultString = extras.getString(SumUpAPI.Response.MESSAGE)
                val txCode = extras.getString(SumUpAPI.Response.TX_CODE)
                // val receiptSent = extras.getBoolean(SumUpAPI.Response.RECEIPT_SENT)

                // TODO: when we have apilevel 33:
                // val txInfo = extras.getParcelable(SumUpAPI.Response.TX_INFO, TransactionInfo::class.java)
                @Suppress("DEPRECATION") val txInfo =
                    extras.getParcelable<TransactionInfo>(SumUpAPI.Response.TX_INFO)
                _paymentStatus.update {
                    SumUpState.Success(
                        msg = resultString ?: "no info",
                        txCode = txCode ?: "no transaction code",
                        txInfo = txInfo,
                    )
                }

                // TODO log the payment locally on the terminal,
                //      and maybe sync it back to the core

                nextAction(context)
            }

            else -> {
                _paymentStatus.update {
                    SumUpState.Error("checkout result: $result: $resultMsg")
                }
            }
        }
    }

    /**
     * open the sumup settings.
     * calls back to settingsresult.
     */
    private fun openOldSettings(context: Activity) {
        // settings for sumup, e.g. pairing with the card terminal
        @Suppress("DEPRECATION") SumUpAPI.openPaymentSettingsActivity(
            context,
            ecSettingsActivityCallbackId
        )
    }

    private fun settingsResult(context: Activity, resultCode: Int, extras: Bundle?) {
        if (!checkResultCode("settings", resultCode)) {
            return
        }

        nextActionIfOk(context, extras)
    }


    /**
     * open the sumup cardreader settings.
     * calls back to cardReaderResult.
     */
    private fun openCardReaderPage(context: Activity) {
        // settings for sumup, e.g. pairing with the card terminal
        SumUpAPI.openCardReaderPage(context, ecCardReaderActivityCallbackId)
    }


    private fun cardReaderResult(context: Activity, resultCode: Int, extras: Bundle?) {
        if (!checkResultCode("card reader", resultCode)) {
            return
        }

        nextActionIfOk(context, extras)
    }

    private fun updateLoginInfo(): String {
        val loggedInMerchant = SumUpAPI.getCurrentMerchant()
        val merchantInfo = if (loggedInMerchant != null) { // == isLoggedIn()
            val loginId = loggedInMerchant.merchantCode
            val currency = loggedInMerchant.currency.isoCode
            "$loginId ($currency)"
        } else {
            "no logged in merchant"
        }
        _loginStatus.update { merchantInfo }
        return merchantInfo
    }
}