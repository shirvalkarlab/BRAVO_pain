/**
=========================================================
* UF BRAVO Platform
=========================================================

* Copyright 2023 by Jackson Cagle, Fixel Institute
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

import { SessionController } from "database/session-control";
import { usePlatformContext, setContextState } from "context";
import { dictionary, dictionaryLookup } from "assets/translation";

export default function FitbitDashboard() {
  const [controller, dispatch] = usePlatformContext();
  const { user, language } = controller;
  const { participant_uid } = useParams();

  const [alert, setAlert] = useState(null);
  const [OAuthURL, setOAuthURL] = useState(null);
  const [fitbitTokenURL, setFitbitTokenURL] = useState("");

  useEffect(() => {
    SessionController.query("/api/queryFitbitData", {
      RequestType: "RequestOverview",
      ParticipantId: participant_uid
    }).then((response) => {
      
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
                  {"Request Fitbit Web API Access"}
                </MDTypography>
              </Grid>
              <Grid item xs={12}>
                <MDTypography variant="h5" fontWeight="regular" color={"black"} fontSize={15}>
                  {"The Fitbit Dashboard Web API require OAuth 2.0 authentication for your account. Please use the Authentication Link provided below to request Authentication token. "}
                  {"Once authentication is successful, please copy the redirect URL into the textbox below to extract authentication token. "}
                </MDTypography>
              </Grid>
            </Grid>
          </MDBox>
        </Card>
      </MDBox>
    </DatabaseLayout>
  );
};

