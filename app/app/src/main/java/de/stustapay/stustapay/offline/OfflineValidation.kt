package de.stustapay.stustapay.offline

import com.ionspin.kotlin.bignum.integer.toBigInteger
import de.stustapay.api.models.*
import java.math.BigDecimal

internal fun cents(value: Double): Long = BigDecimal.valueOf(value).movePointRight(2).longValueExact()
private fun exactCents(value: Double, message: String): Long {
    require(value.isFinite()) { message }
    return try {
        cents(value)
    } catch (_: ArithmeticException) {
        throw IllegalArgumentException(message)
    }
}
internal data class OfflineChecked(val pending: PendingSale, val debit: Long, val positive: Long, val returned: Long)

/** Pure validation: no network, floating point money accumulation, or pending refund credit. */
internal fun validateOffline(snapshot: PreparedOfflineSnapshot, sale: NewSale, history: List<JournalSale>): OfflineChecked {
    require(history.none { it.state == "waiting" }) { "Offline: an earlier sale needs server confirmation" }
    require(sale.paymentMethod == PaymentMethod.tag) { "Offline: only wristband payments are supported" }
    require(sale.usedVouchers == null || sale.usedVouchers == 0.toBigInteger()) { "Offline: vouchers are unavailable" }
    val customer = snapshot.customers.singleOrNull { it.tagUid == sale.customerTagUid }
        ?: error("Offline: unknown wristband")
    require(sale.buttons.isNotEmpty()) { "Offline: empty sale" }
    val lines = sale.buttons.flatMap { selected ->
        val button = snapshot.buttons.singleOrNull { it.id.toBigInteger() == selected.tillButtonId }
            ?: error("Offline: unknown button")
        require(button.products.isNotEmpty()) { "Offline: empty button" }
        val customPrice = selected.price
        val quantity = if (customPrice != null) {
            require(selected.quantity == null) { "Offline: price and quantity cannot be combined" }
            require(button.products.size == 1) { "Offline: free-price bundles are unsupported" }
            val product = button.products.single()
            require(!product.fixedPrice && product.type == ProductType.user_defined && !product.isReturnable) {
                "Offline: unsupported free-price product"
            }
            val amountCents = exactCents(customPrice, "Offline: price must be finite exact cents")
            require(amountCents >= 0) { "Offline: negative price" }
            1.toBigInteger()
        } else {
            val fixedQuantity = selected.quantity ?: error("Offline: quantity is required")
            require(fixedQuantity != 0.toBigInteger()) { "Offline: zero quantity" }
            fixedQuantity
        }
        button.products.map { product ->
            if (customPrice == null) {
                require(product.fixedPrice && product.type == ProductType.user_defined) { "Offline: unsupported product" }
            }
            require(quantity > 0.toBigInteger() || product.isReturnable) { "Offline: product cannot be returned" }
            require(customer.restriction == null || customer.restriction !in product.restrictions) { "Offline: age restriction" }
            val price = customPrice ?: product.price ?: error("Offline: missing price")
            val priceCents = exactCents(price, "Offline: invalid product price")
            require(priceCents >= 0) { "Offline: invalid product price" }
            val count = quantity.toString().toLong()
            val total = Math.multiplyExact(priceCents, count)
            PendingLineItem(quantity, product, price, product.taxRateId, product.taxName, product.taxRate, total / 100.0)
        }
    }
    val positive = lines.filter { it.totalPrice > 0 }.fold(0L) { sum, line -> Math.addExact(sum, cents(line.totalPrice)) }
    val returned = lines.filter { it.totalPrice < 0 }.fold(0L) { sum, line -> Math.addExact(sum, -cents(line.totalPrice)) }
    val net = Math.subtractExact(positive, returned)
    val period = history.filter { it.snapshotId == snapshot.id.toString() && it.state !in setOf("rejected", "local_rejected") }
    val offline = period.filter { it.offline }
    val own = offline.filter { it.tagUid == customer.tagUid.toString() }
    val rules = snapshot.rules
    require(positive <= rules.saleTransaction && returned <= rules.returnTransaction) { "Offline: transaction limit" }
    require(positive + own.sumOf { it.saleCents } <= rules.saleCustomer && returned + own.sumOf { it.returnCents } <= rules.returnCustomer) { "Offline: wristband limit" }
    require(positive + offline.sumOf { it.saleCents } <= rules.saleTill && returned + offline.sumOf { it.returnCents } <= rules.returnTill) { "Offline: till limit" }
    val reserved = period.filter { it.tagUid == customer.tagUid.toString() }.sumOf { it.debitCents }
    val balance = (customer.balance - reserved).coerceAtLeast(0)
    require(net.coerceAtLeast(0) <= balance) { "Offline: insufficient estimated balance" }
    val pending = PendingSale(sale.uuid, balance / 100.0, (balance - net.coerceAtLeast(0)) / 100.0,
        0.toBigInteger(), 0.toBigInteger(), customer.accountId.toBigInteger(), PaymentMethod.tag,
        lines, sale.buttons, 0.toBigInteger(), lines.sumOf { it.quantity.toString().toLong() }.toBigInteger(), net / 100.0)
    return OfflineChecked(pending, net.coerceAtLeast(0), positive, returned)
}
