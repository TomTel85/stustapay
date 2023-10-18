import { fetchConfig } from "@/api/common";
import { useAppSelector } from "@/store";
import { selectTheme } from "@/store/uiSlice";
import { createTheme, CssBaseline, PaletteMode, ThemeProvider, useMediaQuery } from "@mui/material";
import { Loading } from "@stustapay/components";
import * as React from "react";
import { toast, ToastContainer } from "react-toastify";
import { Router } from "./Router";

export function App() {
  const [loading, setLoading] = React.useState(true);
  const darkModeSystem = useMediaQuery("(prefers-color-scheme: dark)");
  const themeModeStore = useAppSelector(selectTheme);

  const themeMode: PaletteMode = themeModeStore === "browser" ? (darkModeSystem ? "dark" : "light") : themeModeStore;

  const theme = React.useMemo(
    () =>
      createTheme({
        palette: {
          mode: themeMode,
        },
      }),
    [themeMode]
  );

  React.useEffect(() => {
    const init = async () => {
      await fetchConfig();
    };
    init()
      .then(() => {
        setLoading(false);
      })
      .catch((e) => {
        console.log(e);
        toast.error(`Error while fetching config: ${e}`);
      });
  }, []);

  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <ToastContainer position="top-right" autoClose={4000} pauseOnFocusLoss={false} theme={themeMode} />
      {loading ? <Loading /> : <Router />}
    </ThemeProvider>
  );
}

export default App;
