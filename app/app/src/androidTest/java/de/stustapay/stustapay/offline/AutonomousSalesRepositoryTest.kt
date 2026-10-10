package de.stustapay.stustapay.offline

import android.content.Context
import androidx.room.withTransaction
import androidx.room.Room
import androidx.test.platform.app.InstrumentationRegistry
import com.ionspin.kotlin.bignum.integer.toBigInteger
import de.stustapay.api.models.*
import de.stustapay.libssp.net.Response
import de.stustapay.stustapay.model.RegistrationState
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.async
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeout
import kotlinx.serialization.decodeFromString
import kotlinx.serialization.encodeToString
import org.junit.Assert.*
import org.junit.Assume.assumeTrue
import org.junit.Test
import java.time.OffsetDateTime
import java.util.UUID

/** Real Room admission with a controlled transport; no background workers or mocking library. */
class AutonomousSalesRepositoryTest {
    private val operator = CurrentUser(1.toBigInteger(), 1.toBigInteger(), "cashier", "Cashier",
        emptyList(), activeRoleId = 2.toBigInteger())
    private fun config(terminalId: Long = 1, tillId: Long? = 1, eventId: Long? = 1) = TerminalConfig(
        id = terminalId.toBigInteger(), name = "Till", description = null,
        mode = TerminalMode.till, entryArea = null, selfService = false, appDisplayMode = null,
        eventName = "Festival", activeUserId = operator.id, availableRoles = emptyList(),
        userPrivileges = emptyList(), secrets = null,
        till = tillId?.let { id -> TerminalTillConfig(id = id.toBigInteger(), name = "Till $id",
            description = null, eventName = "Festival", profileName = "Default", cashRegisterId = null,
            cashRegisterName = null, allowTopUp = false, allowCashOut = false, allowTicketSale = false,
            allowTicketVouchers = false, enableSspPayment = true, enableCashPayment = true,
            enableCardPayment = false, buttons = emptyList(), sumupSecrets = null,
            postPaymentAllowed = false, sumupPaymentEnabled = false, userPrivileges = emptyList(),
            secrets = null, activeUserId = operator.id, availableRoles = emptyList()) },
        testMode = true, testModeMessage = "Test", eventNodeId = eventId?.toBigInteger())
    private val product = Product("Drink", 5.0, true, 1.toBigInteger(), emptyList(), true, false,
        1.toBigInteger(), 1.toBigInteger(), "tax", 0.19, ProductType.user_defined)

    private fun snapshot(terminalId: Long = 1, tillId: Long = 1, eventId: Long = 1): PreparedOfflineSnapshot {
        val now = OffsetDateTime.now()
        return PreparedOfflineSnapshot(UUID.randomUUID(), now, now.plusHours(2), terminalId, tillId, eventId, 1,
            OfflineRules(7200, 2000, 3000, 50000, 2000, 3000, 50000),
            listOf(OfflineCustomer(1, 42.toBigInteger(), 2000)),
            listOf(OfflineButton(1, "Drink", listOf(product))))
    }

    private fun sale(method: PaymentMethod = PaymentMethod.tag) = NewSale(UUID.randomUUID(), method,
        listOf(Button(1.toBigInteger(), 1.toBigInteger())),
        if (method == PaymentMethod.tag) 42.toBigInteger() else null, usedVouchers = 0.toBigInteger())

