package de.stustapay.stustapay.ui.payinout.postpayment



import androidx.compose.foundation.layout.padding
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import de.stustapay.stustapay.ui.common.pay.NoCashRegisterWarning
import kotlinx.coroutines.launch

@Composable
fun PostPaymentView(
    leaveView: () -> Unit = {},
    viewModel: PostPaymentViewModel = hiltViewModel(),
) {


    val status by viewModel.status.collectAsStateWithLifecycle()
    val payOutState by viewModel.payOutState.collectAsStateWithLifecycle()
    val config by viewModel.terminalLoginState.collectAsStateWithLifecycle()
    val scope = rememberCoroutineScope()


    if (!config.canHandleCash()) {
        NoCashRegisterWarning(modifier = Modifier.padding(20.dp), bigStyle = true)
        return
    }

    val checkedPayOut = payOutState.getCheckedPayout()
    if (checkedPayOut == null) {
        PostPaymentScan(
            onScan = { tag ->
                scope.launch {
                    viewModel.tagScanned(tag)
                }
            },
            status = status,
            leaveView = leaveView,
        )
    } else {
        PostPaymentSelection(
            leaveView = leaveView,
            viewModel = viewModel,
            payout = checkedPayOut,
            onClear = {
                scope.launch {
                    viewModel.clearDraft()
                }
            },
        )
    }
}

