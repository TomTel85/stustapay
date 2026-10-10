import { FormSelect } from "@stustapay/form-components";
import { InputAdornment, Typography } from "@mui/material";
import { FormNumericInput, FormTextField } from "@stustapay/form-components";
import { NewTse, TseType } from "@stustapay/models";
import { FormikProps } from "formik";
import { useTranslation } from "react-i18next";

export type TseFormProps<T extends NewTse> = FormikProps<T>;

export function TseForm<T extends NewTse>(props: TseFormProps<T>) {
  const { t } = useTranslation();
  const isFiskaly = props.values.type === "fiskaly";

  return (
    <>
      <FormTextField autoFocus name="name" label={t("tse.name")} formik={props} />
      <FormSelect
        name="type"
        formik={props}
        multiple={false}
        options={["diebold_nixdorf", "fiskaly"] as TseType[]}
        formatOption={(type: TseType) => t(`tse.provider.${type}`)}
        label={t("tse.type")}
      />
      {isFiskaly ? (
        <>
          <FormTextField name="fiskaly_profile" label={t("tse.fiskalyProfile")} formik={props} />
          <Typography variant="body2" color="text.secondary">
            {t("tse.fiskalyProfileHelp")}
          </Typography>
        </>
      ) : (
        <>
          <FormTextField autoFocus name="serial" label={t("tse.serial")} formik={props} />
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
