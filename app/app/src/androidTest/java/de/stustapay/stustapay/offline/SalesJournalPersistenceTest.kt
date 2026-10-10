package de.stustapay.stustapay.offline

import android.database.sqlite.SQLiteDatabase
import android.database.sqlite.SQLiteOpenHelper
import androidx.room.Room
import androidx.room.withTransaction
import androidx.test.platform.app.InstrumentationRegistry
import kotlinx.coroutines.runBlocking
import org.junit.Assert.*
import org.junit.Test
import java.util.UUID

/** Runs against the real SQLite journal on an Android device/emulator. */
class SalesJournalPersistenceTest {
    @Test fun versionOneDatabaseMigratesJournalAndPreparation() = runBlocking {
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        val name = "journal-migration-${UUID.randomUUID()}.db"
        val legacy = object : SQLiteOpenHelper(context, name, null, 1) {
            override fun onCreate(db: SQLiteDatabase) {
                db.execSQL("""CREATE TABLE sales_journal (
                    uuid TEXT NOT NULL PRIMARY KEY, payload TEXT NOT NULL, operatorId TEXT, legacy INTEGER NOT NULL,
                    operatorRole TEXT, state TEXT NOT NULL, transferState TEXT NOT NULL, attemptedOnline INTEGER NOT NULL,
                    snapshotId TEXT, sequence INTEGER NOT NULL, recordedAt TEXT NOT NULL, tagUid TEXT,
                    debitCents INTEGER NOT NULL, saleCents INTEGER NOT NULL, returnCents INTEGER NOT NULL,
                    offline INTEGER NOT NULL, result TEXT, message TEXT)""")
                db.execSQL("""CREATE TABLE offline_preparation (
                    `key` INTEGER NOT NULL PRIMARY KEY, payload TEXT NOT NULL, registration TEXT NOT NULL,
                    user TEXT NOT NULL, config TEXT NOT NULL, receivedWall INTEGER NOT NULL, bootCount INTEGER NOT NULL,
                    receivedElapsed INTEGER NOT NULL, lastWall INTEGER NOT NULL, lastElapsed INTEGER NOT NULL,
                    revoked INTEGER NOT NULL)""")
            }

            override fun onUpgrade(db: SQLiteDatabase, oldVersion: Int, newVersion: Int) = Unit
        }

        var db: JournalDatabase? = null
        try {
            legacy.writableDatabase.use { sqlite ->
                sqlite.execSQL("""INSERT INTO sales_journal VALUES (
                    'old-sale', 'legacy-payload', 'operator-7', 1, 'cashier', 'offline', 'queued', 1,
                    'snapshot-3', 42, '2026-10-08T12:00:00Z', 'tag-9', 1200, 1500, 300, 1,
                    'legacy-result', 'legacy-message')""")
                sqlite.execSQL("""INSERT INTO offline_preparation VALUES (
                    1, 'prep-payload', 'registration-1', 'user-2', 'config-3', 1000, 4, 500,
                    2000, 600, 0)""")
            }
            legacy.close()

            db = Room.databaseBuilder(context, JournalDatabase::class.java, name)
                .addMigrations(JOURNAL_MIGRATION_1_2, JOURNAL_MIGRATION_2_3).build()
            val sale = db!!.journal().sale("old-sale")!!
            assertEquals("legacy-payload", sale.payload)
            assertEquals("operator-7", sale.operatorId)
            assertTrue(sale.legacy)
            assertEquals("cashier", sale.operatorRole)
            assertEquals("offline", sale.state)
            assertEquals("queued", sale.transferState)
            assertTrue(sale.attemptedOnline)
            assertEquals("snapshot-3", sale.snapshotId)
            assertEquals(42L, sale.sequence)
            assertEquals("2026-10-08T12:00:00Z", sale.recordedAt)
            assertEquals("tag-9", sale.tagUid)
            assertEquals(1200L, sale.debitCents)
            assertEquals(1500L, sale.saleCents)
            assertEquals(300L, sale.returnCents)
            assertTrue(sale.offline)
            assertEquals("legacy-result", sale.result)
            assertEquals("legacy-message", sale.message)
            assertNull(sale.localReceipt)

            val preparation = db!!.journal().preparation()!!
            assertEquals("prep-payload", preparation.payload)
            assertEquals("registration-1", preparation.registration)
            assertEquals("user-2", preparation.user)
            assertEquals("config-3", preparation.config)
            assertEquals(1000L, preparation.receivedWall)
            assertEquals(4, preparation.bootCount)
            assertEquals(500L, preparation.receivedElapsed)
            assertEquals(2000L, preparation.lastWall)
            assertEquals(600L, preparation.lastElapsed)
            assertFalse(preparation.revoked)

            db!!.journal().syncMetadata(JournalSyncMetadata(lastSynchronizedAt = "2026-10-08T12:30:00Z"))
            db!!.close()
            db = Room.databaseBuilder(context, JournalDatabase::class.java, name)
                .addMigrations(JOURNAL_MIGRATION_1_2, JOURNAL_MIGRATION_2_3).build()
            assertEquals("2026-10-08T12:30:00Z", db!!.journal().syncMetadata()!!.lastSynchronizedAt)
            assertEquals("legacy-payload", db!!.journal().sale("old-sale")!!.payload)
        } finally {
            db?.close()
            legacy.close()
            context.deleteDatabase(name)
        }
    }

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

