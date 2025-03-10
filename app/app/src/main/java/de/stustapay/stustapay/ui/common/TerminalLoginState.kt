package de.stustapay.stustapay.ui.common


import de.stustapay.api.models.CurrentUser
import de.stustapay.api.models.Privilege
import de.stustapay.api.models.TerminalConfig
import de.stustapay.stustapay.model.UserState
import de.stustapay.stustapay.repository.TerminalConfigState


class TerminalLoginState(
    private val user: UserState = UserState.NoLogin,
    private val terminal: TerminalConfigState = TerminalConfigState.NoConfig
) {
    data class TillName(val title: String, val subtitle: String? = null)

    fun title(): TillName {
        return if (terminal is TerminalConfigState.Success) {
            TillName(terminal.config.till?.name.orEmpty(), terminal.config.till?.profileName)
        } else {
            TillName("TeamFestlichPay")
        }
    }

    fun isTerminalReady(): Boolean {
        return terminal is TerminalConfigState.Success
    }

    fun checkAccess(access: (CurrentUser, TerminalConfig) -> Boolean): Boolean {
        return if (user is UserState.LoggedIn && terminal is TerminalConfigState.Success) {
            access(user.user, terminal.config)
        } else {
            false
        }
    }

    fun hasConfig(): Boolean {
        return terminal is TerminalConfigState.Success
    }

    fun canHandleCash(): Boolean {
        if (terminal !is TerminalConfigState.Success) {
            return false;
        }
        return terminal.config.till?.cashRegisterId != null;
    }
    
    /**
     * Check if the user has only the can_topup privilege but not the can_book_orders privilege.
     * Such users should not see the Cash button in the topup view.
     */
    fun hasOnlyTopUpPrivilege(): Boolean {
        if (user !is UserState.LoggedIn) {
            return false
        }
        
        return user.user.privileges.contains(Privilege.canTopup) && 
               !user.user.privileges.contains(Privilege.canBookOrders)
    }
}