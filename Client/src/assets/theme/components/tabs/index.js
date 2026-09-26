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

// Tabs as a quiet segmented control (SPEC.md sections 2.3 and 5.2): a muted band with 4 px
// corners; the selected tab is a white segment outlined in the accent blue, its text in the
// accent (see tab.js). No shadow.
import { T, RADIUS, SPACE, SHADOW } from "assets/theme/base/tokens";

import pxToRem from "assets/theme/functions/pxToRem";

const tabs = {
  styleOverrides: {
    root: {
      position: "relative",
      backgroundColor: T.fillMuted,
      borderRadius: pxToRem(RADIUS.sm),
      minHeight: "unset",
      padding: pxToRem(SPACE.xxs),
    },

    flexContainer: {
      height: "100%",
      position: "relative",
      zIndex: 10,
    },

    fixed: {
      overflow: "unset !important",
      overflowX: "unset !important",
    },

    vertical: {
      "& .MuiTabs-indicator": {
        width: "100%",
      },
    },

    indicator: {
      height: "100%",
      boxSizing: "border-box",
      borderRadius: pxToRem(RADIUS.sm),
      backgroundColor: T.surface,
      border: `1px solid ${T.accent}`,
      boxShadow: SHADOW.none,
      transition: "all 300ms ease",
    },
  },
};

export default tabs;
