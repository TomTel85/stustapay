import { styled } from "@mui/material/styles";
import { drawerWidth } from "./constants";

export const Main = styled("main", { shouldForwardProp: (prop) => prop !== "open" })<{
  open?: boolean;
}>(({ theme, open }) => ({
  flexGrow: 1,
  minWidth: 0,
  minHeight: "100dvh",
  padding: theme.spacing(3),
  transition: theme.transitions.create("margin", {
    easing: theme.transitions.easing.sharp,
    duration: theme.transitions.duration.leavingScreen,
  }),
  marginLeft: `calc(-1 * var(--sidebar-width, ${drawerWidth}px))`,
  ...(open && {
    transition: theme.transitions.create("margin", {
      easing: theme.transitions.easing.easeOut,
      duration: theme.transitions.duration.enteringScreen,
    }),
    marginLeft: 0,
  }),
  [theme.breakpoints.down("md")]: { padding: theme.spacing(2) },
  [theme.breakpoints.up("lg")]: { padding: theme.spacing(4) },
}));
