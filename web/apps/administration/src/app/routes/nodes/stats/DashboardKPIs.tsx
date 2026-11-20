import * as React from "react";
import { Box, Grid, Skeleton, Stack, Typography } from "@mui/material";
import { useCurrencyFormatter, useCurrentNode } from "@/hooks";
import type {
  GetDashboardOverviewApiResponse,
  GetPaymentMethodStatsApiResponse,
  GetProductStatsApiResponse,
  RevenuePrediction,
} from "@/api";
import { useTranslation } from "react-i18next";

type Metric = { label: string; value: string };

const Metrics: React.FC<{ items: Metric[]; headline?: boolean }> = ({ items, headline = false }) => (
  <Grid component="dl" container spacing={2} sx={{ m: 0 }}>
    {items.map(({ label, value }) => (
      <Grid component="div" key={label} size={{ xs: 6, md: headline ? 6 : 3 }} sx={{ minWidth: 0 }}>
        <Typography component="dt" variant="body2" color="text.secondary">
          {label}
        </Typography>
        <Typography
          component="dd"
          sx={{
            m: 0,
            fontWeight: 600,
            fontSize: headline ? { xs: "1.375rem", md: "1.75rem" } : "1.125rem",
            fontVariantNumeric: "tabular-nums",
            overflowWrap: "anywhere",
          }}
        >
          {value}
        </Typography>
      </Grid>
    ))}
  </Grid>
);

type DashboardKPIsProps = {
  productId?: number;
  isLoading?: boolean;
  overview?: GetDashboardOverviewApiResponse;
  productStats?: GetProductStatsApiResponse;
};

export const DashboardKPIs: React.FC<DashboardKPIsProps> = ({ productId, isLoading, overview, productStats }) => {
  const { currentNode } = useCurrentNode();
  const formatCurrency = useCurrencyFormatter();
  const { t, i18n } = useTranslation();
  const formatCount = (count: number) => count.toLocaleString(i18n.language);

  if (isLoading) return <Skeleton variant="rounded" height={72} />;

  if (productId !== undefined && productStats) {
    const product =
      productStats.product_overall_stats.find((item) => item.product_id === productId) ??
      productStats.deposit_overall_stats.find((item) => item.product_id === productId);
    return product ? (
      <Metrics
        headline
        items={[
          { label: t("overview.productRevenue"), value: formatCurrency(product.revenue) },
          { label: t("overview.productQuantitySold"), value: formatCount(product.count) },
        ]}
      />
    ) : (
      <Typography variant="body2" color="text.secondary">
        {t("overview.noProductSales")}
      </Typography>
    );
  }
  if (!overview || productId !== undefined) return null;

  return (
    <Stack spacing={2}>
      <Metrics
        headline
        items={[
          { label: t("overview.totalRevenue"), value: formatCurrency(overview.total_revenue) },
          { label: t("overview.guestsWithOrders"), value: formatCount(overview.guests_with_orders) },
        ]}
      />
      {currentNode.event != null && (
        <>
          <Metrics items={[{ label: t("overview.guestsPaidOut"), value: formatCount(overview.guests_paid_out) }]} />
          <Box sx={{ borderTop: 1, borderColor: "divider", pt: 2 }}>
            <Typography component="h3" variant="subtitle2">
              {t("overview.currentBalances")}
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
              {t("overview.currentBalancesScope")}
            </Typography>
            <Metrics
              items={[
                { label: t("overview.totalGuestCredit"), value: formatCurrency(overview.total_guest_credit) },
                { label: t("overview.guestsWithCredit"), value: formatCount(overview.guests_with_credit) },
                { label: t("overview.onlineDonation"), value: formatCurrency(overview.online_donation) },
                { label: t("overview.onlineForPayout"), value: formatCurrency(overview.online_for_payout) },
              ]}
            />
          </Box>
        </>
      )}
    </Stack>
  );
};

const paymentLabels: Record<string, string> = {
  cash: "overview.cash",
  sumup: "overview.cashless",
  sumup_online: "overview.onlinePayment",
};

export const PaymentMethodTotals: React.FC<{ data?: GetPaymentMethodStatsApiResponse }> = ({ data }) => {
  const { t } = useTranslation();
  const formatCurrency = useCurrencyFormatter();
  const methods = data?.methods.filter(({ payment_method }) => payment_method !== "tag");
  if (!methods) return null;

  return (
    <Box sx={{ borderTop: 1, borderColor: "divider", pt: 2 }}>
      <Typography component="h3" variant="subtitle2" sx={{ mb: 1 }}>
        {t("overview.topUpPaymentMethods")}
      </Typography>
      {methods.length > 0 ? (
        <Metrics
          items={methods.map(({ payment_method, revenue }) => ({
            label: paymentLabels[payment_method] ? t(paymentLabels[payment_method]) : payment_method,
            value: formatCurrency(revenue),
          }))}
        />
      ) : (
        <Typography variant="body2" color="text.secondary">
          {t("overview.noDataAvailable")}
        </Typography>
      )}
    </Box>
  );
};

export const ForecastMetrics: React.FC<{ prediction: RevenuePrediction }> = ({ prediction }) => {
  const { t } = useTranslation();
  const formatCurrency = useCurrencyFormatter();
  const items = [
    { label: t("overview.predictedEndOfDay"), value: formatCurrency(prediction.predicted_end_of_day) },
    { label: t("overview.predictedEventTotal"), value: formatCurrency(prediction.predicted_event_total) },
  ];
  if (prediction.historical_revenue_per_visitor != null) {
    items.push({
      label: t("overview.revenuePerVisitor"),
      value: formatCurrency(prediction.historical_revenue_per_visitor),
    });
  }
  if (prediction.visitor_based_prediction != null) {
    items.push({
      label: t("overview.visitorBasedPrediction"),
      value: formatCurrency(prediction.visitor_based_prediction),
    });
  }

  return <Metrics items={items} />;
};
