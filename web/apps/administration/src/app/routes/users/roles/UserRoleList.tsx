import { UserRole, selectUserRoleAll, useDeleteUserRoleMutation, useListUserRolesQuery } from "@/api";
import { UserRoleRoutes } from "@/app/routes";
import { ListLayout } from "@/components";
import { useCurrentNode, useCurrentUserHasPrivilege, useCurrentUserHasPrivilegeAtNode, useRenderNode } from "@/hooks";
import { Delete as DeleteIcon, Edit as EditIcon } from "@mui/icons-material";
import { Alert, Link } from "@mui/material";
import { GridActionsCellItem, GridColDef } from "@stustapay/framework";
import { Loading } from "@stustapay/components";
import { useOpenModal } from "@stustapay/modal-provider";
import * as React from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, Link as RouterLink } from "react-router-dom";
import { UserManagementGrid } from "../UserManagementGrid";

export const UserRoleList: React.FC = () => {
  const { t } = useTranslation();
  const canManageUsers = useCurrentUserHasPrivilege(UserRoleRoutes.privilege);
  const canManageUsersAtNode = useCurrentUserHasPrivilegeAtNode(UserRoleRoutes.privilege);
  const { currentNode } = useCurrentNode();
  const navigate = useNavigate();
  const openModal = useOpenModal();

  const { userRoles, error } = useListUserRolesQuery(
    { nodeId: currentNode.id },
    {
      selectFromResult: ({ currentData, ...rest }) => ({
        ...rest,
        userRoles: currentData ? selectUserRoleAll(currentData) : undefined,
      }),
    }
  );
  const [deleteUserRole] = useDeleteUserRoleMutation();
  const { dataGridNodeColumn } = useRenderNode();

  if (error) {
    return <Alert severity="error">{t("common.loadingError")}</Alert>;
  }

  if (!userRoles) {
    return <Loading />;
  }

  const openConfirmDeleteDialog = (role: UserRole) => {
    openModal({
      type: "confirm",
      title: t("userRole.delete"),
      content: t("userRole.deleteDescription", { name: role.name }),
      onConfirm: () => {
        deleteUserRole({ nodeId: currentNode.id, userRoleId: role.id })
          .unwrap()
          .catch(() => undefined);
      },
    });
  };

  const columns: GridColDef<UserRole>[] = [
    {
      field: "name",
      headerName: t("userRole.name"),
      renderCell: (params) => (
        <Link component={RouterLink} to={UserRoleRoutes.detail(params.row.id)} tabIndex={params.tabIndex}>
          {params.row.name}
        </Link>
      ),
      minWidth: 150,
      flex: 1.5,
    },
    {
      field: "privileges",
      headerName: t("userRole.privilegeCount"),
      type: "number",
      width: 155,
      valueGetter: (_, row) => row.privileges.length,
      getApplyQuickFilterFn: (value: string) => (_count, row) =>
        row.privileges.some((privilege) => privilege.includes(value.toLowerCase())),
    },
    {
      field: "is_privileged",
      headerName: t("userRole.isPrivileged"),
      type: "boolean",
      width: 115,
    },
    { ...dataGridNodeColumn, flex: 1 },
  ];

  if (canManageUsers) {
    columns.push({
      field: "actions",
      type: "actions",
      headerName: t("actions"),
      width: 100,
      getActions: (params) =>
        canManageUsersAtNode(params.row.node_id)
          ? [
              <GridActionsCellItem
                icon={<EditIcon />}
                color="primary"
                label={t("edit")}
                onClick={() => navigate(UserRoleRoutes.edit(params.row.id))}
              />,
              <GridActionsCellItem
                icon={<DeleteIcon color="error" />}
                label={t("userRole.delete")}
                onClick={() => openConfirmDeleteDialog(params.row)}
              />,
            ]
          : [],
    });
  }

  return (
    <ListLayout title={t("userRoles")} routes={UserRoleRoutes}>
      <UserManagementGrid rows={userRoles} columns={columns} />
    </ListLayout>
  );
};
