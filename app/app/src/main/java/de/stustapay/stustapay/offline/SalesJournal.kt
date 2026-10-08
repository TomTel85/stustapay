package de.stustapay.stustapay.offline

import android.content.Context
import androidx.room.*
import dagger.hilt.android.qualifiers.ApplicationContext
import javax.inject.Inject
import javax.inject.Singleton
import kotlinx.coroutines.flow.Flow

@Entity(tableName = "sales_journal")
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
@Dao
interface JournalDao {
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
}
@Database(entities = [JournalSale::class, JournalPreparation::class], version = 1, exportSchema = false)
abstract class JournalDatabase : RoomDatabase() { abstract fun journal(): JournalDao }
@Singleton
class SalesJournal @Inject constructor(@ApplicationContext context: Context) {
    val database = Room.databaseBuilder(context, JournalDatabase::class.java, "sales-journal.db").build()
    val dao = database.journal()
    suspend fun hasUnresolved() = dao.sales().any { it.state in setOf("waiting", "offline", "clarification") }
}

/** Merge a delayed reply without erasing a sale accepted locally in the meantime. */
internal fun reconcileJournalReply(current: JournalSale, status: String, result: String?, message: String?,
    requestedOffline: Boolean, confirmedDebit: Long? = null): JournalSale {
    if (current.state in setOf("booked", "dismissed")) return current
    if (current.state in setOf("rejected", "local_rejected") && status !in setOf("booked", "already_booked")) return current
    if (current.offline && !requestedOffline && status !in setOf("booked", "already_booked", "dismissed")) {
        return current.copy(transferState = "queued")
    }
    val booked = status in setOf("booked", "already_booked") && result != null
    val state = when { booked -> "booked"; status == "dismissed" -> "dismissed"; status == "rejected" -> "rejected"; else -> "clarification" }
    return current.copy(state = state, transferState = if (state == "clarification") "blocked" else "confirmed",
        result = result ?: current.result, message = message,
        debitCents = if (current.offline) current.debitCents else confirmedDebit ?: current.debitCents)
}
