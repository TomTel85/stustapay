import { NewUserToRoles, useUpdateUserToRolesMutation } from "@/api";
import { UserToRoleRoutes } from "@/app/routes";
import { CreateLayout } from "@/components";
import { useCurrentNode } from "@/hooks";
import * as React from "react";
import { useTranslation } from "react-i18next";
import { withPrivilegeGuard } from "@/app/layout";
import { Alert } from "@mui/material";
import { Loading } from "@stustapay/components";
import { useUserRoleAssignments } from "../roleAssignments";
import { UserRoleAssignmentForm } from "./UserRoleAssignmentForm";
import { z } from "zod";
import { FormikProps } from "formik";
import { UserSelect } from "@/components/features";

const NewUserToRoleSchema = z.object({
  user_id: z.number().int(),
  role_ids: z.array(z.number().int()),
});

const UserToRoleCreateForm: React.FC<FormikProps<NewUserToRoles>> = (props) => {
  const { values, errors, setFieldValue, touched } = props;
  const { t } = useTranslation();
  const { byUser } = useUserRoleAssignments();
  return (
    <>
      <UserSelect
        label={t("user.user")}
        value={values.user_id}
        onChange={(val) => {
          setFieldValue("user_id", val);
          setFieldValue("role_ids", (byUser.get(val) ?? []).filter((role) => !role.inherited).map((role) => role.roleId));
        }}
        error={touched.user_id && !!errors.user_id}
        helperText={(touched.user_id && errors.user_id) as string}
      />
      <UserRoleAssignmentForm {...props} />
    </>
  );
};

const initialValues: NewUserToRoles = {
  user_id: undefined as unknown as number, // to circument typescript,
  role_ids: [],
};

export const UserToRoleCreate: React.FC = withPrivilegeGuard(UserToRoleRoutes.privilege, () => {
  const { t } = useTranslation();
  const { currentNode } = useCurrentNode();
  const [createUserToRole] = useUpdateUserToRolesMutation();
  const roleAssignments = useUserRoleAssignments();

  if (roleAssignments.error) {
    return <Alert severity="error">{t("common.loadingError")}</Alert>;
  }
  if (roleAssignments.isLoading) {
    return <Loading />;
  }

  return (
    <CreateLayout
      key={currentNode.id}
      title={t("userToRole.create", { node: currentNode.name })}
      initialValues={initialValues}
      validationSchema={NewUserToRoleSchema}
      submitLabel={t("add")}
      successRoute={UserToRoleRoutes.list()}
      onSubmit={(u) => createUserToRole({ nodeId: currentNode.id, newUserToRoles: u })}
      form={UserToRoleCreateForm}
    />
  );
});
