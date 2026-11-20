import { CreateUserPayload } from "@/api";
import { Box, Divider } from "@mui/material";
import { FormTextField } from "@stustapay/form-components";
import { FormikProps } from "formik";
import { useTranslation } from "react-i18next";

type UserCreateFormValues = CreateUserPayload & { email?: string | null };

export type UserCreateFormProps<T extends UserCreateFormValues> = FormikProps<T>;

export function UserCreateForm<T extends UserCreateFormValues>(props: UserCreateFormProps<T>) {
  const { t } = useTranslation();
  return (
    <>
      <Box sx={{ display: "grid", gap: 2, gridTemplateColumns: { sm: "repeat(2, minmax(0, 1fr))" } }}>
        <FormTextField autoFocus name="login" label={t("userLogin")} formik={props} />
        <FormTextField name="display_name" label={t("userDisplayName")} formik={props} />
        <FormTextField type="email" name="email" label={t("userEmail")} formik={props} />
        <FormTextField
          type="password"
          autoComplete="new-password"
          name="password"
          label={t("userPassword")}
          formik={props}
        />
      </Box>
      <FormTextField multiline name="description" label={t("userDescription")} formik={props} />
      <Divider />
      <Box sx={{ display: "grid", gap: 2, gridTemplateColumns: { sm: "repeat(2, minmax(0, 1fr))" } }}>
        <FormTextField name="user_tag_uid_hex" label={t("userTag.uid")} formik={props} />
        <FormTextField name="user_tag_pin" label={t("userTag.pin")} formik={props} />
      </Box>
    </>
  );
}