    private inner class Transport(val received: MutableList<OfflineBooking> = mutableListOf()) : OfflineSalesTransport {
        var online = true
        var prepared = snapshot()
        var checks = 0
        var books = 0
        var imports = 0
        var importFailureStatus: String? = null
        var statusReply: OfflineResult? = null
        var preparations = 0
        var preparationEnabled = true
        var checkEntered: CompletableDeferred<Unit>? = null
        var checkReply: CompletableDeferred<Response<PendingSale>>? = null
        var prepareEntered: CompletableDeferred<Unit>? = null
        var prepareReply: CompletableDeferred<Response<PreparedOfflineSnapshot>>? = null
        var userEntered: CompletableDeferred<Unit>? = null
        var userReply: CompletableDeferred<Response<CurrentUser>>? = null

        private fun pending(sale: NewSale) = validateOffline(prepared,
            sale.copy(paymentMethod = PaymentMethod.tag, customerTagUid = 42.toBigInteger()), emptyList()).pending
            .copy(paymentMethod = sale.paymentMethod)

        private fun completed(sale: NewSale): CompletedSale {
            val pending = pending(sale)
            return CompletedSale(pending.uuid, pending.oldBalance, pending.newBalance,
                pending.oldVoucherBalance, pending.newVoucherBalance, pending.customerAccountId,
                pending.paymentMethod, pending.lineItems, pending.buttons, 123.toBigInteger(),
                OffsetDateTime.now(), operator.id, 1.toBigInteger(), "https://example.invalid/bon/${sale.uuid}",
                pending.usedVouchers, pending.itemCount, pending.totalPrice)
        }

        override suspend fun check(sale: NewSale): Response<PendingSale> {
            checks++
            checkEntered?.complete(Unit)
            checkReply?.let { return it.await() }
            return if (online) Response.OK(pending(sale)) else Response.Error.Request(throwable = java.io.IOException())
        }
        override suspend fun book(sale: NewSale): Response<CompletedSale> {
            books++
            return if (online) Response.OK(completed(sale)) else Response.Error.Request(throwable = java.io.IOException())
        }
        override suspend fun prepare(): Response<PreparedOfflineSnapshot> {
            preparations++
            if (!preparationEnabled) return Response.Error.Service.Generic("Offline operation is disabled")
            prepareEntered?.complete(Unit)
            return prepareReply?.await() ?: if (online) Response.OK(prepared)
                else Response.Error.Request(throwable = java.io.IOException())
        }
        override suspend fun import(payload: OfflineImport): Response<OfflineResults> {
            imports++
            if (!online) return Response.Error.Request(throwable = java.io.IOException())
            importFailureStatus?.let { status ->
                return Response.OK(OfflineResults(payload.bookings.map { OfflineResult(it.sale.uuid, status, message = "Retry later") }))
            }
            return Response.OK(OfflineResults(payload.bookings.map { booking ->
                val status = if (received.any { it.sale.uuid == booking.sale.uuid }) "already_booked" else "booked"
                received.add(booking)
                OfflineResult(booking.sale.uuid, status, completed(booking.sale))
            }))
        }
        override suspend fun status(uuid: String) = Response.OK(statusReply ?: OfflineResult(UUID.fromString(uuid), "not_found"))
        override suspend fun currentUser(): Response<CurrentUser> {
            userEntered?.complete(Unit)
            return userReply?.await() ?: Response.OK(operator)
        }
    }

    private inner class Fixture(val context: Context, received: MutableList<OfflineBooking> = mutableListOf()) {
        val name = "autonomous-${UUID.randomUUID()}.db"
        fun open() = Room.databaseBuilder(context, JournalDatabase::class.java, name).build()
        var db = open()
        val transport = Transport(received)
        var availableBytes = Long.MAX_VALUE
        var registered: RegistrationState = RegistrationState.Registered("test-token", "https://example.invalid/")
        fun repository() = OfflineSalesRepository(SalesJournal(db), transport,
            { registered }, context, { availableBytes })
        var repo = repository()
        suspend fun prepare(terminalId: Long = 1, tillId: Long = 1) {
            transport.prepared = snapshot(terminalId, tillId)
            repo.rememberConfig(config(terminalId, tillId))
            repo.rememberUser(operator)
            assertNotNull(db.journal().preparation())
        }
        suspend fun expirePreparation() {
            val preparation = db.journal().preparation()!!
            val expired = journalJson.decodeFromString<PreparedOfflineSnapshot>(preparation.payload)
                .copy(validUntil = OffsetDateTime.now().minusMinutes(1))
            db.journal().prepare(preparation.copy(payload = journalJson.encodeToString(expired)))
        }
        fun close() { db.close(); context.deleteDatabase(name) }
    }

    private fun test(block: suspend Fixture.() -> Unit) = runBlocking {
        withTimeout(15_000) {
            val context = InstrumentationRegistry.getInstrumentation().targetContext
            assumeTrue(android.provider.Settings.Global.getInt(context.contentResolver,
                android.provider.Settings.Global.BOOT_COUNT, -1) >= 0)
            val fixture = Fixture(context)
            try { fixture.block() } finally { fixture.close() }
        }
    }

