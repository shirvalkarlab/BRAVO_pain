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

function FullPageLayout({ children }) {
  const [controller, dispatch] = usePlatformContext();
  const { miniSidenav, hideSidenav } = controller;
  const { pathname } = useLocation();

  useEffect(() => {
    setContextState(dispatch, "layout", "full-page");
    document.body.style.overflow = null;
  }, [pathname]);

  return (
    <MDBox
      sx={({ breakpoints, transitions, functions: { pxToRem } }) => ({
        p: 3,
        position: "relative",
        minHeight: "calc(100vh)",

        [breakpoints.up("xl")]: {
          marginLeft: pxToRem(10),
          transition: transitions.create(["margin-left", "margin-right"], {
            easing: transitions.easing.easeInOut,
            duration: transitions.duration.standard,
          }),
        },
      })}
    >
      {children}
    </MDBox>
  );
}

// Typechecking props for the DashboardLayout
FullPageLayout.propTypes = {
  children: PropTypes.node.isRequired,
};

export default FullPageLayout;
