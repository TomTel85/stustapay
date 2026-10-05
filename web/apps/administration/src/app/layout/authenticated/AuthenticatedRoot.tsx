import { useGetProfileQuery, useGetTreeForCurrentUserQuery, useLogoutMutation } from "@/api";
import { config } from "@/api/common";
import { HelpRoutes, getNodeIdFromPath } from "@/app/routes";
import { AppBar, DrawerHeader, Main, LanguageSelect } from "@/components";
import { BrandLogo } from "@/components/BrandLogo";
import { drawerWidth } from "@/components/layouts/constants";
import { selectCurrentUser, setCurrentUser, useAppDispatch, useAppSelector } from "@/store";
import {
  AccountCircle as AccountCircleIcon,
  ChevronLeft as ChevronLeftIcon,
  ChevronRight as ChevronRightIcon,
  HelpOutline as HelpOutlineIcon,
  Logout as LogoutIcon,
  Menu as MenuIcon,
} from "@mui/icons-material";
import {
  Alert,
  AlertTitle,
  Box,
  Button,
  CircularProgress,
  CssBaseline,
  Divider,
  Drawer,
  IconButton,
  Toolbar,
  Typography,
  useMediaQuery,
} from "@mui/material";
import { useTheme } from "@mui/material/styles";
import { Loading, TestModeDisclaimer } from "@stustapay/components";
import * as React from "react";
import { useTranslation } from "react-i18next";
import { Navigate, Outlet, Link as RouterLink, useLocation, useNavigate } from "react-router-dom";
import { getCurrentNodePath } from "./currentNodePath";
import { NavigationTree } from "./navigation-tree";

const sidebarWidthKey = "administration.sidebarWidth";
const minSidebarWidth = 220;
const getMaxSidebarWidth = () => Math.max(minSidebarWidth, Math.min(600, window.innerWidth - 400));
const clampSidebarWidth = (width: number) =>
  Math.round(Math.max(minSidebarWidth, Math.min(getMaxSidebarWidth(), width)));

const readSidebarWidth = () => {
  try {
    const saved = Number(window.localStorage.getItem(sidebarWidthKey));
    return saved > 0 && Number.isFinite(saved) ? clampSidebarWidth(saved) : drawerWidth;
  } catch {
    return drawerWidth;
  }
};

