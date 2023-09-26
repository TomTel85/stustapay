import { Grid } from "@mui/material";
import * as React from "react";
import { useTranslation } from "react-i18next";
import { DateTime } from "luxon";
import { DateTimePicker } from "@mui/x-date-pickers";
import { TillStatsTable } from "./TillStatsTable";
import { ProductStatsCard } from "./ProductStatsCard";
import { DepositStatsCard } from "./DepositStatsCard";
import { VoucherStatsCard } from "./VoucherStatsCard";

export const FestivalOverview: React.FC = () => {
  const { t } = useTranslation();
  // Prefilling the initial values
  const [fromTimestamp, setFromTimestamp] = React.useState<null | DateTime>(DateTime.now().minus({ months: 1 }));
  const [toTimestamp, setToTimestamp] = React.useState<null | DateTime>(DateTime.now());


  return (
    <Grid container spacing={2}>
      <Grid item xs={12}>
        <DateTimePicker label={t("overview.fromTimestamp")} value={fromTimestamp} onChange={setFromTimestamp} />
        <DateTimePicker
          label={t("overview.toTimestamp")}
          value={toTimestamp}
          onChange={setToTimestamp}
          sx={{ ml: 1 }}
        />
      </Grid>
      <Grid item xs={4}>
        <ProductStatsCard fromTimestamp={fromTimestamp?.toISO() ?? null} toTimestamp={toTimestamp?.toISO() ?? null} />
      </Grid>
      <Grid item xs={4}>
        <DepositStatsCard fromTimestamp={fromTimestamp?.toISO() ?? null} toTimestamp={toTimestamp?.toISO() ?? null} />
      </Grid>
      <Grid item xs={4}>
        <VoucherStatsCard fromTimestamp={fromTimestamp?.toISO() ?? null} toTimestamp={toTimestamp?.toISO() ?? null} />
      </Grid>
      <Grid item xs={12}>
        <TillStatsTable fromTimestamp={fromTimestamp?.toISO() ?? null} toTimestamp={toTimestamp?.toISO() ?? null} />
      </Grid>
    </Grid>
  );
};
