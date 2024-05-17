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

import de.stustapay.api.models.Ticket

import kotlinx.serialization.Serializable
import kotlinx.serialization.SerialName
import kotlinx.serialization.Contextual

/**
 * 
 *
 * @param customerTagUid 
 * @param customerTagPin 
 * @param ticket 
 */
@Serializable

data class TicketScanResultEntry (

    @SerialName(value = "customer_tag_uid")
    val customerTagUid: @Contextual com.ionspin.kotlin.bignum.integer.BigInteger,

    @SerialName(value = "customer_tag_pin")
    val customerTagPin: kotlin.String,

    @SerialName(value = "ticket")
    val ticket: Ticket

)
