package de.stustapay.stustapay.ec

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class SumUpCheckoutFailureTest {
    @Test
    fun `unknown transaction status keeps a possible charge pending for reconciliation`() {
        val result = sumUpCheckoutFailure(15, "Timed out")
        assertTrue(result.mayHaveCreatedCharge)
        assertTrue(result.msg.contains("reconciled"))
    }

    @Test
    fun `duplicate transaction keeps a possible charge pending for reconciliation`() {
        assertTrue(sumUpCheckoutFailure(9, "Duplicate").mayHaveCreatedCharge)
    }

    @Test
    fun `unrecognized SDK response cannot cancel a possible charge`() {
        assertTrue(sumUpCheckoutFailure(99, null).mayHaveCreatedCharge)
        assertTrue(sumUpCheckoutFailure(0, "Missing result").mayHaveCreatedCharge)
    }

    @Test
    fun `definitive failures allow the pending payment to be cancelled`() {
        for (code in listOf(2, 4, 5, 6, 7, 8, 10, 12, 13, 14)) {
            assertFalse("Result code $code", sumUpCheckoutFailure(code, "Failure").mayHaveCreatedCharge)
        }
    }
}
