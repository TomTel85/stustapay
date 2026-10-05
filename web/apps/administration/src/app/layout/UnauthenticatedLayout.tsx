import { AppBar, Box, Container, CssBaseline, Toolbar } from "@mui/material";
import * as React from "react";

export interface UnauthenticatedLayoutProps {
  toolbar?: React.ReactNode;
  children?: React.ReactNode;
}

export const UnauthenticatedLayout: React.FC<UnauthenticatedLayoutProps> = ({ toolbar, children }) => {
  return (
    <Box sx={{ display: "flex", minHeight: "100dvh" }}>
      <CssBaseline />
      <AppBar position="fixed">
        <Toolbar>{toolbar}</Toolbar>
      </AppBar>

      <Box
        component="main"
        sx={{
          flexGrow: 1,
        }}
      >
        <Toolbar />
        <Container maxWidth="lg" sx={{ py: { xs: 4, md: 7 }, px: { xs: 2, md: 3 } }}>
          {children}
        </Container>
      </Box>
    </Box>
  );
};
