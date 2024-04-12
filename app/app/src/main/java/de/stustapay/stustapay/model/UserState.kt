package de.stustapay.stustapay.model

import de.stustapay.api.models.CurrentUser
import de.stustapay.api.models.UserRole
import de.stustapay.api.models.UserTag

sealed interface UserRolesState {
    data class OK(
        var roles: List<UserRole>,
        var tag: UserTag,
    ) : UserRolesState

    object Unknown : UserRolesState

    data class Error(
        var msg: String,
    ) : UserRolesState
}

sealed interface UserState {
    data class LoggedIn(
        var user: CurrentUser
    ) : UserState

    object NoLogin : UserState

    data class Error(
        var msg: String,
    ) : UserState
}

sealed interface UserCreateState {
    object Created : UserCreateState

    data class Error(
        var msg: String,
    ) : UserCreateState
}

sealed interface UserUpdateState {
    object Created : UserUpdateState

    data class Error(
        var msg: String,
    ) : UserUpdateState
}