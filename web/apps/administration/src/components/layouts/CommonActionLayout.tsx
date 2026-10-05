import { ChevronLeft } from "@mui/icons-material";
import { Box, Button, IconButton, Stack, Typography } from "@mui/material";
import * as React from "react";
import { useNavigate } from "react-router-dom";
import { LayoutAction } from "./types";
import { useTranslation } from "react-i18next";

export interface CommonActionLayoutProps {
  title: string;
  children?: React.ReactNode;
  actions?: LayoutAction[];
}

export const CommonActionLayout: React.FC<CommonActionLayoutProps> = ({ title, children, actions }) => {
  const navigate = useNavigate();
  const { t } = useTranslation();

  const renderedActions = actions?.map(({ hidden, label, icon, onClick, ...props }, index) => {
    if (hidden) {
      return null;
    }

    if (label) {
      return (
        <Button
          key={label}
          variant={props.color === "primary" ? "contained" : "outlined"}
          startIcon={icon}
          onClick={onClick}
          {...props}
        >
          {label}
        </Button>
      );
    }
    return (
      <IconButton key={index} onClick={onClick} {...props}>
        {icon}
      </IconButton>
    );
  });

  return (
    <Stack spacing={3}>
      <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 2 }}>
        <Stack direction="row" alignItems="center" spacing={1} sx={{ minWidth: 0 }}>
          <IconButton
            onClick={() => navigate(-1)}
            aria-label={t("portal.back")}
            sx={{ border: 1, borderColor: "divider", bgcolor: "background.paper" }}
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
        </Stack>
        <Stack direction="row" spacing={1} sx={{ flexWrap: "wrap", gap: 1 }}>
          {renderedActions}
        </Stack>
      </Box>
      {children}
    </Stack>
  );
};