    @Test fun lowStorageBlocksNewSalesButPreservesAcceptedReplayAndSynchronization() = test {
        prepare()
        val accepted = sale()
        assertTrue(repo.check(accepted) is Response.OK)
        assertTrue(repo.book(accepted) is Response.OK)
        val original = db.journal().sale(accepted.uuid.toString())!!
        val newSale = sale()
        // Storage can disappear after validation; booking checks it again before admission.
        assertTrue(repo.check(newSale) is Response.OK)
        availableBytes = JOURNAL_STORAGE_RESERVE_BYTES - 1
        assertTrue(repo.book(newSale) is Response.Error.Service)
        assertNull(db.journal().sale(newSale.uuid.toString()))
        assertTrue(repo.check(sale()) is Response.Error.Service)
        assertTrue(repo.book(sale(PaymentMethod.cash)) is Response.Error.Service)
        assertTrue(repo.book(accepted) is Response.OK)
        assertEquals(original, db.journal().sale(accepted.uuid.toString()))
        assertEquals(0, transport.books)
        assertEquals(0, transport.checks)
        assertTrue(repo.synchronize())
        assertEquals("booked", db.journal().sale(accepted.uuid.toString())!!.state)
        availableBytes = JOURNAL_STORAGE_RESERVE_BYTES
        assertTrue(repo.check(sale()) is Response.OK)
    }

    @Test fun preparedSalesAreAcceptedWithoutForegroundNetworkOnlineAndOffline() = test {
        prepare()
        val preparations = transport.preparations
        for (online in listOf(true, false)) {
            transport.online = online
            val sale = sale()
            assertTrue(repo.check(sale) is Response.OK)
            val result = repo.book(sale)
            assertTrue(result is Response.OK && result.data is SaleBookingOutcome.LocalAccepted)
            val row = db.journal().sale(sale.uuid.toString())!!
            assertEquals("offline", row.state)
            assertEquals(500L, row.debitCents)
            assertNotNull(row.localReceipt)
        }
        assertEquals(0, transport.checks)
        assertEquals(0, transport.books)
        assertEquals(0, transport.imports)
        assertEquals(preparations, transport.preparations)
    }

    @Test fun twoSimulatedTerminalsAcceptTheSameTagWithoutNfcAndReconcileIndependently() = runBlocking {
        withTimeout(15_000) {
            val context = InstrumentationRegistry.getInstrumentation().targetContext
            val serverBookings = mutableListOf<OfflineBooking>()
            val first = Fixture(context, serverBookings)
            val second = Fixture(context, serverBookings)
            try {
                first.prepare(terminalId = 1, tillId = 1)
                second.prepare(terminalId = 2, tillId = 2)
                assertNotEquals(first.transport.prepared.id, second.transport.prepared.id)

                first.transport.online = false
                second.transport.online = false
                // NewSale carries the tag UID supplied by the scan boundary; no NFC hardware is involved.
                val firstSale = sale()
                val secondSale = sale()
                for ((terminal, draft) in listOf(first to firstSale, second to secondSale)) {
                    assertTrue(terminal.repo.check(draft) is Response.OK)
                    val result = terminal.repo.book(draft)
                    assertTrue(result is Response.OK && result.data is SaleBookingOutcome.LocalAccepted)
                    assertEquals("offline", terminal.db.journal().sale(draft.uuid.toString())!!.state)
                    assertFalse(terminal.repo.synchronize())
                }
                assertTrue(serverBookings.isEmpty())
                assertEquals(0, first.transport.checks + second.transport.checks)
                assertEquals(0, first.transport.books + second.transport.books)

                second.transport.online = true
                assertTrue(second.repo.synchronize())
                assertEquals("booked", second.db.journal().sale(secondSale.uuid.toString())!!.state)
                assertEquals("offline", first.db.journal().sale(firstSale.uuid.toString())!!.state)
                first.transport.online = true
                assertTrue(first.repo.synchronize())
                assertEquals("booked", first.db.journal().sale(firstSale.uuid.toString())!!.state)
                assertEquals(setOf(firstSale.uuid, secondSale.uuid), serverBookings.map { it.sale.uuid }.toSet())
                assertEquals(setOf(first.transport.prepared.id, second.transport.prepared.id),
                    serverBookings.map { it.snapshotId }.toSet())
                assertTrue(serverBookings.all { it.sale.customerTagUid == 42.toBigInteger() })
                assertEquals(1L, first.db.journal().sale(firstSale.uuid.toString())!!.sequence)
                assertEquals(1L, second.db.journal().sale(secondSale.uuid.toString())!!.sequence)

                assertTrue(first.repo.synchronize())
                assertTrue(second.repo.synchronize())
                assertEquals(2, serverBookings.size)
            } finally {
                first.close()
                second.close()
            }
        }
    }

