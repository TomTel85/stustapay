package de.stustapay.libssp.nfc

import android.app.Activity
import android.nfc.NfcAdapter
import android.nfc.Tag
import android.nfc.TagLostException
import android.nfc.tech.MifareUltralight
import android.os.Bundle
import android.util.Log
import com.ionspin.kotlin.bignum.integer.toBigInteger
import de.stustapay.libssp.model.NfcScanFailure
import de.stustapay.libssp.model.NfcScanRequest
import de.stustapay.libssp.model.NfcScanResult
import de.stustapay.libssp.model.NfcTag
import de.stustapay.libssp.util.BitVector
import de.stustapay.libssp.util.asBitVector
import java.io.IOException
import java.nio.charset.Charset
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class NfcHandler @Inject constructor(
    private val dataSource: NfcDataSource
) {
    private lateinit var device: NfcAdapter

    fun onCreate(activity: Activity) {
        device = NfcAdapter.getDefaultAdapter(activity)
    }

    fun onPause(activity: Activity) {
        device.disableReaderMode(activity)
    }

    fun onResume(activity: Activity) {
        device.enableReaderMode(
            activity,
            { tag -> handleTag(tag) },
            NfcAdapter.FLAG_READER_NFC_A or NfcAdapter.FLAG_READER_NO_PLATFORM_SOUNDS,
            Bundle().apply {
                putInt(NfcAdapter.EXTRA_READER_PRESENCE_CHECK_DELAY, 500)
            }
        )
    }

    private fun bytesToHexNpe(bytes: ByteArray?): String {
        if (bytes == null) return ""
        val result = StringBuffer()
        for (b in bytes) result.append(
            ((b.toInt() and 0xff) + 0x100).toString(16).substring(1)
        )
        return result.toString()
    }

    private fun handleTag(tag: Tag) {
        Log.d("NfcHandler", "Tag technologies: ${tag.techList.joinToString()}")

        if (!tag.techList.contains("android.nfc.tech.NfcA")) {
            dataSource.setScanResult(
                NfcScanResult.Fail(NfcScanFailure.Incompatible("Device has no NfcA support"))
            )
            return
        }

        if (tag.techList.contains("android.nfc.tech.MifareUltralight")) {
            val mfu = MifareUltralight.get(tag)
            handleMfUlTag(mfu)
        } else if (tag.techList.contains("android.nfc.tech.MifareUltralightAES")) {
            val mfUlAesTag = MifareUltralightAES(tag)
            handleMfUlAesTag(mfUlAesTag)
        } else {
            dataSource.setScanResult(
                NfcScanResult.Fail(
                    NfcScanFailure.Incompatible("Tag not supported")
                )
            )
        }
    }


    private fun handleMfUlAesTag(tag: MifareUltralightAES) {
        val req = dataSource.getScanRequest()
        if (req != null) {
            when (req) {
                is NfcScanRequest.Read -> {
                    tag.connect()
                    dataSource.setScanResult(NfcScanResult.Read(tag.fastRead(req.uidRetrKey, req.dataProtKey)))
                }
                is NfcScanRequest.Write -> {
                    try {
                        tag.connect()
                    } catch (e: TagIncompatibleException) {
                        dataSource.setScanResult(
                            NfcScanResult.Fail(
                                NfcScanFailure.Incompatible(
                                    e.message ?: "Unknown reason"
                                )
                            )
                        )
                        return
                    }

                    authenticate(tag, true, true, req.dataProtKey!!)

                    tag.setCMAC(true)
                    tag.setAuth0(0x10u)
                    tag.writeUserMemory("StuStaPay at StuStaCulum 2024\n".toByteArray(Charset.forName("UTF-8")).asBitVector())
                    tag.writePin("WWWWWWWWWWWW")
                    tag.writeDataProtKey(req.dataProtKey)
                    tag.writeUidRetrKey(req.uidRetrKey)
                    dataSource.setScanResult(NfcScanResult.Write)
                }
                is NfcScanRequest.Test -> {
                    val log = tag.test(req.dataProtKey, req.uidRetrKey)
                    dataSource.setScanResult(NfcScanResult.Test(log))
                }
                else -> {
                    // Handle unsupported request types
                    dataSource.setScanResult(
                        NfcScanResult.Fail(
                            NfcScanFailure.Incompatible("Request type not supported for MifareUltralightAES tags")
                        )
                    )
                }
            }
        }
    }

    private fun handleMfUlTag(mfu: MifareUltralight) {
        val req = dataSource.getScanRequest()
        if (req != null) {
            when (req) {
                is NfcScanRequest.FastRead -> {
                    mfu.connect()
                    if (mfu.isConnected) {
                        val id = bytesToHexNpe(mfu.tag.id)
                        val uidBigInt = id.toULong(16).toBigInteger()
                        val nfcTag = NfcTag(uid = uidBigInt, pin = id)
                        dataSource.setScanResult(NfcScanResult.FastRead(nfcTag))
                    }
                }
                else -> {
                    mfu.connect()
                }
            }
        }
    }

    private fun authenticate(
        tag: MifareUltralightAES,
        auth: Boolean,
        cmac: Boolean,
        key: BitVector
    ): Boolean {
        try {
            if (auth) {
                tag.authenticate(key, MifareUltralightAES.KeyType.DATA_PROT_KEY, cmac)
            }
        } catch (e: Exception) {
            dataSource.setScanResult(
                NfcScanResult.Fail(
                    NfcScanFailure.Auth(
                        e.message ?: "Unknown auth error"
                    )
                )
            )
            return false
        }
        return true
    }
}
