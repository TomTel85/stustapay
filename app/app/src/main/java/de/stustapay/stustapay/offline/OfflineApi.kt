package de.stustapay.stustapay.offline

import de.stustapay.api.infrastructure.*
import io.ktor.client.HttpClientConfig
import io.ktor.client.engine.HttpClientEngine

/** Handwritten adapter using the same authenticated transport as the generated API. */
class OfflineApi(baseUrl: String, engine: HttpClientEngine, configure: (HttpClientConfig<*>) -> Unit) :
    ApiClient(baseUrl, engine, configure) {
    suspend fun prepare(): HttpResponse<PreparedOfflineSnapshot> = jsonRequest(
        RequestConfig<Any?>(RequestMethod.POST, "/order/offline/prepare", requiresAuthentication = true),
        null, listOf("OAuth2PasswordBearer")
    ).wrap()
    suspend fun import(bookings: OfflineImport): HttpResponse<OfflineResults> = jsonRequest(
        RequestConfig<Any?>(RequestMethod.POST, "/order/offline/import", requiresAuthentication = true),
        bookings, listOf("OAuth2PasswordBearer")
    ).wrap()
    suspend fun status(uuid: String): HttpResponse<OfflineResult> = jsonRequest(
        RequestConfig<Any?>(RequestMethod.GET, "/order/offline/status/$uuid", requiresAuthentication = true),
        null, listOf("OAuth2PasswordBearer")
    ).wrap()
}