    @Test fun retentionPreservesOpenActiveAndWatermarkRowsAndPagesRemainingJournal() = runBlocking {
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        val name = "journal-retention-${UUID.randomUUID()}.db"
        val db = Room.databaseBuilder(context, JournalDatabase::class.java, name).build()
        try {
            val rows = listOf(
                journalRow("expired", 1, "booked", "confirmed", "old-snapshot", "2026-01-01T00:00:00Z"),
                journalRow("over-cap-one", 2, "dismissed", "confirmed", "old-snapshot", "2026-10-03T00:00:00Z"),
                journalRow("over-cap-two", 3, "rejected", "confirmed", "old-snapshot", "2026-10-04T00:00:00Z"),
                journalRow("active-confirmed", 4, "booked", "confirmed", "active-snapshot", "2026-01-02T00:00:00Z"),
                journalRow("active-confirmed-recent", 5, "booked", "confirmed", "active-snapshot", "2026-10-06T00:00:00Z"),
                journalRow("waiting-open", 6, "waiting", "queued", "old-snapshot", "2026-01-03T00:00:00Z"),
                journalRow("offline-open", 7, "offline", "queued", "old-snapshot", "2026-01-04T00:00:00Z"),
                journalRow("clarification-open", 8, "clarification", "blocked", "old-snapshot", "2026-01-05T00:00:00Z"),
                journalRow("terminal-transfer-pending", 9, "booked", "pending", "old-snapshot", "2026-01-06T00:00:00Z"),
                journalRow("recent-retained", 10, "booked", "confirmed", "old-snapshot", "2026-10-05T00:00:00Z"),
                journalRow("sequence-watermark", 11, "booked", "confirmed", "old-snapshot", "2026-01-07T00:00:00Z"),
            )
            db.withTransaction { rows.forEach { db.journal().insert(it) } }

            val deleted = db.journal().pruneSettled(
                activeSnapshot = "active-snapshot",
                cutoff = "2026-10-01T00:00:00Z",
                retained = 2,
            )

            assertEquals(3, deleted)
            val remaining = db.journal().sales()
            assertEquals(
                listOf("active-confirmed", "active-confirmed-recent", "waiting-open", "offline-open", "clarification-open", "terminal-transfer-pending", "recent-retained", "sequence-watermark"),
                remaining.map { it.uuid },
            )
            assertEquals(11L, db.journal().lastSequence())
            assertEquals(
                listOf("sequence-watermark", "recent-retained", "terminal-transfer-pending"),
                db.journal().page(limit = 3, offset = 0).map { it.uuid },
            )
            assertEquals(
                listOf("clarification-open", "offline-open"),
                db.journal().page(limit = 2, offset = 3).map { it.uuid },
            )
        } finally {
            db.close()
            context.deleteDatabase(name)
        }
    }

    private fun journalRow(
        uuid: String,
        sequence: Long,
        state: String,
        transferState: String,
        snapshotId: String,
        recordedAt: String,
    ) = JournalSale(
        uuid = uuid,
        payload = "payload-$uuid",
        sequence = sequence,
        recordedAt = recordedAt,
        state = state,
        transferState = transferState,
        snapshotId = snapshotId,
        saleCents = sequence * 100,
    )

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
