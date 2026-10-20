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

// Outlined buttons are the secondary button (SPEC.md section 4 rule 6): white, a 1 px border in
// the caption grey, text in the title ink. An outlined primary button keeps the accent for its
// border and text (6.67:1 on white).
import { T, TYPE, SPACE } from "assets/theme/base/tokens";
import { BUTTON_HEIGHT } from "assets/theme/components/button/root";

import pxToRem from "assets/theme/functions/pxToRem";

const iconSize = (px) => ({
  "& .material-icon, .material-icons-round, svg": {
    fontSize: `${pxToRem(px)} !important`,
  },
});

const outlined = {
  base: {
    minHeight: pxToRem(BUTTON_HEIGHT.medium),
    backgroundColor: T.surface,
    color: T.ink,
    borderColor: T.ink3,
    padding: `${pxToRem(SPACE.xxs)} ${pxToRem(SPACE.sm)}`,

    "&:hover": {
      backgroundColor: T.fillMuted,
      borderColor: T.ink3,
    },

    ...iconSize(TYPE.lead.fontSize),
  },

  small: {
    minHeight: pxToRem(BUTTON_HEIGHT.small),
    padding: `${pxToRem(SPACE.xxs)} ${pxToRem(SPACE.xs)}`,
    fontSize: pxToRem(TYPE.caption.fontSize),
    ...iconSize(TYPE.caption.fontSize),
  },

  large: {
    minHeight: pxToRem(BUTTON_HEIGHT.large),
    padding: `${pxToRem(SPACE.xs)} ${pxToRem(SPACE.md)}`,
    fontSize: pxToRem(TYPE.lead.fontSize),
    ...iconSize(TYPE.title.fontSize),
  },

  primary: {
    backgroundColor: T.surface,
    color: T.accent,
    borderColor: T.accent,

    "&:hover": {
      backgroundColor: T.accentTint,
      borderColor: T.accent,
    },
  },

  secondary: {
    backgroundColor: T.surface,
    color: T.ink,
    borderColor: T.ink3,

    "&:hover": {
      backgroundColor: T.fillMuted,
      borderColor: T.ink3,
    },
  },
};

export default outlined;
