import { alpha, createTheme, PaletteMode } from "@mui/material/styles";
import type {} from "@mui/x-data-grid/themeAugmentation";

export const createAdministrationTheme = (mode: PaletteMode) => {
  const dark = mode === "dark";
  const accent = dark ? "#27cbbb" : "#087f75";
  const border = dark ? "#2a374a" : "#e2e8f0";
  const paper = dark ? "#151f30" : "#ffffff";

  return createTheme({
    palette: {
      mode,
      primary: { main: accent, contrastText: dark ? "#101827" : "#ffffff" },
      secondary: { main: dark ? "#a6b6ce" : "#516582" },
      background: { default: dark ? "#0c1422" : "#f4f7fa", paper },
      text: { primary: dark ? "#eef3f9" : "#172438", secondary: dark ? "#a6b6ce" : "#5a6b82" },
      divider: border,
    },
    shape: { borderRadius: 12 },
    typography: {
      fontFamily: '"Roboto", sans-serif',
      h1: { fontWeight: 700, letterSpacing: "-0.04em" },
      h2: { fontWeight: 700, letterSpacing: "-0.035em" },
      h3: { fontWeight: 700, letterSpacing: "-0.03em" },
      h4: { fontWeight: 700, letterSpacing: "-0.025em", fontSize: "2rem" },
      h5: { fontWeight: 700, letterSpacing: "-0.02em" },
      h6: { fontWeight: 700, letterSpacing: "-0.015em" },
      button: { textTransform: "none", fontWeight: 500 },
      overline: { fontWeight: 700, letterSpacing: "0.12em" },
    },
    components: {
      MuiCssBaseline: {
        styleOverrides: {
          body: { backgroundImage: "none" },
          "::selection": { backgroundColor: alpha(accent, 0.24) },
          "#root :focus-visible": { outline: `2px solid ${accent}`, outlineOffset: 3 },
          "@media (prefers-reduced-motion: reduce)": {
            "*, *::before, *::after": {
              animationDuration: "0.01ms !important",
              transitionDuration: "0.01ms !important",
              scrollBehavior: "auto !important",
            },
          },
        },
      },
      MuiAppBar: {
        defaultProps: { elevation: 0, color: "transparent" },
        styleOverrides: {
          root: {
            color: dark ? "#eef3f9" : "#172438",
            backgroundColor: alpha(paper, 0.96),
            backgroundImage: "none",
            backdropFilter: "blur(16px)",
            borderBottom: `1px solid ${border}`,
          },
        },
      },
      MuiPaper: {
        defaultProps: { elevation: 0 },
        styleOverrides: { root: { backgroundImage: "none" }, rounded: { border: `1px solid ${border}` } },
      },
      MuiButton: {
        defaultProps: { disableElevation: true },
        styleOverrides: {
          root: { borderRadius: 8, padding: "8px 16px", whiteSpace: "nowrap" },
          outlined: { borderColor: border },
          contained: { boxShadow: `0 2px 4px ${alpha(accent, 0.12)}` },
        },
      },
      MuiIconButton: { styleOverrides: { root: { borderRadius: 10 } } },
      MuiOutlinedInput: {
        styleOverrides: {
          root: { borderRadius: 8, backgroundColor: paper },
          notchedOutline: { borderColor: dark ? "#41516a" : "#c7d2df" },
        },
      },
      MuiTableCell: {
        styleOverrides: {
          root: { borderColor: border, padding: "14px 16px" },
          head: { fontWeight: 700, color: dark ? "#a6b6ce" : "#5a6b82", backgroundColor: dark ? "#192638" : "#f8fafc" },
        },
      },
      MuiDataGrid: {
        styleOverrides: {
          root: {
            borderColor: border,
            backgroundColor: paper,
            borderRadius: 12,
            "--DataGrid-containerBackground": dark ? "#192638" : "#f8fafc",
            "& .MuiDataGrid-columnHeaderTitle": { fontWeight: 700, color: dark ? "#a6b6ce" : "#5a6b82" },
            "& .MuiDataGrid-cell, & .MuiDataGrid-columnHeaders, & .MuiDataGrid-footerContainer": {
              borderColor: border,
            },
            "& .MuiDataGrid-row:hover": { backgroundColor: alpha(accent, 0.04) },
          },
        },
      },
      MuiChip: { styleOverrides: { root: { borderRadius: 6, fontWeight: 500 } } },
      MuiAlert: { styleOverrides: { root: { borderRadius: 10 } } },
      MuiTabs: { styleOverrides: { indicator: { height: 3, borderRadius: 3 } } },
      MuiTab: { styleOverrides: { root: { textTransform: "none", fontWeight: 500, minHeight: 52 } } },
      MuiTooltip: { defaultProps: { arrow: true } },
    },
  });
};
