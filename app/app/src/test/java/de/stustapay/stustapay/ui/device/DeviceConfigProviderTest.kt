package de.stustapay.stustapay.ui.device

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class DeviceConfigProviderTest {
    @Test
    fun `sunmi d3 mini is not treated as handheld small screen`() {
        val config = DeviceConfigProvider.determineDeviceConfig(
            modelInput = "D3 Mini",
            manufacturerInput = "SUNMI",
        )

        assertTrue(config.isSunmiD3Mini)
        assertFalse(config.isSmallScreen)
        assertFalse(config.useCenteredDialog)
    }

    @Test
    fun `sunmi l2 stays on handheld layout`() {
        val config = DeviceConfigProvider.determineDeviceConfig(
            modelInput = "L2 PRO",
            manufacturerInput = "SUNMI",
        )

        assertFalse(config.isSunmiD3Mini)
        assertTrue(config.isSmallScreen)
        assertTrue(config.useCenteredDialog)
    }
}
