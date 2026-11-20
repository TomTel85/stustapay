import { NewUserToRoles } from "@/api";
import { RoleSelect } from "@/components/features";
import { useCurrentNode } from "@/hooks";
import { Box, FormHelperText, Typography } from "@mui/material";
import { FormikProps } from "formik";
import * as React from "react";
import { useTranslation } from "react-i18next";
import { RoleAssignmentSummary, useUserRoleAssignments } from "../roleAssignments";

export const UserRoleAssignmentForm: React.FC<FormikProps<NewUserToRoles>> = ({
  values,
  errors,
  setFieldValue,
  touched,
}) => {
  const { t } = useTranslation();
  const { currentNode } = useCurrentNode();
  const { byUser } = useUserRoleAssignments();
  const inheritedRoles = (byUser.get(values.user_id) ?? []).filter((role) => role.inherited);

  return (
    <>
      <RoleSelect
        label={t("userToRole.localRoles", { node: currentNode.name })}
        value={values.role_ids}
        onChange={(val) => setFieldValue("role_ids", val)}
        error={touched.role_ids && !!errors.role_ids}
      />
      <FormHelperText error={touched.role_ids && !!errors.role_ids}>
        {((touched.role_ids && errors.role_ids) as string) || t("userToRole.localRolesHelp")}
      </FormHelperText>
      <Box sx={{ borderTop: 1, borderColor: "divider", pt: 2 }}>
        <Typography component="h2" variant="subtitle2" gutterBottom>
          {t("userToRole.inheritedRoles")}
        </Typography>
        <Typography variant="body2" color="text.secondary" sx={{ overflowWrap: "anywhere" }}>
          {inheritedRoles.length > 0 ? (
            <RoleAssignmentSummary assignments={inheritedRoles} />
          ) : (
            t("userToRole.noInheritedRoles")
          )}
        </Typography>
      </Box>
    </>
  );
};
