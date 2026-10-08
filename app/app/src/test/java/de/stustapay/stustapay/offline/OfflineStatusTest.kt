package de.stustapay.stustapay.offline

import org.junit.Assert.assertEquals
import org.junit.Test

class OfflineStatusTest {
    @Test
    fun `remaining till budgets use only active snapshot offline counters`() {
        val rows = listOf(
            JournalSale("one", "", snapshotId = "active", sequence = 1, recordedAt = "", offline = true,
                saleCents = 250, returnCents = 70),
            JournalSale("two", "", snapshotId = "old", sequence = 2, recordedAt = "", offline = true,
                saleCents = 900, returnCents = 900),
            JournalSale("three", "", snapshotId = "active", sequence = 3, recordedAt = "", offline = false,
                saleCents = 400, returnCents = 300),
            JournalSale("four", "", snapshotId = "active", sequence = 4, recordedAt = "", offline = true,
                saleCents = 200, returnCents = 40, state = "local_rejected"),
        )

        assertEquals(750L to 430L, remainingTillBudgets("active", 1000, 500, rows))
    }

    @Test
    fun `remaining budgets never go below zero`() {
        val row = JournalSale("one", "", snapshotId = "active", sequence = 1, recordedAt = "", offline = true,
            saleCents = 500, returnCents = 600)

        assertEquals(0L to 0L, remainingTillBudgets("active", 100, 100, listOf(row)))
    }
}
