import { config } from "@/api/common";
import { BrandLogo } from "@/components/BrandLogo";
import { selectIsAuthenticated, useAppSelector } from "@/store";
import { Button, CircularProgress, Typography } from "@mui/material";
import { TestModeDisclaimer } from "@stustapay/components";
import * as React from "react";
import { useTranslation } from "react-i18next";
import { Navigate, Outlet, Link as RouterLink, useSearchParams } from "react-router-dom";
import { UnauthenticatedLayout } from "./UnauthenticatedLayout";

export const UnauthenticatedRoot: React.FC = () => {
  const { t } = useTranslation();
  const authenticated = useAppSelector(selectIsAuthenticated);

  const [query] = useSearchParams();

  if (authenticated) {
    const next = query.get("next");
    const redirectUrl = next != null ? next : "/";
    return <Navigate to={redirectUrl} />;
  }

  return (
    <UnauthenticatedLayout
      toolbar={
        <>
          <Typography variant="h6" component="div" sx={{ flexGrow: 1, minWidth: 0 }}>
            <RouterLink
              to="/"
              style={{ textDecoration: "none", color: "inherit", display: "flex", alignItems: "center", gap: 12 }}
            >
              <BrandLogo />
              <Typography variant="h6" component="span" noWrap>
                {t("TeamFestlichPay")}
              </Typography>
            </RouterLink>
          </Typography>
          <Button component={RouterLink} color="inherit" to="/login">
            {t("login")}
          </Button>
        </>
      }
    >
      <TestModeDisclaimer testMode={config.testMode} testModeMessage={config.testModeMessage} />
      <React.Suspense fallback={<CircularProgress />}>
        <Outlet />
      </React.Suspense>
    </UnauthenticatedLayout>
  );
};
