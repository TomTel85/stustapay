import { UpdateTse } from "@/api";
import { InputAdornment } from "@mui/material";
import { FormNumericInput, FormTextField } from "@stustapay/form-components";
import { FormikProps } from "formik";
import { useTranslation } from "react-i18next";

// Renamed the type for clarity
export type UpdateTseFormProps<T extends UpdateTse> = FormikProps<T>;

export function UpdateTseForm<T extends UpdateTse>(props: UpdateTseFormProps<T>) {
  const { t } = useTranslation();

  return (
    <>
      <FormTextField autoFocus name="name" label={t("tse.name")} formik={props} />
      <FormTextField name="ws_url" label={t("tse.wsUrl")} formik={props} />
      <FormTextField name="type" label={t("tse.type")} formik={props} />
      <FormNumericInput
        name="ws_timeout"
        label={t("tse.wsTimeout")}
        InputProps={{ endAdornment: <InputAdornment position="end">s</InputAdornment> }}
        formik={props}
      />
      <FormTextField name="password" label={t("tse.password")} formik={props} />
    </>
  );
}
