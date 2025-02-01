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

import DatabaseLayout from "layouts/DatabaseLayout";
import TherapyHistoryFigure from "./TherapyHistoryFigure";
import ImpedanceHeatmap from "./ImpedanceHeatmap";
import ImpedanceHistory from "./ImpedanceHistory";

import { SessionController } from "database/session-control";
import { usePlatformContext, setContextState } from "context.js";
import { dictionary, dictionaryLookup } from "assets/translation.js";

function TherapyHistoryTable({therapyHistory, viewConfigurationTable}) {
  const navigate = useNavigate();
  const [controller, dispatch] = usePlatformContext();
  const { language, report } = controller;

  const [therapyTable, setTherapyTable] = React.useState({});
  const [interleavingSwitch, setInterleavingSwitch] = React.useState({});

  React.useEffect(() => {
    setTherapyTable(() => {
      let therapyTable = {};
      for (let i in therapyHistory) {
        if (!Object.keys(therapyTable).includes(therapyHistory[i].Device.Id + "(" + therapyHistory[i].Type + ")")) {
          therapyTable[therapyHistory[i].Device.Id + "(" + therapyHistory[i].Type + ")"] = []
        }
        therapyTable[therapyHistory[i].Device.Id + "(" + therapyHistory[i].Type + ")"].push(therapyHistory[i]);
      }

      for (let i in therapyTable) {
        therapyTable[i] = therapyTable[i].sort((a,b) => {
          if (a.GroupId == b.GroupId) {
            return a.Date - b.Date
          } else {
            return a.GroupId.localeCompare(b.GroupId)
          }
        })
      }
      return therapyTable;
    });
  }, [therapyHistory])

  return useMemo(() => (
    <MDBox>
      {Object.keys(therapyTable).sort((a,b) => a.localeCompare(b)).map((key) => {
        return <Accordion key={key}>
          <AccordionSummary
            expandIcon={<ExpandMoreIcon />}
            id={key}
          >
            <MDTypography variant={"h5"} >
              {therapyTable[key][0].Device.Name} {"("}{therapyTable[key][0].Device.Heritage}{")"} {therapyTable[key][0].Type}
            </MDTypography>
          </AccordionSummary>
          <AccordionDetails>
            <Grid container spacing={2}>
              {therapyTable[key].map((config) => {
                return <Grid key={config.Id} item xs={12} sm={6}>
                  <Card>
                    <MDBox px={2} pt={1}>
                      <MDTypography variant={"h5"} >
                        {config.GroupName ? config.GroupName : config.GroupId}{config.Percent ? (" ("+(config.Percent*100).toFixed(1)+"%)") : ""}
                      </MDTypography>
                      <MDTypography variant={"subtitle1"} color={"secondary"} fontSize={15} fontWeight={"medium"} lineHeight={1} style={{cursor: "pointer"}} onClick={() => viewConfigurationTable(config)}>
                        {new Date(config.Date*1000).toLocaleString("en-US", {...SessionController.getTimezoneName(config.Timezone),
                          hour: "2-digit",
                          minute: "2-digit",
                        })}
                        {" (" + config.StimulationType + ")"}
                      </MDTypography>
                      <MDTypography variant={"subtitle1"} color={"error"} fontSize={18} fontWeight={"medium"} lineHeight={1.5}>
                        {config.StimulationSettings[0].Electrode.CustomName}
                      </MDTypography>
                    </MDBox>
                    {config.StimulationSettings.length > 1 ? (
                      <MDBox px={2} pt={1} pb={2} style={{cursor: "pointer"}} onClick={() => {
                        setInterleavingSwitch((switchDict) => {
                          switchDict[config.Id] = !switchDict[config.Id];
                          return {...switchDict};
                        })
                      }}>
                        <MDTypography variant={"subtitle1"} color={"secondary"} fontSize={18} fontWeight={"medium"} lineHeight={1.5}>
                          {"Program " + (interleavingSwitch[config.Id] ? "2" : "1")}
                        </MDTypography>
                        <MDBox display={"flex"} flexDirection={"column"} justifyContent={"start"} pt={1}>
                          <MDTypography variant={"h6"} fontSize={15} fontWeight={"regular"} lineHeight={1}>
                            {"Frequency: "}<b>{config.StimulationSettings[interleavingSwitch[config.Id] ? 1 : 0].Frequency}</b>{" Hz"}<br/>
                          </MDTypography>
                        </MDBox>
                        <MDBox display={"flex"} flexDirection={"column"} justifyContent={"start"} pt={1}>
                          <MDTypography variant={"h6"} fontSize={15} fontWeight={"regular"} lineHeight={1}>
                            {"Pulsewidth: "}<b>{config.StimulationSettings[interleavingSwitch[config.Id] ? 1 : 0].Pulsewidth}</b>{" "}{config.StimulationSettings[0].PulsewidthUnit}<br/>
                          </MDTypography>
                        </MDBox>
                        <MDBox display={"flex"} flexDirection={"row"} alignItems={"center"} justifyContent={"start"} pt={1}>
                          <MDTypography variant={"h6"} fontSize={15} fontWeight={"regular"} lineHeight={1}>
                            {"Stimulation: "}
                          </MDTypography>
                          {config.StimulationSettings[interleavingSwitch[config.Id] ? 1 : 0].Contact.map((a, index) => {
                            return <Tooltip key={a} title={config.StimulationSettings[interleavingSwitch[config.Id] ? 1 : 0].FractionalAmplitudes[index] + " " + config.StimulationSettings[0].AmplitudeUnit}>
                              <MDBadge badgeContent={a} color={"error"} size={"xs"} container sx={{marginLeft: 1, cursor: "pointer"}} />
                            </Tooltip>
                          })}
                        </MDBox>
                        {config.StimulationSettings[interleavingSwitch[config.Id] ? 1 : 0].ReturnContact.length > 0 ? (
                        <MDBox display={"flex"} flexDirection={"row"} alignItems={"center"} pt={1}>
                          <MDTypography variant={"h6"} fontSize={15} fontWeight={"regular"} lineHeight={1}>
                            {"Return: "}
                          </MDTypography>
                          {config.StimulationSettings[interleavingSwitch[config.Id] ? 1 : 0].ReturnContact.map((a) => {
                            return <MDBadge key={a} badgeContent={a} color={"info"} size={"xs"} container sx={{marginLeft: 1}} />
                          })}
                        </MDBox>
                        ) : null}
                        {config.StimulationSettings[interleavingSwitch[config.Id] ? 1 : 0].ReturnContact.length > 0 ? (
                        <MDBox display={"flex"} flexDirection={"row"} alignItems={"center"} pt={1}>
                          <MDTypography variant={"h6"} fontSize={15} fontWeight={"regular"} lineHeight={1}>
                            {"Return: "}
                          </MDTypography>
                          {config.StimulationSettings[interleavingSwitch[config.Id] ? 1 : 0].ReturnContact.map((a) => {
                            return <MDBadge key={a} badgeContent={a} color={"info"} size={"xs"} container sx={{marginLeft: 1}} />
                          })}
                        </MDBox>
                        ) : null}
                        <MDBox display={"flex"} flexDirection={"row"} alignItems={"center"} pt={1}>
                          <MDTypography variant={"h6"} fontSize={15} fontWeight={"regular"} lineHeight={1} pr={1}>
                            {"Cycling: "}{" "}
                          </MDTypography>
                          {config.StimulationSettings[interleavingSwitch[config.Id] ? 1 : 0].CyclingPeriod == 0 ? (
                            <MDTypography variant={"h6"} fontSize={15} fontWeight={"regular"} lineHeight={1}>
                              {" Continuous Stimulation"}
                            </MDTypography>
                          ) : (
                            <MDTypography variant={"h6"} fontSize={15} fontWeight={"regular"} lineHeight={1}>
                              {"Duty Cycle " + (config.StimulationSettings[interleavingSwitch[config.Id] ? 1 : 0].Cycling*100).toFixed(1) + "%"}<br/>
                              {"Duty Period " + (config.StimulationSettings[interleavingSwitch[config.Id] ? 1 : 0].CyclingPeriod/60000).toFixed(1) + " minutes"}
                            </MDTypography>
                          )}
                        </MDBox>
                      </MDBox>
                    ) : (
                      <MDBox px={2} pt={1} pb={2}>
                        <MDBox display={"flex"} flexDirection={"column"} justifyContent={"start"} pt={1}>
                          <MDTypography variant={"h6"} fontSize={15} fontWeight={"regular"} lineHeight={1}>
                            {"Frequency: "}<b>{config.StimulationSettings[0].Frequency}</b>{" Hz"}<br/>
                          </MDTypography>
                        </MDBox>
                        <MDBox display={"flex"} flexDirection={"column"} justifyContent={"start"} pt={1}>
                          <MDTypography variant={"h6"} fontSize={15} fontWeight={"regular"} lineHeight={1}>
                            {"Pulsewidth: "}<b>{config.StimulationSettings[0].Pulsewidth}</b>{" "}{config.StimulationSettings[0].PulsewidthUnit}<br/>
                          </MDTypography>
                        </MDBox>
                        <MDBox display={"flex"} flexDirection={"row"} alignItems={"center"} justifyContent={"start"} pt={1}>
                          <MDTypography variant={"h6"} fontSize={15} fontWeight={"regular"} lineHeight={1}>
                            {"Stimulation: "}
                          </MDTypography>
                          {config.StimulationSettings[0].Contact.map((a, index) => {
                            return <Tooltip key={a} title={config.StimulationSettings[0].FractionalAmplitudes[index] + " " + config.StimulationSettings[0].AmplitudeUnit}>
                              <MDBadge key={a} badgeContent={a} color={"error"} size={"xs"} container sx={{marginLeft: 1, cursor: "pointer"}} />
                            </Tooltip>
                          })}
                        </MDBox>
                        {config.StimulationSettings[0].ReturnContact.length > 0 ? (
                        <MDBox display={"flex"} flexDirection={"row"} alignItems={"center"} pt={1}>
                          <MDTypography variant={"h6"} fontSize={15} fontWeight={"regular"} lineHeight={1}>
                            {"Return: "}
                          </MDTypography>
                          {config.StimulationSettings[0].ReturnContact.map((a) => {
                            return <MDBadge key={a} badgeContent={a} color={"info"} size={"xs"} container sx={{marginLeft: 1}} />
                          })}
                        </MDBox>
                        ) : null}
                        <MDBox display={"flex"} flexDirection={"row"} alignItems={"center"} pt={1}>
                          <MDTypography variant={"h6"} fontSize={15} fontWeight={"regular"} lineHeight={1} pr={1}>
                            {"Cycling: "}{" "}
                          </MDTypography>
                          {config.StimulationSettings[0].CyclingPeriod == 0 ? (
                            <MDTypography variant={"h6"} fontSize={15} fontWeight={"regular"} lineHeight={1}>
                              {" Continuous Stimulation"}
                            </MDTypography>
                          ) : (
                            <MDTypography variant={"h6"} fontSize={15} fontWeight={"regular"} lineHeight={1}>
                              {"Duty Cycle " + (config.StimulationSettings[0].Cycling*100).toFixed(1) + "%"}<br/>
                              {"Duty Period " + (config.StimulationSettings[0].CyclingPeriod/60000).toFixed(1) + " minutes"}
                            </MDTypography>
                          )}
                        </MDBox>
                      </MDBox>
                    )}
                  </Card>
                </Grid>
              })}
            </Grid>
          </AccordionDetails>
        </Accordion>
      })}
    </MDBox>
  ), [therapyTable, interleavingSwitch]);
}

export default TherapyHistoryTable;
