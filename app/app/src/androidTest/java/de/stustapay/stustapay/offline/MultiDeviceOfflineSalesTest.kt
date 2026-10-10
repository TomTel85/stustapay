package de.stustapay.stustapay.offline

import android.content.Context
import androidx.room.Room
import androidx.test.platform.app.InstrumentationRegistry
import com.ionspin.kotlin.bignum.integer.toBigInteger
import de.stustapay.api.models.*
import de.stustapay.libssp.net.Response
import de.stustapay.stustapay.model.RegistrationState
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withContext
import kotlinx.coroutines.withTimeout
import kotlinx.serialization.decodeFromString
import kotlinx.serialization.encodeToString
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Assume.assumeTrue
import org.junit.Test
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL
import java.time.OffsetDateTime
import java.util.UUID

/** Driven by tools/test_offline_emulators.py, with one repository and Room journal per emulator process. */
class MultiDeviceOfflineSalesTest {
    private val operator = CurrentUser(1.toBigInteger(), 1.toBigInteger(), "cashier", "Cashier",
        emptyList(), activeRoleId = 2.toBigInteger())
    private val drink = Product("Drink", 5.0, true, 1.toBigInteger(), emptyList(), true, false,
        1.toBigInteger(), 1.toBigInteger(), "tax", 0.19, ProductType.user_defined)
    private val deposit = drink.copy(name = "Deposit", price = 2.0, id = 2.toBigInteger(), isReturnable = true)

    private fun config(id: Long) = TerminalConfig(
        id = id.toBigInteger(), name = "Emulator $id", description = null,
        mode = TerminalMode.till, entryArea = null, selfService = false, appDisplayMode = null,
        eventName = "Offline test", activeUserId = operator.id, availableRoles = emptyList(),
        userPrivileges = emptyList(), secrets = null,
        till = TerminalTillConfig(id = id.toBigInteger(), name = "Till $id", description = null,
            eventName = "Offline test", profileName = "Test", cashRegisterId = null, cashRegisterName = null,
            allowTopUp = false, allowCashOut = false, allowTicketSale = false, allowTicketVouchers = false,
            enableSspPayment = true, enableCashPayment = false, enableCardPayment = false,
            buttons = emptyList(), sumupSecrets = null, postPaymentAllowed = false, sumupPaymentEnabled = false,
            userPrivileges = emptyList(), secrets = null, activeUserId = operator.id, availableRoles = emptyList()),
        testMode = true, testModeMessage = "Emulator integration test", eventNodeId = 1.toBigInteger())

    private class Coordinator(private val baseUrl: String) {
        suspend fun request(path: String, payload: JSONObject? = null): JSONObject = withContext(Dispatchers.IO) {
            val connection = URL("$baseUrl$path").openConnection() as HttpURLConnection
            try {
                connection.connectTimeout = 5_000
                connection.readTimeout = 10_000
                if (payload != null) {
                    connection.requestMethod = "POST"
                    connection.doOutput = true
                    connection.setRequestProperty("Content-Type", "application/json")
                    connection.outputStream.use { it.write(payload.toString().toByteArray(Charsets.UTF_8)) }
                }
                check(connection.responseCode == 200) { "Test coordinator HTTP ${connection.responseCode}: $path" }
                JSONObject(connection.inputStream.bufferedReader().use { it.readText() })
            } finally {
                connection.disconnect()
            }
        }
    }

