package de.stustapay.stustapay.netsource

import android.content.Context
import dagger.hilt.android.qualifiers.ApplicationContext
import de.stustapay.api.models.CreateUserPayload
import de.stustapay.api.models.LoginPayload
import de.stustapay.api.models.UpdateUserPayload
import de.stustapay.api.models.UserTag
import de.stustapay.libssp.model.NfcTag
import de.stustapay.libssp.net.Response
import de.stustapay.stustapay.MainApplication
import de.stustapay.stustapay.model.UserCreateState
import de.stustapay.stustapay.model.UserRolesState
import de.stustapay.stustapay.model.UserState
import de.stustapay.stustapay.model.UserUpdateState
import de.stustapay.stustapay.net.TerminalApiAccessor
import javax.inject.Inject

/**
 * Remote data source for user-related operations
 * Includes network connectivity checks and better error handling
 */
class UserRemoteDataSource @Inject constructor(
    private val terminalApiAccessor: TerminalApiAccessor,
    @ApplicationContext private val context: Context
) {
    /**
     * Get the current logged-in user
     */
    suspend fun currentUser(): UserState {
        if (!checkNetworkConnectivity()) {
            return UserState.Error("No internet connection available")
        }
        
        return when (val res = terminalApiAccessor.execute {
            it.user()?.getCurrentUser()
        }) {
            is Response.OK -> {
                UserState.LoggedIn(res.data)
            }

            is Response.Error -> {
                if (res is Response.Error.BadResponse) {
                    UserState.NoLogin
                } else {
                    UserState.Error(res.msg())
                }
            }
        }
    }

    /**
     * Check if a user can login with the given tag
     */
    suspend fun checkLogin(tag: NfcTag): UserRolesState {
        if (!checkNetworkConnectivity()) {
            return UserRolesState.Error("No internet connection available")
        }
        
        return when (val res =
            terminalApiAccessor.execute { it.user()?.checkLoginUser(UserTag(tag.uid)) }) {
            is Response.OK -> {
                UserRolesState.OK(res.data.roles, res.data.userTag)
            }

            is Response.Error -> {
                UserRolesState.Error(res.msg())
            }
        }
    }

    /**
     * Login a user with the given credentials
     */
    suspend fun userLogin(loginPayload: LoginPayload): UserState {
        if (!checkNetworkConnectivity()) {
            return UserState.Error("No internet connection available")
        }
        
        return when (val res = terminalApiAccessor.execute { it.user()?.loginUser(loginPayload) }) {
            is Response.OK -> {
                UserState.LoggedIn(res.data)
            }

            is Response.Error -> {
                // If it's a network-related error, try to reset the client
                if (isNetworkError(res)) {
                    terminalApiAccessor.resetNetworkClient()
                }
                UserState.Error(res.msg())
            }
        }
    }

    /**
     * Logout the current user
     */
    suspend fun userLogout(): String? {
        if (!checkNetworkConnectivity()) {
            return "No internet connection available"
        }
        
        return when (val userLogoutResponse =
            terminalApiAccessor.execute { it.user()?.logoutUser() }) {
            is Response.OK -> {
                null
            }

            is Response.Error -> {
                userLogoutResponse.msg()
            }
        }
    }

    /**
     * Create a new user
     */
    suspend fun userCreate(newUser: CreateUserPayload): UserCreateState {
        if (!checkNetworkConnectivity()) {
            return UserCreateState.Error("No internet connection available")
        }
        
        return when (val res = terminalApiAccessor.execute { it.user()?.createUser(newUser) }) {
            is Response.OK -> {
                UserCreateState.Created
            }

            is Response.Error -> {
                UserCreateState.Error(res.msg())
            }
        }
    }

    /**
     * Update a user's roles
     */
    suspend fun userUpdate(updateUser: UpdateUserPayload): UserUpdateState {
        if (!checkNetworkConnectivity()) {
            return UserUpdateState.Error("No internet connection available")
        }
        
        return when (val res =
            terminalApiAccessor.execute { it.user()?.updateUserRoles(updateUser) }) {
            is Response.OK -> {
                UserUpdateState.Created
            }

            is Response.Error -> {
                UserUpdateState.Error(res.msg())
            }
        }
    }
    
    /**
     * Check if network connectivity is available
     */
    private fun checkNetworkConnectivity(): Boolean {
        return MainApplication.hasActiveInternetConnection(context)
    }
    
    /**
     * Check if the error is likely network-related
     */
    private fun isNetworkError(error: Response.Error): Boolean {
        val errorMsg = error.msg().lowercase()
        return errorMsg.contains("timeout") ||
               errorMsg.contains("network") ||
               errorMsg.contains("connect") ||
               errorMsg.contains("host") ||
               errorMsg.contains("socket") ||
               errorMsg.contains("route") ||
               errorMsg.contains("dns")
    }
}