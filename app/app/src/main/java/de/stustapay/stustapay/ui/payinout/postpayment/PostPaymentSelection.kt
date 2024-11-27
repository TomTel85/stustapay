package de.stustapay.stustapay.ui.payinout.postpayment

import android.app.Activity
import androidx.activity.compose.BackHandler
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.MaterialTheme
import androidx.compose.material.Scaffold
import androidx.compose.material.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import de.stustapay.stustapay.R
import de.stustapay.stustapay.ui.common.ErrorDialog
import de.stustapay.stustapay.ui.common.StatusText
import de.stustapay.stustapay.ui.common.TagSelectedItem
import de.stustapay.stustapay.ui.common.amountselect.AmountConfig
import de.stustapay.stustapay.ui.common.pay.CashECCallback
import de.stustapay.stustapay.ui.common.pay.PostpaymentCashECPay
import de.stustapay.stustapay.ui.nav.TopAppBar
import de.stustapay.stustapay.ui.nav.TopAppBarIcon
import de.stustapay.stustapay.ui.payinout.payout.CheckedPayOut
import de.stustapay.stustapay.ui.payinout.payout.PayOutConfirmDialog
import de.stustapay.stustapay.ui.payinout.payout.PayOutSelection
import kotlinx.coroutines.launch
import de.stustapay.libssp.ui.common.rememberDialogDisplayState

@Composable
fun PostPaymentSelection(
    leaveView: () -> Unit = {},
    viewModel: PostPaymentViewModel,
    payout: CheckedPayOut,
    onClear: () -> Unit,
) {
    // Collect state from ViewModel
    val loginState by viewModel.terminalLoginState.collectAsStateWithLifecycle()
    val status by viewModel.status.collectAsStateWithLifecycle()
    val payOutState by viewModel.payOutState.collectAsStateWithLifecycle()
    val postPaymentState by viewModel.postPaymentState.collectAsStateWithLifecycle()
    val topUpConfig by viewModel.terminalLoginState.collectAsStateWithLifecycle()
    val requestActive by viewModel.requestActive.collectAsStateWithLifecycle()
    val _errorMessage by viewModel.errorMessage.collectAsStateWithLifecycle()
    val errorMessage = _errorMessage
    val scope = rememberCoroutineScope()
    val context = LocalContext.current as Activity

    // Handle back button press
    BackHandler {
        leaveView()
    }

    // Display error dialog if there's an error
    if (errorMessage != null) {
        ErrorDialog(onDismiss = {
            scope.launch {
                viewModel.dismissError()
            }
        }) {
            Text(errorMessage, style = MaterialTheme.typography.h4)
        }
    }

    val showPayOutConfirm by viewModel.showPayOutConfirm.collectAsStateWithLifecycle()
    val confirmState = rememberDialogDisplayState()
    LaunchedEffect(showPayOutConfirm) {
        if (showPayOutConfirm) {
            confirmState.open()
        } else {
            confirmState.close()
        }
    }

    if (showPayOutConfirm) {
        PayOutConfirmDialog(
            state = confirmState,
            onConfirm = { scope.launch { viewModel.confirmPayOut() } },
            onAbort = { viewModel.dismissPayOutConfirm() },
            getAmount = { payOutState.getAmount() },
            status = { StatusText(status) }
        )
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(loginState.title().title) },
                icon = TopAppBarIcon(type = TopAppBarIcon.Type.BACK) {
                    leaveView()
                },
            )
        },
        content = { paddingValues ->
            Column(
                modifier = Modifier
                    .padding(paddingValues)
                    .padding(top = 5.dp)
                    .padding(horizontal = 10.dp)
            ) {

                if (payout.maxAmount <= 0.00) {
                    // Display selected tag with option to clear
                    TagSelectedItem(
                        tag = payout.tag,
                        onClear = onClear,
                    )
                }
                // Proceed only if payout is allowed
                if (payout.maxAmount < 0.00) {

                    // Display debit amount
                    Text(
                        stringResource(R.string.debit_amount).format(payout.maxAmount),
                        style = MaterialTheme.typography.h5,
                    )
                    // **Set the Amount Correctly via ViewModel**
                    // Update the amount in ViewModel
                    viewModel.setAmount(-payout.maxAmount)

                    // **Use CashECPay with Existing Tag**
                    PostpaymentCashECPay(
                        modifier = Modifier.fillMaxSize(),
                        existingTag = payout.tag, // Pass the existing tag here
                        status = { StatusText(status) },
                        onPaymentRequested = CashECCallback.Tag(
                            onEC = { tag ->
                                scope.launch {
                                    viewModel.topUpWithCard(context, tag)
                                    // Clear the tag after payment to prevent re-triggering
                                    viewModel.clearTag()
                                }
                            },
                            onCash = { tag ->
                                scope.launch {
                                    viewModel.topUpWithCash(tag)
                                    // Clear the tag after payment to prevent re-triggering
                                    viewModel.clearTag()
                                }
                            },
                        ),
                        ready = topUpConfig.hasConfig() && !requestActive,
                        getAmount = {
                            // Assuming currentAmount is in cents
                            viewModel.postPaymentState.value.currentAmount
                        },
                    ) { innerPaddingValues ->
                        val scrollState = rememberScrollState()
                        Column(
                            modifier = Modifier.verticalScroll(
                                scrollState,
                                reverseScrolling = true
                            )
                        ) {
                            // Additional UI components if any
                        }
                    }

                }
                if(payout.maxAmount > 0.00){
                    PayOutSelection(
                        status = status,
                        payout = payout,
                        amount = payOutState.getAmount(),
                        onAmountUpdate = { viewModel.setAmount(it.toDouble() * 100) },
                        onAmountClear = { viewModel.clearAmount() },
                        onClear = { viewModel.clearDraft() },
                        amountConfig = AmountConfig.Money(
                            limit = payOutState.getMaxAmount(),
                        ),
                        ready = loginState.hasConfig(),
                        onPayout = { scope.launch { viewModel.requestPayOut() } },
                    )
                }
                else {
                    // Display message when payout is not allowed
                    Text(
                        stringResource(R.string.no_expenses),
                        style = MaterialTheme.typography.h4,
                    )

                }
            }
        }
    )
}




