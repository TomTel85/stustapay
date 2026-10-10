package de.stustapay.stustapay.display

import de.stustapay.api.models.PendingSale

/**
 * State displayed on the customer-facing screen
 */
sealed class CustomerDisplayState {
    data object Welcome : CustomerDisplayState()
    data object ScanChip : CustomerDisplayState()
    data object TapToPayReady : CustomerDisplayState()
    data object TapToPayCardRequested : CustomerDisplayState()
    data class TapToPayProcessing(val message: String) : CustomerDisplayState()
    data class TapToPayFailed(val message: String) : CustomerDisplayState()
    data class AccountBalance(
        val accountName: String?,
        val balance: Double,
        val voucherCount: String? = null,
    ) : CustomerDisplayState()
    data class SaleCompleted(val sale: PendingSale) : CustomerDisplayState()
    data class TopUpCompleted(val newBalance: Double, val topUpAmount: Double) : CustomerDisplayState()
    data class ValidatingSale(
        val totalPrice: Double,
        val currentBalance: Double? = null,
        val newBalance: Double? = null,
        val products: List<Pair<String, String>> = emptyList(),
    ) : CustomerDisplayState()
    data class InsufficientFunds(val totalPrice: Double, val currentBalance: Double) : CustomerDisplayState()
}
