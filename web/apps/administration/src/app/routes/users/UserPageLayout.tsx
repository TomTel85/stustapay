import { useNode } from "@/api/nodes";
import { CashierRoutes, UserRoleRoutes, UserRoutes, UserToRoleRoutes } from "@/app/routes";
import { Person as PersonIcon } from "@mui/icons-material";
import { Box, Tab, Tabs } from "@mui/material";
import { Loading } from "@stustapay/components";
import * as React from "react";
import { useTranslation } from "react-i18next";
import { Outlet, Link as RouterLink, useLocation, useParams } from "react-router-dom";

const getActiveTab = (location: string, nodeId: number, showCashiers: boolean) => {
  if (showCashiers && location.startsWith(CashierRoutes.list(nodeId))) {
    return CashierRoutes.list(nodeId);
  }
  if (location.startsWith(UserToRoleRoutes.list(nodeId))) {
    return UserToRoleRoutes.list(nodeId);
  }
  if (location.startsWith(UserRoleRoutes.list(nodeId))) {
    return UserRoleRoutes.list(nodeId);
  }
  return UserRoutes.list(nodeId);
};

export const UserPageLayout: React.FC = () => {
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

  const showCashiers =
    node.event != null &&
    node.privileges_at_node.includes("node_administration") &&
    (!node.computed_forbidden_objects_at_node.includes("user") ||
      !node.computed_forbidden_objects_at_node.includes("user_role"));

  return (
    <Box sx={{ minWidth: 0 }}>
      <Tabs
        value={getActiveTab(location.pathname, node.id, showCashiers)}
        variant="scrollable"
        scrollButtons="auto"
        allowScrollButtonsMobile
        sx={{ borderBottom: 1, borderColor: "divider" }}
        aria-label={t("users")}
      >
        <Tab
          label={t("user.users")}
          component={RouterLink}
          icon={<PersonIcon />}
          iconPosition="start"
          value={UserRoutes.list(node.id)}
          to={UserRoutes.list(node.id)}
        />
        {!node.computed_forbidden_objects_at_node.includes("user_role") && (
          <Tab
            label={t("user.roles")}
            component={RouterLink}
            value={UserRoleRoutes.list(node.id)}
            to={UserRoleRoutes.list(node.id)}
          />
        )}
        <Tab
          label={t("userToRoles")}
          component={RouterLink}
          value={UserToRoleRoutes.list(node.id)}
          to={UserToRoleRoutes.list(node.id)}
        />
        {showCashiers && (
          <Tab
            label={t("cashiers")}
            component={RouterLink}
            value={CashierRoutes.list(node.id)}
            to={CashierRoutes.list(node.id)}
          />
        )}
      </Tabs>
      <Box sx={{ mt: 2 }}>
        <Outlet />
      </Box>
    </Box>
  );
};
