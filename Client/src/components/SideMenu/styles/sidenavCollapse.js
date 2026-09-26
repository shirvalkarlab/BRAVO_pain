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

// One navigation item (SPEC.md sections 2.3 and 2.5, 2026-09-26): 14 px in the body ink on
// white; the active item is the accent blue (6.67:1 on white, 5.98:1 on its tint) on the accent
// tint, weight 600, with a 4 px accent bar on its left edge so the state is not carried by
// colour alone. Hover uses the muted fill. No shadow, no gradient. The `ownerState` flags the
// old dark and transparent sidebars read are still accepted and no longer change the look.
import { T, TYPE, WEIGHT, RADIUS, SPACE, SHADOW } from "assets/theme/base/tokens";

function collapseItem(theme, ownerState) {
  const { transitions, breakpoints, functions } = theme;
  const { active } = ownerState;
  const { pxToRem } = functions;

  return {
    background: active ? T.accentTint : "transparent",
    color: active ? T.accent : T.ink2,
    display: "flex",
    alignItems: "center",
    width: "100%",
    padding: `${pxToRem(SPACE.xs)} ${pxToRem(SPACE.xs)}`,
    margin: `${pxToRem(SPACE.xxs / 2)} ${pxToRem(SPACE.sm)}`,
    borderRadius: pxToRem(RADIUS.sm),
    borderLeft: `${pxToRem(SPACE.xxs)} solid ${active ? T.accent : "transparent"}`,
    cursor: "pointer",
    userSelect: "none",
    whiteSpace: "nowrap",
    boxShadow: SHADOW.none,

    [breakpoints.up("xl")]: {
      transition: transitions.create(["background-color", "color"], {
        easing: transitions.easing.easeInOut,
        duration: transitions.duration.shorter,
      }),
    },

    "&:hover, &:focus": {
      backgroundColor: active ? T.accentTint : T.fillMuted,
    },
  };
}

function collapseIconBox(theme, ownerState) {
  const { transitions, functions } = theme;
  const { active } = ownerState;
  const { pxToRem } = functions;

  return {
    minWidth: pxToRem(SPACE.lg),
    minHeight: pxToRem(SPACE.lg),
    color: active ? T.accent : T.ink3,
    borderRadius: pxToRem(RADIUS.sm),
    display: "grid",
    placeItems: "center",
    transition: transitions.create("margin", {
      easing: transitions.easing.easeInOut,
      duration: transitions.duration.standard,
    }),

    "& svg, svg g": {
      color: active ? T.accent : T.ink3,
    },
  };
}

const collapseIcon = (theme, { active }) => ({
  color: active ? T.accent : T.ink3,
});

function collapseText(theme, ownerState) {
  const { transitions, breakpoints, functions } = theme;
  const { miniSidenav, active } = ownerState;
  const { pxToRem } = functions;

  return {
    marginLeft: pxToRem(SPACE.xs),

    [breakpoints.up("xl")]: {
      opacity: miniSidenav ? 0 : 1,
      maxWidth: miniSidenav ? 0 : "100%",
      marginLeft: miniSidenav ? 0 : pxToRem(SPACE.xs),
      transition: transitions.create(["opacity", "margin"], {
        easing: transitions.easing.easeInOut,
        duration: transitions.duration.standard,
      }),
    },

    "& span": {
      color: active ? T.accent : T.ink2,
      fontWeight: active ? WEIGHT.strong : WEIGHT.regular,
      fontSize: pxToRem(TYPE.body.fontSize),
      lineHeight: TYPE.body.lineHeight,
      letterSpacing: 0,
      whiteSpace: "normal",
    },
  };
}

export { collapseItem, collapseIconBox, collapseIcon, collapseText };
