package de.stustapay.stustapay.ui.common

import de.stustapay.api.models.TerminalConfig

/**
 * Extension property for TerminalConfig that provides the maximum account balance
 * This is a temporary solution until the API is updated to include max balance values
 */
val TerminalConfig.maxAccountBalance: Float
    get() = 200.0f  // Default value, will be updated to use VIP status in future 