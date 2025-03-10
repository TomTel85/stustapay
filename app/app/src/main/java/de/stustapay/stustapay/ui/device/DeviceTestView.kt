package de.stustapay.stustapay.ui.device

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.material.Button
import androidx.compose.material.Divider
import androidx.compose.material.Scaffold
import androidx.compose.material.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import dagger.hilt.android.EntryPointAccessors
import de.stustapay.stustapay.ui.chipscan.NfcScanDialog
import de.stustapay.stustapay.ui.chipscan.rememberNfcScanDialogState
import de.stustapay.stustapay.ui.hilt.DeviceConfigEntryPoint
import de.stustapay.stustapay.ui.nav.TopAppBar

/**
 * A simple test view to help verify the NFC scan dialog positioning on various devices.
 * This is not meant to be used in production, but only for testing purposes.
 */
@Composable
fun DeviceTestView(
    leaveView: () -> Unit
) {
    // Get DeviceConfigProvider using Hilt EntryPoint
    val context = LocalContext.current
    val deviceConfigProvider = remember {
        EntryPointAccessors.fromApplication(
            context.applicationContext,
            DeviceConfigEntryPoint::class.java
        ).deviceConfigProvider()
    }
    
    val deviceConfig = deviceConfigProvider.getDeviceConfig()
    val scanState = rememberNfcScanDialogState()
    val deviceModel = android.os.Build.MODEL
    
    Scaffold(
        topBar = { TopAppBar(title = { Text("Device Test") }) }
    ) { paddingValues ->
        Column(
            modifier = Modifier
                .padding(paddingValues)
                .fillMaxSize()
                .padding(16.dp),
            horizontalAlignment = Alignment.CenterHorizontally
        ) {
            Text("Device Test Mode", fontSize = 24.sp, fontWeight = FontWeight.Bold)
            Spacer(modifier = Modifier.height(24.dp))
            
            Text("Device Model: $deviceModel", fontSize = 16.sp)
            Text("Build.MODEL (lowercase): ${deviceModel.lowercase()}", fontSize = 14.sp)
            Spacer(modifier = Modifier.height(16.dp))
            
            Divider()
            Spacer(modifier = Modifier.height(16.dp))
            
            Text("Device Configuration", fontSize = 18.sp, fontWeight = FontWeight.Bold)
            Spacer(modifier = Modifier.height(8.dp))
            
            Text("Detected as imin Falcon 2: ${deviceConfig.isIminFalcons2}")
            Text("Detection criteria: contains 'i24t01'")
            
            if (deviceConfig.isIminFalcons2) {
                Text(
                    "Custom design for Falcon 2 devices",
                    fontSize = 16.sp,
                    fontWeight = FontWeight.Bold
                )
                Text(
                    "• Enhanced UI with animations and visual cues",
                    fontSize = 14.sp
                )
                Text(
                    "• Directional arrows pointing to the NFC reader",
                    fontSize = 14.sp
                )
                Text(
                    "• \"Chip hier vorhalten\" text",
                    fontSize = 14.sp
                )
            }
            
            Spacer(modifier = Modifier.height(16.dp))
            
            Text(
                "NFC Dialog Offset: X=${deviceConfig.nfcScanDialogOffset.x}, Y=${deviceConfig.nfcScanDialogOffset.y}",
                fontSize = 16.sp
            )
            Spacer(modifier = Modifier.height(32.dp))
            
            Text(
                "Dialog container size is now 1000dp × 800dp with CenterStart alignment and 350dp start padding",
                fontSize = 14.sp
            )
            Text(
                "Enhanced UI with animations and visual indicators to guide users.",
                fontSize = 14.sp
            )
            Spacer(modifier = Modifier.height(32.dp))
            
            Button(onClick = { scanState.open() }) {
                Text("Test Enhanced NFC Scan Dialog")
            }
            
            // NFC Scan Dialog will be shown when the button is clicked
            NfcScanDialog(
                state = scanState,
                onScan = { /* Do nothing, just for testing */ }
            )
        }
    }
}