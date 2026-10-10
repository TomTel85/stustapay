package de.stustapay.stustapay.repository

import de.stustapay.stustapay.ec.SumUpState
import de.stustapay.stustapay.ec.isTapToPayEnabledForTill
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class TapToPayResolutionTest {
    @Test
    fun `tap to pay success is bookable without reader transaction info`() {
        // The Tap-to-Pay gateway returns a transaction code, not the reader SDK's TransactionInfo.
        val success = SumUpState.Success("Paid", "tap-to-pay-code", null)

        assertEquals(
            TapToPayResolution.Complete(ECPaymentResult.Success(success)),
            resolveTapToPayState(success),
        )
    }

    @Test
    fun `tap to pay requires the active till profile to be enabled and available`() {
        assertTrue(isTapToPayEnabledForTill(tapToPayEnabled = true, tapToPayAvailable = true))
        assertFalse(isTapToPayEnabledForTill(tapToPayEnabled = false, tapToPayAvailable = true))
        assertFalse(isTapToPayEnabledForTill(tapToPayEnabled = true, tapToPayAvailable = false))
        assertFalse(isTapToPayEnabledForTill(tapToPayEnabled = null, tapToPayAvailable = true))
    }

    @Test
    fun `pre-start error may fall back to the card reader`() {
        val resolution = resolveTapToPayState(
            SumUpState.Error(
                msg = "SDK initialization failed",
                readerFallbackAllowed = true,
            )
        )

        assertEquals(TapToPayResolution.FallbackToReader, resolution)
    }

    @Test
    fun `unknown result never falls back and preserves pending charge`() {
        val resolution = resolveTapToPayState(
            SumUpState.Error(
                msg = "Transaction result unknown",
                mayHaveCreatedCharge = true,
                readerFallbackAllowed = true,
            )
        )

        assertTrue(resolution is TapToPayResolution.Complete)
        val failure = (resolution as TapToPayResolution.Complete).result as ECPaymentResult.Failure
        assertTrue(failure.mayHaveCreatedCharge)
        assertTrue(failure.msg.contains("unknown"))
    }

    @Test
    fun `post-start failure does not automatically fall back`() {
        val resolution = resolveTapToPayState(SumUpState.Failed("Card declined"))

        assertTrue(resolution is TapToPayResolution.Complete)
        val failure = (resolution as TapToPayResolution.Complete).result as ECPaymentResult.Failure
        assertFalse(failure.mayHaveCreatedCharge)
        assertTrue(failure.msg.contains("Card declined"))
    }

    @Test
    fun `cancellation is represented without parsing the message`() {
        val resolution = resolveTapToPayState(
            SumUpState.Failed(
                msg = "Localized or SDK-specific text",
                canceled = true,
            )
        )

        val failure = (resolution as TapToPayResolution.Complete).result as ECPaymentResult.Failure
        assertEquals("Payment canceled by user", failure.msg)
        assertFalse(failure.mayHaveCreatedCharge)
    }
}
