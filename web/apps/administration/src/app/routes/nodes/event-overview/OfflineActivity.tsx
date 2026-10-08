import { useDismissOfflineMutation, useOfflineDevicesQuery, useOfflineReportQuery, OfflineBookingStatus } from "@/api";
import { useOpenModal } from "@stustapay/modal-provider";
import { useCurrentNode, useCurrencyFormatter } from "@/hooks";
import {
  Alert,
  Card,
  CardContent,
  CircularProgress,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Typography,
  Button,
} from "@mui/material";
import * as React from "react";
import { useTranslation } from "react-i18next";
import { toast } from "react-toastify";

const formatDate = (value: string | null | undefined) =>
  value ? new Date(value).toLocaleString() : "—";

export const OfflineActivity: React.FC = () => {
  const { currentNode } = useCurrentNode();
  const { t } = useTranslation();
  const formatCurrency = useCurrencyFormatter();
  const openModal = useOpenModal();
  const [dismissOffline] = useDismissOfflineMutation();
  const { data: report, isLoading: reportLoading, isError: reportError } = useOfflineReportQuery({ nodeId: currentNode.id });
  const { data: devices, isLoading: devicesLoading, isError: devicesError } = useOfflineDevicesQuery({ nodeId: currentNode.id });

  const statusLabel = (status: OfflineBookingStatus) => {
    if (status === "booked") return t("settings.offline.statusBooked");
    if (status === "already_booked") return t("settings.offline.statusAlreadyBooked");
    if (status === "clarification_required") return t("settings.offline.clarification");
    if (status === "dismissed") return t("settings.offline.dismissed");
    return t("settings.offline.statusNotFound");
  };

  const confirmDismiss = (orderUuid: string) => {
    openModal({
      type: "confirm",
      title: t("settings.offline.dismissTitle"),
      content: t("settings.offline.dismissConfirm"),
      onConfirm: () => {
        dismissOffline({ nodeId: currentNode.id, orderUuid })
          .unwrap()
          .then(() => toast.success(t("settings.offline.dismissedSuccess")))
          .catch(() => toast.error(t("settings.offline.dismissFailed")));
      },
    });
  };

  if ((reportLoading || devicesLoading) && !report && !devices) return <CircularProgress />;

  return (
    <Stack spacing={2} sx={{ mt: 2 }}>
      <Typography variant="h6">{t("settings.offline.activityTitle")}</Typography>
      {(reportError || devicesError) && <Alert severity="error">{t("settings.offline.activityLoadFailed")}</Alert>}
      <Card>
        <CardContent>
          <Typography variant="subtitle1" gutterBottom>{t("settings.offline.deviceStatus")}</Typography>
          {devices?.length ? (
            <TableContainer sx={{ overflowX: "auto" }}><Table size="small" sx={{ minWidth: 480 }}>
              <TableHead><TableRow>
                <TableCell>{t("settings.offline.till")}</TableCell>
                <TableCell>{t("settings.offline.lastContact")}</TableCell>
                <TableCell>{t("settings.offline.preparationExpires")}</TableCell>
              </TableRow></TableHead>
              <TableBody>{devices.map((device) => (
                <TableRow key={`${device.terminal_id}-${device.snapshot_id}`}>
                  <TableCell>{device.till_id} (POS {device.terminal_id})</TableCell>
                  <TableCell>{formatDate(device.last_contact_at)}</TableCell>
                  <TableCell>{formatDate(device.valid_until)}</TableCell>
                </TableRow>
              ))}</TableBody>
            </Table></TableContainer>
          ) : <Typography color="text.secondary">{t("settings.offline.noDevices")}</Typography>}
        </CardContent>
      </Card>
      <Card>
        <CardContent>
          <Typography variant="subtitle1" gutterBottom>{t("settings.offline.importedSales")}</Typography>
          {report?.length ? (
            <TableContainer sx={{ overflowX: "auto" }}><Table size="small" sx={{ minWidth: 850 }}>
              <TableHead><TableRow>
                <TableCell>UUID</TableCell>
                <TableCell>{t("settings.offline.till")}</TableCell>
                <TableCell>{t("settings.offline.recordedAt")}</TableCell>
                <TableCell>{t("settings.offline.receivedAt")}</TableCell>
                <TableCell>{t("settings.offline.status")}</TableCell>
                <TableCell>{t("settings.offline.balanceAfter")}</TableCell>
                <TableCell>{t("settings.offline.order")}</TableCell>
                <TableCell />
              </TableRow></TableHead>
              <TableBody>{report.map((entry) => (
                <TableRow key={entry.uuid}>
                  <TableCell sx={{ fontFamily: "monospace", maxWidth: 160, overflowWrap: "anywhere" }}>{entry.uuid}</TableCell>
                  <TableCell>{entry.till_id} (POS {entry.terminal_id})</TableCell>
                  <TableCell>{formatDate(entry.recorded_at)}</TableCell>
                  <TableCell>{formatDate(entry.received_at)}</TableCell>
                  <TableCell>
                    <Stack spacing={0.5}>
                      <span>{statusLabel(entry.status)}</span>
                      {entry.message && <Typography variant="caption" color="text.secondary">{entry.message}</Typography>}
                    </Stack>
                  </TableCell>
                  <TableCell>{entry.new_balance == null ? "—" : formatCurrency(entry.new_balance)}</TableCell>
                  <TableCell>{entry.order_id ?? "—"}</TableCell>
                  <TableCell>
                    {entry.status === "clarification_required" && (
                      <Button size="small" color="warning" onClick={() => confirmDismiss(entry.uuid)}>
                        {t("settings.offline.dismissClarification")}
                      </Button>
                    )}
                  </TableCell>
                </TableRow>
              ))}</TableBody>
            </Table></TableContainer>
          ) : <Typography color="text.secondary">{t("settings.offline.noActivity")}</Typography>}
        </CardContent>
      </Card>
    </Stack>
  );
};
