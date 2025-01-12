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
import { useNavigate, useParams, useSearchParams } from "react-router-dom";

import {
  Card,
  Grid,
  Link,
  Dialog,
  DialogContent,
  DialogActions,
  TextField,
  Step,
  StepLabel,
  Stepper,
  Select,
  MenuItem,
  FormControl,
  InputLabel
} from "@mui/material";

import { AdapterMoment } from '@mui/x-date-pickers/AdapterMoment';
import { LocalizationProvider } from '@mui/x-date-pickers/LocalizationProvider';
import { TimePicker } from '@mui/x-date-pickers/TimePicker';

import MDBox from "components/MDBox";
import MDTypography from "components/MDTypography";
import MDInput from "components/MDInput";
import MDButton from "components/MDButton";
import MuiAlertDialog from "components/MuiAlertDialog";
import LoadingProgress from "components/LoadingProgress";

import DatabaseLayout from "layouts/DatabaseLayout";
import FitbitScoreTimeline from "./FitbitScoreTimeline";

import { SessionController } from "database/session-control";
import { usePlatformContext, setContextState } from "context";
import { dictionary, dictionaryLookup } from "assets/translation";

export default function FitbitDashboard() {
  const [controller, dispatch] = usePlatformContext();
  const { user, language } = controller;
  const { participant_uid } = useParams();

  const [alert, setAlert] = useState(null);
  const [data, setData] = useState(null);

  useEffect(() => {
    setAlert(<LoadingProgress />)
    SessionController.query("/api/queryFitbitData", {
      RequestType: "RequestOverview",
      ParticipantId: participant_uid
    }).then((response) => {
      setData(response.data)
      setAlert(null)
    }).catch((error) => {
      SessionController.displayError(error, setAlert);
    });
  }, []);

  return (
    <DatabaseLayout>
      {alert}
      <MDBox>
        <Card sx={{marginTop: 5}}>
          <MDBox p={2}>
            <Grid container spacing={2}>
              <Grid item xs={12}>
                <MDTypography variant="h3">
                  {"Request Fitbit Data Update"}
                </MDTypography>
              </Grid>
              <Grid item xs={12}>
                <MDTypography variant="h5" fontWeight="regular" color={"black"} fontSize={15}>
                  {"Fitbit Data API has a request data limit of 150 Request Per Hour (Reset at xx:00), therefore, the data will be be automatically requested unless user interaction. "}
                  {"Please use the button below to request data update. Each refresh (depending on the duration of data acquisition) takes about 20 Requests to complete. "}
                </MDTypography>
              </Grid>
              <Grid item xs={12}>
                <MDButton variant="contained" color="info" style={{marginTop: 5}} onClick={() => {
                  setAlert(<LoadingProgress />)
                  SessionController.query("/api/queryFitbitData", {
                    RequestType: "RefreshFitbitData",
                    ParticipantId: participant_uid
                  }).then((response) => {
                    setAlert(null)
                  }).catch((error) => {
                    SessionController.displayError(error, setAlert);
                  });
                }}>
                  {"Refresh Fitbit Data"} 
                </MDButton>
              </Grid>
            </Grid>
          </MDBox>
          <MDBox p={2}>
            <Grid container spacing={2}>
              <Grid item xs={12}>
                <FitbitScoreTimeline dataToRender={data} figureTitle={"FitbitScoreTimeline"}/>
              </Grid>
            </Grid>
          </MDBox>
        </Card>
      </MDBox>
    </DatabaseLayout>
  );
};

