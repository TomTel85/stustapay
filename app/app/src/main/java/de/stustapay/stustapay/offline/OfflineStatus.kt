package de.stustapay.stustapay.offline

/** Safe-to-display status; intentionally contains no operator or customer data. */
data class OfflineStatus(
    val offlineMode: Boolean = false,
    val preparationUsable: Boolean = false,
    val remainingSeconds: Long? = null,
    val remainingSaleCents: Long? = null,
    val remainingReturnCents: Long? = null,
    val pendingSales: Int = 0,
    val supportedButtonIds: Set<Int> = emptySet(),
)

internal fun remainingTillBudgets(
    snapshotId: String,
    saleLimitCents: Long,
    returnLimitCents: Long,
    rows: List<JournalSale>,
): Pair<Long, Long> {
    val rowsForSnapshot = rows.filter { it.offline && it.snapshotId == snapshotId && it.state !in setOf("rejected", "local_rejected") }
    return (saleLimitCents - rowsForSnapshot.sumOf { it.saleCents }).coerceAtLeast(0) to
        (returnLimitCents - rowsForSnapshot.sumOf { it.returnCents }).coerceAtLeast(0)
}
