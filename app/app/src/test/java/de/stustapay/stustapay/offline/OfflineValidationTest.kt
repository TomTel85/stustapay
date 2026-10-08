package de.stustapay.stustapay.offline

import com.ionspin.kotlin.bignum.integer.toBigInteger
import de.stustapay.api.models.*
import org.junit.Assert.*
import org.junit.Test
import java.time.OffsetDateTime
import java.util.UUID

class OfflineValidationTest {
    private val product = Product("Drink", 5.0, true, 1.toBigInteger(), emptyList(), true, false,
        1.toBigInteger(), 1.toBigInteger(), "tax", 0.19, ProductType.user_defined)
    private val deposit = product.copy(name = "Deposit", price = 2.0, isReturnable = true, id = 2.toBigInteger())
    private val freeProduct = product.copy(name = "Tip", price = null, fixedPrice = false, id = 3.toBigInteger())
    private val snapshot = PreparedOfflineSnapshot(UUID.randomUUID(), OffsetDateTime.now(), OffsetDateTime.now().plusHours(2),
        1, 1, 1, 1, OfflineRules(7200, 2000, 3000, 50000, 2000, 3000, 50000),
        listOf(OfflineCustomer(1, 42.toBigInteger(), 2000)),
        listOf(OfflineButton(1, "Drink", listOf(product)), OfflineButton(2, "Return", listOf(deposit)),
            OfflineButton(3, "Tip", listOf(freeProduct))))
    private fun sale(vararg buttons: Button) = NewSale(UUID.randomUUID(), PaymentMethod.tag, buttons.toList(), 42.toBigInteger())
    private fun button(id: Int, count: Int) = Button(id.toBigInteger(), count.toBigInteger())
    private fun prior(debit: Long = 1000, returns: Long = 0, state: String = "offline") = JournalSale("prior", "", state = state,
        snapshotId = snapshot.id.toString(), sequence = 1, recordedAt = "", tagUid = "42", debitCents = debit,
        saleCents = debit, returnCents = returns, offline = true)
    private fun rejected(block: () -> Unit) {
        try { block(); fail("Expected rejection") } catch (_: IllegalArgumentException) { } catch (_: IllegalStateException) { }
    }
    @Test fun fixedPriceIgnoresEditingLockAndUsesCentMath() {
        val checked = validateOffline(snapshot, sale(button(1, 3)), emptyList())
        assertEquals(1500L, checked.debit)
        assertEquals(5.0, checked.pending.newBalance, 0.0)
    }
    @Test fun returnsCannotBypassGrossSalesLimit() {
        rejected { validateOffline(snapshot, sale(button(1, 5), button(2, -10)), emptyList()) }
    }
    @Test fun pureReturnsDoNotIncreaseSpendableBalance() {
        val checked = validateOffline(snapshot, sale(button(2, -3)), emptyList())
        assertEquals(0L, checked.debit)
        assertEquals(600L, checked.returned)
        assertEquals(20.0, checked.pending.newBalance, 0.0)
    }
    @Test fun pendingRefundDoesNotFundNextSale() {
        val low = snapshot.copy(customers = listOf(snapshot.customers.single().copy(balance = 0)))
        rejected { validateOffline(low, sale(button(1, 1)), listOf(prior(0, 1000))) }
    }
    @Test fun existingDebitsReserveBalance() {
        rejected { validateOffline(snapshot, sale(button(1, 3)), listOf(prior())) }
    }
    @Test fun limitsAggregateByCustomerAndTill() {
        val rich = snapshot.copy(customers = listOf(snapshot.customers.single().copy(balance = 10000)))
        rejected { validateOffline(rich, sale(button(1, 4)), listOf(prior(1500))) }
        val strict = rich.copy(rules = rich.rules.copy(saleTill = 1500))
        rejected { validateOffline(strict, sale(button(1, 2)), listOf(prior(1000).copy(tagUid = "other"))) }
    }
    @Test fun unknownWristbandAndOtherPaymentsRejected() {
        rejected { validateOffline(snapshot, sale(button(1, 1)).copy(customerTagUid = 99.toBigInteger()), emptyList()) }
        rejected { validateOffline(snapshot, sale(button(1, 1)).copy(paymentMethod = PaymentMethod.cash), emptyList()) }
        rejected { validateOffline(snapshot, sale(button(1, 1)).copy(usedVouchers = 1.toBigInteger()), emptyList()) }
    }
    @Test fun nonReturnableAndAgeRestrictedProductsRejected() {
        rejected { validateOffline(snapshot, sale(button(1, -1)), emptyList()) }
        val restricted = snapshot.copy(customers = listOf(snapshot.customers.single().copy(restriction = ProductRestriction.under_16)),
            buttons = listOf(OfflineButton(1, "Drink", listOf(product.copy(restrictions = listOf(ProductRestriction.under_16))))))
        rejected { validateOffline(restricted, sale(button(1, 1)), emptyList()) }
    }
    @Test fun freePricesAndUnclearPriorSalesRejected() {
        rejected { validateOffline(snapshot, sale(button(1, 1)), listOf(prior(state = "waiting"))) }
    }
    @Test fun freePriceAndTipAreRecordedAsOneExactCentProduct() {
        val checked = validateOffline(snapshot, sale(Button(3.toBigInteger(), price = 12.34)), emptyList())
        assertEquals(1234L, checked.debit)
        assertEquals(1, checked.pending.lineItems.size)
        assertEquals(1.toBigInteger(), checked.pending.lineItems.single().quantity)
        assertEquals(12.34, checked.pending.lineItems.single().productPrice, 0.0)
        assertEquals(12.34, checked.pending.totalPrice, 0.0)
        val free = validateOffline(snapshot, sale(Button(3.toBigInteger(), price = 0.0)), emptyList())
        assertEquals(0L, free.debit)
    }
    @Test fun freePriceCanBeCombinedWithFixedItemsAndOtherFreePriceButtons() {
        val beerAndTip = validateOffline(snapshot,
            sale(button(1, 1), Button(3.toBigInteger(), price = 12.34)), emptyList())
        assertEquals(1734L, beerAndTip.debit)
        assertEquals(2, beerAndTip.pending.lineItems.size)
        assertEquals(17.34, beerAndTip.pending.totalPrice, 0.0)

        val secondFreeProduct = freeProduct.copy(name = "Second tip", id = 4.toBigInteger())
        val multipleTips = snapshot.copy(buttons = snapshot.buttons + OfflineButton(4, "Second tip", listOf(secondFreeProduct)))
        val tips = validateOffline(multipleTips, sale(
            Button(3.toBigInteger(), price = 3.00), Button(4.toBigInteger(), price = 2.50)), emptyList())
        assertEquals(550L, tips.debit)
        assertEquals(2, tips.pending.lineItems.size)
    }
    @Test fun freePriceUsesTransactionCustomerTillAndBalanceLimits() {
        val rich = snapshot.copy(customers = listOf(snapshot.customers.single().copy(balance = 10000)))
        val broadCustomerLimit = rich.copy(rules = rich.rules.copy(saleCustomer = 10000))
        rejected { validateOffline(broadCustomerLimit, sale(Button(3.toBigInteger(), price = 72.01)), emptyList()) }
        rejected { validateOffline(rich, sale(Button(3.toBigInteger(), price = 20.01)), emptyList()) }
        rejected { validateOffline(rich, sale(button(1, 1), Button(3.toBigInteger(), price = 15.01)), emptyList()) }
        rejected { validateOffline(broadCustomerLimit.copy(customers = listOf(snapshot.customers.single())),
            sale(Button(3.toBigInteger(), price = 20.01)), emptyList()) }
        rejected { validateOffline(broadCustomerLimit, sale(button(1, 1), Button(3.toBigInteger(), price = 67.01)), emptyList()) }
        rejected { validateOffline(rich.copy(rules = rich.rules.copy(saleTill = 1000)),
            sale(Button(3.toBigInteger(), price = 10.01)), emptyList()) }
    }
    @Test fun freePriceRejectsNegativeFractionalOverridesAndFreePriceBundles() {
        rejected { validateOffline(snapshot, sale(Button(3.toBigInteger(), price = -0.01)), emptyList()) }
        rejected { validateOffline(snapshot, sale(Button(3.toBigInteger(), price = 1.001)), emptyList()) }
        rejected { validateOffline(snapshot, sale(Button(1.toBigInteger(), price = 1.0)), emptyList()) }
        rejected { validateOffline(snapshot, sale(Button(3.toBigInteger(), quantity = 1.toBigInteger(), price = 1.0)), emptyList()) }
        rejected { validateOffline(snapshot.copy(buttons = snapshot.buttons + OfflineButton(4, "Bundle", listOf(freeProduct, product))),
            sale(Button(4.toBigInteger(), price = 1.0)), emptyList()) }
    }
    @Test fun onlyTransportFailuresAllowOfflineAdmission() {
        assertTrue(isOfflineTransportFailure(de.stustapay.libssp.net.Response.Error.Request(throwable = java.io.IOException())))
        assertFalse(isOfflineTransportFailure(de.stustapay.libssp.net.Response.Error.Request(throwable = IllegalStateException())))
    }
    @Test fun delayedOnlineRejectionCannotEraseOfflineAdmission() {
        val accepted = prior().copy(result = "offline-receipt")
        val merged = reconcileJournalReply(accepted, "rejected", null, "Not enough funds", requestedOffline = false)
        assertEquals("offline", merged.state)
        assertEquals(1000L, merged.debitCents)
        assertEquals("offline-receipt", merged.result)
        assertEquals("queued", merged.transferState)
    }
    @Test fun delayedOnlineSuccessPreservesOfflineBudgetAndSettlesExactlyOnce() {
        val accepted = prior().copy(result = "offline-receipt")
        val merged = reconcileJournalReply(accepted, "booked", "server-receipt", null, requestedOffline = false, confirmedDebit = 2000)
        assertEquals("booked", merged.state)
        assertEquals(1000L, merged.debitCents)
        assertEquals(1000L, merged.saleCents)
        assertEquals("server-receipt", merged.result)
        assertEquals(merged, reconcileJournalReply(merged, "rejected", null, "late rejection", requestedOffline = false))
    }
}
