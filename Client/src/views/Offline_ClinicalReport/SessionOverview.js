/**
=========================================================
* UF BRAVO Platform
=========================================================

* Copyright 2025 by Jackson Cagle, Fixel Institute
* The source code is made available under a Creative Common NonCommercial ShareAlike License (CC BY-NC-SA 4.0) (https://creativecommons.org/licenses/by-nc-sa/4.0/) 

 =========================================================

* The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.
*/

import React, { useMemo } from "react";
import { useNavigate } from "react-router-dom";

import {
  Box,
  Backdrop,
  Badge,
  IconButton,
  Dialog,
  DialogContent,
  DialogActions,
  Accordion,
  AccordionSummary,
  AccordionDetails,
  Card,
  Grid,
  Table,
  TableRow,
  TableHead,
  TableBody,
  TableCell,
  ToggleButtonGroup,
  ToggleButton,
  Tooltip,
} from "@mui/material"

import TabletAndroidIcon from '@mui/icons-material/TabletAndroid';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';

// core components
import MDTypography from "components/MDTypography";
import MDBox from "components/MDBox";
import MDBadge from "components/MDBadge";
import MDButton from "components/MDButton";
import LoadingProgress from "components/LoadingProgress";

import { SessionController } from "database/session-control";
import { usePlatformContext, setContextState } from "context.js";

