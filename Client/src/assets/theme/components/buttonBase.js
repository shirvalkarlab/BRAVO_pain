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

// Every clickable Material UI element (buttons, icon buttons, tabs, menu items, list buttons)
// shows the keyboard focus ring (TASTE_AUDIT.md C1, 2026-09-26): Material UI turns the
// browser's own ring off on these, so without this rule keyboard focus was invisible.
import { FOCUS_RING } from "assets/theme/base/tokens";

const buttonBase = {
  defaultProps: {
    disableRipple: false,
  },
  styleOverrides: {
    root: {
      "&:focus-visible, &.Mui-focusVisible": { ...FOCUS_RING },
    },
  },
};

export default buttonBase;
