import { Language, useGetGlobalPrivacyPolicyConfigQuery, useUpdateGlobalPrivacyPolicyConfigMutation } from "@/api";
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

type GlobalPrivacyPolicyValues = { privacy_policy_texts: Record<Language, string> };
const languages = ["de-DE", "en-US"] satisfies Language[];

export const TabGlobalPrivacyPolicy: React.FC = () => {
  const { t } = useTranslation();
  const { data: globalPrivacyPolicyConfig, isLoading, error } = useGetGlobalPrivacyPolicyConfigQuery();
  const [updateGlobalPrivacyPolicyConfig] = useUpdateGlobalPrivacyPolicyConfigMutation();
  const [language, setLanguage] = React.useState<Language>(languages[0]);
  const [preview, setPreview] = React.useState(true);

  const handleSubmit = (values: GlobalPrivacyPolicyValues, { setSubmitting }: FormikHelpers<GlobalPrivacyPolicyValues>) => {
    updateGlobalPrivacyPolicyConfig({ globalPrivacyPolicyConfig: { privacy_policy_texts: values.privacy_policy_texts } })
      .unwrap()
      .then(() => {
        setSubmitting(false);
        toast.success(t("settings.privacyPolicy.updateSuccess"));
      })
      .catch((err) => {
        setSubmitting(false);
        toast.error(t("settings.privacyPolicy.updateFailed", { reason: err?.data?.detail ?? err.error }));
      });
  };

  if (isLoading || (!globalPrivacyPolicyConfig && !error)) {
    return <Loading />;
  }

  if (!globalPrivacyPolicyConfig || error) {
    return (
      <Alert severity="error">
        <AlertTitle>{t("settings.privacyPolicy.loadErrorTitle")}</AlertTitle>
      </Alert>
    );
  }

  return (
    <Formik<GlobalPrivacyPolicyValues>
      initialValues={{
        privacy_policy_texts: {
          "de-DE": globalPrivacyPolicyConfig.privacy_policy_texts?.["de-DE"] ?? "",
          "en-US": globalPrivacyPolicyConfig.privacy_policy_texts?.["en-US"] ?? "",
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
              {t("settings.privacyPolicy.globalHelp")}
            </Typography>
            <FormGroup>
              <FormControlLabel
                label={t("settings.privacyPolicy.preview")}
                control={<Switch checked={preview} onChange={(evt) => setPreview(evt.target.checked)} />}
              />
            </FormGroup>
            <MarkdownEditor
              label={t("settings.privacyPolicy.content")}
              value={formik.values.privacy_policy_texts[language] ?? ""}
              onChange={(value) => {
                formik.setFieldValue("privacy_policy_texts", { ...formik.values.privacy_policy_texts, [language]: value });
                formik.setFieldTouched("privacy_policy_texts");
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