    private inner class Transport(val id: Long, val coordinator: Coordinator, val scenario: String) : OfflineSalesTransport {
        var online = true
        var retryRequired = false
        var loseReplyOnce = false
        var foregroundRequests = 0

        private suspend fun <T> connected(block: suspend () -> Response<T>): Response<T> {
            if (!online) return Response.Error.Request(throwable = IOException("Injected outage on emulator $id"))
            return try { block() } catch (e: IOException) { Response.Error.Request(throwable = e) }
        }

        override suspend fun check(sale: NewSale): Response<PendingSale> {
            foregroundRequests++
            return Response.Error.Request(throwable = IOException("Online fallback disabled in this test"))
        }
        override suspend fun book(sale: NewSale): Response<CompletedSale> {
            foregroundRequests++
            return Response.Error.Request(throwable = IOException("Online fallback disabled in this test"))
        }
        override suspend fun currentUser(): Response<CurrentUser> = connected { Response.OK(operator) }
        override suspend fun prepare(): Response<PreparedOfflineSnapshot> = connected {
            val balance = coordinator.request("/balance/$scenario").getLong("balance_cents")
            val now = OffsetDateTime.now()
            val snapshot = PreparedOfflineSnapshot(UUID.randomUUID(), now, now.plusHours(2), id, id, 1, 1,
                OfflineRules(7200, 2000, 3000, if (scenario == "till-limits") 1500 else 50000, 2000, 3000, 50000),
                listOf(OfflineCustomer(1, 42.toBigInteger(), balance)),
                listOf(OfflineButton(1, "Drink", listOf(drink)), OfflineButton(2, "Deposit", listOf(deposit))))
            coordinator.request("/prepare/$scenario/$id", JSONObject(journalJson.encodeToString(snapshot)))
            Response.OK(snapshot)
        }

        private fun result(reply: JSONObject, sale: NewSale): OfflineResult {
            val status = reply.getString("status")
            if (status !in listOf("booked", "already_booked")) {
                return OfflineResult(sale.uuid, status, message = reply.optString("message"))
            }
            val snapshot = journalJson.decodeFromString<PreparedOfflineSnapshot>(reply.getJSONObject("snapshot").toString())
            val pending = validateOffline(snapshot, sale, emptyList()).pending
            val completed = CompletedSale(sale.uuid, reply.getLong("old_balance_cents") / 100.0,
                reply.getLong("new_balance_cents") / 100.0, pending.oldVoucherBalance, pending.newVoucherBalance,
                pending.customerAccountId, pending.paymentMethod, pending.lineItems, pending.buttons,
                reply.getLong("order_id").toBigInteger(), OffsetDateTime.parse(reply.getString("booked_at")),
                operator.id, id.toBigInteger(), "https://example.invalid/bon/${sale.uuid}",
                pending.usedVouchers, pending.itemCount, pending.totalPrice)
            return OfflineResult(sale.uuid, status, completed)
        }

        override suspend fun import(payload: OfflineImport): Response<OfflineResults> = connected {
            if (retryRequired) return@connected Response.OK(OfflineResults(payload.bookings.map {
                OfflineResult(it.sale.uuid, "retry_required", message = "Injected temporary server failure")
            }))
            val reply = coordinator.request("/import/$scenario/$id", JSONObject(journalJson.encodeToString(payload)))
            if (loseReplyOnce) {
                loseReplyOnce = false
                return@connected Response.Error.Request(throwable = IOException("Reply lost after server commit"))
            }
            val results = reply.getJSONArray("results")
            Response.OK(OfflineResults(payload.bookings.mapIndexed { index, booking -> result(results.getJSONObject(index), booking.sale) }))
        }

        override suspend fun status(uuid: String): Response<OfflineResult> = connected {
            val reply = coordinator.request("/status/$scenario/$uuid")
            if (reply.getString("status") == "not_found") Response.OK(OfflineResult(UUID.fromString(uuid), "not_found"))
            else Response.OK(result(reply, journalJson.decodeFromString<NewSale>(reply.getJSONObject("sale").toString())))
        }
    }

