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


import de.stustapay.api.models.TerminalSecrets
import de.stustapay.api.models.UserRole

import kotlinx.serialization.Serializable
import kotlinx.serialization.SerialName
import kotlinx.serialization.Contextual

/**
 * 
 *
 * @param id 
 * @param name 
 * @param description 
 * @param eventName 
 * @param profileName 
 * @param userPrivileges 
 * @param cashRegisterId 
 * @param cashRegisterName 
 * @param allowTopUp 
 * @param allowCashOut 
 * @param allowTicketSale 
 * @param enableSspPayment 
 * @param enableCashPayment 
 * @param enableCardPayment 
 * @param buttons 
 * @param secrets 
 * @param activeUserId 
 * @param availableRoles
 * @param postPaymentAllowed 
 * @param sumupPaymentEnabled 
 */
@Serializable

data class TerminalTillConfig (

    @SerialName(value = "id")
    val id: @Contextual com.ionspin.kotlin.bignum.integer.BigInteger,

    @SerialName(value = "name")
    val name: kotlin.String,

    @SerialName(value = "description")
    val description: kotlin.String?,

    @SerialName(value = "event_name")
    val eventName: kotlin.String,

    @SerialName(value = "profile_name")
    val profileName: kotlin.String,

    @SerialName(value = "user_privileges")
    val userPrivileges: kotlin.collections.List<Privilege>?,

    @SerialName(value = "cash_register_id")
    val cashRegisterId: @Contextual com.ionspin.kotlin.bignum.integer.BigInteger?,

    @SerialName(value = "cash_register_name")
    val cashRegisterName: kotlin.String?,

    @SerialName(value = "allow_top_up")
    val allowTopUp: kotlin.Boolean,

    @SerialName(value = "allow_cash_out")
    val allowCashOut: kotlin.Boolean,

    @SerialName(value = "allow_ticket_sale")
    val allowTicketSale: kotlin.Boolean,

    @SerialName(value = "enable_ssp_payment")
    val enableSspPayment: kotlin.Boolean,

    @SerialName(value = "enable_cash_payment")
    val enableCashPayment: kotlin.Boolean,

    @SerialName(value = "enable_card_payment")
    val enableCardPayment: kotlin.Boolean,

    @SerialName(value = "buttons")
    val buttons: kotlin.collections.List<TerminalButton>?,

    @SerialName(value = "secrets")
    val secrets: TerminalSecrets?,

    @SerialName(value = "active_user_id")
    val activeUserId: @Contextual com.ionspin.kotlin.bignum.integer.BigInteger?,

    @SerialName(value = "available_roles")
    val availableRoles: kotlin.collections.List<UserRole>,

    @SerialName(value = "post_payment_allowed") 
    val postPaymentAllowed: kotlin.Boolean? = null,
  
    @SerialName(value = "sumup_payment_enabled") 
    val sumupPaymentEnabled: kotlin.Boolean? = null

)