function SessionOverview({JSONData, onUpdateSession}) {
  const navigate = useNavigate();
  const [controller, dispatch] = usePlatformContext();
  const { language, report } = controller;

  const [statistics, setStatistics] = React.useState(null);

  const getSessionDate = (JSONData) => {
    let SessionStartDate = 0;
    if (JSONData.SessionDate !== "") {
      SessionStartDate = new Date(JSONData.SessionDate).getTime() / 1000;
    }

    let SessionEndDate = 0;
    if (JSONData.SessionEndDate !== "") {
      SessionEndDate = new Date(JSONData.SessionEndDate).getTime() / 1000;
    }

    if (SessionStartDate && SessionEndDate) {
      if (SessionEndDate - SessionStartDate < 8 * 60 * 60 && SessionEndDate > SessionStartDate) {
        return SessionStartDate;
      }
    }

    let sessionDatePools = [];
    if (JSONData.EventSummary) {
      sessionDatePools.push(new Date(JSONData.EventSummary.SessionEndDate).getTime() / 1000);
    }
    if (JSONData.CalibrationTests) {
      JSONData.CalibrationTests.forEach(test => {
        sessionDatePools.push(new Date(test.FirstPacketDateTime).getTime() / 1000);
      });
    }
    if (JSONData.SenseChannelTests) {
      JSONData.SenseChannelTests.forEach(test => {
        sessionDatePools.push(new Date(test.FirstPacketDateTime).getTime() / 1000);
      });
    }
    if (JSONData.BrainSenseTimeDomain) {
      JSONData.BrainSenseTimeDomain.forEach(test => {
        sessionDatePools.push(new Date(test.FirstPacketDateTime).getTime() / 1000);
      });
    }
    if (JSONData.BrainSenseLfp) {
      JSONData.BrainSenseLfp.forEach(test => {
        sessionDatePools.push(new Date(test.FirstPacketDateTime).getTime() / 1000);
      });
    }

    sessionDatePools = sessionDatePools.filter(date => date > 1420088400);
    if (sessionDatePools.length === 0) {
      if (SessionStartDate) {
        return SessionStartDate;
      }
      if (SessionEndDate) {
        return SessionEndDate;
      }
    }

    const FirstRecording = Math.min(...sessionDatePools);
    if (SessionStartDate) {
      if (FirstRecording - SessionStartDate < 8 * 60 * 60 && FirstRecording > SessionStartDate) {
        return SessionStartDate;
      }
    }

    return FirstRecording;
  }

  const formatMonths = (batteryLevel, sessionDate, {abbrev=false} = {}) => {
    let months = null;
    if (batteryLevel.EstimatedBatteryLifeInMonths) {
      months = batteryLevel.EstimatedBatteryLifeInMonths;
    } else if (batteryLevel.ERIDate) {
      months = (new Date(batteryLevel.ERIDate).getTime() / 1000 - sessionDate) / (60 * 60 * 24 * 30.44);
    }
    
    if (months === null || months === undefined || Number.isNaN(Number(months))) return "N/A";
    months = Math.round(Number(months));
    if (months === 0) return "0 months";
    const years = Math.floor(months / 12);
    const rem = months % 12;
    if (abbrev) {
      return (years ? `${years}y` : "") + (years && rem ? " " : "") + (rem ? `${rem}m` : "");
    }
    const parts = [];
    if (years) parts.push(`${years} ${years === 1 ? "year" : "years"}`);
    if (rem) parts.push(`${rem} ${rem === 1 ? "month" : "months"}`);
    return parts.join(" ");

  };

  const exportToClipboard = (data) => {
    navigator.clipboard.writeText(JSON.stringify(data, null, 2));
  };

  React.useEffect(() => {
    if (JSONData) {
      let statistics = {};
      statistics.SessionDate = getSessionDate(JSONData);
      statistics.BatteryLevel = JSONData.BatteryInformation;
      onUpdateSession(statistics);
      setStatistics(statistics);
    }
  }, [JSONData]);

  return useMemo(() => {
    if (!statistics) {
      return <LoadingProgress />;
    }

    return (
      <Card>
        <MDBox px={2} pt={2} display="flex" alignItems="center" justifyContent="space-between">
          <MDTypography variant="h5" fontWeight="bold">
            {"Session Recorded Date: " + (statistics.SessionDate ? new Date(statistics.SessionDate * 1000).toLocaleString() : "N/A")}
          </MDTypography>
          <MDButton variant="gradient" color="info" onClick={() => {
            exportToClipboard(statistics);
          }}>
            {"Copy"}
          </MDButton>
        </MDBox>
        <MDBox px={2} pb={2}>
          <MDTypography variant="body" fontSize={18} fontWeight="bold">
            {"Battery Level: "}
          </MDTypography>
          <MDTypography variant="body" fontSize={18}>
            {(statistics.BatteryLevel.BatteryPercentage ? statistics.BatteryLevel.BatteryPercentage + "%" : "N/A")}
          </MDTypography>
          <br/>
          <MDTypography variant="body" fontSize={18} fontWeight="bold">
            {"Estimated Battery Life: "}
          </MDTypography>
          <MDTypography variant="body" fontSize={18}>
            {formatMonths(statistics.BatteryLevel, statistics.SessionDate)}
          </MDTypography>
          <br/>
          <MDTypography variant="body" fontSize={18} fontWeight="bold">
            {"Battery Status: "}
          </MDTypography>
          <MDTypography variant="body" fontSize={18}>
            {(statistics.BatteryLevel.BatteryStatus ? statistics.BatteryLevel.BatteryStatus.replace("DeviceStateDef.","") : "N/A")}
          </MDTypography>
        </MDBox>
        {statistics.BatteryLevel.AverageRechargeTimeInMinutes && 
          <MDBox px={2} pb={2}>
            <MDTypography variant="body" fontSize={18} fontWeight="bold">
              {"Average Recharge Time: "}
            </MDTypography>
            <MDTypography variant="body" fontSize={18}>
              {Math.round(statistics.BatteryLevel.AverageRechargeTimeInMinutes) + " minutes"}
            </MDTypography>
            <br/>
            <MDTypography variant="body" fontSize={18} fontWeight="bold">
              {"Average Time between Recharges: "}
            </MDTypography>
            <MDTypography variant="body" fontSize={18}>
              {(statistics.BatteryLevel.AverageRechargeIntervalInMinutes / 60 / 24).toFixed(1) + " days"}
            </MDTypography>
            <br/>
            <MDTypography variant="body" fontSize={18} fontWeight="bold">
              {"Average Ending Battery Percentage: "}
            </MDTypography>
            <MDTypography variant="body" fontSize={18}>
              {Math.round(statistics.BatteryLevel.AverageEndingBatteryPercentage) + "%"}
            </MDTypography>
          </MDBox>
        }
      </Card>
    )
  }, [statistics]);
}

export default SessionOverview;