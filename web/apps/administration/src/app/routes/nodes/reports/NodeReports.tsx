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
  const { t, i18n } = useTranslation();
  const { currentNode } = useCurrentNode();
  const { eventSettings } = useCurrentEventSettings();
  const canAdminNode = useCurrentUserHasPrivilege("node_administration");
  const canViewStats = useCurrentUserHasPrivilege("view_node_stats");
  const [generateRevenueReport, { isLoading: isRevenueReportGenerating }] = useGenerateRevenueReportMutation();
  const [generateAccountingReport, { isLoading: isAccountingReportGenerating }] = useGenerateAccountingReportMutation();
  const [datePreset, setDatePreset] = React.useState<DatePreset>("all");
  const [selectedDates, setSelectedDates] = React.useState<string[]>([]);
  const [dayMode, setDayMode] = React.useState<ReportDayMode>("calendar_day");
  const [selectedMonth, setSelectedMonth] = React.useState(DateTime.now().setZone(REPORT_TIMEZONE).month);
  const [selectedYear, setSelectedYear] = React.useState(String(DateTime.now().setZone(REPORT_TIMEZONE).year));
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
  const periodMode = datePreset === "all" ? "all" : datePreset === "month" ? "month" : "days";
  const validYear = /^\d{4}$/.test(selectedYear) && Number(selectedYear) >= 1970 && Number(selectedYear) < 4000;

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
      if (!validYear) return [];
      const month = DateTime.fromObject(
        { year: Number(selectedYear), month: selectedMonth, day: 1 },
        { zone: REPORT_TIMEZONE }
      );
      return Array.from({ length: month.daysInMonth ?? 0 }, (_, index) =>
        month.plus({ days: index }).toFormat("yyyy-MM-dd")
      );
    }
    const current = DateTime.fromISO(currentReportDate, { zone: REPORT_TIMEZONE });
    if (datePreset === "today") return [current.toISODate()!];
    if (datePreset === "yesterday") return [current.minus({ days: 1 }).toISODate()!];
    return Array.from({ length: 7 }, (_, index) => current.minus({ days: 6 - index }).toISODate()!);
  }, [currentReportDate, datePreset, selectedDates, selectedMonth, selectedYear, validYear]);

  const selectableDates = [...new Set([...(availableDates ?? []), ...(reportDates ?? [])])].sort();

  const reportArgs = { nodeId: currentNode.id, selectedDates: reportDates, dayMode };
  const canDownloadReport = reportDates === undefined || reportDates.length > 0;

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
          <ToggleButtonGroup
            exclusive
            size="small"
            value={periodMode}
            aria-label={t("reports.periodTitle")}
            onChange={(_event, value: "all" | "month" | "days" | null) => {
              if (!value) return;
              if (value === "days") {
                setDatePreset("custom");
              } else {
                setDatePreset(value);
                setDayMode("calendar_day");
              }
            }}
            sx={{ alignSelf: "flex-start", "& .MuiToggleButton-root": { textTransform: "none" } }}
          >
            <ToggleButton value="all">{t("reports.allBookings")}</ToggleButton>
            <ToggleButton value="month">{t("reports.month")}</ToggleButton>
            <ToggleButton value="days">{t("reports.individualDays")}</ToggleButton>
          </ToggleButtonGroup>

          {periodMode === "month" && (
            <Stack spacing={1}>
              <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
                <FormControl size="small" sx={{ minWidth: 200 }}>
                  <InputLabel id="report-month-label">{t("reports.month")}</InputLabel>
                  <Select
                    labelId="report-month-label"
                    label={t("reports.month")}
                    value={selectedMonth}
                    onChange={(event) => setSelectedMonth(Number(event.target.value))}
                  >
                    {Array.from({ length: 12 }, (_, index) => (
                      <MenuItem key={index + 1} value={index + 1}>
                        {DateTime.fromObject({ month: index + 1 })
                          .setLocale(i18n.language)
                          .toFormat("LLLL")}
                      </MenuItem>
                    ))}
                  </Select>
                </FormControl>
                <TextField
                  type="number"
                  size="small"
                  label={t("reports.year")}
                  value={selectedYear}
                  onChange={(event) => setSelectedYear(event.target.value)}
                  error={!validYear}
                  helperText={!validYear ? t("reports.validYear") : undefined}
                  slotProps={{ htmlInput: { min: 1970, max: 3999 }, inputLabel: { shrink: true } }}
                  sx={{ width: { xs: "100%", sm: 140 } }}
                />
              </Stack>
              <Typography variant="body2" color="text.secondary">
                {t("reports.selectMonthHint")}
              </Typography>
            </Stack>
          )}

          {periodMode === "days" && (
            <Stack spacing={2}>
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
                      setSelectedDates([...(event.target.value as string[])].sort());
                      setDatePreset("custom");
                    }}
                    renderValue={(selected) => {
                      const values = selected as string[];
                      if (values.length === 0) return <em>{t("reports.chooseDays")}</em>;
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
                    setAdditionalDate("");
                  }}
                >
                  {t("reports.addDate")}
                </Button>
              </Stack>
              <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
                {(["today", "yesterday", "last7"] as const).map((preset) => (
                  <Chip
                    key={preset}
                    size="small"
                    color={datePreset === preset ? "primary" : "default"}
                    label={t(`reports.${preset === "last7" ? "last7Days" : preset}`)}
                    onClick={() => setDatePreset(preset)}
                  />
                ))}
              </Stack>
              <FormControl>
                <ToggleButtonGroup
                  exclusive
                  size="small"
                  value={dayMode}
                  aria-label={t("reports.dayMode")}
                  onChange={(_event, value: ReportDayMode | null) => value && setDayMode(value)}
                  sx={{ alignSelf: "flex-start", "& .MuiToggleButton-root": { textTransform: "none" } }}
                >
                  <ToggleButton value="calendar_day">{t("reports.calendarDay")}</ToggleButton>
                  <ToggleButton value="event_day" disabled={!eventSettings.daily_end_time}>
                    {t("reports.eventDay")}
                  </ToggleButton>
                </ToggleButtonGroup>
                <FormHelperText>
                  {dayMode === "event_day" && eventSettings.daily_end_time
                    ? t("reports.eventDayHint", { time: eventSettings.daily_end_time.slice(0, 5) })
                    : t("reports.calendarDayHint")}
                </FormHelperText>
              </FormControl>
            </Stack>
          )}
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
              disabled={!canDownloadReport}
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
              disabled={!canDownloadReport}
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
