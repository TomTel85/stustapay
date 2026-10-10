import { useDismissOfflineMutation, useOfflineDevicesQuery, useOfflineReportQuery, OfflineBookingStatus } from "@/api";
import { useOpenModal } from "@stustapay/modal-provider";
import { useCurrentNode, useCurrencyFormatter } from "@/hooks";
import {
  Alert,
  Accordion,
  AccordionDetails,
  AccordionSummary,
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
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
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
  const queryOptions = { pollingInterval: 10_000, skipPollingIfUnfocused: true };
  const { data: report, isLoading: reportLoading, isError: reportError } = useOfflineReportQuery(
    { nodeId: currentNode.id },
    queryOptions,
  );
  const { data: devices, isLoading: devicesLoading, isError: devicesError } = useOfflineDevicesQuery(
    { nodeId: currentNode.id },
    queryOptions,
  );
  const accordionId = React.useId();
  const devicesHeadingId = `${accordionId}-devices-heading`;
  const devicesPanelId = `${accordionId}-devices-panel`;
  const salesHeadingId = `${accordionId}-sales-heading`;
  const salesPanelId = `${accordionId}-sales-panel`;

  const statusLabel = (status: OfflineBookingStatus) => {
    if (status === "booked") return t("settings.offline.statusBooked");
    if (status === "already_booked") return t("settings.offline.statusAlreadyBooked");
    if (status === "clarification_required") return t("settings.offline.clarification");
    if (status === "retry_required") return t("settings.offline.retryRequired");
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
      <Accordion disableGutters elevation={1} sx={{ borderRadius: 1, overflow: "hidden", "&:before": { display: "none" } }}>
        <AccordionSummary
          expandIcon={<ExpandMoreIcon />}
          id={devicesHeadingId}
          aria-controls={devicesPanelId}
        >
          <Typography variant="subtitle1" component="h2">{t("settings.offline.deviceStatus")}</Typography>
        </AccordionSummary>
        <AccordionDetails id={devicesPanelId} aria-labelledby={devicesHeadingId} sx={{ p: 2 }}>
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
        </AccordionDetails>
      </Accordion>
      <Accordion disableGutters elevation={1} sx={{ borderRadius: 1, overflow: "hidden", "&:before": { display: "none" } }}>
        <AccordionSummary
          expandIcon={<ExpandMoreIcon />}
          id={salesHeadingId}
          aria-controls={salesPanelId}
        >
          <Typography variant="subtitle1" component="h2">{t("settings.offline.importedSales")}</Typography>
        </AccordionSummary>
        <AccordionDetails id={salesPanelId} aria-labelledby={salesHeadingId} sx={{ p: 2 }}>
          {report?.length ? (
            <TableContainer sx={{ overflowX: "auto" }}><Table size="small" sx={{ minWidth: 1100 }}>
              <TableHead><TableRow>
                <TableCell>UUID</TableCell>
                <TableCell>{t("settings.offline.till")}</TableCell>
                <TableCell>{t("settings.offline.recordedAt")}</TableCell>
                <TableCell>{t("settings.offline.receivedAt")}</TableCell>
                <TableCell>{t("settings.offline.status")}</TableCell>
                <TableCell>{t("settings.offline.balanceAfter")}</TableCell>
                <TableCell>{t("settings.offline.amount")}</TableCell>
                <TableCell>{t("settings.offline.customer")}</TableCell>
                <TableCell>{t("settings.offline.buttons")}</TableCell>
                <TableCell>{t("settings.offline.order")}</TableCell>
                <TableCell />
              </TableRow></TableHead>
              <TableBody>{report.map((entry, rowIndex) => {
                const lineItems = entry.line_items;
                const needsAttention = entry.status === "retry_required" || entry.status === "clarification_required";
                return (
                <TableRow key={`${entry.uuid}-${entry.received_at}-${rowIndex}`}>
                  <TableCell sx={{ fontFamily: "monospace", maxWidth: 160, overflowWrap: "anywhere" }}>{entry.uuid}</TableCell>
                  <TableCell>{entry.till_id} (POS {entry.terminal_id})</TableCell>
                  <TableCell>{formatDate(entry.recorded_at)}</TableCell>
                  <TableCell>{formatDate(entry.received_at)}</TableCell>
                  <TableCell>
                    <Stack spacing={0.5}>
                      <span>{statusLabel(entry.status)}</span>
                      {entry.message && <Typography variant="caption" color="text.secondary">{entry.message}</Typography>}
                      {entry.attempt_count != null && entry.attempt_count > 0 && (
                        <Typography variant="caption" color="text.secondary">
                          {t("settings.offline.retryAttempts", { count: entry.attempt_count })}
                        </Typography>
                      )}
                      {entry.last_attempt_at && (
                        <Typography variant="caption" color="text.secondary">
                          {t("settings.offline.lastRetryAt", { time: formatDate(entry.last_attempt_at) })}
                        </Typography>
                      )}
                    </Stack>
                  </TableCell>
                  <TableCell>{entry.new_balance == null ? "—" : formatCurrency(entry.new_balance)}</TableCell>
                  <TableCell>{entry.amount_cents == null ? "—" : formatCurrency(entry.amount_cents / 100)}</TableCell>
                  <TableCell>
                    {needsAttention ? (
                      <Stack spacing={0.5}>
                        <span>{t("settings.offline.customerTagUid", { uid: entry.customer_tag_uid ?? "—" })}</span>
                        <span>{t("settings.offline.customerAccount", { account: entry.customer_account_id ?? "—" })}</span>
                      </Stack>
                    ) : "—"}
                  </TableCell>
                  <TableCell>
                    {needsAttention
                      ? lineItems?.length
                        ? lineItems.map((lineItem) => t("settings.offline.salePosition", {
                            name: lineItem.product.name,
                            quantity: lineItem.quantity,
                            price: formatCurrency(lineItem.product_price),
                          })).join(", ")
                        : entry.buttons?.map((button) => {
                          const label = t("settings.offline.saleButton", { id: button.till_button_id });
                          if (button.quantity != null) return `${label} × ${button.quantity}`;
                          if (button.price != null) return `${label} (${formatCurrency(button.price)})`;
                          return label;
                        }).join(", ") || "—"
                      : "—"}
                  </TableCell>
                  <TableCell>{entry.order_id ?? "—"}</TableCell>
                  <TableCell>
                    {entry.status === "clarification_required" && (
                      <Button size="small" color="warning" onClick={() => confirmDismiss(entry.uuid)}>
                        {t("settings.offline.dismissClarification")}
                      </Button>
                    )}
                  </TableCell>
                </TableRow>
              );
              })}</TableBody>
            </Table></TableContainer>
          ) : <Typography color="text.secondary">{t("settings.offline.noActivity")}</Typography>}
        </AccordionDetails>
      </Accordion>
    </Stack>
  );
};
