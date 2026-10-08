package de.stustapay.stustapay.ui.common.operator

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.heightIn
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
import java.text.NumberFormat
import java.util.Currency
import java.util.Locale

@Composable
fun OfflineStatusIndicator(status: OfflineStatus) {
    var showDetails by remember { mutableStateOf(false) }
    val locale = Locale.getDefault()
    val currency = NumberFormat.getCurrencyInstance(locale).apply { this.currency = Currency.getInstance("EUR") }
    val saleBudget = status.remainingSaleCents?.let { currency.format(it / 100.0) }
    val returnBudget = status.remainingReturnCents?.let { currency.format(it / 100.0) }
    val remainingSeconds = status.remainingSeconds ?: 0
    val remainingMinutes = remainingSeconds / 60
    val remainingSecondPart = remainingSeconds % 60
    val chipLabel = stringResource(
        when {
            status.offlineMode && !status.preparationUsable -> R.string.sale_status_offline_unavailable
            status.offlineMode -> R.string.sale_status_offline
            else -> R.string.sale_status_online
        },
    )
    val accessibleLabel = stringResource(
        if (status.offlineMode && !status.preparationUsable) R.string.sale_status_accessibility_unavailable else R.string.sale_status_accessibility,
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
                        if (status.offlineMode && !status.preparationUsable) OperatorPalette.danger
                        else if (status.offlineMode) Color(0xFFFFB300)
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
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text(stringResource(if (status.offlineMode) R.string.sale_status_details_offline else R.string.sale_status_details_online))
                    if (status.preparationUsable) {
                        Text(stringResource(R.string.sale_status_offline_payments_available))
                        Text(stringResource(R.string.sale_offline_validity_remaining, remainingMinutes, remainingSecondPart))
                        Text(stringResource(R.string.sale_offline_sale_budget, saleBudget.orEmpty()))
                        Text(stringResource(R.string.sale_offline_return_budget, returnBudget.orEmpty()))
                    } else {
                        Text(stringResource(R.string.sale_status_offline_unavailable_detail))
                    }
                    Text(stringResource(R.string.sale_journal_pending_compact, status.pendingSales))
                }
            },
            confirmButton = {
                TextButton(onClick = { showDetails = false }) { Text(stringResource(R.string.sale_status_close)) }
            },
        )
    }
}
