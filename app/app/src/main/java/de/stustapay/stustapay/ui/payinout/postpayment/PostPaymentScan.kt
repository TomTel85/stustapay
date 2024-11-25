package de.stustapay.stustapay.ui.payinout.postpayment

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.material.Scaffold
import androidx.compose.material.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.material.TopAppBar
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Close
import androidx.compose.ui.graphics.Color
import androidx.compose.material.IconButton
import androidx.compose.material.Icon
import de.stustapay.libssp.model.NfcTag
import de.stustapay.stustapay.ui.chipscan.NfcScanCard
import de.stustapay.stustapay.ui.common.StatusText
import de.stustapay.libssp.ui.theme.NfcScanStyle


@Composable
fun PostPaymentScan(
    onScan: (NfcTag) -> Unit,
    status: String,
    leaveView: () -> Unit,
) {

    BackHandler {
        leaveView()
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = {},
                backgroundColor = Color.Transparent,
                elevation = 0.dp,
                actions = {
                    IconButton(onClick = { leaveView() }) {
                        Icon(
                            imageVector = Icons.Default.Close,
                            contentDescription = "Cancel",
                            tint = Color.Red
                        )
                    }
                }
            )
        },
        bottomBar = {
            StatusText(
                status,
                modifier = Modifier.padding(horizontal = 20.dp)
            )
        }
    ) { paddingValues ->
        LazyColumn(
            modifier = Modifier
                .padding(paddingValues)
                .padding(20.dp)
                .fillMaxWidth(),
        ) {
            item {
                NfcScanCard(
                    modifier = Modifier
                        .padding(20.dp)
                        .fillMaxWidth(),
                    onScan = onScan,
                    showStatus = false,
                ) { scanStatus ->
                    Text(
                        text = "Scan a Chip",
                        modifier = Modifier.fillMaxWidth(),
                        style = NfcScanStyle,
                    )
                    Text(
                        // Money with wings emoji
                        text = "\uD83D\uDCB8",
                        modifier = Modifier.fillMaxWidth(),
                        fontSize = 100.sp,
                        textAlign = TextAlign.Center,
                    )
                    Text(
                        text = scanStatus,
                        modifier = Modifier.fillMaxWidth(),
                        fontSize = 26.sp,
                    )
                }
            }
        }
    }
}