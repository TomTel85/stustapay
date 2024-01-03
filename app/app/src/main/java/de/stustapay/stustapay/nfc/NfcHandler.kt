package de.stustapay.stustapay.nfc

import android.app.Activity
import android.nfc.NfcAdapter
import android.nfc.Tag
import android.nfc.TagLostException
import android.nfc.tech.MifareUltralight
import android.os.Bundle
import de.stustapay.stustapay.model.NfcScanFailure
import de.stustapay.stustapay.model.NfcScanResult
import de.stustapay.stustapay.model.NfcScanRequest
import java.io.IOException
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
            // some devices send presence heartbeats to the nfc tag.
            // this heartbeat may be sent in non-cmac-mode - and then a cmac-enabled
            // chip refuses any further communication.
            // -> adjust the check delay so we don't usually check for presence during
            //    a nfc transaction.
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

    fun hexToULong(hex: String): ULong {
        return hex.toULong(16)
    }

    private fun handleTag(tag: Tag) {
        if (!tag.techList.contains("android.nfc.tech.NfcA")) {
            dataSource.setScanResult(NfcScanResult.Fail(NfcScanFailure.Incompatible("device has no NfcA support")))
            return
        }


        // you should have checked that this device is capable of working with Mifare Ultralight tags, otherwise you receive an exception
        val mfu = MifareUltralight.get(tag)

        try {
            handleMfUlTag(mfu)

            mfu.close()
        } catch (e: TagLostException) {
            dataSource.setScanResult(
                NfcScanResult.Fail(
                    NfcScanFailure.Lost(
                        e.message ?: "unknown reason"
                    )
                )
            )
        } catch (e: TagAuthException) {
            dataSource.setScanResult(
                NfcScanResult.Fail(
                    NfcScanFailure.Auth(
                        e.message ?: "unknown reason"
                    )
                )
            )
        } catch (e: TagIncompatibleException) {
            dataSource.setScanResult(
                NfcScanResult.Fail(
                    NfcScanFailure.Incompatible(
                        e.message ?: "unknown reason"
                    )
                )
            )
        } catch (e: IOException) {
            dataSource.setScanResult(
                NfcScanResult.Fail(
                    NfcScanFailure.Lost(
                        e.message ?: "io error"
                    )
                )
            )
        } catch (e: SecurityException) {
            dataSource.setScanResult(
                NfcScanResult.Fail(
                    NfcScanFailure.Lost(
                        e.message ?: "security error"
                    )
                )
            )
        } catch (e: Exception) {
            e.printStackTrace()
            dataSource.setScanResult(
                NfcScanResult.Fail(
                    NfcScanFailure.Other(
                        e.localizedMessage ?: "unknown exception"
                    )
                )
            )
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
                        dataSource.setScanResult(NfcScanResult.FastRead(hexToULong(id)))
                    }

                }
                else ->  {
                    mfu.connect()

                }
            }
        }

    }
}
