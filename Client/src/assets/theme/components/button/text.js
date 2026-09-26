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

// Text buttons: no fill, no shadow; text in the body ink, or the accent for a primary one.
import { T, TYPE, SPACE, SHADOW } from "assets/theme/base/tokens";
import { BUTTON_HEIGHT } from "assets/theme/components/button/root";

import pxToRem from "assets/theme/functions/pxToRem";

const iconSize = (px) => ({
  "& .material-icon, .material-icons-round, svg": {
    fontSize: `${pxToRem(px)} !important`,
  },
});

const buttonText = {
  base: {
    backgroundColor: "transparent",
    minHeight: pxToRem(BUTTON_HEIGHT.medium),
    color: T.ink2,
    boxShadow: SHADOW.none,
    padding: `${pxToRem(SPACE.xxs)} ${pxToRem(SPACE.xs)}`,

    "&:hover": {
      backgroundColor: T.fillMuted,
      boxShadow: SHADOW.none,
    },

    "&:focus, &:active, &:active:focus, &:active:hover, &:disabled": {
      boxShadow: SHADOW.none,
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
    padding: `${pxToRem(SPACE.xs)} ${pxToRem(SPACE.sm)}`,
    fontSize: pxToRem(TYPE.lead.fontSize),
    ...iconSize(TYPE.title.fontSize),
  },

  primary: {
    color: T.accent,

    "&:hover": {
      color: T.accent,
      backgroundColor: T.accentTint,
    },

    "&:focus:not(:hover)": {
      color: T.accent,
      boxShadow: SHADOW.none,
    },
  },

  secondary: {
    color: T.ink3,

    "&:hover": {
      color: T.ink2,
    },

    "&:focus:not(:hover)": {
      color: T.ink3,
      boxShadow: SHADOW.none,
    },
  },
};

export default buttonText;
