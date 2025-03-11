import {
  PayoutRunWithStats,
  selectPayoutRunAll,
  selectUserById,
  useListPayoutRunsQuery,
  useListUsersQuery,
} from "@/api";
import { PayoutRunRoutes, UserRoutes } from "@/app/routes";
import { ListLayout } from "@/components";
import { useCurrentNode } from "@/hooks";
import { Link } from "@mui/material";
import { DataGrid, GridColDef } from "@stustapay/framework";
import { Loading } from "@stustapay/components";
import * as React from "react";
import { Check as CheckIcon, Delete as DeleteIcon } from "@mui/icons-material";
import { useTranslation } from "react-i18next";
import { Link as RouterLink } from "react-router-dom";
import { PendingPayoutDetail } from "./PendingPayoutDetail";
import { getUserName } from "@stustapay/models";

export const PayoutRunList: React.FC = () => {
  const { t } = useTranslation();
  const { currentNode } = useCurrentNode();

  const { payoutRuns, isLoading: isPayoutRunsLoading } = useListPayoutRunsQuery(
    { nodeId: currentNode.id },
    {
      selectFromResult: ({ data, ...rest }) => ({
        ...rest,
        payoutRuns: data ? selectPayoutRunAll(data) : undefined,
      }),
    }
  );
  const { data: users } = useListUsersQuery({ nodeId: currentNode.id });

  if (isPayoutRunsLoading) {
    return <Loading />;
  }

  const columns: GridColDef<PayoutRunWithStats>[] = [
    {
      field: "id",
      headerName: t("payoutRun.id"),
      minWidth: 50,
      renderCell: (params) => (
        <Link component={RouterLink} to={PayoutRunRoutes.detail(params.row.id)}>
          {params.row.id}
        </Link>
      ),
    },
    {
      field: "created_by",
      headerName: t("payoutRun.createdBy"),
      flex: 1,
      renderCell: (params) =>
        params.row.created_by && (
          <Link component={RouterLink} to={UserRoutes.detail(params.row.created_by)}>
            {users && getUserName(selectUserById(users, params.row.created_by))}
          </Link>
        ),
    },
    {
      field: "created_at",
      headerName: t("payoutRun.createdAt"),
      type: "dateTime",
      valueGetter: (value) => new Date(value),
      minWidth: 200,
    },
    {
      field: "done",
      headerName: t("common.status"),
      minWidth: 100,
      renderCell: (params) => {
        if (params.row.done) {
          return (
            <>
              <CheckIcon />
              {t("payoutRun.done")}
            </>
          );
        }
        if (params.row.revoked) {
          return (
            <>
              <DeleteIcon />
              {t("payoutRun.revoked")}
            </>
          );
        }
        return "";
      },
    },
    {
      field: "total_payout_amount",
      headerName: t("payoutRun.totalPayoutAmount"),
      type: "currency",
      minWidth: 150,
    },
    {
      field: "total_donation_amount",
      headerName: t("payoutRun.totalDonationAmount"),
      type: "currency",
      minWidth: 150,
    },
    {
      field: "n_payouts",
      headerName: t("payoutRun.nPayouts"),
      type: "number",
      minWidth: 150,
    },
  ];

  return (
    <ListLayout title={t("payoutRun.payoutRuns")} routes={PayoutRunRoutes}>
      <PendingPayoutDetail />
      <DataGrid
        autoHeight
        rows={payoutRuns ?? []}
        columns={columns}
        initialState={{
          sorting: {
            sortModel: [{ field: "created_at", sort: "desc" }],
          },
        }}
        disableRowSelectionOnClick
        sx={{ p: 1, boxShadow: (theme) => theme.shadows[1] }}
      />
    </ListLayout>
  );
};
