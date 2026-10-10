package de.stustapay.stustapay.ec

import android.content.Context
import com.sumup.taptopay.TapToPay
import com.sumup.taptopay.TapToPayApiProvider
import com.sumup.taptopay.auth.AuthTokenProvider
import com.sumup.taptopay.payment.domain.model.api.CheckoutData
import com.sumup.taptopay.payment.domain.model.api.PaymentEvent
import dagger.Binds
import dagger.Module
import dagger.hilt.InstallIn
import dagger.hilt.components.SingletonComponent
import javax.inject.Inject
import javax.inject.Singleton
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map

@Singleton
class SumUpTapToPaySdkGateway @Inject constructor() : TapToPaySdkGateway {
    override val isAvailable: Boolean = true

    private var tapToPay: TapToPay? = null

    override suspend fun initialize(
        context: Context,
        tokenProvider: () -> String,
    ): Result<Unit> {
        val authTokenProvider = object : AuthTokenProvider {
            override fun getAccessToken(): String = tokenProvider()
        }
        val instance = TapToPayApiProvider.provide(context.applicationContext)
        val result = instance.init(authTokenProvider)
        if (result.isSuccess) {
            tapToPay = instance
        } else {
            tapToPay = null
        }
        return result
    }

    override suspend fun tearDown(): Result<Unit> {
        val instance = tapToPay ?: return Result.success(Unit)
        val result = instance.tearDown()
        if (result.isSuccess) {
            tapToPay = null
        }
        return result
    }

    override fun startPayment(
        totalAmount: Long,
        clientUniqueTransactionId: String,
    ): Flow<TapToPaySdkEvent> {
        val instance = checkNotNull(tapToPay) { "Tap To Pay SDK has not been initialized" }
        val checkoutData = CheckoutData(
            totalAmount = totalAmount,
            tipsAmount = null,
            vatAmount = null,
            clientUniqueTransactionId = clientUniqueTransactionId,
            customItems = emptyList(),
            priceItems = emptyList(),
            products = emptyList(),
            processCardAs = null,
            affiliateData = null,
        )
        return instance.startPayment(checkoutData, false).map(::mapPaymentEvent)
    }

    private fun mapPaymentEvent(event: PaymentEvent): TapToPaySdkEvent = when (event) {
        PaymentEvent.CardRequested -> TapToPaySdkEvent.CardRequested
        PaymentEvent.CardPresented -> TapToPaySdkEvent.CardPresented
        PaymentEvent.CVMRequested -> TapToPaySdkEvent.CvmRequested
        PaymentEvent.CVMPresented -> TapToPaySdkEvent.CvmPresented
        is PaymentEvent.TransactionDone -> TapToPaySdkEvent.TransactionDone(event.paymentOutput.txCode)
        is PaymentEvent.TransactionFailed -> TapToPaySdkEvent.TransactionFailed(
            event.tapToPayException?.message
                ?: event.tapToPayException?.toString()
                ?: "Transaction failed"
        )
        is PaymentEvent.TransactionCanceled -> TapToPaySdkEvent.TransactionCanceled
        is PaymentEvent.PaymentFlowClosedSuccessfully -> TapToPaySdkEvent.PaymentFlowClosedSuccessfully
        is PaymentEvent.TransactionResultUnknown -> TapToPaySdkEvent.TransactionResultUnknown
    }
}

@Module
@InstallIn(SingletonComponent::class)
abstract class TapToPaySdkModule {
    @Binds
    @Singleton
    abstract fun bindTapToPaySdkGateway(implementation: SumUpTapToPaySdkGateway): TapToPaySdkGateway
}
