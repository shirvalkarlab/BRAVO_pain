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
  Slider,
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

function TherapyModificationHistory({therapyHistory, device, viewConfigurationTable}) {
  const navigate = useNavigate();
  const [controller, dispatch] = usePlatformContext();
  const { language, report } = controller;

  const [therapyTable, setTherapyTable] = React.useState({});
  const [interleavingSwitch, setInterleavingSwitch] = React.useState({});
  const [therapyDateSlider, setTherapyDateSlider] = React.useState({active: 0, options: []});

  React.useEffect(() => {
    let therapyDates = {active: 0, options: []};
    for (let i in therapyHistory.TherapyTimeline) {
      if (therapyHistory.TherapyTimeline[i].DefinedTherapies.some((a) => a.Device.GenericName == device) == false) continue;
      therapyDates.options.push(therapyHistory.TherapyTimeline[i].Date);
    }
    therapyDates.active = therapyDates.options[therapyDates.options.length-1];
    setTherapyDateSlider(therapyDates);
  }, [therapyHistory, device]);

  React.useEffect(() => {
    for (let i in therapyHistory.TherapyTimeline) {
      if (therapyHistory.TherapyTimeline[i].Date == therapyDateSlider.active) {
        setTherapyTable(() => {
          const definedTherapies = therapyHistory.TherapyTimeline[i].DefinedTherapies.filter((a) => a.Device.GenericName == device);
          return { ...therapyHistory.TherapyTimeline[i], DefinedTherapies: definedTherapies };
        });
        break;
      }
    }
  }, [therapyDateSlider]);

  React.useEffect(() => {
    
  }, [therapyTable]);

  const getPreTherapySettings = (config) => {
    let configKey = "Pre";
    let interleaving = false;
    let sensing = false;
    if (!config.StimulationSettings[0].Pre.TherapyType && !config.StimulationSettings[0].Pre.length) {
      if (!config.StimulationSettings[0].Summary.TherapyType && !config.StimulationSettings[0].Summary.length) return null;
      configKey = "Summary";
    }

    if (config.StimulationSettings[0][configKey].length > 1) {
      interleaving = true;
    }

    if (!interleaving && config.AdaptiveSettings[0][configKey].RecordingConfiguration.Type !== "Unknown") {
      sensing = true;
      console.log(config.AdaptiveSettings[0][configKey].StimulationConfiguration)
      console.log(config.AdaptiveSettings[0][configKey].RecordingConfiguration)
    }

    return (
      <MDBox px={2} pt={1} pb={2}>
        <MDTypography variant={"h6"} fontWeight={"bold"}>
          {"Therapy Settings Before Visit:"}
        </MDTypography>
        <MDBox display={"flex"} flexDirection={"column"} justifyContent={"start"} pt={1}>
          {interleaving ? (
          <MDTypography variant={"h6"} fontSize={15} fontWeight={"regular"} lineHeight={1}>
            {"Frequency: "}<b>{config.StimulationSettings[0][configKey][0].Frequency}</b>{" Hz"}{" | "}<b>{config.StimulationSettings[0][configKey][1].Frequency}</b>{" Hz"}<br/>
          </MDTypography>
          ) : (
          <MDTypography variant={"h6"} fontSize={15} fontWeight={"regular"} lineHeight={1}>
            {"Frequency: "}<b>{config.StimulationSettings[0][configKey].Frequency}</b>{" Hz"}<br/>
          </MDTypography>
          )}
        </MDBox>
        <MDBox display={"flex"} flexDirection={"column"} justifyContent={"start"} pt={1}>
          {interleaving ? (
          <MDTypography variant={"h6"} fontSize={15} fontWeight={"regular"} lineHeight={1}>
            {"Pulsewidth: "}<b>{config.StimulationSettings[0][configKey][0].Pulsewidth}</b>{" "}{config.StimulationSettings[0][configKey][0].PulsewidthUnit}{" | "}<b>{config.StimulationSettings[0][configKey][1].Pulsewidth}</b>{" "}{config.StimulationSettings[0][configKey][1].PulsewidthUnit}<br/>
          </MDTypography>
          ) : (
          <MDTypography variant={"h6"} fontSize={15} fontWeight={"regular"} lineHeight={1}>
            {"Pulsewidth: "}<b>{config.StimulationSettings[0][configKey].Pulsewidth}</b>{" "}{config.StimulationSettings[0][configKey].PulsewidthUnit}<br/>
          </MDTypography>
          )}
        </MDBox>
        
        {interleaving ? (
        <MDBox display={"flex"} flexDirection={"row"} alignItems={"center"} justifyContent={"start"} pt={1}>
          <MDTypography variant={"h6"} fontSize={15} fontWeight={"regular"} lineHeight={1}>
            {"Stimulation: "}
          </MDTypography>
          {config.StimulationSettings[0][configKey][0].Contact.map((a, index) => {
            return <Tooltip key={a} title={config.StimulationSettings[0][configKey][0].FractionalAmplitudes[index] / (configKey === "Summary" ? config.StimulationSettings[0][configKey][0].Contact.length : 1) + " " + config.StimulationSettings[0][configKey][0].AmplitudeUnit}>
              <MDBadge badgeContent={a} color={"error"} size={"xs"} container sx={{marginLeft: 1, cursor: "pointer"}} />
            </Tooltip>
          })}
          <MDTypography variant={"h6"} fontSize={15} fontWeight={"regular"} lineHeight={1} ml={1}>
            {" | "}
          </MDTypography>
          {config.StimulationSettings[0][configKey][1].Contact.map((a, index) => {
            return <Tooltip key={a} title={config.StimulationSettings[0][configKey][1].FractionalAmplitudes[index] / (configKey === "Summary" ? config.StimulationSettings[0][configKey][1].Contact.length : 1) + " " + config.StimulationSettings[0][configKey][1].AmplitudeUnit}>
              <MDBadge badgeContent={a} color={"error"} size={"xs"} container sx={{marginLeft: 1, cursor: "pointer"}} />
            </Tooltip>
          })}
        </MDBox>
        ) : (
        <MDBox display={"flex"} flexDirection={"row"} alignItems={"center"} justifyContent={"start"} pt={1}>
          <MDTypography variant={"h6"} fontSize={15} fontWeight={"regular"} lineHeight={1}>
            {"Stimulation: "}
          </MDTypography>
          {config.StimulationSettings[0][configKey].Contact.map((a, index) => {
            return <Tooltip key={a} title={config.StimulationSettings[0][configKey].FractionalAmplitudes[index] / (configKey === "Summary" ? config.StimulationSettings[0][configKey].Contact.length : 1) + " " + config.StimulationSettings[0][configKey].AmplitudeUnit}>
              <MDBadge badgeContent={a} color={"error"} size={"xs"} container sx={{marginLeft: 1, cursor: "pointer"}} />
            </Tooltip>
          })}
        </MDBox>
        )}
        
        {interleaving ? (
        <MDBox display={"flex"} flexDirection={"row"} alignItems={"center"} justifyContent={"start"} pt={1}>
          <MDTypography variant={"h6"} fontSize={15} fontWeight={"regular"} lineHeight={1}>
            {"Stimulation Return: "}
          </MDTypography>
          {config.StimulationSettings[0][configKey][0].ReturnContact.map((a, index) => {
            return <MDBadge key={a} badgeContent={a} color={"info"} size={"xs"} container sx={{marginLeft: 1}} />
          })}
          <MDTypography variant={"h6"} fontSize={15} fontWeight={"regular"} lineHeight={1} ml={1}>
            {" | "}
          </MDTypography>
          {config.StimulationSettings[0][configKey][1].ReturnContact.map((a, index) => {
            return <MDBadge key={a} badgeContent={a} color={"info"} size={"xs"} container sx={{marginLeft: 1}} />
          })}
        </MDBox>
        ) : (
        <MDBox display={"flex"} flexDirection={"row"} alignItems={"center"} pt={1}>
          <MDTypography variant={"h6"} fontSize={15} fontWeight={"regular"} lineHeight={1}>
            {"Stimulation Return: "}
          </MDTypography>
          {config.StimulationSettings[0][configKey].ReturnContact.map((a) => {
            return <MDBadge key={a} badgeContent={a} color={"info"} size={"xs"} container sx={{marginLeft: 1}} />
          })}
        </MDBox>
        )}

        {interleaving ? ( 
        <MDBox display={"flex"} flexDirection={"row"} alignItems={"center"} pt={1}>
          <MDTypography variant={"h6"} fontSize={15} fontWeight={"regular"} lineHeight={1} pr={1}>
            {"Cycling: "}{" "}
          </MDTypography>
          {config.StimulationSettings[0][configKey][0].CyclingPeriod == 0 ? (
            <MDTypography variant={"h6"} fontSize={15} fontWeight={"regular"} lineHeight={1}>
              {" Continuous Stimulation"}
            </MDTypography>
          ) : (
            <MDTypography variant={"h6"} fontSize={15} fontWeight={"regular"} lineHeight={1}>
              {"Duty Cycle " + (config.StimulationSettings[0][configKey][0].Cycling*100).toFixed(1) + "%"}<br/>
              {"Duty Period " + (config.StimulationSettings[0][configKey][0].CyclingPeriod/60000).toFixed(1) + " minutes"}
            </MDTypography>
          )}
          <MDTypography variant={"h6"} fontSize={15} fontWeight={"regular"} lineHeight={1} px={1}>
            {" | "}
          </MDTypography>
          {config.StimulationSettings[0][configKey][1].CyclingPeriod == 0 ? (
            <MDTypography variant={"h6"} fontSize={15} fontWeight={"regular"} lineHeight={1}>
              {" Continuous Stimulation"}
            </MDTypography>
          ) : (
            <MDTypography variant={"h6"} fontSize={15} fontWeight={"regular"} lineHeight={1}>
              {"Duty Cycle " + (config.StimulationSettings[0][configKey][1].Cycling*100).toFixed(1) + "%"}<br/>
              {"Duty Period " + (config.StimulationSettings[0][configKey][1].CyclingPeriod/60000).toFixed(1) + " minutes"}
            </MDTypography>
          )}
        </MDBox>
        ) : (
        <MDBox display={"flex"} flexDirection={"row"} alignItems={"center"} pt={1}>
          <MDTypography variant={"h6"} fontSize={15} fontWeight={"regular"} lineHeight={1} pr={1}>
            {"Cycling: "}{" "}
          </MDTypography>
          {config.StimulationSettings[0][configKey].CyclingPeriod == 0 ? (
            <MDTypography variant={"h6"} fontSize={15} fontWeight={"regular"} lineHeight={1}>
              {" Continuous Stimulation"}
            </MDTypography>
          ) : (
            <MDTypography variant={"h6"} fontSize={15} fontWeight={"regular"} lineHeight={1}>
              {"Duty Cycle " + (config.StimulationSettings[0][configKey].Cycling*100).toFixed(1) + "%"}<br/>
              {"Duty Period " + (config.StimulationSettings[0][configKey].CyclingPeriod/60000).toFixed(1) + " minutes"}
            </MDTypography>
          )}
        </MDBox>
        )}

        {interleaving || !sensing ? null : (
          <MDBox pt={2}>
            <MDBox display={"flex"} flexDirection={"column"} justifyContent={"start"} pt={1}>
              <MDTypography variant={"h6"} fontSize={15} fontWeight={"regular"} lineHeight={1}>
                {"Sensing Frequency: "}<b>{config.AdaptiveSettings[0][configKey].RecordingConfiguration.Config.SensingSetup.FrequencyInHertz}</b>{" Hz"}<br/>
              </MDTypography>
            </MDBox>
            {config.AdaptiveSettings[0][configKey].StimulationConfiguration.Type === "Medtronic Adaptive" ? (
              <MDBox display={"flex"} flexDirection={"column"} justifyContent={"start"} pt={1}>
                <MDTypography variant={"h6"} fontSize={15} fontWeight={"regular"} lineHeight={1}>
                  {"Adaptive Mode: "}<b>{config.AdaptiveSettings[0][configKey].StimulationConfiguration.Config.Status}</b><br/>
                </MDTypography>
                <MDTypography variant={"h6"} fontSize={15} fontWeight={"regular"} lineHeight={1}>
                  {"Lower Onset Duration: "}<b>{config.AdaptiveSettings[0][configKey].StimulationConfiguration.Config.LowerThresholdOnsetInMilliSeconds}</b>{" ms"}<br/>
                </MDTypography>
                <MDTypography variant={"h6"} fontSize={15} fontWeight={"regular"} lineHeight={1}>
                  {"Upper Onset Duration: "}<b>{config.AdaptiveSettings[0][configKey].StimulationConfiguration.Config.UpperThresholdOnsetInMilliSeconds}</b>{" ms"}<br/>
                </MDTypography>
                {config.AdaptiveSettings[0][configKey].StimulationConfiguration.Config.Bypass ? (
                  <MDTypography variant={"h6"} fontSize={15} fontWeight={"regular"} lineHeight={1}>
                    {"Signal Bypass: "}<b>{config.AdaptiveSettings[0][configKey].StimulationConfiguration.Config.Bypass}</b><br/>
                  </MDTypography>
                ) : null}
              </MDBox>
            ) : null}
          </MDBox>
        )}
      </MDBox>
    )
  };

  const getPostTherapySettings = (config) => {
    let configKey = "Post";
    let interleaving = false;
    if (!config.StimulationSettings[0].Post.TherapyType && !config.StimulationSettings[0].Post.length) {
      return null;
    }

    if (config.StimulationSettings[0][configKey].length > 1) {
      interleaving = true;
    }

    return (
      <MDBox px={2} pt={1} pb={2}>
        <MDTypography variant={"h6"} fontWeight={"bold"}>
          {"Therapy Settings After Visit: "}
        </MDTypography>
        <MDBox display={"flex"} flexDirection={"column"} justifyContent={"start"} pt={1}>
          {interleaving ? (
          <MDTypography variant={"h6"} fontSize={15} fontWeight={"regular"} lineHeight={1}>
            {"Frequency: "}<b>{config.StimulationSettings[0][configKey][0].Frequency}</b>{" Hz"}{" | "}<b>{config.StimulationSettings[0][configKey][1].Frequency}</b>{" Hz"}<br/>
          </MDTypography>
          ) : (
          <MDTypography variant={"h6"} fontSize={15} fontWeight={"regular"} lineHeight={1}>
            {"Frequency: "}<b>{config.StimulationSettings[0][configKey].Frequency}</b>{" Hz"}<br/>
          </MDTypography>
          )}
        </MDBox>
        <MDBox display={"flex"} flexDirection={"column"} justifyContent={"start"} pt={1}>
          {interleaving ? (
          <MDTypography variant={"h6"} fontSize={15} fontWeight={"regular"} lineHeight={1}>
            {"Pulsewidth: "}<b>{config.StimulationSettings[0][configKey][0].Pulsewidth}</b>{" "}{config.StimulationSettings[0][configKey][0].PulsewidthUnit}{" | "}<b>{config.StimulationSettings[0][configKey][1].Pulsewidth}</b>{" "}{config.StimulationSettings[0][configKey][1].PulsewidthUnit}<br/>
          </MDTypography>
          ) : (
          <MDTypography variant={"h6"} fontSize={15} fontWeight={"regular"} lineHeight={1}>
            {"Pulsewidth: "}<b>{config.StimulationSettings[0][configKey].Pulsewidth}</b>{" "}{config.StimulationSettings[0][configKey].PulsewidthUnit}<br/>
          </MDTypography>
          )}
        </MDBox>
        
        {interleaving ? (
        <MDBox display={"flex"} flexDirection={"row"} alignItems={"center"} justifyContent={"start"} pt={1}>
          <MDTypography variant={"h6"} fontSize={15} fontWeight={"regular"} lineHeight={1}>
            {"Stimulation: "}
          </MDTypography>
          {config.StimulationSettings[0][configKey][0].Contact.map((a, index) => {
            return <Tooltip key={a} title={config.StimulationSettings[0][configKey][0].FractionalAmplitudes[index] / (configKey === "Summary" ? config.StimulationSettings[0][configKey][0].Contact.length : 1) + " " + config.StimulationSettings[0][configKey][0].AmplitudeUnit}>
              <MDBadge badgeContent={a} color={"error"} size={"xs"} container sx={{marginLeft: 1, cursor: "pointer"}} />
            </Tooltip>
          })}
          <MDTypography variant={"h6"} fontSize={15} fontWeight={"regular"} lineHeight={1} ml={1}>
            {" | "}
          </MDTypography>
          {config.StimulationSettings[0][configKey][1].Contact.map((a, index) => {
            return <Tooltip key={a} title={config.StimulationSettings[0][configKey][1].FractionalAmplitudes[index] / (configKey === "Summary" ? config.StimulationSettings[0][configKey][1].Contact.length : 1) + " " + config.StimulationSettings[0][configKey][1].AmplitudeUnit}>
              <MDBadge badgeContent={a} color={"error"} size={"xs"} container sx={{marginLeft: 1, cursor: "pointer"}} />
            </Tooltip>
          })}
        </MDBox>
        ) : (
        <MDBox display={"flex"} flexDirection={"row"} alignItems={"center"} justifyContent={"start"} pt={1}>
          <MDTypography variant={"h6"} fontSize={15} fontWeight={"regular"} lineHeight={1}>
            {"Stimulation: "}
          </MDTypography>
          {config.StimulationSettings[0][configKey].Contact.map((a, index) => {
            return <Tooltip key={a} title={config.StimulationSettings[0][configKey].FractionalAmplitudes[index] / (configKey === "Summary" ? config.StimulationSettings[0][configKey].Contact.length : 1) + " " + config.StimulationSettings[0][configKey].AmplitudeUnit}>
              <MDBadge badgeContent={a} color={"error"} size={"xs"} container sx={{marginLeft: 1, cursor: "pointer"}} />
            </Tooltip>
          })}
        </MDBox>
        )}
        
        {interleaving ? (
        <MDBox display={"flex"} flexDirection={"row"} alignItems={"center"} justifyContent={"start"} pt={1}>
          <MDTypography variant={"h6"} fontSize={15} fontWeight={"regular"} lineHeight={1}>
            {"Stimulation Return: "}
          </MDTypography>
          {config.StimulationSettings[0][configKey][0].ReturnContact.map((a, index) => {
            return <MDBadge key={a} badgeContent={a} color={"info"} size={"xs"} container sx={{marginLeft: 1}} />
          })}
          <MDTypography variant={"h6"} fontSize={15} fontWeight={"regular"} lineHeight={1} ml={1}>
            {" | "}
          </MDTypography>
          {config.StimulationSettings[0][configKey][1].ReturnContact.map((a, index) => {
            return <MDBadge key={a} badgeContent={a} color={"info"} size={"xs"} container sx={{marginLeft: 1}} />
          })}
        </MDBox>
        ) : (
        <MDBox display={"flex"} flexDirection={"row"} alignItems={"center"} pt={1}>
          <MDTypography variant={"h6"} fontSize={15} fontWeight={"regular"} lineHeight={1}>
            {"Stimulation Return: "}
          </MDTypography>
          {config.StimulationSettings[0][configKey].ReturnContact.map((a) => {
            return <MDBadge key={a} badgeContent={a} color={"info"} size={"xs"} container sx={{marginLeft: 1}} />
          })}
        </MDBox>
        )}

        {interleaving ? ( 
        <MDBox display={"flex"} flexDirection={"row"} alignItems={"center"} pt={1}>
          <MDTypography variant={"h6"} fontSize={15} fontWeight={"regular"} lineHeight={1} pr={1}>
            {"Cycling: "}{" "}
          </MDTypography>
          {config.StimulationSettings[0][configKey][0].CyclingPeriod == 0 ? (
            <MDTypography variant={"h6"} fontSize={15} fontWeight={"regular"} lineHeight={1}>
              {" Continuous Stimulation"}
            </MDTypography>
          ) : (
            <MDTypography variant={"h6"} fontSize={15} fontWeight={"regular"} lineHeight={1}>
              {"Duty Cycle " + (config.StimulationSettings[0][configKey][0].Cycling*100).toFixed(1) + "%"}<br/>
              {"Duty Period " + (config.StimulationSettings[0][configKey][0].CyclingPeriod/60000).toFixed(1) + " minutes"}
            </MDTypography>
          )}
          <MDTypography variant={"h6"} fontSize={15} fontWeight={"regular"} lineHeight={1} px={1}>
            {" | "}
          </MDTypography>
          {config.StimulationSettings[0][configKey][1].CyclingPeriod == 0 ? (
            <MDTypography variant={"h6"} fontSize={15} fontWeight={"regular"} lineHeight={1}>
              {" Continuous Stimulation"}
            </MDTypography>
          ) : (
            <MDTypography variant={"h6"} fontSize={15} fontWeight={"regular"} lineHeight={1}>
              {"Duty Cycle " + (config.StimulationSettings[0][configKey][1].Cycling*100).toFixed(1) + "%"}<br/>
              {"Duty Period " + (config.StimulationSettings[0][configKey][1].CyclingPeriod/60000).toFixed(1) + " minutes"}
            </MDTypography>
          )}
        </MDBox>
        ) : (
        <MDBox display={"flex"} flexDirection={"row"} alignItems={"center"} pt={1}>
          <MDTypography variant={"h6"} fontSize={15} fontWeight={"regular"} lineHeight={1} pr={1}>
            {"Cycling: "}{" "}
          </MDTypography>
          {config.StimulationSettings[0][configKey].CyclingPeriod == 0 ? (
            <MDTypography variant={"h6"} fontSize={15} fontWeight={"regular"} lineHeight={1}>
              {" Continuous Stimulation"}
            </MDTypography>
          ) : (
            <MDTypography variant={"h6"} fontSize={15} fontWeight={"regular"} lineHeight={1}>
              {"Duty Cycle " + (config.StimulationSettings[0][configKey].Cycling*100).toFixed(1) + "%"}<br/>
              {"Duty Period " + (config.StimulationSettings[0][configKey].CyclingPeriod/60000).toFixed(1) + " minutes"}
            </MDTypography>
          )}
        </MDBox>
        )}
      </MDBox>
    )
  }

  return useMemo(() => (
    <MDBox>
      <MDBox p={2} mt={2} pb={0}>
        <Slider aria-label="TherapyDates"
          value={therapyDateSlider.active} getAriaValueText={(value) => {
            return new Date(value*1000).toLocaleDateString("en-US", {
              month: "2-digit",
              day: "2-digit",
              year: "2-digit"
            });
          }}
          marks={therapyDateSlider.options.map((date,i) => {
            if (i > 0) {
              const minScale = therapyDateSlider.options[therapyDateSlider.options.length-1] - therapyDateSlider.options[0];
              if (date - therapyDateSlider.options[i-1] < minScale*.01) {
                return {value: date, label: ""};
              }
            }
            return {value: date, label: new Date(date*1000).toLocaleDateString("en-US", {
              month: "2-digit",
              day: "2-digit",
              year: "2-digit"
            })}
          })}
          valueLabelDisplay="on"
          valueLabelFormat={value =>
            new Date(value * 1000).toLocaleDateString("en-US", {
              month: "2-digit",
              day: "2-digit",
              year: "2-digit"
            })
          }
          step={null}
          min={therapyDateSlider.options.length > 0 ? therapyDateSlider.options[0] : 0}
          max={therapyDateSlider.options.length > 0 ? therapyDateSlider.options[therapyDateSlider.options.length-1] : 0}
          onChange={(event, newValue) => {
            setTherapyDateSlider((state) => ({...state, active: newValue}));
          }}
          sx={{
            '& .MuiSlider-markLabel': {
              transform: 'rotate(-45deg) translate(-50px, -40px)',
              whiteSpace: 'nowrap',
              fontSize: '0.85em',
              minWidth: '40px',
              textAlign: 'left',
              display: "none"
            },
            '& .MuiSlider-mark': {
              width: '4px',
              height: '4px',
              borderRadius: '50%',
              backgroundColor: '#f53131ff', // optional: change color
              marginLeft: '-6px', // center the dot
            }
          }}
        />
      </MDBox>

      {therapyTable.Date ? (
        <MDBox p={2} pt={0}>
          <MDTypography variant={"h4"} fontWeight={"bold"}>
            {"Therapy Configurations on " + new Date(therapyTable.Date*1000).toLocaleDateString("en-US", {
              month: "2-digit",
              day: "2-digit",
              year: "2-digit"
            })}
          </MDTypography>
          
          <Grid container spacing={2}>
            {therapyTable.DefinedTherapies.map((config) => (
              <Grid item xs={12} key={config.Id}>
                <Card p={2}>
                  <MDBox px={2} pt={1}>
                    <MDTypography variant={"h5"} >
                      {config.GroupName ? config.GroupName : config.GroupId}{config.Percent ? (" ("+(config.Percent*100).toFixed(1)+"%)") : ""}
                    </MDTypography>
                    <MDTypography variant={"subtitle1"} color={"secondary"} fontSize={15} fontWeight={"medium"} lineHeight={1} style={{cursor: "pointer"}} onClick={() => viewConfigurationTable(config)}>
                      {new Date(config.Date*1000).toLocaleString("en-US", {...SessionController.getTimezoneName(config.Timezone),
                        hour: "2-digit",
                        minute: "2-digit",
                      })}
                    </MDTypography>
                  </MDBox>
                  <Grid container spacing={2}>
                    <Grid item xs={12} md={6}>
                      {getPreTherapySettings(config)}
                    </Grid>
                    <Grid item xs={12} md={6}>
                      {getPostTherapySettings(config)}
                    </Grid>
                  </Grid>
                </Card>
              </Grid>
            ))}
          </Grid>
        </MDBox>
      ) : null}

      {Object.keys({}).sort((a,b) => a.localeCompare(b)).map((key) => {
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
  ), [therapyTable, device, therapyDateSlider, interleavingSwitch]);
}

export default TherapyModificationHistory;
