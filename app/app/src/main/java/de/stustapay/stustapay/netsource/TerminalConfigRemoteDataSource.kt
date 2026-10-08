package de.stustapay.stustapay.netsource

import de.stustapay.api.models.TerminalConfig
import de.stustapay.libssp.net.Response
import de.stustapay.stustapay.net.TerminalApiAccessor
import javax.inject.Inject

class TerminalConfigRemoteDataSource @Inject constructor(
    private val terminalApiAccessor: TerminalApiAccessor
){
    suspend fun getTerminalConfig(offlinePrepared: Boolean = false): Response<TerminalConfig> {
        return de.stustapay.stustapay.net.withOfflineRecoveryDeadline(offlinePrepared) {
            terminalApiAccessor.execute { it.base()?.config() }
        }
    }
}
