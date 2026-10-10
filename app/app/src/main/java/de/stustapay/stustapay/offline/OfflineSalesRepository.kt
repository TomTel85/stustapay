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

private class SaleAssignmentChanged(message: String) : IllegalStateException(message)

private data class SaleAssignment(
    val terminalId: String,
    val tillId: String?,
    val eventId: String?,
    val legacyEventName: String?,
    val cashRegisterId: String?,
    val mode: TerminalMode,
    val operatorId: String?,
)

private data class CheckedSaleContext(val assignment: SaleAssignment?, val registration: String?, val generation: Long)

private fun TerminalConfig.saleAssignment() = SaleAssignment(
    id.toString(), till?.id?.toString(), eventNodeId?.toString(),
    eventName.takeIf { eventNodeId == null }, till?.cashRegisterId?.toString(), mode, activeUserId?.toString(),
)

/** Names alone cannot identify an event. Old saved configurations use a conservative name fallback. */
private fun preparedAssignmentMatches(snapshot: PreparedOfflineSnapshot, prepared: TerminalConfig, current: TerminalConfig): Boolean {
    if (current.mode != TerminalMode.till || prepared.mode != TerminalMode.till ||
        current.id.toString() != snapshot.terminalId.toString() || prepared.id != current.id ||
        current.till?.id?.toString() != snapshot.tillId.toString() || prepared.till?.id != current.till?.id ||
        prepared.till?.cashRegisterId != current.till?.cashRegisterId ||
        current.activeUserId?.toString() != snapshot.userId.toString()) return false
    if (prepared.eventNodeId != null && prepared.eventNodeId.toString() != snapshot.eventNodeId.toString()) return false
    return if (current.eventNodeId != null) current.eventNodeId.toString() == snapshot.eventNodeId.toString()
    else prepared.eventNodeId == null && current.eventName == prepared.eventName && current.till?.eventName == prepared.till?.eventName
}

