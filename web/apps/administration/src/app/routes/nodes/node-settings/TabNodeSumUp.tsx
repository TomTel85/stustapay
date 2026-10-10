import {
  NodeSumUpConnectionStatus,
  SumUpEnvironment,
  useConfigureSumupSandboxKeyMutation,
  useDeleteNodeSumupLinkMutation,
  useGetNodeSumupLinkStatusQuery,
} from "@/api";
import { useCurrentNode } from "@/hooks";
import { Alert, AlertTitle, Button, Divider, List, ListItem, ListItemText, Stack, TextField, Typography } from "@mui/material";
import { Loading } from "@stustapay/components";
import * as React from "react";
import { useTranslation } from "react-i18next";
import { toast } from "react-toastify";
import { buildSumupOauthUrl } from "../sumupOauth";

const ConnectionDetails: React.FC<{
  status: NodeSumUpConnectionStatus;
  onConnect?: () => void;
  onDisconnect: () => void;
  disconnecting: boolean;
}> = ({ status, onConnect, onDisconnect, disconnecting }) => {
  const { t } = useTranslation();
  return (
    <Stack spacing={1}>
      {status.connected ? (
        <Alert severity={status.environment === "sandbox" ? "warning" : "success"}>
          {t("settings.sumup.linkConnected")}
        </Alert>
      ) : (
        <Alert severity="info">{t("settings.sumup.linkNotConnected")}</Alert>
      )}
      <List dense>
        <ListItem>
          <ListItemText
            primary={t("settings.sumup.sumup_merchant_code")}
            secondary={status.merchant_code ?? t("settings.sumup.secretNotConfigured")}
          />
        </ListItem>
        <ListItem>
          <ListItemText
            primary={t("settings.sumup.merchantName")}
            secondary={status.merchant_name ?? t("settings.sumup.secretNotConfigured")}
          />
        </ListItem>
        <ListItem>
          <ListItemText
            primary={t("settings.sumup.linkedEventCount")}
            secondary={t("settings.sumup.linkedEventCountValue", { count: status.linked_event_count })}
          />
        </ListItem>
      </List>
      <Stack direction="row" spacing={2}>
        {onConnect && (
          <Button variant="contained" onClick={onConnect}>
            {status.connected ? t("settings.sumup.reconnect") : t("settings.sumup.connect")}
          </Button>
        )}
        <Button
          variant="outlined"
          color="secondary"
          onClick={onDisconnect}
          disabled={!status.connected || disconnecting}
        >
          {t("settings.sumup.disconnect")}
        </Button>
      </Stack>
    </Stack>
  );
};

export const TabNodeSumUp: React.FC = () => {
  const { t } = useTranslation();
  const { currentNode } = useCurrentNode();
  const liveQuery = useGetNodeSumupLinkStatusQuery({ nodeId: currentNode.id, environment: "live" });
  const sandboxQuery = useGetNodeSumupLinkStatusQuery({ nodeId: currentNode.id, environment: "sandbox" });
  const [deleteNodeSumupLink, deleteState] = useDeleteNodeSumupLinkMutation();
  const [configureSandboxKey, configureSandboxState] = useConfigureSumupSandboxKeyMutation();
  const [sandboxApiKey, setSandboxApiKey] = React.useState("");

  const handleLiveConnect = () => {
    const oauthClientId = liveQuery.data?.oauth_client_id ?? "";
    if (!liveQuery.data || oauthClientId.trim() === "") {
      toast.error(t("settings.sumup.oauthConfigMissing"));
      return;
    }
    window.location.href = buildSumupOauthUrl(currentNode.id, oauthClientId);
  };

  const handleDisconnect = (environment: SumUpEnvironment) => {
    deleteNodeSumupLink({ nodeId: currentNode.id, environment })
      .unwrap()
      .then(() => toast.success(t("settings.sumup.disconnectSuccess")))
      .catch((err) => {
        toast.error(t("settings.sumup.disconnectFailed", { reason: err?.data?.detail ?? err.error }));
      });
  };

  const handleSandboxConnect = () => {
    const apiKey = sandboxApiKey.trim();
    if (!apiKey) {
      toast.error(t("settings.sumup.sandboxKeyRequired"));
      return;
    }
    configureSandboxKey({
      nodeId: currentNode.id,
      sumUpApiKeyPayload: { api_key: apiKey },
    })
      .unwrap()
      .then(() => {
        setSandboxApiKey("");
        toast.success(t("settings.sumup.sandboxConnectSuccess"));
      })
      .catch((err) => {
        toast.error(t("settings.sumup.sandboxConnectFailed", { reason: err?.data?.detail ?? err.error }));
      });
  };

  if (liveQuery.isLoading || sandboxQuery.isLoading) {
    return <Loading />;
  }
  if (!liveQuery.data || !sandboxQuery.data || liveQuery.error || sandboxQuery.error) {
    return (
      <Alert severity="error">
        <AlertTitle>{t("settings.sumup.linkLoadErrorTitle")}</AlertTitle>
      </Alert>
    );
  }

  return (
    <Stack spacing={3}>
      {!liveQuery.data.oauth_configured && (
        <Alert severity="warning">{t("settings.sumup.oauthConfigMissing")}</Alert>
      )}
      {!liveQuery.data.affiliate_key_configured && (
        <Alert severity="info">{t("settings.sumup.affiliateKeyMissing")}</Alert>
      )}
      <Typography variant="h6">{t("settings.sumup.liveEnvironment")}</Typography>
      <ConnectionDetails
        status={liveQuery.data}
        onConnect={handleLiveConnect}
        onDisconnect={() => handleDisconnect("live")}
        disconnecting={deleteState.isLoading}
      />
      <Divider />
      <Typography variant="h6">{t("settings.sumup.sandboxEnvironment")}</Typography>
      <Alert severity="warning">{t("settings.sumup.sandboxNotice")}</Alert>
      <ConnectionDetails
        status={sandboxQuery.data}
        onDisconnect={() => handleDisconnect("sandbox")}
        disconnecting={deleteState.isLoading}
      />
      <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
        <TextField
          fullWidth
          type="password"
          label={t("settings.sumup.sandboxApiKey")}
          value={sandboxApiKey}
          onChange={(event) => setSandboxApiKey(event.target.value)}
          autoComplete="new-password"
        />
        <Button
          variant="contained"
          color="warning"
          onClick={handleSandboxConnect}
          disabled={configureSandboxState.isLoading}
        >
          {sandboxQuery.data.connected
            ? t("settings.sumup.replaceSandboxKey")
            : t("settings.sumup.connectSandbox")}
        </Button>
      </Stack>
    </Stack>
  );
};
