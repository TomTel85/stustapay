package de.stustapay.stustapay.ec

import android.content.Context
import dagger.Binds
import dagger.Module
import dagger.hilt.InstallIn
import dagger.hilt.components.SingletonComponent
import javax.inject.Inject
import javax.inject.Singleton
import kotlinx.coroutines.flow.Flow

@Singleton
class StandardTapToPaySdkGateway @Inject constructor() : TapToPaySdkGateway {
    override val isAvailable: Boolean = false

    override suspend fun initialize(
        context: Context,
        tokenProvider: () -> String,
    ): Result<Unit> = Result.failure(IllegalStateException("Tap To Pay SDK is not included in this build"))

    override suspend fun tearDown(): Result<Unit> = Result.success(Unit)

    override fun startPayment(
        totalAmount: Long,
        clientUniqueTransactionId: String,
    ): Flow<TapToPaySdkEvent> = error("Tap To Pay SDK is not included in this build")
}

@Module
@InstallIn(SingletonComponent::class)
abstract class TapToPaySdkModule {
    @Binds
    @Singleton
    abstract fun bindTapToPaySdkGateway(implementation: StandardTapToPaySdkGateway): TapToPaySdkGateway
}
