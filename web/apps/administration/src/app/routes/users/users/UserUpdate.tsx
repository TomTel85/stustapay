import { useGetUserQuery, useUpdateUserMutation } from "@/api";
import { UserRoutes } from "@/app/routes";
import { EditLayout } from "@/components";
import { useCurrentNode } from "@/hooks";
import { Alert } from "@mui/material";
import { Loading } from "@stustapay/components";
import { UserSchema } from "@stustapay/models";
import * as React from "react";
import { useTranslation } from "react-i18next";
import { useParams } from "react-router-dom";
import { UserUpdateForm } from "./UserUpdateForm";
import { withPrivilegeGuard } from "@/app/layout";

export const UserUpdate: React.FC = withPrivilegeGuard("user_management", () => {
  const { t } = useTranslation();
  const { currentNode } = useCurrentNode();
  const { userId } = useParams();
  const [updateUser] = useUpdateUserMutation();
  const { currentData: user, error } = useGetUserQuery({ nodeId: currentNode.id, userId: Number(userId) });

  if (error && !user) {
    return <Alert severity="error">{t("common.loadingError")}</Alert>;
  }

  if (!user) {
    return <Loading />;
  }

  return (
    <>
      {error && (
        <Alert severity="warning" sx={{ mb: 2 }}>
          {t("common.refreshError")}
        </Alert>
      )}
      <EditLayout
        key={`${currentNode.id}:${userId}`}
        title={t("updateUser")}
        submitLabel={t("update")}
        successRoute={UserRoutes.detail(user.id, user.node_id)}
        initialValues={user}
        validationSchema={UserSchema}
        onSubmit={(u) => updateUser({ nodeId: user.node_id, userId: user.id, updateUserPayload: u })}
        form={UserUpdateForm}
      />
    </>
  );
});
