package de.stustapay.stustapay.repository

import de.stustapay.api.models.CompletedSale
import de.stustapay.api.models.NewSale
import de.stustapay.api.models.Order
import de.stustapay.api.models.PendingSale
import de.stustapay.libssp.net.Response
import de.stustapay.stustapay.netsource.SaleRemoteDataSource
import java.util.UUID
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class SaleRepository @Inject constructor(
    private val saleRemoteDataSource: SaleRemoteDataSource,
    val offlineSales: de.stustapay.stustapay.offline.OfflineSalesRepository,
) {
    suspend fun checkSale(newSale: NewSale): Response<PendingSale> {
        if (offlineSales.offline.value && newSale.paymentMethod == de.stustapay.api.models.PaymentMethod.tag) return offlineSales.check(newSale)
        val prepared = newSale.paymentMethod == de.stustapay.api.models.PaymentMethod.tag &&
            offlineSales.restoredConfig() != null
        val response = de.stustapay.stustapay.net.withOfflineRecoveryDeadline(prepared) {
            saleRemoteDataSource.checkSale(newSale)
        }
        return if (response is Response.Error.Request && de.stustapay.stustapay.offline.isOfflineTransportFailure(response)) offlineSales.check(newSale) else response
    }

    suspend fun bookSale(newSale: NewSale): Response<CompletedSale> {
        return offlineSales.book(newSale)
    }

    suspend fun registerPendingSale(newSale: NewSale): Response<PendingSale> {
        return saleRemoteDataSource.registerPendingSale(newSale)
    }

    suspend fun cancelPendingSale(orderUUID: UUID): Response<Unit> {
        return saleRemoteDataSource.cancelPendingSale(orderUUID)
    }

    suspend fun listSales(): Response<List<Order>> {
        return saleRemoteDataSource.listSales()
    }

    suspend fun cancelSale(id: Int): Response<Unit> {
        return saleRemoteDataSource.cancelSale(id)
    }
}
