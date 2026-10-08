package de.stustapay.stustapay.net

import de.stustapay.libssp.net.Response
import kotlinx.coroutines.withTimeoutOrNull
import java.net.SocketTimeoutException

internal const val OFFLINE_RECOVERY_TIMEOUT_MILLIS = 3_000L

/** Bound transport retries only when a valid local preparation can take over. */
internal suspend fun <T : Any> withOfflineRecoveryDeadline(
    prepared: Boolean,
    timeoutMillis: Long = OFFLINE_RECOVERY_TIMEOUT_MILLIS,
    request: suspend () -> Response<T>,
): Response<T> {
    if (!prepared) return request()
    return withTimeoutOrNull(timeoutMillis) { request() }
        ?: Response.Error.Request(null, SocketTimeoutException("Offline recovery: server did not respond in time"))
}
