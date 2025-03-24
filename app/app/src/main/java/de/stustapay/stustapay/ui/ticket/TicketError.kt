package de.stustapay.stustapay.ui.ticket

import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import de.stustapay.stustapay.R
import de.stustapay.stustapay.ui.common.ErrorScreen

@Composable
fun TicketError(
    onDismiss: () -> Unit,
    viewModel: TicketViewModel
) {
    val status by viewModel.status.collectAsStateWithLifecycle()
    val config by viewModel.terminalLoginState.collectAsStateWithLifecycle()

    ErrorScreen(
        modifier = Modifier.fillMaxSize(),
        onDismiss = onDismiss,
        topBarTitle = config.title().title,
    ) {
        Text(text = stringResource(R.string.ticket_error_preambel), fontSize = 30.sp)

        Text(status, fontSize = 24.sp)
    }
}