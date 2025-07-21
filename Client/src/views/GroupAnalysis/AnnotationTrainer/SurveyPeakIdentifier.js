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
  Autocomplete,
  Card,
  Grid,
  Dialog,
  Stack,
  Switch,
} from "@mui/material"
import { styled } from '@mui/material/styles';

import MDButton from "components/MDButton";
import MDBox from "components/MDBox";
import MDTypography from "components/MDTypography";
import FormField from "components/MDInput/FormField";
import LoadingProgress from "components/LoadingProgress";
import MuiAlertDialog from "components/MuiAlertDialog";

// core components
import DatabaseLayout from "layouts/DatabaseLayout";
import SurveyPSDViewer from "./SurveyPSDViewer";

import { SessionController } from "database/session-control";
import { usePlatformContext, setContextState } from "context.js";
import { dictionary, dictionaryLookup } from "assets/translation.js";

 function SurveyPeakIdentifier() {
  const navigate = useNavigate();
  const [controller, dispatch] = usePlatformContext();
  const { language } = controller;
  const { study_uid } = useParams();

  const [data, setData] = useState(false);
  const [psdData, setPSDData] = useState(null);
  const [resultDialog, setResultDialog] = useState({show: false, participant_uid: "", recordings: []})

  const [availableChannels, setAvailableChannels] = useState({active: null, options: []});

  const [circadianState, setCircadianState] = useState({eventCount: false, amplitude: false});
  const [showAdaptiveMode, setShowAdaptiveMode] = useState(false);
  const [availableTherapy, setAvailableTherapy] = useState({active: null, options: []});
 
  const [annotationState, setAnnotationState] = useState({});
  const [circadianData, setCircadianData] = useState({});
  const [eventPSDData, setEventPSDData] = useState(false);
  const [eventRelatedPower, setEventRelatedPower] = useState(false)
  const [eventLockedPowerData, setEventLockedPowerData] = useState(false);
  const [normalizeCircadianRhythm, setNormalizeCircadianRhythm] = useState(false);

  const [alert, setAlert] = useState(null);

  useEffect(() => {
    setContextState(dispatch, "report", "GroupAnalysis");
    
    setAlert(<LoadingProgress/>);
    SessionController.query("/api/queryGroupAnalysis", {
      AnalysisName: "ExtractSpectralFeaturesDuringSurvey", 
      RequestType: "RequestFullTable"
    }).then((response) => {
      setData(response.data.RecordingCollection.map((a) => {
        a.Participant = response.data.Participants.filter((b) => b.Id == a.ParticipantId);
        if (a.Participant.length > 0) {
          a.Participant = a.Participant[0];
        } else {
          a.Participant = null;
        }
        return a
      }));
      setAlert(null);
    }).catch((error) => {
      SessionController.displayError(error, setAlert);
    });
    
  }, [study_uid]);
  
  useEffect(() => {
    if (data.length > 0 && !psdData) {
      setPSDData(data[0]);
    }
  }, [data]);

  const getRecordingData = (participantId) => {

  }

  return (
    <>
      {alert}
      <DatabaseLayout>
        <MDBox pt={3}>
          <MDBox>
            <Grid container spacing={2}>
              <Grid item xs={12}>
                <Card sx={{width: "100%"}}>
                  <Grid container>
                    {data ? (
                      <>
                        <Grid item xs={12}>
                          <MDBox p={2} display={"flex"} flexDirection={"row"} justifyContent={"space-between"}>
                            <MDTypography variant={"h6"} fontSize={24}>
                              {"Survey PSDs - "} {data.indexOf(psdData) + 1} / {data.length}
                            </MDTypography>
                          </MDBox>
                        </Grid>
                        <Grid item xs={12} lg={12}>
                          <MDBox p={2}>
                            <Autocomplete
                              value={psdData}
                              options={data}
                              onChange={(event, value) => setPSDData(value)}
                              renderOption={(props, option) => <li {...props}>{option.ParticipantId} - {option.Date} - {option.Contact}</li>}
                              getOptionLabel={(option) => `${option.ParticipantId} - ${option.Date} - ${option.Contact}`}
                              renderInput={(params) => (
                                <FormField
                                  {...params}
                                  label={"Channel Selector"}
                                  InputLabelProps={{ shrink: true }}
                                />
                              )}
                            />
                          </MDBox>
                        </Grid>
                        <Grid item xs={12}>
                          <MDBox p={2}>
                            <MDButton color="info" onClick={() => {
                              setPSDData(() => {
                                for (let i = 0; i < data.length; i++) {
                                  if (data[i].ParticipantId === psdData.ParticipantId && data[i].Date === psdData.Date && data[i].Contact === psdData.Contact) {
                                    return data[i-1];
                                  }
                                }
                                return data[0];
                              });
                            }}>
                              <MDTypography variant="button" fontWeight="medium" color="white">
                                {"Last PSD"}
                              </MDTypography>
                            </MDButton>
                            <MDButton color="info" onClick={() => {
                              setPSDData(() => {
                                for (let i = 0; i < data.length; i++) {
                                  if (data[i].ParticipantId === psdData.ParticipantId && data[i].Date === psdData.Date && data[i].Contact === psdData.Contact) {
                                    return data[i+1];
                                  }
                                }
                                return data[data.length-1];
                              });
                            }}>
                              <MDTypography variant="button" fontWeight="medium" color="white">
                                {"Next PSD"}
                              </MDTypography>
                            </MDButton>
                          </MDBox>
                        </Grid>
                        <Grid item xs={12} lg={12}>
                          <SurveyPSDViewer dataToRender={psdData} setCenterFreq={(centerFreq) => {
                            setData(() => {
                              for (let i = 0; i < data.length; i++) {
                                if (data[i].ParticipantId === psdData.ParticipantId && data[i].Date === psdData.Date && data[i].Contact === psdData.Contact) {
                                  data[i].CenterFrequency = centerFreq;
                                }
                              }
                              return data;
                            });
                          }} figureTitle={"Survey PSDs"} />
                        </Grid>
                      </>
                    ) : (
                      <Grid item xs={12}>
                        <MDBox p={2}>
                          <MDTypography variant="h6" fontSize={24}>
                            {dictionary.WarningMessage.NoData[language]}
                          </MDTypography>
                        </MDBox>
                      </Grid>
                    )}
                  </Grid>
                </Card>
              </Grid>
            </Grid>
          </MDBox>
        </MDBox>
      </DatabaseLayout>
    </>
  );
}

export default SurveyPeakIdentifier;
