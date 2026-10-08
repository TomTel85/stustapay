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
