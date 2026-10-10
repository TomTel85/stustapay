package de.stustapay.stustapay.repository

import android.app.Activity
import de.stustapay.libssp.util.waitFor
import de.stustapay.stustapay.ec.ECPayment
import de.stustapay.stustapay.ec.PaymentCapability
import de.stustapay.stustapay.ec.SumUp
import de.stustapay.stustapay.ec.SumUpState
import de.stustapay.stustapay.ec.TapToPay
import de.stustapay.stustapay.ec.isTapToPayEnabledForTill
import kotlinx.coroutines.delay
import javax.inject.Inject
import javax.inject.Singleton

sealed interface ECPaymentResult {
    data class Success(val result: SumUpState.Success) : ECPaymentResult
    data class Failure(
        val msg: String,
        val mayHaveCreatedCharge: Boolean = false,
    ) : ECPaymentResult
}

internal sealed interface TapToPayResolution {
    data object FallbackToReader : TapToPayResolution
    data class Complete(val result: ECPaymentResult) : TapToPayResolution
}

internal fun resolveTapToPayState(paymentState: SumUpState): TapToPayResolution = when (paymentState) {
    is SumUpState.None,
    is SumUpState.Started -> TapToPayResolution.Complete(
        ECPaymentResult.Failure("Tap To Pay not finished? ${paymentState.msg()}")
    )

    is SumUpState.Failed -> TapToPayResolution.Complete(
        ECPaymentResult.Failure(
            msg = if (paymentState.canceled) {
                "Payment canceled by user"
            } else {
                "Tap To Pay failed: ${paymentState.msg}"
            },
        )
    )

    is SumUpState.Error -> {
        if (paymentState.readerFallbackAllowed && !paymentState.mayHaveCreatedCharge) {
            TapToPayResolution.FallbackToReader
        } else {
            TapToPayResolution.Complete(
                ECPaymentResult.Failure(
                    msg = "Tap To Pay failed: ${paymentState.msg}",
                    mayHaveCreatedCharge = paymentState.mayHaveCreatedCharge,
                )
            )
        }
    }

    is SumUpState.Success -> TapToPayResolution.Complete(ECPaymentResult.Success(paymentState))
}

internal fun verifiedCardPaymentResult(
    result: SumUpState.Success,
    expectedTransactionId: String,
    actualTransactionId: String?,
): ECPaymentResult {
    if (expectedTransactionId.isNotBlank() && actualTransactionId == expectedTransactionId) {
        return ECPaymentResult.Success(result)
    }

    // A success for another payment (or without an ID) cannot safely be booked or cancelled.
    return ECPaymentResult.Failure(
        msg = "Card payment could not be matched to this order. Check the payment status before retrying.",
        mayHaveCreatedCharge = true,
    )
}

@Singleton
class ECPaymentRepository @Inject constructor(
    private val sumUp: SumUp,
    private val tapToPay: TapToPay,
    private val terminalConfigRepository: TerminalConfigRepository,
) {
    private fun isTapToPayEnabledForTill(): Boolean {
        val currentConfig = terminalConfigRepository.terminalConfigState.value
        if (currentConfig !is TerminalConfigState.Success) {
            return false
        }
        val tillConfig = currentConfig.config.till
        return isTapToPayEnabledForTill(tillConfig?.tapToPayEnabled, tillConfig?.tapToPayAvailable)
    }

    fun isReady(): Boolean {
        return sumUp.isLoggedIn()
    }

    suspend fun startCardReaderSetup(_context: Activity): String? {
        return try {
            if (!sumUp.reactivateConnectedReader()) {
                return "Could not activate the connected card reader."
            }
            when (val state = sumUp.paymentStatus.value) {
                is SumUpState.Error -> state.msg
                is SumUpState.Failed -> state.msg
                else -> null
            }
        } catch (exc: Exception) {
            exc.message ?: "EC reader setup could not be started."
        }
    }

    suspend fun reactivateReader(): String? {
        return try {
            if (sumUp.reactivateConnectedReader()) {
                null
            } else {
                "Could not activate the connected card reader."
            }
        } catch (exc: Exception) {
            exc.message ?: "EC reader could not be activated."
        }
    }

    suspend fun wakeup() {
        sumUp.wakeup()
    }

    suspend fun pay(context: Activity, ecPayment: ECPayment): ECPaymentResult {
        terminalConfigRepository.fetchConfig(keepTrying = false)

        return if (PaymentCapability.supportsTapToPay(context) && isTapToPayEnabledForTill()) {
            payWithTapToPay(context, ecPayment)
        } else {
            payWithCardReader(context, ecPayment)
        }
    }

    private suspend fun payWithTapToPay(context: Activity, ecPayment: ECPayment): ECPaymentResult {
        if (!tapToPay.initialize(context)) {
            android.util.Log.w(
                "ECPaymentRepository",
                "Tap To Pay initialization failed, falling back to card reader: ${tapToPay.status.value}",
            )
            return payWithCardReader(context, ecPayment)
        }

        tapToPay.pay(ecPayment)

        val paymentState = tapToPay.paymentStatus.waitFor {
            when (it) {
                is SumUpState.Success,
                is SumUpState.Error,
                is SumUpState.Failed -> true
                else -> false
            }
        }

        if (paymentState is SumUpState.Failed || paymentState is SumUpState.Error) {
            delay(1200)
        }
        tapToPay.restoreCustomerDisplayState()

        return when (val resolution = resolveTapToPayState(paymentState)) {
            TapToPayResolution.FallbackToReader -> payWithCardReader(context, ecPayment)
            is TapToPayResolution.Complete -> resolution.result
        }
    }

    private suspend fun payWithCardReader(context: Activity, ecPayment: ECPayment): ECPaymentResult {
        sumUp.pay(context, ecPayment)

        val sumUpState = sumUp.paymentStatus.waitFor {
            when (it) {
                is SumUpState.Success,
                is SumUpState.Error,
                is SumUpState.Failed -> true
                else -> false
            }
        }

        return when (sumUpState) {
            is SumUpState.None,
            is SumUpState.Started -> ECPaymentResult.Failure("SumUp not finished? ${sumUpState.msg()}")

            is SumUpState.Error -> ECPaymentResult.Failure(
                msg = "SumUp failed: ${sumUpState.msg()}",
                mayHaveCreatedCharge = sumUpState.mayHaveCreatedCharge,
            )

            is SumUpState.Failed -> ECPaymentResult.Failure("SumUp failed: ${sumUpState.msg()}")
            is SumUpState.Success -> verifiedCardPaymentResult(
                result = sumUpState,
                expectedTransactionId = ecPayment.id,
                actualTransactionId = sumUpState.txInfo?.foreignTransactionId,
            )
        }
    }
}
