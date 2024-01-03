package de.stustapay.stustapay.nfc

import android.nfc.Tag
import android.nfc.tech.MifareUltralight
import java.io.IOException

class MifareUltralightC(private val rawTag: Tag) {
    private val mifareUltralightTag: MifareUltralight = MifareUltralight.get(rawTag)

    fun authenticate(key: ByteArray) {
        if (key.size != 6) { throw IllegalArgumentException("Key size must be 6 bytes for 3DES authentication.") }

        mifareUltralightTag.connect()

        try {
            val authCmd = ByteArray(8)
            authCmd[0] = 0x1A  // this is the AUTH0 command
            authCmd[1] = 0x00  // authentication with the provided key

            System.arraycopy(key, 0, authCmd, 2, key.size)

            val response = mifareUltralightTag.transceive(authCmd)
            if (response.size != 8) {
                throw IOException("Authentication failed, unexpected response size.")
            }
            // Further processing can be added here based on the received response.

        } catch (e: IOException) {
            throw IOException("Authentication failed.", e)
        } finally {
            mifareUltralightTag.close()
        }
    }

    fun connect() {
        mifareUltralightTag.connect()
    }

    fun close() {
        mifareUltralightTag.close()
    }
}
