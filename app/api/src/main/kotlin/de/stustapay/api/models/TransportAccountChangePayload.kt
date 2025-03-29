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


import kotlinx.serialization.Serializable
import kotlinx.serialization.SerialName
import kotlinx.serialization.Contextual

/**
 * 
 *
 * @param orgaTagUid 
 * @param amount 
 */
@Serializable

data class TransportAccountChangePayload (

    @SerialName(value = "orga_tag_uid")
    val orgaTagUid: @Contextual com.ionspin.kotlin.bignum.integer.BigInteger,

    @Contextual @SerialName(value = "amount")
    val amount: kotlin.Double

) {


}

