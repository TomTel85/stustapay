import { selectUserAll, useDeleteUserMutation, useListUsersQuery, User } from "@/api";
import { UserRoutes, UserTagRoutes } from "@/app/routes";
import { ListLayout } from "@/components";
import { useCurrentNode, useCurrentUserHasPrivilege, useCurrentUserHasPrivilegeAtNode, useRenderNode } from "@/hooks";
import { Delete as DeleteIcon, Edit as EditIcon } from "@mui/icons-material";
import { Alert, Box, Link, Stack } from "@mui/material";
import { GridActionsCellItem, GridColDef } from "@stustapay/framework";
import { Loading } from "@stustapay/components";
import { useOpenModal } from "@stustapay/modal-provider";
import * as React from "react";
import { useTranslation } from "react-i18next";
import { Link as RouterLink, useNavigate } from "react-router-dom";
import { RoleAssignmentSummary, useUserRoleAssignments } from "../roleAssignments";
import { UserManagementGrid } from "../UserManagementGrid";

export const UserList: React.FC = () => {
  const { t } = useTranslation();
  const { currentNode } = useCurrentNode();
  const canManageUsers = useCurrentUserHasPrivilege(UserRoutes.privilege);
  const canManageUsersAtNode = useCurrentUserHasPrivilegeAtNode(UserRoutes.privilege);
  const navigate = useNavigate();
  const openModal = useOpenModal();
  const roleAssignments = useUserRoleAssignments();

  const { users, isLoading, error } = useListUsersQuery(
    { nodeId: currentNode.id },
    {
      selectFromResult: ({ currentData, ...rest }) => ({
        ...rest,
        users: currentData ? selectUserAll(currentData) : undefined,
      }),
    }
  );
  const [deleteUser] = useDeleteUserMutation();
  const { dataGridNodeColumn } = useRenderNode();

  if (error) {
    return <Alert severity="error">{t("common.loadingError")}</Alert>;
  }

  if (isLoading || users === undefined) {
    return <Loading />;
  }

  const openConfirmDeleteDialog = (userId: number, userNodeId: number) => {
    openModal({
      type: "confirm",
      title: t("deleteUser"),
      content: t("deleteUserDescription"),
      onConfirm: () => {
        deleteUser({ nodeId: userNodeId, userId })
          .unwrap()
          .catch(() => undefined);
      },
    });
  };

  const columns: GridColDef<User>[] = [
    {
      field: "login",
      headerName: t("userLogin"),
      flex: 1.25,
      minWidth: 140,
      renderCell: (params) => (
        <Link
          component={RouterLink}
          to={UserRoutes.detail(
            params.row.id,
            currentNode.parent_ids.includes(params.row.node_id) ? currentNode.id : params.row.node_id
          )}
          tabIndex={params.tabIndex}
          sx={{ overflowWrap: "anywhere", fontWeight: 500 }}
        >
          {params.row.login}
        </Link>
      ),
    },
    {
      field: "display_name",
      headerName: t("userDisplayName"),
      flex: 1,
      minWidth: 128,
    },
    {
      field: "roles",
      headerName: t("user.roles"),
      flex: 2,
      minWidth: 210,
      valueGetter: (_, user) =>
        (roleAssignments.byUser.get(user.id) ?? []).map((role) => `${role.roleName} ${role.nodeName}`).join("; "),
      renderCell: ({ row }) => (
        <Box component="span" sx={{ overflowWrap: "anywhere" }}>
          {roleAssignments.error ? (
            t("userToRole.loadError")
          ) : roleAssignments.isLoading ? (
            t("userToRole.loadingRoles")
          ) : (
            <RoleAssignmentSummary assignments={roleAssignments.byUser.get(row.id) ?? []} />
          )}
        </Box>
      ),
    },
    {
      field: "email",
      headerName: t("userEmail"),
      flex: 1.25,
      minWidth: 150,
      renderCell: ({ row }) => (
        <Box component="span" sx={{ overflowWrap: "anywhere", color: row.email ? "text.primary" : "text.secondary" }}>
          {row.email || t("user.noEmail")}
        </Box>
      ),
    },
    {
      field: "description",
      headerName: t("userDescription"),
      flex: 1.25,
      minWidth: 110,
    },
    {
      field: "user_tag_id",
      headerName: t("user.tagId"),
      width: 125,
      renderCell: (params) =>
        params.row.user_tag_id && (
          <Link component={RouterLink} to={UserTagRoutes.detail(params.row.user_tag_id)} tabIndex={params.tabIndex}>
            {params.row.user_tag_id}
          </Link>
        ),
    },
    { ...dataGridNodeColumn, minWidth: 125, flex: 1 },
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
                onClick={() => navigate(UserRoutes.edit(params.row.id, params.row.node_id))}
              />,
              <GridActionsCellItem
                icon={<DeleteIcon color="error" />}
                label={t("delete")}
                onClick={() => openConfirmDeleteDialog(params.row.id, params.row.node_id)}
              />,
            ]
          : [],
    });
  }

  return (
    <ListLayout title={t("users")} routes={UserRoutes}>
      <Stack spacing={1.5}>
        {roleAssignments.error != null && <Alert severity="error">{t("userToRole.loadError")}</Alert>}
        <UserManagementGrid rows={users} columns={columns} />
      </Stack>
    </ListLayout>
  );
};
