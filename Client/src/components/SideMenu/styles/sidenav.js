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

// The product name at the top of the sidebar: 16 px, weight 600, the title ink, sentence case
// as written. The name itself is the PI's to choose and is not changed here.
import { T, TYPE, WEIGHT } from "assets/theme/base/tokens";

export default function sidenavLogoLabel(theme, ownerState) {
  const { functions, transitions, breakpoints } = theme;
  const { miniSidenav } = ownerState;
  const { pxToRem } = functions;

  return {
    ml: 1,
    color: T.ink,
    fontWeight: WEIGHT.strong,
    fontSize: pxToRem(TYPE.lead.fontSize),
    letterSpacing: 0,
    textTransform: "none",
    transition: transitions.create("opacity", {
      easing: transitions.easing.easeInOut,
      duration: transitions.duration.standard,
    }),

    [breakpoints.up("xl")]: {
      opacity: miniSidenav ? 0 : 1,
    },
  };
}
