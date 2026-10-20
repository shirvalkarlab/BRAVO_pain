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

// Material Dashboard 2 React Base Styles
import colors from "assets/theme/base/colors";
import { FOCUS_RING } from "assets/theme/base/tokens";

const { transparent } = colors;

const iconButton = {
  styleOverrides: {
    root: {
      "&:hover": {
        backgroundColor: transparent.main,
      },
      // Keyboard focus ring (TASTE_AUDIT.md C1): icon buttons are the easiest to lose.
      "&:focus-visible, &.Mui-focusVisible": { ...FOCUS_RING },
    },
  },
};

export default iconButton;
