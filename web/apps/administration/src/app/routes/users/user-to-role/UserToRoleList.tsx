import {
  selectUserById,
  selectUserRoleById,
  findNode,
  useGetUserQuery,
  useListUsersQuery,
  useListUserRolesQuery,
  useListUserToRoleQuery,
  UserToRoles,
  useUpdateUserToRolesMutation,
  useNodeTree,
} from "@/api";
import { UserRoleRoutes, UserRoutes, UserToRoleRoutes } from "@/app/routes";
import { ListLayout } from "@/components";
import { useCurrentNode, useCurrentUserHasPrivilege } from "@/hooks";
import { Delete as DeleteIcon, Edit as EditIcon } from "@mui/icons-material";
import { Alert, Box, Link } from "@mui/material";
import { DataGrid, GridActionsCellItem, GridColDef } from "@stustapay/framework";
import { Loading } from "@stustapay/components";
import { useOpenModal } from "@stustapay/modal-provider";
import { getUserName } from "@stustapay/models";
import * as React from "react";
import { useTranslation } from "react-i18next";
import { Link as RouterLink, useNavigate } from "react-router-dom";

type UserLinkCellProps = {
  currentNodeId: number;
  userId: number;
  users?: Parameters<typeof selectUserById>[0];
};

const UserLinkCell: React.FC<UserLinkCellProps> = ({ currentNodeId, userId, users }) => {
  const cachedUser = users ? selectUserById(users, userId) : undefined;
  const { data: fetchedUser } = useGetUserQuery(
    { nodeId: currentNodeId, userId },
    { skip: cachedUser != null }
  );

  const user = cachedUser ?? fetchedUser;
  if (!user) {
    return <>{userId}</>;
  }

  return (
    <Link component={RouterLink} to={UserRoutes.detail(userId, currentNodeId)}>
      {getUserName(user)}
    </Link>
  );
};

export const UserToRoleList: React.FC = () => {
  const { t } = useTranslation();
  const { currentNode } = useCurrentNode();
  const canManageNode = useCurrentUserHasPrivilege(UserToRoleRoutes.privilege);

  const { currentData: userToRoles, error: assignmentsError } = useListUserToRoleQuery({ nodeId: currentNode.id });
  const { currentData: users, error: usersError } = useListUsersQuery({ nodeId: currentNode.id });
  const { currentData: userRoles, error: rolesError } = useListUserRolesQuery({ nodeId: currentNode.id });
  const [updateUserToRoles] = useUpdateUserToRolesMutation();
  const { root } = useNodeTree();
  const openModal = useOpenModal();
  const navigate = useNavigate();

  if (assignmentsError || usersError || rolesError) {
    return <Alert severity="error">{t("common.loadingError")}</Alert>;
  }

  if (!userToRoles || !users || !userRoles) {
    return <Loading />;
  }

  const openConfirmDeleteDialog = (userToRoles: UserToRoles) => {
    if (userToRoles.node_id !== currentNode.id) {
      return;
    }
    openModal({
      type: "confirm",
      title: t("userToRole.deleteAssociation"),
      content: t("userToRole.deleteAssociationDescription"),
      onConfirm: () => {
        updateUserToRoles({
          nodeId: currentNode.id,
          newUserToRoles: { user_id: userToRoles.user_id, role_ids: [] },
        })
          .unwrap()
          .catch(() => undefined);
      },
    });
  };

  const renderUser = (id: number) => {
    return <UserLinkCell currentNodeId={currentNode.id} userId={id} users={users} />;
  };

  const renderRoles = (ids: number[]) => {
    if (!userRoles) {
      return "";
    }
    const roles = ids.map((id) => selectUserRoleById(userRoles, id));
    roles.sort((lhs, rhs) =>
      (lhs?.name ?? "").localeCompare(rhs?.name ?? "")
    );

    return (
      <Box sx={{ display: "flex", gap: 1, flexWrap: "wrap" }}>
        {roles.map(
          (role) =>
            role != null && (
              <Link key={role.id} component={RouterLink} to={UserRoleRoutes.detail(role.id, role.node_id)}>
                {role.name}
              </Link>
            )
        )}
      </Box>
    );
  };

  const columns: GridColDef<UserToRoles>[] = [
    {
      field: "user_id",
      headerName: t("userToRole.user"),
      flex: 1,
      valueGetter: (_, row) =>
        (users && getUserName(selectUserById(users, row.user_id))) || String(row.user_id),
      renderCell: (params) => renderUser(params.row.user_id),
    },
    {
      field: "role_ids",
      headerName: t("userToRole.role"),
      flex: 1,
      valueGetter: (_, row) =>
        row.role_ids.map((id) => (userRoles && selectUserRoleById(userRoles, id)?.name) || `#${id}`).join(", "),
      renderCell: (params) => renderRoles(params.row.role_ids),
    },
    {
      field: "node_name",
      headerName: t("common.definedAtNode"),
      minWidth: 180,
      valueGetter: (_, row) => findNode(row.node_id, root)?.name ?? `#${row.node_id}`,
      renderCell: ({ row, value }) => row.node_id === currentNode.id ? value : t("userToRole.inheritedAt", { node: value }),
    },
  ];

  if (canManageNode) {
    columns.push({
      field: "actions",
      type: "actions",
      headerName: t("actions"),
      width: 150,
      getActions: (params) =>
        currentNode.id === params.row.node_id
          ? [
              <GridActionsCellItem
                icon={<EditIcon />}
                color="primary"
                label={t("edit")}
                onClick={() => navigate(UserToRoleRoutes.edit(params.row.user_id))}
              />,
              <GridActionsCellItem
                icon={<DeleteIcon />}
                color="primary"
                label={t("delete")}
                onClick={() => openConfirmDeleteDialog(params.row)}
              />,
            ]
          : [],
    });
  }

  return (
    <ListLayout title={t("userToRoles")} routes={UserToRoleRoutes}>
      <DataGrid
        autoHeight
        showToolbar
        disableColumnFilter={false}
        getRowId={(row) => `${row.node_id}-${row.user_id}`}
        rows={userToRoles ?? []}
        columns={columns}
        disableRowSelectionOnClick
        sx={{ p: 1, boxShadow: (theme) => theme.shadows[1] }}
        initialState={{
          sorting: {
            sortModel: [{ field: "user_id", sort: "asc" }],
          },
        }}
      />
    </ListLayout>
  );
};
