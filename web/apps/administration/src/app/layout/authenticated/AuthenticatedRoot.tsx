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
  MoreVert as MoreVertIcon,
} from "@mui/icons-material";
import {
  Alert,
  AlertTitle,
  Box,
  Breadcrumbs,
  Button,
  CircularProgress,
  CssBaseline,
  Divider,
  Drawer,
  IconButton,
  ListItemIcon,
  ListSubheader,
  Menu,
  MenuItem,
  Toolbar,
  Typography,
  useMediaQuery,
} from "@mui/material";
import { alpha, useTheme } from "@mui/material/styles";
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
    return saved > 0 && Number.isFinite(saved)
      ? Math.round(Math.max(minSidebarWidth, Math.min(600, saved)))
      : drawerWidth;
  } catch {
    return drawerWidth;
  }
};

export const AuthenticatedRoot: React.FC = () => {
  const { t, i18n } = useTranslation();
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down("md"));
  const [actionsAnchor, setActionsAnchor] = React.useState<HTMLElement | null>(null);
  const actionsMenuId = React.useId();
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
    if (isMobile) setOpen(false);
    setActionsAnchor(null);
  }, [isMobile, location.pathname]);

  React.useEffect(() => {
    if (isMobile) return;
    try {
      window.localStorage.setItem(sidebarWidthKey, String(sidebarWidth));
    } catch {
      // Resizing still works when browser storage is unavailable.
    }
  }, [sidebarWidth, isMobile]);

  React.useEffect(() => {
    const handleResize = () => {
      if (window.innerWidth >= theme.breakpoints.values.md) {
        setSidebarWidth((width) => clampSidebarWidth(width));
      }
    };
    handleResize();
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, [theme.breakpoints.values.md]);

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
      <AppBar position="fixed" open={open && !isMobile}>
        <Toolbar sx={{ gap: 1 }}>
          <IconButton
            color="inherit"
            aria-label={t("portal.openNavigation")}
            onClick={handleDrawerOpen}
            edge="start"
            sx={{ width: 44, height: 44, flexShrink: 0, ...(open && { display: "none" }) }}
          >
            <MenuIcon />
          </IconButton>
          <Box
            title={currentNodePath?.map((segment) => t(segment)).join(" / ")}
            sx={{ flexGrow: 1, minWidth: 0, overflow: "hidden" }}
          >
            <Breadcrumbs
              aria-label={t("portal.workspace")}
              separator={<ChevronRightIcon sx={{ fontSize: 16, color: "text.disabled" }} />}
              sx={{
                py: 1,
                "& .MuiBreadcrumbs-ol": { gap: 0.5, flexWrap: "nowrap" },
                "& .MuiBreadcrumbs-li": { minWidth: 0, maxWidth: "100%", overflow: "hidden" },
                "& .MuiBreadcrumbs-separator": { mx: 0 },
              }}
            >
              {(currentNodePath?.length
                ? isMobile
                  ? currentNodePath.slice(-1)
                  : currentNodePath
                : ["portal.administration"]
              ).map((segment, index, path) =>
                index === path.length - 1 ? (
                  <Box
                    key={index}
                    aria-current="location"
                    sx={{
                      display: "inline-flex",
                      alignItems: "center",
                      gap: 1,
                      px: 1.5,
                      py: 0.625,
                      borderRadius: 2,
                      bgcolor: alpha(theme.palette.primary.main, 0.1),
                      border: "1px solid",
                      borderColor: alpha(theme.palette.primary.main, 0.18),
                      maxWidth: "100%",
                    }}
                  >
                    <Box sx={{ width: 6, height: 6, borderRadius: "50%", bgcolor: "primary.main", flexShrink: 0 }} />
                    <Typography
                      sx={{
                        fontWeight: 700,
                        fontSize: { xs: "0.875rem", sm: "1rem" },
                        lineHeight: 1.4,
                        minWidth: 0,
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                        whiteSpace: "nowrap",
                      }}
                    >
                      {t(segment)}
                    </Typography>
                  </Box>
                ) : (
                  <Typography key={index} color="text.secondary" noWrap sx={{ fontSize: "0.8125rem" }}>
                    {t(segment)}
                  </Typography>
                )
              )}
            </Breadcrumbs>
          </Box>
          {isMobile ? (
            <>
              <IconButton
                color="inherit"
                aria-label={t("actions")}
                aria-controls={actionsAnchor ? actionsMenuId : undefined}
                aria-haspopup="menu"
                aria-expanded={Boolean(actionsAnchor)}
                onClick={(event) => setActionsAnchor(event.currentTarget)}
                sx={{ width: 44, height: 44, flexShrink: 0 }}
              >
                <MoreVertIcon />
              </IconButton>
              <Menu
                id={actionsMenuId}
                anchorEl={actionsAnchor}
                open={Boolean(actionsAnchor)}
                onClose={() => setActionsAnchor(null)}
                anchorOrigin={{ vertical: "bottom", horizontal: "right" }}
                transformOrigin={{ vertical: "top", horizontal: "right" }}
                slotProps={{ paper: { sx: { minWidth: 220 } }, list: { "aria-label": t("actions") } }}
              >
                <MenuItem component={RouterLink} to={helpRoute} onClick={() => setActionsAnchor(null)}>
                  <ListItemIcon>
                    <HelpOutlineIcon fontSize="small" />
                  </ListItemIcon>
                  {t("help.open")}
                </MenuItem>
                <MenuItem component={RouterLink} to="/profile" onClick={() => setActionsAnchor(null)}>
                  <ListItemIcon>
                    <AccountCircleIcon fontSize="small" />
                  </ListItemIcon>
                  {t("auth.profile")}
                </MenuItem>
                <Divider />
                <ListSubheader>{t("settings.language")}</ListSubheader>
                {[
                  { code: "de-DE", label: "languages.de" },
                  { code: "en-US", label: "languages.en" },
                ].map(({ code, label }) => (
                  <MenuItem
                    key={code}
                    selected={i18n.language === code}
                    onClick={() => {
                      i18n.changeLanguage(code);
                      setActionsAnchor(null);
                    }}
                  >
                    {t(label)}
                  </MenuItem>
                ))}
                <Divider />
                <MenuItem
                  onClick={() => {
                    setActionsAnchor(null);
                    handleLogout();
                  }}
                >
                  <ListItemIcon>
                    <LogoutIcon fontSize="small" />
                  </ListItemIcon>
                  {t("logout")}
                </MenuItem>
              </Menu>
            </>
          ) : (
            <Box sx={{ display: "flex", alignItems: "center", gap: 1, flexShrink: 0 }}>
              <Button component={RouterLink} color="inherit" to={helpRoute} startIcon={<HelpOutlineIcon />}>
                {t("help.open")}
              </Button>
              <Button component={RouterLink} color="inherit" to="/profile">
                {t("auth.profile")}
              </Button>
              <LanguageSelect variant="outlined" size="small" sx={{ color: "inherit", minWidth: 96 }} />
              <Button color="inherit" onClick={handleLogout}>
                {t("logout")}
              </Button>
            </Box>
          )}
        </Toolbar>
      </AppBar>
      <Drawer
        sx={{
          width: isMobile ? 0 : "var(--sidebar-width)",
          flexShrink: 0,
          "& .MuiDrawer-paper": {
            width: isMobile ? "min(320px, 88vw)" : "var(--sidebar-width)",
            boxSizing: "border-box",
            bgcolor: "background.paper",
            borderRight: 1,
            borderColor: "divider",
          },
        }}
        variant={isMobile ? "temporary" : "persistent"}
        anchor="left"
        open={open}
        onClose={handleDrawerClose}
      >
        <DrawerHeader sx={{ px: 2, gap: 1.5 }}>
          <BrandLogo />
          <Typography variant="subtitle2" sx={{ flexGrow: 1, fontWeight: 700 }}>
            {t("portal.administration")}
          </Typography>
          <IconButton onClick={handleDrawerClose} aria-label={t("portal.closeNavigation")} size="small">
            {theme.direction === "ltr" ? <ChevronLeftIcon /> : <ChevronRightIcon />}
          </IconButton>
        </DrawerHeader>
        <Divider />
        <Typography variant="overline" color="text.secondary" sx={{ px: 2.5, pt: 2, pb: 1 }}>
          {t("portal.workspace")}
        </Typography>
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
      <Main open={open || isMobile}>
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
