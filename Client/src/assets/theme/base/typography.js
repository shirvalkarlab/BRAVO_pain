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

// Values come from the design tokens (SPEC.md section 2.4, 2026-09-26): one face (IBM Plex
// Sans), weights 400 and 600, five sizes (12, 14, 16, 18, 22 px), sentence case everywhere.
// Removed as below the 11 px floor or outside the scale: fontSizeXXS (10.4 px), d1-d6 and
// fontWeightLighter. fontWeightLight is kept as a name because components import it; it now
// draws at 400, since no light weight is loaded.
// Line breaking (TASTE_AUDIT.md C5, 2026-09-26): headings h1-h6 balance their lines; body and
// subtitle prose avoids a lone last word ("pretty").
import { T, TYPE, WEIGHT, FONT_FAMILY, WRAP } from "assets/theme/base/tokens";

// Material Dashboard 2 React Helper Functions
import pxToRem from "assets/theme/functions/pxToRem";

const baseProperties = {
  fontFamily: FONT_FAMILY,
  fontWeightLight: WEIGHT.regular,
  fontWeightRegular: WEIGHT.regular,
  fontWeightMedium: WEIGHT.strong,
  fontWeightBold: WEIGHT.strong,
  fontSizeXS: pxToRem(TYPE.caption.fontSize),
  fontSizeSM: pxToRem(TYPE.body.fontSize),
  fontSizeMD: pxToRem(TYPE.lead.fontSize),
  fontSizeLG: pxToRem(TYPE.title.fontSize),
  fontSizeXL: pxToRem(TYPE.answer.fontSize),
  fontSize2XL: pxToRem(TYPE.answer.fontSize),
  fontSize3XL: pxToRem(TYPE.answer.fontSize),
};

const lineHeightOf = (role) => parseFloat(role.lineHeight) / role.fontSize;

const heading = (role) => ({
  fontFamily: baseProperties.fontFamily,
  color: T.ink,
  fontWeight: WEIGHT.strong,
  fontSize: pxToRem(role.fontSize),
  lineHeight: lineHeightOf(role),
  letterSpacing: 0,
  textTransform: "none",
  ...WRAP.balance,
});

const text = (role, weight = WEIGHT.regular) => ({
  fontFamily: baseProperties.fontFamily,
  fontSize: pxToRem(role.fontSize),
  fontWeight: weight,
  lineHeight: lineHeightOf(role),
  letterSpacing: 0,
  textTransform: "none",
});

const typography = {
  fontFamily: baseProperties.fontFamily,
  fontWeightLight: baseProperties.fontWeightLight,
  fontWeightRegular: baseProperties.fontWeightRegular,
  fontWeightMedium: baseProperties.fontWeightMedium,
  fontWeightBold: baseProperties.fontWeightBold,

  // The page answer
  h1: heading(TYPE.answer),
  h2: heading(TYPE.answer),
  h3: heading(TYPE.answer),
  // A section title, written as a question
  h4: heading(TYPE.title),
  h5: heading(TYPE.title),
  // A lead answer
  h6: heading(TYPE.lead),

  subtitle1: { ...text(TYPE.lead), ...WRAP.pretty },
  subtitle2: { ...text(TYPE.body), ...WRAP.pretty },
  body1: { ...text(TYPE.body), ...WRAP.pretty },
  body2: { ...text(TYPE.body), ...WRAP.pretty },
  button: text(TYPE.body, WEIGHT.strong),
  caption: text(TYPE.caption),
  overline: text(TYPE.caption),

  size: {
    // "xxs" is kept as a name (MDBadge reads it) but no longer draws below the minimum: 12 px.
    xxs: baseProperties.fontSizeXS,
    xs: baseProperties.fontSizeXS,
    sm: baseProperties.fontSizeSM,
    md: baseProperties.fontSizeMD,
    lg: baseProperties.fontSizeLG,
    xl: baseProperties.fontSizeXL,
    "2xl": baseProperties.fontSize2XL,
    "3xl": baseProperties.fontSize3XL,
  },

  lineHeight: {
    sm: 1.25,
    md: 1.5,
    lg: 2,
  },
};

export default typography;
