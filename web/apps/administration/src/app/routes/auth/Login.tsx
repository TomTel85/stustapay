import { useLoginMutation, UserLoginResult } from "@/api";
import { selectIsAuthenticated, useAppSelector } from "@/store";
import { logoSrc } from "@/components/BrandLogo";
import { LockOutlined as LockOutlinedIcon } from "@mui/icons-material";
import {
  Alert,
  Stack,
  Avatar,
  Button,
  Container,
  Box,
  Chip,
  Paper,
  LinearProgress,
  Typography,
  List,
  ListItemButton,
  ListItemText,
} from "@mui/material";
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
  mfa_code: z.string().optional(),
});

type FormSchema = z.infer<typeof validationSchema>;

type NodeSelectInfo = {
  username: string;
  password: string;
  availableNodes: NonNullable<UserLoginResult["available_nodes"]>;
};

const SelectNode: React.FC<{
  availableNodes: NodeSelectInfo["availableNodes"];
  onSelect: (nodeId: number) => void;
  busy: boolean;
}> = ({ availableNodes, onSelect, busy }) => {
  const { t } = useTranslation();

  return (
    <>
      <Typography component="h1" variant="h5">
        {t("auth.selectNode")}
      </Typography>
      <List sx={{ width: "100%" }}>
        {availableNodes.map((node, index) => (
          <ListItemButton
            key={node.node_id}
            disabled={busy}
            onClick={() => onSelect(node.node_id)}
            sx={{
              borderTop: index === 0 ? 1 : 0,
              borderRight: 1,
              borderLeft: 1,
              borderBottom: 1,
              borderColor: "divider",
            }}
          >
            <ListItemText primary={node.name} secondary={node.description} />
          </ListItemButton>
        ))}
      </List>
    </>
  );
};

