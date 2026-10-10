package de.stustapay.stustapay.ui.payinout.postpayment

import de.stustapay.stustapay.repository.ECPaymentResult
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class PostPaymentPendingPaymentTest {
    @Test
    fun `definite failure cancels the pending top up`() {
        assertTrue(
            shouldCancelPendingCardPayment(
                ECPaymentResult.Failure("Card declined")
            )
        )
    }

    @Test
    fun `indeterminate failure keeps the pending top up for reconciliation`() {
        assertFalse(
            shouldCancelPendingCardPayment(
                ECPaymentResult.Failure(
                    msg = "Payment status unknown",
                    mayHaveCreatedCharge = true,
                )
            )
        )
    }
}
