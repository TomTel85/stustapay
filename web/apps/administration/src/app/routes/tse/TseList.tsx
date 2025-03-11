import { Tse, selectTseAll, useListTsesQuery } from "@/api";
import { TseRoutes } from "@/app/routes";
import { ListLayout } from "@/components";
import { useCurrentNode, useCurrentUserHasPrivilege, useCurrentUserHasPrivilegeAtNode, useRenderNode } from "@/hooks";
import { Link } from "@mui/material";
import { Edit as EditIcon } from "@mui/icons-material";
import { DataGrid, GridActionsCellItem, GridColDef } from "@stustapay/framework";
import { Loading } from "@stustapay/components";
import * as React from "react";
import { useTranslation } from "react-i18next";
import { Link as RouterLink, useNavigate } from "react-router-dom";

export const TseList: React.FC = () => {
  const { t } = useTranslation();
  const { currentNode } = useCurrentNode();
  const canManageTses = useCurrentUserHasPrivilege(TseRoutes.privilege);
  const canManageTsesAtNode = useCurrentUserHasPrivilegeAtNode(TseRoutes.privilege);
  const navigate = useNavigate();

  const { tses, isLoading: isTsesLoading } = useListTsesQuery(
    { nodeId: currentNode.id },
    {
      selectFromResult: ({ data, ...rest }) => ({
        ...rest,
        tses: data ? selectTseAll(data) : undefined,
      }),
    }
  );
  const { dataGridNodeColumn } = useRenderNode();

  if (isTsesLoading) {
    return <Loading />;
  }

  const columns: GridColDef<Tse>[] = [
    {
      field: "name",
      headerName: t("tse.name"),
      flex: 1,
      renderCell: (params) => (
        <Link component={RouterLink} to={TseRoutes.detail(params.row.id)}>
          {params.row.name}
        </Link>
      ),
    },
    {
      field: "status",
      headerName: t("tse.status"),
    },
    {
      field: "type",
      headerName: t("tse.type"),
      minWidth: 120,
    },
    {
      field: "hashalgo",
      headerName: t("tse.hashalgo"),
      minWidth: 200,
    },
    {
      field: "time_format",
      headerName: t("tse.timeFormat"),
    },
    {
      field: "process_data_encoding",
      headerName: t("tse.processDataEncoding"),
    },
    dataGridNodeColumn,
  ];

  if (canManageTses) {
    columns.push({
      field: "actions",
      type: "actions",
      headerName: t("actions"),
      width: 150,
      getActions: (params) =>
        canManageTsesAtNode(params.row.node_id)
          ? [
              <GridActionsCellItem
                icon={<EditIcon />}
                color="primary"
                label={t("edit")}
                onClick={() => navigate(TseRoutes.edit(params.row.id, params.row.node_id))}
              />,
            ]
          : [],
    });
  }

  return (
    <ListLayout title={t("tse.tses")} routes={TseRoutes}>
      <DataGrid
        autoHeight
        rows={tses ?? []}
        columns={columns}
        disableRowSelectionOnClick
        sx={{ p: 1, boxShadow: (theme) => theme.shadows[1] }}
      />
    </ListLayout>
  );
};
