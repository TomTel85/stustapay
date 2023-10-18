import { useNode } from "@/api/nodes";
import { UserTagRoutes } from "@/app/routes";
import { Box, Tab, Tabs } from "@mui/material";
import { Loading } from "@stustapay/components";
import * as React from "react";
import { useTranslation } from "react-i18next";
import { Outlet, Link as RouterLink, useLocation, useParams } from "react-router-dom";

const getActiveTab = (location: string) => {
  return UserTagRoutes.list();
};

export const UserTagPageLayout: React.FC = () => {
  const { t } = useTranslation();
  const { nodeId } = useParams();
  const { node } = useNode({ nodeId: Number(nodeId) });
  const location = useLocation();

  if (!nodeId) {
    // TODO: return error page / redirect
    return null;
  }

  if (!node) {
    return <Loading />;
  }

  return (
    <Box>
      <Tabs
        value={getActiveTab(location.pathname)}
        sx={{ borderBottom: 1, borderColor: "divider" }}
        aria-label="User Tags"
      >
        <Tab label={t("userTag.find")} component={RouterLink} value={UserTagRoutes.list()} to={UserTagRoutes.list()} />
      </Tabs>
      <Box sx={{ mt: 2 }}>
        <Outlet />
      </Box>
    </Box>
  );
};
