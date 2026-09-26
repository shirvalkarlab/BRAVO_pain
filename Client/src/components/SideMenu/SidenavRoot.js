/**
=========================================================
* Material Dashboard 2 React - v2.1.0
=========================================================

* Product Page: https://www.creative-tim.com/product/material-dashboard-react
* Copyright 2022 Creative Tim (https://www.creative-tim.com)

Coded by www.creative-tim.com

 =========================================================

* The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.
*/

// The sidebar drawer (SPEC.md section 2.5, 2026-09-26): white, one hairline on its right edge,
// no shadow and no gradient, the full height of the window. The open, mini and hidden states
// and their transitions are unchanged. Dark mode is not supported on this pass (section 2.6).
import Drawer from "@mui/material/Drawer";
import { styled } from "@mui/material/styles";

import { T, SHADOW } from "assets/theme/base/tokens";
import { SIDENAV_WIDTH } from "assets/theme/components/sidenav";

export const SIDENAV_MINI_WIDTH = 96;

export default styled(Drawer)(({ theme, ownerState }) => {
  const { transitions, breakpoints, functions } = theme;
  const { hideSidenav, showSidenav, miniSidenav } = ownerState;
  const { pxToRem } = functions;

  const surface = {
    background: T.surface,
    borderRight: `1px solid ${T.rule}`,
    boxShadow: SHADOW.none,
  };

  // styles for the sidenav when miniSidenav={false}
  const drawerOpenStyles = () => ({
    ...surface,
    transform: "translateX(0)",
    transition: transitions.create("transform", {
      easing: transitions.easing.sharp,
      duration: transitions.duration.shorter,
    }),
    [breakpoints.up("xl")]: {
      left: "0",
      width: pxToRem(SIDENAV_WIDTH),
      transform: "translateX(0)",
      transition: transitions.create(["width", "background-color"], {
        easing: transitions.easing.sharp,
        duration: transitions.duration.enteringScreen,
      }),
    },
  });

  // styles for the sidenav when miniSidenav={true}
  const drawerCloseStyles = () => ({
    ...surface,
    transform: `translateX(${pxToRem(-320)})`,
    transition: transitions.create("transform", {
      easing: transitions.easing.sharp,
      duration: transitions.duration.shorter,
    }),
    [breakpoints.up("xl")]: {
      left: "0",
      width: pxToRem(SIDENAV_MINI_WIDTH),
      overflowX: "hidden",
      transform: "translateX(0)",
      transition: transitions.create(["width", "background-color"], {
        easing: transitions.easing.sharp,
        duration: transitions.duration.shorter,
      }),
    },
  });

  // styles for the sidenav when hideSidenav={true}
  const drawerHideStyles = () => ({
    ...surface,
    transform: `translateX(${pxToRem(-320)})`,
    transition: transitions.create("transform", {
      easing: transitions.easing.sharp,
      duration: transitions.duration.shorter,
    }),
  });

  return {
    "& .MuiDrawer-paper": {
      boxShadow: SHADOW.none,
      border: "none",
      ...(hideSidenav ? drawerHideStyles() : (miniSidenav && !showSidenav ? drawerCloseStyles() : drawerOpenStyles())),
    },
  };
});
