package de.stustapay.stustapay.offline

internal const val JOURNAL_PAGE_SIZE = 50
internal const val JOURNAL_RETAINED_SETTLED = 1000
internal const val JOURNAL_RETENTION_DAYS = 7L
internal const val JOURNAL_STORAGE_RESERVE_BYTES = 64L * 1024 * 1024

internal class JournalStorageUnavailable(message: String) : IllegalStateException(message)
