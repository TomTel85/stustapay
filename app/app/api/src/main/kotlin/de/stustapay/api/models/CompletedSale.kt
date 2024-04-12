/**
 *
 * Please note:
 * This class is auto generated by OpenAPI Generator (https://openapi-generator.tech).
 * Do not edit this file manually.
 *
 */

@file:Suppress(
    "ArrayInDataClass",
    "EnumEntryName",
    "RemoveRedundantQualifierName",
    "UnusedImport"
)

package de.stustapay.api.models

import de.stustapay.api.models.Button
import de.stustapay.api.models.PendingLineItem

import kotlinx.serialization.Serializable
import kotlinx.serialization.SerialName
import kotlinx.serialization.Contextual

/**
 * 
 *
 * @param uuid 
 * @param oldBalance 
 * @param newBalance 
 * @param oldVoucherBalance 
 * @param newVoucherBalance 
 * @param customerAccountId 
 * @param lineItems 
 * @param buttons 
 * @param id 
 * @param bookedAt 
 * @param cashierId 
 * @param tillId 
 * @param usedVouchers 
 * @param itemCount 
 * @param totalPrice 
 */
@Serializable

data class CompletedSale (

    @Contextual @SerialName(value = "uuid")
    val uuid: java.util.UUID,

    @Contextual @SerialName(value = "old_balance")
    val oldBalance: kotlin.Double,

    @Contextual @SerialName(value = "new_balance")
    val newBalance: kotlin.Double,

    @SerialName(value = "old_voucher_balance")
    val oldVoucherBalance: @Contextual com.ionspin.kotlin.bignum.integer.BigInteger,

    @SerialName(value = "new_voucher_balance")
    val newVoucherBalance: @Contextual com.ionspin.kotlin.bignum.integer.BigInteger,

    @SerialName(value = "customer_account_id")
    val customerAccountId: @Contextual com.ionspin.kotlin.bignum.integer.BigInteger,

    @SerialName(value = "line_items")
    val lineItems: kotlin.collections.List<PendingLineItem>,

    @SerialName(value = "buttons")
    val buttons: kotlin.collections.List<Button>,

    @SerialName(value = "id")
    val id: @Contextual com.ionspin.kotlin.bignum.integer.BigInteger,

    @Contextual @SerialName(value = "booked_at")
    val bookedAt: java.time.OffsetDateTime,

    @SerialName(value = "cashier_id")
    val cashierId: @Contextual com.ionspin.kotlin.bignum.integer.BigInteger,

    @SerialName(value = "till_id")
    val tillId: @Contextual com.ionspin.kotlin.bignum.integer.BigInteger,

    @SerialName(value = "used_vouchers")
    val usedVouchers: @Contextual com.ionspin.kotlin.bignum.integer.BigInteger,

    @SerialName(value = "item_count")
    val itemCount: @Contextual com.ionspin.kotlin.bignum.integer.BigInteger,

    @Contextual @SerialName(value = "total_price")
    val totalPrice: kotlin.Double

)