    @Test fun acceptedSaleSurvivesReopenAndExplicitSynchronizationConfirmsSameUuid() = test {
        prepare()
        val sale = sale()
        assertTrue(repo.check(sale) is Response.OK)
        assertTrue(repo.book(sale) is Response.OK)
        val original = db.journal().sale(sale.uuid.toString())!!
        db.close()
        db = open()
        repo = repository()
        repo.rememberConfig(config())
        assertEquals(original, db.journal().sale(sale.uuid.toString()))
        assertTrue(repo.synchronize())
        val confirmed = db.journal().sale(sale.uuid.toString())!!
        assertEquals("booked", confirmed.state)
        assertEquals(original.payload, confirmed.payload)
        assertEquals(original.debitCents, confirmed.debitCents)
        assertEquals(original.sequence, confirmed.sequence)
        assertEquals(sale.uuid, transport.received.single().sale.uuid)
        assertTrue(repo.book(sale) is Response.OK)
        assertEquals(0, transport.books)
        assertEquals(1, transport.imports)
    }

    @Test fun retryableServerFailureSurvivesReopenAndAutomaticallySettlesOriginalSale() = test {
        prepare()
        val accepted = sale()
        assertTrue(repo.check(accepted) is Response.OK)
        assertTrue(repo.book(accepted) is Response.OK)
        val original = db.journal().sale(accepted.uuid.toString())!!
        transport.importFailureStatus = "retry_required"
        assertFalse(repo.synchronize())
        val pending = db.journal().sale(original.uuid)!!
        assertEquals("offline", pending.state)
        assertEquals("queued", pending.transferState)
        assertEquals(original.debitCents, pending.debitCents)
        assertEquals(original.localReceipt, pending.localReceipt)
        db.close()
        db = open()
        repo = repository()
        repo.rememberConfig(config())
        transport.importFailureStatus = null
        assertTrue(repo.synchronize())
        val confirmed = db.journal().sale(original.uuid)!!
        assertEquals("booked", confirmed.state)
        assertEquals(original.payload, confirmed.payload)
        assertEquals(original.sequence, confirmed.sequence)
        assertEquals(1, transport.received.size)
        assertEquals(0, transport.books)
        assertEquals(0, transport.checks)
    }

    @Test fun previousClarificationCanReturnToAutomaticReconciliation() = test {
        prepare()
        val accepted = sale()
        assertTrue(repo.check(accepted) is Response.OK)
        assertTrue(repo.book(accepted) is Response.OK)
        transport.importFailureStatus = "clarification_required"
        assertFalse(repo.synchronize())
        assertEquals("clarification", db.journal().sale(accepted.uuid.toString())!!.state)
        transport.statusReply = OfflineResult(accepted.uuid, "retry_required", message = "Dependency recovering")
        transport.importFailureStatus = null
        assertFalse(repo.synchronize())
        assertEquals("offline", db.journal().sale(accepted.uuid.toString())!!.state)
        assertTrue(repo.synchronize())
        assertEquals("booked", db.journal().sale(accepted.uuid.toString())!!.state)
        assertEquals(0, transport.books)
    }

    @Test fun preparationInFlightCannotReplaceSnapshotAfterLocalAdmission() = test {
        prepare()
        val old = db.journal().preparation()!!.payload
        transport.prepared = snapshot()
        transport.prepareEntered = CompletableDeferred()
        transport.prepareReply = CompletableDeferred()
        coroutineScope {
            val sync = async(Dispatchers.Default) { repo.synchronize() }
            transport.prepareEntered!!.await()
            val sale = sale()
            assertTrue(repo.check(sale) is Response.OK)
            assertTrue(repo.book(sale) is Response.OK)
            transport.prepareReply!!.complete(Response.OK(transport.prepared))
            sync.await()
        }
        assertEquals(old, db.journal().preparation()!!.payload)
        assertEquals("offline", db.journal().sales().single().state)
        assertEquals(0, transport.imports)
    }

