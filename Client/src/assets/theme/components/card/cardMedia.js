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

import { RADIUS, SPACE } from "assets/theme/base/tokens";

import pxToRem from "assets/theme/functions/pxToRem";

const cardMedia = {
  styleOverrides: {
    root: {
      borderRadius: pxToRem(RADIUS.md),
      margin: `${pxToRem(SPACE.sm)} ${pxToRem(SPACE.sm)} 0`,
    },

    media: {
      width: "auto",
    },
  },
};

export default cardMedia;
