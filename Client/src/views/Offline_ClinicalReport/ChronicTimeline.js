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
  Card, 
  Grid,
} from "@mui/material"

// core components
import MDTypography from "components/MDTypography";
import MDBox from "components/MDBox";
import MDBadge from "components/MDBadge";
import MDButton from "components/MDButton";
import LoadingProgress from "components/LoadingProgress";

import moment from "moment";
import MedtronicChronicTimeline from "views/Reports/ChronicNeuralActivity/ChronicTimeline/MedtronicChronicTimeline";
import MedtronicCircadianRhythm from "views/Reports/ChronicNeuralActivity/CircadianRhythm/MedtronicCircadianRhythm";
import CircadianDataDistribution from "./CircadianDataDistribution.js";

import { SessionController } from "database/session-control";
import { usePlatformContext, setContextState } from "context.js";

function ChronicTimeline({JSONData, therapyModifications}) {
  const navigate = useNavigate();
  const [controller, dispatch] = usePlatformContext();
  const { language, report } = controller;

  const [chronicTimeline, setChronicTimeline] = React.useState(null); 
  const [availableTherapy, setAvailableTherapy] = React.useState({options: [], active: []});
  const [circadianTimelineRange, setCircadianTimelineRange] = React.useState({start: null, end: null});
  const [circadianSelection, setCircadianSelection] = React.useState([]);

  const getChronicTimeline = (JSONData) => {
    const ChronicTimeline = [];
    if (JSONData.DiagnosticData.LFPTrendLogs) {
      for (let hemisphere in JSONData.DiagnosticData.LFPTrendLogs) {
        let TimelineData = {Hemisphere: hemisphere, Time: [], Power: [], Amplitude: []};
        for (let date in JSONData.DiagnosticData.LFPTrendLogs[hemisphere]) {
          const log = JSONData.DiagnosticData.LFPTrendLogs[hemisphere][date].map((entry) => {
            return {
              Time: new Date(entry.DateTime).getTime()/1000,
              Power: entry.LFP,
              Amplitude: entry.AmplitudeInMilliAmps
            }
          });
          TimelineData.Time.push(...log.map((e) => e.Time));
          TimelineData.Power.push(...log.map((e) => e.Power));
          TimelineData.Amplitude.push(...log.map((e) => e.Amplitude));
        }
        const sortedTimeIndices = TimelineData.Time.map((e, i) => i)
          .sort((a, b) => TimelineData.Time[a] - TimelineData.Time[b]);
        TimelineData.Time = sortedTimeIndices.map((i) => TimelineData.Time[i]);
        TimelineData.Power = sortedTimeIndices.map((i) => TimelineData.Power[i]);
        TimelineData.Amplitude = sortedTimeIndices.map((i) => TimelineData.Amplitude[i]);
        ChronicTimeline.push(TimelineData);
      }
    }
    return ChronicTimeline;
  }

  React.useEffect(() => {
    if (JSONData && therapyModifications.length > 0) {
      const ChronicTimelineData = getChronicTimeline(JSONData);
      if (ChronicTimelineData.length === 0)  return;

      let ChronicNeuralActivity = [];
      let AvailableChannels = {options: [], active: []};
      let AvailableTherapy = {options: [], active: []};
      for (let i = 0; i < ChronicTimelineData.length; i++) {
        for (let j = 0; j < therapyModifications.length-1; j++) {
          const availableIndices = ChronicTimelineData[i].Time
              .map((t, idx) => (t > therapyModifications[j].Date && t < therapyModifications[j+1].Date) ? idx : -1)
              .filter(idx => idx !== -1);

          if (availableIndices.length > 0) {
            let timelineEntry = {
              Device: {
                Heritage: "Percept",
              },
              ChannelNames: [ChronicTimelineData[i].Hemisphere + " LFP", ChronicTimelineData[i].Hemisphere + " Amplitude"],
              Time: availableIndices.map((idx) => ChronicTimelineData[i].Time[idx]),
              Data: [availableIndices.map((idx) => ChronicTimelineData[i].Power[idx]),
                     availableIndices.map((idx) => ChronicTimelineData[i].Amplitude[idx])],
              ChannelUnits: [" (a.u.)", " (mA)"],
              Description: [{
                SensingFrequency: therapyModifications[j].New,
                Stimulation: "",
                Bypass: false
              }, {
                SensingFrequency: therapyModifications[j].New,
                Stimulation: "",
                Bypass: false
              }],
              TherapyNote: [null, null],
            }

            const channelName = timelineEntry.Device.Heritage + ": " + ChronicTimelineData[i].Hemisphere;
            const therapyName = channelName + " (" + timelineEntry.Description[0].Stimulation + " Sense: " + timelineEntry.Description[0].SensingFrequency + ")";
            if (!AvailableTherapy.options.includes(therapyName)) {
              AvailableTherapy.options.push(therapyName);
            }

            if (!AvailableChannels.options.includes("Percept: " + ChronicTimelineData[i].Hemisphere)) {
              AvailableChannels.options.push("Percept: " + ChronicTimelineData[i].Hemisphere);
              AvailableChannels.active.push("Percept: " + ChronicTimelineData[i].Hemisphere);
            }
            ChronicNeuralActivity.push(timelineEntry);
          }
        }
      }
      AvailableTherapy.options.push("Time-based Assessment (Zoom in Timeline)");
      setChronicTimeline({
        ChronicNeuralActivity: ChronicNeuralActivity,
        AvailableChannels: AvailableChannels
      });
      setAvailableTherapy({options: AvailableTherapy.options, active: AvailableTherapy.options[0]});
    }
  }, [JSONData, therapyModifications]);

  return useMemo(() => {
    if (!chronicTimeline) {
      return <></>;
    }

    return (
      <Card>
        <Grid container spacing={2}>
          <Grid item xs={12}>
            <MDBox px={2}>
              <MedtronicChronicTimeline data={chronicTimeline.ChronicNeuralActivity} 
                showAdaptiveMode={false} 
                availableChannels={chronicTimeline.AvailableChannels} 
                annotations={[]}
                onSelection={(range) => {
                  setCircadianTimelineRange({start: moment.unix(range.start), end: moment.unix(range.end)});
                }}
                height={400} figureTitle={"ChronicTimeline"}
                handleAddEvent={() => {}} handleDeleteEvent={() => {}} updateColor={() => {}} 
              />
            </MDBox>
          </Grid>
          <Grid item xs={12}>
            <MDBox px={2} display="flex" alignItems="center" flexWrap="wrap" mb={1} flexDirection="row">
              {availableTherapy.options.map((option) => (
                <MDButton key={option} variant={availableTherapy.active === option ? "gradient" : "outlined"} color="secondary" size="small"
                  onClick={() => {
                    setAvailableTherapy((availableTherapy) => {
                      availableTherapy.active = option;
                      return {...availableTherapy};
                    });
                  }}
                  sx={{mr: 1, mb: 1}}
                >
                  <MDTypography variant="button" fontWeight="regular" color={availableTherapy.active === option ? "white" : "info"}>
                    {option}
                  </MDTypography>
                </MDButton>
              ))}
            </MDBox>
          </Grid>
          <Grid item xs={12} sm={6}>
            <MDBox px={2}>
              <MedtronicCircadianRhythm dataToRender={chronicTimeline.ChronicNeuralActivity} 
                channelSelector={chronicTimeline.AvailableChannels.options} 
                activeChannel={availableTherapy.active} 
                annotations={[]}
                timelineRange={{start: circadianTimelineRange.start, end: circadianTimelineRange.end, device: chronicTimeline.AvailableChannels.options[0]}}
                onSelection={(points) => {
                  setCircadianSelection(points);
                }}
                circadianState={{eventCount: false, amplitude: false, histogram: false}} figureTitle={"CircadianRhythm"} />
            </MDBox>
          </Grid>
          <Grid item xs={12} sm={6}>
            <CircadianDataDistribution data={circadianSelection} figureTitle={"CircadianDataDistribution"} />
          </Grid>
        </Grid>
      </Card>
    )
  }, [chronicTimeline, circadianSelection, circadianTimelineRange, availableTherapy]);
}

export default ChronicTimeline;