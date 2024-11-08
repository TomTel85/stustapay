import { CashierShiftStats, useGetCashierShiftStatsQuery } from "@/api";
import { OrderTable } from "@/components/features";
import { useCurrentNode } from "@/hooks";
import { TabContext, TabList, TabPanel } from "@mui/lab";
import { Box, Tab } from "@mui/material";
import { DataGrid, Loading, GridColDef } from "@stustapay/components";
import * as React from "react";
import { useTranslation } from "react-i18next";

export interface CashierShiftStatsOverview {
  cashierId: number;
  shiftId?: number;
}

type ArrElement<ArrType> = ArrType extends readonly (infer ElementType)[] ? ElementType : never;

export const CashierShiftStatsOverview: React.FC<CashierShiftStatsOverview> = ({ cashierId, shiftId }) => {
  const { currentNode } = useCurrentNode();
  const { data } = useGetCashierShiftStatsQuery({ nodeId: currentNode.id, cashierId, shiftId });
  const { t } = useTranslation();
  const [activeTab, setActiveTab] = React.useState("products");

  if (!data) {
    return <Loading />;
  }

  const columns: GridColDef<ArrElement<CashierShiftStats["booked_products"]>>[] = [
    {
      field: "product.name",
      headerName: t("product.name") as string,
      flex: 1,
    },
    {
      field: "quantity",
      headerName: t("shift.soldProductQuantity") as string,
      type: "number",
      width: 150,
    },
  ];

  return (
    <TabContext value={activeTab}>
      <Box sx={{ borderBottom: 1, borderColor: "divider" }}>
        <TabList onChange={(e, val) => setActiveTab(val)}>
          <Tab label={t("shift.bookedProducts")} value="products" />
          <Tab label={t("shift.orders")} value="orders" />
        </TabList>
      </Box>
      <TabPanel value="products">
        <DataGrid
          autoHeight
          rows={data.booked_products}
          columns={columns}
          getRowId={(row) => row.product.id}
          disableRowSelectionOnClick
          sx={{ mt: 2, p: 1, boxShadow: (theme) => theme.shadows[1] }}
        />
      </TabPanel>
      <TabPanel value="orders">{activeTab === "orders" && <OrderTable orders={data.orders} />}</TabPanel>
    </TabContext>
  );
};
