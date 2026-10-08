package de.stustapay.stustapay.ui.root

import de.stustapay.stustapay.offline.OfflineStatus
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class StartpageOfflinePolicyTest {
    @Test
    fun `online sale remains available without offline preparation`() {
        assertTrue(isOperatorMenuRouteEnabled(RootNavDests.sale, OfflineStatus()))
    }

    @Test
    fun `offline sale requires usable preparation`() {
        assertTrue(
            isOperatorMenuRouteEnabled(
                RootNavDests.sale,
                OfflineStatus(offlineMode = true, preparationUsable = true),
            ),
        )
        assertFalse(
            isOperatorMenuRouteEnabled(
                RootNavDests.sale,
                OfflineStatus(offlineMode = true, preparationUsable = false),
            ),
        )
    }

    @Test
    fun `offline mode disables server routes but keeps local actions available`() {
        val offline = OfflineStatus(offlineMode = true, preparationUsable = true)

        assertFalse(isOperatorMenuRouteEnabled(RootNavDests.topup, offline))
        assertFalse(isOperatorMenuRouteEnabled(RootNavDests.history, offline))
        assertFalse(isOperatorMenuRouteEnabled(RootNavDests.status, offline))
        assertFalse(isOperatorMenuRouteEnabled(RootNavDests.entry, offline))
        assertFalse(isOperatorMenuRouteEnabled(RootNavDests.user, offline))
        assertFalse(isOperatorMenuRouteEnabled(RootNavDests.postpayment, offline))
        assertFalse(isOperatorMenuRouteEnabled(RootNavDests.ticket, offline))
        assertFalse(isOperatorMenuRouteEnabled(RootNavDests.rewards, offline))
        assertFalse(isOperatorMenuRouteEnabled(RootNavDests.cashier, offline))
        assertFalse(isOperatorMenuRouteEnabled(RootNavDests.stats, offline))
        assertFalse(isOperatorMenuRouteEnabled(RootNavDests.vault, offline))
        assertFalse(isOperatorMenuRouteEnabled(RootNavDests.swap, offline))
        assertTrue(isOperatorMenuRouteEnabled(RootNavDests.settings, offline))
        assertTrue(isOperatorMenuRouteEnabled(RootNavDests.development, offline))
        assertTrue(isOperatorMenuRouteEnabled(null, offline)) // Local restart action.
    }
}
