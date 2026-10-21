import { MfaResult, MfaUpdate, useGetMfaStatusQuery, useUpdateMfaMutation } from "@/api";
import {
  Alert,
  Box,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Paper,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import React from "react";
import QRCode from "react-qr-code";
import { useTranslation } from "react-i18next";

export const MfaSettings: React.FC = () => {
  const { t } = useTranslation();
  const { data: status, error: statusError, refetch } = useGetMfaStatusQuery();
  const [update, { isLoading, reset }] = useUpdateMfaMutation();
  const [pendingAction, setPendingAction] = React.useState<Exclude<MfaUpdate["action"], "setup"> | null>(null);
  const confirmationTitleId = React.useId();
  const [password, setPassword] = React.useState("");
  const [code, setCode] = React.useState("");
  const [setup, setSetup] = React.useState<MfaResult | null>(null);
  const [recoveryCodes, setRecoveryCodes] = React.useState<string[] | null>(null);
  const [error, setError] = React.useState<string | null>(null);

  const openConfirmation = (action: Exclude<MfaUpdate["action"], "setup">) => {
    setPassword("");
    setError(null);
    setPendingAction(action);
  };

  const closeConfirmation = () => {
    if (isLoading) return;
    setPendingAction(null);
    setPassword("");
    setError(null);
  };

  const act = async (action: MfaUpdate["action"], confirmationPassword = "") => {
    setError(null);
    try {
      setPassword("");
      const result = await update({ mfaUpdate: { action, password: confirmationPassword, code } }).unwrap();
      if (!result.success) {
        setError(t(`auth.mfa.errors.${result.error}`));
        return;
      }
      setCode("");
      if (action === "setup") {
        setSetup(result);
      } else {
        setSetup(null);
        setPendingAction(null);
        setPassword("");
        setRecoveryCodes(result.recovery_codes ?? null);
      }
      await refetch();
    } catch {
      setError(t("auth.mfa.requestFailed"));
    } finally {
      reset();
    }
  };

  return (
    <Paper sx={{ p: 2 }}>
      <Stack spacing={2}>
        <Typography variant="h5">{t("auth.mfa.title")}</Typography>
        {statusError ? (
          <Alert severity="error">{t("auth.mfa.requestFailed")}</Alert>
        ) : !status ? (
          <Typography>{t("auth.mfa.loading")}</Typography>
        ) : (
          <>
            <Typography>{t(status.enabled ? "auth.mfa.enabled" : "auth.mfa.disabled")}</Typography>
            {status.enabled && (
              <Typography>{t("auth.mfa.remaining", { count: status.recovery_codes_remaining })}</Typography>
            )}
            {error && !pendingAction && <Alert severity="error">{error}</Alert>}
            {recoveryCodes ? (
              <>
                <Alert severity="warning">{t("auth.mfa.saveRecovery")}</Alert>
                <Box component="pre" sx={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere", userSelect: "all" }}>
                  {recoveryCodes.join("\n")}
                </Box>
                <Button onClick={() => setRecoveryCodes(null)}>{t("auth.mfa.savedRecovery")}</Button>
              </>
            ) : (
              <Box
                component="form"
                onSubmit={(event: React.FormEvent) => {
                  event.preventDefault();
                  if (!setup && !status.enabled) {
                    void act("setup");
                  } else {
                    openConfirmation(setup ? "enable" : "regenerate");
                  }
                }}
              >
                <Stack spacing={2}>
                  {setup?.provisioning_uri && (
                    <>
                      <Typography>{t("auth.mfa.scan")}</Typography>
                      <Box sx={{ bgcolor: "white", p: 2, alignSelf: "flex-start" }}>
                        <QRCode value={setup.provisioning_uri} size={180} title={t("auth.mfa.qrTitle")} />
                      </Box>
                      <TextField
                        label={t("auth.mfa.secret")}
                        value={setup.secret ?? ""}
                        slotProps={{ input: { readOnly: true } }}
                      />
                    </>
                  )}
                  {(setup || status.enabled) && (
                    <TextField
                      required
                      autoComplete="one-time-code"
                      label={t("auth.mfa.code")}
                      value={code}
                      onChange={(event) => setCode(event.target.value)}
                    />
                  )}
                  <Stack direction="row" spacing={2} sx={{ flexWrap: "wrap", gap: 1 }}>
                    <Button type="submit" variant="contained" disabled={isLoading}>
                      {t(setup ? "auth.mfa.confirm" : status.enabled ? "auth.mfa.regenerate" : "auth.mfa.setup")}
                    </Button>
                    {status.enabled && (
                      <Button
                        color="error"
                        disabled={isLoading || !code.trim()}
                        onClick={() => openConfirmation("disable")}
                      >
                        {t("auth.mfa.disable")}
                      </Button>
                    )}
                    {setup && (
                      <Button
                        disabled={isLoading}
                        onClick={() => {
                          setSetup(null);
                          setPassword("");
                          setCode("");
                        }}
                      >
                        {t("auth.mfa.cancel")}
                      </Button>
                    )}
                  </Stack>
                </Stack>
              </Box>
            )}
          </>
        )}
      </Stack>
      <Dialog
        open={pendingAction !== null}
        onClose={closeConfirmation}
        disableEscapeKeyDown={isLoading}
        aria-labelledby={confirmationTitleId}
        fullWidth
        maxWidth="xs"
      >
        <Box
          component="form"
          onSubmit={(event: React.FormEvent) => {
            event.preventDefault();
            if (pendingAction && password && !isLoading) void act(pendingAction, password);
          }}
        >
          <DialogTitle id={confirmationTitleId}>{t("auth.mfa.confirmChange")}</DialogTitle>
          <DialogContent>
            <Stack spacing={2} sx={{ pt: 1 }}>
              <Typography>{t("auth.mfa.passwordHint")}</Typography>
              {error && <Alert severity="error">{error}</Alert>}
              <TextField
                autoFocus
                type="password"
                autoComplete="current-password"
                required
                fullWidth
                label={t("auth.mfa.password")}
                value={password}
                disabled={isLoading}
                onChange={(event) => setPassword(event.target.value)}
              />
            </Stack>
          </DialogContent>
          <DialogActions>
            <Button disabled={isLoading} onClick={closeConfirmation}>
              {t("cancel")}
            </Button>
            <Button type="submit" variant="contained" disabled={isLoading || !password}>
              {t("confirm")}
            </Button>
          </DialogActions>
        </Box>
      </Dialog>
    </Paper>
  );
};
