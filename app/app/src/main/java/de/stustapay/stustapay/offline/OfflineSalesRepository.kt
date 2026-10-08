package de.stustapay.stustapay.offline

import android.content.Context
import android.os.SystemClock
import androidx.room.withTransaction
import androidx.work.*
import com.ionspin.kotlin.bignum.integer.toBigInteger
import com.ionspin.kotlin.bignum.serialization.kotlinx.biginteger.bigIntegerhumanReadableSerializerModule
import dagger.hilt.android.EntryPointAccessors
import dagger.hilt.EntryPoint
import dagger.hilt.InstallIn
import dagger.hilt.android.qualifiers.ApplicationContext
import dagger.hilt.components.SingletonComponent
import de.stustapay.api.models.*
import de.stustapay.libssp.net.Response
import de.stustapay.libssp.util.offsetDateTimeSerializerModule
import de.stustapay.libssp.util.uuidSerializersModule
import de.stustapay.stustapay.model.RegistrationState
import de.stustapay.stustapay.net.TerminalApiAccessor
import de.stustapay.stustapay.netsource.SaleRemoteDataSource
import de.stustapay.stustapay.repository.RegistrationRepositoryInner
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.flow
import kotlinx.coroutines.flow.collect
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.serialization.encodeToString
import kotlinx.serialization.decodeFromString
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json
import kotlinx.serialization.modules.SerializersModule
import java.time.OffsetDateTime
import java.util.UUID
import java.util.concurrent.TimeUnit
import javax.inject.Inject
import javax.inject.Singleton

internal val journalJson = Json {
    ignoreUnknownKeys = true
    serializersModule = SerializersModule {
        include(bigIntegerhumanReadableSerializerModule)
        include(uuidSerializersModule)
        include(offsetDateTimeSerializerModule)
    }
}

@Serializable
private data class RegisteredTerminalIdentity(
    val token: String,
    val apiUrl: String,
    val source: String,
    val managedConfigDisabled: Boolean,
)

private fun registrationIdentity(state: RegistrationState.Registered): String = journalJson.encodeToString(
    RegisteredTerminalIdentity(
        token = state.token,
        apiUrl = state.apiUrl,
        source = state.source.name,
        managedConfigDisabled = state.managedConfigDisabled,
    )
)

