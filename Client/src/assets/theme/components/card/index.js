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

// App shell (SPEC.md section 2.5, 2026-09-26): a card is white, a 1 px hairline border in the
// `rule` grey, 6 px corners and no shadow. Values come from the design tokens only.
import { CARD } from "assets/theme/base/tokens";

const card = {
  styleOverrides: {
    root: {
      display: "flex",
      flexDirection: "column",
      position: "relative",
      minWidth: 0,
      wordWrap: "break-word",
      backgroundColor: CARD.background,
      backgroundClip: "border-box",
      border: CARD.border,
      borderRadius: CARD.borderRadius,
      boxShadow: CARD.boxShadow,
      overflow: "visible",
    },
  },
};

export default card;
