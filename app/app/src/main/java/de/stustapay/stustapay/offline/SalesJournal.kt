package de.stustapay.stustapay.offline

import android.content.Context
import androidx.room.*
import dagger.hilt.android.qualifiers.ApplicationContext
import javax.inject.Inject
import javax.inject.Singleton
import kotlinx.coroutines.flow.Flow

@Entity(tableName = "sales_journal", indices = [Index("sequence"), Index("snapshotId"), Index("state")])
data class JournalSale(
    @PrimaryKey val uuid: String,
    val payload: String,
    val operatorId: String? = null,
    val legacy: Boolean = false,
    val operatorRole: String? = null,
    val state: String = "waiting",
    val transferState: String = "queued",
    val attemptedOnline: Boolean = false,
    val snapshotId: String? = null,
    val sequence: Long,
    val recordedAt: String,
    val tagUid: String? = null,
    val debitCents: Long = 0,
    val saleCents: Long = 0,
    val returnCents: Long = 0,
    val offline: Boolean = false,
    val result: String? = null,
    val message: String? = null,
    val localReceipt: String? = null,
)
@Entity(tableName = "offline_preparation")
data class JournalPreparation(
    @PrimaryKey val key: Int = 1,
    val payload: String,
    val registration: String,
    val user: String,
    val config: String,
    val receivedWall: Long,
    val bootCount: Int,
    val receivedElapsed: Long,
    val lastWall: Long,
    val lastElapsed: Long,
    val revoked: Boolean = false,
)
@Entity(tableName = "journal_sync_metadata")
data class JournalSyncMetadata(@PrimaryKey val key: Int = 1, val lastSynchronizedAt: String? = null)

@Dao
interface JournalDao {
    @Query("SELECT COUNT(*) FROM sales_journal") fun observeCount(): Flow<Int>
    @Query("SELECT uuid, saleCents - returnCents AS amountCents, recordedAt, state, transferState, message FROM sales_journal ORDER BY sequence DESC LIMIT :limit OFFSET :offset")
    suspend fun page(limit: Int, offset: Int): List<JournalEntrySummary>
    @Query("SELECT * FROM sales_journal WHERE snapshotId = :snapshotId OR state = 'waiting' ORDER BY sequence")
    suspend fun validationHistory(snapshotId: String): List<JournalSale>
    @Query("SELECT * FROM sales_journal WHERE state IN ('waiting','offline','clarification') ORDER BY sequence")
    suspend fun unresolved(): List<JournalSale>
    @Query("SELECT COUNT(*) FROM sales_journal WHERE state IN ('waiting','offline','clarification')")
    suspend fun unresolvedCount(): Int
    @Query("SELECT COALESCE(MAX(sequence), 0) FROM sales_journal") suspend fun lastSequence(): Long
    // Keep the highest sequence as a persistent watermark, even if every other old entry expires.
    @Query("""DELETE FROM sales_journal WHERE state IN ('booked','dismissed','rejected','local_rejected')
        AND transferState = 'confirmed' AND (snapshotId IS NULL OR snapshotId != :activeSnapshot)
        AND sequence < (SELECT MAX(sequence) FROM sales_journal)
        AND (julianday(recordedAt) < julianday(:cutoff) OR uuid NOT IN
            (SELECT uuid FROM sales_journal WHERE state IN ('booked','dismissed','rejected','local_rejected')
                AND transferState = 'confirmed' ORDER BY sequence DESC LIMIT :retained))""")
    suspend fun pruneSettled(activeSnapshot: String, cutoff: String, retained: Int): Int
    @Query("SELECT * FROM sales_journal ORDER BY sequence") suspend fun sales(): List<JournalSale>
    @Query("SELECT * FROM sales_journal ORDER BY sequence") fun observeSales(): Flow<List<JournalSale>>
    @Query("SELECT * FROM sales_journal WHERE uuid = :uuid") suspend fun sale(uuid: String): JournalSale?
    @Insert(onConflict = OnConflictStrategy.ABORT) suspend fun insert(sale: JournalSale)
    @Update suspend fun update(sale: JournalSale)
    @Query("SELECT COUNT(*) FROM sales_journal WHERE state IN ('waiting','offline','clarification')") fun pending(): Flow<Int>
    @Query("SELECT COUNT(*) FROM sales_journal WHERE legacy = 1 AND operatorId IS NULL AND state = 'waiting'") fun legacyNeedsOwner(): Flow<Int>
    @Query("SELECT * FROM offline_preparation WHERE `key` = 1") suspend fun preparation(): JournalPreparation?
    @Insert(onConflict = OnConflictStrategy.REPLACE) suspend fun prepare(preparation: JournalPreparation)
    @Query("UPDATE offline_preparation SET revoked = 1 WHERE `key` = 1") suspend fun revoke()
    @Query("SELECT * FROM journal_sync_metadata WHERE `key` = 1") suspend fun syncMetadata(): JournalSyncMetadata?
    @Insert(onConflict = OnConflictStrategy.REPLACE) suspend fun syncMetadata(value: JournalSyncMetadata)
}
val JOURNAL_MIGRATION_1_2 = object : androidx.room.migration.Migration(1, 2) {
    override fun migrate(db: androidx.sqlite.db.SupportSQLiteDatabase) {
        db.execSQL("ALTER TABLE sales_journal ADD COLUMN localReceipt TEXT DEFAULT NULL")
        db.execSQL("CREATE TABLE IF NOT EXISTS journal_sync_metadata (`key` INTEGER NOT NULL, lastSynchronizedAt TEXT, PRIMARY KEY(`key`))")
    }
}
val JOURNAL_MIGRATION_2_3 = object : androidx.room.migration.Migration(2, 3) {
    override fun migrate(db: androidx.sqlite.db.SupportSQLiteDatabase) {
        db.execSQL("CREATE INDEX IF NOT EXISTS index_sales_journal_sequence ON sales_journal(sequence)")
        db.execSQL("CREATE INDEX IF NOT EXISTS index_sales_journal_snapshotId ON sales_journal(snapshotId)")
        db.execSQL("CREATE INDEX IF NOT EXISTS index_sales_journal_state ON sales_journal(state)")
    }
}

