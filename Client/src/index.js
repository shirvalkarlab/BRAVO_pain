/**
=========================================================
* UF BRAVO Platform
=========================================================

* Copyright 2023 by Jackson Cagle, Fixel Institute
* The source code is made available under a Creative Common NonCommercial ShareAlike License (CC BY-NC-SA 4.0) (https://creativecommons.org/licenses/by-nc-sa/4.0/) 

 =========================================================

* The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.
*/

import { useState, useEffect } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Link, useLocation, useNavigate } from "react-router-dom";
import App from "App";

import { ThemeProvider } from "@mui/material/styles";
import {
  CssBaseline,
} from "@mui/material";

import LoadingProgress from "components/LoadingProgress";

import theme from "assets/theme";
import themeDark from "assets/theme-dark";

import { PlatformContextProvider } from "context.js";
import "assets/fontawesome/css/all.min.css";

import { usePlatformContext, setContextState } from "context.js";
import { SessionController } from "database/session-control";

function Main() {
  const navigate = useNavigate();

  const [controller, dispatch] = usePlatformContext();
  const { user, layout } = controller;
  const { pathname } = useLocation();

  const [sessionReady, setSessionReady] = useState(false);
  const [initialized, setInitialized] = useState(false);

  useEffect(() => {
    if (pathname.startsWith("/survey/")) {
      setSessionReady(true);
    } else {
      SessionController.syncSession().then((sessionStates) => {
        for (let key of Object.keys(sessionStates)) {
          setContextState(dispatch, key, sessionStates[key]);
        }
        setSessionReady(true);
      });
    }
  }, []);

  useEffect(() => {
    if (sessionReady) {
      if (Object.keys(user).length == 0) {
        setContextState(dispatch, "report", "");
        setContextState(dispatch, "participant_uid", null);
      }
      setInitialized(true);
      return;
    }

    const sessionTimeout = setTimeout(() => {
      setContextState(dispatch, "user", {});
      setContextState(dispatch, "report", "");
      setContextState(dispatch, "participant_uid", null);
      setInitialized(true);
    }, 5000);

    return () => clearTimeout(sessionTimeout);
  }, [sessionReady])

  useEffect(() => {
    
  }, [user])

  return initialized ? (
    <App />
  ) : (
    <LoadingProgress message={"Initializing"} />
  )
}

const root = createRoot(document.getElementById("root"))
root.render(
  <BrowserRouter>
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <PlatformContextProvider initialStates={{
        language: "en",
        user: {}
      }}>
        <Main />
      </PlatformContextProvider>
    </ThemeProvider>
  </BrowserRouter>,
);
