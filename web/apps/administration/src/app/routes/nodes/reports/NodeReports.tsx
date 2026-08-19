import { useGenerateAccountingReportMutation, useGenerateRevenueReportMutation } from "@/api";
import { useCurrentEventSettings, useCurrentNode, useCurrentUserHasPrivilege } from "@/hooks";
import { AccountBalanceWallet, ReceiptLong } from "@mui/icons-material";
import { Alert, Button, Paper, Stack, Typography } from "@mui/material";
import { DateTime } from "luxon";
import * as React from "react";
import { useTranslation } from "react-i18next";
import { toast } from "react-toastify";

const safeFilePart = (value: string) =>
  value
    .normalize("NFKD")
    .replace(/[^a-zA-Z0-9-]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .toLowerCase();

const downloadBlobUrl = (url: string, filename: string) => {
  const link = document.createElement("a");
  try {
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
  } finally {
    link.remove();
    window.setTimeout(() => window.URL.revokeObjectURL(url), 100);
  }
};

export const NodeReports: React.FC = () => {
  const { t } = useTranslation();
  const { currentNode } = useCurrentNode();
  const { eventSettings } = useCurrentEventSettings();
  const canAdminNode = useCurrentUserHasPrivilege("node_administration");
  const canViewStats = useCurrentUserHasPrivilege("view_node_stats");
  const [generateRevenueReport, { isLoading: isRevenueReportGenerating }] = useGenerateRevenueReportMutation();
  const [generateAccountingReport, { isLoading: isAccountingReportGenerating }] = useGenerateAccountingReportMutation();

  const isInEventContext = currentNode.event != null || currentNode.event_node_id != null;
  const eventName = eventSettings.bon_title || currentNode.name || "event";
  const scopeName = currentNode.name || `node-${currentNode.id}`;
  const reportDate = DateTime.now().toISODate();
  const filenameSuffix = `${safeFilePart(eventName)}_${safeFilePart(scopeName)}_${reportDate}`;

  const downloadRevenueReport = async () => {
    try {
      const pdfUrl = await generateRevenueReport({ nodeId: currentNode.id }).unwrap();
      downloadBlobUrl(pdfUrl, `umsatzbericht_${filenameSuffix}.pdf`);
    } catch {
      toast.error(t("reports.revenueError"));
    }
  };

  const downloadAccountingReport = async () => {
    try {
      const pdfUrl = await generateAccountingReport({ nodeId: currentNode.id }).unwrap();
      downloadBlobUrl(pdfUrl, `finanzbericht_${filenameSuffix}.pdf`);
    } catch {
      toast.error(t("reports.accountingError"));
    }
  };

  if (!isInEventContext) {
    return <Alert severity="info">{t("reports.eventRequired")}</Alert>;
  }

  return (
    <Stack spacing={2}>
      <Typography variant="h4">{t("reports.title")}</Typography>
      <Typography color="text.secondary">{t("reports.description")}</Typography>

      {canAdminNode && (
        <Paper variant="outlined" sx={{ p: 2 }}>
          <Stack spacing={1.5} alignItems="flex-start">
            <Typography variant="h6">{t("reports.revenueTitle")}</Typography>
            <Typography color="text.secondary">{t("reports.revenueDescription")}</Typography>
            <Button
              variant="contained"
              startIcon={<ReceiptLong />}
              loading={isRevenueReportGenerating}
              loadingPosition="start"
              onClick={downloadRevenueReport}
            >
              {t("reports.downloadRevenue")}
            </Button>
          </Stack>
        </Paper>
      )}

      {(canAdminNode || canViewStats) && (
        <Paper variant="outlined" sx={{ p: 2 }}>
          <Stack spacing={1.5} alignItems="flex-start">
            <Typography variant="h6">{t("reports.accountingTitle")}</Typography>
            <Typography color="text.secondary">{t("reports.accountingDescription")}</Typography>
            <Button
              variant="contained"
              startIcon={<AccountBalanceWallet />}
              loading={isAccountingReportGenerating}
              loadingPosition="start"
              onClick={downloadAccountingReport}
            >
              {t("reports.downloadAccounting")}
            </Button>
          </Stack>
        </Paper>
      )}
    </Stack>
  );
};
