package de.stustapay.stustapay.ui.payinout.postpayment

import android.app.Activity
import android.util.Log
import androidx.activity.compose.BackHandler
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.Button
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
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import de.stustapay.stustapay.R
import de.stustapay.stustapay.ui.common.ErrorDialog
import de.stustapay.stustapay.ui.common.StatusText
import de.stustapay.stustapay.ui.common.TagSelectedItem
import de.stustapay.stustapay.ui.common.pay.CashECCallback
import de.stustapay.stustapay.ui.common.pay.CashECPay
import de.stustapay.stustapay.ui.common.pay.NoCashRegisterWarning
import de.stustapay.stustapay.ui.common.pay.PostpaymentCashECPay
import de.stustapay.stustapay.ui.nav.TopAppBar
import de.stustapay.stustapay.ui.nav.TopAppBarIcon
import de.stustapay.stustapay.ui.payinout.payout.CheckedPayOut
import kotlinx.coroutines.launch


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
    val postPaymentState by viewModel.postPaymentState.collectAsStateWithLifecycle()
    val payOutState by viewModel.payOutState.collectAsStateWithLifecycle()
    val topUpConfig by viewModel.terminalLoginState.collectAsStateWithLifecycle()
    val requestActive by viewModel.requestActive.collectAsStateWithLifecycle()
    val _errorMessage by viewModel.errorMessage.collectAsStateWithLifecycle()
    val errorMessage = _errorMessage
    val scope = rememberCoroutineScope()
    val context = LocalContext.current as Activity
    val canPayOut = payout.maxAmount <= -0.01

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
                // Display selected tag with option to clear
                TagSelectedItem(
                    tag = payout.tag,
                    onClear = onClear,
                )

                // Display debit amount
                Text(
                    stringResource(R.string.debit_amount).format(payout.maxAmount),
                    style = MaterialTheme.typography.h5,
                )

                // Proceed only if payout is allowed
                if (canPayOut) {
                    // **Set the Amount Correctly via ViewModel**
                    // Assuming payout.amount is in euros and negative for payouts
                    val amountInCents = if (payout.amount < 0) -payout.amount else payout.amount
                    // Update the amount in ViewModel
                    viewModel.setAmount(amountInCents)

                    // **Use CashECPay with Existing Tag**
                    PostpaymentCashECPay(
                        modifier = Modifier.fillMaxSize(),
                        existingTag = payout.tag, // Pass the existing tag here
                        checkAmount = {
                            viewModel.checkAmountLocal(postPaymentState.currentAmount)
                        },
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

                } else {
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




