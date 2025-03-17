import { useLoginUserMutation, useListUserToRoleQuery, useListUserRolesQuery } from "@/api/generated/api";
import { useCurrentNode } from "@/hooks";
import { Button, Dialog, DialogActions, DialogContent, DialogTitle, FormControl, InputLabel, MenuItem, Select } from "@mui/material";
import { useFormik } from "formik";
import * as React from "react";
import { useTranslation } from "react-i18next";
import { toast } from "react-toastify";
import * as Yup from "yup";
import { NormalizedListUserInt, User, UserRole } from "@/api/generated/api";
import { getUserName } from "@stustapay/models";
import { Loading } from "@stustapay/components";

interface Props {
  open: boolean;
  terminalId: number;
  users: NormalizedListUserInt;
  onClose: () => void;
}

interface FormValues {
  userId: number;
  roleId: number;
}

const validationSchema = Yup.object().shape({
  userId: Yup.number().required(),
  roleId: Yup.number().required(),
});

export const TerminalUserLogin: React.FC<Props> = ({ open, terminalId, users, onClose }) => {
  const { t } = useTranslation();
  const { currentNode } = useCurrentNode();
  const [loginUser] = useLoginUserMutation();
  const { data: userToRoles, isLoading: isLoadingUserToRoles } = useListUserToRoleQuery({ nodeId: currentNode.id });
  const { data: userRoles, isLoading: isLoadingUserRoles } = useListUserRolesQuery({ nodeId: currentNode.id });

  const formik = useFormik<FormValues>({
    initialValues: {
      userId: 0,
      roleId: 0,
    },
    validationSchema,
    onSubmit: async (values, { setSubmitting }) => {
      try {
        await loginUser({
          nodeId: currentNode.id,
          terminalId,
          loginPayload: {
            user_id: values.userId,
            role_id: values.roleId,
          },
        }).unwrap();
        toast.success(t("terminal.userLoginSuccess"));
        onClose();
      } catch (err: any) {
        toast.error(t("terminal.userLoginFailed", { reason: err.error }));
      } finally {
        setSubmitting(false);
      }
    },
  });

  if (isLoadingUserToRoles || isLoadingUserRoles) {
    return <Loading />;
  }

  const getUserRoles = (userId: number): UserRole[] => {
    if (!userToRoles || !userRoles) return [];
    const userRole = userToRoles.find((utr) => utr.user_id === userId);
    if (!userRole) return [];
    return userRole.role_ids
      .map((roleId) => userRoles.entities[roleId])
      .filter((role): role is UserRole => role !== undefined);
  };

  return (
    <Dialog open={open} onClose={onClose}>
      <form onSubmit={formik.handleSubmit}>
        <DialogTitle>{t("terminal.loginUser")}</DialogTitle>
        <DialogContent>
          <FormControl fullWidth margin="normal">
            <InputLabel>{t("user.select")}</InputLabel>
            <Select
              name="userId"
              value={formik.values.userId}
              onChange={(e) => {
                formik.setFieldValue("userId", e.target.value);
                formik.setFieldValue("roleId", 0);
              }}
              error={formik.touched.userId && Boolean(formik.errors.userId)}
            >
              {users.ids.map((id) => {
                const user = users.entities[id];
                return (
                  <MenuItem key={id} value={id}>
                    {getUserName(user)}
                  </MenuItem>
                );
              })}
            </Select>
          </FormControl>
          <FormControl fullWidth margin="normal">
            <InputLabel>{t("role.select")}</InputLabel>
            <Select
              name="roleId"
              value={formik.values.roleId}
              onChange={formik.handleChange}
              error={formik.touched.roleId && Boolean(formik.errors.roleId)}
            >
              {formik.values.userId > 0 &&
                getUserRoles(formik.values.userId).map((role) => (
                  <MenuItem key={role.id} value={role.id}>
                    {role.name}
                  </MenuItem>
                ))}
            </Select>
          </FormControl>
        </DialogContent>
        <DialogActions>
          <Button onClick={onClose}>{t("cancel")}</Button>
          <Button type="submit" variant="contained" disabled={formik.isSubmitting}>
            {t("login")}
          </Button>
        </DialogActions>
      </form>
    </Dialog>
  );
}; 