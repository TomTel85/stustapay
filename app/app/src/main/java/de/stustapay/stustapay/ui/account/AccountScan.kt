package de.stustapay.stustapay.ui.account

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import dagger.hilt.android.EntryPointAccessors
import de.stustapay.libssp.model.NfcTag
import de.stustapay.stustapay.ui.chipscan.NfcScanCard
import de.stustapay.stustapay.ui.device.DeviceConfigProvider
import de.stustapay.stustapay.ui.hilt.DeviceConfigEntryPoint

@Composable
fun AccountScan(onScan: (NfcTag) -> Unit) {
    // Get DeviceConfigProvider using Hilt EntryPoint
    val context = LocalContext.current
    val deviceConfigProvider = remember {
        EntryPointAccessors.fromApplication(
            context.applicationContext,
            DeviceConfigEntryPoint::class.java
        ).deviceConfigProvider()
    }
    
    val deviceConfig = deviceConfigProvider.getDeviceConfig()
    
    // Use the same large container with offset approach as the NfcScanDialog
    Box(
        modifier = Modifier
            .padding(20.dp)
            .fillMaxWidth(),
        contentAlignment = Alignment.Center
    ) {
        // Create a much larger Box to ensure no clipping occurs
        Box(
            modifier = Modifier
                .size(1000.dp, 800.dp)
                .padding(start = 350.dp), // Add padding from the start to shift the starting point
            contentAlignment = Alignment.CenterStart // Align from the start rather than center
        ) {
            // Apply the offset directly as a modifier on the NfcScanCard
            NfcScanCard(
                modifier = Modifier
                    .size(350.dp, 350.dp)
                    .offset(
                        x = deviceConfig.nfcScanDialogOffset.x,
                        y = deviceConfig.nfcScanDialogOffset.y
                    ),
                onScan = onScan,
                keepScanning = true,
                content = { status ->
                    // Use our enhanced content
                    EnhancedAccountScanContent(
                        isIminFalcons2 = deviceConfig.isIminFalcons2,
                        scanStatus = status
                    )
                }
            )
        }
    }
}