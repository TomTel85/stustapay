import { UpdateUserPayload } from "@/api";
import { Box, Divider } from "@mui/material";
import { FormTextField } from "@stustapay/form-components";
import { FormikProps } from "formik";
import { useTranslation } from "react-i18next";

type UserUpdateFormValues = UpdateUserPayload & { email?: string | null };

export type UserUpdateFormProps<T extends UserUpdateFormValues> = FormikProps<T>;

export function UserUpdateForm<T extends UserUpdateFormValues>(props: UserUpdateFormProps<T>) {
  const { t } = useTranslation();
  return (
    <>
      <Box sx={{ display: "grid", gap: 2, gridTemplateColumns: { sm: "repeat(2, minmax(0, 1fr))" } }}>
        <FormTextField autoFocus name="login" label={t("userLogin")} formik={props} />
        <FormTextField name="display_name" label={t("userDisplayName")} formik={props} />
      </Box>
      <FormTextField type="email" name="email" label={t("userEmail")} formik={props} />
      <FormTextField multiline name="description" label={t("userDescription")} formik={props} />
      <Divider />
      <Box sx={{ display: "grid", gap: 2, gridTemplateColumns: { sm: "repeat(2, minmax(0, 1fr))" } }}>
        <FormTextField name="user_tag_uid_hex" label={t("userTag.uid")} formik={props} />
        <FormTextField name="user_tag_pin" label={t("userTag.pin")} formik={props} />
      </Box>
    </>
  );
}
