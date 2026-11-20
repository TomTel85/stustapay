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
import { Add as AddIcon, Delete as DeleteIcon, Edit as EditIcon } from "@mui/icons-material";
import { Alert, Box, Link, Typography } from "@mui/material";
import { GridActionsCellItem, GridColDef } from "@stustapay/framework";
import { Loading } from "@stustapay/components";
import { useOpenModal } from "@stustapay/modal-provider";
import { getUserName } from "@stustapay/models";
import * as React from "react";
import { useTranslation } from "react-i18next";
import { Link as RouterLink, useNavigate } from "react-router-dom";
import { UserManagementGrid } from "../UserManagementGrid";

type UserLinkCellProps = {
  currentNodeId: number;
  userId: number;
  tabIndex: number;
  users?: Parameters<typeof selectUserById>[0];
};

const UserLinkCell: React.FC<UserLinkCellProps> = ({ currentNodeId, userId, tabIndex, users }) => {
  const cachedUser = users ? selectUserById(users, userId) : undefined;
  const { data: fetchedUser } = useGetUserQuery({ nodeId: currentNodeId, userId }, { skip: cachedUser != null });

  const user = cachedUser ?? fetchedUser;
  if (!user) {
    return <>{userId}</>;
  }

  return (
    <Link component={RouterLink} to={UserRoutes.detail(userId, currentNodeId)} tabIndex={tabIndex}>
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
    return <Alert severity="error">{t("userToRole.loadError")}</Alert>;
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

  const renderRoles = (ids: number[], tabIndex: number) => {
    if (ids.length === 0) {
      return (
        <Typography variant="body2" color="text.secondary">
          {t("userToRole.noRoles")}
        </Typography>
      );
    }
    const roles = ids
      .map((id) => {
        const role = selectUserRoleById(userRoles, id);
        return { id, role, name: role?.name ?? `#${id}` };
      })
      .sort((lhs, rhs) => lhs.name.localeCompare(rhs.name));

    return (
      <Box
        component="ul"
        role="list"
        sx={{ display: "flex", gap: 0.5, flexWrap: "wrap", listStyle: "none", m: 0, p: 0 }}
      >
        {roles.map(({ id, role, name }) => (
          <Box
            key={id}
            component="li"
            sx={{
              minWidth: 0,
              maxWidth: "100%",
              "& > *": {
                display: "block",
                border: 1,
                borderColor: "divider",
                borderRadius: 1,
                px: 1,
                py: 0.25,
                whiteSpace: "normal",
                overflowWrap: "anywhere",
              },
            }}
          >
            {role ? (
              <Link component={RouterLink} to={UserRoleRoutes.detail(id, role.node_id)} tabIndex={tabIndex}>
                {name}
              </Link>
            ) : (
              <Box component="span" sx={{ color: "text.secondary" }}>
                {name}
              </Box>
            )}
          </Box>
        ))}
      </Box>
    );
  };

  const columns: GridColDef<UserToRoles>[] = [
    {
      field: "user_id",
      headerName: t("userToRole.user"),
      flex: 1,
      minWidth: 160,
      valueGetter: (_, row) => (users && getUserName(selectUserById(users, row.user_id))) || String(row.user_id),
      renderCell: ({ row, tabIndex }) => (
        <UserLinkCell currentNodeId={currentNode.id} userId={row.user_id} tabIndex={tabIndex} users={users} />
      ),
    },
    {
      field: "role_ids",
      headerName: t("user.roles"),
      flex: 1.5,
      minWidth: 160,
      valueGetter: (_, row) =>
        row.role_ids.map((id) => (userRoles && selectUserRoleById(userRoles, id)?.name) || `#${id}`).join(", "),
      renderCell: ({ row, tabIndex }) => renderRoles(row.role_ids, tabIndex),
    },
    {
      field: "node_name",
      headerName: t("common.definedAtNode"),
      flex: 0.75,
      minWidth: 140,
      valueGetter: (_, row) => findNode(row.node_id, root)?.name ?? `#${row.node_id}`,
      renderCell: ({ row, value }) =>
        row.node_id === currentNode.id ? (
          value
        ) : (
          <Typography variant="body2" color="text.secondary">
            {t("userToRole.inheritedAt", { node: value })}
          </Typography>
        ),
    },
  ];

  if (canManageNode) {
    columns.push({
      field: "actions",
      type: "actions",
      headerName: t("actions"),
      width: 100,
      getActions: (params) =>
        currentNode.id === params.row.node_id
          ? [
              <GridActionsCellItem
                icon={<EditIcon />}
                color="primary"
                label={t("edit")}
                onClick={() => navigate(UserToRoleRoutes.edit(params.row.user_id, currentNode.id))}
              />,
              <GridActionsCellItem
                icon={<DeleteIcon color="error" />}
                label={t("userToRole.deleteAssociation")}
                onClick={() => openConfirmDeleteDialog(params.row)}
              />,
            ]
          : [],
    });
  }

  return (
    <ListLayout
      title={t("userToRoles")}
      additionalActions={
        canManageNode
          ? [
              {
                label: t("user.assignRoles"),
                color: "primary",
                icon: <AddIcon />,
                onClick: () => navigate(UserToRoleRoutes.add(currentNode.id)),
              },
            ]
          : []
      }
    >
      <UserManagementGrid
        disableColumnFilter={false}
        getRowId={(row) => `${row.node_id}-${row.user_id}`}
        rows={userToRoles}
        columns={columns}
        initialState={{
          sorting: {
            sortModel: [{ field: "user_id", sort: "asc" }],
          },
        }}
      />
    </ListLayout>
  );
};
