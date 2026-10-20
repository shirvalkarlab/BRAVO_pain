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

// Values come from the design tokens (SPEC.md section 2.5, 2026-09-26): no shadow on cards,
// the navigation bar, the sidebar or buttons. Menus, popovers, autocomplete lists and tooltips
// (the components that read `lg`) use the one overlay shadow. Every key components import is
// kept; the ones that meant "a raised surface" now read "none".
import { SHADOW } from "assets/theme/base/tokens";

const NONE = SHADOW.none;
const colored = {
  primary: NONE,
  secondary: NONE,
  info: NONE,
  success: NONE,
  warning: NONE,
  error: NONE,
  light: NONE,
  dark: NONE,
};

const boxShadows = {
  none: NONE,
  overlay: SHADOW.overlay,
  xs: NONE,
  sm: NONE,
  md: NONE, // cards, table containers, switches, sidenav items
  lg: SHADOW.overlay, // menus, popovers, autocomplete lists
  xl: NONE,
  xxl: NONE, // the sidebar and dialogs
  inset: NONE,
  colored,
  navbarBoxShadow: NONE,
  sliderBoxShadow: {
    thumb: SHADOW.overlay,
  },
  tabsBoxShadow: {
    indicator: NONE,
  },
};

export default boxShadows;
