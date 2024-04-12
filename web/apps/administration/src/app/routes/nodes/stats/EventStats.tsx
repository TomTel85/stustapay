import * as React from "react";
import { DateTime } from "luxon";
import { Card, CardContent, Grid, Skeleton, Typography } from "@mui/material";
import { useGetEntryStatsQuery, useGetTopUpStatsQuery } from "@/api";
import { DailyStatsTable, HourlyGraph } from "@/components";
import { useCurrentNode } from "@/hooks";

const EntryStats: React.FC<{
  nodeId: number;
  fromTimestamp?: DateTime;
  toTimestamp?: DateTime;
  dailyEndTime: string;
  groupByDay: boolean;
  useRevenue: boolean;
}> = ({ nodeId, fromTimestamp, toTimestamp, groupByDay, dailyEndTime, useRevenue }) => {
  const { data } = useGetEntryStatsQuery({
    nodeId: nodeId,
    fromTimestamp: fromTimestamp?.toISO() ?? undefined,
    toTimestamp: toTimestamp?.toISO() ?? undefined,
  });

  if (!data) {
    return (
      <>
        <Typography variant="h5">Entry Stats</Typography>
        <Grid container spacing={2}>
          <Grid item xs={12} md={10} height={300}>
            <Skeleton variant="rounded" height={300} />
          </Grid>
          <Grid item xs={12} md={2} height={300}>
            <Skeleton variant="rounded" height={300} />
          </Grid>
        </Grid>
      </>
    );
  }

  return (
    <>
      <Typography variant="h5">Entry Stats</Typography>
      <Grid container spacing={2}>
        <Grid item xs={12} md={10} height={300}>
          <HourlyGraph dailyEndTime={dailyEndTime} groupByDay={groupByDay} useRevenue={useRevenue} data={data} />
        </Grid>
        <Grid item xs={12} md={2} height={300}>
          <DailyStatsTable data={data} useRevenue={useRevenue} />
        </Grid>
      </Grid>
    </>
  );
  return;
};

const TopUpStats: React.FC<{
  nodeId: number;
  fromTimestamp?: DateTime;
  toTimestamp?: DateTime;
  groupByDay: boolean;
  dailyEndTime: string;
  useRevenue: boolean;
}> = ({ nodeId, fromTimestamp, toTimestamp, groupByDay, dailyEndTime, useRevenue }) => {
  const { data } = useGetTopUpStatsQuery({
    nodeId: nodeId,
    fromTimestamp: fromTimestamp?.toISO() ?? undefined,
    toTimestamp: toTimestamp?.toISO() ?? undefined,
  });

  if (!data) {
    return (
      <>
        <Typography variant="h5">Top Up Stats</Typography>
        <Grid container spacing={2}>
          <Grid item xs={12} md={9} height={300}>
            <Skeleton variant="rounded" height={300} />
          </Grid>
          <Grid item xs={12} md={3} height={300}>
            <Skeleton variant="rounded" height={300} />
          </Grid>
        </Grid>
      </>
    );
  }

  return (
    <>
      <Typography variant="h5">Top Up Stats</Typography>
      <Grid container spacing={2}>
        <Grid item xs={12} md={9} height={300}>
          <HourlyGraph dailyEndTime={dailyEndTime} groupByDay={groupByDay} useRevenue={useRevenue} data={data} />
        </Grid>
        <Grid item xs={12} md={3} height={300}>
          <DailyStatsTable data={data} useRevenue={useRevenue} />
        </Grid>
      </Grid>
    </>
  );
  return;
};

export type EventStatsProps = {
  fromTimestamp?: DateTime;
  toTimestamp?: DateTime;
  dailyEndTime: string;
  groupByDay: boolean;
  useRevenue: boolean;
};

export const EventStats: React.FC<EventStatsProps> = ({
  fromTimestamp,
  dailyEndTime,
  toTimestamp,
  groupByDay,
  useRevenue,
}) => {
  const { currentNode } = useCurrentNode();

  return (
    <>
      <Grid item xs={12}>
        <Card>
          <CardContent>
            <EntryStats
              nodeId={currentNode.id}
              dailyEndTime={dailyEndTime}
              fromTimestamp={fromTimestamp}
              toTimestamp={toTimestamp}
              groupByDay={groupByDay}
              useRevenue={useRevenue}
            />
          </CardContent>
        </Card>
      </Grid>
      <Grid item xs={12}>
        <Card>
          <CardContent>
            <TopUpStats
              nodeId={currentNode.id}
              dailyEndTime={dailyEndTime}
              fromTimestamp={fromTimestamp}
              toTimestamp={toTimestamp}
              groupByDay={groupByDay}
              useRevenue={useRevenue}
            />
          </CardContent>
        </Card>
      </Grid>
    </>
  );
};
