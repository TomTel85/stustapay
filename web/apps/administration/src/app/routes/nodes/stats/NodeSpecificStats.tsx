import * as React from "react";
import { DateTime } from "luxon";
import { useTranslation } from "react-i18next";
import { Alert, AlertTitle, Card, CardContent, Grid, Skeleton, Typography } from "@mui/material";
import { useCurrencyFormatter, useCurrentNode } from "@/hooks";
import { DailyStatsTable, HourlyGraph, NodeSelect } from "@/components";
import { useGetProductStatsQuery, useListProductsQuery, selectProductById, ProductStats } from "@/api";
import { DatumValue, ResponsiveLine } from "@nivo/line";

const IndividualProductStats: React.FC<{
  nodeId: number;
  data: ProductStats;
  useRevenue: boolean;
}> = ({ data, nodeId, useRevenue }) => {
  const { data: products, isLoading: isProductsLoading } = useListProductsQuery({
    nodeId: nodeId,
  });

  const hourlyData = React.useMemo(() => {
    if (!products) {
      return [];
    }

    return data.product_hourly_intervals.map((productData) => ({
      id: selectProductById(products, productData.product_id)?.name ?? "",
      data: productData.intervals.map((interval) => ({
        x: DateTime.fromISO(interval.to_time).toJSDate(),
        y: useRevenue ? interval.revenue : interval.count,
      })),
    }));
  }, [data, products, useRevenue]);

  const formatCurrency = useCurrencyFormatter();

  if (isProductsLoading) {
    return (
      <Grid item xs={12}>
        <Skeleton variant="rounded" height={300} />
      </Grid>
    );
  }

  if (!products) {
    return (
      <Alert severity="error">
        <AlertTitle>Error loading list of products</AlertTitle>
      </Alert>
    );
  }

  return (
    <Grid container spacing={2}>
      <Grid item xs={12} height={300}>
        <ResponsiveLine
          animate={false}
          data={hourlyData}
          colors={{ scheme: "category10" }}
          axisBottom={{
            format: "%a %H:%M",
            legend: "time",
            tickRotation: 0,
            legendPosition: "middle",
            legendOffset: 35,
          }}
          axisLeft={{
            legend: useRevenue ? "revenue per hour" : "count per hour",
            legendPosition: "middle",
            legendOffset: useRevenue ? -80 : -40,
            format: (value) => {
              if (useRevenue) {
                return formatCurrency(value);
              } else {
                return value;
              }
            },
          }}
          xFormat={(value: DatumValue) => DateTime.fromJSDate(value as Date).toISO() ?? ""}
          enableSlices="x"
          enableTouchCrosshair
          curve="monotoneX"
          margin={{
            bottom: 40,
            left: useRevenue ? 90 : 80,
            right: 150,
            top: 20,
          }}
          useMesh
          xScale={{
            type: "time",
            useUTC: false,
          }}
          yScale={{
            type: "linear",
            min: "auto",
            max: "auto",
          }}
          legends={[
            {
              anchor: "bottom-right",
              direction: "column",
              translateX: 90,
              itemDirection: "left-to-right",
              itemWidth: 80,
              itemHeight: 20,
              symbolSize: 12,
              symbolShape: "circle",
            },
          ]}
        />
      </Grid>
    </Grid>
  );
};

export type NodeSpecificStatsProps = {
  fromTimestamp?: DateTime;
  toTimestamp?: DateTime;
  dailyEndTime: string;
  groupByDay: boolean;
  useRevenue: boolean;
};

export const NodeSpecificStats: React.FC<NodeSpecificStatsProps> = ({
  fromTimestamp,
  toTimestamp,
  dailyEndTime,
  groupByDay,
  useRevenue,
}) => {
  const { currentNode } = useCurrentNode();
  const [node, setNode] = React.useState(currentNode);
  const { data: productStats, isLoading: isStatsLoading } = useGetProductStatsQuery({
    nodeId: node.id,
    fromTimestamp: fromTimestamp?.toISO() ?? undefined,
    toTimestamp: toTimestamp?.toISO() ?? undefined,
  });

  if (isStatsLoading) {
    return (
      <Grid item xs={12}>
        <Skeleton variant="rounded" height={300} />
      </Grid>
    );
  }

  if (!productStats) {
    return (
      <Alert severity="error">
        <AlertTitle>Error loading stats</AlertTitle>
      </Alert>
    );
  }

  return (
    <Grid item xs={12}>
      <Card>
        <CardContent>
          <NodeSelect label="Node" value={node} onChange={(val) => val && setNode(val)} />
          <Typography variant="h5">Total revenue through sales</Typography>
          <Grid container spacing={2}>
            <Grid item xs={12} md={9} height={300}>
              <HourlyGraph dailyEndTime={dailyEndTime} groupByDay={groupByDay} useRevenue={true} data={productStats} />
            </Grid>
            <Grid item xs={12} md={3} height={300}>
              <DailyStatsTable data={productStats} useRevenue={true} />
            </Grid>
          </Grid>
          <IndividualProductStats nodeId={node.id} data={productStats} useRevenue={useRevenue} />
        </CardContent>
      </Card>
    </Grid>
  );
};
