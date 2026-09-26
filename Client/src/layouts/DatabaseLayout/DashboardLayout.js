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

import { useEffect } from "react";

// react-router-dom components
import { useLocation } from "react-router-dom";

// prop-types is a library for typechecking of props.
import PropTypes from "prop-types";

import MDBox from "components/MDBox";

import { usePlatformContext, setContextState } from "context";
import { T, LAYOUT, SPACE_FACTOR } from "assets/theme/base/tokens";
import pxToRemPlain from "assets/theme/functions/pxToRem";
import { SIDENAV_WIDTH } from "assets/theme/components/sidenav";
import { SIDENAV_MINI_WIDTH } from "components/SideMenu/SidenavRoot";

function DashboardLayout({ children }) {
  const [controller, dispatch] = usePlatformContext();
  const { miniSidenav, hideSidenav } = controller;
  const { pathname } = useLocation();

  useEffect(() => {
    setContextState(dispatch, "layout", "dashboard");
    document.body.style.overflow = null;
  }, [pathname]);

  // The page frame (SPEC.md section 2.5, 2026-09-26): the page background, 16 px side gutters on
  // a phone, 24 px on a tablet and 32 px on a wide screen, and one content column no wider than
  // 1120 px, centred in the space beside the sidebar, so a line of prose never runs the full
  // width of a large monitor. The sidebar is flush with the window's left edge.
  return (
    <MDBox
      sx={({ breakpoints, transitions, functions: { pxToRem } }) => ({
        px: { xs: SPACE_FACTOR.sm, md: SPACE_FACTOR.md, lg: SPACE_FACTOR.lg },
        pb: SPACE_FACTOR.xl,
        position: "relative",
        minHeight: "calc(100vh - 80px)",
        backgroundColor: T.page,
        maxWidth: "100vw",

        [breakpoints.up("xl")]: {
          marginLeft: miniSidenav ? pxToRem(SIDENAV_MINI_WIDTH) : pxToRem(SIDENAV_WIDTH),
          maxWidth: `calc(100vw - ${pxToRem(miniSidenav ? SIDENAV_MINI_WIDTH : SIDENAV_WIDTH)})`,
          transition: transitions.create(["margin-left", "margin-right"], {
            easing: transitions.easing.easeInOut,
            duration: transitions.duration.standard,
          }),
        },
      })}
    >
      <MDBox sx={{ maxWidth: pxToRemPlain(LAYOUT.contentMax), mx: "auto", width: "100%" }}>
        {children}
      </MDBox>
    </MDBox>
  );
}

// Typechecking props for the DashboardLayout
DashboardLayout.propTypes = {
  children: PropTypes.node.isRequired,
};

export default DashboardLayout;
