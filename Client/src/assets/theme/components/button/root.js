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

// App shell (SPEC.md section 4 rule 6, 2026-09-26): buttons are 36 px tall, 14 px, weight 600,
// sentence case with no letter-spacing, 4 px corners and no shadow. Values from the tokens.
// Keyboard focus (TASTE_AUDIT.md C1, 2026-09-26): a 2 px accent ring 2 px outside the button,
// on keyboard focus only; a mouse click draws none.
import {
  TYPE, WEIGHT, FONT_FAMILY, RADIUS, SPACE, SHADOW, FOCUS_RING,
} from "assets/theme/base/tokens";

import pxToRem from "assets/theme/functions/pxToRem";

export const BUTTON_HEIGHT = { small: 32, medium: 36, large: 40 };

const root = {
  display: "inline-flex",
  justifyContent: "center",
  alignItems: "center",
  fontFamily: FONT_FAMILY,
  fontSize: pxToRem(TYPE.body.fontSize),
  fontWeight: WEIGHT.strong,
  borderRadius: pxToRem(RADIUS.sm),
  padding: `${pxToRem(SPACE.xxs)} ${pxToRem(SPACE.sm)}`,
  lineHeight: TYPE.body.lineHeight,
  letterSpacing: 0,
  textAlign: "center",
  textTransform: "none",
  userSelect: "none",
  boxShadow: SHADOW.none,
  transition: "background-color 150ms ease-in, border-color 150ms ease-in",

  "&:hover, &:focus, &:active": {
    boxShadow: SHADOW.none,
  },

  "&:focus-visible, &.Mui-focusVisible": { ...FOCUS_RING },

  "&:disabled": {
    pointerEvent: "none",
    opacity: 0.65,
  },

  "& .material-icons": {
    fontSize: pxToRem(TYPE.lead.fontSize),
    marginTop: 0,
  },
};

export default root;
