package de.stustapay.stustapay.repository

import android.app.Activity
import android.content.Context
import dagger.hilt.android.qualifiers.ApplicationContext
import de.stustapay.api.models.PendingOrderStatus
import de.stustapay.libssp.net.Response
import de.stustapay.libssp.util.waitFor
import de.stustapay.stustapay.R
import de.stustapay.stustapay.ec.ECPayment
import de.stustapay.stustapay.ec.PaymentCapability
import de.stustapay.stustapay.ec.SumUp
import de.stustapay.stustapay.ec.SumUpState
import de.stustapay.stustapay.ec.TapToPay
import de.stustapay.stustapay.ec.isTapToPayEnabledForTill
import de.stustapay.stustapay.net.TerminalApiAccessor
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext
import kotlinx.coroutines.withTimeoutOrNull
import java.util.UUID
import javax.inject.Inject
import javax.inject.Singleton

sealed interface ECPaymentResult {
    data class Success(val result: SumUpState.Success) : ECPaymentResult
    data class Failure(
        val msg: String,
        val mayHaveCreatedCharge: Boolean = false,
        val previousPaymentBooked: Boolean = false,
        val retryWithNewId: Boolean = false,
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

internal fun pendingPaymentMayHaveLaunched(hasPayment: Boolean, sdkLaunched: Boolean?): Boolean =
    hasPayment && sdkLaunched != false

internal fun shouldRetryWithNewPaymentId(pendingId: String, currentId: String, sdkLaunched: Boolean?): Boolean =
    pendingId == currentId && !pendingPaymentMayHaveLaunched(true, sdkLaunched)

internal fun wasPaymentReleased(releasedId: String?, paymentId: String): Boolean = releasedId == paymentId

@Singleton
class ECPaymentRepository @Inject constructor(
    private val sumUp: SumUp,
    private val tapToPay: TapToPay,
    private val terminalConfigRepository: TerminalConfigRepository,
    private val api: TerminalApiAccessor,
    @ApplicationContext private val appContext: Context,
) {
    private val paymentMutex = Mutex()
    private val pendingPayment by lazy { appContext.getSharedPreferences("pending-card-payment", Context.MODE_PRIVATE) }

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

    suspend fun pay(context: Activity, ecPayment: ECPayment, register: suspend () -> Boolean): ECPaymentResult? {
        if (!paymentMutex.tryLock()) return ECPaymentResult.Failure(appContext.getString(R.string.card_payment_busy), true)
        try {
            val pendingId = pendingPayment.getString("uuid", null)
            if (wasPaymentReleased(pendingPayment.getString("released_uuid", null), ecPayment.id)) {
                return ECPaymentResult.Failure(
                    appContext.getString(R.string.card_payment_released_retry),
                    mayHaveCreatedCharge = true,
                    retryWithNewId = true,
                )
            }
            if (pendingId != null) {
                val launchFlag = if (pendingPayment.contains("sdk_launched")) {
                    pendingPayment.getBoolean("sdk_launched", true)
                } else {
                    null // Older app versions stored no launch state, so treat their attempts as ambiguous.
                }
                if (!pendingPaymentMayHaveLaunched(true, launchFlag)) {
                    storePendingPayment(null)
                    if (shouldRetryWithNewPaymentId(pendingId, ecPayment.id, launchFlag)) return ECPaymentResult.Failure(
                        appContext.getString(R.string.card_payment_prelaunch_retry),
                        retryWithNewId = true,
                    )
                } else {
                    val orderUuid = runCatching { UUID.fromString(pendingId) }.getOrNull()
                        ?: return ECPaymentResult.Failure(
                            appContext.getString(R.string.card_payment_pending, pendingId), true,
                        )
                    val response = api.execute { it.order()?.getCardPaymentStatus(orderUuid) }
                    when ((response as? Response.OK)?.data) {
                        PendingOrderStatus.booked -> {
                            storePendingPayment(null)
                            return ECPaymentResult.Failure(
                                appContext.getString(R.string.card_payment_previous_booked, pendingId),
                                mayHaveCreatedCharge = true, previousPaymentBooked = true,
                            )
                        }
                        PendingOrderStatus.cancelled -> {
                            storePendingPayment(null)
                            if (pendingId == ecPayment.id) return ECPaymentResult.Failure(
                                appContext.getString(R.string.card_payment_previous_cancelled),
                                mayHaveCreatedCharge = true, retryWithNewId = true,
                            )
                        }
                        else -> return ECPaymentResult.Failure(
                            appContext.getString(R.string.card_payment_pending, pendingId), true,
                        )
                    }
                }
            }

            terminalConfigRepository.fetchConfig(keepTrying = false)
            if (!storePendingPayment(ecPayment.id, sdkLaunched = false)) return ECPaymentResult.Failure(
                appContext.getString(R.string.card_payment_storage_failed),
            )
            if (!register()) {
                // The backend may have registered the UUID before the response was lost.
                return null
            }
            val result = try {
                withTimeoutOrNull(6 * 60 * 1000L) {
                    if (PaymentCapability.supportsTapToPay(context) && isTapToPayEnabledForTill()) {
                        payWithTapToPay(context, ecPayment) { markSdkLaunched(ecPayment.id) }
                    } else {
                        payWithCardReader(context, ecPayment) { markSdkLaunched(ecPayment.id) }
                    }
                }
            } catch (e: CancellationException) {
                throw e
            } catch (_: Exception) {
                null
            } ?: if (pendingPayment.getBoolean("sdk_launched", true)) {
                ECPaymentResult.Failure(appContext.getString(R.string.card_payment_pending, ecPayment.id), true)
            } else {
                ECPaymentResult.Failure(appContext.getString(R.string.card_payment_not_started))
            }
            if (result is ECPaymentResult.Failure && !result.mayHaveCreatedCharge) storePendingPayment(null)
            return result
        } finally {
            paymentMutex.unlock()
        }
    }

    suspend fun confirmBooking(orderUuid: UUID) = paymentMutex.withLock {
        if (pendingPayment.getString("uuid", null) == orderUuid.toString()) storePendingPayment(null)
    }

    suspend fun ambiguousPaymentIdForOperator(): String? = paymentMutex.withLock {
        withContext(Dispatchers.IO) {
            val id = pendingPayment.getString("uuid", null) ?: return@withContext null
            val sdkLaunched = if (pendingPayment.contains("sdk_launched")) {
                pendingPayment.getBoolean("sdk_launched", true)
            } else {
                null
            }
            id.takeIf { pendingPaymentMayHaveLaunched(true, sdkLaunched) }
        }
    }

    suspend fun releaseAmbiguousPaymentAfterProviderCheck(paymentId: String): Boolean = paymentMutex.withLock {
        withContext(Dispatchers.IO) {
            if (pendingPayment.getString("uuid", null) != paymentId) return@withContext false
            val sdkLaunched = if (pendingPayment.contains("sdk_launched")) {
                pendingPayment.getBoolean("sdk_launched", true)
            } else {
                null
            }
            if (!pendingPaymentMayHaveLaunched(true, sdkLaunched)) return@withContext false
            pendingPayment.edit()
                .putString("released_uuid", paymentId)
                .remove("uuid")
                .remove("sdk_launched")
                .commit()
        }
    }

    private suspend fun storePendingPayment(uuid: String?, sdkLaunched: Boolean = false): Boolean = withContext(Dispatchers.IO) {
        val editor = pendingPayment.edit()
        if (uuid == null) {
            editor.remove("uuid").remove("sdk_launched")
        } else {
            editor.putString("uuid", uuid).putBoolean("sdk_launched", sdkLaunched)
        }
        editor.commit()
    }

    private fun markSdkLaunched(paymentId: String): Boolean =
        if (pendingPayment.getString("uuid", null) == paymentId) {
            pendingPayment.edit().putBoolean("sdk_launched", true).commit()
        } else {
            false
        }

    private suspend fun payWithTapToPay(
        context: Activity,
        ecPayment: ECPayment,
        beforeSdkLaunch: () -> Boolean,
    ): ECPaymentResult {
        if (!tapToPay.initialize(context)) {
            android.util.Log.w(
                "ECPaymentRepository",
                "Tap To Pay initialization failed, falling back to card reader: ${tapToPay.status.value}",
            )
            return payWithCardReader(context, ecPayment, beforeSdkLaunch)
        }

        val paymentState = try {
            tapToPay.pay(ecPayment, beforeSdkLaunch).also {
                if (it is SumUpState.Failed || it is SumUpState.Error) delay(1200)
            }
        } finally {
            tapToPay.restoreCustomerDisplayState()
        }

        return when (val resolution = resolveTapToPayState(paymentState)) {
            TapToPayResolution.FallbackToReader -> payWithCardReader(context, ecPayment, beforeSdkLaunch)
            is TapToPayResolution.Complete -> resolution.result
        }
    }

    private suspend fun payWithCardReader(
        context: Activity,
        ecPayment: ECPayment,
        beforeSdkLaunch: () -> Boolean,
    ): ECPaymentResult {
        sumUp.pay(context, ecPayment, beforeSdkLaunch)

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
