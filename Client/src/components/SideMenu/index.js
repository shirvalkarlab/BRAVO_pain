import { useEffect, useState } from "react";

// react-router-dom components
import { useLocation, NavLink, matchPath } from "react-router-dom";

// prop-types is a library for typechecking of props.
import PropTypes from "prop-types";

// @mui material components
import List from "@mui/material/List";
import Divider from "@mui/material/Divider";
import Link from "@mui/material/Link";
import Icon from "@mui/material/Icon";
import Tooltip from "@mui/material/Tooltip";
import { featureAvailability, loadFeatureInformation, publishFeatureInformation } from "views/Dashboard/ParticipantOverview/featureAvailability";

import MDBox from "components/MDBox";
import MDTypography from "components/MDTypography";
import SidenavCollapse from "components/SideMenu/SidenavCollapse";

// Custom styles for the Sidenav
import SidenavRoot from "components/SideMenu/SidenavRoot";
import sidenavLogoLabel from "components/SideMenu/styles/sidenav";

import {
  usePlatformContext,
  setContextState,
} from "context";

import { dictionary } from "assets/translation";

const SideMenu = ({ color, brand, brandName, routes, ...rest }) => {
  const [openCollapse, setOpenCollapse] = useState(false);
  const [openNestedCollapse, setOpenNestedCollapse] = useState(false);
  const [controller, dispatch] = usePlatformContext();
  const { miniSidenav, transparentSidenav, hideSidenav, showSidenav, whiteSidenav, language, darkMode, user, report, participant_uid } = controller;

  const location = useLocation();
  const { pathname } = location;
  const pathParticipant = Object.values(routes).flatMap((group) => group.children || [])
    .map((item) => item.route && matchPath(item.route, pathname))
    .find((match) => match && match.params.participant_uid);
  const availabilityUid = pathParticipant ? pathParticipant.params.participant_uid : participant_uid;

  useEffect(() => {
    if (!availabilityUid || pathname === "/database" || pathname.startsWith("/group-analysis")) return undefined;
    let cancelled = false;
    const refresh = () => loadFeatureInformation(availabilityUid).then(({ data }) => {
      if (!cancelled) publishFeatureInformation(dispatch, availabilityUid, data);
    }).catch(() => {
      if (!cancelled) dispatch({ name: "participantFeatureAvailability", value: {
        participantUid: availabilityUid, features: {}, error: "Availability could not be checked",
      } });
    });
    refresh();
    window.addEventListener("focus", refresh);
    return () => { cancelled = true; window.removeEventListener("focus", refresh); };
  }, [availabilityUid, pathname, dispatch]);
  const collapseName = pathname.split("/").slice(1)[0];
  const items = pathname.split("/").slice(1);
  const itemParentName = items[1];
  const itemName = items[items.length - 1];

  let textColor = "white";

  if (transparentSidenav || (whiteSidenav && !darkMode)) {
    textColor = "dark";
  } else if (whiteSidenav && darkMode) {
    textColor = "inherit";
  }

  const closeSidenav = () => setContextState(dispatch, "hideSidenav", true);

  useEffect(() => {
    // A function that sets the mini state of the sidenav.
    function handleMiniSidenav() {
      setContextState(dispatch, "hideSidenav", window.innerWidth < 1200);
      setContextState(dispatch, "showSidenav", window.innerWidth < 1200);
    }

    setOpenCollapse(collapseName);

    /** 
     The event listener that's calling the handleMiniSidenav function when resizing the window.
    */
    window.addEventListener("resize", handleMiniSidenav);

    // Call the handleMiniSidenav function to set the state with the initial value.
    handleMiniSidenav();

    // Remove event listener on cleanup
    return () => window.removeEventListener("resize", handleMiniSidenav);
  }, [dispatch, location]);

  const renderCollapse = (collapses) => {
    return collapses.map(({ name, collapse, route, href, key, icon }) => {
      let returnValue;

      var nameString = "";
      if (Object.keys(dictionary.Routes).includes(name)) {
        nameString = dictionary.Routes[name][language];
      } else {
        nameString = name;
      }

      returnValue = href ? (
        <NavLink to={route} key={key}>
          <SidenavCollapse
            name={nameString}
            icon={icon}
            active={key === itemName}
          >
          </SidenavCollapse>
        </NavLink>
      ) : (
        <NavLink to={route} key={key} sx={{ textDecoration: "none" }}>
          <SidenavCollapse
            name={nameString}
            icon={icon}
            active={key === itemName}
          >
          </SidenavCollapse>
        </NavLink>
      );

      return <List key={key} sx={{paddingLeft: 2}}>
        {returnValue}
      </List>;
    });
  };

  // Render all the routes from the routes.js (All the visible items on the Sidenav)
  const renderRoute = ({ type, name, icon, title, collapse, noCollapse, key, hide, href, route, report_type }) => {
    let returnValue;

    if (hide) return;

    var nameString = "";
    if (Object.keys(dictionary.Routes).includes(name)) {
      nameString = dictionary.Routes[name][language];
    } else {
      nameString = name;
    }

    if (report_type && (report_type != report)) {
      return returnValue;
    }

    if (type === "collapse") {
      if (noCollapse && route) {
        returnValue = (
          <NavLink to={route.replace(":participant_uid",availabilityUid)} key={key}>
            <SidenavCollapse
              name={nameString}
              icon={icon}
              active={key === itemName}
            >
              {collapse ? renderCollapse(collapse) : null}
            </SidenavCollapse>
          </NavLink>
        );
      } else {
        returnValue = (
          <SidenavCollapse
            key={key}
            name={nameString}
            icon={icon}
            active={key === collapseName}
            open={openCollapse === key}
            onClick={() => (openCollapse === key ? setOpenCollapse(false) : setOpenCollapse(key))}
          >
            {collapse ? renderCollapse(collapse) : null}
          </SidenavCollapse>
        );
      }

    } else if (type === "title") {
      returnValue = (
        <MDTypography
          key={key}
          color={textColor}
          display="block"
          variant="caption"
          fontWeight="bold"
          textTransform="uppercase"
          pl={3}
          mt={2}
          mb={1}
          ml={1}
          sx={{display: {xs: "block", xl: miniSidenav && !showSidenav ? "none" : "block"}, whiteSpace: "normal", overflowWrap: "anywhere", pr: 2}}
        >
          {nameString}
        </MDTypography>
      );
    } else if (type === "divider") {
      returnValue = (
        <Divider
          key={key}
          light={
            (!darkMode && !whiteSidenav && !transparentSidenav) ||
            (darkMode && !transparentSidenav && whiteSidenav)
          }
        />
      );
    }

    return returnValue;
  };

  const allRoutes = routes.Main.children.map(renderRoute);

  let reportName = report;
  if (pathname == "/database" || pathname.startsWith("/group-analysis")) {
    reportName = "StudyGroupAnalysis";
  }

  return (
    <SidenavRoot
      {...rest}
      variant="permanent"
      ownerState={{ transparentSidenav, whiteSidenav, miniSidenav, hideSidenav, showSidenav, darkMode }}
    >
      <MDBox pt={3} pb={1} px={3} textAlign="center" sx={{ flexShrink: 0 }}>
        <MDBox
          display={{ xs: "block", xl: "none" }}
          position="absolute"
          top={0}
          right={0}
          p={1.625}
          onClick={closeSidenav}
          sx={{ cursor: "pointer" }}
        >
          <MDTypography variant="h6" color="secondary">
            <Icon sx={{ fontWeight: "bold" }}>close</Icon>
          </MDTypography>
        </MDBox>
        <MDBox component={NavLink} to="/" aria-label={brandName || "BRAVO home"} display="flex" alignItems="center" sx={{width: "100%", minWidth: 0}}>
          {brand && <MDBox component="img" src={brand} alt="Brand" width="2rem" sx={{ flexShrink: 0 }} />}
          <MDBox
            sx={(theme) => sidenavLogoLabel(theme, { miniSidenav: miniSidenav && !showSidenav })}
          >
            <MDTypography component="h6" variant="button" fontWeight="medium" color={textColor}>
              {brandName}
            </MDTypography>
          </MDBox>
        </MDBox>
      </MDBox>
      <Divider
        light={
          (!darkMode && !whiteSidenav && !transparentSidenav) ||
          (darkMode && !transparentSidenav && whiteSidenav)
        }
      />
      <List>{allRoutes}</List>
      <Divider
        light={
          (!darkMode && !whiteSidenav && !transparentSidenav) ||
          (darkMode && !transparentSidenav && whiteSidenav)
        }
      />
      {routes[reportName] ? (
        <List key={reportName}>{routes[reportName].children.map(({ key, name, title, icon, route }) => {
          var nameString = "";
          if (Object.keys(dictionary.Routes).includes(name)) {
            nameString = dictionary.Routes[name][language];
          } else {
            nameString = name;
          }

          if (title) {
            return (
              <MDTypography
                key={key}
                color={textColor}
                display="block"
                variant="caption"
                fontWeight="bold"
                textTransform="uppercase"
                pl={3}
                mt={2}
                mb={1}
                ml={1}
                sx={{display: {xs: "block", xl: miniSidenav && !showSidenav ? "none" : "block"}, whiteSpace: "normal", overflowWrap: "anywhere", pr: 2}}
              >
                {nameString}
              </MDTypography>
            );
          }

          if (!route) return null;
          const availability = featureAvailability(key, controller.participantFeatureAvailability, availabilityUid);
          if (!availability.available) return (
            <Tooltip title={availability.reason} placement="right" key={`${reportName}-${key}`}>
              <MDBox role="link" aria-disabled="true" tabIndex={0} sx={{ opacity: 0.5, cursor: "not-allowed" }}>
                <SidenavCollapse name={`${nameString} — ${availability.reason}`} icon={icon} active={false} />
              </MDBox>
            </Tooltip>
          );

          return <NavLink to={route.replace(":participant_uid",availabilityUid)} key={`${reportName}-${key}`}>
            <SidenavCollapse
              name={nameString}
              icon={icon}
              active={key === itemName}
            >
            </SidenavCollapse>
          </NavLink>;
        })}</List>
      ) : null}
    </SidenavRoot>
  );
}

export default SideMenu;