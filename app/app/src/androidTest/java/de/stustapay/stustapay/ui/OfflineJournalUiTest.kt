package de.stustapay.stustapay.ui

import androidx.compose.material.MaterialTheme
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.ui.test.assertCountEquals
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.hasText
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import androidx.test.platform.app.InstrumentationRegistry
import de.stustapay.stustapay.R
import de.stustapay.stustapay.offline.JournalEntrySummary
import de.stustapay.stustapay.offline.OfflineStatus
import de.stustapay.stustapay.ui.common.operator.OfflineStatusIndicator
import org.junit.Assert.assertEquals
import org.junit.Rule
import org.junit.Test
import java.io.File
import java.io.FileOutputStream
import java.text.NumberFormat
import java.util.Currency
import java.util.Locale

class OfflineJournalUiTest {
    @get:Rule val compose = createComposeRule()

    @Test fun journalPagingControlsReportAndChangePages() {
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        var journalPage by mutableStateOf(0)
        val requestedPages = mutableListOf<Int>()
        compose.setContent {
            MaterialTheme {
                OfflineStatusIndicator(
                    OfflineStatus(connected = true, journalPage = journalPage, journalPageCount = 2),
                    onJournalPage = { page ->
                        requestedPages += page
                        journalPage = page
                    },
                )
            }
        }

        compose.onNodeWithText(context.getString(R.string.sale_status_online)).performClick()
        compose.onNodeWithText(context.getString(R.string.sale_journal_title)).performScrollTo().performClick()
        compose.onNodeWithText(context.getString(R.string.sale_journal_page, 1, 2)).assertIsDisplayed()
        compose.onNodeWithText(context.getString(R.string.sale_journal_next)).performClick()
        compose.onNodeWithText(context.getString(R.string.sale_journal_page, 2, 2)).assertIsDisplayed()
        compose.onNodeWithText(context.getString(R.string.sale_journal_previous)).performClick()

        compose.runOnIdle { assertEquals(listOf(1, 0), requestedPages) }
    }

    @Test fun journalSeparatesLocalAcceptanceTransferAndFinancialResolution() {
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        val rows = listOf(
            entry("local-queued", "offline", "queued"),
            entry("local-sending", "offline", "sending"),
            entry("confirmed-sale", "booked", "confirmed"),
            entry("review-sale", "clarification", "blocked", "Server reconciliation needs review"),
            entry("dismissed-sale", "dismissed", "confirmed"),
            entry("rejected-sale", "rejected", "confirmed"),
        )
        var synchronizationRequests = 0
        compose.setContent {
            MaterialTheme {
                OfflineStatusIndicator(
                    OfflineStatus(
                        offlineMode = true,
                        connected = false,
                        preparationUsable = true,
                        pendingSales = 3,
                        journalEntries = rows,
                    ),
                    onSynchronize = { synchronizationRequests++ },
                )
            }
        }

        compose.onNodeWithText(context.getString(R.string.sale_status_offline)).performClick()
        compose.waitForIdle()
        saveScreenshot("autonomous-status.png")
        compose.onNodeWithText(context.getString(R.string.sale_journal_title)).performScrollTo().performClick()

        compose.waitForIdle()
        saveScreenshot("autonomous-journal.png")

        val amount = NumberFormat.getCurrencyInstance(Locale.getDefault()).apply { currency = Currency.getInstance("EUR") }.format(12.5)
        compose.onAllNodesWithText(amount).assertCountEquals(rows.size)
        compose.onAllNodesWithText("2026-10-08T12:00:00Z").assertCountEquals(rows.size)
        rows.forEach { row -> compose.onNodeWithText(row.uuid).performScrollTo().assertIsDisplayed() }
        compose.onAllNodesWithText(context.getString(R.string.sale_journal_local_accepted)).assertCountEquals(2)
        compose.onAllNodesWithText(context.getString(R.string.sale_journal_transfer_pending)).assertCountEquals(2)
        listOf(
            R.string.sale_journal_confirmed,
            R.string.sale_journal_review,
            R.string.sale_journal_dismissed,
            R.string.sale_journal_rejected,
        ).forEach { label -> compose.onNodeWithText(context.getString(label)).performScrollTo().assertIsDisplayed() }
        compose.onNodeWithText("Server reconciliation needs review").performScrollTo().assertIsDisplayed()
        compose.onAllNodes(hasText("Delete", substring = true) or hasText("Löschen", substring = true) or hasText("Verwijderen", substring = true))
            .assertCountEquals(0)
        compose.onNodeWithText(context.getString(R.string.sale_synchronize_prepare)).performClick()
        compose.runOnIdle { assertEquals(1, synchronizationRequests) }
        // Retrying leaves the same journal identities intact; it cannot generate a replacement sale.
        rows.forEach { row -> compose.onNodeWithText(row.uuid).performScrollTo().assertIsDisplayed() }
    }

    private fun entry(uuid: String, state: String, transfer: String, message: String? = null) = JournalEntrySummary(
        uuid = uuid,
        amountCents = 1250,
        recordedAt = "2026-10-08T12:00:00Z",
        state = state,
        transferState = transfer,
        message = message,
    )

    private fun saveScreenshot(fileName: String) {
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        val bitmap = instrumentation.uiAutomation.takeScreenshot() ?: return
        val file = File(instrumentation.targetContext.cacheDir, fileName)
        FileOutputStream(file).use { stream -> bitmap.compress(android.graphics.Bitmap.CompressFormat.PNG, 100, stream) }
        bitmap.recycle()
    }
}
