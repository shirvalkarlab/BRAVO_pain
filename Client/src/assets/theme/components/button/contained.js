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

// Contained buttons (SPEC.md section 4 rule 6): the one primary button per card is filled with
// the accent blue and carries white text (6.67:1). Every other contained button reads as a
// secondary button: white, a 1 px border in the caption grey, text in the title ink.
import { T, TYPE, SPACE } from "assets/theme/base/tokens";
import { BUTTON_HEIGHT } from "assets/theme/components/button/root";

import pxToRem from "assets/theme/functions/pxToRem";

const secondaryLook = {
  backgroundColor: T.surface,
  color: T.ink,
  border: `1px solid ${T.ink3}`,

  "&:hover": {
    backgroundColor: T.fillMuted,
  },

  "&:focus:not(:hover)": {
    backgroundColor: T.surface,
  },
};

const iconSize = (px) => ({
  "& .material-icon, .material-icons-round, svg": {
    fontSize: `${pxToRem(px)} !important`,
  },
});

const contained = {
  base: {
    ...secondaryLook,
    minHeight: pxToRem(BUTTON_HEIGHT.medium),
    padding: `${pxToRem(SPACE.xxs)} ${pxToRem(SPACE.sm)}`,

    "&:active, &:active:focus, &:active:hover": {
      opacity: 0.9,
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
    backgroundColor: T.accent,
    color: T.onFill,
    border: `1px solid ${T.accent}`,

    "&:hover": {
      backgroundColor: T.accent,
    },

    "&:focus:not(:hover)": {
      backgroundColor: T.accent,
    },
  },

  secondary: secondaryLook,
};

export default contained;