@Singleton
class OfflineSalesRepository private constructor(
    private val journal: SalesJournal,
    private val transport: OfflineSalesTransport,
    private val registration: suspend () -> RegistrationState,
    private val context: Context,
    private val backgroundEnabled: Boolean,
    private val availableStorage: () -> Long = { android.os.StatFs(context.filesDir.absolutePath).availableBytes },
) {
    @Inject constructor(
        journal: SalesJournal, api: TerminalApiAccessor, remote: SaleRemoteDataSource,
        registration: RegistrationRepositoryInner, @ApplicationContext context: Context,
    ) : this(journal, AndroidOfflineSalesTransport(api, remote), registration::currentStoredState, context, true)

    internal constructor(journal: SalesJournal, transport: OfflineSalesTransport,
        registration: suspend () -> RegistrationState, context: Context,
        availableStorage: () -> Long = { android.os.StatFs(context.filesDir.absolutePath).availableBytes },
    ) : this(journal, transport, registration, context, false, availableStorage)

    private val mutex = Mutex()
    private val syncMutex = Mutex()
    private var config: TerminalConfig? = null
    private var user: CurrentUser? = null
    private val authorizationGeneration = java.util.concurrent.atomic.AtomicLong()
    private var started = false
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private val checkedSnapshots = java.util.concurrent.ConcurrentHashMap<UUID, UUID>()
    private val onlineChecks = mutableSetOf<UUID>()
    private val checkedAssignments = mutableMapOf<UUID, CheckedSaleContext>()
    private suspend fun currentSaleContext() = CheckedSaleContext(config?.saleAssignment(),
        (registration() as? RegistrationState.Registered)?.let(::registrationIdentity), authorizationGeneration.get())
    fun isLocallyChecked(uuid: UUID): Boolean = checkedSnapshots.containsKey(uuid)
    private val _preparedConfig = MutableStateFlow<TerminalConfig?>(null)
    val preparedConfig = _preparedConfig.asStateFlow()
    private val connected = MutableStateFlow<Boolean?>(null)
    private val synchronizing = MutableStateFlow(false)
    val pendingCount = journal.dao.pending()
    val legacyNeedsOwner = journal.dao.legacyNeedsOwner()
    val onlineAuthenticated = MutableStateFlow(false)
    val offline = MutableStateFlow(false)
    val lastOfflineSale = MutableStateFlow<UUID?>(null)
    private val journalPage = MutableStateFlow(0)
    fun setJournalPage(page: Int) { journalPage.value = page.coerceAtLeast(0) }
    private fun storageBlockReason(): String? = if (runCatching { availableStorage() }.getOrDefault(0) < JOURNAL_STORAGE_RESERVE_BYTES)
        context.getString(de.stustapay.stustapay.R.string.sale_journal_storage_low) else null
    private val _status = MutableStateFlow(OfflineStatus())
    val status = _status.asStateFlow()

    fun start() {
        if (started || !backgroundEnabled) return
        started = true
        val connectivity = context.getSystemService(Context.CONNECTIVITY_SERVICE) as android.net.ConnectivityManager
        connectivity.registerDefaultNetworkCallback(object : android.net.ConnectivityManager.NetworkCallback() {
            override fun onAvailable(network: android.net.Network) { requestSynchronization() }
            override fun onLost(network: android.net.Network) { connected.value = null; offline.value = true }
        })
        WorkManager.getInstance(context).enqueueUniquePeriodicWork("sales-journal-periodic", ExistingPeriodicWorkPolicy.KEEP,
            PeriodicWorkRequestBuilder<JournalSyncWorker>(15, TimeUnit.MINUTES)
                .setConstraints(Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build()).build())
        scope.launch {
            while (isActive) {
                try { synchronize() } catch (e: CancellationException) { throw e } catch (_: Exception) { }
                delay(5 * 60 * 1000L)
            }
        }
        scope.launch {
            val ticks = flow { while (currentCoroutineContext().isActive) { emit(Unit); delay(1000) } }
            combine(journal.dao.observeCount(), journalPage, ticks) { total, page, _ -> total to page }.collect { (total, requestedPage) ->
                val pageCount = ((total.toLong() + JOURNAL_PAGE_SIZE - 1) / JOURNAL_PAGE_SIZE).toInt().coerceAtLeast(1)
                val page = requestedPage.coerceAtMost(pageCount - 1)
                val entries = journal.dao.page(JOURNAL_PAGE_SIZE, page * JOURNAL_PAGE_SIZE)
                val pending = journal.dao.unresolvedCount()
                try {
                    mutex.withLock {
                        val (preparation, snapshot) = validPreparation(persistClock = false)
                        val rows = journal.dao.validationHistory(snapshot.id.toString())
                        val storageReason = storageBlockReason()
                        val budgets = remainingTillBudgets(snapshot.id.toString(), snapshot.rules.saleTill, snapshot.rules.returnTill, rows)
                        val serverNow = preparedServerNow(preparation, snapshot)
                        val seconds = java.time.Duration.between(serverNow, snapshot.validUntil).seconds.coerceAtLeast(0)
                        _preparedConfig.value = catalogConfig(preparation, snapshot)
                        _status.value = OfflineStatus(offline.value, storageReason == null, seconds, budgets.first, budgets.second, pending,
                            snapshot.buttons.map { Math.toIntExact(it.id) }.toSet(),
                            preparedAt = snapshot.serverTime.toString(),
                            lastSynchronizedAt = journal.dao.syncMetadata()?.lastSynchronizedAt,
                            synchronizing = synchronizing.value, connected = connected.value, journalEntries = entries,
                            journalPage = page, journalPageCount = pageCount, journalTotal = total, blockReason = storageReason)
                    }
                } catch (e: CancellationException) { throw e } catch (e: Exception) {
                    _preparedConfig.value = null
                    val preparedAt = journal.dao.preparation()?.let { prep ->
                        runCatching { journalJson.decodeFromString<PreparedOfflineSnapshot>(prep.payload).serverTime.toString() }.getOrNull()
                    }
                    _status.value = OfflineStatus(offline.value, false, null, null, null, pending,
                        preparedAt = preparedAt, blockReason = e.message, lastSynchronizedAt = journal.dao.syncMetadata()?.lastSynchronizedAt,
                        synchronizing = synchronizing.value, connected = connected.value, journalEntries = entries,
                        journalPage = page, journalPageCount = pageCount, journalTotal = total)
                }
            }
        }
    }
    fun requestSynchronization() {
        if (!backgroundEnabled) return
        start()
        scope.launch { try { synchronize() } catch (e: CancellationException) { throw e } catch (_: Exception) { } }
        schedule()
    }
    private fun schedule() {
        if (!backgroundEnabled) return
        WorkManager.getInstance(context).enqueueUniqueWork("sales-journal-sync", ExistingWorkPolicy.KEEP,
            OneTimeWorkRequestBuilder<JournalSyncWorker>()
                .setConstraints(Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build()).build())
    }
    suspend fun rememberConfig(value: TerminalConfig) {
        mutex.withLock {
            val prep = journal.dao.preparation()
            val assignmentChanged = if (prep != null) try {
                val prepared = journalJson.decodeFromString<TerminalConfig>(prep.config)
                val snapshot = journalJson.decodeFromString<PreparedOfflineSnapshot>(prep.payload)
                val registered = registration() as? RegistrationState.Registered
                registered == null || prep.registration != registrationIdentity(registered) ||
                    !preparedAssignmentMatches(snapshot, prepared, value)
            } catch (e: CancellationException) { throw e } catch (_: Exception) { true } else config?.saleAssignment()?.let { it != value.saleAssignment() } == true
            config = value
            if (assignmentChanged) {
                authorizationGeneration.incrementAndGet()
                journal.dao.revoke()
                _preparedConfig.value = null
                _status.value = _status.value.copy(preparationUsable = false,
                    blockReason = context.getString(de.stustapay.stustapay.R.string.sale_offline_assignment_changed))
            }
        }
        requestSynchronization()
    }
    suspend fun rememberUser(value: CurrentUser) {
        mutex.withLock {
            authorizationGeneration.incrementAndGet()
            val prior = journal.dao.preparation()
            val priorUser = prior?.let { journalJson.decodeFromString<CurrentUser>(it.user) }
            if (priorUser != null && (priorUser.id != value.id || priorUser.activeRoleId != value.activeRoleId)) journal.dao.revoke()
            user = value
            onlineAuthenticated.value = true
        }
        start()
        synchronize()
    }
    suspend fun revoke() = mutex.withLock { authorizationGeneration.incrementAndGet(); user = null; onlineAuthenticated.value = false; _preparedConfig.value = null; journal.dao.revoke() }
    suspend fun hasUnresolved() = journal.hasUnresolved()
    private suspend fun validPreparation(persistClock: Boolean = true): Pair<JournalPreparation, PreparedOfflineSnapshot> {
        val prep = journal.dao.preparation() ?: error("Offline: preparation is missing")
        val snapshot = journalJson.decodeFromString<PreparedOfflineSnapshot>(prep.payload)
        val prepared = journalJson.decodeFromString<TerminalConfig>(prep.config)
        require(preparedAssignmentMatches(snapshot, prepared, config ?: prepared)) {
            context.getString(de.stustapay.stustapay.R.string.sale_offline_assignment_changed)
        }
        require(!prep.revoked) { "Offline: preparation revoked; online preparation required" }
        val stored = registration()
        if (stored !is RegistrationState.Registered || prep.registration != registrationIdentity(stored)) {
            authorizationGeneration.incrementAndGet()
            journal.dao.revoke()
            _preparedConfig.value = null
            error(context.getString(de.stustapay.stustapay.R.string.sale_offline_assignment_changed))
        }
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
    private fun preparedServerNow(prep: JournalPreparation, snapshot: PreparedOfflineSnapshot): OffsetDateTime {
        val boot = android.provider.Settings.Global.getInt(context.contentResolver, android.provider.Settings.Global.BOOT_COUNT, -1)
        val elapsed = if (boot == prep.bootCount) SystemClock.elapsedRealtime() - prep.receivedElapsed
            else System.currentTimeMillis() - prep.receivedWall
        return snapshot.serverTime.plusNanos(elapsed * 1_000_000)
    }

    private fun catalogConfig(prep: JournalPreparation, snapshot: PreparedOfflineSnapshot): TerminalConfig {
        val stored = journalJson.decodeFromString<TerminalConfig>(prep.config)
        val till = stored.till ?: return stored
        val buttons = snapshot.buttons.map { button ->
            val free = button.products.singleOrNull()?.takeIf { !it.fixedPrice }
            TerminalButton(button.id.toBigInteger(), button.name,
                if (free != null) null else button.products.sumOf { it.price ?: 0.0 },
                button.products.all { it.isReturnable }, free == null)
        }
        val overrides = buttons.associateBy { it.id }
        val existingIds = till.buttons.orEmpty().map { it.id }.toSet()
        return stored.copy(till = till.copy(buttons = till.buttons.orEmpty().map { overrides[it.id] ?: it } +
            buttons.filter { it.id !in existingIds }))
    }

    /** Local validation does not wait for any network or synchronization lock. */
    suspend fun check(sale: NewSale): Response<PendingSale> {
        if (journal.dao.sale(sale.uuid.toString()) == null) storageBlockReason()?.let { return Response.Error.Service.Generic(it) }
        val local = mutex.withLock {
            if (sale.paymentMethod != PaymentMethod.tag || (sale.usedVouchers != null && sale.usedVouchers != 0.toBigInteger())) null
            else try {
                val snapshot = validPreparation().second
                val checked = validateOffline(snapshot, sale, journal.dao.validationHistory(snapshot.id.toString()).filter { it.uuid != sale.uuid.toString() })
                checkedAssignments[sale.uuid] = currentSaleContext()
                checkedSnapshots[sale.uuid] = snapshot.id
                onlineChecks.remove(sale.uuid)
                Response.OK(checked.pending)
            } catch (e: CancellationException) { throw e } catch (e: Exception) {
                Response.Error.Service.Generic(e.message ?: "Local sale unavailable")
            }
        }
        if (local is Response.OK) return local
        return syncMutex.withLock {
            // Online checks must account for everything already accepted on this device.
            if (sale.paymentMethod == PaymentMethod.tag && (!synchronizeLocked(prepare = false) || journal.hasUnresolved())) {
                return@withLock local ?: Response.Error.Service.Generic("Sales must be reconciled before online validation")
            }
            val ready = mutex.withLock { sale.paymentMethod != PaymentMethod.tag || !journal.hasUnresolved() }
            if (!ready) return@withLock Response.Error.Service.Generic("Sales must be reconciled before online validation")
            val expectedContext = mutex.withLock { currentSaleContext() }
            val response = transport.check(sale)
            trackConnection(response)
            if (response is Response.OK) {
                val stillCurrent = mutex.withLock {
                    if (currentSaleContext() != expectedContext) {
                        onlineChecks.remove(sale.uuid)
                        checkedAssignments.remove(sale.uuid)
                        checkedSnapshots.remove(sale.uuid)
                        false
                    } else {
                        checkedAssignments[sale.uuid] = expectedContext
                        onlineChecks.add(sale.uuid)
                        checkedSnapshots.remove(sale.uuid)
                        true
                    }
                }
                if (!stillCurrent) return@withLock Response.Error.Service.Generic(
                    context.getString(de.stustapay.stustapay.R.string.sale_offline_assignment_changed))
            }
            if (response is Response.Error.Request && local is Response.Error) local else response
        }
    }

    suspend fun book(sale: NewSale): Response<SaleBookingOutcome> {
        try {
            lastOfflineSale.value = null
            val local = mutex.withLock {
                val existing = journal.dao.sale(sale.uuid.toString())
                if (existing == null && checkedAssignments.containsKey(sale.uuid) && checkedAssignments[sale.uuid] != currentSaleContext())
                    return@withLock Response.Error.Service.Generic(context.getString(de.stustapay.stustapay.R.string.sale_offline_assignment_changed))
                if (existing == null) storageBlockReason()?.let { return@withLock Response.Error.Service.Generic(it) }
                if (existing != null) {
                    if (existing.payload != journalJson.encodeToString(if (existing.offline && sale.usedVouchers == null) sale.copy(usedVouchers = 0.toBigInteger()) else sale))
                        return@withLock Response.Error.Service.Generic("Sale UUID contents changed")
                    if (existing.state == "booked" && existing.result != null)
                        return@withLock Response.OK(SaleBookingOutcome.Confirmed(journalJson.decodeFromString<CompletedSale>(existing.result)))
                    if (existing.state in setOf("rejected", "local_rejected", "clarification", "dismissed"))
                        return@withLock Response.Error.Service.Generic(existing.message ?: "Sale requires clarification")
                    if (existing.offline) return@withLock localOutcome(existing)
                    null
                } else if (sale.paymentMethod == PaymentMethod.tag && sale.uuid !in onlineChecks) {
                    try {
                        journal.database.withTransaction {
                            storageBlockReason()?.let { throw JournalStorageUnavailable(it) }
                            val (prep, snapshot) = validPreparation()
                            require(checkedSnapshots[sale.uuid]?.let { it == snapshot.id } != false) {
                                "Prepared prices changed; please validate the sale again"
                            }
                            val checked = validateOffline(snapshot, sale, journal.dao.validationHistory(snapshot.id.toString()))
                            val normalized = if (sale.usedVouchers == null) sale.copy(usedVouchers = 0.toBigInteger()) else sale
                            val recordedAt = preparedServerNow(prep, snapshot).toString()
                            val receipt = SaleBookingOutcome.LocalAccepted(checked.pending, recordedAt, snapshot.serverTime.toString())
                            val row = JournalSale(sale.uuid.toString(), journalJson.encodeToString(normalized),
                                operatorId = snapshot.userId.toString(), operatorRole = user?.activeRoleId?.toString(),
                                state = "offline", snapshotId = snapshot.id.toString(), sequence = nextSequence(),
                                recordedAt = recordedAt, tagUid = sale.customerTagUid?.toString(),
                                debitCents = checked.debit, saleCents = checked.positive, returnCents = checked.returned,
                                offline = true, localReceipt = journalJson.encodeToString(receipt))
                            journal.dao.insert(row)
                            checkedSnapshots.remove(sale.uuid)
                            checkedAssignments.remove(sale.uuid)
                            lastOfflineSale.value = sale.uuid
                            schedule()
                            if (backgroundEnabled) scope.launch { try { synchronize() } catch (e: CancellationException) { throw e } catch (_: Exception) { } }
                            Response.OK(receipt)
                        }
                    } catch (e: CancellationException) { throw e } catch (e: Exception) {
                        // A previously validated local sale must be rechecked, never silently reprice it online.
                        if (e is JournalStorageUnavailable || e is android.database.sqlite.SQLiteFullException)
                            Response.Error.Service.Generic(context.getString(de.stustapay.stustapay.R.string.sale_journal_storage_low))
                        else if (checkedSnapshots.containsKey(sale.uuid)) Response.Error.Service.Generic(e.message ?: "Local sale unavailable") else null
                    }
                } else null
            }
            if (local != null) return local
            return syncMutex.withLock {
                val existing = mutex.withLock { journal.dao.sale(sale.uuid.toString()) }
                // Replay an existing journal row by UUID through reconciliation, never a second foreground request.
                if (existing != null) {
                    synchronizeLocked(prepare = false)
                    return@withLock mutex.withLock {
                        val row = journal.dao.sale(sale.uuid.toString())!!
                        if (row.state == "booked" && row.result != null)
                            Response.OK(SaleBookingOutcome.Confirmed(journalJson.decodeFromString<CompletedSale>(row.result)))
                        else Response.Error.Service.Generic(row.message ?: "Sale is awaiting server confirmation")
                    }
                }
                if (sale.paymentMethod == PaymentMethod.tag && !mutex.withLock { sale.uuid in onlineChecks })
                    return@withLock Response.Error.Service.Generic("Please validate the basket again before online booking")
                if (sale.paymentMethod == PaymentMethod.tag && (!synchronizeLocked(prepare = false) || journal.hasUnresolved()))
                    return@withLock Response.Error.Service.Generic("Sales must be reconciled before online booking")
                val row = mutex.withLock {
                    if (checkedAssignments.containsKey(sale.uuid) && checkedAssignments[sale.uuid] != currentSaleContext())
                        throw SaleAssignmentChanged(context.getString(de.stustapay.stustapay.R.string.sale_offline_assignment_changed))
                    storageBlockReason()?.let { throw JournalStorageUnavailable(it) }
                    if (sale.paymentMethod == PaymentMethod.tag && journal.hasUnresolved()) null
                    else JournalSale(sale.uuid.toString(), journalJson.encodeToString(sale),
                        operatorId = user?.id?.toString(), operatorRole = user?.activeRoleId?.toString(),
                        snapshotId = journal.dao.preparation()?.let { journalJson.decodeFromString<PreparedOfflineSnapshot>(it.payload).id.toString() },
                        sequence = nextSequence(), recordedAt = OffsetDateTime.now().toString(),
                        tagUid = sale.customerTagUid?.toString(), transferState = "sending", attemptedOnline = true)
                        .also { journal.dao.insert(it); onlineChecks.remove(sale.uuid); checkedAssignments.remove(sale.uuid) }
                } ?: return@withLock Response.Error.Service.Generic("Sales must be reconciled before online booking")
                schedule()
                // The persisted waiting row prevents concurrent local spending; network never holds the local mutex.
                val response = transport.book(sale)
                trackConnection(response)
                mutex.withLock {
                    when (response) {
                        is Response.OK -> {
                            journal.dao.update(row.copy(state = "booked", transferState = "confirmed",
                                result = journalJson.encodeToString(response.data), debitCents = cents(response.data.totalPrice).coerceAtLeast(0),
                                saleCents = cents(response.data.totalPrice).coerceAtLeast(0), returnCents = (-cents(response.data.totalPrice)).coerceAtLeast(0)))
                            Response.OK(SaleBookingOutcome.Confirmed(response.data))
                        }
                        is Response.Error.Request, is Response.Error.Server, is Response.Error.BadResponse -> response
                        is Response.Error -> {
                            journal.dao.update(row.copy(state = "rejected", transferState = "confirmed", message = response.msg()))
                            response
                        }
                    }
                }
            }
        } catch (e: android.database.sqlite.SQLiteFullException) {
            return Response.Error.Service.Generic(context.getString(de.stustapay.stustapay.R.string.sale_journal_storage_low))
        } catch (e: SaleAssignmentChanged) {
            return Response.Error.Service.Generic(e.message ?: "Sale assignment changed; validate again")
        } catch (e: JournalStorageUnavailable) {
            return Response.Error.Service.Generic(e.message ?: context.getString(de.stustapay.stustapay.R.string.sale_journal_storage_low))
        }
    }

    private suspend fun nextSequence(): Long = Math.addExact(journal.dao.lastSequence(), 1)

    private suspend fun localOutcome(row: JournalSale): Response<SaleBookingOutcome> {
        val receipt = row.localReceipt?.let { journalJson.decodeFromString<SaleBookingOutcome.LocalAccepted>(it) }
            ?: row.result?.let {
                val legacy = journalJson.decodeFromString<CompletedSale>(it)
                SaleBookingOutcome.LocalAccepted(legacy.pendingSale(), row.recordedAt,
                    journal.dao.preparation()?.let { prep -> journalJson.decodeFromString<PreparedOfflineSnapshot>(prep.payload).serverTime.toString() }
                        ?: row.recordedAt)
            } ?: return Response.Error.Service.Generic("Local receipt requires clarification")
        lastOfflineSale.value = receipt.sale.uuid
        return Response.OK(receipt)
    }

    private fun trackConnection(response: Response<*>) {
        if (response is Response.Error.Request || response is Response.Error.Server || response is Response.Error.BadResponse) {
            connected.value = false
            offline.value = true
        } else {
            connected.value = true
            offline.value = false
        }
    }

    suspend fun synchronize(): Boolean = syncMutex.withLock {
        synchronizing.value = true
        try { synchronizeLocked() } finally { synchronizing.value = false }
    }

    private suspend fun synchronizeLocked(prepare: Boolean = true): Boolean {
        mutex.withLock {
            // Retention also applies to online-only events and when an unresolved sale blocks preparation.
            val activeSnapshot = journal.dao.preparation()?.takeUnless { it.revoked }?.let {
                journalJson.decodeFromString<PreparedOfflineSnapshot>(it.payload).id.toString()
            }.orEmpty()
            journal.dao.pruneSettled(activeSnapshot, OffsetDateTime.now().minusDays(JOURNAL_RETENTION_DAYS).toString(),
                JOURNAL_RETAINED_SETTLED)
        }
        val initialRows = mutex.withLock { journal.dao.unresolved() }
        for (candidate in initialRows.filter { it.state == "clarification" }) {
            val response = transport.status(candidate.uuid)
            trackConnection(response)
            if (response is Response.OK && response.data.status in setOf("dismissed", "booked", "already_booked", "retry_required")) {
                applyReply(candidate.uuid, response.data, requestedOffline = candidate.offline)
            }
        }
        val localRows = initialRows.filter { it.state == "offline" && it.offline && it.snapshotId != null }.sortedBy { it.sequence }
        for (batch in offlineBatches(localRows)) {
            val rows = mutex.withLock {
                batch.mapNotNull { candidate -> journal.dao.sale(candidate.uuid)?.takeIf { it.state == "offline" && it.offline } }
                    .also { current -> current.forEach { journal.dao.update(it.copy(transferState = "sending")) } }
            }
            if (rows.isEmpty()) continue
            val bookings = rows.map { row -> OfflineBooking(UUID.fromString(row.snapshotId), journalJson.decodeFromString<NewSale>(row.payload), row.sequence, OffsetDateTime.parse(row.recordedAt)) }
            val response = transport.import(OfflineImport(bookings))
            trackConnection(response)
            if (response !is Response.OK) {
                mutex.withLock { rows.forEach { journal.dao.sale(it.uuid)?.let { current -> journal.dao.update(current.copy(transferState = "queued")) } } }
                return false
            }
            val replies = matchedOfflineReplies(rows, response.data.results)
            replies.forEach { (uuid, reply) -> applyReply(uuid, reply, requestedOffline = true) }
            if (replies.size != rows.size) {
                mutex.withLock { rows.filter { it.uuid !in replies }.forEach { journal.dao.sale(it.uuid)?.let { current -> journal.dao.update(current.copy(transferState = "queued")) } } }
                return false
            }
        }
        for (candidate in initialRows.filter { it.state == "waiting" && !it.offline }.sortedBy { it.sequence }) {
            val row = mutex.withLock {
                journal.dao.sale(candidate.uuid)?.takeIf { it.state == "waiting" && !it.offline }
            } ?: continue
            val sale = journalJson.decodeFromString<NewSale>(row.payload)
            if (!row.offline) {
                val known = transport.status(row.uuid)
                trackConnection(known)
                if (known !is Response.OK) return false
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
                val res = transport.book(sale)
                trackConnection(res)
                when (res) {
                    is Response.OK -> applyReply(row.uuid, OfflineResult(sale.uuid, "booked", res.data), requestedOffline = false)
                    is Response.Error.Request, is Response.Error.Server, is Response.Error.BadResponse -> return false
                    is Response.Error -> applyReply(row.uuid, OfflineResult(sale.uuid, "rejected", message = res.msg()), requestedOffline = false)
                }
            }
        }
        if (journal.hasUnresolved()) return false
        // No connected response yet is not evidence that online fallback is usable; caller probes server.
        if (initialRows.any { it.state in setOf("waiting", "offline", "clarification") } && connected.value == true) {
            mutex.withLock {
                if (!journal.hasUnresolved()) journal.dao.syncMetadata(JournalSyncMetadata(lastSynchronizedAt = OffsetDateTime.now().toString()))
            }
        }
        if (!prepare) return true
        if (user == null) {
            val (previous, generation) = mutex.withLock { journal.dao.preparation() to authorizationGeneration.get() }
            if (previous != null && !previous.revoked) {
                val priorUser = journalJson.decodeFromString<CurrentUser>(previous.user)
                val res = transport.currentUser()
                trackConnection(res)
                val recovered = mutex.withLock {
                    val currentPreparation = journal.dao.preparation()
                    val sameAuthorization = authorizationGeneration.get() == generation && user == null &&
                        currentPreparation?.revoked == false && currentPreparation.payload == previous.payload &&
                        (registration() as? RegistrationState.Registered)?.let(::registrationIdentity) == previous.registration
                    if (!sameAuthorization) false
                    else if (res is Response.OK && res.data.id == priorUser.id && res.data.activeRoleId == priorUser.activeRoleId) {
                        user = res.data
                        onlineAuthenticated.value = true
                        true
                    } else {
                        if (res is Response.Error.Access || res is Response.Error.Service) {
                            authorizationGeneration.incrementAndGet()
                            journal.dao.revoke()
                            _preparedConfig.value = null
                            onlineAuthenticated.value = false
                        }
                        false
                    }
                }
                if (!recovered) return false
            }
        }
        val currentUser = user ?: return true
        val currentConfig = config ?: return true
        val reg = registration() as? RegistrationState.Registered ?: return true
        val expectedRegistration = registrationIdentity(reg)
        val expectedSequence = mutex.withLock { nextSequence() }
        val expectedAuthorization = authorizationGeneration.get()
        val requestStarted = SystemClock.elapsedRealtime()
        val res = de.stustapay.stustapay.net.withOfflineRecoveryDeadline(true) { transport.prepare() }
        trackConnection(res)
        return when (res) {
            is Response.OK -> {
                if (res.data.userId != currentUser.id.toString().toLong() ||
                    !preparedAssignmentMatches(res.data, currentConfig, currentConfig)) return false
                val now = System.currentTimeMillis()
                mutex.withLock {
                    // A sale may have been admitted while preparation was travelling over the network.
                    if (!journal.hasUnresolved() && user?.id == currentUser.id && user?.activeRoleId == currentUser.activeRoleId &&
                        (registration() as? RegistrationState.Registered)?.let(::registrationIdentity) == expectedRegistration &&
                        config == currentConfig && nextSequence() == expectedSequence && authorizationGeneration.get() == expectedAuthorization) {
                        journal.database.withTransaction {
                            journal.dao.prepare(JournalPreparation(payload = journalJson.encodeToString(res.data), registration = registrationIdentity(reg),
                                user = journalJson.encodeToString(currentUser), config = journalJson.encodeToString(currentConfig),
                                bootCount = android.provider.Settings.Global.getInt(context.contentResolver, android.provider.Settings.Global.BOOT_COUNT, -1),
                                receivedWall = now - (SystemClock.elapsedRealtime() - requestStarted), receivedElapsed = requestStarted, lastWall = now, lastElapsed = SystemClock.elapsedRealtime()))
                            journal.dao.syncMetadata(JournalSyncMetadata(lastSynchronizedAt = OffsetDateTime.now().toString()))
                            journal.dao.pruneSettled(res.data.id.toString(),
                                res.data.serverTime.minusDays(JOURNAL_RETENTION_DAYS).toString(), JOURNAL_RETAINED_SETTLED)
                        }
                        _preparedConfig.value = catalogConfig(journal.dao.preparation()!!, res.data)
                        offline.value = false
                    }
                }
                true
            }
            is Response.Error.Access, is Response.Error.Service -> {
                mutex.withLock {
                    // A delayed denial for an older login must not revoke a newer operator.
                    if (authorizationGeneration.get() == expectedAuthorization && user?.id == currentUser.id && user?.activeRoleId == currentUser.activeRoleId &&
                        (registration() as? RegistrationState.Registered)?.let(::registrationIdentity) == expectedRegistration) {
                        journal.dao.revoke()
                        _preparedConfig.value = null
                    }
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
            for (row in journal.dao.unresolved().filter { it.legacy && it.operatorId == null && it.state == "waiting" }) {
                journal.dao.update(row.copy(operatorId = current.id.toString(), operatorRole = current.activeRoleId?.toString()))
            }
        }
        synchronize()
    }
    suspend fun migrateLegacy(sale: NewSale) = mutex.withLock {
        if (journal.dao.sale(sale.uuid.toString()) == null) journal.dao.insert(JournalSale(sale.uuid.toString(), journalJson.encodeToString(sale), legacy = true, attemptedOnline = true,
            sequence = nextSequence(), recordedAt = OffsetDateTime.now().toString(), tagUid = sale.customerTagUid?.toString()))
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
