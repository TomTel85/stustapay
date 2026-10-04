package de.stustapay.stustapay.ui.user

import com.ionspin.kotlin.bignum.integer.toBigInteger
import de.stustapay.api.models.CurrentUser
import de.stustapay.api.models.Privilege
import de.stustapay.stustapay.model.UserState
import de.stustapay.stustapay.ui.common.TerminalLoginState
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.flowOf
import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class DeviceUserUiStateTest {
    private fun user(device: Boolean) = CurrentUser(
        id = 1.toBigInteger(), nodeId = 1.toBigInteger(), login = "internal-device-login",
        displayName = "Gerät: Theke 1", activeRoleName = "Verkauf",
        privileges = listOf(Privilege.terminal_login), isDeviceIdentity = device,
    )

    @Test
    fun deviceIdentityShowsDeviceNameAndHidesPersonalActions() = runBlocking {
        val state = userUiState(flowOf(TerminalLoginState(user = UserState.LoggedIn(user(true)))))
            .first { it is UserUIState.LoggedIn } as UserUIState.LoggedIn
        assertEquals("Gerät: Theke 1", state.username)
        assertEquals("Verkauf", state.activeRole)
        assertFalse(state.showLoginUser)
        assertFalse(state.showLogout)
    }

    @Test
    fun personalUserKeepsLoginAndLogoutActions() = runBlocking {
        val state = userUiState(flowOf(TerminalLoginState(user = UserState.LoggedIn(user(false)))))
            .first { it is UserUIState.LoggedIn } as UserUIState.LoggedIn
        assertEquals("internal-device-login", state.username)
        assertTrue(state.showLoginUser)
        assertTrue(state.showLogout)
    }
}
