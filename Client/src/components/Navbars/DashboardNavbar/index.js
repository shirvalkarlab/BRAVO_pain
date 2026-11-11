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

import { useState, useEffect } from "react";
import { useLocation, Link, useNavigate } from "react-router-dom";
import PropTypes from "prop-types";

// @material-ui core components
import { 
  AppBar,
  Avatar,
  Dialog,
  Toolbar,
  Icon,
  IconButton,
  Menu,
  MenuItem,
  CircularProgress
} from "@mui/material";

import {
  Translate,
  ChangeCircle,
  PublishedWithChanges
} from '@mui/icons-material';

import { FaArrowRightFromBracket, FaUser } from "react-icons/fa6";

import MDBox from "components/MDBox";
import MDInput from "components/MDInput";
import MDBadge from "components/MDBadge";
import Breadcrumbs from "components/Breadcrumbs";
import ProcessingQueue from "components/ProcessingQueue";

// Custom styles for DashboardNavbar
import {
  navbar,
  navbarContainer,
  navbarRow,
  navbarIconButton,
  navbarMobileMenu,
} from "components/Navbars/DashboardNavbar/styles";

//  BRAVO context
import { usePlatformContext, setContextState } from "context";
import { dictionary } from "assets/translation";
import { SessionController } from "database/session-control";
import MDTypography from "components/MDTypography";
import { T, SPACE, MIN_TEXT_PX } from "assets/theme/base/tokens";
import SkipToContent from "components/Navbars/DashboardNavbar/SkipToContent";
import { openNotificationSocket } from "./notificationSocket";

