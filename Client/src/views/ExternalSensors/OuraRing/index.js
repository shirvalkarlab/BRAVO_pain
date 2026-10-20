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

import moment from "moment";
import { AdapterMoment } from '@mui/x-date-pickers/AdapterMoment';
import { LocalizationProvider } from '@mui/x-date-pickers/LocalizationProvider';
import { DatePicker } from '@mui/x-date-pickers/DatePicker';

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

const streamLabels = {
  DailyActivity: "Daily activity", DailyReadiness: "Daily readiness",
  DailyCardiovascularAge: "Cardiovascular age", DailySpo2: "Blood oxygen",
  DailyStress: "Daily stress", HeartRate: "Heart rate", Sleep: "Sleep"
};

export default function OuraRingDashboard() {
  const [controller, dispatch] = usePlatformContext();
  const { user, language } = controller;
  const { participant_uid } = useParams();

  const [alert, setAlert] = useState(null);
  const [data, setData] = useState(null);

  const [authenticated, setAuthenticated] = useState(0);
  const [OAuthURL, setOAuthURL] = useState(null);
  const [personalAccessToken, setPersonalAccessToken] = useState("");
  const [authPeriod, setAuthPeriod] = useState([]);
  const [managedConnection, setManagedConnection] = useState(false);
  const [canRefresh, setCanRefresh] = useState(true);

  useEffect(() => {
    SessionController.query("/api/requestOuraRingAuth", {
      RequestType: "RequestURL",
      ParticipantId: participant_uid
    }).then((response) => {
      if (!response.data.OAuthURL) {
        const managed = response.data.ManagedByServer === true;
        const periods = managed ? response.data.DatePeriods : response.data;
        setManagedConnection(managed);
        setCanRefresh(!managed || response.data.CanRefresh === true);
        setAuthenticated((a) => a+1);
        setAuthPeriod(periods.map((a) => a.map((b) => moment(new Date(b*1000+new Date().getTimezoneOffset()*60000)))))
      } else {
        setOAuthURL(response.data.OAuthURL);
      }
    }).catch((error) => {
      SessionController.displayError(error, setAlert);
    });
  }, []);

  useEffect(() => {
    if (authenticated < 1) return;
    
    setAlert(<LoadingProgress />)
    SessionController.query("/api/queryOuraRingData", {
      RequestType: "RequestOverview",
      ParticipantId: participant_uid
    }).then((response) => {
      setData(response.data)
      setAlert(null)
    }).catch((error) => {
      SessionController.displayError(error, setAlert);
    });
  }, [authenticated])

  useEffect(() => {
    if (!authenticated || !authPeriod || managedConnection) return;
    SessionController.query("/api/requestOuraRingAuth", {
      RequestType: "SetAuthPeriod",
      ParticipantId: participant_uid,
      DatePeriods: authPeriod.map((a) => a.map((b) => {
        const timestamp = new Date(b.format("YYYY-MM-DD")+"T00:00:00Z").getTime()/1000 - b.utcOffset()*60;
        return timestamp
      })),
    }).then((response) => {
      
    }).catch((error) => {
      SessionController.displayError(error, setAlert);
    });
  }, [authPeriod, managedConnection])

  return (
    <DatabaseLayout>
      {alert}
      
      {authenticated ? (
        <MDBox>
          {managedConnection ? (
            <Card sx={{marginTop: 5}}>
              <MDBox p={2}>
                <MDTypography variant="h3">{"Oura connection"}</MDTypography>
                <MDTypography variant="body2">
                  {"This participant's Oura connection and collection dates are managed by the server administrator. Stored observations remain available if a refresh fails."}
                </MDTypography>
              </MDBox>
            </Card>
          ) : (
          <Card sx={{marginTop: 5}}>
            <MDBox p={2}>
              <Grid container spacing={2}>
                <Grid item xs={12}>
                  <MDTypography variant="h3">
                    {"Define Data Collection Period"}
                  </MDTypography>
                </Grid>
                <Grid item xs={12}>
                  <MDTypography variant="h5" fontWeight="regular" color={"black"} fontSize={15}>
                    {"If multiple participants are sharing the same device, please use this section to define time period of data collection. All dates are inclusive. If empty, server will send error. "}
                  </MDTypography>

                  <MDButton variant="contained" color="info" style={{marginTop: 5}} onClick={() => {
                    setAuthPeriod((authPeriod) => {
                      return [...authPeriod, [moment(new Date()), moment(new Date())]]
                    });
                  }}>
                    {"Add Date Periods"} 
                  </MDButton>
                  
                  <MDButton variant="contained" color="error" style={{marginTop: 5, marginLeft: 5}} onClick={() => {
                    SessionController.query("/api/requestOuraRingAuth", {
                      RequestType: "DeleteAuthentication",
                      ParticipantId: participant_uid
                    }).then((response) => {
                      setAuthenticated(0);
                      setAuthPeriod([])
                    }).catch((error) => {
                      SessionController.displayError(error, setAlert);
                    });
                  }}>
                    {"Delete Authentication"} 
                  </MDButton>
                </Grid>
                {authPeriod.map((section, sectionIndex) => {
                return <Grid key={sectionIndex} item xs={12}>
                  <MDBox p={2} display={"flex"} flexDirection={"row"} alignItems={"center"}>
                    <MDTypography variant={"h6"} fontSize={24} pr={2}>
                      {"Date " + (sectionIndex+1).toFixed(0) + ": From"}
                    </MDTypography>
                    <LocalizationProvider dateAdapter={AdapterMoment} adapterLocale={"us"}>
                      <DatePicker
                        label="Start Date"
                        value={section[0]}
                        onChange={(newDate) => {
                          setAuthPeriod((authPeriod) => {
                            authPeriod[sectionIndex][0] = newDate;
                            return [...authPeriod];
                          });
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
                        value={section[1]}
                        onChange={(newDate) => {
                          setAuthPeriod((authPeriod) => {
                            authPeriod[sectionIndex][1] = newDate;
                            return [...authPeriod];
                          });
                        }}
                        renderInput={(params) => <TextField {...params} />}
                      />
                    </LocalizationProvider>
                    <MDButton variant="contained" color="error" style={{marginLeft: 15}} onClick={() => {
                      setAuthPeriod((authPeriod) => {
                        authPeriod.splice(sectionIndex, 1);
                        return [...authPeriod]
                      });
                    }}>
                      {"Remove"} 
                    </MDButton>
                  </MDBox>
                </Grid>
                })}
              </Grid>
            </MDBox>
          </Card>
          )}
          <Card sx={{marginTop: 5}}>
            <MDBox p={2}>
              <MDTypography variant="h3">{"Stored Oura observations"}</MDTypography>
              {data && Object.keys(data).length > 0 ? Object.entries(data).map(([stream, records]) => (
                <MDTypography key={stream} variant="body2">
                  {(streamLabels[stream] || stream) + ": " + (Array.isArray(records) ? records.length + " stored records" : "unavailable")}
                </MDTypography>
              )) : <MDTypography variant="body2">{"No Oura observations have been imported yet."}</MDTypography>}
            </MDBox>
          </Card>
          <Card sx={{marginTop: 5}}>
            <MDBox p={2}>
              <Grid container spacing={2}>
                <Grid item xs={12}>
                  <MDTypography variant="h3">
                    {"Request Oura Ring Data Update"}
                  </MDTypography>
                </Grid>
                <Grid item xs={12}>
                  <MDTypography variant="h5" fontWeight="regular" color={"black"} fontSize={15}>
                    {managedConnection
                      ? "Refresh requests the configured Oura history. A complete refresh replaces the stored snapshot only after every data stream succeeds."
                      : "Use the button below to request data for the selected collection periods."}
                  </MDTypography>
                </Grid>
                <Grid item xs={12}>
                  {canRefresh && <MDButton variant="contained" color="info" style={{marginTop: 5}} onClick={() => {
                    setAlert(<LoadingProgress />)
                    SessionController.query("/api/queryOuraRingData", {
                      RequestType: "RefreshOuraRingData",
                      ParticipantId: participant_uid
                    }).then((response) => {
                      setAuthenticated((a) => a+1);
                      setAlert(null);
                    }).catch((error) => {
                      SessionController.displayError(error, setAlert);
                    });
                  }}>
                    {"Refresh Oura Ring Data"} 
                  </MDButton>}
                  <MDButton variant="contained" color="primary" style={{marginTop: 5, marginLeft: 15}} onClick={() => {
                    let downloader = document.createElement('a');
                    downloader.href = SessionController.getDownloadLink("/api/queryOuraRingData", {
                      ParticipantId: participant_uid
                    });
                    downloader.download = 'OuraRingData.pkl';
                    downloader.target = '_blank';
                    downloader.click();
                  }}>
                    {"Download Oura Ring Data"} 
                  </MDButton>
                </Grid>
              </Grid>
            </MDBox>
          </Card>
        </MDBox>
      ) : (
        <MDBox>
          <Card sx={{marginTop: 5}}>
            <MDBox p={2}>
              <Grid container spacing={2}>
                <Grid item xs={12}>
                  <MDTypography variant="h3">
                    {"Request Oura Ring API Access"}
                  </MDTypography>
                </Grid>
                <Grid item xs={12}>
                  <MDTypography variant="h5" fontWeight="regular" color={"black"} fontSize={15}>
                    {"The Oura Ring Dashboard API require OAuth 2.0 or Personal Access Token authentication for your account. In BRAVO we decided to implemented the simpler Personal Access Token authentication."}
                    {"Please enter your Personal Access Token below."}
                  </MDTypography>
                </Grid>
                {OAuthURL ? (
                <Grid item xs={12} sx={{lineHeight: 1}}>
                  <Link href={OAuthURL} target="_blank">
                    <MDTypography variant="p" fontWeight="regular" color={"info"} fontSize={12}>
                      {OAuthURL}
                    </MDTypography>
                  </Link>
                </Grid>
                ) : null}

                {OAuthURL ? (
                <Grid item xs={12} sx={{lineHeight: 1}}>
                  <MDBox display={"flex"} flexDirection={"row"}>
                    <TextField
                      variant="standard"
                      margin="dense" id="oura_ring_personal_access_token"
                      value={personalAccessToken}
                      onChange={(event) => setPersonalAccessToken(event.target.value)}
                      fullWidth
                    />
                    <MDButton variant="contained" color="info" style={{minWidth: 200, marginLeft: 15}} onClick={() => {
                      setAlert(<LoadingProgress />)
                      SessionController.query("/api/requestOuraRingAuth", {
                        RequestType: "VerifyToken",
                        ParticipantId: participant_uid,
                        AccessToken: personalAccessToken
                      }).then((response) => {
                        setAlert(null);
                        setAuthenticated(true);
                      }).catch((error) => {
                        SessionController.displayError(error, setAlert);
                      });
                    }}>
                      {"Verify Token"} 
                    </MDButton>
                  </MDBox>
                </Grid>
                ) : null}
              </Grid>
            </MDBox>
          </Card>
        </MDBox>
      )}

    </DatabaseLayout>
  );
};

