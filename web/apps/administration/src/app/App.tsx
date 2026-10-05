import { fetchConfig } from "@/api/common";
import { BrandLogo, logoSrc } from "@/components/BrandLogo";
import { useAppSelector } from "@/store";
import { selectTheme } from "@/store/uiSlice";
import { Box, CssBaseline, PaletteMode, ThemeProvider, Typography, useMediaQuery } from "@mui/material";
import { Loading, MaintenancePage } from "@stustapay/components";
import * as React from "react";
import { useTranslation } from "react-i18next";
import { ToastContainer } from "react-toastify";
import { UnauthenticatedLayout } from "./layout/UnauthenticatedLayout";
import { Router } from "./Router";
import { createAdministrationTheme } from "./theme";

export function App() {
  const { t } = useTranslation();
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState(false);
  const darkModeSystem = useMediaQuery("(prefers-color-scheme: dark)");
  const themeModeStore = useAppSelector(selectTheme);

  const themeMode: PaletteMode = themeModeStore === "browser" ? (darkModeSystem ? "dark" : "light") : themeModeStore;

  const theme = React.useMemo(() => createAdministrationTheme(themeMode), [themeMode]);

  React.useEffect(() => {
    const init = async () => {
      await fetchConfig();
    };
    init()
      .then(() => {
        setLoading(false);
      })
      .catch(() => {
        setError(true);
        setLoading(false);
      });
  }, []);

  if (error) {
    return (
      <ThemeProvider theme={theme}>
        <CssBaseline />
        <UnauthenticatedLayout
          toolbar={
            <Box sx={{ display: "flex", alignItems: "center", gap: 1.5, flexGrow: 1, minWidth: 0 }}>
              <BrandLogo />
              <Typography variant="h6" noWrap>
                {t("TeamFestlichPay")}
              </Typography>
            </Box>
          }
        >
          <MaintenancePage
            brandName={t("errorPage.brand")}
            title={t("errorPage.maintenance")}
            message={t("errorPage.currentlyUnavailable")}
            logoSrc={logoSrc}
          />
        </UnauthenticatedLayout>
      </ThemeProvider>
    );
  }

  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <ToastContainer position="top-right" autoClose={4000} pauseOnFocusLoss={false} theme={themeMode} />
      {loading ? <Loading /> : <Router />}
    </ThemeProvider>
  );
}
