import { useChangeUserPasswordMutation, useGetUserQuery } from "@/api";
import { withPrivilegeGuard } from "@/app/layout";
import { UserRoutes } from "@/app/routes";
import { EditLayout } from "@/components";
import { useCurrentNode } from "@/hooks";
import i18n from "@/i18n";
import { Alert } from "@mui/material";
import { Loading } from "@stustapay/components";
import { FormTextField } from "@stustapay/form-components";
import { FormikProps } from "formik";
import * as React from "react";
import { useTranslation } from "react-i18next";
import { useParams } from "react-router-dom";
import { z } from "zod";

const PasswordChangeSchema = z
  .object({
    new_password: z.string(),
    new_password_confirm: z.string(),
  })
  .refine((values) => values.new_password === values.new_password_confirm, {
    message: i18n.t("auth.passwordsDontMatch"),
    path: ["new_password_confirm"],
  });

type PasswordChange = z.infer<typeof PasswordChangeSchema>;

export const UserUpdateForm = (props: FormikProps<PasswordChange>) => {
  const { t } = useTranslation();
  return (
    <>
      <FormTextField
        autoFocus
        name="new_password"
        label={t("user.changePassword.new_password")}
        type="password"
        autoComplete="new-password"
        formik={props}
      />
      <FormTextField
        name="new_password_confirm"
        label={t("user.changePassword.new_password_confirm")}
        type="password"
        autoComplete="new-password"
        formik={props}
      />
    </>
  );
};

const initialValues: PasswordChange = {
  new_password: "",
  new_password_confirm: "",
};

export const UserPasswordChange: React.FC = withPrivilegeGuard("user_management", () => {
  const { t } = useTranslation();
  const { currentNode } = useCurrentNode();
  const { userId } = useParams();
  const [updateUser] = useChangeUserPasswordMutation();
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
        title={t("user.changePassword.title")}
        submitLabel={t("save")}
        successRoute={UserRoutes.detail(user.id, user.node_id)}
        initialValues={initialValues}
        validationSchema={PasswordChangeSchema}
        onSubmit={(u) =>
          updateUser({
            nodeId: user.node_id,
            userId: user.id,
            changeUserPasswordPayload: { new_password: u.new_password },
          })
        }
        form={UserUpdateForm}
      />
    </>
  );
});
