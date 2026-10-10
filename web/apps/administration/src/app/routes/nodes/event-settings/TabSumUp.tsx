import { RestrictedEventSettings, useClearLegacySumupSettingsMutation, useUpdateEventMutation } from "@/api";
import { config } from "@/api/common";
import { useCurrentNode } from "@/hooks";
import { Alert, Button, LinearProgress, List, ListItem, ListItemText, Stack } from "@mui/material";
import { FormSelect, FormSwitch } from "@stustapay/form-components";
import { toFormikValidationSchema } from "@stustapay/utils";
import { Form, Formik, FormikHelpers, FormikProps } from "formik";
import { useOpenModal } from "@stustapay/modal-provider";
import * as React from "react";
import { useTranslation } from "react-i18next";
import { Link as RouterLink } from "react-router-dom";
import { toast } from "react-toastify";
import { type EventSumUpSettings, EventSumUpSettingsSchema } from "./sumupEnvironment";

export { EventSumUpSettingsSchema } from "./sumupEnvironment";
export type { EventSumUpSettings } from "./sumupEnvironment";

export const EventSumupSettingsForm: React.FC<FormikProps<EventSumUpSettings>> = (formik) => {
  const { t } = useTranslation();
  return (
    <>
      <FormSwitch
        disabled={!config.sumupTopupEnabledGlobally}
        label={t("settings.sumup.sumup_topup_enabled")}
        name="sumup_topup_enabled"
        formik={formik}
      />
      <FormSelect
        label={t("settings.sumup.environment")}
        name="sumup_environment"
        formik={formik}
        multiple={false}
        options={EventSumUpSettingsSchema.shape.sumup_environment.options}
        formatOption={(environment: unknown) =>
          environment === "sandbox"
            ? t("settings.sumup.sandboxEnvironment")
            : t("settings.sumup.liveEnvironment")
        }
      />
      <FormSwitch
        disabled={!config.sumupTopupEnabledGlobally}
        label={t("settings.sumup.group_topup_enabled")}
        name="group_topup_enabled"
        formik={formik}
      />
      <FormSwitch
        disabled={!config.sumupTopupEnabledGlobally}
        label={t("settings.sumup.sumup_payment_enabled")}
        name="sumup_payment_enabled"
        formik={formik}
      />
    </>
  );
};

const formatConnectionSource = (eventSettings: RestrictedEventSettings, t: (key: string, options?: Record<string, unknown>) => string) => {
  const source = eventSettings.resolved_sumup_link?.source;
  if (source === "node_link") {
    return t("settings.sumup.sourceNodeLink");
  }
  if (source === "legacy_event_oauth") {
    return t("settings.sumup.sourceLegacyOauth");
  }
  if (source === "legacy_event_api_key") {
    return t("settings.sumup.sourceLegacyApiKey");
  }
  return t("settings.sumup.sourceUnavailable");
};