@Database(entities = [JournalSale::class, JournalPreparation::class, JournalSyncMetadata::class], version = 3, exportSchema = false)
abstract class JournalDatabase : RoomDatabase() { abstract fun journal(): JournalDao }
@Singleton
class SalesJournal internal constructor(val database: JournalDatabase) {
    @Inject constructor(@ApplicationContext context: Context) : this(
        Room.databaseBuilder(context, JournalDatabase::class.java, "sales-journal.db").addMigrations(JOURNAL_MIGRATION_1_2, JOURNAL_MIGRATION_2_3).build()
    )
    val dao = database.journal()
    suspend fun hasUnresolved() = dao.unresolvedCount() != 0
}

/** Merge a delayed reply without erasing a sale accepted locally in the meantime. */
internal fun reconcileJournalReply(current: JournalSale, status: String, result: String?, message: String?,
    requestedOffline: Boolean, confirmedDebit: Long? = null): JournalSale {
    if (current.state in setOf("booked", "dismissed")) return current
    if (current.state in setOf("rejected", "local_rejected") && status !in setOf("booked", "already_booked")) return current
    if (status == "retry_required") return current.copy(
        state = if (current.offline) "offline" else "waiting", transferState = "queued", message = message,
    )
    if (current.offline && !requestedOffline && status !in setOf("booked", "already_booked", "dismissed")) {
        return current.copy(transferState = "queued")
    }
    val booked = status in setOf("booked", "already_booked") && result != null
    val state = when { booked -> "booked"; status == "dismissed" -> "dismissed"; status == "rejected" -> "rejected"; else -> "clarification" }
    return current.copy(state = state, transferState = if (state == "clarification") "blocked" else "confirmed",
        result = result ?: current.result, message = message,
        debitCents = if (current.offline) current.debitCents else confirmedDebit ?: current.debitCents)
}
