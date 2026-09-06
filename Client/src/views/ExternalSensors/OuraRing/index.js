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
import useRCS08Sync from "views/Dashboard/Overview/useRCS08Sync";

export default function OuraRingDashboard() {
  const [controller, dispatch] = usePlatformContext();
  const { user, language } = controller;
  const { participant_uid } = useParams();

  const [alert, setAlert] = useState(null);
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [summary, setSummary] = useState(null);

  const [authenticated, setAuthenticated] = useState(0);
  const [OAuthURL, setOAuthURL] = useState(null);
  const [personalAccessToken, setPersonalAccessToken] = useState("");
  const [authPeriod, setAuthPeriod] = useState([]);
  const [managedSync, setManagedSync] = useState(false);
  const sync = useRCS08Sync(managedSync);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setAuthenticated(0);
    setSummary(null);
    SessionController.query("/api/requestOuraRingAuth", {
      RequestType: "RequestURL",
      ParticipantId: participant_uid
    }).then((response) => {
      if (cancelled) return;
      setLoading(false);
      setManagedSync(response.headers["x-bravo-managed-sync"] === "true");
      if (!response.data.OAuthURL) {
        setAuthenticated((a) => a+1);
        setAuthPeriod(response.data.map((a) => a.map((b) => moment(new Date(b*1000+new Date().getTimezoneOffset()*60000)))))
      } else {
        setOAuthURL(response.data.OAuthURL);
      }
    }).catch((error) => {
      if (!cancelled) { setLoading(false); SessionController.displayError(error, setAlert); }
    });
    return () => { cancelled = true; };
  }, [participant_uid]);

  useEffect(() => {
    if (!authenticated) return;
    let cancelled = false;
    SessionController.query("/api/queryOuraRingData", {ParticipantId: participant_uid, RequestType: "RequestSummary"})
      .then(response => { if (!cancelled) setSummary(response.data); })
      .catch(error => { if (!cancelled) SessionController.displayError(error, setAlert); });
    return () => { cancelled = true; };
  }, [participant_uid, authenticated, sync.state?.finished_at_utc]);

  useEffect(() => {
    if (!authenticated || !authPeriod || managedSync) return;
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
  }, [authPeriod, managedSync])

  return (
    <DatabaseLayout>
      {alert}
      
      {loading ? <MDTypography role="status">Loading Oura connection…</MDTypography> : authenticated ? (
        <MDBox>
          <Card sx={{marginTop: 5}}>
            <MDBox p={2}>
              <MDTypography variant="h3">Oura data</MDTypography>
              <MDTypography variant="body2" role="status">{summary === null ? "Loading stored data…" : summary.some(row => row.records > 0) ? "Stored Oura data is available. View Oura timeline opens Oura-only charts with event overlays off. Switch to Combined there to compare with neural signals and surveys." : "No Oura data has been imported yet."}</MDTypography>
              {summary?.some(row => row.qc_version) && <MDTypography variant="body2" role="status">
                Quality control applied: daily summaries from April 30–May 27, 2026 are excluded. Timestamped samples from April 29 at 20:53:55.700 through May 27 at 13:55:36 Pacific are excluded (end time included again). Original stored records are preserved; the timeline and download use QC data. Missing values remain gaps.
              </MDTypography>}
              {summary?.map(row => <MDTypography key={row.name} variant="body2">
                {row.name.replace(/([a-z])([A-Z])/g, "$1 $2")}: {row.records} stored records{row.first_day ? ` · ${row.first_day} – ${row.last_day}` : ""}{row.qc_version ? ` · ${row.summary_included} summaries eligible / ${row.summary_excluded} excluded; ${row.samples_excluded.toLocaleString()} sample times excluded` : ""}
              </MDTypography>)}
              <MDButton color="info" disabled={!summary?.some(row => row.records > 0)} onClick={() => navigate(`/reports/multimodal-timeline-report/${participant_uid}?source=oura`)}>View Oura timeline</MDButton>
            </MDBox>
          </Card>
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
                    {managedSync ? "The platform sync manages the collection period for this account." : "Define the inclusive collection periods for this participant. At least one period is required."}
                  </MDTypography>

                  <MDButton disabled={managedSync} variant="contained" color="info" style={{marginTop: 5}} onClick={() => {
                    setAuthPeriod((authPeriod) => {
                      return [...authPeriod, [moment(new Date()), moment(new Date())]]
                    });
                  }}>
                    {"Add Date Periods"} 
                  </MDButton>
                  
                  <MDButton disabled={managedSync} variant="contained" color="error" style={{marginTop: 5, marginLeft: 5}} onClick={() => {
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
                        disabled={managedSync}
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
                        disabled={managedSync}
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
                    <MDButton disabled={managedSync} variant="contained" color="error" style={{marginLeft: 15}} onClick={() => {
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
                    {managedSync ? "This Oura account uses the platform sync. Updates continue if you leave this page." : "Use the button below to refresh Oura data for the selected collection periods."}
                  </MDTypography>
                </Grid>
                <Grid item xs={12}>
                  <MDButton disabled={managedSync && sync.disabled} variant="contained" color="info" style={{marginTop: 5}} onClick={() => {
                    if (managedSync) { sync.start(); return; }
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
                    {managedSync ? (sync.disabled ? "Checking / syncing…" : "Sync platform data") : "Refresh Oura Ring Data"}
                  </MDButton>
                  {managedSync && <MDTypography variant="body2" role="status">{sync.message || (sync.state ? `Sync status: ${sync.state.status}` : "Checking sync status…")}</MDTypography>}
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
                  <MDBox display="flex" flexDirection={{xs: "column", sm: "row"}} gap={2}>
                    <TextField
                      variant="standard"
                      margin="dense" id="oura_ring_personal_access_token"
                      value={personalAccessToken}
                      onChange={(event) => setPersonalAccessToken(event.target.value)}
                      fullWidth
                    />
                    <MDButton variant="contained" color="info" sx={{minWidth: {xs: 0, sm: 200}}} onClick={() => {
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
