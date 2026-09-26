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

// One tab: 14 px, sentence case, body ink; the selected tab takes the accent blue and weight
// 600 (SPEC.md section 2.3: the accent marks the selected tab).
import { T, TYPE, WEIGHT, RADIUS, SPACE } from "assets/theme/base/tokens";

import pxToRem from "assets/theme/functions/pxToRem";

const tab = {
  styleOverrides: {
    root: {
      display: "flex",
      alignItems: "center",
      flexDirection: "row",
      flex: "1 1 auto",
      textAlign: "center",
      maxWidth: "unset !important",
      minWidth: "unset !important",
      minHeight: "unset !important",
      fontSize: pxToRem(TYPE.body.fontSize),
      fontWeight: WEIGHT.regular,
      letterSpacing: 0,
      textTransform: "none",
      lineHeight: "inherit",
      padding: `${pxToRem(SPACE.xxs)} ${pxToRem(SPACE.xs)}`,
      borderRadius: pxToRem(RADIUS.sm),
      color: `${T.ink2} !important`,
      opacity: "1 !important",

      "&.Mui-selected": {
        color: `${T.accent} !important`,
        fontWeight: WEIGHT.strong,
      },

      "& .material-icons, .material-icons-round": {
        marginBottom: "0 !important",
        marginRight: pxToRem(SPACE.xs),
      },

      "& svg": {
        marginBottom: "0 !important",
        marginRight: pxToRem(SPACE.xs),
      },
    },

    labelIcon: {
      paddingTop: pxToRem(SPACE.xxs),
    },
  },
};

export default tab;
