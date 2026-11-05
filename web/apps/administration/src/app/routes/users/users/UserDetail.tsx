import { useDeleteUserMutation, useGetUserQuery, UserRead } from "@/api";
import { UserRoutes, UserTagRoutes, UserToRoleRoutes } from "@/app/routes";
import { DetailField, DetailLayout, DetailView } from "@/components";
import { useCurrentNode, useCurrentUserHasPrivilege } from "@/hooks";
import { selectAuthToken, useAppSelector } from "@/store";
import { Delete as DeleteIcon, Edit as EditIcon, Mail as MailIcon } from "@mui/icons-material";
import { Link } from "@mui/material";
import { Loading } from "@stustapay/components";
import { useOpenModal } from "@stustapay/modal-provider";
import * as React from "react";
import { useTranslation } from "react-i18next";
import { Link as RouterLink, Navigate, useNavigate, useParams } from "react-router-dom";
import { toast } from "react-toastify";
import { RoleAssignmentSummary, useUserRoleAssignments } from "../roleAssignments";

export const UserDetail: React.FC = () => {
  const { t } = useTranslation();
  const { currentNode } = useCurrentNode();
  const canManageUserRoles = useCurrentUserHasPrivilege(UserToRoleRoutes.privilege);
  const { userId } = useParams();
  const navigate = useNavigate();
  const [deleteUser] = useDeleteUserMutation();
  const { currentData: user, error } = useGetUserQuery({ nodeId: currentNode.id, userId: Number(userId) });
  const openModal = useOpenModal();
  const roleAssignments = useUserRoleAssignments();

  const token = useAppSelector(selectAuthToken);
  const handleInvite = async () => {
    if (!user) {
      return;
    }

    try {
      const response = await fetch(`/api/users/${user.id}/invite?node_id=${user.node_id}`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
      });
      if (response.ok) {
        toast.success(t("user.invitationSent"));
      } else {
        const error = await response.json();
        toast.error(error.detail || t("user.invitationFailed"));
      }
    } catch (err) {
      toast.error(t("user.invitationFailed"));
    }
  };

  if (error) {
    return <Navigate to={UserRoutes.list()} />;
  }

  const openConfirmDeleteDialog = () => {
    if (!user) {
      return;
    }

    openModal({
      type: "confirm",
      title: t("deleteUser"),
      content: t("deleteUserDescription"),
      onConfirm: () => {
        deleteUser({ nodeId: user.node_id, userId: user.id }).then(() => navigate(UserRoutes.list(user.node_id)));
      },
    });
  };

  if (user === undefined) {
    return <Loading />;
  }

  return (
    <DetailLayout
      title={user.login}
      routes={UserRoutes}
      elementNodeId={user.node_id}
      actions={[
        {
          label: t("user.invite"),
          onClick: handleInvite,
          color: "primary",
          icon: <MailIcon />,
          disabled: !(user as UserRead & { email?: string | null }).email,
        },
        {
          label: t("user.changePassword.title"),
          onClick: () => navigate(`${UserRoutes.detail(user.id, user.node_id)}/change-password`),
          color: "primary",
          icon: <EditIcon />,
        },
        {
          label: t("edit"),
          onClick: () => navigate(UserRoutes.edit(user.id, user.node_id)),
          color: "primary",
          icon: <EditIcon />,
        },
        { label: t("delete"), onClick: openConfirmDeleteDialog, color: "error", icon: <DeleteIcon /> },
      ]}
    >
      <DetailView>
        <DetailField label={t("userLogin")} value={user.login} />
        <DetailField label={t("userDisplayName")} value={user.display_name} />
        <DetailField label={t("userEmail")} value={(user as UserRead & { email?: string | null }).email || t("user.noEmail")} />
        <DetailField label={t("userDescription")} value={user.description} />
        <DetailField
          label={t("user.roles")}
          value={roleAssignments.error ? t("common.loadingError") : roleAssignments.isLoading ? (
            t("userToRole.loadingRoles")
          ) : <RoleAssignmentSummary assignments={roleAssignments.byUser.get(user.id) ?? []} />}
        />
        {canManageUserRoles && (
          <DetailField
            label={t("userToRoles")}
            value={
              <Link component={RouterLink} to={UserToRoleRoutes.edit(user.id, currentNode.id)}>
                {t("userToRole.assignAtNode", { node: currentNode.name })}
              </Link>
            }
          />
        )}
        {user.user_tag_id ? (
          <DetailField
            label={t("user.tagId")}
            linkTo={UserTagRoutes.detail(user.user_tag_id)}
            value={user.user_tag_id}
          />
        ) : (
          <DetailField label={t("user.tagId")} value={t("user.noTagAssigned")} />
        )}
      </DetailView>
    </DetailLayout>
  );
};
