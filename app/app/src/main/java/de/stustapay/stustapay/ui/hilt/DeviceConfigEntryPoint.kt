package de.stustapay.stustapay.ui.hilt

import dagger.hilt.EntryPoint
import dagger.hilt.InstallIn
import dagger.hilt.components.SingletonComponent
import de.stustapay.stustapay.ui.device.DeviceConfigProvider

/**
 * Hilt EntryPoint to access DeviceConfigProvider in Composables
 */
@EntryPoint
@InstallIn(SingletonComponent::class)
interface DeviceConfigEntryPoint {
    fun deviceConfigProvider(): DeviceConfigProvider
} 