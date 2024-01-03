package de.stustapay.stustapay.ui.root

import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.ui.res.stringResource
import de.stustapay.stustapay.R
import de.stustapay.stustapay.model.Access


val startpageItems = listOf(
    StartpageItem(
        icon = Icons.Filled.Face,
        label = R.string.root_item_ticket,
        navDestination = RootNavDests.ticket,
        canAccess = { u, t -> Access.canSellTicket(t, u) }
    ),
    StartpageItem(
        icon = Icons.Filled.ShoppingCart,
        label = R.string.root_item_sale,
        navDestination = RootNavDests.sale,
        canAccess = { u, t -> Access.canSell(u, t) }
    ),
    StartpageItem(
        icon = Icons.Filled.KeyboardArrowUp,
        label = R.string.root_item_topup,
        navDestination = RootNavDests.topup,
        canAccess = { u, t -> Access.canTopUp(t, u) }
    ),
    StartpageItem(
        icon = Icons.Filled.Info,
        label = R.string.customer_title,
        navDestination = RootNavDests.status,
        canAccess = { _, _ -> true }
    ),
    StartpageItem(
        icon = Icons.Filled.List,
        label = R.string.history_title,
        navDestination = RootNavDests.history,
        canAccess = { u, t -> Access.canSell(u, t) }
    ),
    StartpageItem(
        icon = Icons.Filled.Favorite,
        label = R.string.root_item_rewards,
        navDestination = RootNavDests.rewards,
        canAccess = { u, _ -> Access.canGiveVouchers(u) || Access.canGiveFreeTickets(u) }
    ),
    StartpageItem(
        icon = Icons.Filled.ThumbUp,
        label = R.string.management_title,
        navDestination = RootNavDests.cashierManagement,
        canAccess = { u, _ -> Access.canManageCashiers(u) or Access.canHackTheSystem(u)}
    ),
    StartpageItem(
        icon = Icons.Filled.Info,
        label = R.string.cashier_title,
        navDestination = RootNavDests.cashierStatus,
        canAccess = { u, t -> Access.canManageCashiers(u) or t.allow_cash_out or t.allow_top_up or t.allow_ticket_sale }
    )
)