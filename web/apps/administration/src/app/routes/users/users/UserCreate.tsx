import { useCreateUserMutation } from "@/api";
import { UserRoutes, UserToRoleRoutes } from "@/app/routes";
import { CreateLayout } from "@/components";
import { useCurrentNode } from "@/hooks";
import { NewUser, NewUserSchema } from "@stustapay/models";
import * as React from "react";
import { useTranslation } from "react-i18next";
import { UserCreateForm } from "./UserCreateForm";
import { withPrivilegeGuard } from "@/app/layout";

const initialValues: NewUser & { email?: string | null } = {
  login: "",
  display_name: "",
  description: "",
  email: undefined,
  password: "",
  user_tag_uid_hex: undefined,
  user_tag_pin: undefined,
};

export const UserCreate: React.FC = withPrivilegeGuard("user_management", () => {
  const { t } = useTranslation();
  const { currentNode } = useCurrentNode();
  const [createUser] = useCreateUserMutation();

  return (
    <CreateLayout
      title={t("createUser")}
      initialValues={initialValues}
      validationSchema={NewUserSchema}
      submitLabel={t("add")}
      alternativeSubmitLabel={t("user.createAndAssignRoles")}
      successRoute={(user: unknown, alternative: boolean) =>
        alternative
          ? UserToRoleRoutes.edit((user as { id: number }).id, currentNode.id)
          : UserRoutes.list(currentNode.id)
      }
      onSubmit={(u) => createUser({ nodeId: currentNode.id, createUserPayload: u })}
      form={UserCreateForm}
    />
  );
});
