package de.stustapay.stustapay.nfc

import android.nfc.tech.MifareUltralight // Use the appropriate import for MIFARE Ultralight C
import de.stustapay.stustapay.util.BitVector
import de.stustapay.stustapay.util.asBitVector

const val PAGE_COUNT_ULC = 48uL // MIFARE Ultralight C has 48 pages
const val USER_BYTES_ULC  = 384uL // MIFARE Ultralight C has 384 bytes of user memory

fun cmdGetVersion(tag: MifareUltralight): BitVector {
    val cmd = byteArrayOf(0x60.toByte())
    return tag.transceive(cmd).asBitVector()
}

fun cmdRead(page: UByte, tag: MifareUltralight): BitVector {
    if (page !in 0x00uL until PAGE_COUNT_ULC) { throw IllegalArgumentException() }

    val cmd = byteArrayOf(0x30.toByte(), page.toByte())
    return tag.transceive(cmd).asBitVector()
}

fun cmdWrite(page: UByte, data: ByteArray, tag: MifareUltralight) {
    if (page !in 0x00uL until PAGE_COUNT_ULC || data.size != 4) { throw Exception("Invalid parameters") }

    val cmd = byteArrayOf(0xA2.toByte(), page.toByte(), data[0], data[1], data[2], data[3])
    tag.writePage(page.toInt(), data)
    tag.transceive(cmd)
}

fun cmdAuthenticate1(type: UByte, tag: MifareUltralight): BitVector {
    if (type !in 0x00u..0x02u) { throw Exception("Invalid parameters") }

    val cmd = byteArrayOf(0x1A.toByte(), type.toByte())
    return tag.transceive(cmd).asBitVector()
}

fun cmdAuthenticate2(challenge: BitVector, tag: MifareUltralight): BitVector {
    if (challenge.len != 32uL * 8uL) { throw Exception("Invalid parameters") }

    val cmd = ByteArray(33)
    cmd[0] = 0xAF.toByte()
    for (i in 0 until 32) {
        cmd[i + 1] = challenge.gbe(i.toULong()).toByte() // Convert to Byte
    }

    return tag.transceive(cmd).asBitVector()
}
