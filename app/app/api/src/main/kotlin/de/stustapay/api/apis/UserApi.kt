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

package de.stustapay.api.apis

import kotlinx.serialization.Contextual

import de.stustapay.api.models.Account
import de.stustapay.api.models.CheckLoginResult
import de.stustapay.api.models.CurrentUser
import de.stustapay.api.models.GrantVoucherPayload

import de.stustapay.api.models.LoginPayload
import de.stustapay.api.models.NewFreeTicketGrant
import de.stustapay.api.models.NewUser
import de.stustapay.api.models.User
import de.stustapay.api.models.UserTag

import de.stustapay.api.infrastructure.*
import io.ktor.client.HttpClientConfig
import io.ktor.client.request.forms.formData
import io.ktor.client.engine.HttpClientEngine
import io.ktor.http.ParametersBuilder

    open class UserApi(
    baseUrl: String = ApiClient.BASE_URL,
    httpClientEngine: HttpClientEngine? = null,
    httpClientConfig: ((HttpClientConfig<*>) -> Unit)? = null,
    ) : ApiClient(
        baseUrl,
        httpClientEngine,
        httpClientConfig,
    ) {

        /**
        * Check if a user can login to the terminal and return his roles
        * 
         * @param userTag  
         * @return CheckLoginResult
        */
            @Suppress("UNCHECKED_CAST")
        open suspend fun checkLoginUser(userTag: UserTag): HttpResponse<CheckLoginResult> {

            val localVariableAuthNames = listOf<String>("OAuth2PasswordBearer")

            val localVariableBody = userTag

            val localVariableQuery = mutableMapOf<String, List<String>>()

            val localVariableHeaders = mutableMapOf<String, String>()

            val localVariableConfig = RequestConfig<kotlin.Any?>(
            RequestMethod.POST,
            "/user/check-login",
            query = localVariableQuery,
            headers = localVariableHeaders,
            requiresAuthentication = true,
            )

            return jsonRequest(
            localVariableConfig,
            localVariableBody,
            localVariableAuthNames
            ).wrap()
            }

        /**
        * Create a new user with the given roles
        * 
         * @param newUser  
         * @return User
        */
            @Suppress("UNCHECKED_CAST")
        open suspend fun createUser(newUser: NewUser): HttpResponse<User> {

            val localVariableAuthNames = listOf<String>("OAuth2PasswordBearer")

            val localVariableBody = newUser

            val localVariableQuery = mutableMapOf<String, List<String>>()

            val localVariableHeaders = mutableMapOf<String, String>()

            val localVariableConfig = RequestConfig<kotlin.Any?>(
            RequestMethod.POST,
            "/user/create-user",
            query = localVariableQuery,
            headers = localVariableHeaders,
            requiresAuthentication = true,
            )

            return jsonRequest(
            localVariableConfig,
            localVariableBody,
            localVariableAuthNames
            ).wrap()
            }

        /**
        * Get the currently logged in User
        * 
         * @return CurrentUser
        */
            @Suppress("UNCHECKED_CAST")
        open suspend fun getCurrentUser(): HttpResponse<CurrentUser> {

            val localVariableAuthNames = listOf<String>("OAuth2PasswordBearer")

            val localVariableBody = 
                    io.ktor.client.utils.EmptyContent

            val localVariableQuery = mutableMapOf<String, List<String>>()

            val localVariableHeaders = mutableMapOf<String, String>()

            val localVariableConfig = RequestConfig<kotlin.Any?>(
            RequestMethod.GET,
            "/user",
            query = localVariableQuery,
            headers = localVariableHeaders,
            requiresAuthentication = true,
            )

            return request(
            localVariableConfig,
            localVariableBody,
            localVariableAuthNames
            ).wrap()
            }

        /**
        * grant a free ticket, e.g. to a volunteer
        * 
         * @param newFreeTicketGrant  
         * @return Account
        */
            @Suppress("UNCHECKED_CAST")
        open suspend fun grantFreeTicket(newFreeTicketGrant: NewFreeTicketGrant): HttpResponse<Account> {

            val localVariableAuthNames = listOf<String>("OAuth2PasswordBearer")

            val localVariableBody = newFreeTicketGrant

            val localVariableQuery = mutableMapOf<String, List<String>>()

            val localVariableHeaders = mutableMapOf<String, String>()

            val localVariableConfig = RequestConfig<kotlin.Any?>(
            RequestMethod.POST,
            "/user/grant-free-ticket",
            query = localVariableQuery,
            headers = localVariableHeaders,
            requiresAuthentication = true,
            )

            return jsonRequest(
            localVariableConfig,
            localVariableBody,
            localVariableAuthNames
            ).wrap()
            }

        /**
        * grant vouchers to a customer
        * 
         * @param grantVoucherPayload  
         * @return Account
        */
            @Suppress("UNCHECKED_CAST")
        open suspend fun grantVouchers(grantVoucherPayload: GrantVoucherPayload): HttpResponse<Account> {

            val localVariableAuthNames = listOf<String>("OAuth2PasswordBearer")

            val localVariableBody = grantVoucherPayload

            val localVariableQuery = mutableMapOf<String, List<String>>()

            val localVariableHeaders = mutableMapOf<String, String>()

            val localVariableConfig = RequestConfig<kotlin.Any?>(
            RequestMethod.POST,
            "/user/grant-vouchers",
            query = localVariableQuery,
            headers = localVariableHeaders,
            requiresAuthentication = true,
            )

            return jsonRequest(
            localVariableConfig,
            localVariableBody,
            localVariableAuthNames
            ).wrap()
            }

        /**
        * Login User
        * 
         * @param loginPayload  
         * @return CurrentUser
        */
            @Suppress("UNCHECKED_CAST")
        open suspend fun loginUser(loginPayload: LoginPayload): HttpResponse<CurrentUser> {

            val localVariableAuthNames = listOf<String>("OAuth2PasswordBearer")

            val localVariableBody = loginPayload

            val localVariableQuery = mutableMapOf<String, List<String>>()

            val localVariableHeaders = mutableMapOf<String, String>()

            val localVariableConfig = RequestConfig<kotlin.Any?>(
            RequestMethod.POST,
            "/user/login",
            query = localVariableQuery,
            headers = localVariableHeaders,
            requiresAuthentication = true,
            )

            return jsonRequest(
            localVariableConfig,
            localVariableBody,
            localVariableAuthNames
            ).wrap()
            }

        /**
        * Logout the current user
        * 
         * @return void
        */
        open suspend fun logoutUser(): HttpResponse<Unit> {

            val localVariableAuthNames = listOf<String>("OAuth2PasswordBearer")

            val localVariableBody = 
                    io.ktor.client.utils.EmptyContent

            val localVariableQuery = mutableMapOf<String, List<String>>()

            val localVariableHeaders = mutableMapOf<String, String>()

            val localVariableConfig = RequestConfig<kotlin.Any?>(
            RequestMethod.POST,
            "/user/logout",
            query = localVariableQuery,
            headers = localVariableHeaders,
            requiresAuthentication = true,
            )

            return request(
            localVariableConfig,
            localVariableBody,
            localVariableAuthNames
            ).wrap()
            }

        }
