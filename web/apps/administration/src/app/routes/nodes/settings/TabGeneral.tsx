import { Event, useUpdateEventMutation } from "@/api";
import { Button, LinearProgress, Stack } from "@mui/material";
import { FormTextField } from "@stustapay/form-components";
import { toFormikValidationSchema } from "@stustapay/utils";
import { Form, Formik, FormikHelpers } from "formik";
import * as React from "react";
import { useTranslation } from "react-i18next";
import { toast } from "react-toastify";
import { z } from "zod";

const GeneralSettingsSchema = z.object({
  currency_identifier: z.literal("EUR"),
  max_account_balance: z.number(),
  ust_id: z.string(),
});

type GeneralSettings = z.infer<typeof GeneralSettingsSchema>;

export const TabGeneral: React.FC<{ nodeId: number; event: Event }> = ({ nodeId, event }) => {
  const { t } = useTranslation();
  const [updateEvent] = useUpdateEventMutation();

  const handleSubmit = (values: GeneralSettings, { setSubmitting }: FormikHelpers<GeneralSettings>) => {
    setSubmitting(true);
    updateEvent({ nodeId: nodeId, updateEvent: { ...event, ...values } })
      .unwrap()
      .then(() => {
        setSubmitting(false);
        toast.success(t("settings.updateEventSucessful"));
      })
      .catch((err) => {
        setSubmitting(false);
        toast.error(t("settings.updateEventFailed", { reason: err.error }));
      });
  };

  return (
    <Formik
      initialValues={event as GeneralSettings} // TODO: figure out a way of not needing to cast this
      onSubmit={handleSubmit}
      validationSchema={toFormikValidationSchema(GeneralSettingsSchema)}
    >
      {(formik) => (
        <Form onSubmit={formik.handleSubmit}>
          <Stack spacing={2}>
            <FormTextField
              label={t("settings.general.currency_identifier")}
              name="currency_identifier"
              formik={formik}
            />
            <FormTextField
              label={t("settings.general.max_account_balance")}
              name="max_account_balance"
              formik={formik}
            />
            <FormTextField label={t("settings.general.ust_id")} name="ust_id" formik={formik} />
            {formik.isSubmitting && <LinearProgress />}
            <Button
              type="submit"
              color="primary"
              variant="contained"
              disabled={formik.isSubmitting || Object.keys(formik.touched).length === 0}
            >
              {t("save")}
            </Button>
          </Stack>
        </Form>
      )}
    </Formik>
  );
};
