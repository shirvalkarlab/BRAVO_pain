/**
=========================================================
* UF BRAVO Platform
=========================================================

* Copyright 2025 by Jackson Cagle, Fixel Institute
* The source code is made available under a Creative Common NonCommercial ShareAlike License (CC BY-NC-SA 4.0) (https://creativecommons.org/licenses/by-nc-sa/4.0/) 

 =========================================================

* The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.
*/

import React from "react";
import { useNavigate, useParams } from "react-router-dom";

import {
  Box,
  Backdrop,
  IconButton,
  Dialog,
  DialogContent,
  DialogActions,
  Accordion,
  AccordionSummary,
  AccordionDetails,
  Card,
  Grid,
  Tabs,
  Tab,
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
import LoadingProgress from "components/LoadingProgress";

import DatabaseLayout from "layouts/DatabaseLayout";
import TherapyHistoryFigure from "./TherapyHistoryFigure";
import ImpedanceHeatmap from "./ImpedanceHeatmap";
import ImpedanceHistory from "./ImpedanceHistory";

import { SessionController } from "database/session-control";
import { usePlatformContext, setContextState } from "context.js";
import { dictionary, dictionaryLookup } from "assets/translation.js";
import MDButton from "components/MDButton";
import MDBadge from "components/MDBadge";
import TherapyHistoryTable from "./TherapyHistoryTable";

function TherapyHistory() {
  const navigate = useNavigate();
  const [controller, dispatch] = usePlatformContext();
  const { language, report } = controller;

  const [data, setData] = React.useState({});
  const [therapyHistory, setTherapyHistory] = React.useState({TherapyModification: [], TherapyDevices: []});
  const [therapyHistoryOld, setTherapyHistoryOld] = React.useState({});
  const [therapyDate, setTherapyDate] = React.useState({active: false, options: []});
  const [therapyConfigurations, setTherapyConfigurations] = React.useState([]);

  const [impedanceLogs, setImpedanceLogs] = React.useState({});
  const [impedanceMode, setImpedanceMode] = React.useState("Bipolar");
  const [dataToRender, setDataToRender] = React.useState(null);
  const [therapyConfig, setTherapyConfig] = React.useState({show: false, config: null});
  const [currentTherapy, setCurrentTherapy] = React.useState({show: false, configs: []});
  const [interleavingSwitch, setInterleavingSwitch] = React.useState({});

  const [alert, setAlert] = React.useState(null);
  const [therapyTypes, setTherapyTypes] = React.useState([]);
  const [activeTab, setActiveTab] = React.useState(null);
  const [activeDevice, setActiveDevice] = React.useState(null);

  const { participant_uid } = useParams();

  React.useEffect(() => {
    if (!participant_uid) {
      navigate("/dashboard", {replace: false});
      return
    }
    setContextState(dispatch, "report", "GeneralReports");

    setAlert(<LoadingProgress/>);
    SessionController.query("/api/queryTherapyHistory", {
      ParticipantId: participant_uid
    }).then((response) => {
      setTherapyHistory(response.data);
      setAlert(null);
    }).catch((error) => {
      SessionController.displayError(error, setAlert);
    });
  }, [participant_uid]);

  React.useEffect(() => {
    let UniqueDateStrings = [];
    let TherapyConfigurations = {}
    for (let i in therapyHistory.TherapyConfiguration) {
      for (let j in therapyHistory.TherapyConfiguration[i].History) {
        const dateString = new Date(therapyHistory.TherapyConfiguration[i].History[j].Date*1000).toLocaleString("en-US", {...SessionController.getTimezoneName(therapyHistory.TherapyConfiguration[i].History[j].Timezone),
          year: "numeric",
          month: "2-digit",
          day: "2-digit",
          hour: "2-digit",
          minute: "2-digit",
          timeZoneName: "longGeneric"
        })
        if (!UniqueDateStrings.map((a)=>a.label).includes(dateString)) {
          UniqueDateStrings.push({
            label: dateString,
            value: therapyHistory.TherapyConfiguration[i].History[j].Date
          });
          TherapyConfigurations[dateString] = [];
        }

        TherapyConfigurations[dateString].push({
          ...therapyHistory.TherapyConfiguration[i].History[j],
          Device: therapyHistory.TherapyConfiguration[i].Device
        })
      }
    }
    UniqueDateStrings = UniqueDateStrings.sort((a,b) => b.value - a.value).map((a) => a.label)

    if (UniqueDateStrings.length > 0) {
      setTherapyConfigurations(TherapyConfigurations)
      setTherapyDate({
        active: UniqueDateStrings[0],
        options: UniqueDateStrings
      })
    } else {
      setTherapyConfigurations({})
      setTherapyDate({
        active: null,
        options: []
      })
    }

  }, [therapyHistory, language]);

  const showPerceptAdaptiveSettings = (therapy, captureAmplitude, amplitudeThreshold) => {
    setAlert(
      <Dialog open={true} onClose={() => setAlert(null)}>
        <MDBox px={2} pt={2}>
          <MDTypography variant="h5">
            {"Adaptive Configurations"} 
          </MDTypography>
        </MDBox>
        <DialogContent>
          <MDBox px={2} pt={2}>
            <MDTypography variant="h6" fontSize={15}>
              {"Adaptive Mode Configuration:"} 
            </MDTypography>
            <MDTypography variant="p" fontSize={12}>
              {therapy.Mode.endsWith("SINGLE_THRESHOLD_DIRECT") ? "Single Threshold" : ""} 
            </MDTypography>
            <MDTypography variant="p" fontSize={12}>
              {therapy.Mode.endsWith("DUAL_THRESHOLD_DIRECT") ? "Dual Threshold" : ""} 
            </MDTypography>
          </MDBox>
          <MDBox px={2}>
            <MDTypography variant="h6" fontSize={15}>
              {"Capture Amplitude:"} 
            </MDTypography>
            <MDTypography variant="p" fontSize={12}>
              {therapy.Mode.endsWith("SINGLE_THRESHOLD_DIRECT") ? captureAmplitude[1] : captureAmplitude[0]}
            </MDTypography>
            <MDTypography variant="p" fontSize={12}>
              {therapy.Mode.endsWith("DUAL_THRESHOLD_DIRECT") ? captureAmplitude[1] : ""} 
            </MDTypography>
          </MDBox>
          <MDBox px={2}>
            <MDTypography variant="h6" fontSize={15}>
              {"LFP Threshold:"} 
            </MDTypography>
            <MDTypography variant="p" fontSize={12}>
              {therapy.Mode.endsWith("SINGLE_THRESHOLD_DIRECT") ? amplitudeThreshold[1] : amplitudeThreshold[0]}
            </MDTypography>
            <MDTypography variant="p" fontSize={12}>
              {therapy.Mode.endsWith("DUAL_THRESHOLD_DIRECT") ? amplitudeThreshold[1] : ""} 
            </MDTypography>
          </MDBox>
          <MDBox px={2}>
            <MDTypography variant="h6" fontSize={15}>
              {"Detection Blanking:"} 
            </MDTypography>
            <MDTypography variant="p" fontSize={12}>
              {therapy.DetectionBlankingDurationInMilliSeconds} {"ms"}
            </MDTypography>
          </MDBox>
          <MDBox px={2}>
            <MDTypography variant="h6" fontSize={15}>
              {"Ramping Time (Up/Down):"} 
            </MDTypography>
            <MDTypography variant="p" fontSize={12}>
              {therapy.RampUpTime} {"ms"} {"/"} {therapy.RampDownTime} {"ms"} 
            </MDTypography>
          </MDBox>
          <MDBox px={2}>
            <MDTypography variant="h6" fontSize={15}>
              {"Threshold Onset Duration (Up/Down):"} 
            </MDTypography>
            <MDTypography variant="p" fontSize={12}>
              {therapy.Mode.endsWith("SINGLE_THRESHOLD_DIRECT") ? `${therapy.LowerThresholdOnsetInMilliSeconds} ms` : `${therapy.LowerThresholdOnsetInMilliSeconds} ms / ${therapy.UpperThresholdOnsetInMilliSeconds} ms`}
            </MDTypography>
          </MDBox>
        </DialogContent>
        <DialogActions>
          <MDButton color="secondary" onClick={() => setAlert(null)}>{"Close"}</MDButton>
        </DialogActions>
      </Dialog>
    )
  }

  const showSummitAdaptiveSettings = (therapy) => {
    let powerChannel = {Ld0: [], Ld1: []};
    if (therapy.Adaptive.Detector.Ld0.detectionEnable > 0) {
      for (let i = 0; i < 8; i++) {
        if (therapy.Adaptive.Detector.Ld0.detectionInputs & (Math.pow(2, i))) {
          const LfpChan = parseInt(therapy.Adaptive.Power.Enabled[i][2]);
          const FreqResolution = therapy.Adaptive.Power.LfpConfig[LfpChan].SamplingRate / therapy.Adaptive.Power.NFFT;
          powerChannel.Ld0.push(therapy.Adaptive.Power.Enabled[i] + ` ${(therapy.Adaptive.Power.PowerBands[i][0]*FreqResolution).toFixed(2)}-${(therapy.Adaptive.Power.PowerBands[i][1]*FreqResolution).toFixed(2)}Hz`)
        }
      }
    }
    if (therapy.Adaptive.Detector.Ld1.detectionEnable > 0) {
      for (let i = 0; i < 8; i++) {
        if (therapy.Adaptive.Detector.Ld1.detectionInputs & (Math.pow(2, i))) {
          const LfpChan = parseInt(therapy.Adaptive.Power.Enabled[i][2]);
          const FreqResolution = therapy.Adaptive.Power.LfpConfig[LfpChan].SamplingRate / therapy.Adaptive.Power.NFFT;
          powerChannel.Ld1.push(therapy.Adaptive.Power.Enabled[i] + ` ${(therapy.Adaptive.Power.PowerBands[i][0]*FreqResolution).toFixed(2)}-${(therapy.Adaptive.Power.PowerBands[i][1]*FreqResolution).toFixed(2)}Hz`)
        }
      }
    }

    setAlert(
      <Dialog open={true} onClose={() => setAlert(null)}>
        <MDBox px={2} pt={2}>
          <MDTypography variant="h5">
            {"Summit Adaptive Configurations"} 
          </MDTypography>
        </MDBox>
        <DialogContent>
          <MDBox px={2} pt={2}>
            <MDTypography variant="h6" fontSize={15}>
              {"State Configurations:"} 
            </MDTypography>
            <Grid container>
              {therapy.Adaptive.Adaptive.State.map((state, index) => {
                return <Grid item xs={4} key={index}>
                  {state.prog0Amp < 255 ? state.prog0Amp/10 + " mA" : "Disabled"}
                </Grid>
              })}
            </Grid>
          </MDBox>
          {powerChannel.Ld0.length > 0 ? (
            <MDBox px={2} pt={1} display={"flex"} flexDirection={"column"}>
              <MDTypography variant="h6" fontSize={15}>
                {"Ld0 Channel Input:"} 
              </MDTypography>
              {powerChannel.Ld0.map((channel) => (
                <MDTypography key={channel} variant="p" fontSize={14}>
                  {channel} 
                </MDTypography>
              ))}
              <MDTypography variant="p" fontSize={14}>
                {"Thresholds: "} 
                {therapy.Adaptive.Detector.Ld0.biasTerm[0]} 
                {therapy.Adaptive.Detector.Ld0.biasTerm[0] == therapy.Adaptive.Detector.Ld0.biasTerm[1] ? "" : " / " + therapy.Adaptive.Detector.Ld0.biasTerm[1]} 
              </MDTypography>
              <MDTypography variant="p" fontSize={14}>
                {"Onset Duration: "} 
                {therapy.Adaptive.Detector.Ld0.onsetDuration * therapy.Adaptive.Detector.Ld0.updateRate * therapy.Adaptive.Power.Interval / 1000} {" sec"}
              </MDTypography>
              <MDTypography variant="p" fontSize={14}>
                {"Termination Duration: "} 
                {therapy.Adaptive.Detector.Ld0.terminationDuration * therapy.Adaptive.Detector.Ld0.updateRate * therapy.Adaptive.Power.Interval / 1000} {" sec"}
              </MDTypography>
            </MDBox>
          ) : null}
          {powerChannel.Ld1.length > 0 ? (
            <MDBox px={2} pt={1} display={"flex"} flexDirection={"column"}>
              <MDTypography variant="h6" fontSize={15}>
                {"Ld1 Channel Input:"} 
              </MDTypography>
              {powerChannel.Ld1.map((channel) => (
                <MDTypography key={channel} variant="p" fontSize={14}>
                  {channel} 
                </MDTypography>
              ))}
              <MDTypography variant="p" fontSize={14}>
                {"Thresholds:"} 
                {therapy.Adaptive.Detector.Ld1.biasTerm[0]} 
                {therapy.Adaptive.Detector.Ld1.biasTerm[0] == therapy.Adaptive.Detector.Ld1.biasTerm[1] ? "" : " / " + therapy.Adaptive.Detector.Ld1.biasTerm[1]} 
              </MDTypography>
              <MDTypography variant="p" fontSize={14}>
                {"Onset Duration: "} 
                {therapy.Adaptive.Detector.Ld1.onsetDuration * therapy.Adaptive.Detector.Ld1.updateRate * therapy.Adaptive.Power.Interval / 1000} {" sec"}
              </MDTypography>
              <MDTypography variant="p" fontSize={14}>
                {"Termination Duration: "} 
                {therapy.Adaptive.Detector.Ld1.terminationDuration * therapy.Adaptive.Detector.Ld1.updateRate * therapy.Adaptive.Power.Interval / 1000} {" sec"}
              </MDTypography>
            </MDBox>
          ) : null}
          <MDBox px={2}>
            
          </MDBox>
          <MDBox px={2}>
            
          </MDBox>
          <MDBox px={2}>
            
          </MDBox>
        </DialogContent>
        <DialogActions>
          <MDButton color="secondary" onClick={() => setAlert(null)}>{"Close"}</MDButton>
        </DialogActions>
      </Dialog>
    )
  }

  const formatTherapySettings = (therapy, type, color) => {
    if (type == "Contacts") {
      if (therapy.Mode == "Interleaving") {
        return (
          therapy.Channel.map((program, index) => {
            return <MDTypography key={"program" + index.toString()} color={color} fontSize={12} style={{flexDirection: "row", paddingBottom: 0, paddingTop: 0, marginBottom: 0}}>
              {program.map((contact) => {
                if (!contact.Electrode.startsWith("ElectrodeDef")) {
                  return contact.Electrode + " ";
                }
              })}
            </MDTypography>
          })
        );
      } else {
        return (
          <MDBox style={{display: "flex", flexDirection: "row"}}>
            {therapy.Channel.map((contact) => {
              if (!contact.Electrode.startsWith("ElectrodeDef")) {
                if (contact.ElectrodeAmplitudeInMilliAmps) {
                  return <Tooltip key={contact.Electrode} title={contact.ElectrodeAmplitudeInMilliAmps + " mA"} placement="top">
                    <MDTypography fontSize={12} color={color} style={{paddingBottom: 0, paddingRight: 5, paddingTop: 0, marginBottom: 0}}>
                      {contact.Electrode + " "}
                    </MDTypography>
                  </Tooltip>
                } else {
                  return <MDTypography key={contact.Electrode} fontSize={12} color={color} style={{paddingBottom: 0, paddingRight: 5, paddingTop: 0, marginBottom: 0}}>
                    {contact.Electrode + " "}
                  </MDTypography>
                }
              }
            })}
          </MDBox>
        );
      }
    } else if (type == "Settings") {
      if (therapy.Mode == "Interleaving") {
        return (
          therapy.Channel.map((program, index) => {
            return (<MDTypography key={"program" + index.toString()} color={color} fontSize={12} style={{paddingBottom: 0, paddingTop: 0, marginBottom: 0}}>
                {therapy.Frequency[index]} {" Hz"} {therapy.PulseWidth[index]} {" μSec"} {therapy.Amplitude[index].toFixed(1)} {" "} {therapy.Unit[index]}
              </MDTypography>
            );
          })
        );
      } else {
        return (<MDTypography color={color} fontSize={12} style={{paddingBottom: 0, paddingTop: 0, marginBottom: 0}}>
            {therapy.Frequency} {" Hz"} {therapy.PulseWidth} {" μSec"} {therapy.Amplitude.toFixed(1)} {" "} {therapy.Unit}
          </MDTypography>
        );
      }
    } else if (type == "BrainSense") {
      if (therapy.Mode == "BrainSense") {
        if ((therapy.LFPThresholds[0] == 20 && therapy.LFPThresholds[1] == 30 && therapy.CaptureAmplitudes[0] == 0 && therapy.CaptureAmplitudes[1] == 0) || !therapy.AdaptiveSetup) {
          return (
          <MDBox display={"flex"} flexDirection={"row"} alignItems={"center"}>
            <MDTypography color={color} fontSize={12} style={{paddingBottom: 0, paddingTop: 0, marginBottom: 0}}>
              {therapy.SensingSetup.FrequencyInHertz} {" Hz"} 
            </MDTypography>
            <MDBox display={"flex"} flexDirection={"column"} ml={2}>
              <MDTypography color={color} fontSize={12} style={{paddingBottom: 0, paddingTop: 0, marginBottom: 0}}>
                {"Sense Only"}
              </MDTypography>
            </MDBox>
          </MDBox>
          );
        } else {
          return (
          <MDBox display={"flex"} flexDirection={"row"} alignItems={"center"}>
            <MDTypography color={color} fontSize={12} style={{paddingBottom: 0, paddingTop: 0, marginBottom: 0}}>
              {therapy.SensingSetup.FrequencyInHertz} {" Hz"} 
            </MDTypography>
            <MDBox display={"flex"} flexDirection={"column"} ml={2} style={{cursor: "pointer"}} onClick={() => {
              showPerceptAdaptiveSettings(therapy.AdaptiveSetup, therapy.CaptureAmplitudes, therapy.LFPThresholds);
            }}>
              {therapy.AdaptiveSetup.Bypass ? (
                <MDTypography color={color} fontSize={12} style={{paddingBottom: 0, paddingTop: 0, marginBottom: 0}}>
                  {"Adaptive Sense Only"}
                </MDTypography>
              ) : (
                <MDTypography color={color} fontSize={12} style={{paddingBottom: 0, paddingTop: 0, marginBottom: 0}}>
                  {therapy.AdaptiveSetup.Status === "ADBSStatusDef.RUNNING" ? "Adaptive Enabled" : ""}
                  {therapy.AdaptiveSetup.Status === "ADBSStatusDef.SUSPENDED" ? "Adaptive Suspended" : ""}
                  {therapy.AdaptiveSetup.Status === "ADBSStatusDef.DISABLED" ? "Adaptive Stim Only" : ""}
                </MDTypography>
              )}
            </MDBox>
          </MDBox>
          );
        }
      } else if (therapy.Mode == "SummitAdaptive") {
        if (therapy.Adaptive.Adaptive.Status != "EmbeddedActive") {
          return (<MDTypography color={color} fontSize={12} style={{paddingBottom: 0, paddingTop: 0, marginBottom: 0}}>
              {"Adaptive Disabled"}
            </MDTypography>
          );
        } else {
          return (
            <MDBox display={"flex"} flexDirection={"column"} alignItems={"start"} style={{cursor: "pointer"}} onClick={() => {
              showSummitAdaptiveSettings(therapy);
            }}>
              <MDTypography color={color} fontSize={12} style={{paddingBottom: 0, paddingTop: 0, marginBottom: 0}}>
                {therapy.Adaptive.Detector.Ld0.detectionEnable == 2 ? "LD0 Enabled" : ""}
              </MDTypography>
              <MDTypography color={color} fontSize={12} style={{paddingBottom: 0, paddingTop: 0, marginBottom: 0}}>
                {therapy.Adaptive.Detector.Ld1.detectionEnable == 2 ? "LD1 Enabled" : ""}
              </MDTypography>
            </MDBox>
            );
        }
      } else {
        return (<MDTypography color={color} fontSize={12} style={{paddingBottom: 0, paddingTop: 0, marginBottom: 0}}>
            {"BrainSense Disabled"}
          </MDTypography>
        );
      }
    }
  };

  const formatCyclingStim = (cycling) => {
    const percent = cycling.OnDurationInMilliSeconds / (cycling.OnDurationInMilliSeconds + cycling.OffDurationInMilliSeconds) * 100;
    return `${percent.toFixed(1)}% (${(cycling.OnDurationInMilliSeconds/1000).toFixed(1) + " " + dictionary.Time.Seconds[language]} : ${(cycling.OffDurationInMilliSeconds/1000).toFixed(1) + " " + dictionary.Time.Seconds[language]})`;
  };

  const translateMedtronicAdaptiveString = (string) => {
    if (string === "AdaptiveModeDef.SINGLE_THRESHOLD_DIRECT") {
      return "Single Threshold"
    } else if (string === "AdaptiveModeDef.DUAL_THRESHOLD_DIRECT" ) {
      return "Dual Threshold"
    } else {
      return string
    }
  }

  const formatConfigurationTable = (config) => {
    if (config.StimulationType === "BrainSense") {
      return (
        <Grid container spacing={2}>
          <Grid item xs={12}>
            <Grid container spacing={0}>
              <Grid item xs={12}>
                <MDTypography variant={"p"} fontSize={18} fontFamily={"lato"}>
                  {"Sensing Frequency: "}<b>{therapyConfig.config.AdaptiveSettings[0].RecordingConfiguration.Config.SensingSetup.FrequencyInHertz} {" Hz"}</b>
                </MDTypography>
              </Grid>
              <Grid item xs={12}>
                <MDTypography variant={"p"} fontSize={18} fontFamily={"lato"}>
                  {"Averaging Duration: "}<b>{therapyConfig.config.AdaptiveSettings[0].RecordingConfiguration.Config.SensingSetup.AveragingDurationInMilliSeconds} {" milliseconds"}</b>
                </MDTypography>
              </Grid>
              {therapyConfig.config.AdaptiveSettings[0].RecordingConfiguration.Config.Thresholds.AmplitudeThreshold[0] != therapyConfig.config.AdaptiveSettings[0].RecordingConfiguration.Config.Thresholds.AmplitudeThreshold[1] ? (
                <Grid item xs={12}>
                  <MDTypography variant={"p"} fontSize={18} fontFamily={"lato"}>
                    {"Amplitude Threshold: "}<b>{therapyConfig.config.AdaptiveSettings[0].RecordingConfiguration.Config.Thresholds.AmplitudeThreshold[0]}
                    {" - "}{therapyConfig.config.AdaptiveSettings[0].RecordingConfiguration.Config.Thresholds.AmplitudeThreshold[1]}
                    {" mA"}</b>
                  </MDTypography>
                </Grid>
              ) : null}
            </Grid>
          </Grid>
          {therapyConfig.config.AdaptiveSettings[0].StimulationConfiguration.Type === "Medtronic Adaptive" ? (
            <Grid item xs={12} pt={5}>
              <Grid container spacing={0}>
                <Grid item xs={12}>
                  <MDTypography variant={"p"} fontSize={18} fontFamily={"lato"}>
                    {"Threshold Mode: "}<b>{translateMedtronicAdaptiveString(therapyConfig.config.AdaptiveSettings[0].StimulationConfiguration.Config.Mode)}</b>
                  </MDTypography>
                </Grid>
                <Grid item xs={12}>
                  <MDTypography variant={"p"} fontSize={18} fontFamily={"lato"}>
                    {"Capture Threshold: "}<b>{therapyConfig.config.AdaptiveSettings[0].RecordingConfiguration.Config.Thresholds.CaptureAmplitudes[0]}
                    {" - "}{therapyConfig.config.AdaptiveSettings[0].RecordingConfiguration.Config.Thresholds.CaptureAmplitudes[1]}
                    {" mA"}</b>
                  </MDTypography>
                </Grid>
                <Grid item xs={12}>
                  <MDTypography variant={"p"} fontSize={18} fontFamily={"lato"}>
                    {"LFP at Capture Threshold: "}<b>{therapyConfig.config.AdaptiveSettings[0].RecordingConfiguration.Config.Thresholds.MeasuredLFP[0]}
                    {" - "}{therapyConfig.config.AdaptiveSettings[0].RecordingConfiguration.Config.Thresholds.MeasuredLFP[1]}
                    {" A.U."}</b>
                  </MDTypography>
                </Grid>
                <Grid item xs={12}>
                  <MDTypography variant={"p"} fontSize={18} fontFamily={"lato"}>
                    {"Final Threshold: "}<b>{therapyConfig.config.AdaptiveSettings[0].RecordingConfiguration.Config.Thresholds.LFPThresholds[0]}
                    {" - "}{therapyConfig.config.AdaptiveSettings[0].RecordingConfiguration.Config.Thresholds.LFPThresholds[1]}
                    {" A.U."}</b>
                  </MDTypography>
                </Grid>
                <Grid item xs={12}>
                  <MDTypography variant={"p"} fontSize={18} fontFamily={"lato"}>
                    {"Detection Blanking: "}<b>{therapyConfig.config.AdaptiveSettings[0].StimulationConfiguration.Config.DetectionBlankingDurationInMilliSeconds} {" milliseconds"}</b>
                  </MDTypography>
                </Grid>
                <Grid item xs={12}>
                  <MDTypography variant={"p"} fontSize={18} fontFamily={"lato"}>
                    {"Lower Onset Duration: "}<b>{therapyConfig.config.AdaptiveSettings[0].StimulationConfiguration.Config.LowerThresholdOnsetInMilliSeconds} {" milliseconds"}</b>
                  </MDTypography>
                </Grid>
                <Grid item xs={12}>
                  <MDTypography variant={"p"} fontSize={18} fontFamily={"lato"}>
                    {"Upper Onset Duration: "}<b>{therapyConfig.config.AdaptiveSettings[0].StimulationConfiguration.Config.UpperThresholdOnsetInMilliSeconds} {" milliseconds"}</b>
                  </MDTypography>
                </Grid>
                <Grid item xs={12}>
                  <MDTypography variant={"p"} fontSize={18} fontFamily={"lato"}>
                    {"Ramp-up Time: "}<b>{therapyConfig.config.AdaptiveSettings[0].StimulationConfiguration.Config.RampUpTime} {" milliseconds"}</b>
                  </MDTypography>
                </Grid>
                <Grid item xs={12}>
                  <MDTypography variant={"p"} fontSize={18} fontFamily={"lato"}>
                    {"Ramp-down Time: "}<b>{therapyConfig.config.AdaptiveSettings[0].StimulationConfiguration.Config.RampDownTime} {" milliseconds"}</b>
                  </MDTypography>
                </Grid>
              </Grid>
            </Grid>
          ) : null}
        </Grid>
      )
    }

    return <></>
  }

  const onContactSelect = (point) => {
    let dataToRender = {};
    if (point.data.xaxis === "x") {
      // This is Left Side
      dataToRender.data = impedanceLogs.map((data) => {
        try {
          if (therapyHistoryOld[activeDevice].Device != data.device) return null;
          return {timestamps: data.session_date, value: impedanceMode === "Monopolar" ? data.log.Left[impedanceMode][point.y] : data.log.Left[impedanceMode][point.y][point.x]};
        } catch (error) {
          return null;
        }
      }).filter((value) => value);
      for (let i in therapyHistoryOld[activeDevice].Lead) {
        if (therapyHistoryOld[activeDevice].Lead[i].TargetLocation.startsWith("Left")) {
          dataToRender.title = `${therapyHistoryOld[activeDevice].Device} ${therapyHistoryOld[activeDevice].Lead[i].CustomName} `;
        }
      }
    } else {
      // This is Right Side
      dataToRender.data = impedanceLogs.map((data) => {
        try {
          if (therapyHistoryOld[activeDevice].Device != data.device) return null;
          return {timestamps: data.session_date, value: impedanceMode === "Monopolar" ? data.log.Right[impedanceMode][point.y] : data.log.Right[impedanceMode][point.y][point.x]};
        } catch (error) {
          return null;
        }
      }).filter((value) => value);
      for (let i in therapyHistoryOld[activeDevice].Lead) {
        if (therapyHistoryOld[activeDevice].Lead[i].TargetLocation.startsWith("Right")) {
          dataToRender.title = `${therapyHistoryOld[activeDevice].Device} ${therapyHistoryOld[activeDevice].Lead[i].CustomName} `;
        }
      }
    }

    if (impedanceMode === "Monopolar") {
      dataToRender.title += `Contact ${point.yaxis.ticktext.filter((value, index) => point.yaxis.tickvals[index] == point.y)[0]} `
    } else {
      dataToRender.title += `Contact ${point.yaxis.ticktext.filter((value, index) => point.yaxis.tickvals[index] == point.y)[0]}-${point.xaxis.ticktext.filter((value, index) => point.xaxis.tickvals[index] == point.x)[0]} `
    }

    dataToRender.point = point;
    setDataToRender(dataToRender);
  } 

  return (
    <DatabaseLayout>
      {alert}
      <MDBox py={2}>
        <Grid container spacing={2}>
          {therapyHistory.TherapyModification.length > 0 ? (
          <Grid item xs={12}>
            <Card>
              <MDBox p={2}>
                <TherapyHistoryFigure dataToRender={therapyHistory} 
                  onTimeClick={(time, group) => {
                    let configs = [];
                    for (let dateString in therapyConfigurations) {
                      for (let j in therapyConfigurations[dateString]) {
                        if (therapyConfigurations[dateString][j].Date > time && therapyConfigurations[dateString][j].GroupId == group) {
                          configs.push(therapyConfigurations[dateString][j])
                        }
                      }
                      if (configs.length > 0) break;
                    }
                    setCurrentTherapy({configs: configs, show: true});
                  }}
                  height={400} figureTitle={"TherapyHistoryLog"}/>
              </MDBox>
            </Card>
          </Grid>
          ) : null}

          <Grid item xs={6} sm={4}>
            <Tabs
              orientation="vertical"
              variant="scrollable"
              value={therapyDate.active}
              onChange={(event, newValue) => setTherapyDate({...therapyDate, active: newValue})}
              sx={{ borderRight: 1, borderColor: 'divider', maxHeight: "80vh" }}
            >
              {therapyDate.options.map((date) => {
                return <Tab key={date} value={date} label={date}/>
              })}
            </Tabs>
          </Grid>
          
          {therapyDate.active ? (
            <Grid item xs={6} sm={8}>
              <TherapyHistoryTable therapyHistory={therapyConfigurations[therapyDate.active]} viewConfigurationTable={(config) => {
                if (config.StimulationType == "BrainSense") {
                  setTherapyConfig({show: true, config: config});
                }
              }} />
            </Grid>
          ) : null}

        </Grid>
      </MDBox>

      <Dialog PaperProps={{sx: {minWidth: 600}}} open={currentTherapy.show} onClose={() => setCurrentTherapy({...currentTherapy, show: false})}>
        {currentTherapy.config ? (
          <MDBox px={2} pt={2}>
            <MDTypography variant={"h5"} >
              {currentTherapy.config.GroupName ? currentTherapy.config.GroupName : currentTherapy.config.GroupId}
            </MDTypography>
            <MDTypography variant={"subtitle1"} color={"error"} fontSize={18} fontWeight={"medium"} lineHeight={1.5}>
              {currentTherapy.config.StimulationSettings[0].Electrode.CustomName}
            </MDTypography>
          </MDBox>
        ) : null}
        <DialogContent>
        <Grid container spacing={2}>
          {currentTherapy.configs.map((config) => {
            return <Grid key={config.Id} item xs={12} sm={6}>
              <Card>
                <MDBox px={2} pt={1}>
                  <MDTypography variant={"h5"} >
                    {config.GroupName ? config.GroupName : config.GroupId}
                  </MDTypography>
                  <MDTypography variant={"subtitle1"} color={"secondary"} fontSize={15} fontWeight={"medium"} lineHeight={1} style={{cursor: "pointer"}} onClick={() => {
                    if (config.StimulationType == "BrainSense") {
                      setTherapyConfig({show: true, config: config});
                    }
                  }}>
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
        </DialogContent>
      </Dialog>

      <Dialog PaperProps={{sx: {minWidth: 600}}} open={therapyConfig.show} onClose={() => setTherapyConfig({...therapyConfig, show: false})}>
        {therapyConfig.config ? (
          <MDBox px={2} pt={2}>
            <MDTypography variant={"h5"} >
              {therapyConfig.config.GroupName ? therapyConfig.config.GroupName : therapyConfig.config.GroupId}
            </MDTypography>
            <MDTypography variant={"subtitle1"} color={"error"} fontSize={18} fontWeight={"medium"} lineHeight={1.5}>
              {therapyConfig.config.StimulationSettings[0].Electrode.CustomName}
            </MDTypography>
          </MDBox>
        ) : null}
        <DialogContent>
        {therapyConfig.config ? <>
          {formatConfigurationTable(therapyConfig.config)}
        </> : null}
        </DialogContent>
      </Dialog>
    </DatabaseLayout>
  );
}

export default TherapyHistory;
