import * as React from "react";
import {
  NodeSeenByUser,
  useGetAvailableDatesQuery,
  useGetDashboardOverviewQuery,
  useGetPaymentMethodStatsQuery,
  useGetProductStatsQuery,
  useGetRevenueByCounterQuery,
  useListTillsQuery,
  useListProductsQuery,
  useGetRevenuePredictionQuery,
  api,
} from "@/api";
import { Privilege } from "@stustapay/models";
import { DateTime } from "luxon";
import { useTranslation } from "react-i18next";
import {
  Alert,
  AlertTitle,
  Grid,
  Stack,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Button,
  Accordion,
  AccordionSummary,
  AccordionDetails,
  Typography,
  Chip,
  Checkbox,
  ListItemText,
} from "@mui/material";
import type { Theme } from "@mui/material/styles";
import { useCurrentEventSettings, useCurrentNode, useCurrentUserHasPrivilege } from "@/hooks";
import { Navigate } from "react-router-dom";
import { OrderRoutes } from "@/app/routes";
import {
  useAppDispatch,
  useAppSelector,
  selectStatsPollingInterval,
  selectStatsExpandedSections,
  setStatsPollingInterval,
  setStatsSectionExpanded,
} from "@/store";
import { Refresh as RefreshIcon, ExpandMore as ExpandMoreIcon, AutoGraph as AutoGraphIcon } from "@mui/icons-material";
import { DashboardKPIs, ForecastMetrics, PaymentMethodTotals } from "./DashboardKPIs";
import { RevenueByCounterChart } from "./RevenueByCounterChart";
import { RevenueByProductChart } from "./RevenueByProductChart";
import { RevenueByCounterTable } from "./RevenueByCounterTable";
import { QuantitiesByProductTable } from "./QuantitiesByProductTable";
import { OrdersTable } from "./OrdersTable";
import { RevenuePredictionChart } from "./RevenuePredictionChart";
import { StatsQueryState } from "./StatsQueryState";
import { statsQueryOptions } from "./queryOptions";

type SectionKey =
  | "filters"
  | "kpis"
  | "prediction"
  | "counterChart"
  | "productChart"
  | "quantityTable"
  | "counterTable"
  | "orders";

const eventTimeZone = "Europe/Berlin";

type DatePreset = "all" | "today" | "yesterday" | "last7" | "custom";

