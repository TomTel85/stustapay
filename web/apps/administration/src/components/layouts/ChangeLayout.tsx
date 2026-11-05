import { ChevronLeft } from "@mui/icons-material";
import { Button, Grid, IconButton, LinearProgress, Paper, Stack, Typography } from "@mui/material";
import { MutationActionCreatorResult } from "@reduxjs/toolkit/dist/query/react/index";
import { toFormikValidationSchema } from "@stustapay/utils";
import { Form, Formik, FormikHelpers, FormikProps } from "formik";
import { useNavigate } from "react-router-dom";
import { z } from "zod";
import { useTranslation } from "react-i18next";
import { useRef } from "react";

export interface ChangeLayoutProps<T extends Record<string, any>> {
  title: string;
  submitLabel?: string;
  initialValues: T;
  validationSchema: z.ZodSchema<T>;
  successRoute: string | ((result: unknown, alternative: boolean) => string);
  alternativeSubmitLabel?: string;
  onSubmit: (t: T, helpers: FormikHelpers<T>) => MutationActionCreatorResult<any> | Promise<unknown>;
  form: React.FC<FormikProps<T>>;
}

export function ChangeLayout<T extends Record<string, any>>({
  title,
  successRoute,
  submitLabel,
  alternativeSubmitLabel,
  initialValues,
  validationSchema,
  onSubmit,
  form: ChildForm,
}: ChangeLayoutProps<T>) {
  const navigate = useNavigate();
  const { t } = useTranslation();
  const alternativeSubmit = useRef(false);
  const handleSubmit = async (values: T, helpers: FormikHelpers<T>) => {
    helpers.setSubmitting(true);
    try {
      const result = onSubmit(values, helpers);
      const data = await ("unwrap" in result ? result.unwrap() : result);
      navigate(typeof successRoute === "function" ? successRoute(data, alternativeSubmit.current) : successRoute);
    } catch (err) {
      console.warn("error in change", err);
    } finally {
      helpers.setSubmitting(false);
    }
  };

  return (
    <Stack spacing={3}>
      <Grid container spacing={1}>
        <Grid display="flex" alignItems="center">
          <IconButton
            onClick={() => navigate(-1)}
            aria-label={t("portal.back")}
            sx={{ mr: 1, border: 1, borderColor: "divider", bgcolor: "background.paper" }}
          >
            <ChevronLeft />
          </IconButton>
          <Typography
            component="h1"
            variant="h4"
            sx={{ fontSize: { xs: "1.5rem", sm: "2rem" }, overflowWrap: "anywhere" }}
          >
            {title}
          </Typography>
        </Grid>
      </Grid>
      <Formik
        initialValues={initialValues}
        onSubmit={handleSubmit}
        validationSchema={toFormikValidationSchema(validationSchema)}
      >
        {(props) => (
          <Form
            onSubmit={(event) => {
              alternativeSubmit.current =
                (event.nativeEvent as SubmitEvent).submitter?.getAttribute("value") === "alternative";
              props.handleSubmit(event);
            }}
          >
            <Stack spacing={2}>
              <Paper sx={{ p: { xs: 2, sm: 3 } }}>
                <Stack spacing={2}>
                  <ChildForm {...props} />
                </Stack>
                {props.isSubmitting && <LinearProgress />}
              </Paper>
              <Button
                type="submit"
                variant="contained"
                color="primary"
                disabled={props.isSubmitting}
                sx={{ alignSelf: { xs: "stretch", sm: "flex-end" }, minWidth: 160 }}
              >
                {submitLabel}
              </Button>
              {alternativeSubmitLabel && (
                <Button
                  type="submit"
                  value="alternative"
                  variant="outlined"
                  disabled={props.isSubmitting}
                  sx={{ alignSelf: { xs: "stretch", sm: "flex-end" }, minWidth: 160 }}
                >
                  {alternativeSubmitLabel}
                </Button>
              )}
            </Stack>
          </Form>
        )}
      </Formik>
    </Stack>
  );
}
