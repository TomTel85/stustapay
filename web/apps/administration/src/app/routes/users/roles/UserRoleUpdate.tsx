import { selectUserRoleById, useListUserRolesQuery, useUpdateUserRoleMutation } from "@/api";
import { UserRoleRoutes } from "@/app/routes";
import { EditLayout } from "@/components";
import { useCurrentNode } from "@/hooks";
import { Alert } from "@mui/material";
import { Loading } from "@stustapay/components";
import * as React from "react";
import { useTranslation } from "react-i18next";
import { useParams } from "react-router-dom";
import { UserRoleUpdateForm, UserRoleUpdateSchema, UserRoleUpdate as UserRoleUpdateType } from "./UserRoleUpdateForm";
import { withPrivilegeGuard } from "@/app/layout";

export const UserRoleUpdate: React.FC = withPrivilegeGuard("user_management", () => {
  const { t } = useTranslation();
  const { roleId } = useParams();
  const { currentNode } = useCurrentNode();
  const [updateUserRole] = useUpdateUserRoleMutation();
  const { userRole, hasRoles, error } = useListUserRolesQuery(
    { nodeId: currentNode.id },
    {
      selectFromResult: ({ currentData, ...rest }) => ({
        ...rest,
        userRole: currentData ? selectUserRoleById(currentData, Number(roleId)) : undefined,
        hasRoles: currentData !== undefined,
      }),
    }
  );

  if (error && !userRole) {
    return <Alert severity="error">{t("common.loadingError")}</Alert>;
  }

  if (!userRole) {
    return hasRoles ? <Alert severity="warning">{t("userRole.notFound")}</Alert> : <Loading />;
  }

  return (
    <>
      {error && (
        <Alert severity="warning" sx={{ mb: 2 }}>
          {t("common.refreshError")}
        </Alert>
      )}
      <EditLayout
        key={`${currentNode.id}:${roleId}`}
        title={t("userRole.update", { name: userRole.name })}
        submitLabel={t("save")}
        successRoute={UserRoleRoutes.list()}
        initialValues={userRole as UserRoleUpdateType}
        validationSchema={UserRoleUpdateSchema}
        onSubmit={(u) =>
          updateUserRole({ nodeId: currentNode.id, userRoleId: userRole.id, updateUserRolePrivilegesPayload: u })
        }
        form={UserRoleUpdateForm}
      />
    </>
  );
});
