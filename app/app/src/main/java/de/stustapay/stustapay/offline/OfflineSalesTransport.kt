package de.stustapay.stustapay.offline

import de.stustapay.api.models.CompletedSale
import de.stustapay.api.models.CurrentUser
import de.stustapay.api.models.NewSale
import de.stustapay.api.models.PendingSale
import de.stustapay.libssp.net.Response
import de.stustapay.stustapay.net.TerminalApiAccessor
import de.stustapay.stustapay.netsource.SaleRemoteDataSource

/** Network boundary kept separate from local admission and durable journal state. */
internal interface OfflineSalesTransport {
    suspend fun check(sale: NewSale): Response<PendingSale>
    suspend fun book(sale: NewSale): Response<CompletedSale>
    suspend fun prepare(): Response<PreparedOfflineSnapshot>
    suspend fun import(payload: OfflineImport): Response<OfflineResults>
    suspend fun status(uuid: String): Response<OfflineResult>
    suspend fun currentUser(): Response<CurrentUser>
}

internal class AndroidOfflineSalesTransport(
    private val api: TerminalApiAccessor,
    private val remote: SaleRemoteDataSource,
) : OfflineSalesTransport {
    override suspend fun check(sale: NewSale) = remote.checkSale(sale)
    override suspend fun book(sale: NewSale) = remote.bookSale(sale)
    override suspend fun prepare() = api.execute { it.offline()?.prepare() }
    override suspend fun import(payload: OfflineImport) = api.execute { it.offline()?.import(payload) }
    override suspend fun status(uuid: String) = api.execute { it.offline()?.status(uuid) }
    override suspend fun currentUser() = api.execute { it.user()?.getCurrentUser() }
}