export const AuthenticatedRoot: React.FC = () => {
  const { t } = useTranslation();
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down("md"));
  const [open, setOpen] = React.useState(!isMobile);
  const [sidebarWidth, setSidebarWidth] = React.useState(readSidebarWidth);
  const [resizing, setResizing] = React.useState(false);
  const resizeStart = React.useRef<{ x: number; width: number } | null>(null);
  const location = useLocation();
  const [logout] = useLogoutMutation();
  const navigate = useNavigate();
  const currentNodeId = getNodeIdFromPath(location.pathname);
  const helpRoute = HelpRoutes.index(currentNodeId);
  const dispatch = useAppDispatch();

  const user = useAppSelector(selectCurrentUser);
  const { data: currentProfile } = useGetProfileQuery(undefined, { skip: !user });

  const { data: tree, isLoading: isTreeLoading, error: treeError } = useGetTreeForCurrentUserQuery();

  const currentNodePath = React.useMemo(() => {
    if (!tree) {
      return null;
    }

    return getCurrentNodePath(tree, currentNodeId);
  }, [tree, currentNodeId]);

  React.useEffect(() => {
    if (isMobile) {
      setOpen(false);
      resizeStart.current = null;
      setResizing(false);
    }
  }, [isMobile]);

  React.useEffect(() => {
    try {
      window.localStorage.setItem(sidebarWidthKey, String(sidebarWidth));
    } catch {
      // Resizing still works when browser storage is unavailable.
    }
  }, [sidebarWidth]);

  React.useEffect(() => {
    const handleResize = () => setSidebarWidth((width) => clampSidebarWidth(width));
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, []);

  React.useEffect(() => {
    if (currentProfile) {
      dispatch(setCurrentUser(currentProfile));
    }
  }, [currentProfile, dispatch]);

  if (!user) {
    const next = location.pathname !== "/logout" ? `?next=${location.pathname}` : "";
    return <Navigate to={`/login${next}`} />;
  }

  const handleDrawerOpen = () => {
    setOpen(true);
  };

  const handleDrawerClose = () => {
    setOpen(false);
  };

  const handleLogout = () => {
    logout()
      .unwrap()
      .then(() => {
        navigate("/login");
      })
      .catch((err) => console.error("error during logout", err));
  };

  return (
    <Box
      sx={{
        display: "flex",
        "--sidebar-width": `${isMobile ? drawerWidth : sidebarWidth}px`,
        ...(resizing && {
          cursor: "col-resize",
          userSelect: "none",
          "& .MuiAppBar-root, & main": { transition: "none" },
        }),
      }}
    >
      <CssBaseline />
      <AppBar position="fixed" open={open}>
        <Toolbar sx={{ gap: { xs: 0.5, sm: 1 } }}>
          <IconButton
            color="inherit"
            aria-label="open drawer"
            onClick={handleDrawerOpen}
            edge="start"
            sx={{ mr: 2, ...(open && { display: "none" }) }}
          >
            <MenuIcon />
          </IconButton>
          <Box sx={{ flexGrow: 1, minWidth: 0, overflow: "hidden" }}>
            <RouterLink
              to="/"
              style={{
                textDecoration: "none",
                color: "inherit",
                display: "flex",
                alignItems: "center",
                gap: 12,
              }}
            >
              <BrandLogo />
              <Box sx={{ minWidth: 0 }}>
                <Typography
                  variant="h6"
                  component="div"
                  sx={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}
                >
                  {t("TeamFestlichPay")}
                </Typography>
                {currentNodePath && currentNodePath.length > 0 ? (
                  <Typography
                    variant="body2"
                    component="div"
                    sx={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", opacity: 0.85 }}
                  >
                    {currentNodePath.map((segment) => t(segment)).join(" > ")}
                  </Typography>
                ) : null}
              </Box>
            </RouterLink>
          </Box>
          <Box sx={{ display: "flex", alignItems: "center", gap: { xs: 0.5, sm: 1 }, flexShrink: 0 }}>
            {isMobile ? (
              <IconButton
                color="inherit"
                component={RouterLink}
                to={helpRoute}
                size="small"
                aria-label={t("help.open")}
              >
                <HelpOutlineIcon fontSize="small" />
              </IconButton>
            ) : (
              <Button component={RouterLink} color="inherit" to={helpRoute} startIcon={<HelpOutlineIcon />}>
                {t("help.open")}
              </Button>
            )}
            {isMobile ? (
              <IconButton
                color="inherit"
                component={RouterLink}
                to="/profile"
                size="small"
                aria-label={t("auth.profile")}
              >
                <AccountCircleIcon fontSize="small" />
              </IconButton>
            ) : (
              <Button component={RouterLink} color="inherit" to="/profile">
                {t("auth.profile")}
              </Button>
            )}
            <LanguageSelect
              variant="outlined"
              size="small"
              sx={{
                color: "inherit",
                minWidth: { xs: 74, sm: 96 },
                "& .MuiSelect-select": {
                  py: { xs: 0.5, sm: 0.75 },
                },
              }}
            />
            {isMobile ? (
              <IconButton color="inherit" onClick={handleLogout} size="small" aria-label={t("logout")}>
                <LogoutIcon fontSize="small" />
              </IconButton>
            ) : (
              <Button color="inherit" onClick={handleLogout}>
                {t("logout")}
              </Button>
            )}
          </Box>
        </Toolbar>
      </AppBar>
      <Drawer
        sx={{
          width: "var(--sidebar-width)",
          flexShrink: 0,
          "& .MuiDrawer-paper": {
            width: "var(--sidebar-width)",
            boxSizing: "border-box",
          },
        }}
        variant="persistent"
        anchor="left"
        open={open}
      >
        <DrawerHeader>
          <IconButton onClick={handleDrawerClose}>
            {theme.direction === "ltr" ? <ChevronLeftIcon /> : <ChevronRightIcon />}
          </IconButton>
        </DrawerHeader>
        <Divider />
        {/* <Sidebar /> */}
        {isTreeLoading ? (
          <Loading />
        ) : treeError ? (
          <Alert severity="error">
            <AlertTitle>Error loading tree data</AlertTitle>
          </Alert>
        ) : (
          <NavigationTree />
        )}
      </Drawer>
      {open && !isMobile && (
        <Box
          role="separator"
          aria-label={t("auth.resizeSidebar")}
          aria-orientation="vertical"
          aria-valuemin={minSidebarWidth}
          aria-valuemax={getMaxSidebarWidth()}
          aria-valuenow={sidebarWidth}
          tabIndex={0}
          onPointerDown={(event) => {
            if (event.button !== 0) return;
            event.preventDefault();
            event.currentTarget.focus();
            event.currentTarget.setPointerCapture(event.pointerId);
            resizeStart.current = { x: event.clientX, width: sidebarWidth };
            setResizing(true);
          }}
          onPointerMove={(event) => {
            if (resizeStart.current) {
              setSidebarWidth(clampSidebarWidth(resizeStart.current.width + event.clientX - resizeStart.current.x));
            }
          }}
          onLostPointerCapture={() => {
            resizeStart.current = null;
            setResizing(false);
          }}
          onPointerUp={(event) => event.currentTarget.releasePointerCapture(event.pointerId)}
          onPointerCancel={() => {
            resizeStart.current = null;
            setResizing(false);
          }}
          onDoubleClick={() => setSidebarWidth(clampSidebarWidth(drawerWidth))}
          onKeyDown={(event) => {
            const step = event.shiftKey ? 50 : 10;
            const widths: Record<string, number> = {
              ArrowLeft: sidebarWidth - step,
              ArrowRight: sidebarWidth + step,
              Home: minSidebarWidth,
              End: getMaxSidebarWidth(),
            };
            if (event.key in widths) {
              event.preventDefault();
              setSidebarWidth(clampSidebarWidth(widths[event.key]));
            }
          }}
          sx={{
            position: "fixed",
            top: 0,
            bottom: 0,
            left: sidebarWidth - 4,
            width: 8,
            zIndex: theme.zIndex.drawer + 1,
            cursor: "col-resize",
            touchAction: "none",
            "&::after": {
              content: '""',
              position: "absolute",
              inset: "0 3px",
              bgcolor: resizing ? "primary.main" : "transparent",
            },
            "&:hover::after, &:focus-visible::after": { bgcolor: "primary.main" },
          }}
        />
      )}
      <Main open={open}>
        <DrawerHeader />
        <TestModeDisclaimer testMode={config.testMode} testModeMessage={config.testModeMessage} />
        <React.Suspense fallback={<CircularProgress />}>
          {isTreeLoading ? (
            <Loading />
          ) : treeError ? (
            <Alert severity="error">
              <AlertTitle>Error loading tree data</AlertTitle>
            </Alert>
          ) : (
            <Outlet />
          )}
        </React.Suspense>
      </Main>
    </Box>
  );
};
