package de.stustapay.stustapay.ec

import android.content.Context
import android.content.pm.PackageManager
import android.nfc.NfcAdapter
import android.nfc.NfcManager
import android.os.Build
import de.stustapay.stustapay.BuildConfig

/**
 * Utility to detect device capability for Tap To Pay payments.
 * Tap To Pay requires:
 * - NFC hardware
 * - Android 11+ (API level 30+)
 */
object PaymentCapability {
    /**
     * Check if the device supports Tap To Pay.
     * @param context Android context
     * @return true if device supports Tap To Pay, false otherwise
     */
    fun supportsTapToPay(context: Context): Boolean {
        android.util.Log.d("PaymentCapability", "Checking Tap To Pay support...")

        if (!BuildConfig.TAP_TO_PAY_INCLUDED) {
            android.util.Log.d("PaymentCapability", "  Tap To Pay SDK not included in this build")
            return false
        }

        // Check Android version (requires API 30+)
        val androidVersion = Build.VERSION.SDK_INT
        android.util.Log.d("PaymentCapability", "  Android version: $androidVersion (required: ${Build.VERSION_CODES.R})")
        if (androidVersion < Build.VERSION_CODES.R) {
            android.util.Log.d("PaymentCapability", "  Android version too old")
            return false
        }

        // Check if NFC is available
        val nfcManager = context.getSystemService(Context.NFC_SERVICE) as? NfcManager
        val nfcAdapter = nfcManager?.defaultAdapter

        if (nfcAdapter == null) {
            android.util.Log.d("PaymentCapability", "  NFC adapter not available")
            return false
        }

        // Check if NFC is enabled
        val nfcEnabled = nfcAdapter.isEnabled
        android.util.Log.d("PaymentCapability", "  NFC enabled: $nfcEnabled")
        if (!nfcEnabled) {
            android.util.Log.d("PaymentCapability", "  NFC not enabled")
            return false
        }

        // Check if NFC feature is declared in manifest
        val packageManager = context.packageManager
        val hasNfcFeature = packageManager.hasSystemFeature(PackageManager.FEATURE_NFC)
        android.util.Log.d("PaymentCapability", "  NFC feature declared: $hasNfcFeature")
        if (!hasNfcFeature) {
            android.util.Log.d("PaymentCapability", "  NFC feature not declared in manifest")
            return false
        }

        android.util.Log.d("PaymentCapability", "  Device supports Tap To Pay!")
        return true
    }

    /**
     * Check if NFC is available on the device (hardware check only).
     */
    fun hasNfcHardware(context: Context): Boolean {
        val packageManager = context.packageManager
        return packageManager.hasSystemFeature(PackageManager.FEATURE_NFC)
    }

    /**
     * Check if NFC is enabled on the device.
     */
    fun isNfcEnabled(context: Context): Boolean {
        val nfcManager = context.getSystemService(Context.NFC_SERVICE) as? NfcManager
        val nfcAdapter = nfcManager?.defaultAdapter
        return nfcAdapter?.isEnabled == true
    }
}
