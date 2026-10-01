import {
  ReportDayMode,
  useGenerateAccountingReportMutation,
  useGenerateRevenueReportMutation,
  useGetAvailableDatesQuery,
} from "@/api";
import { useCurrentEventSettings, useCurrentNode, useCurrentUserHasPrivilege } from "@/hooks";
import { AccountBalanceWallet, ReceiptLong } from "@mui/icons-material";
import {
  Alert,
  Button,
  Checkbox,
  Chip,
  FormControl,
  FormHelperText,
  InputLabel,
  ListItemText,
  MenuItem,
  Paper,
  Select,
  Stack,
  TextField,
  ToggleButton,
  ToggleButtonGroup,
  Typography,
} from "@mui/material";
import { DateTime } from "luxon";
import * as React from "react";
import { useTranslation } from "react-i18next";
import { toast } from "react-toastify";

type DatePreset = "all" | "today" | "yesterday" | "last7" | "custom" | "month";

const REPORT_TIMEZONE = "Europe/Berlin";

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
  const [datePreset, setDatePreset] = React.useState<DatePreset>("all");
  const [selectedDates, setSelectedDates] = React.useState<string[]>([]);
  const [dayMode, setDayMode] = React.useState<ReportDayMode>("calendar_day");
  const [selectedMonth, setSelectedMonth] = React.useState("");
  const [additionalDate, setAdditionalDate] = React.useState("");

  const isInEventContext = currentNode.event != null || currentNode.event_node_id != null;
  const { data: availableDates } = useGetAvailableDatesQuery(
    { nodeId: currentNode.id, dayMode },
    { skip: !isInEventContext }
  );
  const eventName = eventSettings.bon_title || currentNode.name || "event";
  const scopeName = currentNode.name || `node-${currentNode.id}`;
  const reportDate = DateTime.now().toISODate();
  const filenameSuffix = `${safeFilePart(eventName)}_${safeFilePart(scopeName)}_${reportDate}`;

  const currentReportDate = React.useMemo(() => {
    const now = DateTime.now().setZone(REPORT_TIMEZONE);
    if (dayMode !== "event_day" || !eventSettings.daily_end_time) {
      return now.toISODate()!;
    }
    const [hour, minute, second] = eventSettings.daily_end_time.split(":").map(Number);
    const boundary = now.startOf("day").set({ hour, minute, second: second || 0 });
    return (now < boundary ? now.minus({ days: 1 }) : now).toISODate()!;
  }, [dayMode, eventSettings.daily_end_time]);

  const reportDates = React.useMemo(() => {
    if (datePreset === "all") return undefined;
    if (datePreset === "custom") return [...selectedDates].sort();
    if (datePreset === "month") {
      const month = DateTime.fromISO(`${selectedMonth}-01`, { zone: REPORT_TIMEZONE });
      return Array.from({ length: month.daysInMonth ?? 0 }, (_, index) =>
        month.plus({ days: index }).toFormat("yyyy-MM-dd")
      );
    }
    const current = DateTime.fromISO(currentReportDate, { zone: REPORT_TIMEZONE });
    if (datePreset === "today") return [current.toISODate()!];
    if (datePreset === "yesterday") return [current.minus({ days: 1 }).toISODate()!];
    return Array.from({ length: 7 }, (_, index) => current.minus({ days: 6 - index }).toISODate()!);
  }, [currentReportDate, datePreset, selectedDates, selectedMonth]);

  const selectableDates = [...new Set([...(availableDates ?? []), ...(reportDates ?? [])])].sort();

  const reportArgs = { nodeId: currentNode.id, selectedDates: reportDates, dayMode };

  const downloadRevenueReport = async () => {
    try {
      const pdfUrl = await generateRevenueReport(reportArgs).unwrap();
      downloadBlobUrl(pdfUrl, `umsatzbericht_${filenameSuffix}.pdf`);
    } catch {
      toast.error(t("reports.revenueError"));
    }
  };

  const downloadAccountingReport = async () => {
    try {
      const pdfUrl = await generateAccountingReport(reportArgs).unwrap();
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

      <Paper variant="outlined" sx={{ p: 2 }}>
        <Stack spacing={2}>
          <Typography variant="h6">{t("reports.periodTitle")}</Typography>
          <Stack direction={{ xs: "column", md: "row" }} spacing={2} alignItems={{ md: "flex-start" }}>
            <FormControl size="small" sx={{ minWidth: { xs: "100%", md: 320 } }}>
              <InputLabel id="report-date-select-label" shrink>
                {t("reports.selectDates")}
              </InputLabel>
              <Select
                labelId="report-date-select-label"
                multiple
                value={reportDates ?? []}
                label={t("reports.selectDates")}
                displayEmpty
                notched
                onChange={(event) => {
                  const values = [...(event.target.value as string[])].sort();
                  setSelectedDates(values);
                  setSelectedMonth("");
                  setDatePreset(values.length > 0 ? "custom" : "all");
                }}
                renderValue={(selected) => {
                  const values = selected as string[];
                  if (datePreset === "all") return <em>{t("reports.allDates")}</em>;
                  if (datePreset === "today") return <em>{t("reports.today")}</em>;
                  if (datePreset === "yesterday") return <em>{t("reports.yesterday")}</em>;
                  if (datePreset === "last7") return <em>{t("reports.last7Days")}</em>;
                  if (datePreset === "month") {
                    return DateTime.fromISO(`${selectedMonth}-01`).toLocaleString({ month: "long", year: "numeric" });
                  }
                  if (values.length === 1) return DateTime.fromISO(values[0]).toLocaleString(DateTime.DATE_MED);
                  return t("reports.selectedDatesCount", { count: values.length });
                }}
              >
                {selectableDates.length ? (
                  selectableDates.map((date) => (
                    <MenuItem key={date} value={date}>
                      <Checkbox checked={reportDates?.includes(date) ?? false} size="small" />
                      <ListItemText primary={DateTime.fromISO(date).toLocaleString(DateTime.DATE_MED)} />
                    </MenuItem>
                  ))
                ) : (
                  <MenuItem disabled>{t("reports.noDatesAvailable")}</MenuItem>
                )}
              </Select>
            </FormControl>

            <FormControl>
              <ToggleButtonGroup
                exclusive
                size="small"
                value={dayMode}
                aria-label={t("reports.dayMode")}
                onChange={(_event, value: ReportDayMode | null) => value && setDayMode(value)}
              >
                <ToggleButton value="calendar_day">{t("reports.calendarDay")}</ToggleButton>
                <ToggleButton value="event_day" disabled={!eventSettings.daily_end_time || datePreset === "month"}>
                  {t("reports.eventDay")}
                </ToggleButton>
              </ToggleButtonGroup>
              <FormHelperText>
                {dayMode === "event_day" && eventSettings.daily_end_time
                  ? t("reports.eventDayHint", { time: eventSettings.daily_end_time.slice(0, 5) })
                  : !eventSettings.daily_end_time
                    ? t("reports.eventDayUnavailable")
                    : t("reports.calendarDayHint")}
              </FormHelperText>
            </FormControl>
          </Stack>

          <Stack direction={{ xs: "column", md: "row" }} spacing={2} alignItems={{ md: "flex-start" }}>
            <TextField
              type="month"
              size="small"
              label={t("reports.selectMonth")}
              value={selectedMonth}
              slotProps={{ inputLabel: { shrink: true } }}
              helperText={t("reports.selectMonthHint")}
              onChange={(event) => {
                const month = event.target.value;
                setSelectedMonth(month);
                if (DateTime.fromISO(`${month}-01`).isValid) {
                  setDatePreset("month");
                  setSelectedDates([]);
                  setDayMode("calendar_day");
                } else if (datePreset === "month") {
                  setDatePreset("all");
                }
              }}
            />
            <TextField
              type="date"
              size="small"
              label={t("reports.additionalDate")}
              value={additionalDate}
              slotProps={{ inputLabel: { shrink: true } }}
              onChange={(event) => setAdditionalDate(event.target.value)}
            />
            <Button
              variant="outlined"
              disabled={!DateTime.fromISO(additionalDate).isValid}
              onClick={() => {
                setSelectedDates([...new Set([...(reportDates ?? []), additionalDate])].sort());
                setDatePreset("custom");
                setSelectedMonth("");
                setAdditionalDate("");
              }}
            >
              {t("reports.addDate")}
            </Button>
          </Stack>

          <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
            {(["all", "today", "yesterday", "last7"] as const).map((preset) => (
              <Chip
                key={preset}
                size="small"
                color={datePreset === preset ? "primary" : "default"}
                label={t(`reports.${preset === "all" ? "allDates" : preset === "last7" ? "last7Days" : preset}`)}
                onClick={() => {
                  setDatePreset(preset);
                  setSelectedDates([]);
                  setSelectedMonth("");
                }}
              />
            ))}
          </Stack>
        </Stack>
      </Paper>

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
