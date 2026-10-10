package de.stustapay.stustapay.offline

import org.junit.Assert.*
import org.junit.Test
import java.util.UUID

class OfflineSynchronizationTest {
    private fun row(sequence: Long, snapshot: String = "snapshot") = JournalSale(
        UUID.randomUUID().toString(), "payload", state = "offline", snapshotId = snapshot,
        sequence = sequence, recordedAt = "timestamp", offline = true,
    )

    @Test fun batchesKeepAdmissionOrderAndNeverMixSnapshotsOrExceedWireLimit() {
        val rows = (1L..205L).map { row(it) } + row(206, "other") + row(207)
        val batches = offlineBatches(rows.reversed())
        assertEquals(listOf(100, 100, 5, 1, 1), batches.map { it.size })
        assertEquals(rows.map { it.uuid }, batches.flatten().map { it.uuid })
        assertTrue(batches.all { batch -> batch.map { it.snapshotId }.distinct().size == 1 })
    }

    @Test fun partialResponsesOnlySettleReturnedUuidsRegardlessOfOrder() {
        val rows = listOf(row(1), row(2), row(3))
        val replies = listOf(
            OfflineResult(UUID.fromString(rows[2].uuid), "clarification_required"),
            OfflineResult(UUID.fromString(rows[0].uuid), "dismissed"),
        )
        val matched = matchedOfflineReplies(rows, replies)
        assertEquals(setOf(rows[0].uuid, rows[2].uuid), matched.keys)
        assertFalse(rows[1].uuid in matched)
    }

    @Test fun duplicatesUnsolicitedAndIncompleteConfirmationsStayUnresolved() {
        val rows = listOf(row(1), row(2))
        val duplicate = OfflineResult(UUID.fromString(rows[0].uuid), "dismissed")
        val missingReceipt = OfflineResult(UUID.fromString(rows[1].uuid), "booked")
        assertTrue(matchedOfflineReplies(rows, listOf(duplicate, duplicate, missingReceipt,
            OfflineResult(UUID.randomUUID(), "dismissed"))).isEmpty())
        assertTrue(matchedOfflineReplies(rows, listOf(duplicate.copy(status = "not_found"))).isEmpty())
    }

    @Test fun retryReplyPreservesAcceptedSaleAndItsReservedBudget() {
        val sale = row(1).copy(debitCents = 500, saleCents = 500, localReceipt = "receipt")
        val reply = OfflineResult(UUID.fromString(sale.uuid), "retry_required", message = "Temporary failure")
        assertEquals(reply, matchedOfflineReplies(listOf(sale), listOf(reply))[sale.uuid])
        val retry = reconcileJournalReply(sale, reply.status, null, reply.message, requestedOffline = true)
        assertEquals("offline", retry.state)
        assertEquals("queued", retry.transferState)
        assertEquals(sale.payload, retry.payload)
        assertEquals(sale.localReceipt, retry.localReceipt)
        assertEquals(sale.debitCents, retry.debitCents)
        val clarification = sale.copy(state = "clarification", transferState = "blocked")
        assertEquals("offline", reconcileJournalReply(clarification, reply.status, null, reply.message, true).state)
        val confirmed = sale.copy(state = "booked", result = "final", transferState = "confirmed")
        assertEquals(confirmed, reconcileJournalReply(confirmed, reply.status, null, reply.message, true))
    }
}
