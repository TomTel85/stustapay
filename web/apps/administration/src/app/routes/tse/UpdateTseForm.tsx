import { InputAdornment, Typography } from "@mui/material";
import { FormNumericInput, FormTextField } from "@stustapay/form-components";
import { UpdateTse } from "@stustapay/models";
import { FormikProps } from "formik";
import { useTranslation } from "react-i18next";

export type UpdateTseForm<T extends UpdateTse> = FormikProps<T>;

export function UpdateTseForm<T extends UpdateTse>(props: UpdateTseForm<T>) {
  const { t } = useTranslation();
  const isFiskaly = props.values.type === "fiskaly";

  return (
    <>
      <FormTextField autoFocus name="name" label={t("tse.name")} formik={props} />
      {isFiskaly ? (
        <>
          <FormTextField name="fiskaly_profile" label={t("tse.fiskalyProfile")} formik={props} />
          <Typography variant="body2" color="text.secondary">
            {t("tse.fiskalyProfileHelp")}
          </Typography>
        </>
      ) : (
        <>
          <FormTextField name="ws_url" label={t("tse.wsUrl")} formik={props} />
          <FormNumericInput
            name="ws_timeout"
            label={t("tse.wsTimeout")}
            slotProps={{ input: { endAdornment: <InputAdornment position="end">s</InputAdornment> } }}
            formik={props}
          />
          <FormTextField name="password" label={t("tse.password")} type="password" formik={props} />
        </>
      )}
    </>
  );
}
