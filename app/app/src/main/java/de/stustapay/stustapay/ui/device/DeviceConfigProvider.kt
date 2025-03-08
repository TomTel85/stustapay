package de.stustapay.stustapay.ui.device

import android.content.Context
import android.os.Build
import androidx.compose.ui.unit.DpOffset
import androidx.compose.ui.unit.dp
import dagger.hilt.android.qualifiers.ApplicationContext
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Device-specific configuration.
 */
data class DeviceConfig(
    // Whether this device is an imin Falcons 2 terminal
    val isIminFalcons2: Boolean = false,
    // The offset for NFC scan dialog for this specific device
    val nfcScanDialogOffset: DpOffset = DpOffset(0.dp, 0.dp)
)

/**
 * Provides device-specific configurations based on the device model.
 */
@Singleton
class DeviceConfigProvider @Inject constructor(
    @ApplicationContext private val context: Context
) {
    private val deviceConfig: DeviceConfig = determineDeviceConfig()

    /**
     * Get the device-specific configuration.
     */
    fun getDeviceConfig(): DeviceConfig = deviceConfig

    private fun determineDeviceConfig(): DeviceConfig {
        val model = Build.MODEL.lowercase()
        
        // imin Falcon 2 configuration - NFC reader is on the left side
        if (model.contains("i24t01")) {
            return DeviceConfig(
                isIminFalcons2 = true,
                nfcScanDialogOffset = DpOffset((-300).dp, 0.dp) // Move dialog much further to the left
            )
        }
        
        // Default configuration for other devices
        return DeviceConfig()
    }
} 