    @Test fun tillChangeRevokesOldPreparationButImportsItsAcceptedSaleBeforePreparingNewTill() = test {
        prepare()
        val oldSnapshot = journalJson.decodeFromString<PreparedOfflineSnapshot>(db.journal().preparation()!!.payload)
        val accepted = sale()
        assertTrue(repo.check(accepted) is Response.OK)
        assertTrue(repo.book(accepted) is Response.OK)

        val newConfig = config(tillId = 2)
        transport.prepared = snapshot(tillId = 2)
        repo.rememberConfig(newConfig)
        transport.online = false
        assertTrue(repo.check(sale()) is Response.Error)
        assertNull(repo.restoredConfig())
        val blockedSale = sale()
        assertTrue(repo.book(blockedSale) is Response.Error)
        assertNull(db.journal().sale(blockedSale.uuid.toString()))

        transport.online = true
        assertTrue(repo.synchronize())
        val imported = transport.received.single()
        assertEquals(oldSnapshot.id, imported.snapshotId)
        assertEquals(accepted.uuid, imported.sale.uuid)
        val activePreparation = db.journal().preparation()!!
        assertFalse(activePreparation.revoked)
        assertEquals(2L, journalJson.decodeFromString<PreparedOfflineSnapshot>(activePreparation.payload).tillId)
        assertEquals(2.toBigInteger(), repo.restoredConfig()!!.till!!.id)

        val newSale = sale()
        assertTrue(repo.check(newSale) is Response.OK)
        val result = repo.book(newSale)
        assertTrue(result is Response.OK && result.data is SaleBookingOutcome.LocalAccepted)
        assertEquals(2L, journalJson.decodeFromString<PreparedOfflineSnapshot>(
            db.journal().preparation()!!.payload).tillId)
    }

    @Test fun changedEventInvalidatesOldPreparationAndIgnoresDelayedOldPrepareReply() = test {
        prepare()
        transport.prepareEntered = CompletableDeferred()
        transport.prepareReply = CompletableDeferred()
        coroutineScope {
            val sync = async(Dispatchers.Default) { repo.synchronize() }
            transport.prepareEntered!!.await()
            repo.rememberConfig(config(eventId = 2))
            transport.online = false
            transport.prepareReply!!.complete(Response.OK(transport.prepared))
            sync.await()
        }
        assertTrue(db.journal().preparation()!!.revoked)
        assertNull(repo.restoredConfig())
        assertTrue(repo.check(sale()) is Response.Error)
        val blockedSale = sale()
        assertTrue(repo.book(blockedSale) is Response.Error)
        assertNull(db.journal().sale(blockedSale.uuid.toString()))
    }

    @Test fun changedTerminalInvalidatesThePreparation() = test {
        prepare()
        repo.rememberConfig(config(terminalId = 2))
        transport.online = false
        assertNull(repo.restoredConfig())
        assertTrue(repo.check(sale()) is Response.Error)
        val blockedSale = sale()
        assertTrue(repo.book(blockedSale) is Response.Error)
        assertNull(db.journal().sale(blockedSale.uuid.toString()))
        assertTrue(db.journal().preparation()!!.revoked)
    }

    @Test fun removedTillInvalidatesThePreparation() = test {
        prepare()
        repo.rememberConfig(config(tillId = null))
        transport.online = false
        assertNull(repo.restoredConfig())
        assertTrue(repo.check(sale()) is Response.Error)
        val blockedSale = sale()
        assertTrue(repo.book(blockedSale) is Response.Error)
        assertNull(db.journal().sale(blockedSale.uuid.toString()))
        assertTrue(db.journal().preparation()!!.revoked)
    }

    @Test fun onlineValidatedCartMustBeRecheckedAfterAssignmentChange() = test {
        prepare()
        expirePreparation()
        val draft = sale()
        assertTrue(repo.check(draft) is Response.OK)
        assertEquals(1, transport.checks)
        repo.rememberConfig(config(tillId = 2))
        transport.prepared = snapshot(tillId = 2)
        assertTrue(repo.book(draft) is Response.Error.Service)
        assertNull(db.journal().sale(draft.uuid.toString()))
        assertEquals(0, transport.books)
        assertTrue(repo.check(draft) is Response.OK)
        assertTrue(repo.book(draft) is Response.OK)
        assertEquals(1, transport.books)
    }

