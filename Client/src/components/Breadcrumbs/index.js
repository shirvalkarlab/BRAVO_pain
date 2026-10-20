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

// react-router-dom components
import { Link } from "react-router-dom";

// prop-types is a library for typechecking of props.
import PropTypes from "prop-types";

// @mui material components
import { Breadcrumbs as MuiBreadcrumbs } from "@mui/material";
import Icon from "@mui/material/Icon";

import MDBox from "components/MDBox";
import MDTypography from "components/MDTypography";

import { usePlatformContext } from "context";
import { dictionary } from "assets/translation";
import { dictionaryLookup } from "assets/translation";

function isUUID(str) {
  const regex = /^[0-9a-f]{8}[0-9a-f]{4}[4][0-9a-f]{3}[89ab][0-9a-f]{3}[0-9a-f]{12}$/i;
  return regex.test(str);
}

function Breadcrumbs({ icon, title, route, light }) {
  const [controller, ] = usePlatformContext();
  const { language } = controller;
  const routes = route.slice(0, -1);

  let participant_uid = ""
  if (isUUID(route[route.length-1])) {
    participant_uid = route[route.length-1]
    return (
      <MDBox mr={{ xs: 0, xl: 8 }}>
        <MuiBreadcrumbs
          sx={{
            "& .MuiBreadcrumbs-separator": {
              color: ({ palette: { white, grey } }) => (light ? white.main : grey[600]),
            },
          }}
        >
          <Link to="/database">
            <MDTypography
              component="span"
              variant="body2"
              color={light ? "white" : "dark"}
              opacity={light ? 0.8 : 0.5}
              sx={{ lineHeight: 0 }}
            >
              <Icon>{icon}</Icon>
            </MDTypography>
          </Link>
          {route.slice(0,-2).map((el) => {
            return <Link to={`/participant-overview/${participant_uid}`} key={el}>
              <MDTypography
                component="span"
                variant="button"
                fontWeight="regular"
                textTransform="capitalize"
                color={light ? "white" : "dark"}
                opacity={light ? 0.8 : 0.5}
                sx={{ lineHeight: 0 }}
              >
                {dictionary.Breadcrumbs[el] ? dictionary.Breadcrumbs[el][language] : el}
              </MDTypography>
            </Link>
          })}
          <MDTypography
            variant="button"
            fontWeight="regular"
            textTransform="capitalize"
            color={light ? "white" : "dark"}
            sx={{ lineHeight: 0 }}
          >
            {dictionaryLookup(dictionary.Breadcrumbs, route[route.length-2], language)}
          </MDTypography>
        </MuiBreadcrumbs>
        <MDTypography
          fontWeight="bold"
          textTransform="capitalize"
          variant="h6"
          color={light ? "white" : "dark"}
          noWrap
        >
          {dictionaryLookup(dictionary.Breadcrumbs, route[route.length-2], language)}
        </MDTypography>
      </MDBox>
    );
  } else {
    return (
      <MDBox mr={{ xs: 0, xl: 8 }}>
        <MuiBreadcrumbs
          sx={{
            "& .MuiBreadcrumbs-separator": {
              color: ({ palette: { white, grey } }) => (light ? white.main : grey[600]),
            },
          }}
        >
          <Link to="/database">
            <MDTypography
              component="span"
              variant="body2"
              color={light ? "white" : "dark"}
              opacity={light ? 0.8 : 0.5}
              sx={{ lineHeight: 0 }}
            >
              <Icon>{icon}</Icon>
            </MDTypography>
          </Link>
          {routes.map((el) => {
            return <Link to={`/${el}`} key={el}>
              <MDTypography
                component="span"
                variant="button"
                fontWeight="regular"
                textTransform="capitalize"
                color={light ? "white" : "dark"}
                opacity={light ? 0.8 : 0.5}
                sx={{ lineHeight: 0 }}
              >
                {dictionary.Breadcrumbs[el] ? dictionary.Breadcrumbs[el][language] : el}
              </MDTypography>
            </Link>
          })}
          <MDTypography
            variant="button"
            fontWeight="regular"
            textTransform="capitalize"
            color={light ? "white" : "dark"}
            sx={{ lineHeight: 0 }}
          >
            {dictionaryLookup(dictionary.Breadcrumbs, title, language)}
          </MDTypography>
        </MuiBreadcrumbs>
        <MDTypography
          fontWeight="bold"
          textTransform="capitalize"
          variant="h6"
          color={light ? "white" : "dark"}
          noWrap
        >
          {dictionaryLookup(dictionary.Breadcrumbs, title, language)}
        </MDTypography>
      </MDBox>
    );
  }
}

// Setting default values for the props of Breadcrumbs
Breadcrumbs.defaultProps = {
  light: false,
};

// Typechecking props for the Breadcrumbs
Breadcrumbs.propTypes = {
  icon: PropTypes.node.isRequired,
  title: PropTypes.string.isRequired,
  route: PropTypes.oneOfType([PropTypes.string, PropTypes.array]).isRequired,
  light: PropTypes.bool,
};

export default Breadcrumbs;
