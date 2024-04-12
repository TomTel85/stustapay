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

import de.stustapay.api.models.ProductRestriction
import de.stustapay.api.models.ProductType

import kotlinx.serialization.Serializable
import kotlinx.serialization.SerialName
import kotlinx.serialization.Contextual

/**
 * 
 *
 * @param name 
 * @param price 
 * @param fixedPrice 
 * @param taxRateId 
 * @param restrictions 
 * @param isLocked 
 * @param isReturnable 
 * @param nodeId 
 * @param id 
 * @param taxName 
 * @param taxRate 
 * @param type 
 * @param priceInVouchers 
 * @param targetAccountId 
 * @param pricePerVoucher 
 */
@Serializable

data class Product (

    @SerialName(value = "name")
    val name: kotlin.String,

    @Contextual @SerialName(value = "price")
    val price: kotlin.Double?,

    @SerialName(value = "fixed_price")
    val fixedPrice: kotlin.Boolean,

    @SerialName(value = "tax_rate_id")
    val taxRateId: @Contextual com.ionspin.kotlin.bignum.integer.BigInteger,

    @SerialName(value = "restrictions")
    val restrictions: kotlin.collections.List<@Contextual ProductRestriction>,

    @SerialName(value = "is_locked")
    val isLocked: kotlin.Boolean,

    @SerialName(value = "is_returnable")
    val isReturnable: kotlin.Boolean,

    @SerialName(value = "node_id")
    val nodeId: @Contextual com.ionspin.kotlin.bignum.integer.BigInteger,

    @SerialName(value = "id")
    val id: @Contextual com.ionspin.kotlin.bignum.integer.BigInteger,

    @SerialName(value = "tax_name")
    val taxName: kotlin.String,

    @Contextual @SerialName(value = "tax_rate")
    val taxRate: kotlin.Double,

    @Contextual @SerialName(value = "type")
    val type: ProductType,

    @SerialName(value = "price_in_vouchers")
    val priceInVouchers: @Contextual com.ionspin.kotlin.bignum.integer.BigInteger? = null,

    @SerialName(value = "target_account_id")
    val targetAccountId: @Contextual com.ionspin.kotlin.bignum.integer.BigInteger? = null,

    @Contextual @SerialName(value = "price_per_voucher")
    val pricePerVoucher: kotlin.Double? = null

)

