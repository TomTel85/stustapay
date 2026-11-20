import * as React from "react";
import { Alert, Button, Stack, Typography } from "@mui/material";
import { DateTime } from "luxon";
import { useTranslation } from "react-i18next";

type StatsQueryStateProps = React.PropsWithChildren<{
  query: {
    isFetching: boolean;
    isError: boolean;
    currentData?: unknown;
    fulfilledTimeStamp?: number;
    refetch: () => unknown;
  };
  enabled?: boolean;
  showLastUpdated?: boolean;
}>;

export const StatsQueryState: React.FC<StatsQueryStateProps> = ({
  query,
  enabled = true,
  showLastUpdated = false,
  children,
}) => {
  const { t, i18n } = useTranslation();
  if (!enabled) return <>{children}</>;

  const hasData = query.currentData !== undefined;
  const lastUpdated =
    hasData && query.fulfilledTimeStamp
      ? t("overview.lastUpdated", {
          time: DateTime.fromMillis(query.fulfilledTimeStamp)
            .setLocale(i18n.language)
            .toLocaleString(DateTime.DATETIME_SHORT_WITH_SECONDS),
        })
      : undefined;

  return (
    <Stack spacing={1}>
      {query.isError && (
        <Alert
          severity={hasData ? "warning" : "error"}
          action={
            <Button color="inherit" onClick={() => query.refetch()}>
              {t("overview.retryStats")}
            </Button>
          }
        >
          {hasData ? t("overview.statsStale") : t("overview.statsLoadFailed")}
          {hasData && lastUpdated && <Typography variant="body2">{lastUpdated}</Typography>}
        </Alert>
      )}
      {(query.isFetching || (showLastUpdated && lastUpdated)) && !query.isError && (
        <Typography role="status" variant="body2" color="text.secondary">
          {query.isFetching
            ? [t("overview.statsUpdating"), showLastUpdated && lastUpdated].filter(Boolean).join(" ")
            : lastUpdated}
        </Typography>
      )}
      {(hasData || !query.isError) && children}
    </Stack>
  );
};
