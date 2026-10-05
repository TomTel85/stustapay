package de.stustapay.stustapay.repository

import android.app.Activity
import de.stustapay.libssp.util.waitFor
import de.stustapay.stustapay.ec.ECPayment
import de.stustapay.stustapay.ec.SumUp
import de.stustapay.stustapay.ec.SumUpState
import javax.inject.Inject
import javax.inject.Singleton


sealed interface ECPaymentResult {
    data class Success(val result: SumUpState.Success) : ECPaymentResult
    data class Failure(
        val msg: String,
        val mayHaveCreatedCharge: Boolean = false,
    ) : ECPaymentResult
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
    private val terminalConfigRepository: TerminalConfigRepository,
)
{
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
        // Refresh terminal configuration to ensure we have the latest SumUp token
        terminalConfigRepository.fetchConfig(keepTrying = false)

        // perform sumup flow
        sumUp.pay(context, ecPayment)

        val sumUpState = sumUp.paymentStatus.waitFor {
            when (it) {
                is SumUpState.Success,
                is SumUpState.Error,
                is SumUpState.Failed -> {
                    true
                }

                else -> {
                    false
                }
            }
        }

        // proceed to notify the server about the new topup.
        when (sumUpState) {
            is SumUpState.None,
            is SumUpState.Started -> {
                return ECPaymentResult.Failure("SumUp not finished? ${sumUpState.msg()}")
            }

            is SumUpState.Error -> {
                return ECPaymentResult.Failure(
                    msg = "SumUp failed: ${sumUpState.msg()}",
                    mayHaveCreatedCharge = sumUpState.mayHaveCreatedCharge,
                )
            }

            is SumUpState.Failed -> {
                return ECPaymentResult.Failure("SumUp failed: ${sumUpState.msg()}")
            }

            is SumUpState.Success -> {
                return verifiedCardPaymentResult(
                    result = sumUpState,
                    expectedTransactionId = ecPayment.id,
                    actualTransactionId = sumUpState.txInfo?.foreignTransactionId,
                )
            }
        }
    }
}
