package de.stustapay.stustapay.offline

import de.stustapay.api.models.*
import kotlinx.serialization.Serializable
import kotlinx.serialization.SerialName
import kotlinx.serialization.Contextual
import java.time.OffsetDateTime
import java.util.UUID

@Serializable
data class OfflineRules(
    @SerialName("validity_seconds") val validitySeconds: Long,
    @SerialName("sale_per_transaction_cents") val saleTransaction: Long,
    @SerialName("sale_per_customer_cents") val saleCustomer: Long,
    @SerialName("sale_per_till_cents") val saleTill: Long,
    @SerialName("return_per_transaction_cents") val returnTransaction: Long,
    @SerialName("return_per_customer_cents") val returnCustomer: Long,
    @SerialName("return_per_till_cents") val returnTill: Long,
)
@Serializable
data class OfflineCustomer(
    @SerialName("customer_account_id") val accountId: Long,
    @SerialName("customer_tag_uid") val tagUid: @Contextual com.ionspin.kotlin.bignum.integer.BigInteger,
    @SerialName("balance_cents") val balance: Long,
    val restriction: ProductRestriction? = null,
)
@Serializable
data class OfflineButton(val id: Long, val name: String, val products: List<Product>)
@Serializable
data class PreparedOfflineSnapshot(
    @Contextual val id: UUID,
    @SerialName("server_time") @Contextual val serverTime: OffsetDateTime,
    @SerialName("valid_until") @Contextual val validUntil: OffsetDateTime,
    @SerialName("terminal_id") val terminalId: Long,
    @SerialName("till_id") val tillId: Long,
    @SerialName("event_node_id") val eventNodeId: Long,
    @SerialName("user_id") val userId: Long,
    val rules: OfflineRules,
    val customers: List<OfflineCustomer>,
    val buttons: List<OfflineButton>,
    val capabilities: List<String> = listOf("fixed_price", "deposit_return"),
)
@Serializable
data class OfflineBooking(
    @SerialName("snapshot_id") @Contextual val snapshotId: UUID,
    val sale: NewSale,
    val sequence: Long,
    @SerialName("recorded_at") @Contextual val recordedAt: OffsetDateTime,
)
@Serializable
data class OfflineImport(val bookings: List<OfflineBooking>)
@Serializable
data class OfflineResult(@Contextual val uuid: UUID, val status: String, val sale: CompletedSale? = null, val message: String? = null)
@Serializable
data class OfflineResults(val results: List<OfflineResult>)

/** Preserve admission order, keeping each import scoped to one snapshot and at most 100 rows. */
internal fun offlineBatches(rows: List<JournalSale>): List<List<JournalSale>> {
    val batches = mutableListOf<MutableList<JournalSale>>()
    for (row in rows.sortedBy { it.sequence }) {
        val last = batches.lastOrNull()
        if (last == null || last.size == 100 || last.first().snapshotId != row.snapshotId) batches.add(mutableListOf(row))
        else last.add(row)
    }
    return batches
}

/** Unsolicited, duplicated or mismatched replies cannot confirm an unrelated booking. */
internal fun matchedOfflineReplies(rows: List<JournalSale>, replies: List<OfflineResult>): Map<String, OfflineResult> {
    val expected = rows.map { it.uuid }.toSet()
    return replies.groupBy { it.uuid.toString() }.mapNotNull { (uuid, group) ->
        val reply = group.singleOrNull()
        if (uuid !in expected || reply == null || reply.sale?.uuid?.toString()?.let { it != uuid } == true ||
            (reply.status in setOf("booked", "already_booked") && reply.sale == null) ||
            reply.status !in setOf("booked", "already_booked", "retry_required", "clarification_required", "dismissed")) null
        else uuid to reply
    }.toMap()
}