function DashboardNavbar({ absolute, light, isMini, fixedNavbar }) {
  const navigate = useNavigate();
  const [alert, setAlert] = useState(null);
  const [queueState, setQueueState] = useState({queues: [], show: false})
  const [navbarType, setNavbarType] = useState();
  const [controller, dispatch] = usePlatformContext();
  const { miniSidenav, hideSidenav, transparentNavbar, darkMode, language, user } = controller;
  const [openMenu, setOpenMenu] = useState(false);
  const [whichMenu, setWhichMenu] = useState("");

  const route = useLocation().pathname.split("/").slice(1);

  function handleTransparentNavbar() {
    setContextState(dispatch, "transparentNavbar", (fixedNavbar && window.scrollY === 0) || !fixedNavbar);
  }

  useEffect(() => {
    if (Object.keys(user).length == 0) {
      setContextState(dispatch, "user", {});
      setContextState(dispatch, "participant_uid", null);
      navigate("/", {replace: false});
      return;
    };

    // Live processing-queue notifications. The server-side WebSocket endpoint (/socket/notification)
    // is NOT implemented (the ASGI app is HTTP-only, no Channels consumer), so this connection is
    // expected to fail; the queue still updates on navigation/poll. Fail QUIETLY -- don't spam the
    // console with "Connection Error"/"Connection Closed" on every page load, and don't reconnect.
    // The onmessage handler is kept intact so that if a Channels backend is ever added, live updates
    // work with no frontend change.
    const client = openNotificationSocket(() => SessionController.getServer().replace("http","ws") + "/socket/notification");
    if (client) {
    client.onerror = function() {
      // endpoint not implemented; ignore quietly
    };
    client.onopen = () => {
      
    };
    client.onclose = () => {
      // expected when the endpoint is absent; ignore quietly
    };

    client.onmessage = (event) => {
      let content = JSON.parse(event.data);
      if (content["Notification"] === "QueueUpdate") {
        if (content["UpdateType"] === "JobCompletion") {
          setQueueState(currentState => {
            for (let i in currentState.queues) {
              if (currentState.queues[i].taskId == content["TaskID"]) {
                currentState.queues[i].state = content["State"];
                currentState.queues[i].descriptor = {...currentState.queues[i].descriptor, Message: content["Message"]};
              }
            }
            return {...currentState};
          });
        } else if (content["UpdateType"] === "JobUpdate") {
          setQueueState(currentState => {
            for (let i in currentState.queues) {
              if (currentState.queues[i].taskId == content["TaskID"]) {
                currentState.queues[i].state = content["State"];
                currentState.queues[i].descriptor = {...currentState.queues[i].descriptor, Message: content["Message"]};
              }
            }
            return {...currentState};
          });
        } else if (content["UpdateType"] === "NewJob") {
          setQueueState(currentState => {
            currentState.queues.push(content["NewJob"]);
            return {...currentState};
          });
        }
      }
    };
    }

    return () => {
      if (client) { try { client.close(); } catch (e) { /* already closed */ } }
    }
  }, []);

  useEffect(() => {
    // Setting the navbar type
    if (fixedNavbar) {
      setNavbarType("sticky");
    } else {
      setNavbarType("static");
    }
  }, [dispatch, fixedNavbar]);

  const handleHideSidenav = () => {
    setContextState(dispatch, "hideSidenav", !hideSidenav);
  };
  const handleMiniSidenav = () => setContextState(dispatch, "miniSidenav", !miniSidenav);
  const handleOpenMenu = (event, name) => {
    setOpenMenu(event.currentTarget);
    setWhichMenu(name);
  }
  const handleCloseMenu = () => {
    setWhichMenu("");
    setOpenMenu(null);
  };

  const logoutUser = () => {
    SessionController.logout().then((response) => {
      SessionController.nullifyUser();
      setContextState(dispatch, "user", {});
      setContextState(dispatch, "report", "");
      setContextState(dispatch, "participant_uid", null);
      navigate("/", {replace: false});
    }).catch((error) => {
      if (error.response.status == 401) {
        SessionController.nullifyUser();
        setContextState(dispatch, "user", {});
        setContextState(dispatch, "report", "");
        setContextState(dispatch, "participant_uid", null);
        navigate("/", {replace: false});
      } else {
        console.log(error)
      }
    });
  };

  // Render the notifications menu
  const renderProfileMenu = () => (
    <Menu
      anchorEl={openMenu}
      anchorReference={null}
      disableScrollLock
      anchorOrigin={{
        vertical: "bottom",
        horizontal: "left",
      }}
      open={whichMenu === "ProfileMenu"}
      onClose={handleCloseMenu}
      sx={{ mt: 2 }}
    >
      <Link to="/profile">
        <MenuItem>
          <FaUser fontSize={MIN_TEXT_PX} style={{paddingRight: SPACE.xs}} />
          <MDTypography variant="button" fontWeight="regular" color="text">
            {"Profile"}
          </MDTypography>
        </MenuItem>
      </Link>
      <MenuItem onClick={() => logoutUser()}>
        <FaArrowRightFromBracket fontSize={MIN_TEXT_PX} style={{paddingRight: SPACE.xs}} />
        <MDTypography variant="button" fontWeight="regular" color="text">
          {dictionary.SimplifiedNavbar.Logout[language]}
        </MDTypography>
      </MenuItem>
    </Menu>
  );

  const setLanguage = (lang) => {
    if (lang === "English") {
      setContextState(dispatch, "language", "en");
    } else if (lang === "中文") {
      setContextState(dispatch, "language", "zh");
    }
    handleCloseMenu();
  };

  // Render the notifications menu
  const renderLanguageSelectionMenu = () => (
    <Menu
      anchorEl={openMenu}
      anchorReference={null}
      anchorOrigin={{
        vertical: "bottom",
        horizontal: "left",
      }}
      open={whichMenu === "LanguageMenu"}
      onClose={handleCloseMenu}
      sx={{ mt: 2 }}
    >
      {["English","中文"].map((lang) => (
        <MenuItem key={lang} onClick={() => setLanguage(lang)}>
          <Icon sx={{ mr: 1 }}><ChangeCircle/></Icon>
          <MDTypography variant="button" fontWeight="regular" color="text">
            {lang}
          </MDTypography>
        </MenuItem>
      ))}
    </Menu>
  );

  const getProcessingQueue = () => {
    SessionController.query("/api/queryProcessingQueue").then((response) => {
      setQueueState({...queueState, queues: response.data, show: true});
    }).catch((error) => {
      SessionController.displayError(error, setAlert);
    });
  };

  const clearQueue = (type) => {
    if (type == "All") {
      SessionController.query("/api/clearProcessingQueue").then((response) => {
        if (response.status == 200) {
          setQueueState({...queueState, queues:[], show: false});
        }
      }).catch((error) => {
        SessionController.displayError(error,setAlert);
      })
    } else if (type == "Complete") {
      SessionController.query("/api/clearProcessingQueue").then((response) => {
        if (response.status == 200) {
          setQueueState(currentState => {
            currentState.queues = currentState.queues.filter((item) => item.state != "Complete");
            return {...currentState};
          });
        }
      }).catch((error) => {
        SessionController.displayError(error,setAlert);
      })
    }
  };

  // Styles for the navbar icons
  // Icons in the caption grey (6.48:1 on the page background); the bar has one light look.
  const iconsStyle = () => ({
    color: T.ink3,
  });

  return (
    <AppBar
      position={absolute ? "absolute" : navbarType}
      color="inherit"
      sx={(theme) => navbar(theme, { transparentNavbar, absolute, light, darkMode })}
    >
      {alert}
      {/* First in the top bar, so it is the first thing a keyboard reaches (TASTE_AUDIT.md C7). */}
      <SkipToContent />
      <Toolbar sx={(theme) => navbarContainer(theme)}>
        <MDBox color="inherit" mb={{ xs: 1, md: 0 }} sx={(theme) => navbarRow(theme, { isMini })}>
          <Breadcrumbs icon="home" title={route[route.length - 1]} route={route} light={light} />
          <IconButton sx={{display: {xs: "none", xl: "block"}}} onClick={handleMiniSidenav} size="small" disableRipple
            aria-label={!miniSidenav ? "Shrink the side menu" : "Widen the side menu"}>
            <Icon fontSize="medium" sx={iconsStyle}>
              {!miniSidenav ? "menu_open" : "menu"}
            </Icon>
          </IconButton>
          <IconButton
            size="small"
            disableRipple
            color="inherit"
            sx={navbarMobileMenu}
            onClick={handleHideSidenav}
            aria-label={!hideSidenav ? "Hide the side menu" : "Show the side menu"}
          >
            <Icon sx={iconsStyle} fontSize="medium">
              {!hideSidenav ? "menu_open" : "menu"}
            </Icon>
          </IconButton>
        </MDBox>
        {isMini ? null : (
          <MDBox sx={(theme) => navbarRow(theme, { isMini })}>
            <MDBox pr={1}/>
            <MDBox color={light ? "white" : "inherit"}>
              <IconButton
                size="small"
                disableRipple
                color="inherit"
                sx={navbarIconButton}
                aria-controls="notification-menu"
                aria-haspopup="true"
                aria-label="Account menu: profile and log out"
                variant="contained"
                onClick={(event) => handleOpenMenu(event, "ProfileMenu")}
              >
                <MDBadge badgeContent={null} color="error" size="xs" circular>
                  <Avatar src={""} />
                </MDBadge>
              </IconButton>
              {renderProfileMenu()}
              {renderLanguageSelectionMenu()}
            </MDBox>
          </MDBox>
        )}
      </Toolbar>
      
    </AppBar>
  );
}

// Setting default values for the props of DashboardNavbar
DashboardNavbar.defaultProps = {
  absolute: false,
  light: false,
  isMini: false,
};

// Typechecking props for the DashboardNavbar
DashboardNavbar.propTypes = {
  absolute: PropTypes.bool,
  light: PropTypes.bool,
  isMini: PropTypes.bool,
};

export default DashboardNavbar;
