import { ButtonProps } from "@mui/material";

export type LayoutAction = Pick<ButtonProps, "color" | "disabled" | "variant"> & {
  icon?: React.ReactNode;
  label?: string;
  onClick: React.MouseEventHandler;
  hidden?: boolean;
};
