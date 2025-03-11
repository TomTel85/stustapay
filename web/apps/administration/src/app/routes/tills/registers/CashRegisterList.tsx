import {
  selectCashierById,
  selectTillById,
  selectCashRegisterAll,
  useDeleteRegisterMutation,
  useListCashRegistersAdminQuery,
  useListCashiersQuery,
  useListTillsQuery,
  CashRegister,
} from "@/api";
import { CashierRoutes, CashRegistersRoutes, TillRoutes } from "@/app/routes";
import { ListLayout } from "@/components";
import { useCurrentNode, useCurrentUserHasPrivilege, useCurrentUserHasPrivilegeAtNode, useRenderNode } from "@/hooks";
import { Delete as DeleteIcon, Edit as EditIcon, SwapHoriz as SwapHorizIcon, PersonAdd as PersonAddIcon, MonetizationOn as MonetizationOnIcon } from "@mui/icons-material";
import { Link } from "@mui/material";
import { DataGrid, GridActionsCellItem, GridColDef } from "@stustapay/framework";
import { Loading } from "@stustapay/components";
import { useOpenModal } from "@stustapay/modal-provider";
import { getUserName } from "@stustapay/models";
import * as React from "react";
import { useTranslation } from "react-i18next";
import { Link as RouterLink, useNavigate } from "react-router-dom";

export const CashRegisterList: React.FC = () => {
  const { t } = useTranslation();
  const { currentNode } = useCurrentNode();
  const canManageRegisters = useCurrentUserHasPrivilege(CashRegistersRoutes.privilege);
  const canManageRegistersAtNode = useCurrentUserHasPrivilegeAtNode(CashRegistersRoutes.privilege);
  const navigate = useNavigate();
  const openModal = useOpenModal();
  const { dataGridNodeColumn } = useRenderNode();

  const { data: tills } = useListTillsQuery({ nodeId: currentNode.id });
  const { data: cashiers } = useListCashiersQuery({ nodeId: currentNode.id });
  const { registers, isLoading } = useListCashRegistersAdminQuery(
    { nodeId: currentNode.id },
    {
      selectFromResult: ({ data, ...rest }) => ({
        ...rest,
        registers: data ? selectCashRegisterAll(data) : undefined,
      }),
    }
  );
  const [deleteRegister] = useDeleteRegisterMutation();

  if (isLoading) {
    return <Loading />;
  }

  const openConfirmDeleteDialog = (registerId: number) => {
    openModal({
      type: "confirm",
      title: t("register.deleteRegister"),
      content: t("register.deleteRegisterDescription"),
      onConfirm: () => {
        deleteRegister({ nodeId: currentNode.id, registerId })
          .unwrap()
          .catch(() => undefined);
      },
    });
  };

  const renderTill = (id: number | null) => {
    if (id == null || !tills) {
      return "";
    }
    const till = selectTillById(tills, id);
    if (!till) {
      return "";
    }

    return (
      <Link component={RouterLink} to={TillRoutes.detail(till.id)}>
        {till.name}
      </Link>
    );
  };

  const renderCashier = (id: number | null) => {
    if (id == null || !cashiers) {
      return "";
    }
    const cashier = selectCashierById(cashiers, id);
    if (!cashier) {
      return "";
    }

    return (
      <Link component={RouterLink} to={CashierRoutes.detail(cashier.id, cashier.node_id)}>
        {getUserName(cashier)}
      </Link>
    );
  };

  const columns: GridColDef<CashRegister>[] = [
    {
      field: "name",
      headerName: t("register.name"),
      flex: 1,
      renderCell: (params) => (
        <Link component={RouterLink} to={CashRegistersRoutes.detail(params.row.id, params.row.node_id)}>
          {params.row.name}
        </Link>
      ),
    },
    {
      field: "current_cashier_id",
      headerName: t("register.currentCashier"),
      width: 200,
      renderCell: (params) => renderCashier(params.row.current_cashier_id),
    },
    {
      field: "current_till_id",
      headerName: t("register.currentTill"),
      width: 200,
      renderCell: (params) => renderTill(params.row.current_till_id),
    },
    {
      field: "balance",
      headerName: t("register.currentBalance"),
      type: "currency",
      width: 200,
    },
    dataGridNodeColumn,
  ];

  if (canManageRegisters) {
    columns.push({
      field: "actions",
      type: "actions",
      headerName: t("actions"),
      width: 150,
      getActions: (params) =>
        canManageRegistersAtNode(params.row.node_id)
          ? [
              <GridActionsCellItem
                icon={<SwapHorizIcon />}
                color="primary"
                label={t("register.transfer")}
                disabled={params.row.current_cashier_id == null}
                onClick={() => navigate(`${CashRegistersRoutes.detail(params.row.id)}/transfer`)}
              />,
              <GridActionsCellItem
                icon={<PersonAddIcon />}
                color="primary"
                label={t("register.assign")}
                disabled={params.row.current_cashier_id != null}
                onClick={() => navigate(`${CashRegistersRoutes.detail(params.row.id)}/assign`)}
              />,
              <GridActionsCellItem
                icon={<MonetizationOnIcon />}
                color="primary"
                label={t("register.modifyBalance")}
                disabled={params.row.current_cashier_id == null}
                onClick={() => navigate(`${CashRegistersRoutes.detail(params.row.id)}/modify-balance`)}
              />,
              <GridActionsCellItem
                icon={<EditIcon />}
                color="primary"
                label={t("edit")}
                onClick={() => navigate(CashRegistersRoutes.edit(params.row.id))}
              />,
              <GridActionsCellItem
                icon={<DeleteIcon />}
                color="error"
                label={t("delete")}
                onClick={() => openConfirmDeleteDialog(params.row.id)}
              />,
            ]
          : [],
    });
  }

  return (
    <ListLayout title={t("register.registers")} routes={CashRegistersRoutes}>
      <DataGrid
        autoHeight
        rows={registers ?? []}
        columns={columns}
        disableRowSelectionOnClick
        sx={{ p: 1, boxShadow: (theme) => theme.shadows[1] }}
      />
    </ListLayout>
  );
};
