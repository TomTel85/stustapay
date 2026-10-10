package de.stustapay.stustapay.offline

import de.stustapay.api.models.CompletedSale
import de.stustapay.api.models.PendingSale
import kotlinx.serialization.Serializable

/** Local acceptance deliberately has no server order ID or final receipt URL. */
sealed interface SaleBookingOutcome {
    @Serializable
    data class LocalAccepted(
        val sale: PendingSale,
        val recordedAt: String,
        val preparedAt: String,
    ) : SaleBookingOutcome
    data class Confirmed(val sale: CompletedSale) : SaleBookingOutcome
}

internal fun CompletedSale.pendingSale() = PendingSale(
    uuid, oldBalance, newBalance, oldVoucherBalance, newVoucherBalance, customerAccountId,
    paymentMethod, lineItems, buttons, usedVouchers, itemCount, totalPrice,
)
