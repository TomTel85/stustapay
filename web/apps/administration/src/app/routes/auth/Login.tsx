import { useLoginMutation } from "@/api";
import { selectIsAuthenticated, useAppSelector } from "@/store";
import { LockOutlined as LockOutlinedIcon } from "@mui/icons-material";
import { Stack, Avatar, Button, Container, CssBaseline, LinearProgress, Typography } from "@mui/material";
import { FormTextField } from "@stustapay/form-components";
import { toFormikValidationSchema } from "@stustapay/utils";
import { Form, Formik, FormikHelpers } from "formik";
import React, { useEffect } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, useSearchParams } from "react-router-dom";
import { toast } from "react-toastify";
import { z } from "zod";

const validationSchema = z.object({
  username: z.string(),
  password: z.string(),
});

type FormSchema = z.infer<typeof validationSchema>;

const initialValues: FormSchema = {
  username: "",
  password: "",
};

export const Login: React.FC = () => {
  const { t } = useTranslation();
  const isLoggedIn = useAppSelector(selectIsAuthenticated);
  const [query] = useSearchParams();
  const navigate = useNavigate();
  const [login] = useLoginMutation();

  useEffect(() => {
    if (isLoggedIn) {
      const next = query.get("next");
      const redirectUrl = next != null ? next : "/";
      navigate(redirectUrl);
    }
  }, [isLoggedIn, navigate, query]);

  const handleSubmit = (values: FormSchema, { setSubmitting }: FormikHelpers<FormSchema>) => {
    setSubmitting(true);
    login({ loginPayload: { username: values.username, password: values.password } })
      .unwrap()
      .then(() => {
        setSubmitting(false);
      })
      .catch((err) => {
        setSubmitting(false);
        console.log(err);
        toast.error(t("auth.loginFailed", { reason: err.error }));
      });
  };

  return (
    <Container component="main" maxWidth="xs">
      <CssBaseline />
      <Stack alignItems="center" justifyContent="center">
        <Avatar sx={{ margin: 1, backgroundColor: "primary.main" }}>
          <LockOutlinedIcon />
        </Avatar>
        <Typography component="h1" variant="h5">
          Sign in
        </Typography>
        <Formik
          initialValues={initialValues}
          onSubmit={handleSubmit}
          validationSchema={toFormikValidationSchema(validationSchema)}
        >
          {(formik) => (
            <Form onSubmit={formik.handleSubmit} style={{ width: "100%" }}>
              <Stack spacing={2}>
                <input type="hidden" name="remember" value="true" />
                <FormTextField
                  variant="outlined"
                  autoFocus
                  type="text"
                  label={t("auth.username")}
                  name="username"
                  formik={formik}
                />

                <FormTextField
                  variant="outlined"
                  type="password"
                  name="password"
                  label={t("auth.password")}
                  formik={formik}
                />

                {formik.isSubmitting && <LinearProgress />}
                <Button
                  type="submit"
                  fullWidth
                  variant="contained"
                  color="primary"
                  disabled={formik.isSubmitting}
                  sx={{ mt: 1 }}
                >
                  {t("auth.login")}
                </Button>
              </Stack>
            </Form>
          )}
        </Formik>
      </Stack>
    </Container>
  );
};
