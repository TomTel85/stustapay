package de.stustapay.stustapay.ui.root

import com.ionspin.kotlin.bignum.integer.toBigInteger
import de.stustapay.api.models.AppDisplayMode
import de.stustapay.api.models.TerminalConfig
import de.stustapay.api.models.TerminalMode
import de.stustapay.stustapay.model.UserState
import de.stustapay.stustapay.repository.TerminalConfigState
import de.stustapay.stustapay.ui.common.TerminalLoginState
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class TerminalConfigStateUiTest {
    @Test
    fun `stale success shows startpage warning while keeping terminal ready`() {
        val state = TerminalConfigState.Success(
            config = terminalConfig(),
            refreshErrorMessage = "backend timeout",
        )

        assertEquals(
            "Configuration refresh failed: backend timeout",
            terminalConfigStatusMessage(state),
        )
        assertTrue(TerminalLoginState(user = UserState.NoLogin, terminal = state).hasConfig())
    }

    @Test
    fun `stale success shows border warning instead of clearing config`() {
        val state = TerminalConfigState.Success(
            config = terminalConfig(),
            refreshErrorMessage = "backend timeout",
        )

        assertEquals(
            BorderState.Border("config refresh failed: backend timeout"),
            terminalConfigBorderState(state),
        )
    }

    @Test
    fun `offline transport refresh failure is hidden only in offline mode`() {
        val state = TerminalConfigState.Success(
            config = terminalConfig(),
            refreshErrorMessage = "request error: Network is unreachable",
            refreshTransportError = true,
        )

        assertEquals(
            "Configuration refresh failed: request error: Network is unreachable",
            terminalConfigStatusMessage(state, offlineMode = false),
        )
        assertEquals(null, terminalConfigStatusMessage(state, offlineMode = true))
    }

    @Test
    fun `offline transport failure suppression preserves test mode warning`() {
        val state = TerminalConfigState.Success(
            config = terminalConfig().copy(testMode = true, testModeMessage = "Test mode enabled"),
            refreshErrorMessage = "request error: Network is unreachable",
            refreshTransportError = true,
        )

        assertEquals("Test mode enabled", terminalConfigStatusMessage(state, offlineMode = true))
    }

    @Test
    fun `business refresh failure remains visible during offline mode`() {
        val state = TerminalConfigState.Success(
            config = terminalConfig(),
            refreshErrorMessage = "terminal config missing user tag secret",
            refreshTransportError = false,
        )

        assertEquals(
            "Configuration refresh failed: terminal config missing user tag secret",
            terminalConfigStatusMessage(state, offlineMode = true),
        )
    }

    @Test
    fun `configuration error remains visible during offline mode`() {
        assertEquals(
            "Configuration error: terminal config missing user tag secret",
            terminalConfigStatusMessage(TerminalConfigState.Error("terminal config missing user tag secret"), offlineMode = true),
        )
    }

    private fun terminalConfig(): TerminalConfig {
        return TerminalConfig(
            id = 1.toBigInteger(),
            name = "Test Terminal",
            description = null,
            mode = TerminalMode.till,
            entryArea = null,
            selfService = false,
            appDisplayMode = AppDisplayMode.day,
            eventName = "Test Event",
            activeUserId = null,
            availableRoles = emptyList(),
            userPrivileges = null,
            secrets = null,
            till = null,
            testMode = false,
            testModeMessage = "",
        )
    }
}
