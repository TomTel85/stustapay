import { useGetMfaStatusQuery } from "@/api";
import { Alert, AlertTitle, Box, Button } from "@mui/material";
import { useTranslation } from "react-i18next";
import { Link as RouterLink } from "react-router-dom";

export const MfaReminder = () => {
  const { t } = useTranslation();
  const { data: status, error } = useGetMfaStatusQuery();

  if (!status || error || status.enabled) return null;

  return (
    <Alert severity="warning" sx={{ mb: 2, "& .MuiAlert-message": { width: "100%", minWidth: 0 } }}>
      <Box sx={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 1 }}>
        <Box sx={{ flex: "1 1 320px" }}>
          <AlertTitle>{t("auth.mfa.reminderTitle")}</AlertTitle>
          {t("auth.mfa.reminderText")}
        </Box>
        <Button component={RouterLink} to="/profile" color="inherit" size="small" sx={{ flexShrink: 0 }}>
          {t("auth.mfa.setup")}
        </Button>
      </Box>
    </Alert>
  );
};
