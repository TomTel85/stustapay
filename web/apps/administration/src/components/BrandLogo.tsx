import { Box } from "@mui/material";

export const logoSrc = "favicon.png";

export const BrandLogo = () => (
  <Box component="img" src={logoSrc} alt="" width={36} height={36} sx={{ display: "block", flexShrink: 0 }} />
);
