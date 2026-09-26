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

// Breadcrumbs: 14 px, sentence case, in the caption grey (6.48:1 on the page background). The
// crumbs are drawn at full opacity so none falls under 4.5:1; the component's own half-opacity
// setting is overridden here, where the theme can reach it.
import { T, TYPE } from "assets/theme/base/tokens";

import pxToRem from "assets/theme/functions/pxToRem";

const breadcrumbs = {
  styleOverrides: {
    li: {
      lineHeight: 0,

      "& .MuiTypography-root": {
        color: `${T.ink3} !important`,
        opacity: "1 !important",
        textTransform: "none !important",
        fontSize: `${pxToRem(TYPE.body.fontSize)} !important`,
      },
    },

    separator: {
      fontSize: pxToRem(TYPE.body.fontSize),
      color: `${T.ink3} !important`,
    },
  },
};

export default breadcrumbs;
