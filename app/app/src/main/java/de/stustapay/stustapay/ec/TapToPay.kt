package de.stustapay.stustapay.ec

import android.content.Context
import android.util.Log
import de.stustapay.stustapay.display.CustomerDisplayManager
import de.stustapay.stustapay.display.CustomerDisplayState
import de.stustapay.stustapay.repository.TerminalConfigRepository
import de.stustapay.stustapay.repository.TerminalConfigState
import java.math.BigDecimal
import javax.inject.Inject
import javax.inject.Singleton
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.collect
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

internal fun isTapToPayEnabledForTill(
    tapToPayEnabled: Boolean?,
    tapToPayAvailable: Boolean?,
): Boolean = tapToPayEnabled == true && tapToPayAvailable == true

@Singleton
class TapToPay @Inject constructor(
    private val terminalConfigRepository: TerminalConfigRepository,
    private val customerDisplayManager: CustomerDisplayManager,
    private val sdkGateway: TapToPaySdkGateway,
) {
    private val _paymentStatus = MutableStateFlow<SumUpState>(SumUpState.None)
    val paymentStatus = _paymentStatus.asStateFlow()

    private val _status = MutableStateFlow("no status")
    val status = _status.asStateFlow()

    private var isInitialized = false
    private var sessionIdentity: TapToPaySessionIdentity? = null
    private var sandboxSession = false
    private val displaySession = TapToPayDisplaySession()

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main)

    suspend fun initialize(context: Context): Boolean {
        if (!sdkGateway.isAvailable) {
            _status.update { "Tap To Pay SDK not available in this build" }
            return false
        }

        return when (val terminalConfig = terminalConfigRepository.terminalConfigState.value) {
            is TerminalConfigState.Success -> {
                val tillConfig = terminalConfig.config.till
                if (!isTapToPayEnabledForTill(tillConfig?.tapToPayEnabled, tillConfig?.tapToPayAvailable)) {
                    _status.update { "Tap To Pay is not enabled for the active till profile" }
                    return false
                }
                val secrets = tillConfig?.sumupSecrets
                if (secrets == null) {
                    _status.update { "No SumUp secrets in terminal config" }
                    return false
                }
                val requestedIdentity = TapToPaySessionIdentity(
                    environment = secrets.sumupEnvironment.toString(),
                    merchantCode = secrets.sumupMerchantCode,
                )
                if (isInitialized && sessionIdentity == requestedIdentity) {
                    Log.d("TapToPay", "Tap To Pay already initialized for the active merchant, skipping")
                    return true
                }

                try {
                    if (shouldReinitializeTapToPay(isInitialized, sessionIdentity, requestedIdentity)) {
                        val tearDownResult = sdkGateway.tearDown()
                        val tearDownError = tearDownResult.exceptionOrNull()
                        if (tearDownError != null) {
                            Log.e("TapToPay", "Failed to tear down previous SDK session", tearDownError)
                            _status.update { "Tap To Pay merchant switch failed: ${tearDownError.message}" }
                            return false
                        }
                        isInitialized = false
                        sessionIdentity = null
                    }
                    val initResult = sdkGateway.initialize(context.applicationContext) {
                        currentTapToPayToken(fallbackToken = secrets.sumupApiKey)
                    }
                    val initError = initResult.exceptionOrNull()
                    if (initError != null) {
                        Log.e("TapToPay", "Failed to initialize SDK", initError)
                        _status.update { "Tap To Pay initialization failed: ${initError.message}" }
                        isInitialized = false
                        sessionIdentity = null
                        return false
                    }

                    isInitialized = true
                    sessionIdentity = requestedIdentity
                    sandboxSession = requestedIdentity.environment.equals("sandbox", ignoreCase = true)
                    _status.update {
                        if (sandboxSession) "SANDBOX — Tap To Pay initialized" else "Tap To Pay initialized"
                    }
                    Log.d("TapToPay", "Tap To Pay SDK initialized successfully")
                    true
                } catch (exc: Exception) {
                    Log.e("TapToPay", "Failed to initialize Tap To Pay", exc)
                    _status.update { "Tap To Pay initialization failed: ${exc.message}" }
                    isInitialized = false
                    sessionIdentity = null
                    false
                }
            }

            else -> {
                _status.update { "No terminal configuration available" }
                false
            }
        }
    }

    suspend fun pay(payment: ECPayment) {
        if (!isInitialized || !sdkGateway.isAvailable) {
            _paymentStatus.update {
                SumUpState.Error(
                    msg = "Tap To Pay SDK not available",
                    readerFallbackAllowed = true,
                )
            }
            return
        }

        val config = fetchConfig()
        if (config is SumUpConfigState.Error) {
            _paymentStatus.update {
                SumUpState.Error(
                    msg = "Failed to fetch configuration: ${config.msg}",
                    readerFallbackAllowed = true,
                )
            }
            return
        }

        val amountInCents = payment.amount.multiply(BigDecimal(100)).toLong()

        displaySession.begin(customerDisplayManager.currentState())
        _paymentStatus.update { SumUpState.Started(payment.id) }
        _status.update { "Starting Tap To Pay transaction..." }
        customerDisplayManager.updateState(CustomerDisplayState.TapToPayReady)

        try {
            val paymentFlow = sdkGateway.startPayment(
                totalAmount = amountInCents,
                clientUniqueTransactionId = payment.id,
            )

            scope.launch {
                try {
                    paymentFlow.collect { event ->
                        handlePaymentEvent(event)
                    }
                } catch (exc: CancellationException) {
                    throw exc
                } catch (exc: Exception) {
                    Log.e("TapToPay", "Tap To Pay payment flow failed", exc)
                    if (_paymentStatus.value !is SumUpState.Success) {
                        _status.update { "Payment status unknown: ${exc.message}" }
                        _paymentStatus.update {
                            SumUpState.Error(
                                msg = "Tap To Pay payment status unknown: ${exc.message}",
                                mayHaveCreatedCharge = true,
                            )
                        }
                    }
                }
            }
        } catch (exc: Exception) {
            Log.e("TapToPay", "Failed to start payment", exc)
            _paymentStatus.update {
                SumUpState.Error(
                    msg = "Failed to start payment: ${exc.message}",
                    readerFallbackAllowed = true,
                )
            }
        }
    }

    suspend fun wakeup() {
        _status.update { "Tap To Pay ready" }
    }

    fun restoreCustomerDisplayState() {
        displaySession.finish()?.let(customerDisplayManager::updateState)
    }

    private fun handlePaymentEvent(event: TapToPaySdkEvent) {
        Log.d("TapToPay", "Received payment event: ${event::class.java.simpleName}")

        when (event) {
            TapToPaySdkEvent.CardRequested -> {
                _status.update { "Waiting for card..." }
                customerDisplayManager.updateState(CustomerDisplayState.TapToPayCardRequested)
            }

            TapToPaySdkEvent.CardPresented -> {
                _status.update { "Card presented" }
                customerDisplayManager.updateState(
                    CustomerDisplayState.TapToPayProcessing("Card detected. Processing payment...")
                )
            }

            TapToPaySdkEvent.CvmRequested -> {
                _status.update { "Cardholder verification requested" }
                customerDisplayManager.updateState(
                    CustomerDisplayState.TapToPayProcessing("Follow the instructions on your card or phone.")
                )
            }

            TapToPaySdkEvent.CvmPresented -> {
                _status.update { "Cardholder verification provided" }
                customerDisplayManager.updateState(
                    CustomerDisplayState.TapToPayProcessing("Verification received. Finishing payment...")
                )
            }

            is TapToPaySdkEvent.TransactionDone -> {
                val message = "Transaction successful: ${event.transactionCode}"
                _status.update { message }
                customerDisplayManager.updateState(
                    CustomerDisplayState.TapToPayProcessing("Payment approved. Finalizing receipt...")
                )
                _paymentStatus.update {
                    SumUpState.Success(
                        msg = message,
                        txCode = event.transactionCode,
                        txInfo = null,
                    )
                }
            }

            is TapToPaySdkEvent.TransactionFailed -> {
                _status.update { "Transaction failed: ${event.message}" }
                customerDisplayManager.updateState(CustomerDisplayState.TapToPayFailed(event.message))
                _paymentStatus.update { SumUpState.Failed(event.message) }
            }

            TapToPaySdkEvent.TransactionCanceled -> {
                _status.update { "Transaction canceled by user" }
                customerDisplayManager.updateState(CustomerDisplayState.TapToPayFailed("Payment canceled"))
                _paymentStatus.update {
                    SumUpState.Failed(
                        msg = "Transaction canceled by user",
                        canceled = true,
                    )
                }
            }

            TapToPaySdkEvent.PaymentFlowClosedSuccessfully -> {
                _status.update { "Payment flow closed successfully" }
            }

            TapToPaySdkEvent.TransactionResultUnknown -> {
                _status.update { "Transaction result unknown" }
                customerDisplayManager.updateState(
                    CustomerDisplayState.TapToPayFailed("Payment status unknown. Please ask staff for help.")
                )
                _paymentStatus.update {
                    SumUpState.Error(
                        msg = "Transaction result unknown. Do not charge again; ask staff to verify the payment.",
                        mayHaveCreatedCharge = true,
                    )
                }
            }
        }
    }

    private fun currentTapToPayToken(fallbackToken: String): String {
        val currentConfig = terminalConfigRepository.terminalConfigState.value
        return when (currentConfig) {
            is TerminalConfigState.Success -> {
                val currentSecrets = currentConfig.config.till?.sumupSecrets
                if (currentSecrets == null || currentSecrets.sumupApiKey.isEmpty()) {
                    Log.w("TapToPay", "No OAuth token available in config, using cached token")
                    fallbackToken
                } else {
                    val expiresAt = currentSecrets.sumupApiKeyExpiresAt
                    if (expiresAt != null) {
                        val expiresInMinutes = java.time.Duration.between(java.time.OffsetDateTime.now(), expiresAt).toMinutes()
                        if (expiresInMinutes < 5) {
                            scope.launch(Dispatchers.IO) {
                                terminalConfigRepository.fetchConfig(keepTrying = false)
                            }
                        }
                    }
                    currentSecrets.sumupApiKey
                }
            }

            else -> {
                Log.w("TapToPay", "Terminal config not available, using cached token")
                fallbackToken
            }
        }
    }

    private suspend fun fetchConfig(): SumUpConfigState {
        return when (val terminalConfig = terminalConfigRepository.terminalConfigState.value) {
            is TerminalConfigState.Success -> {
                val cfg = terminalConfig.config
                val tillConfig = cfg.till
                if (!isTapToPayEnabledForTill(tillConfig?.tapToPayEnabled, tillConfig?.tapToPayAvailable)) {
                    return SumUpConfigState.Error("tap to pay not enabled for the active till profile")
                }
                val secrets = tillConfig?.sumupSecrets ?: return SumUpConfigState.Error("no terminal ec secrets in config")
                if (!secrets.sumupAffiliateKey.startsWith("sup_afk")) {
                    return SumUpConfigState.Error("invalid affiliate key: '${secrets.sumupAffiliateKey}'")
                }
                if (secrets.sumupMerchantCode.isBlank()) {
                    return SumUpConfigState.Error("missing merchant code in terminal config")
                }

                SumUpConfigState.OK(
                    SumUpConfig(
                        affiliateKey = secrets.sumupAffiliateKey,
                        apiKey = secrets.sumupApiKey,
                        merchantCode = secrets.sumupMerchantCode,
                        terminal = ECTerminalConfig(
                            name = cfg.name,
                            id = cfg.id.toString(),
                            eventName = cfg.eventName,
                            enableCardPayment = tillConfig.enableCardPayment,
                        ),
                    ),
                )
            }

            else -> SumUpConfigState.Error("no terminal configuration for ec")
        }
    }

}

internal data class TapToPaySessionIdentity(
    val environment: String,
    val merchantCode: String,
)

internal fun shouldReinitializeTapToPay(
    isInitialized: Boolean,
    currentIdentity: TapToPaySessionIdentity?,
    requestedIdentity: TapToPaySessionIdentity,
): Boolean = isInitialized && currentIdentity != requestedIdentity

internal class TapToPayDisplaySession {
    private var previousState: CustomerDisplayState? = null
    private var active = false

    fun begin(currentState: CustomerDisplayState) {
        previousState = currentState
        active = true
    }

    fun finish(): CustomerDisplayState? {
        if (!active) {
            return null
        }
        val stateToRestore = previousState ?: CustomerDisplayState.Welcome
        previousState = null
        active = false
        return stateToRestore
    }
}
