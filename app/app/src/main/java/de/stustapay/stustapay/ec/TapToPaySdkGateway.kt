package de.stustapay.stustapay.ec

import android.content.Context
import kotlinx.coroutines.flow.Flow

/**
 * Build-variant boundary for the proprietary SumUp Tap-to-Pay SDK.
 *
 * The standard variant binds an unavailable implementation, while the Tap-to-Pay
 * variant compiles directly against the SDK and maps its events into these stable
 * application-owned types.
 */
interface TapToPaySdkGateway {
    val isAvailable: Boolean

    suspend fun initialize(
        context: Context,
        tokenProvider: () -> String,
    ): Result<Unit>

    suspend fun tearDown(): Result<Unit>

    fun startPayment(
        totalAmount: Long,
        clientUniqueTransactionId: String,
    ): Flow<TapToPaySdkEvent>
}

sealed interface TapToPaySdkEvent {
    data object CardRequested : TapToPaySdkEvent
    data object CardPresented : TapToPaySdkEvent
    data object CvmRequested : TapToPaySdkEvent
    data object CvmPresented : TapToPaySdkEvent
    data class TransactionDone(val transactionCode: String) : TapToPaySdkEvent
    data class TransactionFailed(val message: String) : TapToPaySdkEvent
    data object TransactionCanceled : TapToPaySdkEvent
    data object PaymentFlowClosedSuccessfully : TapToPaySdkEvent
    data object TransactionResultUnknown : TapToPaySdkEvent
}