    private inner class Device(val context: Context, val id: Long, val coordinator: Coordinator) {
        var name: String? = null
        var database: JournalDatabase? = null
        lateinit var transport: Transport
        lateinit var repository: OfflineSalesRepository
        var availableBytes = Long.MAX_VALUE

        suspend fun open(scenario: String, existingName: String? = null) {
            close(delete = true)
            name = existingName ?: "offline-emulator-$id-${UUID.randomUUID()}.db"
            database = Room.databaseBuilder(context, JournalDatabase::class.java, name!!).build()
            transport = Transport(id, coordinator, scenario)
            repository = repository()
            repository.rememberConfig(config(id))
            if (existingName == null) repository.rememberUser(operator)
            assertNotNull(database!!.journal().preparation())
        }

        fun repository() = OfflineSalesRepository(SalesJournal(database!!), transport,
            { RegistrationState.Registered("test-emulator-$id", "https://example.invalid/") }, context, { availableBytes })

        fun close(delete: Boolean) {
            database?.close()
            database = null
            if (delete) name?.let { context.deleteDatabase(it) }
        }

        suspend fun state(): JSONObject {
            val rows = database!!.journal().sales()
            return JSONObject().put("database", name).put("scenario", transport.scenario)
                .put("foreground_requests", transport.foregroundRequests)
                .put("rows", org.json.JSONArray(rows.map { row -> JSONObject()
                    .put("uuid", row.uuid).put("state", row.state).put("transfer_state", row.transferState)
                    .put("sequence", row.sequence).put("debit_cents", row.debitCents)
                    .put("snapshot_id", row.snapshotId).put("payload", row.payload) }))
        }

        suspend fun execute(command: JSONObject): JSONObject {
            when (command.getString("operation")) {
                "reset" -> { availableBytes = Long.MAX_VALUE; open(command.getString("scenario")) }
                "network" -> {
                    transport.online = command.getBoolean("online")
                    transport.retryRequired = command.optBoolean("retry_required", false)
                    transport.loseReplyOnce = command.optBoolean("lose_reply_once", false)
                }
                "sale" -> {
                    // Same UID as the NFC scan boundary supplies, created entirely inside the test APK.
                    val sale = NewSale(UUID.fromString(command.getString("uuid")), PaymentMethod.tag,
                        listOf(Button(command.optLong("button", 1).toBigInteger(), command.optLong("quantity", 1).toBigInteger())),
                        command.optLong("tag", 42).toBigInteger(), usedVouchers = command.optLong("vouchers", 0).toBigInteger())
                    val checked = repository.check(sale)
                    if (command.getBoolean("accepted")) {
                        assertTrue("Sale check failed: $checked", checked is Response.OK)
                        val booked = repository.book(sale)
                        assertTrue("Expected durable local acceptance: $booked", booked is Response.OK && booked.data is SaleBookingOutcome.LocalAccepted)
                    } else {
                        assertTrue("Invalid sale accepted: $checked", checked is Response.Error)
                        assertNull(database!!.journal().sale(sale.uuid.toString()))
                    }
                }
                "synchronize" -> assertEquals(command.getBoolean("success"), repository.synchronize())
                "replay" -> {
                    val row = database!!.journal().sale(command.getString("uuid"))!!
                    assertTrue(repository.book(journalJson.decodeFromString<NewSale>(row.payload)) is Response.OK)
                }
                "storage" -> availableBytes = command.getLong("bytes")
                "expire" -> {
                    val preparation = database!!.journal().preparation()!!
                    val snapshot = journalJson.decodeFromString<PreparedOfflineSnapshot>(preparation.payload)
                    database!!.journal().prepare(preparation.copy(payload = journalJson.encodeToString(
                        snapshot.copy(validUntil = OffsetDateTime.now().minusMinutes(1)))))
                }
                "revoke" -> repository.revoke()
                "state", "pause", "finish" -> Unit
                else -> error("Unknown emulator command: $command")
            }
            return state()
        }
    }

    @Test fun coordinatedOfflineScenarios() = runBlocking {
        val arguments = InstrumentationRegistry.getArguments()
        // Ordinary connectedAndroidTest runs skip this opt-in test; the host runner supplies its coordinator.
        assumeTrue(arguments.containsKey("offlineCoordinator"))
        val id = arguments.getString("offlineTerminal")!!.toLong()
        val coordinator = Coordinator(arguments.getString("offlineCoordinator")!!)
        val device = Device(InstrumentationRegistry.getInstrumentation().targetContext, id, coordinator)
        var preserveJournal = false
        try {
            withTimeout(300_000) {
                arguments.getString("offlineDatabase")?.let { device.open(arguments.getString("offlineScenario")!!, it) }
                coordinator.request("/ready/$id", JSONObject())
                while (true) {
                    val command = coordinator.request("/command/$id")
                    if (!command.has("operation")) { delay(100); continue }
                    val result = JSONObject().put("id", command.getString("id"))
                    try {
                        result.put("state", device.execute(command)).put("ok", true)
                    } catch (error: Throwable) {
                        result.put("ok", false).put("error", error.stackTraceToString())
                        coordinator.request("/result/$id", result)
                        throw error
                    }
                    coordinator.request("/result/$id", result)
                    when (command.getString("operation")) {
                        "pause" -> { preserveJournal = true; break }
                        "finish" -> break
                    }
                }
            }
        } finally {
            device.close(delete = !preserveJournal)
        }
    }
}