    @Test fun invalidatedPreparationStaysInvalidAfterRestart() = test {
        prepare()
        repo.rememberConfig(config(eventId = 2))
        db.close()
        db = open()
        repo = repository()
        assertNull(repo.restoredConfig())
        assertNull(repo.restoredUser())
        assertTrue(db.journal().preparation()!!.revoked)
    }

    @Test fun eventRenameWithSameEventIdKeepsPreparationValid() = test {
        prepare()
        val renamed = config().copy(eventName = "Renamed Festival",
            till = config().till!!.copy(eventName = "Renamed Festival"))
        repo.rememberConfig(renamed)
        transport.online = false
        assertNotNull(repo.restoredConfig())
        assertTrue(repo.check(sale()) is Response.OK)
        assertFalse(db.journal().preparation()!!.revoked)
    }

    @Test fun mismatchedPreparationReplyCannotReplaceRevokedAssignment() = test {
        prepare()
        repo.rememberConfig(config(tillId = 2))
        transport.prepared = snapshot(tillId = 2, eventId = 2)
        transport.online = true

        assertFalse(repo.synchronize())
        assertTrue(db.journal().preparation()!!.revoked)
        assertNull(repo.restoredConfig())
        transport.online = false
        assertTrue(repo.check(sale()) is Response.Error)
    }

    @Test fun registrationReassignmentRevocationSurvivesReturningToOriginalTokenAndReopening() = test {
        prepare()
        val originalRegistration = registered
        registered = RegistrationState.Registered("replacement-token", "https://example.invalid/")

        assertNull(repo.restoredConfig())
        assertTrue(db.journal().preparation()!!.revoked)

        registered = originalRegistration
        db.close()
        db = open()
        repo = repository()
        assertNull(repo.restoredConfig())
        assertTrue(db.journal().preparation()!!.revoked)
    }

    @Test fun legacyPreparationWithoutEventIdRestoresUntilStableLiveEventIdChanges() = test {
        prepare()
        val preparation = db.journal().preparation()!!
        val legacyConfig = config(eventId = null)
        db.journal().prepare(preparation.copy(config = journalJson.encodeToString(legacyConfig)))

        assertNotNull(repo.restoredConfig())
        repo.rememberConfig(config(eventId = 2))
        assertNull(repo.restoredConfig())
        assertTrue(db.journal().preparation()!!.revoked)
    }

    @Test fun delayedOnlineCheckCannotValidateCartAfterAssignmentChanges() = test {
        prepare()
        expirePreparation()
        val draft = sale()
        transport.checkEntered = CompletableDeferred()
        transport.checkReply = CompletableDeferred()

        coroutineScope {
            val check = async(Dispatchers.Default) { repo.check(draft) }
            transport.checkEntered!!.await()
            repo.rememberConfig(config(tillId = 2))
            val stalePending = validateOffline(transport.prepared, draft, emptyList()).pending
            transport.checkReply!!.complete(Response.OK(stalePending))

            assertTrue(check.await() is Response.Error)
        }

        assertTrue(repo.book(draft) is Response.Error)
        assertNull(db.journal().sale(draft.uuid.toString()))
        assertEquals(0, transport.books)
    }

    @Test fun delayedUserRecoveryDoesNotUndoConcurrentLogout() = test {
        prepare()
        repo = repository()
        repo.rememberConfig(config())
        transport.userEntered = CompletableDeferred()
        transport.userReply = CompletableDeferred()
        val preparations = transport.preparations
        coroutineScope {
            val sync = async(Dispatchers.Default) { repo.synchronize() }
            transport.userEntered!!.await()
            repo.revoke()
            transport.userReply!!.complete(Response.OK(operator))
            sync.await()
        }
        assertTrue(db.journal().preparation()!!.revoked)
        assertFalse(repo.onlineAuthenticated.value)
        assertNull(repo.restoredUser())
        assertEquals(preparations, transport.preparations)
    }

