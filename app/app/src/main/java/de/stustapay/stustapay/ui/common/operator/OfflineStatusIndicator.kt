package de.stustapay.stustapay.ui.common.operator

import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.AlertDialog
import androidx.compose.material.Text
import androidx.compose.material.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.role
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import de.stustapay.stustapay.R
import de.stustapay.stustapay.offline.OfflineStatus
import java.time.Duration
import java.time.OffsetDateTime
import java.text.NumberFormat
import java.util.Currency
import java.util.Locale

@Composable
fun OfflineStatusIndicator(
    status: OfflineStatus,
    onSynchronize: (() -> Unit)? = null,
    onJournalPage: ((Int) -> Unit)? = null,
) {
    var showJournal by remember { mutableStateOf(false) }
    var showDetails by remember { mutableStateOf(false) }
    val locale = Locale.getDefault()
    val currency = NumberFormat.getCurrencyInstance(locale).apply { this.currency = Currency.getInstance("EUR") }
    val saleBudget = status.remainingSaleCents?.let { currency.format(it / 100.0) }
    val returnBudget = status.remainingReturnCents?.let { currency.format(it / 100.0) }
    val remainingSeconds = status.remainingSeconds ?: 0
    val remainingMinutes = remainingSeconds / 60
    val remainingSecondPart = remainingSeconds % 60
    val disconnected = status.connected == false || (status.connected == null && status.offlineMode)
    val chipLabel = stringResource(
        when {
            disconnected && !status.preparationUsable -> R.string.sale_status_offline_unavailable
            disconnected -> R.string.sale_status_offline
            status.connected == null -> R.string.sale_connection_unknown
            else -> R.string.sale_status_online
        },
    )
    val accessibleLabel = stringResource(
        if (disconnected && !status.preparationUsable) R.string.sale_status_accessibility_unavailable else R.string.sale_status_accessibility,
        chipLabel,
    )
    Box(
        modifier = Modifier
            .widthIn(min = 48.dp)
            .heightIn(min = 48.dp)
            .background(OperatorPalette.pill, RoundedCornerShape(999.dp))
            .border(1.dp, OperatorPalette.panelBorder, RoundedCornerShape(999.dp))
            .clickable(onClickLabel = stringResource(R.string.sale_status_open_details), role = Role.Button) { showDetails = true }
            .semantics { contentDescription = accessibleLabel; role = Role.Button }
            .padding(horizontal = 10.dp),
        contentAlignment = Alignment.Center,
    ) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(5.dp)) {
            Box(
                modifier = Modifier
                    .size(7.dp)
                    .background(
                        if (disconnected && !status.preparationUsable) OperatorPalette.danger
                        else if (disconnected) Color(0xFFFFB300)
                        else OperatorPalette.success,
                        CircleShape,
                    ),
            )
            Text(chipLabel, color = OperatorPalette.title, fontWeight = FontWeight.Bold, fontSize = 12.sp)
        }
    }

    if (showDetails) {
        AlertDialog(
            onDismissRequest = { showDetails = false },
            title = { Text(stringResource(R.string.sale_status_details_title)) },
            text = {
                Column(Modifier.heightIn(max = 420.dp).verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text(stringResource(when {
                        disconnected -> R.string.sale_status_details_offline
                        status.connected == null -> R.string.sale_connection_unknown
                        else -> R.string.sale_status_details_online
                    }))
                    if (status.preparationUsable) {
                        Text(stringResource(R.string.sale_status_offline_payments_available))
                        Text(stringResource(R.string.sale_offline_validity_remaining, remainingMinutes, remainingSecondPart))
                        Text(stringResource(R.string.sale_offline_sale_budget, saleBudget.orEmpty()))
                        Text(stringResource(R.string.sale_offline_return_budget, returnBudget.orEmpty()))
                    } else {
                        Text(stringResource(R.string.sale_status_offline_unavailable_detail))
                    }
                    status.preparedAt?.let {
                        Text(stringResource(R.string.sale_prepared_at, it))
                        val age = runCatching { Duration.between(OffsetDateTime.parse(it), OffsetDateTime.now()).toMinutes().coerceAtLeast(0) }.getOrNull()
                        age?.let { minutes -> Text(stringResource(R.string.sale_preparation_age, minutes)) }
                    }
                    status.lastSynchronizedAt?.let { Text(stringResource(R.string.sale_synchronized_at, it)) }
                    status.blockReason?.let { Text(it) }
                    Text(stringResource(R.string.sale_journal_pending_compact, status.pendingSales))
                    if (status.synchronizing) Text(stringResource(R.string.sale_synchronizing))
                    TextButton(onClick = { showDetails = false; showJournal = true }) { Text(stringResource(R.string.sale_journal_title)) }
                    onSynchronize?.let { synchronize ->
                        TextButton(onClick = synchronize, enabled = !status.synchronizing) {
                            Text(stringResource(R.string.sale_synchronize_prepare))
                        }
                    }
                }
            },
            confirmButton = {
                TextButton(onClick = { showDetails = false }) { Text(stringResource(R.string.sale_status_close)) }
            },
        )
    }

    if (showJournal) {
        AlertDialog(
            onDismissRequest = { showJournal = false },
            title = { Text(stringResource(R.string.sale_journal_title)) },
            text = {
                Column(Modifier.heightIn(max = 420.dp).verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                    if (status.journalPageCount > 1) {
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.SpaceBetween,
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            TextButton(
                                onClick = { onJournalPage?.invoke(status.journalPage - 1) },
                                enabled = status.journalPage > 0 && onJournalPage != null,
                            ) { Text(stringResource(R.string.sale_journal_previous)) }
                            Text(stringResource(R.string.sale_journal_page, status.journalPage + 1, status.journalPageCount))
                            TextButton(
                                onClick = { onJournalPage?.invoke(status.journalPage + 1) },
                                enabled = status.journalPage + 1 < status.journalPageCount && onJournalPage != null,
                            ) { Text(stringResource(R.string.sale_journal_next)) }
                        }
                    }
                    if (status.journalEntries.isEmpty()) Text(stringResource(R.string.sale_journal_empty))
                    status.journalEntries.forEach { entry ->
                        Column(verticalArrangement = Arrangement.spacedBy(3.dp)) {
                            Text(currency.format(entry.amountCents / 100.0), fontWeight = FontWeight.Bold)
                            Text(entry.recordedAt)
                            Text(entry.uuid, fontSize = 12.sp)
                            Text(stringResource(when {
                                entry.state == "dismissed" -> R.string.sale_journal_dismissed
                                entry.state in setOf("rejected", "local_rejected") -> R.string.sale_journal_rejected
                                entry.state in setOf("needs_review", "conflict", "clarification") || entry.transferState == "needs_owner" -> R.string.sale_journal_review
                                entry.state in setOf("accepted", "imported", "booked", "confirmed") -> R.string.sale_journal_confirmed
                                entry.state == "offline" -> R.string.sale_journal_local_accepted
                                else -> R.string.sale_journal_transfer_pending
                            }))
                            if (entry.state == "offline" && entry.transferState in setOf("pending", "sending", "uncertain", "retry", "queued")) {
                                Text(stringResource(R.string.sale_journal_transfer_pending))
                            }
                            entry.message?.let { Text(it) }
                        }
                    }
                }
            },
            confirmButton = { TextButton(onClick = { showJournal = false }) { Text(stringResource(R.string.sale_status_close)) } },
            dismissButton = {
                onSynchronize?.let { synchronize ->
                    TextButton(onClick = synchronize, enabled = !status.synchronizing) { Text(stringResource(R.string.sale_synchronize_prepare)) }
                }
            },
        )
    }
}
