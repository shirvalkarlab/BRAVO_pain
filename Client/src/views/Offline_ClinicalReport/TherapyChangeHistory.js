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

import TherapyHistoryFigure from "views/Reports/TherapyHistory/TherapyHistoryFigure";

import { SessionController } from "database/session-control";
import { usePlatformContext, setContextState } from "context.js";

function TherapyChangeHistory({JSONData, sessionDate, onUpdateTimeline}) {
  const navigate = useNavigate();
  const [controller, dispatch] = usePlatformContext();
  const { language, report } = controller;

  const [therapyHistory, setTherapyHistory] = React.useState({
    TherapyDevices: [],
    TherapyModification: []
  });

  const getTherapyDevice = (JSONData) => {
    let device = {
      Id: JSONData.DeviceInformation.Final.NeurostimulatorSerialNumber || "Unknown Device",
      Date: JSONData.DeviceInformation.Final.ImplantDate ? new Date(JSONData.DeviceInformation.Final.ImplantDate).getTime() / 1000 : 0,
    }
    return device;
  }

  const getTherapyModifications = (JSONData, device) => {
    if (!JSONData.DiagnosticData) return [];
    if (!JSONData.DiagnosticData.EventLogs) return [];

    const therapyLogs = JSONData.DiagnosticData.EventLogs.filter((a) => {
      return a.ParameterTrendId === "ParameterTrendIdDef.ActiveGroup";
    }).map((log) => {
      return {
        Id: "",
        Name: "",
        Type: "TherapyChangeGroup",
        Date: new Date(log.DateTime).getTime() / 1000,
        Previous: log.OldGroupId,
        New: log.NewGroupId,
      };
    });

    therapyLogs.push({
      Id: "",
      Name: "",
      Type: "TherapyChangeGroup",
      Date: new Date(sessionDate).getTime() / 1000,
      Previous: therapyLogs[therapyLogs.length - 1].New,
      New: therapyLogs[therapyLogs.length - 1].New,
    });

    onUpdateTimeline(therapyLogs);

    return [{
      Device: device,
      History: therapyLogs
    }];
  }

  React.useEffect(() => {
    if (JSONData && sessionDate) {
      const device = getTherapyDevice(JSONData);
      const modifications = getTherapyModifications(JSONData, device);
      onUpdateTimeline(modifications);
      setTherapyHistory({
        TherapyDevices: [device],
        TherapyModification: modifications
      });
    }
  }, [JSONData, sessionDate]);

  return useMemo(() => {
    if (therapyHistory.TherapyModification.length < 1) {
      return <LoadingProgress />;
    }

    return (
      <Card>
        <MDBox p={2}>
          <TherapyHistoryFigure dataToRender={therapyHistory} rangeSlider={true}
            onTimeClick={(time, group) => {}} height={400} figureTitle={"TherapyHistoryLog"}/>
        </MDBox>
      </Card>
    )
  }, [therapyHistory]);
}

export default TherapyChangeHistory;