    @Test fun cashAndCardContinueOnlineWhileAnUnrelatedSaleNeedsClarification() = test {
        prepare()
        db.journal().insert(JournalSale(UUID.randomUUID().toString(), "unrelated", sequence = 1,
            recordedAt = OffsetDateTime.now().toString(), state = "clarification", offline = true))
        for (method in listOf(PaymentMethod.cash, PaymentMethod.sumup)) {
            val sale = sale(method)
            assertTrue(repo.check(sale) is Response.OK)
            val result = repo.book(sale)
            assertTrue(result is Response.OK && result.data is SaleBookingOutcome.Confirmed)
        }
        assertEquals(2, transport.checks)
        assertEquals(2, transport.books)
        assertEquals(0, transport.imports)
    }

    @Test fun expiredPreparationFallsBackToOnlineCheckAndConfirmedBooking() = test {
        prepare()
        expirePreparation()
        val sale = sale()
        assertTrue(repo.check(sale) is Response.OK)
        val result = repo.book(sale)
        assertTrue(result is Response.OK && result.data is SaleBookingOutcome.Confirmed)
        val row = db.journal().sale(sale.uuid.toString())!!
        assertEquals("booked", row.state)
        assertFalse(row.offline)
        assertEquals(sale.uuid, journalJson.decodeFromString<NewSale>(row.payload).uuid)
        assertEquals(1, transport.checks)
        assertEquals(1, transport.books)
        assertEquals(0, transport.imports)
    }

    @Test fun tagFallbackRemainsBlockedUntilExistingClarificationIsResolved() = test {
        prepare()
        expirePreparation()
        val clarification = JournalSale(UUID.randomUUID().toString(), "unrelated", sequence = 1,
            recordedAt = OffsetDateTime.now().toString(), state = "clarification", offline = true)
        db.journal().insert(clarification)
        val sale = sale()
        assertTrue(repo.check(sale) is Response.Error)
        assertTrue(repo.book(sale) is Response.Error)
        assertNull(db.journal().sale(sale.uuid.toString()))
        assertEquals(clarification, db.journal().sale(clarification.uuid))
        assertEquals(0, transport.checks)
        assertEquals(0, transport.books)
        assertEquals(0, transport.imports)
    }

    @Test fun onlineOnlyJournalRetentionRunsWithoutOfflinePreparation() = test {
        transport.preparationEnabled = false
        repo.rememberConfig(config())
        repo.rememberUser(operator)
        assertNull(db.journal().preparation())
        db.withTransaction {
            for (sequence in 1..1005) {
                val settled = sale()
                db.journal().insert(JournalSale(settled.uuid.toString(), journalJson.encodeToString(settled),
                    sequence = sequence.toLong(), recordedAt = OffsetDateTime.now().minusDays(2).toString(),
                    state = "booked", transferState = "confirmed"))
            }
        }
        assertFalse(repo.synchronize()) // The event still denies offline capability.
        val retained = db.journal().sales()
        assertEquals(JOURNAL_RETAINED_SETTLED, retained.size)
        assertEquals(1005L, db.journal().lastSequence())
        val unresolved = JournalSale(UUID.randomUUID().toString(), "unrelated", sequence = 1006,
            recordedAt = OffsetDateTime.now().minusDays(30).toString(), state = "clarification", offline = true)
        db.journal().insert(unresolved)
        assertFalse(repo.synchronize())
        assertEquals(unresolved, db.journal().sale(unresolved.uuid))
    }

    @Test fun journalRetentionProtectsActiveBudgetHistoryUntilAuthorizationRevoked() = test {
        prepare()
        db.withTransaction {
            for (sequence in 1..1005) {
                val settled = sale()
                db.journal().insert(JournalSale(settled.uuid.toString(), journalJson.encodeToString(settled),
                    sequence = sequence.toLong(), recordedAt = OffsetDateTime.now().minusDays(2).toString(),
                    snapshotId = transport.prepared.id.toString(), offline = true,
                    state = "booked", transferState = "confirmed"))
            }
        }
        assertTrue(repo.synchronize())
        assertEquals(1005, db.journal().sales().size)
        transport.preparationEnabled = false
        repo.revoke()
        assertTrue(repo.synchronize()) // No operator: cleanup runs without preparing a new authorization.
        assertEquals(JOURNAL_RETAINED_SETTLED, db.journal().sales().size)
        assertEquals(1005L, db.journal().lastSequence())
    }
}
