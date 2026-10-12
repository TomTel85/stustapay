import { Language, useGetGlobalFaqConfigQuery, useUpdateGlobalFaqConfigMutation } from "@/api";
import { MarkdownEditor } from "@/components";
import { Loading, Select } from "@stustapay/components";
import {
  Alert,
  AlertTitle,
  Button,
  FormControlLabel,
  FormGroup,
  LinearProgress,
  Stack,
  Switch,
  Typography,
} from "@mui/material";
import { Form, Formik, FormikHelpers } from "formik";
import * as React from "react";
import { useTranslation } from "react-i18next";
import { toast } from "react-toastify";

type GlobalFaqValues = { faq_texts: Record<Language, string> };
const languages = ["de-DE", "en-US"] satisfies Language[];

export const TabGlobalFaq: React.FC = () => {
  const { t } = useTranslation();
  const { data: globalFaqConfig, isLoading, error } = useGetGlobalFaqConfigQuery();
  const [updateGlobalFaqConfig] = useUpdateGlobalFaqConfigMutation();
  const [language, setLanguage] = React.useState<Language>(languages[0]);
  const [preview, setPreview] = React.useState(true);

  const handleSubmit = (values: GlobalFaqValues, { setSubmitting }: FormikHelpers<GlobalFaqValues>) => {
    updateGlobalFaqConfig({ globalFaqConfig: { faq_texts: values.faq_texts } })
      .unwrap()
      .then(() => {
        setSubmitting(false);
        toast.success(t("settings.faq.updateSuccess"));
      })
      .catch((err) => {
        setSubmitting(false);
        toast.error(t("settings.faq.updateFailed", { reason: err?.data?.detail ?? err.error }));
      });
  };

  if (isLoading || (!globalFaqConfig && !error)) {
    return <Loading />;
  }

  if (!globalFaqConfig || error) {
    return (
      <Alert severity="error">
        <AlertTitle>{t("settings.faq.loadErrorTitle")}</AlertTitle>
      </Alert>
    );
  }

  return (
    <Formik<GlobalFaqValues>
      initialValues={{
        faq_texts: {
          "de-DE": globalFaqConfig.faq_texts?.["de-DE"] ?? "",
          "en-US": globalFaqConfig.faq_texts?.["en-US"] ?? "",
        },
      }}
      onSubmit={handleSubmit}
      enableReinitialize
    >
      {(formik) => (
        <Form onSubmit={formik.handleSubmit}>
          <Stack spacing={2}>
            <Select
              label={t("settings.language")}
              multiple={false}
              value={language}
              onChange={(value) => (value != null ? setLanguage(value as Language) : null)}
              options={languages}
              formatOption={(option: Language) => option}
            />
            <Typography variant="body2" color="text.secondary">
              {t("settings.faq.globalHelp")}
            </Typography>
            <FormGroup>
              <FormControlLabel
                label={t("settings.faq.preview")}
                control={<Switch checked={preview} onChange={(evt) => setPreview(evt.target.checked)} />}
              />
            </FormGroup>
            <MarkdownEditor
              label={t("settings.faq.content")}
              value={formik.values.faq_texts[language] ?? ""}
              onChange={(value) => {
                formik.setFieldValue("faq_texts", { ...formik.values.faq_texts, [language]: value });
                formik.setFieldTouched("faq_texts");
              }}
              showPreview={preview}
            />
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
