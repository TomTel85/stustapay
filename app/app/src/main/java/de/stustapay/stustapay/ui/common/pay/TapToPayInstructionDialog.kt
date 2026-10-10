package de.stustapay.stustapay.ui.common.pay

import androidx.compose.foundation.layout.*
import androidx.compose.material.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.runtime.remember
import androidx.compose.ui.platform.LocalContext
import dagger.hilt.android.EntryPointAccessors
import de.stustapay.stustapay.ec.PaymentCapability
import de.stustapay.stustapay.ui.device.DeviceConfigProvider
import de.stustapay.stustapay.ui.hilt.DeviceConfigEntryPoint

/**
 * Dialog showing Tap To Pay instructions, especially for devices with NFC in the display.
 * This is shown before starting a Tap To Pay payment to guide users on where to hold their card.
 */
@Composable
fun TapToPayInstructionDialog(
    onDismiss: () -> Unit,
    onContinue: () -> Unit,
    modifier: Modifier = Modifier
) {
    val context = LocalContext.current
    val deviceConfigProvider = remember {
        EntryPointAccessors.fromApplication(
            context.applicationContext,
            DeviceConfigEntryPoint::class.java
        ).deviceConfigProvider()
    }
    val deviceConfig = deviceConfigProvider.getDeviceConfig()

    Dialog(
        onDismissRequest = onDismiss,
        properties = DialogProperties(
            dismissOnBackPress = true,
            dismissOnClickOutside = false
        )
    ) {
        Card(
            modifier = modifier
                .fillMaxWidth(0.9f)
                .padding(16.dp),
            elevation = 8.dp
        ) {
            Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(24.dp),
                horizontalAlignment = Alignment.CenterHorizontally,
                verticalArrangement = Arrangement.spacedBy(16.dp)
            ) {
                // Title
                Text(
                    text = "Tap Your Card",
                    style = MaterialTheme.typography.h5,
                    textAlign = TextAlign.Center
                )

                // Device-specific instructions
                if (deviceConfig.isIminFalcons2) {
                    // imin device with NFC in display
                    Column(
                        horizontalAlignment = Alignment.CenterHorizontally,
                        verticalArrangement = Arrangement.spacedBy(12.dp)
                    ) {
                        Text(
                            text = "Hold your card or phone on the screen",
                            style = MaterialTheme.typography.body1,
                            textAlign = TextAlign.Center,
                            fontSize = 18.sp
                        )
                        Text(
                            text = "Place your card or mobile device on the NFC area in the center of the display",
                            style = MaterialTheme.typography.body2,
                            textAlign = TextAlign.Center,
                            color = MaterialTheme.colors.onSurface.copy(alpha = 0.7f)
                        )
                        // Visual indicator - could be enhanced with an icon or graphic
                        Box(
                            modifier = Modifier
                                .size(120.dp)
                                .padding(16.dp),
                            contentAlignment = Alignment.Center
                        ) {
                            // Simple visual representation
                            Card(
                                modifier = Modifier.size(100.dp),
                                backgroundColor = MaterialTheme.colors.primary.copy(alpha = 0.1f),
                                elevation = 4.dp
                            ) {
                                Box(
                                    modifier = Modifier.fillMaxSize(),
                                    contentAlignment = Alignment.Center
                                ) {
                                    Text(
                                        text = "📱\nNFC",
                                        textAlign = TextAlign.Center,
                                        fontSize = 24.sp
                                    )
                                }
                            }
                        }
                    }
                } else {
                    // Generic instructions for other devices
                    Column(
                        horizontalAlignment = Alignment.CenterHorizontally,
                        verticalArrangement = Arrangement.spacedBy(12.dp)
                    ) {
                        Text(
                            text = "Hold your card or phone near the device",
                            style = MaterialTheme.typography.body1,
                            textAlign = TextAlign.Center,
                            fontSize = 18.sp
                        )
                        Text(
                            text = "Place your card or mobile device near the NFC reader on this device",
                            style = MaterialTheme.typography.body2,
                            textAlign = TextAlign.Center,
                            color = MaterialTheme.colors.onSurface.copy(alpha = 0.7f)
                        )
                    }
                }

                Divider(modifier = Modifier.padding(vertical = 8.dp))

                // Action buttons
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(12.dp)
                ) {
                    OutlinedButton(
                        onClick = onDismiss,
                        modifier = Modifier.weight(1f)
                    ) {
                        Text("Cancel")
                    }
                    Button(
                        onClick = onContinue,
                        modifier = Modifier.weight(1f)
                    ) {
                        Text("Continue")
                    }
                }
            }
        }
    }
}

/**
 * Helper function to check if Tap To Pay instruction dialog should be shown.
 * Returns true if device supports Tap To Pay and should show instructions.
 */
fun shouldShowTapToPayInstructions(context: android.content.Context): Boolean {
    return PaymentCapability.supportsTapToPay(context)
}
