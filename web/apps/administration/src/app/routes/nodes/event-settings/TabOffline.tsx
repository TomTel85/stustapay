import { RestrictedEventSettings, useUpdateEventMutation } from "@/api";
import { Alert, Button, FormControlLabel, LinearProgress, Stack, Switch, Typography } from "@mui/material";
import { FormCurrencyInput, FormNumericInput } from "@stustapay/form-components";
import { toFormikValidationSchema } from "@stustapay/utils";
import { Form, Formik, FormikHelpers } from "formik";
import * as React from "react";
import { useTranslation } from "react-i18next";
import { toast } from "react-toastify";
import { OfflineFormSchema, OfflineFormValues, toOfflineApiSettings, toOfflineFormValues } from "./offlineSettings";

export const TabOffline: React.FC<{ nodeId: number; eventSettings: RestrictedEventSettings }> = ({
  nodeId,
  eventSettings,
}) => {
  const { t } = useTranslation();
  const [updateEvent] = useUpdateEventMutation();

  const initialValues = toOfflineFormValues(eventSettings);

  const handleSubmit = (values: OfflineFormValues, { setSubmitting }: FormikHelpers<OfflineFormValues>) => {
    const settings = toOfflineApiSettings(values);
    updateEvent({ nodeId, updateEvent: { ...eventSettings, ...settings } })
      .unwrap()
      .then(() => toast.success(t("settings.updateEventSucessful")))
      .catch((err) => toast.error(t("settings.updateEventFailed", { reason: err.error })))
      .finally(() => setSubmitting(false));
  };

  return (
    <Formik
      initialValues={initialValues}
      enableReinitialize
      onSubmit={handleSubmit}
      validationSchema={toFormikValidationSchema(OfflineFormSchema)}
    >
      {(formik) => (
        <Form onSubmit={formik.handleSubmit}>
          <Stack spacing={2} maxWidth={640}>
            <Typography variant="h6">{t("settings.offline.title")}</Typography>
            <Alert severity="warning">{t("settings.offline.risk")}</Alert>
            <FormControlLabel
              control={
                <Switch
                  checked={formik.values.offline_enabled}
                  onChange={(event) => formik.setFieldValue("offline_enabled", event.target.checked)}
                />
              }
              label={t("settings.offline.enabled")}
            />
            <FormNumericInput
              label={t("settings.offline.validityMinutes")}
              name="offline_validity_minutes"
      formik={formik}
      integerOnly
      inputProps={{ min: 1, max: 24 }}
            />
            <Typography variant="subtitle1">{t("settings.offline.sales")}</Typography>
            <FormCurrencyInput
              label={t("settings.offline.perTransaction")}
              name="offline_sale_per_transaction"
              formik={formik}
            />
            <FormCurrencyInput
              label={t("settings.offline.perCustomer")}
              name="offline_sale_per_customer"
              formik={formik}
            />
            <FormCurrencyInput
              label={t("settings.offline.perTill")}
              name="offline_sale_per_till"
              formik={formik}
            />
            <Typography variant="subtitle1">{t("settings.offline.returns")}</Typography>
            <FormCurrencyInput
              label={t("settings.offline.perTransaction")}
              name="offline_return_per_transaction"
              formik={formik}
            />
            <FormCurrencyInput
              label={t("settings.offline.perCustomer")}
              name="offline_return_per_customer"
              formik={formik}
            />
            <FormCurrencyInput
              label={t("settings.offline.perTill")}
              name="offline_return_per_till"
              formik={formik}
            />
            {formik.isSubmitting && <LinearProgress />}
            <Button type="submit" variant="contained" disabled={formik.isSubmitting || !formik.dirty}>
              {t("save")}
            </Button>
          </Stack>
        </Form>
      )}
    </Formik>
  );
};
