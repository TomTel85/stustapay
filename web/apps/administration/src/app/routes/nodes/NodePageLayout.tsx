import { useNode } from "@/api";
import { useTreeForCurrentUser } from "@/api/nodes";
import { Dashboard as DashboardIcon, Settings as SettingsIcon } from "@mui/icons-material";
import { Alert, AlertTitle, Box, Link, Tab, Tabs } from "@mui/material";
import * as React from "react";
import { useTranslation } from "react-i18next";
import { Outlet, Link as RouterLink, useLocation, useParams } from "react-router-dom";
import { EventPageLayout } from "./EventPageLayout";

const getActiveTab = (nodeId: number, location: string) => {
  if (location.startsWith(`/node/${nodeId}/settings`)) {
    return `/node/${nodeId}/settings`;
  }
  return `/node/${nodeId}`;
};

export const NodePageLayout: React.FC = () => {
  const { t } = useTranslation();
  const location = useLocation();
  const { nodeId } = useParams();
  const { node } = useNode({ nodeId: Number(nodeId) });
  const tree = useTreeForCurrentUser();

  if (!nodeId || !node) {
    return (
      <Alert severity="warning">
        <AlertTitle>{t("nodes.unavailableTitle")}</AlertTitle>
        {t("nodes.unavailableDescription")}{" "}
        <Link component={RouterLink} to={`/node/${tree.id}`}>
          {t("nodes.returnToWorkspace")}
        </Link>
      </Alert>
    );
  }

  if (node.event != null) {
    return <EventPageLayout node={node} />;
  }
  const nodeUrl = `/node/${node.id}`;

  return (
    <Box>
      <Tabs
        sx={{ borderBottom: 1, borderColor: "divider" }}
        value={getActiveTab(node.id, location.pathname)}
        aria-label={t("portal.workspace")}
      >
        <Tab
          label={t("nodes.overview")}
          component={RouterLink}
          value={nodeUrl}
          icon={<DashboardIcon />}
          iconPosition="start"
          to={nodeUrl}
        />
        <Tab
          label={t("nodes.settings")}
          component={RouterLink}
          value={`${nodeUrl}/settings`}
          icon={<SettingsIcon />}
          iconPosition="start"
          to={`${nodeUrl}/settings`}
        />
      </Tabs>
      <Box sx={{ mt: 2 }}>
        <Outlet />
      </Box>
    </Box>
  );
};