export const TabSumUp: React.FC<{ nodeId: number; eventSettings: RestrictedEventSettings }> = ({
  nodeId,
  eventSettings,
}) => {
  const { currentNode } = useCurrentNode();
  const { t } = useTranslation();
  const openModal = useOpenModal();
  const [updateEvent] = useUpdateEventMutation();
  const [clearLegacySumupSettings, clearLegacyState] = useClearLegacySumupSettingsMutation();
  const hasLegacyCredentials =
    eventSettings.sumup_legacy_api_key_configured || eventSettings.sumup_legacy_oauth_configured;
  const usesLegacyCredentials =
    eventSettings.resolved_sumup_link?.source === "legacy_event_api_key" ||
    eventSettings.resolved_sumup_link?.source === "legacy_event_oauth";

  const performUpdate = (
    values: EventSumUpSettings,
    { setSubmitting }: Pick<FormikHelpers<EventSumUpSettings>, "setSubmitting">,
  ) => {
    setSubmitting(true);
    updateEvent({ nodeId: nodeId, updateEvent: { ...eventSettings, ...values } })
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

  const handleSubmit = (values: EventSumUpSettings, helpers: FormikHelpers<EventSumUpSettings>) => {
    if (values.sumup_environment === eventSettings.sumup_environment) {
      performUpdate(values, helpers);
      return;
    }
    helpers.setSubmitting(false);
    openModal({
      type: "confirm",
      title: t("settings.sumup.environmentChangeConfirmTitle"),
      content: t("settings.sumup.environmentChangeConfirmContent", {
        environment:
          values.sumup_environment === "sandbox"
            ? t("settings.sumup.sandboxEnvironment")
            : t("settings.sumup.liveEnvironment"),
      }),
      onConfirm: () => performUpdate(values, helpers),
    });
  };

  const linkedNodeId = eventSettings.resolved_sumup_link?.source_node_id;
  const linkedNodeSettingsUrl =
    linkedNodeId != null ? `/node/${linkedNodeId}/settings?tab=sumupConnection` : `/node/${currentNode.parent}/settings?tab=sumupConnection`;
  const handleClearLegacySettings = () => {
    openModal({
      type: "confirm",
      title: t("settings.sumup.clearLegacyConfirmTitle"),
      content: t("settings.sumup.clearLegacyConfirmContent"),
      onConfirm: () => {
        clearLegacySumupSettings({ nodeId })
          .unwrap()
          .then(() => {
            toast.success(t("settings.sumup.clearLegacySuccess"));
          })
          .catch((err) => {
            toast.error(t("settings.sumup.clearLegacyFailed", { reason: err?.data?.detail ?? err.error }));
          });
      },
    });
  };

  return (
    <Stack spacing={2}>
      {!config.sumupTopupEnabledGlobally && (
        <Alert severity="warning">SumUp payment is disabled globally in this StuStaPay instance configuration.</Alert>
      )}
      {eventSettings.resolved_sumup_link ? (
        <Alert severity={eventSettings.sumup_environment === "sandbox" ? "warning" : "success"}>
          {t("settings.sumup.resolvedLinkSummary", {
            merchantCode: eventSettings.resolved_sumup_link.merchant_code,
            nodeName: eventSettings.resolved_sumup_link.source_node_name,
          })}
        </Alert>
      ) : (
        <Alert severity="warning">{t("settings.sumup.noResolvedLink")}</Alert>
      )}
      {eventSettings.sumup_environment === "sandbox" && (
        <Alert severity="warning">{t("settings.sumup.eventSandboxNotice")}</Alert>
      )}
      {!eventSettings.sumup_global_oauth_configured && <Alert severity="info">{t("settings.sumup.oauthConfigMissing")}</Alert>}
      {!eventSettings.sumup_global_affiliate_key_configured && <Alert severity="info">{t("settings.sumup.affiliateKeyMissing")}</Alert>}
      {hasLegacyCredentials && usesLegacyCredentials && (
        <Alert severity="info">{t("settings.sumup.legacyFallbackNotice")}</Alert>
      )}
      {hasLegacyCredentials && !usesLegacyCredentials && (
        <Alert severity="info">{t("settings.sumup.legacyStoredButUnusedNotice")}</Alert>
      )}
      <List>
        <ListItem>
          <ListItemText primary={t("settings.sumup.connectionSource")} secondary={formatConnectionSource(eventSettings, t)} />
        </ListItem>
        <ListItem>
          <ListItemText
            primary={t("settings.sumup.sourceNode")}
            secondary={eventSettings.resolved_sumup_link?.source_node_name ?? t("settings.sumup.sourceUnavailable")}
          />
        </ListItem>
        <ListItem>
          <ListItemText
            primary={t("settings.sumup.sumup_merchant_code")}
            secondary={eventSettings.resolved_sumup_link?.merchant_code ?? t("settings.sumup.secretNotConfigured")}
          />
        </ListItem>
        <ListItem>
          <ListItemText
            primary={t("settings.sumup.merchantName")}
            secondary={eventSettings.resolved_sumup_link?.merchant_name ?? t("settings.sumup.secretNotConfigured")}
          />
        </ListItem>
      </List>
      <Button variant="outlined" component={RouterLink} to={linkedNodeSettingsUrl}>
        {t("settings.sumup.openConnectionSettings")}
      </Button>
      {hasLegacyCredentials && (
        <Button variant="outlined" color="secondary" onClick={handleClearLegacySettings} disabled={clearLegacyState.isLoading}>
          {t("settings.sumup.clearLegacyButton")}
        </Button>
      )}
      <Formik
        initialValues={eventSettings as EventSumUpSettings}
        onSubmit={handleSubmit}
        validationSchema={toFormikValidationSchema(EventSumUpSettingsSchema)}
        enableReinitialize={true}
      >
        {(formik) => (
          <Form onSubmit={formik.handleSubmit}>
            <Stack spacing={2}>
              <EventSumupSettingsForm {...formik} />
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
    </Stack>
  );
};
