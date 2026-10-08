package de.stustapay.stustapay.net

import de.stustapay.libssp.net.Response
import de.stustapay.stustapay.offline.isOfflineTransportFailure
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.async
import kotlinx.coroutines.awaitCancellation
import kotlinx.coroutines.delay
import kotlinx.coroutines.runBlocking
import org.junit.Assert.*
import org.junit.Test

class OfflineRecoveryDeadlineTest {
    @Test fun `prepared timeout cancels outstanding request and allows transport fallback`() = runBlocking {
        var cancelled = false
        val response = withOfflineRecoveryDeadline<String>(true, timeoutMillis = 25) {
            try { awaitCancellation() } finally { cancelled = true }
        }
        assertTrue(cancelled)
        assertTrue(response is Response.Error.Request)
        assertTrue(isOfflineTransportFailure(response as Response.Error.Request))
    }

    @Test fun `without preparation existing request timing is unchanged`() = runBlocking {
        val response = withOfflineRecoveryDeadline(false, timeoutMillis = 1) {
            delay(25)
            Response.OK("online")
        }
        assertEquals("online", (response as Response.OK).data)
    }

    @Test fun `business denial remains a business denial`() = runBlocking {
        val denial = Response.Error.Access("operator denied")
        val response = withOfflineRecoveryDeadline<String>(true) { denial }
        assertSame(denial, response)
    }

    @Test fun `external cancellation does not become an offline sale`() = runBlocking {
        val task = async { withOfflineRecoveryDeadline<String>(true) { awaitCancellation() } }
        task.cancel()
        try { task.await(); fail("Cancellation must propagate") }
        catch (_: CancellationException) { }
    }
}
