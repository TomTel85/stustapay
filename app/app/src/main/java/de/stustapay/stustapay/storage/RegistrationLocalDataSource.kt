package de.stustapay.stustapay.storage

import androidx.datastore.core.DataStore
import de.stustapay.stustapay.model.RegistrationState
import kotlinx.coroutines.flow.Flow
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class RegistrationLocalDataSource @Inject constructor(
    private val regStateStore: DataStore<RegistrationState>
) {
    val registrationState: Flow<RegistrationState> = regStateStore.data

    suspend fun setState(registrationState: RegistrationState) {
        regStateStore.updateData { registrationState }
    }

    suspend fun setLogoutPending(token: String, apiUrl: String, pending: Boolean): Boolean =
        regStateStore.updateData { state ->
            if (state is RegistrationState.Registered && state.token == token && state.apiUrl == apiUrl) {
                state.copy(logoutPending = pending)
            } else {
                state
            }
        }.let { state ->
            state is RegistrationState.Registered && state.token == token && state.apiUrl == apiUrl &&
                state.logoutPending == pending
        }
}
