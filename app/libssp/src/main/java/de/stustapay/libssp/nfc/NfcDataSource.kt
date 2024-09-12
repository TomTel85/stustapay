package de.stustapay.libssp.nfc

import android.util.Log
import de.stustapay.libssp.model.NfcScanRequest
import de.stustapay.libssp.model.NfcScanResult
import de.stustapay.libssp.util.waitFor
import javax.inject.Inject
import javax.inject.Singleton
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.*

sealed interface NfcScanRequestState {
    data class Active(val req: NfcScanRequest) : NfcScanRequestState
    object None : NfcScanRequestState
}

sealed interface NfcScanResultState {
    data class Done(val res: NfcScanResult) : NfcScanResultState
    object None : NfcScanResultState
}

@Singleton
class NfcDataSource @Inject constructor() {
    private val scanResult = MutableStateFlow<NfcScanResultState>(NfcScanResultState.None)
    private val scanRequest = MutableStateFlow<NfcScanRequestState>(NfcScanRequestState.None)

    suspend fun scan(req: NfcScanRequest): NfcScanResult {
        Log.i("TeamFestlichPay", "nfc scan requested")
        try {
            scanResult.update { NfcScanResultState.None }
            scanRequest.update { NfcScanRequestState.Active(req) }
            val res = scanResult.waitFor { it is NfcScanResultState.Done }
            return (res as NfcScanResultState.Done).res
        } catch (e: CancellationException) {
            scanRequest.update { NfcScanRequestState.None }
            throw e
        }
    }

    fun getScanRequest(): NfcScanRequest? {
        Log.i("TeamFestlichPay", "nfc scan fetching...")
        val req = scanRequest.value
        return if (req is NfcScanRequestState.Active) {
            scanRequest.update { NfcScanRequestState.None }
            req.req
        } else {
            null
        }
    }

    fun setScanResult(res: NfcScanResult) {
        Log.i("TeamFestlichPay", "nfc scan result: $res")
        scanRequest.update { NfcScanRequestState.None }
        scanResult.update { NfcScanResultState.Done(res) }
    }
}