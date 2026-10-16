package de.stustapay.stustapay.ui.sale

import com.ionspin.kotlin.bignum.integer.toBigInteger
import de.stustapay.api.models.TerminalTillConfig
import de.stustapay.api.models.PaymentMethod
import de.stustapay.api.models.PendingSale
import java.util.UUID
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotEquals
import org.junit.Test

class SaleStatusTest {
    @Test
    fun `retry after confirmed card cancellation uses a fresh order UUID and keeps the cart`() {
        val status = checkedCardSale()
        val firstAttempt = status.getNewSale(method = PaymentMethod.sumup)

        val retryStatus = status.afterCardPaymentCancelled(firstAttempt.uuid)
        val retry = retryStatus.getNewSale(method = PaymentMethod.sumup)

        assertNotEquals(firstAttempt.uuid, retry.uuid)
        assertEquals(firstAttempt.copy(uuid = retry.uuid), retry)
        assertEquals(status.checkedSale!!.copy(uuid = retry.uuid), retryStatus.checkedSale)
        assertEquals(retry.uuid, retryStatus.getNewSale(method = PaymentMethod.sumup).uuid)
        assertEquals(firstAttempt.uuid, status.checkedSale!!.uuid)
    }

    @Test
    fun `cancellation for another attempt does not change the current sale`() {
        val status = checkedCardSale()
        assertEquals(status, status.afterCardPaymentCancelled(UUID.randomUUID()))
    }

    private fun checkedCardSale(): SaleStatus = SaleStatus(
        buttonSelection = mutableMapOf(1 to SaleItemAmount.FixedPrice(2)),
        checkedSale = PendingSale(
            uuid = UUID.randomUUID(),
            oldBalance = 0.0,
            newBalance = 0.0,
            oldVoucherBalance = 0.toBigInteger(),
            newVoucherBalance = 0.toBigInteger(),
            customerAccountId = null,
            paymentMethod = PaymentMethod.sumup,
            lineItems = emptyList(),
            buttons = emptyList(),
            usedVouchers = 0.toBigInteger(),
            itemCount = 2.toBigInteger(),
            totalPrice = 4.0,
        ),
    )

    @Test
    fun `returnable buttons use signed net quantities and remove zero`() {
        val saleStatus = SaleStatus()
        val saleConfig = saleConfigWithReturnableButton()

        saleStatus.decrementButton(1, saleConfig)
        assertEquals(-1, (saleStatus.buttonSelection[1] as SaleItemAmount.FixedPrice).amount)

        saleStatus.decrementButton(1, saleConfig)
        assertEquals(-2, (saleStatus.buttonSelection[1] as SaleItemAmount.FixedPrice).amount)

        saleStatus.incrementButton(1, saleConfig)
        assertEquals(-1, (saleStatus.buttonSelection[1] as SaleItemAmount.FixedPrice).amount)

        saleStatus.incrementButton(1, saleConfig)
        assertFalse(saleStatus.buttonSelection.containsKey(1))

        saleStatus.incrementButton(1, saleConfig)
        assertEquals(1, (saleStatus.buttonSelection[1] as SaleItemAmount.FixedPrice).amount)
    }

    private fun saleConfigWithReturnableButton(): SaleConfig.Ready {
        return SaleConfig.Ready(
            tillName = "Test Till",
            buttons = mapOf(
                1 to SaleItemConfig(
                    id = 1,
                    caption = "Pfand Becher",
                    price = SaleItemPrice.Returnable(2.0),
                    returnable = true,
                )
            ),
            till = TerminalTillConfig(
                id = 1.toBigInteger(),
                name = "Test Till",
                description = null,
                eventName = "Test Event",
                profileName = "Test Profile",
                cashRegisterId = 1.toBigInteger(),
                cashRegisterName = "Cash",
                allowTopUp = false,
                allowCashOut = false,
                allowTicketSale = false,
                allowTicketVouchers = false,
                enableSspPayment = true,
                enableCashPayment = true,
                enableCardPayment = true,
                tapToPayEnabled = false,
                tapToPayAvailable = false,
                buttons = emptyList(),
                sumupSecrets = null,
                postPaymentAllowed = false,
                sumupPaymentEnabled = false,
                userPrivileges = emptyList(),
                secrets = null,
                activeUserId = null,
                availableRoles = emptyList(),
            ),
        )
    }
}
