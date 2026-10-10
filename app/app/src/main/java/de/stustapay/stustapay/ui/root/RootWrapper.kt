package de.stustapay.stustapay.ui.root

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material.MaterialTheme
import androidx.compose.material.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import de.stustapay.stustapay.R
import de.stustapay.stustapay.ui.common.selfservice.ObserveAppDisplayMode


@Composable
fun RootWrapper(
    viewModel: RootWrapperViewModel = hiltViewModel(), content: @Composable () -> Unit
) {
    val infallibleVisible by viewModel.infallibleVisible.collectAsStateWithLifecycle()
    val managedAppDisplayMode by viewModel.managedAppDisplayMode.collectAsStateWithLifecycle()
    val sumUpSandboxActive by viewModel.sumUpSandboxActive.collectAsStateWithLifecycle()
    ObserveAppDisplayMode(managedDisplayMode = managedAppDisplayMode)
    RootWrapperContent(infallibleVisible, sumUpSandboxActive, content)
}


@Composable
fun RootWrapperContent(
    infallibleVisible: Boolean,
    sumUpSandboxActive: Boolean = false,
    content: @Composable () -> Unit,
) {
    if (infallibleVisible) {
        InfallibleError()
    } else {
        Box {
            content()
            if (sumUpSandboxActive) {
                Text(
                    text = stringResource(R.string.sumup_sandbox_banner),
                    modifier = Modifier
                        .align(Alignment.TopCenter)
                        .fillMaxWidth()
                        .background(Color(0xFFFFB300))
                        .padding(vertical = 4.dp),
                    color = Color.Black,
                    fontWeight = FontWeight.Bold,
                    style = MaterialTheme.typography.subtitle1,
                )
            }
        }
    }
}
