package de.stustapay.stustapay.ec

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class TapToPaySessionIdentityTest {
    @Test
    fun sameMerchantAndEnvironmentKeepsExistingSession() {
        val identity = TapToPaySessionIdentity(environment = "live", merchantCode = "MERCHANT")

        assertFalse(
            shouldReinitializeTapToPay(
                isInitialized = true,
                currentIdentity = identity,
                requestedIdentity = identity,
            )
        )
    }

    @Test
    fun environmentChangeRequiresNewSession() {
        assertTrue(
            shouldReinitializeTapToPay(
                isInitialized = true,
                currentIdentity = TapToPaySessionIdentity("live", "MERCHANT"),
                requestedIdentity = TapToPaySessionIdentity("sandbox", "MERCHANT"),
            )
        )
    }

    @Test
    fun merchantChangeRequiresNewSession() {
        assertTrue(
            shouldReinitializeTapToPay(
                isInitialized = true,
                currentIdentity = TapToPaySessionIdentity("sandbox", "OLD"),
                requestedIdentity = TapToPaySessionIdentity("sandbox", "NEW"),
            )
        )
    }
}
