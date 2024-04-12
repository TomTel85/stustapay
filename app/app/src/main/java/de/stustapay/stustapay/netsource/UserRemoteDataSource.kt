package de.stustapay.stustapay.netsource


import de.stustapay.stustapay.net.Response
import de.stustapay.stustapay.net.TerminalApiAccessor
import de.stustapay.api.models.LoginPayload
import de.stustapay.api.models.NewUser
import de.stustapay.api.models.UserTag
import de.stustapay.stustapay.model.UserCreateState
import de.stustapay.stustapay.model.UserRolesState
import de.stustapay.stustapay.model.UserState
import de.stustapay.stustapay.model.UserUpdateState
import javax.inject.Inject

class UserRemoteDataSource @Inject constructor(
    private val terminalApiAccessor: TerminalApiAccessor
) {
    suspend fun currentUser(): UserState {
        return when (val res = terminalApiAccessor.execute { it.user().getCurrentUser() }) {
            is Response.OK -> {
                UserState.LoggedIn(res.data)
            }

            is Response.Error -> {
                UserState.Error(res.msg())
            }
        }
    }

    /**
     * Login a user by token and desired role.
     */
    suspend fun checkLogin(tag: UserTag): UserRolesState {
        return when (val res = terminalApiAccessor.execute { it.user().checkLoginUser(tag) }) {
            is Response.OK -> {
                UserRolesState.OK(res.data.roles, res.data.userTag)
            }

            is Response.Error -> {
                UserRolesState.Error(res.msg())
            }
        }
    }

    /**
     * Login a user by token and desired role.
     */
    suspend fun userLogin(loginPayload: LoginPayload): UserState {
        return when (val res = terminalApiAccessor.execute { it.user().loginUser(loginPayload) }) {
            is Response.OK -> {
                UserState.LoggedIn(res.data)
            }

            is Response.Error -> {
                UserState.Error(res.msg())
            }
        }
    }

    /**
     * Logout the current user.
     */
    suspend fun userLogout(): String? {
        return when (val userLogoutResponse =
            terminalApiAccessor.execute { it.user().logoutUser() }) {
            is Response.OK -> {
                null
            }

            is Response.Error -> {
                userLogoutResponse.msg()
            }
        }
    }

    /**
     * Create a new user of any type.
     */
    suspend fun userCreate(newUser: NewUser): UserCreateState {
        return when (val res = terminalApiAccessor.execute { it.user().createUser(newUser) }) {
            is Response.OK -> {
                UserCreateState.Created
            }

            is Response.Error -> {
                UserCreateState.Error(res.msg())
            }
        }
    }

    /**
     * Change a user's roles.
     */
    suspend fun userUpdate(): UserUpdateState {
        return UserUpdateState.Error("not implemented")
        /*return when (val res =
            terminalApiAccessor.execute { it.user().createFinanzorga(updateUser) }) {
            is Response.OK -> {
                UserUpdateState.Created
            }

            is Response.Error -> {
                UserUpdateState.Error(res.msg())
            }
        }*/
    }
}