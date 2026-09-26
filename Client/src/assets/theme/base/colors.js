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

// Values come from the design tokens (tokens.js, SPEC section 2); the key names are the
// Material Dashboard names the rest of the application imports, kept so nothing breaks.
import { T } from "assets/theme/base/tokens";

const flat = (c) => ({ main: c, state: c });

const colors = {
  background: {
    default: T.page,
  },

  text: {
    main: T.ink3,
    focus: T.ink2,
  },

  transparent: {
    main: "transparent",
  },

  white: {
    main: T.surface,
    focus: T.surface,
  },

  black: {
    light: "#000000",
    main: "#000000",
    focus: "#000000",
  },

  primary: {
    main: T.accent,
    focus: T.accent,
  },

  secondary: {
    main: T.ink3,
    focus: T.ink2,
  },

  info: {
    main: T.accent,
    focus: T.accent,
  },

  success: {
    main: T.bluishGreenText,
    focus: T.bluishGreenText,
  },

  warning: {
    main: T.caution,
    focus: T.caution,
  },

  error: {
    main: T.refused,
    focus: T.refused,
  },

  light: {
    main: T.fillMuted,
    focus: T.fillMuted,
  },

  dark: {
    main: T.ink,
    focus: T.ink2,
  },

  grey: {
    100: T.page,
    200: T.fillMuted,
    300: T.rule,
    400: "#BDBDBA",
    500: T.graphic,
    600: T.ink3,
    700: T.ink2,
    800: "#2A2A2A",
    900: T.ink,
  },

  // Flat fills: the minimalist design draws no gradients, so each pair is one colour.
  gradients: {
    primary: flat(T.accent),
    secondary: flat(T.ink3),
    info: flat(T.accent),
    success: flat(T.bluishGreenText),
    warning: flat(T.caution),
    error: flat(T.refused),
    light: flat(T.fillMuted),
    dark: flat(T.ink),
  },

  socialMediaColors: {
    facebook: { main: "#3b5998", dark: "#344e86" },
    twitter: { main: "#55acee", dark: "#3ea1ec" },
    instagram: { main: "#125688", dark: "#0e456d" },
    linkedin: { main: "#0077b5", dark: "#00669c" },
    pinterest: { main: "#cc2127", dark: "#b21d22" },
    youtube: { main: "#e52d27", dark: "#d41f1a" },
    vimeo: { main: "#1ab7ea", dark: "#13a3d2" },
    slack: { main: "#3aaf85", dark: "#329874" },
    dribbble: { main: "#ea4c89", dark: "#e73177" },
    github: { main: "#24292e", dark: "#171a1d" },
    reddit: { main: "#ff4500", dark: "#e03d00" },
    tumblr: { main: "#35465c", dark: "#2a3749" },
  },

  // Badge text is always a text-safe ink on its own tint.
  badgeColors: {
    primary: { background: T.accentTint, text: T.accent },
    secondary: { background: T.fillMuted, text: T.ink3 },
    info: { background: T.accentTint, text: T.accent },
    success: { background: T.fillMuted, text: T.bluishGreenText },
    warning: { background: T.cautionTint, text: T.caution },
    error: { background: T.refusedTint, text: T.refused },
    light: { background: T.surface, text: T.ink3 },
    dark: { background: T.fillMuted, text: T.ink },
  },

  coloredShadows: {
    primary: T.accent,
    secondary: T.ink3,
    info: T.accent,
    success: T.bluishGreenText,
    warning: T.caution,
    error: T.refused,
    light: T.rule,
    dark: T.ink,
  },

  inputBorderColor: T.graphic, // 3.45:1, meets the 3:1 minimum for a control's outline

  tabs: {
    indicator: { boxShadow: "transparent" },
  },
};

export default colors;
