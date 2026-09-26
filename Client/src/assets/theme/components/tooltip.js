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

// Tooltips (SPEC.md section 2.5): white, a 1 px hairline, the one soft overlay shadow, 12 px
// text in the title ink at full opacity (17.40:1), left-aligned so a sentence reads as one.
import Fade from "@mui/material/Fade";

import { T, TYPE, WEIGHT, FONT_FAMILY, RADIUS, SPACE, SHADOW } from "assets/theme/base/tokens";

import pxToRem from "assets/theme/functions/pxToRem";

const tooltip = {
  defaultProps: {
    arrow: true,
    TransitionComponent: Fade,
  },

  styleOverrides: {
    tooltip: {
      maxWidth: pxToRem(280),
      backgroundColor: T.surface,
      color: T.ink,
      border: `1px solid ${T.rule}`,
      boxShadow: SHADOW.overlay,
      fontFamily: FONT_FAMILY,
      fontSize: pxToRem(TYPE.caption.fontSize),
      lineHeight: TYPE.caption.lineHeight,
      fontWeight: WEIGHT.regular,
      textAlign: "left",
      borderRadius: pxToRem(RADIUS.sm),
      opacity: 1,
      padding: `${pxToRem(SPACE.xs)} ${pxToRem(SPACE.xs)}`,
    },

    arrow: {
      color: T.surface,

      "&::before": {
        border: `1px solid ${T.rule}`,
      },
    },
  },
};

export default tooltip;
