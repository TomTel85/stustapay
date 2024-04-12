import { CustomerRead } from "@/api";
import { CustomerRoutes, PayoutRunRoutes, UserTagRoutes } from "@/app/routes";
import { useCurrencyFormatter, useRenderNode } from "@/hooks";
import { Link } from "@mui/material";
import { DataGrid, GridColDef } from "@mui/x-data-grid";
import { formatUserTagUid } from "@stustapay/models";
import * as React from "react";
import { useTranslation } from "react-i18next";
import { Link as RouterLink } from "react-router-dom";

export interface CustomerTableProps {
  customers: CustomerRead[];
}

export const CustomerTable: React.FC<CustomerTableProps> = ({ customers }) => {
  const { t } = useTranslation();
  const formatCurrency = useCurrencyFormatter();
  const renderNode = useRenderNode();

  const columns: GridColDef<CustomerRead>[] = [
    {
      field: "id",
      headerName: t("account.id") as string,
      renderCell: (params) => (
        <Link component={RouterLink} to={CustomerRoutes.detail(params.row.id)}>
          {params.row.id}
        </Link>
      ),
    },
    {
      field: "name",
      headerName: t("account.name") as string,
    },
    {
      field: "user_tag_uid_hex",
      headerName: t("account.user_tag_uid") as string,
      align: "right",
      renderCell: (params) => (
        <Link component={RouterLink} to={UserTagRoutes.detail(params.row.user_tag_uid_hex)}>
          {formatUserTagUid(params.row.user_tag_uid_hex)}
        </Link>
      ),
      width: 100,
    },
    {
      field: "comment",
      headerName: t("account.comment") as string,
    },
    {
      field: "balance",
      headerName: t("account.balance") as string,
      type: "number",
      minWidth: 80,
      valueFormatter: ({ value }) => value && formatCurrency(value),
    },
    {
      field: "vouchers",
      headerName: t("account.vouchers") as string,
      type: "number",
      minWidth: 80,
    },
    {
      field: "email",
      headerName: t("common.email") as string,
    },
    {
      field: "account_name",
      headerName: t("customer.bankAccountHolder") as string,
    },
    {
      field: "iban",
      headerName: t("customer.iban") as string,
    },
    {
      field: "donation",
      headerName: t("customer.donation") as string,
      type: "number",
      valueFormatter: ({ value }) => (value != null ? formatCurrency(value) : "-"),
    },
    {
      field: "payout_run_id",
      headerName: t("customer.payoutRun") as string,
      renderCell: (params) => (
        <Link component={RouterLink} to={PayoutRunRoutes.detail(params.row.payout_run_id)}>
          {params.row.payout_run_id}
        </Link>
      ),
      minWidth: 80,
    },
    {
      field: "node_id",
      headerName: t("common.definedAtNode") as string,
      valueFormatter: ({ value }) => renderNode(value),
      flex: 1,
    },
  ];

  return (
    <DataGrid
      autoHeight
      rows={customers}
      columns={columns}
      disableRowSelectionOnClick
      sx={{ p: 1, boxShadow: (theme) => theme.shadows[1] }}
    />
  );
};
