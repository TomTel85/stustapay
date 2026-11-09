package de.stustapay.stustapay.repository

import de.stustapay.stustapay.ec.SumUpState
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class ECPaymentRepositoryTest {
    private val success = SumUpState.Success("Paid", "sumup-code", null)

    @Test
    fun `matching payment may be booked`() {
        assertEquals(
            ECPaymentResult.Success(success),
            verifiedCardPaymentResult(success, "pending-payment", "pending-payment"),
        )
    }

    @Test
    fun `success from another payment must not book or cancel the pending order`() {
        assertRequiresReconciliation("pending-payment", "other-payment")
    }

    @Test
    fun `missing payment identity must not book or cancel the pending order`() {
        assertRequiresReconciliation("pending-payment", null)
        assertRequiresReconciliation("pending-payment", "")
    }

    @Test
    fun `empty pending identity cannot authorize booking`() {
        assertRequiresReconciliation("", "")
        assertRequiresReconciliation(" ", " ")
    }

    @Test
    fun `only definitely unlaunched attempts may be discarded on restart`() {
        assertEquals(false, pendingPaymentMayHaveLaunched(true, false))
        assertEquals(true, pendingPaymentMayHaveLaunched(true, true))
        assertEquals(true, pendingPaymentMayHaveLaunched(true, null))
        assertEquals(false, pendingPaymentMayHaveLaunched(false, null))
        assertEquals(true, shouldRetryWithNewPaymentId("same", "same", false))
        assertEquals(false, shouldRetryWithNewPaymentId("same", "same", true))
        assertEquals(false, shouldRetryWithNewPaymentId("same", "other", false))
        assertEquals(true, wasPaymentReleased("released", "released"))
        assertEquals(false, wasPaymentReleased("released", "other"))
    }

    private fun assertRequiresReconciliation(expectedId: String, actualId: String?) {
        val result = verifiedCardPaymentResult(success, expectedId, actualId)
        assertTrue(result is ECPaymentResult.Failure)
        assertTrue((result as ECPaymentResult.Failure).mayHaveCreatedCharge)
    }
}
