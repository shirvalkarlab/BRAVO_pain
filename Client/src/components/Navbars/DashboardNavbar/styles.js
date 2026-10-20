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
// The top bar (SPEC.md section 2.5, 2026-09-26): the page background, one hairline beneath it,
// no shadow, no blur, square corners; text in the title ink. Dark mode is not supported on this
// pass (section 2.6), so the "darkMode" and "light" flags no longer change the colours.
import { T, SHADOW, SPACE } from "assets/theme/base/tokens";

function navbar(theme, ownerState) {
  const { functions, transitions, breakpoints } = theme;
  const { absolute } = ownerState;
  const { pxToRem } = functions;

  return {
    boxShadow: SHADOW.none,
    backdropFilter: "none",
    backgroundColor: absolute ? "transparent !important" : T.page,
    borderBottom: absolute ? "none" : `1px solid ${T.rule}`,
    color: T.ink,
    top: 0,
    minHeight: pxToRem(SPACE.xl + SPACE.xs),
    display: "grid",
    alignItems: "center",
    borderRadius: 0,
    marginBottom: pxToRem(SPACE.md),
    paddingTop: pxToRem(SPACE.xs),
    paddingBottom: pxToRem(SPACE.xs),
    paddingRight: absolute ? pxToRem(SPACE.xs) : 0,
    paddingLeft: absolute ? pxToRem(SPACE.sm) : 0,

    "& > *": {
      transition: transitions.create("all", {
        easing: transitions.easing.easeInOut,
        duration: transitions.duration.standard,
      }),
    },

    // The page heading the breadcrumbs draw is shown in sentence case, as its label is written.
    "& .MuiTypography-root": {
      textTransform: "none",
      letterSpacing: 0,
    },

    // On a phone the crumbs wrap onto more than one line. Their labels are drawn with a line
    // height of 0 (to sit level with the home icon on a wide screen), so wrapped lines were drawn
    // on top of each other and over the page title under them (taste audit E1, 2026-09-26). Below
    // the md breakpoint the crumbs get a real line height and the list may wrap.
    "& .MuiBreadcrumbs-ol": {
      flexWrap: "wrap",
    },
    "& .MuiBreadcrumbs-root .MuiTypography-root": {
      [breakpoints.down("md")]: {
        lineHeight: 1.5,
      },
    },

    "& .MuiToolbar-root": {
      display: "flex",
      justifyContent: "space-between",
      alignItems: "center",

      [breakpoints.up("sm")]: {
        minHeight: "auto",
        padding: `${pxToRem(SPACE.xxs)} 0`,
      },
    },
  };
}

const navbarContainer = ({ breakpoints }) => ({
  flexDirection: "column",
  alignItems: "flex-start",
  justifyContent: "space-between",
  pt: 0.5,
  pb: 0.5,

  [breakpoints.up("md")]: {
    flexDirection: "row",
    alignItems: "center",
    paddingTop: "0",
    paddingBottom: "0",
  },
});

const navbarRow = ({ breakpoints }, { isMini }) => ({
  display: "flex",
  alignItems: "center",
  justifyContent: "space-between",
  width: "100%",
  // The breadcrumb block may shrink below its text's width, so a long page name is cut with an
  // ellipsis (the heading is drawn `noWrap`) instead of widening the page on a phone.
  "& > :first-of-type": {
    minWidth: 0,
    maxWidth: "100%",
  },

  [breakpoints.up("md")]: {
    justifyContent: isMini ? "space-between" : "stretch",
    width: isMini ? "100%" : "max-content",
  },

  [breakpoints.up("xl")]: {
    justifyContent: "stretch !important",
    width: "max-content !important",
  },
});

const navbarIconButton = ({ typography: { size }, breakpoints }) => ({
  px: 1,
  color: T.ink3,

  "& .material-icons, .material-icons-round": {
    fontSize: `${size.xl} !important`,
  },

  "& .MuiTypography-root": {
    display: "none",

    [breakpoints.up("sm")]: {
      display: "inline-block",
      lineHeight: 1.2,
      ml: 0.5,
    },
  },
});

const navbarMobileMenu = ({ breakpoints }) => ({
  display: "inline-block",
  lineHeight: 0,
  paddingLeft: 3,

  [breakpoints.up("xl")]: {
    display: "none",
  },
});

export { navbar, navbarContainer, navbarRow, navbarIconButton, navbarMobileMenu };
