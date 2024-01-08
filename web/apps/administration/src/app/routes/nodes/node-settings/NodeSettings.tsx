import { useUpdateNodeMutation } from "@/api";
import { isErrorResp } from "@/api/utils";
import { useCurrentNode } from "@/hooks";
import { Box, Button, Container, LinearProgress, Stack } from "@mui/material";
import { FormSelect, FormTextField } from "@stustapay/form-components";
import { toFormikValidationSchema } from "@stustapay/utils";
import { Form, Formik, FormikHelpers } from "formik";
import * as React from "react";
import { useTranslation } from "react-i18next";
import { Link as RouterLink } from "react-router-dom";
import { toast } from "react-toastify";
import { EventSettings } from "../event-settings";
import { NodeSettingsSchema, ObjectTypeSchema, type NodeSettingsSchemaType } from "../types";

const NodeConfiguration: React.FC = () => {
  const { t } = useTranslation();
  const { currentNode } = useCurrentNode();

  const [updateNode] = useUpdateNodeMutation();

  const handleSubmit = (values: NodeSettingsSchemaType, { setSubmitting }: FormikHelpers<NodeSettingsSchemaType>) => {
    setSubmitting(true);
    updateNode({
      nodeId: currentNode.id,
      newNode: {
        name: values.name,
        description: values.description,
        forbidden_objects_at_node: values.forbidden_objects_at_node,
        forbidden_objects_in_subtree: values.forbidden_objects_in_subtree,
      },
    }).then((resp) => {
      if (isErrorResp(resp)) {
        toast.error(`Error saving node settings: ${resp.error.data.detail}`);
      }
      setSubmitting(false);
    });
  };

  return (
    <Formik
      initialValues={currentNode as NodeSettingsSchemaType}
      enableReinitialize={true}
      validationSchema={toFormikValidationSchema(NodeSettingsSchema)}
      onSubmit={handleSubmit}
    >
      {(formik) => (
        <Form>
          <Stack spacing={2}>
            <FormTextField label={t("settings.general.name")} name="name" formik={formik} />
            <FormTextField label={t("settings.general.description")} name="description" formik={formik} />
            <FormSelect
              label={t("settings.general.forbidden_objects_at_node")}
              name="forbidden_objects_at_node"
              formik={formik}
              multiple={true}
              checkboxes={true}
              formatOption={(o: string) => o}
              options={ObjectTypeSchema.options}
            />
            <FormSelect
              label={t("settings.general.forbidden_objects_in_subtree")}
              name="forbidden_objects_in_subtree"
              formik={formik}
              multiple={true}
              checkboxes={true}
              formatOption={(o: string) => o}
              options={ObjectTypeSchema.options}
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

export const NodeSettings: React.FC = () => {
  const { t } = useTranslation();
  const { currentNode } = useCurrentNode();

  if (currentNode.event != null) {
    return <EventSettings />;
  }

  return (
    <Container maxWidth="md">
      <Stack spacing={2}>
        <Stack direction="row" justifyContent="center" spacing={2}>
          {currentNode.event_node_id == null && (
            <Button variant="outlined" component={RouterLink} to={`/node/${currentNode.id}/create-event`}>
              {t("settings.createEvent.link")}
            </Button>
          )}
          <Button variant="outlined" component={RouterLink} to={`/node/${currentNode.id}/create-node`}>
            {t("settings.createNode.link")}
          </Button>
        </Stack>
        <NodeConfiguration />
      </Stack>
    </Container>
  );
};