export const Login: React.FC = () => {
  const { t } = useTranslation();
  const isLoggedIn = useAppSelector(selectIsAuthenticated);
  const [query] = useSearchParams();
  const navigate = useNavigate();
  const [login] = useLoginMutation();
  const [nodeSelectInfo, setNodeSelectInfo] = React.useState<NodeSelectInfo | null>(null);
  const [credentials, setCredentials] = React.useState<{ username: string; password: string } | null>(null);
  const [mfaRequired, setMfaRequired] = React.useState(false);
  const [selectedNode, setSelectedNode] = React.useState<number | null>(null);
  const [busy, setBusy] = React.useState(false);
  const prefilledUsername = query.get("username") ?? "";
  const showInvitationAcceptedHint = query.get("invitationAccepted") === "1" && prefilledUsername !== "";
  const initialValues = React.useMemo(
    () => ({
      username: credentials?.username ?? prefilledUsername,
      password: credentials?.password ?? "",
      mfa_code: "",
    }),
    [prefilledUsername, credentials]
  );

  useEffect(() => {
    if (isLoggedIn) {
      const next = query.get("next");
      const redirectUrl = next != null ? next : "/";
      navigate(redirectUrl);
    }
  }, [isLoggedIn, navigate, query]);

  const submitLogin = async (values: FormSchema, nodeId: number | null) => {
    setBusy(true);
    try {
      const result = await login({
        loginPayload: { ...values, node_id: nodeId, mfa_code: values.mfa_code || null },
      }).unwrap();
      if (result.available_nodes) {
        setNodeSelectInfo({
          username: values.username,
          password: values.password,
          availableNodes: result.available_nodes,
        });
      } else if (result.mfa_required) {
        setCredentials({ username: values.username, password: values.password });
        setNodeSelectInfo(null);
        setMfaRequired(true);
        if (result.mfa_error) toast.error(t(`auth.mfa.errors.${result.mfa_error}`));
      }
    } catch (err) {
      const error = err as { error?: string; data?: { detail?: string } };
      toast.error(t("auth.loginFailed", { reason: error.data?.detail ?? error.error }));
    } finally {
      setBusy(false);
    }
  };

  const handleSubmit = async (values: FormSchema, { setSubmitting }: FormikHelpers<FormSchema>) => {
    await submitLogin(values, selectedNode);
    setSubmitting(false);
  };

  return (
    <Container maxWidth="lg" disableGutters>
      <Paper
        sx={{
          display: "grid",
          gridTemplateColumns: { xs: "1fr", md: "1fr 1fr" },
          maxWidth: 1040,
          mx: "auto",
          overflow: "hidden",
          borderRadius: 3,
        }}
      >
        <Stack
          sx={{ display: { xs: "none", md: "flex" }, bgcolor: "#101827", color: "#ffffff", p: 5, minHeight: 560 }}
          justifyContent="space-between"
          spacing={5}
        >
          <Stack direction="row" alignItems="center" spacing={2}>
            <Box component="img" src={logoSrc} alt="" width={56} height={56} />
            <Typography variant="h6">{t("TeamFestlichPay")}</Typography>
          </Stack>
          <Box>
            <Typography variant="overline" sx={{ color: "#27cbbb", display: "block", mb: 2 }}>
              {t("portal.administration")}
            </Typography>
            <Typography
              variant="h3"
              component="p"
              sx={{ fontSize: "3rem", lineHeight: 1.15, whiteSpace: "pre-line", mb: 3 }}
            >
              {t("portal.loginTitle")}
            </Typography>
            <Typography sx={{ color: "#b6c5d8", maxWidth: 320, lineHeight: 1.8 }}>
              {t("portal.loginDescription")}
            </Typography>
          </Box>
          <Stack direction="row" spacing={1} sx={{ flexWrap: "wrap", gap: 1 }}>
            {["sales", "teams", "terminals"].map((key) => (
              <Chip
                key={key}
                label={t(`portal.${key}`)}
                variant="outlined"
                sx={{ color: "#d6e1ef", borderColor: "#3a4b63" }}
              />
            ))}
          </Stack>
        </Stack>
        <Stack sx={{ p: { xs: 3, sm: 5 }, py: { xs: 4, md: 7 }, minWidth: 0 }} justifyContent="center" spacing={3}>
          <Avatar
            sx={{
              backgroundColor: "primary.main",
              color: "primary.contrastText",
              borderRadius: 2,
              width: 48,
              height: 48,
            }}
          >
            <LockOutlinedIcon />
          </Avatar>

          {nodeSelectInfo ? (
            <SelectNode
              availableNodes={nodeSelectInfo.availableNodes}
              busy={busy}
              onSelect={(nodeId) => {
                setSelectedNode(nodeId);
                void submitLogin(
                  { username: nodeSelectInfo.username, password: nodeSelectInfo.password, mfa_code: "" },
                  nodeId
                );
              }}
            />
          ) : (
            <>
              <Box>
                <Typography component="h1" variant="h4">
                  {t("auth.signIn")}
                </Typography>
                <Typography color="text.secondary" sx={{ mt: 1 }}>
                  {t("portal.loginHint")}
                </Typography>
              </Box>
              {showInvitationAcceptedHint && (
                <Alert severity="success" sx={{ mt: 2, width: "100%" }}>
                  {t("auth.invitationLoginHint", { username: prefilledUsername })}
                </Alert>
              )}
              <Formik<FormSchema>
                initialValues={initialValues}
                enableReinitialize
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
                        autoComplete="username"
                        formik={formik}
                      />

                      <FormTextField
                        variant="outlined"
                        type="password"
                        name="password"
                        autoComplete="current-password"
                        label={t("auth.password")}
                        formik={formik}
                      />

                      {mfaRequired && (
                        <>
                          <Alert severity="info">{t("auth.mfa.loginHint")}</Alert>
                          <FormTextField
                            autoFocus
                            variant="outlined"
                            name="mfa_code"
                            label={t("auth.mfa.code")}
                            autoComplete="one-time-code"
                            formik={formik}
                          />
                        </>
                      )}
                      {formik.isSubmitting && <LinearProgress />}
                      <Button
                        type="submit"
                        fullWidth
                        variant="contained"
                        color="primary"
                        disabled={formik.isSubmitting}
                        sx={{ mt: 1, py: 1.5 }}
                      >
                        {t("auth.login")}
                      </Button>
                    </Stack>
                  </Form>
                )}
              </Formik>
            </>
          )}
        </Stack>
      </Paper>
    </Container>
  );
};
