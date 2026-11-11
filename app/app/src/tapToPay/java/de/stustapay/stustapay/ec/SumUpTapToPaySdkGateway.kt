package de.stustapay.stustapay.ec

import android.content.Context
import android.util.Log
import com.sumup.taptopay.TapToPay
import com.sumup.taptopay.TapToPayApiProvider
import com.sumup.taptopay.auth.AuthTokenProvider
import com.sumup.taptopay.exception.api.PaymentException
import com.sumup.taptopay.exception.api.TapToPayException
import com.sumup.taptopay.payment.domain.model.api.AffiliateModel
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
        affiliateKey: String,
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
            affiliateData = AffiliateModel(key = affiliateKey, foreignTransactionId = clientUniqueTransactionId),
        )
        return instance.startPayment(checkoutData, false).map(::mapPaymentEvent)
    }

    private fun mapPaymentEvent(event: PaymentEvent): TapToPaySdkEvent = when (event) {
        PaymentEvent.CardRequested -> TapToPaySdkEvent.CardRequested
        PaymentEvent.CardPresented -> TapToPaySdkEvent.CardPresented
        PaymentEvent.CVMRequested -> TapToPaySdkEvent.CvmRequested
        PaymentEvent.CVMPresented -> TapToPaySdkEvent.CvmPresented
        is PaymentEvent.TransactionDone -> TapToPaySdkEvent.TransactionDone(event.paymentOutput.txCode)
        is PaymentEvent.TransactionFailed -> {
            val exception = event.tapToPayException
            val cause = exception?.cause
            val acquiringError = exception as? PaymentException.ErrorAction
            val acquiringErrorDescription = acquiringError?.acquiringErrorDescription
                ?.replace('\n', ' ')?.replace('\r', ' ')
            Log.w(
                "TapToPay",
                "SumUp transaction failed: type=${exception?.name}, code=${exception?.code}, " +
                    "causeType=${cause?.javaClass?.simpleName}, causeCode=${(cause as? TapToPayException)?.code}, " +
                    "acquiringErrorTextId=${acquiringError?.acquiringErrorTextId}, " +
                    "acquiringErrorDescription=$acquiringErrorDescription",
            )
            TapToPaySdkEvent.TransactionFailed(exception?.message ?: exception?.toString() ?: "Transaction failed")
        }
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
