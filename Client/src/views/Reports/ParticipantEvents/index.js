/**
=========================================================
* UF BRAVO Platform
=========================================================

* Copyright 2025 by Jackson Cagle, Fixel Institute
* The source code is made available under a Creative Common NonCommercial ShareAlike License (CC BY-NC-SA 4.0) (https://creativecommons.org/licenses/by-nc-sa/4.0/) 

 =========================================================

* The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.
*/

import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import {
  TextField,
  Autocomplete,
  Card,
  Grid,
} from "@mui/material";

import { AdapterMoment } from '@mui/x-date-pickers/AdapterMoment';
import { LocalizationProvider } from '@mui/x-date-pickers/LocalizationProvider';
import { DatePicker } from '@mui/x-date-pickers/DatePicker';
import { TimePicker } from '@mui/x-date-pickers/TimePicker';

import colormap from "colormap";

import MDBox from "components/MDBox";
import MDTypography from "components/MDTypography";
import RadioButtonGroup from "components/RadioButtonGroup";
import MDBadge from "components/MDBadge";
import MDButton from "components/MDButton";
import FormField from "components/MDInput/FormField";
import LoadingProgress from "components/LoadingProgress";

// core components
import ParticipantEventCount from "./ParticipantEventCount";
import EventPowerSpectrum from "./EventPowerSpectrum";

import DatabaseLayout from "layouts/DatabaseLayout";

import { SessionController } from "database/session-control";
import { usePlatformContext, setContextState } from "context.js";
import { dictionary } from "assets/translation.js";

function ParticipantEvents() {
  const navigate = useNavigate();
  const [controller, dispatch] = usePlatformContext();
  const { language } = controller;
  const { participant_uid } = useParams();

  const [data, setData] = useState(false);
  const [annotations, setAnnotations] = useState([]);
  const [eventList, setEventList] = useState([]);
  const [eventGroupingDuration, setEventGroupingDuration] = useState("Month");

  const [timerange, setTimerange] = useState({start: null, end: null});

  const [alert, setAlert] = useState(null);

  useEffect(() => {
    if (!participant_uid) {
      navigate("/dashboard", {replace: false});
      return;
    }
    setContextState(dispatch, "report", "GeneralReports");

    setAlert(<LoadingProgress/>);
    SessionController.query("/api/queryParticipantEvents", {
      RequestType: "RequestAll",
      ParticipantId: participant_uid
    }).then((response) => {
      setAnnotations(response.data.Annotations);
      setAlert(null);
    }).catch((error) => {
      SessionController.displayError(error, setAlert);
    });
  }, [participant_uid]);

  const adapterLocales = {
    "zh": "zh-CN",
    "en": "en-US"
  }

  return (
    <DatabaseLayout>
    {alert}
      <MDBox pt={3}>
        <MDBox>
          <Grid container spacing={2}>
            {annotations.length > 0 ? (
            <Grid item xs={12}>
              <Card sx={{width: "100%"}}>
                <Grid container>
                  <Grid item xs={12}>
                    <MDBox p={2}>
                      <MDTypography variant={"h6"} fontSize={24}>
                        {"Participant Chronic Event-Frequency Timeline"}
                      </MDTypography>
                    </MDBox>
                  </Grid>
                  <Grid item xs={12}>
                    <ParticipantEventCount dataToRender={annotations} height={400} events={eventList} figureTitle={"EventCounts"}/>
                  </Grid>
                </Grid>
              </Card>
            </Grid>
            ) : null}
            <Grid item xs={12}>
              <Card sx={{width: "100%"}}>
                <Grid container>
                  <Grid item xs={12}>
                    <MDBox p={2}>
                      <MDTypography variant={"h6"} fontSize={24}>
                        {dictionary.PatientEvents.Figure.EventFrequencyTimeRange[language]}
                      </MDTypography>
                    </MDBox>
                  </Grid>
                  <Grid item xs={12}>
                    <MDBox p={2} display={"flex"} flexDirection={"row"}>
                      <MDTypography variant={"h6"} fontSize={24} pr={2}>
                        {"From"}
                      </MDTypography>
                      <LocalizationProvider dateAdapter={AdapterMoment} adapterLocale={"us"}>
                        <DatePicker
                          label="Start Date"
                          value={timerange.start}
                          onChange={(newDate) => {
                            setTimerange({...timerange, start: newDate});
                          }}
                          renderInput={(params) => <TextField {...params} />}
                        />
                      </LocalizationProvider>
                      <MDTypography variant={"h6"} fontSize={24} px={2}>
                        {"To"}
                      </MDTypography>
                      <LocalizationProvider dateAdapter={AdapterMoment}>
                        <DatePicker
                          label="End Date"
                          value={timerange.end}
                          onChange={(newDate) => {
                            setTimerange({...timerange, end: newDate});
                          }}
                          renderInput={(params) => <TextField {...params} />}
                        />
                      </LocalizationProvider>
                    </MDBox>
                  </Grid>
                  <Grid item xs={12}>
                    <EventPowerSpectrum dataToRender={data} timerange={[timerange.start, timerange.end]} events={eventList} height={600} figureTitle={"EventPSDs"} />
                  </Grid>
                </Grid>
              </Card>
            </Grid>
          </Grid>
        </MDBox>
      </MDBox>
    </DatabaseLayout>
  );
}

export default ParticipantEvents;
