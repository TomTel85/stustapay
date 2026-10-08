package de.stustapay.stustapay.offline

import androidx.room.Room
import androidx.room.withTransaction
import androidx.test.platform.app.InstrumentationRegistry
import kotlinx.coroutines.runBlocking
import org.junit.Assert.*
import org.junit.Test
import java.util.UUID

/** Runs against the real SQLite journal on an Android device/emulator. */
class SalesJournalPersistenceTest {
    @Test fun admissionAndBudgetSurviveDatabaseReopen() = runBlocking {
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        val name = "journal-test-${UUID.randomUUID()}.db"
        fun open() = Room.databaseBuilder(context, JournalDatabase::class.java, name).build()
        var db = open()
        try {
            db.withTransaction {
                db.journal().insert(JournalSale("uuid", "immutable-payload", state = "offline", sequence = 1,
                    recordedAt = "timestamp", debitCents = 1500, saleCents = 1500, offline = true, result = "immutable-receipt"))
            }
            db.close()
            db = open()
            val row = db.journal().sale("uuid")!!
            assertEquals("immutable-payload", row.payload)
            assertEquals(1500L, row.debitCents)
            assertEquals("immutable-receipt", row.result)
            assertEquals("offline", row.state)
        } finally { db.close(); context.deleteDatabase(name) }
    }
    @Test fun interruptedAdmissionRollsBackAndUuidCannotBeDuplicated() = runBlocking {
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        val db = Room.inMemoryDatabaseBuilder(context, JournalDatabase::class.java).build()
        try {
            val row = JournalSale("uuid", "payload", sequence = 1, recordedAt = "timestamp")
            try {
                db.withTransaction { db.journal().insert(row); error("Simulated interruption") }
            } catch (_: IllegalStateException) { }
            assertNull(db.journal().sale("uuid"))
            db.journal().insert(row)
            try { db.journal().insert(row); fail("Duplicate UUID must fail") } catch (_: android.database.sqlite.SQLiteConstraintException) { }
            assertEquals(1, db.journal().sales().size)
        } finally { db.close() }
    }
}
