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

// The sidebar (SPEC.md section 2.5, 2026-09-26): a white column the full height of the window,
// divided from the page by one hairline, with no shadow and no rounded floating panel.
import { T, SHADOW } from "assets/theme/base/tokens";

import pxToRem from "assets/theme/functions/pxToRem";

export const SIDENAV_WIDTH = 250;

const sidenav = {
  styleOverrides: {
    root: {
      width: pxToRem(SIDENAV_WIDTH),
      whiteSpace: "nowrap",
      border: "none",
    },

    paper: {
      width: pxToRem(SIDENAV_WIDTH),
      backgroundColor: T.surface,
      height: "100vh",
      margin: 0,
      borderRadius: 0,
      border: "none",
      borderRight: `1px solid ${T.rule}`,
      boxShadow: SHADOW.none,
    },

    paperAnchorDockedLeft: {
      borderRight: `1px solid ${T.rule}`,
    },
  },
};

export default sidenav;
