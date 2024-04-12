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

import de.stustapay.api.models.AccountType
import de.stustapay.api.models.ProductRestriction
import de.stustapay.api.models.UserTagHistoryEntry

import kotlinx.serialization.Serializable
import kotlinx.serialization.SerialName
import kotlinx.serialization.Contextual

/**
 * 
 *
 * @param nodeId 
 * @param id 
 * @param type 
 * @param name 
 * @param comment 
 * @param balance 
 * @param vouchers 
 * @param userTagUid 
 * @param restriction 
 * @param tagHistory 
 * @param iban 
 * @param accountName 
 * @param email 
 * @param donation 
 * @param payoutError 
 * @param payoutRunId 
 * @param payoutExport 
 * @param userTagUidHex 
 * @param userTagComment 
 */
@Serializable

data class Customer (

    @SerialName(value = "node_id")
    val nodeId: @Contextual com.ionspin.kotlin.bignum.integer.BigInteger,

    @SerialName(value = "id")
    val id: @Contextual com.ionspin.kotlin.bignum.integer.BigInteger,

    @Contextual @SerialName(value = "type")
    val type: AccountType,

    @SerialName(value = "name")
    val name: kotlin.String?,

    @SerialName(value = "comment")
    val comment: kotlin.String?,

    @Contextual @SerialName(value = "balance")
    val balance: kotlin.Double,

    @SerialName(value = "vouchers")
    val vouchers: @Contextual com.ionspin.kotlin.bignum.integer.BigInteger,

    @SerialName(value = "user_tag_uid")
    val userTagUid: @Contextual com.ionspin.kotlin.bignum.integer.BigInteger?,

    @Contextual @SerialName(value = "restriction")
    val restriction: ProductRestriction?,

    @SerialName(value = "tag_history")
    val tagHistory: kotlin.collections.List<UserTagHistoryEntry>,

    @SerialName(value = "iban")
    val iban: kotlin.String?,

    @SerialName(value = "account_name")
    val accountName: kotlin.String?,

    @SerialName(value = "email")
    val email: kotlin.String?,

    @Contextual @SerialName(value = "donation")
    val donation: kotlin.Double?,

    @SerialName(value = "payout_error")
    val payoutError: kotlin.String?,

    @SerialName(value = "payout_run_id")
    val payoutRunId: @Contextual com.ionspin.kotlin.bignum.integer.BigInteger?,

    @SerialName(value = "payout_export")
    val payoutExport: kotlin.Boolean?,

    @SerialName(value = "user_tag_uid_hex")
    val userTagUidHex: kotlin.String?,

    @SerialName(value = "user_tag_comment")
    val userTagComment: kotlin.String? = null

)

