package de.stustapay.stustapay.ui.common.pay


import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material.Button
import androidx.compose.material.Divider
import androidx.compose.material.Scaffold
import androidx.compose.material.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.hapticfeedback.HapticFeedbackType
import androidx.compose.ui.platform.LocalHapticFeedback
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import de.stustapay.libssp.model.NfcTag
import de.stustapay.libssp.ui.theme.LargeButtonStyle
import de.stustapay.stustapay.R
import de.stustapay.stustapay.ui.chipscan.NfcScanDialog
import de.stustapay.stustapay.ui.chipscan.rememberNfcScanDialogState
import de.stustapay.stustapay.ui.nav.navigateTo

enum class PostPaymentCashECPage(val route: String) {
    Selection("selection"),
    CashConfirm("cash_confirm"),
}

/**
 * if we want to pay something either by cash or by credit card.
 */
@Composable
fun PostpaymentCashECPay(
    modifier: Modifier = Modifier,
    existingTag: NfcTag? = null, // New optional parameter
    onPaymentRequested: CashECCallback,
    checkAmount: () -> Boolean = { true },
    ready: Boolean,
    getAmount: () -> Double,
    status: @Composable () -> Unit = {},
    content: @Composable (PaddingValues) -> Unit,
) {
    val nav = rememberNavController()

    NavHost(
        modifier = modifier,
        navController = nav,
        startDestination = PostPaymentCashECPage.Selection.route,
    ) {
        composable(PostPaymentCashECPage.Selection.route) {
            PostPaymentCashECSelection(
                goToCash = {
                    if (checkAmount()) {
                        nav.navigateTo(PostPaymentCashECPage.CashConfirm.route)
                    }
                },
                goToEC = {
                    if (checkAmount()) {
                        nav.navigateTo(PostPaymentCashECPage.CashConfirm.route)
                    }
                },
                onPayRequested = onPaymentRequested,
                ready = ready,
                status = status,
                checkAmount = checkAmount,
                existingTag = existingTag, // Pass the existing tag to the selection screen
                content = content,
            )
        }
        composable(PostPaymentCashECPage.CashConfirm.route) {
            PostPaymentCashConfirmView(
                goBack = { nav.navigateTo(PostPaymentCashECPage.Selection.route) },
                getAmount = getAmount,
                status = status,
                onPay = onPaymentRequested,
                existingTag = existingTag // Pass the existing tag to the confirmation view
            )
        }
    }
}


/**
 * Container for payment selections.
 * Has Cash/EC button in the bottom bar.
 */
@Composable
fun PostPaymentCashECSelection(
    goToCash: () -> Unit,
    goToEC: () -> Unit,
    onPayRequested: CashECCallback,
    ready: Boolean,
    checkAmount: () -> Boolean = { true },
    existingTag: NfcTag? = null, // Accept the existing tag
    viewModel: CashECSelectionViewModel = hiltViewModel(),
    status: @Composable () -> Unit = {},
    content: @Composable (PaddingValues) -> Unit
) {
    val haptic = LocalHapticFeedback.current
    val config by viewModel.terminalLoginState.collectAsStateWithLifecycle()

    Scaffold(
        content = content,
        bottomBar = {
            Column(
                modifier = Modifier
                    .padding(horizontal = 10.dp)
                    .padding(bottom = 5.dp)
            ) {
                Divider(modifier = Modifier.fillMaxWidth())
                status()

                Row(modifier = Modifier.padding(top = 5.dp)) {
                    // Cash flow
                    Button(
                        modifier = Modifier
                            .fillMaxWidth(0.5f)
                            .padding(end = 10.dp),
                        onClick = {
                            haptic.performHapticFeedback(HapticFeedbackType.LongPress)
                            goToCash()
                        },
                        enabled = ready && config.canHandleCash(),
                    ) {
                        // Unicode "Coin"
                        Text(
                            stringResource(R.string.pay_cash),
                            textAlign = TextAlign.Center,
                            style = LargeButtonStyle,
                        )
                    }

                    // EC Flow
                    val scanState = rememberNfcScanDialogState()
                    NfcScanDialog(
                        state = scanState,
                        onScan = { tag ->
                            when (onPayRequested) {
                                is CashECCallback.Tag -> {
                                    onPayRequested.onEC(tag)
                                }
                                is CashECCallback.NoTag -> {
                                    // Never reached
                                    error("NFC scanned in EC NoTag mode")
                                }
                            }
                        }
                    )

                    Button(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(start = 10.dp),
                        onClick = {
                            haptic.performHapticFeedback(HapticFeedbackType.LongPress)
                            if (checkAmount()) {
                                if (existingTag != null) {
                                    // Use the provided tag for EC payment
                                    when (onPayRequested) {
                                        is CashECCallback.Tag -> {
                                            onPayRequested.onEC(existingTag)
                                            goToEC() // Navigate to confirmation
                                        }
                                        is CashECCallback.NoTag -> {
                                            // Should not be reached
                                            error("NoTag callback with an existing tag.")
                                        }
                                    }
                                } else {
                                    // Open NFC dialog for scanning
                                    scanState.open()
                                }
                            }
                        },
                        enabled = ready,
                    ) {
                        // Unicode "Credit Card"
                        Text(
                            stringResource(R.string.pay_card),
                            textAlign = TextAlign.Center,
                            style = LargeButtonStyle,
                        )
                    }
                }
            }
        }
    )
}