@Singleton
class OfflineSalesRepository @Inject constructor(
    private val journal: SalesJournal,
    private val api: TerminalApiAccessor,
    private val remote: SaleRemoteDataSource,
    private val registration: RegistrationRepositoryInner,
    @ApplicationContext private val context: Context,
) {
    private val mutex = Mutex()
    private val syncMutex = Mutex()
    private var config: TerminalConfig? = null
    private var user: CurrentUser? = null
    private var started = false
    val pendingCount = journal.dao.pending()
    val legacyNeedsOwner = journal.dao.legacyNeedsOwner()
    val onlineAuthenticated = MutableStateFlow(false)
    val offline = MutableStateFlow(false)
    val lastOfflineSale = MutableStateFlow<UUID?>(null)
    private val _status = MutableStateFlow(OfflineStatus())
    val status = _status.asStateFlow()

    fun start() {
        if (started) return
        started = true
        WorkManager.getInstance(context).enqueueUniquePeriodicWork("sales-journal-periodic", ExistingPeriodicWorkPolicy.KEEP,
            PeriodicWorkRequestBuilder<JournalSyncWorker>(15, TimeUnit.MINUTES)
                .setConstraints(Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build()).build())
        CoroutineScope(SupervisorJob() + Dispatchers.IO).launch {
            while (isActive) {
                try { synchronize() } catch (e: CancellationException) { throw e } catch (_: Exception) { }
                delay(5 * 60 * 1000L)
            }
        }
        CoroutineScope(SupervisorJob() + Dispatchers.IO).launch {
            val ticks = flow { while (currentCoroutineContext().isActive) { emit(Unit); delay(1000) } }
            combine(journal.dao.observeSales(), ticks) { rows, _ -> rows }.collect { rows ->
                val pending = rows.count { it.state in setOf("waiting", "offline", "clarification") }
                try {
                    val (preparation, snapshot) = mutex.withLock { validPreparation(persistClock = false) }
                    val budgets = remainingTillBudgets(snapshot.id.toString(), snapshot.rules.saleTill, snapshot.rules.returnTill, rows)
                    val serverNow = snapshot.serverTime.plusNanos((SystemClock.elapsedRealtime() - preparation.receivedElapsed) * 1_000_000)
                    val seconds = java.time.Duration.between(serverNow, snapshot.validUntil).seconds.coerceAtLeast(0)
                    _status.value = OfflineStatus(offline.value, true, seconds, budgets.first, budgets.second, pending,
                        snapshot.buttons.map { Math.toIntExact(it.id) }.toSet())
                } catch (e: CancellationException) { throw e } catch (_: Exception) {
                    _status.value = OfflineStatus(offline.value, false, null, null, null, pending)
                }
            }
        }
    }
    private fun schedule() {
        WorkManager.getInstance(context).enqueueUniqueWork("sales-journal-sync", ExistingWorkPolicy.KEEP,
            OneTimeWorkRequestBuilder<JournalSyncWorker>()
                .setConstraints(Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build()).build())
    }
    fun rememberConfig(value: TerminalConfig) { config = value }
    suspend fun rememberUser(value: CurrentUser) {
        mutex.withLock {
            val prior = journal.dao.preparation()
            val priorUser = prior?.let { journalJson.decodeFromString<CurrentUser>(it.user) }
            if (priorUser != null && (priorUser.id != value.id || priorUser.activeRoleId != value.activeRoleId)) journal.dao.revoke()
            user = value
            onlineAuthenticated.value = true
        }
        start()
        synchronize()
    }
    suspend fun revoke() = mutex.withLock { user = null; onlineAuthenticated.value = false; journal.dao.revoke() }
    suspend fun hasUnresolved() = journal.hasUnresolved()
    private suspend fun validPreparation(persistClock: Boolean = true): Pair<JournalPreparation, PreparedOfflineSnapshot> {
        val prep = journal.dao.preparation() ?: error("Offline: preparation is missing")
        require(!prep.revoked) { "Offline: operator authorization ended" }
        val stored = registration.currentStoredState()
        require(stored is RegistrationState.Registered && prep.registration == registrationIdentity(stored)) { "Offline: terminal registration changed" }
        val snapshot = journalJson.decodeFromString<PreparedOfflineSnapshot>(prep.payload)
        val wall = System.currentTimeMillis()
        val elapsed = SystemClock.elapsedRealtime()
        val boot = android.provider.Settings.Global.getInt(context.contentResolver, android.provider.Settings.Global.BOOT_COUNT, -1)
        require(boot >= 0 && prep.bootCount >= 0) { "Offline: cannot verify device clock" }
        require(wall >= prep.lastWall - 1000) { "Offline: clock moved backwards" }
        if (boot == prep.bootCount) {
            require(elapsed >= prep.lastElapsed) { "Offline: monotonic clock changed" }
            require(kotlin.math.abs((wall - prep.lastWall) - (elapsed - prep.lastElapsed)) < 60_000) { "Offline: clock changed" }
        }
        val serverNow = snapshot.serverTime.plusNanos(
            (if (boot == prep.bootCount) elapsed - prep.receivedElapsed else wall - prep.receivedWall) * 1_000_000)
        require(!serverNow.isAfter(snapshot.validUntil) && wall >= prep.receivedWall - 1000) { "Offline: preparation expired" }
        val updated = prep.copy(lastWall = wall, lastElapsed = elapsed, bootCount = boot,
            receivedElapsed = if (boot == prep.bootCount) prep.receivedElapsed else elapsed - (wall - prep.receivedWall))
        if (persistClock) journal.dao.prepare(updated)
        return updated to snapshot
    }
    suspend fun restoredConfig(): TerminalConfig? = mutex.withLock {
        try { journalJson.decodeFromString(validPreparation().first.config) }
        catch (e: CancellationException) { throw e }
        catch (_: Exception) { null }
    }
    suspend fun restoredUser(): CurrentUser? = mutex.withLock {
        try {
            val restored = journalJson.decodeFromString<CurrentUser>(validPreparation().first.user)
            offline.value = true
            restored
        } catch (e: CancellationException) { throw e }
        catch (_: Exception) { null }
    }
    suspend fun check(sale: NewSale): Response<PendingSale> = mutex.withLock {
        try {
            val snapshot = validPreparation().second
            offline.value = true
            Response.OK(validateOffline(snapshot, sale, journal.dao.sales().filter { it.uuid != sale.uuid.toString() }).pending)
        } catch (e: CancellationException) { throw e } catch (e: Exception) { Response.Error.Service.Generic(e.message ?: "Offline unavailable") }
    }
    suspend fun book(sale: NewSale): Response<CompletedSale> = mutex.withLock {
        lastOfflineSale.value = null
        var row = journal.dao.sale(sale.uuid.toString())
        val payload = journalJson.encodeToString(sale)
        if (row != null) {
            if (row.payload != payload) return@withLock Response.Error.Service.Generic("Sale UUID contents changed")
            if (row.state == "booked" && row.result != null) return@withLock Response.OK(journalJson.decodeFromString(row.result))
            if (row.state == "rejected" || row.state == "clarification") return@withLock Response.Error.Service.Generic(row.message ?: "Sale requires clarification")
            if (row.offline) return@withLock offlineSuccess(row, sale)
        } else {
            journal.database.withTransaction {
                val prep = journal.dao.preparation()
                row = JournalSale(sale.uuid.toString(), payload, operatorId = user?.id?.toString(), operatorRole = user?.activeRoleId?.toString(), snapshotId = prep?.let { journalJson.decodeFromString<PreparedOfflineSnapshot>(it.payload).id.toString() },
                    sequence = (journal.dao.sales().maxOfOrNull { it.sequence } ?: 0) + 1,
                    recordedAt = OffsetDateTime.now().toString(), tagUid = sale.customerTagUid?.toString())
                journal.dao.insert(row!!)
            }
        }
        if (offline.value && sale.paymentMethod == PaymentMethod.tag && !row!!.legacy) {
            return@withLock admitOffline(row!!, sale, previouslySent = row!!.attemptedOnline)
        }
        row = row!!.copy(transferState = "sending", attemptedOnline = true)
        journal.dao.update(row!!)
        schedule()
        val prepared = sale.paymentMethod == PaymentMethod.tag && try {
            validPreparation(persistClock = false)
            true
        } catch (e: CancellationException) { throw e } catch (_: Exception) { false }
        val response = de.stustapay.stustapay.net.withOfflineRecoveryDeadline(prepared) { remote.bookSale(sale) }
        when (response) {
            is Response.OK -> {
                journal.dao.update(row!!.copy(state = "booked", transferState = "confirmed", result = journalJson.encodeToString(response.data), debitCents = cents(response.data.totalPrice).coerceAtLeast(0)))
                // Only full reconciliation plus fresh preparation exits offline mode.
                response
            }
            is Response.Error.Request -> {
                if (row!!.legacy || !isOfflineTransportFailure(response)) { schedule(); return@withLock response }
                val accepted = admitOffline(row!!, sale, previouslySent = true)
                if (accepted is Response.OK) accepted else { schedule(); response }
            }
            is Response.Error.Server, is Response.Error.BadResponse -> { schedule(); response }
            is Response.Error -> { journal.dao.update(row!!.copy(state = "rejected", transferState = "confirmed", message = response.msg())); response }
        }
    }
    private suspend fun admitOffline(original: JournalSale, sale: NewSale, previouslySent: Boolean): Response<CompletedSale> {
        var row = original
        return try {
            journal.database.withTransaction {
                require(sale.usedVouchers == 0.toBigInteger()) { "Offline: explicit voucher-free sale required" }
                val preparation = validPreparation()
                val snap = preparation.second
                val checked = validateOffline(snap, sale, journal.dao.sales().filter { it.uuid != row.uuid })
                val sameBoot = android.provider.Settings.Global.getInt(context.contentResolver, android.provider.Settings.Global.BOOT_COUNT, -1) == preparation.first.bootCount
                val duration = if (sameBoot) SystemClock.elapsedRealtime() - preparation.first.receivedElapsed else System.currentTimeMillis() - preparation.first.receivedWall
                row = row.copy(state = "offline", transferState = "queued", offline = true, snapshotId = snap.id.toString(),
                    recordedAt = snap.serverTime.plusNanos(duration * 1_000_000).toString(),
                    debitCents = checked.debit, saleCents = checked.positive, returnCents = checked.returned)
                row = row.copy(result = journalJson.encodeToString(localReceipt(checked.pending, snap, row)))
                journal.dao.update(row)
            }
            schedule()
            offlineSuccess(row, sale)
        } catch (e: CancellationException) { throw e } catch (e: Exception) {
            // An unseen local rejection is final. A possibly delivered online request must remain unresolved.
            if (!previouslySent) journal.dao.update(row.copy(state = "local_rejected", transferState = "blocked", message = e.message))
            Response.Error.Service.Generic(e.message ?: "Offline sale unavailable")
        }
    }
    private suspend fun offlineSuccess(row: JournalSale, sale: NewSale): Response<CompletedSale> {
        val receipt = row.result?.let { journalJson.decodeFromString<CompletedSale>(it) }
            ?: return Response.Error.Service.Generic("Offline receipt requires clarification")
        offline.value = true
        lastOfflineSale.value = sale.uuid
        return Response.OK(receipt)
    }
    private fun localReceipt(pending: PendingSale, snapshot: PreparedOfflineSnapshot, row: JournalSale) =
        CompletedSale(pending.uuid, pending.oldBalance, pending.newBalance,
            pending.oldVoucherBalance, pending.newVoucherBalance, pending.customerAccountId, pending.paymentMethod,
            pending.lineItems, pending.buttons, 0.toBigInteger(), OffsetDateTime.parse(row.recordedAt), snapshot.userId.toBigInteger(),
            snapshot.tillId.toBigInteger(), "", pending.usedVouchers, pending.itemCount, pending.totalPrice)

    suspend fun synchronize(): Boolean = syncMutex.withLock {
        val initialRows = mutex.withLock { journal.dao.sales() }
        for (candidate in initialRows.filter { it.state == "clarification" }) {
            val response = api.execute { it.offline()?.status(candidate.uuid) }
            if (response is Response.OK && response.data.status in setOf("dismissed", "booked", "already_booked")) {
                applyReply(candidate.uuid, response.data, requestedOffline = candidate.offline)
            }
        }
        for (candidate in initialRows.filter { it.state in setOf("waiting", "offline") }.sortedBy { it.sequence }) {
            val row = mutex.withLock {
                val current = journal.dao.sale(candidate.uuid)
                if (current == null || current.state !in setOf("waiting", "offline") || current.offline != candidate.offline) null
                else { journal.dao.update(current.copy(transferState = "sending")); current }
            } ?: continue
            val sale = journalJson.decodeFromString<NewSale>(row.payload)
            if (row.offline && row.snapshotId != null) {
                when (val res = api.execute { it.offline()?.import(OfflineImport(listOf(OfflineBooking(UUID.fromString(row.snapshotId), sale, row.sequence, OffsetDateTime.parse(row.recordedAt))))) }) {
                    is Response.OK -> res.data.results.singleOrNull()?.let { applyReply(row.uuid, it, requestedOffline = true) }
                    else -> return@withLock false
                }
            } else {
                val known = api.execute { it.offline()?.status(row.uuid) }
                if (known !is Response.OK) return@withLock false
                if (known.data.status != "not_found") {
                    applyReply(row.uuid, known.data, requestedOffline = false)
                    continue
                }
                val mayRetry = mutex.withLock {
                    val current = journal.dao.sale(row.uuid)
                    val eligible = current?.state == "waiting" && !current.offline && user != null &&
                        current.operatorId == user?.id?.toString() && current.operatorRole == user?.activeRoleId?.toString()
                    if (eligible && current != null) journal.dao.update(current.copy(attemptedOnline = true))
                    eligible
                }
                if (!mayRetry) continue
                when (val res = remote.bookSale(sale)) {
                    is Response.OK -> applyReply(row.uuid, OfflineResult(sale.uuid, "booked", res.data), requestedOffline = false)
                    is Response.Error.Request, is Response.Error.Server, is Response.Error.BadResponse -> return@withLock false
                    is Response.Error -> applyReply(row.uuid, OfflineResult(sale.uuid, "rejected", message = res.msg()), requestedOffline = false)
                }
            }
        }
        if (journal.hasUnresolved()) return@withLock false
        if (user == null) {
            val previous = journal.dao.preparation()
            if (previous != null && !previous.revoked) {
                val priorUser = journalJson.decodeFromString<CurrentUser>(previous.user)
                val res = api.execute { it.user()?.getCurrentUser() }
                if (res is Response.OK && res.data.id == priorUser.id && res.data.activeRoleId == priorUser.activeRoleId) {
                    user = res.data
                    onlineAuthenticated.value = true
                } else if (res is Response.Error.Access || res is Response.Error.Service) {
                    mutex.withLock {
                        journal.dao.revoke()
                        offline.value = false
                    }
                    return@withLock false
                }
            }
        }
        val currentUser = user ?: return@withLock true
        val currentConfig = config ?: return@withLock true
        val reg = registration.currentStoredState() as? RegistrationState.Registered ?: return@withLock true
        val requestStarted = SystemClock.elapsedRealtime()
        when (val res = api.execute { it.offline()?.prepare() }) {
            is Response.OK -> {
                if (res.data.userId != currentUser.id.toString().toLong()) return@withLock false
                val now = System.currentTimeMillis()
                mutex.withLock {
                    // A sale may have been admitted while preparation was travelling over the network.
                    if (!journal.hasUnresolved() && user?.id == currentUser.id && user?.activeRoleId == currentUser.activeRoleId) {
                        journal.dao.prepare(JournalPreparation(payload = journalJson.encodeToString(res.data), registration = registrationIdentity(reg),
                            user = journalJson.encodeToString(currentUser), config = journalJson.encodeToString(currentConfig),
                            bootCount = android.provider.Settings.Global.getInt(context.contentResolver, android.provider.Settings.Global.BOOT_COUNT, -1),
                            receivedWall = now - (SystemClock.elapsedRealtime() - requestStarted), receivedElapsed = requestStarted, lastWall = now, lastElapsed = SystemClock.elapsedRealtime()))
                        offline.value = false
                    }
                }
                true
            }
            is Response.Error.Access, is Response.Error.Service -> {
                mutex.withLock {
                    journal.dao.revoke()
                    offline.value = false
                }
                false
            }
            else -> false
        }
    }
    private suspend fun applyReply(uuid: String, reply: OfflineResult, requestedOffline: Boolean) = mutex.withLock {
        val current = journal.dao.sale(uuid) ?: return@withLock
        journal.dao.update(reconcileJournalReply(current, reply.status, reply.sale?.let { journalJson.encodeToString(it) },
            reply.message, requestedOffline, reply.sale?.let { cents(it.totalPrice).coerceAtLeast(0) }))
    }
    /** Explicit operator action; old single-request storage had no cashier attribution. */
    suspend fun retryLegacyAsCurrentOperator() {
        mutex.withLock {
            val current = user ?: return@withLock
            for (row in journal.dao.sales().filter { it.legacy && it.operatorId == null && it.state == "waiting" }) {
                journal.dao.update(row.copy(operatorId = current.id.toString(), operatorRole = current.activeRoleId?.toString()))
            }
        }
        synchronize()
    }
    suspend fun migrateLegacy(sale: NewSale) = mutex.withLock {
        if (journal.dao.sale(sale.uuid.toString()) == null) journal.dao.insert(JournalSale(sale.uuid.toString(), journalJson.encodeToString(sale), legacy = true, attemptedOnline = true,
            sequence = (journal.dao.sales().maxOfOrNull { it.sequence } ?: 0) + 1, recordedAt = OffsetDateTime.now().toString(), tagUid = sale.customerTagUid?.toString()))
        schedule()
    }
}
@EntryPoint
@InstallIn(SingletonComponent::class)
interface JournalWorkerEntryPoint { fun offlineSales(): OfflineSalesRepository }
class JournalSyncWorker(context: Context, params: WorkerParameters) : CoroutineWorker(context, params) {
    override suspend fun doWork(): Result = try {
        val repo = EntryPointAccessors.fromApplication(applicationContext, JournalWorkerEntryPoint::class.java).offlineSales()
        if (repo.synchronize()) Result.success() else Result.retry()
    } catch (e: CancellationException) { throw e } catch (_: Exception) { Result.retry() }
}

internal fun isOfflineTransportFailure(error: Response.Error.Request): Boolean {
    val cause = error.throwable ?: return false
    return cause is java.io.IOException || cause is io.ktor.client.network.sockets.ConnectTimeoutException ||
        cause is io.ktor.client.network.sockets.SocketTimeoutException || cause is io.ktor.client.plugins.HttpRequestTimeoutException
}