export const NodeStats: React.FC = () => {
  const { t, i18n } = useTranslation();
  const canViewNodeStats = useCurrentUserHasPrivilege(Privilege.view_node_stats);
  const canAdminNode = useCurrentUserHasPrivilege(Privilege.node_administration);
  const canViewOrders = useCurrentUserHasPrivilege(OrderRoutes.privilege);
  const { eventSettings } = useCurrentEventSettings();
  const { currentNode } = useCurrentNode();
  const dispatch = useAppDispatch();
  const [datePreset, setDatePreset] = React.useState<DatePreset>("today");
  const [selectedDates, setSelectedDates] = React.useState<string[]>([]);
  const [selectedSubnodeId, setSelectedSubnodeId] = React.useState<number | undefined>(undefined);
  const [selectedTillId, setSelectedTillId] = React.useState<number | undefined>(undefined);
  const [selectedProductId, setSelectedProductId] = React.useState<number | undefined>(undefined);
  const [isPredictionEnabled, setIsPredictionEnabled] = React.useState(false);
  const [isCustomDatePickerOpen, setIsCustomDatePickerOpen] = React.useState(false);
  const ordersSummaryRef = React.useRef<HTMLButtonElement>(null);
  const pollingIntervalMs = useAppSelector(selectStatsPollingInterval);
  const expandedSections = useAppSelector(selectStatsExpandedSections) as Record<SectionKey, boolean>;
  const predictionPollingIntervalMs = pollingIntervalMs > 0 ? Math.max(pollingIntervalMs, 300000) : 0;

  const effectiveFilterNodeId = selectedSubnodeId ?? currentNode.id;
  const isFiltersExpanded = expandedSections.filters;
  const isKpisExpanded = expandedSections.kpis;
  const isPredictionExpanded = expandedSections.prediction;
  const isCounterChartExpanded = expandedSections.counterChart;
  const isProductChartExpanded = expandedSections.productChart;
  const isQuantityTableExpanded = expandedSections.quantityTable;
  const isCounterTableExpanded = expandedSections.counterTable;
  const isOrdersExpanded = expandedSections.orders;

  const subnodeOptions = React.useMemo(() => {
    const options: Array<{ id: number; name: string; depth: number }> = [];
    const queue: Array<{ node: NodeSeenByUser; depth: number }> = currentNode.children.map((child) => ({
      node: child,
      depth: 1,
    }));

    while (queue.length > 0) {
      const current = queue.shift();
      if (!current) break;
      options.push({ id: current.node.id, name: current.node.name, depth: current.depth });
      for (const child of current.node.children) {
        queue.push({ node: child, depth: current.depth + 1 });
      }
    }

    return options;
  }, [currentNode]);

  React.useEffect(() => {
    if (selectedSubnodeId === undefined) {
      return;
    }

    const isValidSelection = subnodeOptions.some((option) => option.id === selectedSubnodeId);
    if (!isValidSelection) {
      setSelectedSubnodeId(undefined);
      setSelectedTillId(undefined);
      setSelectedProductId(undefined);
    }
  }, [selectedSubnodeId, subnodeOptions]);

  const isProductSelected = selectedProductId !== undefined;
  const isProductDataEnabled =
    isProductChartExpanded || isQuantityTableExpanded || (isKpisExpanded && isProductSelected);
  const isCounterDataEnabled = !isProductSelected && (isCounterChartExpanded || isCounterTableExpanded);
  const isOverviewDataEnabled = isKpisExpanded && !isProductSelected;
  const isOrdersDataEnabled = isOrdersExpanded && canViewOrders;
  const canShowForecast = currentNode.event != null && !isProductSelected;

  const datesQuery = useGetAvailableDatesQuery(
    {
      nodeId: currentNode.id,
      subnodeId: selectedSubnodeId,
      dayMode: eventSettings.daily_end_time ? "event_day" : "calendar_day",
    },
    {
      ...statsQueryOptions(pollingIntervalMs, isCustomDatePickerOpen),
      skip: !isCustomDatePickerOpen,
    }
  );
  const tillsQuery = useListTillsQuery({ nodeId: effectiveFilterNodeId }, statsQueryOptions(pollingIntervalMs));
  const productsQuery = useListProductsQuery({ nodeId: effectiveFilterNodeId }, statsQueryOptions(pollingIntervalMs));
  const { currentData: tills } = tillsQuery;
  const { currentData: products } = productsQuery;
  const predictionQuery = useGetRevenuePredictionQuery(
    { nodeId: currentNode.id, tillId: selectedTillId, subnodeId: selectedSubnodeId },
    {
      ...statsQueryOptions(predictionPollingIntervalMs, isPredictionExpanded),
      skip: !canShowForecast || !isPredictionEnabled || !isPredictionExpanded,
    }
  );

  const handleManualRefresh = React.useCallback(() => {
    dispatch(api.util.invalidateTags(["stats", "orders", "tills", "products"]));
  }, [dispatch]);

  const clearAllFilterSelections = React.useCallback(() => {
    setDatePreset("all");
    setSelectedDates([]);
    setIsCustomDatePickerOpen(false);
    setSelectedSubnodeId(undefined);
    setSelectedTillId(undefined);
    setSelectedProductId(undefined);
  }, []);

  const sectionSx = {
    backgroundColor: (theme: Theme) =>
      theme.palette.mode === "dark" ? "rgba(26, 27, 30, 0.8)" : "rgba(255, 255, 255, 0.9)",
    border: (theme: Theme) =>
      `1px solid ${theme.palette.mode === "dark" ? "rgba(255, 255, 255, 0.1)" : "rgba(0, 0, 0, 0.1)"}`,
    boxShadow: "none",
    "&::before": { display: "none" },
  };

  const summaryTextSx = {
    fontSize: "0.9375rem",
    fontWeight: 600,
  };
  const summarySx = {
    minHeight: 48,
    px: { xs: 1, sm: 1.5, md: 2 },
    "& .MuiAccordionSummary-content": {
      my: { xs: 0.5, sm: 0.75, md: 1 },
    },
    "& .MuiAccordionSummary-expandIconWrapper .MuiSvgIcon-root": {
      fontSize: { xs: "1.1rem", sm: "1.2rem" },
    },
  };

  const handleSectionToggle = React.useCallback(
    (section: SectionKey) => (_event: React.SyntheticEvent, expanded: boolean) => {
      dispatch(setStatsSectionExpanded({ section, expanded }));
    },
    [dispatch]
  );

  const dailyEndParts = React.useMemo(() => {
    if (!eventSettings.daily_end_time) {
      return { hour: 0, minute: 0, second: 0 };
    }
    const timeParts = eventSettings.daily_end_time.split(":");
    return {
      hour: parseInt(timeParts[0], 10) || 0,
      minute: parseInt(timeParts[1], 10) || 0,
      second: parseInt(timeParts[2], 10) || 0,
    };
  }, [eventSettings.daily_end_time]);

  const businessDayStartForDate = React.useCallback(
    (date: DateTime) => date.startOf("day").set({ ...dailyEndParts, millisecond: 0 }),
    [dailyEndParts]
  );

  const getBusinessDayStart = React.useCallback(
    (now: DateTime) => {
      const boundary = businessDayStartForDate(now);
      return now < boundary ? businessDayStartForDate(now.minus({ days: 1 })) : boundary;
    },
    [businessDayStartForDate]
  );
  const [now, setNow] = React.useState(() => DateTime.now().setZone(eventTimeZone));
  const currentBusinessDayStart = React.useMemo(() => getBusinessDayStart(now), [getBusinessDayStart, now]);

  React.useEffect(() => {
    let timeout: ReturnType<typeof setTimeout>;
    const updateClock = () => {
      clearTimeout(timeout);
      const currentTime = DateTime.now().setZone(eventTimeZone);
      const start = getBusinessDayStart(currentTime);
      setNow((previous) => (getBusinessDayStart(previous).equals(start) ? previous : currentTime));
      const nextStart = businessDayStartForDate(start.plus({ days: 1 }));
      timeout = setTimeout(updateClock, Math.max(1, nextStart.diff(currentTime).as("milliseconds")));
    };
    updateClock();
    window.addEventListener("focus", updateClock);
    return () => {
      window.removeEventListener("focus", updateClock);
      clearTimeout(timeout);
    };
  }, [businessDayStartForDate, getBusinessDayStart]);

  const forecastDay = currentBusinessDayStart.toMillis();
  const previousForecastDay = React.useRef(forecastDay);
  React.useEffect(() => {
    if (previousForecastDay.current !== forecastDay) {
      previousForecastDay.current = forecastDay;
      if (canShowForecast && isPredictionEnabled && isPredictionExpanded) predictionQuery.refetch();
    }
  }, [forecastDay, canShowForecast, isPredictionEnabled, isPredictionExpanded, predictionQuery.refetch]);

  const sortedSelectedDates = React.useMemo(() => [...selectedDates].sort(), [selectedDates]);
  const selectedDatesForQuery = React.useMemo(
    () => (datePreset === "custom" && sortedSelectedDates.length > 0 ? sortedSelectedDates : undefined),
    [datePreset, sortedSelectedDates]
  );

  // Determine timestamp bounds based on selected date and event settings
  const fromTimestamp = React.useMemo(() => {
    if (datePreset === "all") {
      return undefined;
    }
    if (datePreset === "today") {
      return currentBusinessDayStart;
    }
    if (datePreset === "yesterday") {
      return businessDayStartForDate(currentBusinessDayStart.minus({ days: 1 }));
    }
    if (datePreset === "last7") {
      return businessDayStartForDate(currentBusinessDayStart.minus({ days: 6 }));
    }
    if (sortedSelectedDates.length === 0) {
      return undefined;
    }

    const dt = DateTime.fromISO(sortedSelectedDates[0], { zone: eventTimeZone });
    if (eventSettings.daily_end_time) {
      return businessDayStartForDate(dt);
    }
    return dt.startOf("day");
  }, [datePreset, sortedSelectedDates, eventSettings.daily_end_time, currentBusinessDayStart, businessDayStartForDate]);

  const toTimestamp = React.useMemo(() => {
    if (!fromTimestamp) return undefined;

    if (datePreset === "last7") {
      return businessDayStartForDate(fromTimestamp.plus({ days: 7 })).minus({ milliseconds: 1 });
    }
    if (datePreset === "custom" && sortedSelectedDates.length > 0) {
      const lastDate = DateTime.fromISO(sortedSelectedDates[sortedSelectedDates.length - 1], { zone: eventTimeZone });
      const lastRangeStart = eventSettings.daily_end_time ? businessDayStartForDate(lastDate) : lastDate.startOf("day");
      return businessDayStartForDate(lastRangeStart.plus({ days: 1 })).minus({ milliseconds: 1 });
    }
    return businessDayStartForDate(fromTimestamp.plus({ days: 1 })).minus({ milliseconds: 1 });
  }, [fromTimestamp, datePreset, sortedSelectedDates, eventSettings.daily_end_time, businessDayStartForDate]);

  const sharedStatsArgs = React.useMemo(
    () => ({
      nodeId: currentNode.id,
      fromTimestamp: fromTimestamp?.toISO() ?? undefined,
      toTimestamp: toTimestamp?.toISO() ?? undefined,
      selectedDates: selectedDatesForQuery,
      tillId: selectedTillId,
      subnodeId: selectedSubnodeId,
    }),
    [currentNode.id, fromTimestamp, selectedDatesForQuery, selectedTillId, selectedSubnodeId, toTimestamp]
  );
  const overviewQuery = useGetDashboardOverviewQuery(sharedStatsArgs, {
    ...statsQueryOptions(pollingIntervalMs, isOverviewDataEnabled),
    skip: !isOverviewDataEnabled,
  });
  const paymentMethodsQuery = useGetPaymentMethodStatsQuery(sharedStatsArgs, {
    ...statsQueryOptions(pollingIntervalMs, isOverviewDataEnabled),
    skip: !isOverviewDataEnabled,
  });
  const productStatsQuery = useGetProductStatsQuery(sharedStatsArgs, {
    ...statsQueryOptions(pollingIntervalMs, isProductDataEnabled),
    skip: !isProductDataEnabled,
  });
  const counterStatsQuery = useGetRevenueByCounterQuery(sharedStatsArgs, {
    ...statsQueryOptions(pollingIntervalMs, isCounterDataEnabled),
    skip: !isCounterDataEnabled,
  });

  const selectedSubnodeName = React.useMemo(
    () => subnodeOptions.find((node) => node.id === selectedSubnodeId)?.name,
    [subnodeOptions, selectedSubnodeId]
  );

  const hasNonDateFilters = selectedSubnodeId !== undefined || selectedTillId !== undefined || isProductSelected;
  const formatDateTime = (date: DateTime) =>
    date
      .setLocale(i18n.language)
      .toLocaleString(dailyEndParts.second ? DateTime.DATETIME_MED_WITH_SECONDS : DateTime.DATETIME_MED);
  const cutoff = DateTime.fromObject(dailyEndParts, { zone: "UTC", locale: i18n.language }).toLocaleString(
    dailyEndParts.second ? DateTime.TIME_WITH_SECONDS : DateTime.TIME_SIMPLE
  );
  const reportingWindow =
    selectedDatesForQuery && selectedDatesForQuery.length > 1
      ? t("overview.selectedBusinessDates", {
          dates: selectedDatesForQuery
            .map((date) => DateTime.fromISO(date).setLocale(i18n.language).toLocaleString(DateTime.DATE_MED))
            .join(", "),
          cutoff,
        })
      : fromTimestamp && toTimestamp
        ? t("overview.reportingWindow", {
            start: formatDateTime(fromTimestamp),
            end: formatDateTime(toTimestamp.plus({ milliseconds: 1 })),
          })
        : t("overview.fullReportingWindow", { cutoff });
  const primaryQuery = isProductSelected ? productStatsQuery : overviewQuery;
  const loading = (query: { isFetching: boolean; currentData?: unknown }) =>
    query.isFetching && query.currentData === undefined;

  if (!canViewNodeStats && !canAdminNode) {
    return <Navigate to="/" />;
  }

  if (
    currentNode.event != null &&
    (eventSettings.start_date == null || eventSettings.end_date == null || eventSettings.daily_end_time == null)
  ) {
    return (
      <Alert severity="warning">
        <AlertTitle>{t("overview.warningEventDatesNeedConfiguration")}</AlertTitle>
      </Alert>
    );
  }

  return (
    <Grid container spacing={{ xs: 0.75, sm: 1, md: 1.5 }}>
      <Grid size={12}>
        <Stack spacing={1.5} sx={{ mb: 1 }}>
          <Stack
            direction="row"
            spacing={1}
            alignItems="center"
            justifyContent="space-between"
            useFlexGap
            flexWrap="wrap"
          >
            <Typography component="h1" variant="h5">
              {t("overview.statisticsTitle")}
            </Typography>
            <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
              <Button startIcon={<RefreshIcon />} onClick={handleManualRefresh} sx={{ minHeight: 44 }}>
                {t("refresh")}
              </Button>
              {canViewOrders && (
                <Button
                  sx={{ minHeight: 44 }}
                  onClick={() => {
                    dispatch(setStatsSectionExpanded({ section: "orders", expanded: true }));
                    ordersSummaryRef.current?.focus();
                  }}
                >
                  {t("overview.viewOrders")}
                </Button>
              )}
            </Stack>
          </Stack>
          <Grid container spacing={1}>
            <Grid size={{ xs: 12, sm: 4 }}>
              <FormControl fullWidth>
                <InputLabel id="stats-period-label">{t("overview.reportingPeriod")}</InputLabel>
                <Select
                  labelId="stats-period-label"
                  label={t("overview.reportingPeriod")}
                  value={isCustomDatePickerOpen ? "custom" : datePreset}
                  onChange={(event) => {
                    const preset = event.target.value as DatePreset;
                    setIsCustomDatePickerOpen(preset === "custom");
                    if (preset !== "custom") {
                      setDatePreset(preset);
                      setSelectedDates([]);
                    }
                  }}
                >
                  <MenuItem value="today">{t("overview.today")}</MenuItem>
                  <MenuItem value="yesterday">{t("overview.yesterday")}</MenuItem>
                  <MenuItem value="last7">{t("overview.last7Days")}</MenuItem>
                  <MenuItem value="all">{t("overview.allDates")}</MenuItem>
                  <MenuItem value="custom">{t("overview.customDates")}</MenuItem>
                </Select>
              </FormControl>
            </Grid>
            <Grid size={{ xs: 6, sm: 4 }}>
              <FormControl fullWidth>
                <InputLabel id="till-select-label" shrink>
                  {t("overview.filterTill")}
                </InputLabel>
                <Select
                  labelId="till-select-label"
                  id="till-select"
                  value={selectedTillId ?? ""}
                  label={t("overview.filterTill")}
                  onChange={(e) => {
                    const val = e.target.value as string | number;
                    setSelectedTillId(val === "" ? undefined : (val as number));
                  }}
                  displayEmpty
                  notched
                >
                  <MenuItem value="">
                    <em>{t("overview.allTills")}</em>
                  </MenuItem>
                  {tills &&
                    tills.ids.map((id) => (
                      <MenuItem key={id} value={id} sx={{ whiteSpace: "normal", overflowWrap: "anywhere" }}>
                        {tills.entities[id]?.name}
                      </MenuItem>
                    ))}
                </Select>
              </FormControl>
            </Grid>

            <Grid size={{ xs: 6, sm: 4 }}>
              <FormControl fullWidth>
                <InputLabel id="product-select-label" shrink>
                  {t("overview.filterProduct")}
                </InputLabel>
                <Select
                  labelId="product-select-label"
                  id="product-select"
                  value={selectedProductId ?? ""}
                  label={t("overview.filterProduct")}
                  onChange={(e) => {
                    const val = e.target.value as string | number;
                    setSelectedProductId(val === "" ? undefined : (val as number));
                  }}
                  displayEmpty
                  notched
                >
                  <MenuItem value="">
                    <em>{t("overview.allProducts")}</em>
                  </MenuItem>
                  {products &&
                    products.ids.map((id) => (
                      <MenuItem key={id} value={id} sx={{ whiteSpace: "normal", overflowWrap: "anywhere" }}>
                        {products.entities[id]?.name}
                      </MenuItem>
                    ))}
                </Select>
              </FormControl>
            </Grid>
          </Grid>
          {tillsQuery.isError && <StatsQueryState query={tillsQuery} />}
          {productsQuery.isError && <StatsQueryState query={productsQuery} />}
          {isCustomDatePickerOpen && (
            <StatsQueryState query={datesQuery}>
              <FormControl size="small" sx={{ width: { xs: "100%", sm: 320 } }}>
                <InputLabel id="date-select-label" shrink>
                  {t("overview.filterDate")}
                </InputLabel>
                <Select
                  labelId="date-select-label"
                  label={t("overview.filterDate")}
                  multiple
                  displayEmpty
                  notched
                  value={selectedDates}
                  renderValue={(dates) =>
                    dates.length ? t("overview.selectedDatesCount", { count: dates.length }) : t("overview.chooseDates")
                  }
                  onChange={(event) => {
                    const dates = event.target.value as string[];
                    setSelectedDates(dates);
                    if (dates.length > 0) setDatePreset("custom");
                    else if (datePreset === "custom") setDatePreset("all");
                  }}
                >
                  {Array.from(new Set([...(datesQuery.currentData ?? []), ...selectedDates]))
                    .sort()
                    .map((date) => (
                      <MenuItem key={date} value={date}>
                        <Checkbox checked={selectedDates.includes(date)} size="small" />
                        <ListItemText
                          primary={DateTime.fromISO(date).setLocale(i18n.language).toLocaleString(DateTime.DATE_MED)}
                        />
                      </MenuItem>
                    ))}
                  {datesQuery.currentData?.length === 0 && (
                    <MenuItem disabled>{t("overview.noDatesAvailable")}</MenuItem>
                  )}
                </Select>
              </FormControl>
            </StatsQueryState>
          )}
          <Typography variant="body2" color="text.secondary">
            {reportingWindow}
          </Typography>
          {hasNonDateFilters && (
            <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap" alignItems="center">
              {selectedSubnodeId !== undefined && (
                <Chip
                  size="small"
                  label={`${t("overview.filterSubnode")}: ${selectedSubnodeName ?? selectedSubnodeId}`}
                  onDelete={() => {
                    setSelectedSubnodeId(undefined);
                    setSelectedTillId(undefined);
                    setSelectedProductId(undefined);
                  }}
                />
              )}
              <Button size="small" variant="text" onClick={clearAllFilterSelections}>
                {t("overview.clearAllFilters")}
              </Button>
            </Stack>
          )}
        </Stack>
      </Grid>
      <Grid size={12}>
        <Accordion
          expanded={expandedSections.kpis}
          onChange={handleSectionToggle("kpis")}
          disableGutters
          sx={sectionSx}
        >
          <AccordionSummary expandIcon={<ExpandMoreIcon />} sx={summarySx}>
            <Typography sx={summaryTextSx}>{t("overview.overviewMetrics")}</Typography>
          </AccordionSummary>
          <AccordionDetails sx={{ p: { xs: 0.75, sm: 1, md: 1.5 } }}>
            {isKpisExpanded && (
              <Stack spacing={2}>
                <StatsQueryState query={primaryQuery} showLastUpdated>
                  <DashboardKPIs
                    productId={selectedProductId}
                    isLoading={loading(primaryQuery)}
                    overview={overviewQuery.currentData}
                    productStats={productStatsQuery.currentData}
                  />
                </StatsQueryState>
                {!isProductSelected && (
                  <StatsQueryState query={paymentMethodsQuery}>
                    <PaymentMethodTotals data={paymentMethodsQuery.currentData} />
                  </StatsQueryState>
                )}
              </Stack>
            )}
          </AccordionDetails>
        </Accordion>
      </Grid>
      <Grid size={12}>
        <Accordion expanded={isFiltersExpanded} onChange={handleSectionToggle("filters")} disableGutters sx={sectionSx}>
          <AccordionSummary expandIcon={<ExpandMoreIcon />} sx={summarySx}>
            <Typography sx={summaryTextSx}>{t("overview.moreStatsSettings")}</Typography>
          </AccordionSummary>
          <AccordionDetails>
            <Grid container spacing={2} alignItems="center">
              <Grid size={{ xs: 12, sm: 6, md: 4 }}>
                <FormControl size="small" fullWidth>
                  <InputLabel id="subnode-select-label" shrink>
                    {t("overview.filterSubnode")}
                  </InputLabel>
                  <Select
                    labelId="subnode-select-label"
                    id="subnode-select"
                    value={selectedSubnodeId ?? ""}
                    label={t("overview.filterSubnode")}
                    onChange={(e) => {
                      const val = e.target.value as string | number;
                      setSelectedSubnodeId(val === "" ? undefined : (val as number));
                      setSelectedTillId(undefined);
                      setSelectedProductId(undefined);
                    }}
                    displayEmpty
                    notched
                  >
                    <MenuItem value="">
                      <em>{t("overview.allSubnodes")}</em>
                    </MenuItem>
                    {subnodeOptions.map((option) => (
                      <MenuItem key={option.id} value={option.id}>
                        {`${"  ".repeat(Math.max(0, option.depth - 1))}${option.name}`}
                      </MenuItem>
                    ))}
                  </Select>
                </FormControl>
              </Grid>

              <Grid size={{ xs: 12, sm: 6, md: 4 }}>
                <FormControl size="small" fullWidth>
                  <InputLabel id="polling-select-label" shrink>
                    {t("overview.pollingInterval")}
                  </InputLabel>
                  <Select
                    labelId="polling-select-label"
                    id="polling-select"
                    value={pollingIntervalMs}
                    label={t("overview.pollingInterval")}
                    onChange={(e) => dispatch(setStatsPollingInterval(Number(e.target.value)))}
                    notched
                  >
                    <MenuItem value={0}>
                      <em>{t("overview.pollingOff")}</em>
                    </MenuItem>
                    <MenuItem value={30000}>30s</MenuItem>
                    <MenuItem value={60000}>1min</MenuItem>
                    <MenuItem value={300000}>5min</MenuItem>
                    <MenuItem value={1800000}>30min</MenuItem>
                  </Select>
                </FormControl>
              </Grid>
              {canShowForecast && (
                <Grid size={{ xs: 12, md: 4 }}>
                  <Button
                    startIcon={<AutoGraphIcon />}
                    sx={{ minHeight: 44 }}
                    onClick={() => {
                      setIsPredictionEnabled(!isPredictionEnabled);
                      if (!isPredictionEnabled)
                        dispatch(setStatsSectionExpanded({ section: "prediction", expanded: true }));
                    }}
                  >
                    {isPredictionEnabled ? t("overview.disablePrediction") : t("overview.enablePrediction")}
                  </Button>
                </Grid>
              )}
            </Grid>
          </AccordionDetails>
        </Accordion>
      </Grid>
      {/* Revenue prediction chart - only show when no product filter is active */}
      {isPredictionEnabled && canShowForecast && (
        <Grid size={12}>
          <Accordion
            expanded={expandedSections.prediction}
            onChange={handleSectionToggle("prediction")}
            disableGutters
            sx={sectionSx}
          >
            <AccordionSummary expandIcon={<ExpandMoreIcon />} sx={summarySx}>
              <Typography sx={summaryTextSx}>{t("overview.revenuePredictionChart")}</Typography>
            </AccordionSummary>
            <AccordionDetails sx={{ p: { xs: 0.75, sm: 1, md: 1.5 } }}>
              {isPredictionExpanded && (
                <StatsQueryState query={predictionQuery} showLastUpdated>
                  <Typography variant="body2" color="text.secondary">
                    {t("overview.forecastScope")}
                  </Typography>
                  {predictionQuery.currentData && (
                    <>
                      <ForecastMetrics prediction={predictionQuery.currentData} />
                      <RevenuePredictionChart prediction={predictionQuery.currentData} />
                    </>
                  )}
                </StatsQueryState>
              )}
            </AccordionDetails>
          </Accordion>
        </Grid>
      )}
      {/* Only show revenue by counter when no product is selected (not filterable by product) */}
      {selectedProductId === undefined && (
        <Grid size={12}>
          <Accordion
            expanded={expandedSections.counterChart}
            onChange={handleSectionToggle("counterChart")}
            disableGutters
            sx={sectionSx}
          >
            <AccordionSummary expandIcon={<ExpandMoreIcon />} sx={summarySx}>
              <Typography sx={summaryTextSx}>{t("overview.revenuePerCounterChart")}</Typography>
            </AccordionSummary>
            <AccordionDetails sx={{ p: { xs: 0.75, sm: 1, md: 1.5 } }}>
              <StatsQueryState query={counterStatsQuery} enabled={isCounterChartExpanded} showLastUpdated>
                <RevenueByCounterChart
                  tillId={selectedTillId}
                  enabled={isCounterChartExpanded}
                  isLoading={loading(counterStatsQuery)}
                  data={counterStatsQuery.currentData}
                  onBarClick={(tillId) => setSelectedTillId(tillId)}
                  onClearFilter={() => setSelectedTillId(undefined)}
                />
              </StatsQueryState>
            </AccordionDetails>
          </Accordion>
        </Grid>
      )}
      <Grid size={12}>
        <Accordion
          expanded={expandedSections.productChart}
          onChange={handleSectionToggle("productChart")}
          disableGutters
          sx={sectionSx}
        >
          <AccordionSummary expandIcon={<ExpandMoreIcon />} sx={summarySx}>
            <Typography sx={summaryTextSx}>{t("overview.revenuePerProduct")}</Typography>
          </AccordionSummary>
          <AccordionDetails sx={{ p: { xs: 0.75, sm: 1, md: 1.5 } }}>
            <StatsQueryState query={productStatsQuery} enabled={isProductChartExpanded} showLastUpdated>
              <RevenueByProductChart
                enabled={isProductChartExpanded}
                productId={selectedProductId}
                isLoading={loading(productStatsQuery)}
                data={productStatsQuery.currentData}
                onProductClick={(productId) => setSelectedProductId(productId)}
                onClearFilter={() => setSelectedProductId(undefined)}
              />
            </StatsQueryState>
          </AccordionDetails>
        </Accordion>
      </Grid>
      <Grid size={12}>
        <Accordion
          expanded={expandedSections.quantityTable}
          onChange={handleSectionToggle("quantityTable")}
          disableGutters
          sx={sectionSx}
        >
          <AccordionSummary expandIcon={<ExpandMoreIcon />} sx={summarySx}>
            <Typography sx={summaryTextSx}>{t("overview.quantitiesPerProduct")}</Typography>
          </AccordionSummary>
          <AccordionDetails sx={{ p: { xs: 0.75, sm: 1, md: 1.5 } }}>
            <StatsQueryState query={productStatsQuery} enabled={isQuantityTableExpanded} showLastUpdated>
              <QuantitiesByProductTable
                enabled={isQuantityTableExpanded}
                productId={selectedProductId}
                isLoading={loading(productStatsQuery)}
                data={productStatsQuery.currentData}
              />
            </StatsQueryState>
          </AccordionDetails>
        </Accordion>
      </Grid>
      {/* Only show revenue by counter table when no product is selected (not filterable by product) */}
      {selectedProductId === undefined && (
        <Grid size={12}>
          <Accordion
            expanded={expandedSections.counterTable}
            onChange={handleSectionToggle("counterTable")}
            disableGutters
            sx={sectionSx}
          >
            <AccordionSummary expandIcon={<ExpandMoreIcon />} sx={summarySx}>
              <Typography sx={summaryTextSx}>{t("overview.revenuePerCounterTable")}</Typography>
            </AccordionSummary>
            <AccordionDetails sx={{ p: { xs: 0.75, sm: 1, md: 1.5 } }}>
              <StatsQueryState query={counterStatsQuery} enabled={isCounterTableExpanded} showLastUpdated>
                <RevenueByCounterTable
                  fromTimestamp={fromTimestamp}
                  toTimestamp={toTimestamp}
                  selectedDates={selectedDatesForQuery}
                  enabled={isCounterTableExpanded}
                  isLoading={loading(counterStatsQuery)}
                  data={counterStatsQuery.currentData}
                />
              </StatsQueryState>
            </AccordionDetails>
          </Accordion>
        </Grid>
      )}
      {canViewOrders && (
        <Grid size={12}>
          <Accordion
            expanded={expandedSections.orders}
            onChange={handleSectionToggle("orders")}
            disableGutters
            sx={sectionSx}
          >
            <AccordionSummary component="button" ref={ordersSummaryRef} expandIcon={<ExpandMoreIcon />} sx={summarySx}>
              <Typography sx={summaryTextSx}>{t("overview.orders")}</Typography>
            </AccordionSummary>
            <AccordionDetails sx={{ p: { xs: 0.75, sm: 1, md: 1.5 } }}>
              <OrdersTable
                fromTimestamp={fromTimestamp}
                toTimestamp={toTimestamp}
                selectedDates={selectedDatesForQuery}
                tillId={selectedTillId}
                subnodeId={selectedSubnodeId}
                productId={selectedProductId}
                pollingIntervalMs={pollingIntervalMs}
                enabled={isOrdersDataEnabled}
              />
            </AccordionDetails>
          </Accordion>
        </Grid>
      )}
    </Grid>
  );
};
