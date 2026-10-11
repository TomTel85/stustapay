package de.stustapay.stustapay.ec

import de.stustapay.stustapay.display.CustomerDisplayState
import java.math.BigDecimal
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class TapToPayDisplaySessionTest {
    @Test
    fun `payment amounts are rounded to cents half up`() {
        assertEquals(1999L, tapToPayAmountCents(BigDecimal(19.99)))
        assertEquals(-1999L, tapToPayAmountCents(BigDecimal(-19.99)))
        assertEquals(1234L, tapToPayAmountCents(BigDecimal("12.34")))
    }

    @Test
    fun `restores the captured state exactly once`() {
        val session = TapToPayDisplaySession()
        val previousState = CustomerDisplayState.ValidatingSale(
            totalPrice = 12.50,
            currentBalance = 20.00,
            newBalance = 7.50,
        )

        session.begin(previousState)

        assertEquals(previousState, session.finish())
        assertNull(session.finish())
    }

    @Test
    fun `does nothing when no payment display session is active`() {
        assertNull(TapToPayDisplaySession().finish())
    }
}
