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

// Material Dashboard 2 React base styles
import typography from "assets/theme/base/typography";
import colors from "assets/theme/base/colors";

// Material Dashboard 2 React helper functions
import pxToRem from "assets/theme/functions/pxToRem";

const { size, fontWeightRegular, fontWeightBold } = typography;
const { white } = colors;

const stepLabel = {
  styleOverrides: {
    label: {
      marginTop: `${pxToRem(8)} !important`,
      fontWeight: fontWeightRegular,
      fontSize: size.xs,
      // White on the accent fill (8.0:1 at least; the pale blue it replaces was 4.0:1, under
      // the 4.5:1 text minimum). The current and done steps are set in weight 600.
      color: `${white.main} !important`,
      textTransform: "none", // sentence case everywhere (SPEC.md section 2.4)

      "&.Mui-active": {
        fontWeight: `${fontWeightBold} !important`,
        color: `${white.main} !important`,
      },

      "&.Mui-completed": {
        fontWeight: `${fontWeightBold} !important`,
        color: `${white.main} !important`,
      },
    },
  },
};

export default stepLabel;
