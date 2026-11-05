import { useGetUserQuery, useListUserToRoleQuery, useUpdateUserToRolesMutation } from "@/api";
import { UserRoutes, UserToRoleRoutes } from "@/app/routes";
import { EditLayout } from "@/components";
import { Alert } from "@mui/material";
import { useUserRoleAssignments } from "../roleAssignments";
import { getUserName } from "@stustapay/models";
import { useCurrentNode } from "@/hooks";
import * as React from "react";
import { useTranslation } from "react-i18next";
import { z } from "zod";
import { UserRoleAssignmentForm } from "./UserRoleAssignmentForm";
import { withPrivilegeGuard } from "@/app/layout";
import { useParams } from "react-router-dom";
import { Loading } from "@stustapay/components";

const UpdateUserToRolesSchema = z.object({
  user_id: z.number().int(),
  role_ids: z.array(z.number().int()),
});

export const UserToRoleUpdate: React.FC = withPrivilegeGuard(UserToRoleRoutes.privilege, () => {
  const { t } = useTranslation();
  const { currentNode } = useCurrentNode();
  const [updateUserToRoles] = useUpdateUserToRolesMutation();
  const { userId: userIdP } = useParams();
  const userId = Number(userIdP);
  const roleAssignments = useUserRoleAssignments();
  const { currentData: user, error: userError } = useGetUserQuery({ nodeId: currentNode.id, userId });
  const { userToRoles, error } = useListUserToRoleQuery(
    { nodeId: currentNode.id },
    {
      selectFromResult: ({ currentData, ...rest }) => ({
        ...rest,
        userToRoles: currentData
          ? currentData.find((u) => u.node_id === currentNode.id && u.user_id === userId) ?? {
              user_id: userId,
              node_id: currentNode.id,
              role_ids: [],
            }
          : undefined,
      }),
    }
  );

  if (error || userError || roleAssignments.error) {
    return <Alert severity="error">{t("common.loadingError")}</Alert>;
  }

  if (!userToRoles || !user || roleAssignments.isLoading) {
    return <Loading />;
  }

  return (
    <EditLayout
      key={`${currentNode.id}-${userId}`}
      title={t("userToRole.update", { user: getUserName(user), node: currentNode.name })}
      initialValues={userToRoles}
      validationSchema={UpdateUserToRolesSchema}
      submitLabel={t("save")}
      successRoute={UserRoutes.detail(userId, currentNode.id)}
      onSubmit={(u) =>
        updateUserToRoles({ nodeId: currentNode.id, newUserToRoles: { user_id: userId, role_ids: u.role_ids } })
      }
      form={UserRoleAssignmentForm}
    />
  );
});
