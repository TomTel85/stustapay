import { Container, Link } from "@mui/material";
import { Box } from "@mui/system";
import { Trans, useTranslation } from "react-i18next";
import { Link as RouterLink } from "react-router-dom";

export const PrivacyPolicy = () => {
  useTranslation();

  return (
    <Container component="main" maxWidth="md">
      <Box sx={{ flexDirection: "column", alignItems: "center", width: "100%", textAlign: "justify" }}>
        <h2 id="datenschutz">Datenschutz</h2>
        <p>
          <Trans i18nKey="privacyPolicyHeader">
            link to
            <Link component={RouterLink} to="/agb">
              terms and conditions
            </Link>
            .
          </Trans>
        </p>
        <h3 id="tbd">tbd</h3>
        
      </Box>
    </Container>
  );
};
