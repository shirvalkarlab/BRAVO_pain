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

// Values come from the design tokens (SPEC.md section 2.5, 2026-09-26): radius 4 for inputs,
// buttons and chips, 6 for cards. The older keys (xs, lg, xl, xxl) are kept because components
// import them; they now draw at 4 or 6. `section` stays fully round, for circular badges.
import { T, RADIUS } from "assets/theme/base/tokens";

// Material Dashboard 2 React Helper Functions
import pxToRem from "assets/theme/functions/pxToRem";

const borders = {
  borderColor: T.rule,

  borderWidth: {
    0: 0,
    1: pxToRem(1),
    2: pxToRem(2),
    3: pxToRem(3),
    4: pxToRem(4),
    5: pxToRem(5),
  },

  borderRadius: {
    none: 0,
    xs: pxToRem(RADIUS.sm),
    sm: pxToRem(RADIUS.sm),
    md: pxToRem(RADIUS.md),
    lg: pxToRem(RADIUS.md),
    xl: pxToRem(RADIUS.md),
    xxl: pxToRem(RADIUS.md),
    section: pxToRem(160),
  },
};

export default borders;
