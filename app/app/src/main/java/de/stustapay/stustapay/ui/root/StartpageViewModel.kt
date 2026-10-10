package de.stustapay.stustapay.ui.root

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import dagger.hilt.android.lifecycle.HiltViewModel
import de.stustapay.stustapay.model.UserState
import de.stustapay.stustapay.repository.TerminalConfigState
import de.stustapay.stustapay.repository.TerminalConfigRepository
import de.stustapay.stustapay.repository.UserRepository
import de.stustapay.stustapay.ui.common.TerminalLoginState
import de.stustapay.libssp.util.Result
import de.stustapay.libssp.util.asResult
import de.stustapay.stustapay.repository.InfallibleRepository
import de.stustapay.stustapay.offline.OfflineSalesRepository
import de.stustapay.stustapay.offline.OfflineStatus
import kotlinx.coroutines.flow.*
import javax.inject.Inject


@HiltViewModel
class StartpageViewModel @Inject constructor(
    userRepository: UserRepository,
    terminalConfigRepository: TerminalConfigRepository,
    private val offlineSalesRepository: OfflineSalesRepository,
) : ViewModel() {

    fun synchronizeAndPrepare() = offlineSalesRepository.requestSynchronization()
    fun setJournalPage(page: Int) = offlineSalesRepository.setJournalPage(page)

    val configLoading = terminalConfigRepository.fetching.stateIn(
        scope = viewModelScope,
        started = SharingStarted.WhileSubscribed(5_000),
        initialValue = false,
    )

    val uiState = combine(
        userRepository.userState,
        terminalConfigRepository.terminalConfigState
    ) { user, terminal ->
        TerminalLoginState(user, terminal)
    }.stateIn(
        scope = viewModelScope,
        started = SharingStarted.WhileSubscribed(5_000),
        initialValue = TerminalLoginState(),
    )

    val offlineStatus = combine(offlineSalesRepository.status, terminalConfigRepository.terminalConfigState) { status, configState ->
        val refreshTransportFailed = (configState as? TerminalConfigState.Success)?.refreshTransportError == true
        status.copy(offlineMode = status.offlineMode || refreshTransportFailed)
    }.stateIn(
        scope = viewModelScope,
        started = SharingStarted.WhileSubscribed(5_000),
        initialValue = OfflineStatus(),
    )

    val terminalStatusMessage = combine(terminalConfigRepository.terminalConfigState, offlineStatus) { state, status ->
        terminalConfigStatusMessage(state, status.offlineMode)
    }.stateIn(
        scope = viewModelScope,
        started = SharingStarted.WhileSubscribed(5_000),
        initialValue = null,
    )
}

internal fun terminalConfigStatusMessage(state: TerminalConfigState, offlineMode: Boolean = false): String? {
    return when (state) {
        is TerminalConfigState.NoConfig -> null
        is TerminalConfigState.Error -> "Configuration error: ${state.message}"
        is TerminalConfigState.Success -> {
            val refreshError = state.refreshErrorMessage?.takeUnless { offlineMode && state.refreshTransportError }
            refreshError?.let { "Configuration refresh failed: $it" }
                ?: state.config.testModeMessage.takeIf { state.config.testMode }
        }
    }
}
