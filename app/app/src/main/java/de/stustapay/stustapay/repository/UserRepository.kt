package de.stustapay.stustapay.repository

import com.ionspin.kotlin.bignum.integer.BigInteger
import com.ionspin.kotlin.bignum.integer.toBigInteger
import de.stustapay.api.models.CreateUserPayload
import de.stustapay.api.models.LoginPayload
import de.stustapay.api.models.UpdateUserPayload
import de.stustapay.api.models.UserTag
import de.stustapay.libssp.model.NfcTag
import de.stustapay.stustapay.model.UserCreateState
import de.stustapay.stustapay.model.UserRolesState
import de.stustapay.stustapay.model.UserState
import de.stustapay.stustapay.model.UserUpdateState
import de.stustapay.stustapay.netsource.UserRemoteDataSource
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class UserRepository @Inject constructor(
    private val userRemoteDataSource: UserRemoteDataSource,
    private val offlineSales: de.stustapay.stustapay.offline.OfflineSalesRepository,
    private val terminalConfigRepository: TerminalConfigRepository
) {
    private var _userState = MutableStateFlow<UserState>(UserState.Error("loading..."))
    var userState = _userState.asStateFlow()

    private var _userRolesState = MutableStateFlow<UserRolesState>(UserRolesState.Unknown)
    var userRoles = _userRolesState.asStateFlow()

    var status = MutableStateFlow<String?>(null)

    suspend fun fetchLogin() {
        val result = userRemoteDataSource.currentUser(offlinePrepared = offlineSales.restoredConfig() != null)
        if (result is UserState.LoggedIn) {
            _userState.value = result
            offlineSales.rememberUser(result.user)
        } else {
            val restored = if (userRemoteDataSource.currentUserTransportFailure) offlineSales.restoredUser() else null
            if (!userRemoteDataSource.currentUserTransportFailure) offlineSales.revoke()
            _userState.value = restored?.let { UserState.LoggedIn(it) } ?: result
            offlineSales.start()
        }
    }

    suspend fun checkLogin(userTag: NfcTag) {
        _userRolesState.update { UserRolesState.Unknown }
        when (val checkResult = userRemoteDataSource.checkLogin(userTag)) {
            is UserRolesState.Error -> {
                status.update { checkResult.msg }
            }

            is UserRolesState.OK -> {
                status.update { null }
                _userRolesState.update { checkResult }
            }

            is UserRolesState.Unknown -> {
                // checkLogin never returns this anyway
                status.update { "roles unknown" }
            }
        }
    }

    suspend fun login(userTag: NfcTag, roleID: BigInteger) {
        when (val loginResult =
            userRemoteDataSource.userLogin(LoginPayload(UserTag(userTag.uid), roleID))) {
            is UserState.Error -> {
                status.update { loginResult.msg }
            }

            is UserState.LoggedIn, is UserState.NoLogin -> {
                status.update { null }
                _userState.update { loginResult }
                terminalConfigRepository.fetchConfig(keepTrying = false)
                if (loginResult is UserState.LoggedIn) offlineSales.rememberUser(loginResult.user)
            }
        }
    }

    suspend fun logout() {
        offlineSales.revoke()
        _userState.value = UserState.NoLogin
        val result = userRemoteDataSource.userLogout()
        if (result != null) {
            status.emit(result)
        } else {
            status.update { "Logged out." }
            _userState.update { UserState.NoLogin }
        }
    }

    suspend fun create(
        login: String,
        displayName: String,
        userTag: NfcTag,
        roles: List<BigInteger>,
        description: String
    ): UserCreateState {
        return userRemoteDataSource.userCreate(
            CreateUserPayload(
                login = login,
                displayName = displayName,
                userTagUid = userTag.uid,
                userTagPin = userTag.pin,
                description = description,
                roleIds = roles
            )
        )
    }

    suspend fun update(userTag: NfcTag, roles: List<BigInteger>): UserUpdateState {
        return userRemoteDataSource.userUpdate(
            UpdateUserPayload(
                userTagUid = userTag.uid, roleIds = roles
            )
        )
    }
}
