/**
=========================================================
* UF BRAVO Platform
=========================================================

* Copyright 2025 by Jackson Cagle, Fixel Institute
* The source code is made available under a Creative Common NonCommercial ShareAlike License (CC BY-NC-SA 4.0) (https://creativecommons.org/licenses/by-nc-sa/4.0/) 

 =========================================================

* The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.
*/

import { currentTargetText } from "utils/participantTargets";
import { useEffect, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";

import {
  Alert,
  Autocomplete,
  Card,
  FormControlLabel,
  Grid,
  Stack,
  Switch,
  ToggleButton,
  ToggleButtonGroup,
  SpeedDial,
  SpeedDialAction,
  SpeedDialIcon
} from "@mui/material"
import { styled } from '@mui/material/styles';

import MDButton from "components/MDButton";
import MDBox from "components/MDBox";
import MDTypography from "components/MDTypography";
import FormField from "components/MDInput/FormField";
import LoadingProgress from "components/LoadingProgress";
import MuiAlertDialog from "components/MuiAlertDialog";

import KeyboardDoubleArrowUpIcon from '@mui/icons-material/KeyboardDoubleArrowUp';
import CachedIcon from '@mui/icons-material/Cached';

// core components
import GenericTimeline from "./GenericTimeline";
import StatisticalTable from "./StatisticalTable";
import { channelsForView, defaultViewChannels, timelineViews } from "graphing-utility/timelineViews";

import DatabaseLayout from "layouts/DatabaseLayout";

import { SessionController } from "database/session-control";
import { usePlatformContext, setContextState } from "context.js";
import { dictionary, dictionaryLookup } from "assets/translation.js";

 function ChronicTimeline() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const requestedSource = searchParams.get("source");
  const initialView = timelineViews.some(view => view.value === requestedSource) ? requestedSource : "combined";
  const [dataView, setDataView] = useState(initialView);
  const [controller, dispatch] = usePlatformContext();
  const { language } = controller;
  const { participant_uid } = useParams();

  const [data, setData] = useState(false);
  const [annotations, setAnnotations] = useState([]);
  const [showEventOverlays, setShowEventOverlays] = useState(initialView === "combined");

  const [availableChannels, setAvailableChannels] = useState({active: [], options: []});

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
    if (!participant_uid) {
      navigate("/database", {replace: false});
      return;
    } 
    setContextState(dispatch, "report", "GeneralReports");
    
    let cancelled = false;
    setData(false);
    setDataView(initialView);
    setShowEventOverlays(initialView === "combined");
    setAvailableChannels({active: [], options: []});
    setAlert(<LoadingProgress/>);
    SessionController.query("/api/queryChronicTimeline", {
      ParticipantId: participant_uid, 
      RequestType: "RequestAll"
    }).then((response) => {
      if (cancelled) return;
      if (response.data.Timelines.length == 0) {
        setAlert(null);
        return;
      }

      setAvailableChannels({
        active: defaultViewChannels(response.data.Timelines, initialView),
        options: channelsForView(response.data.Timelines, initialView),
      });
      setData(response.data.Timelines);
      setAnnotations(response.data.Annotations);
      setAlert(null);
    }).catch((error) => {
      if (!cancelled) SessionController.displayError(error, setAlert);
    });
    return () => { cancelled = true; };

  }, [participant_uid, initialView]);

  const changeDataView = (event, view) => {
    if (!view || view === dataView) return;
    const options = channelsForView(data, view);
    const retained = availableChannels.active.filter(channel => options.includes(channel));
    const defaults = defaultViewChannels(data, view);
    const active = view === "combined" ? [...new Set([...retained, ...defaults])]
      : retained.length ? retained : defaults;
    setDataView(view);
    setAvailableChannels({active, options});
    if (view !== "combined") setShowEventOverlays(false);
  };
  
  const updateAnnotationColor = (data) => {
    setAnnotationState({...data})
  };
  
  useEffect(() => {
    for (let i in availableChannels.active) {
      for (let j in data) {
        if (data[j].ChannelNames.includes(availableChannels.active[i])) {
          if (data[j].DataId && !data[j].Data) {
            setAlert(<LoadingProgress/>);
            SessionController.query("/api/queryChronicTimeline", {
              ParticipantId: participant_uid, 
              RequestType: "RequestData",
              DataIds: data[j].DataId,
              Channel: availableChannels.active[i]
            }).then((response) => {
              setData((oldData) => {
                oldData = oldData.filter((d) => d.DataId != data[j].DataId);
                for (let k in response.data) {
                  oldData.push({
                    ...data[j],
                    DataId: null,
                    ...response.data[k],
                  });
                }
                return [...oldData];
              });
              
              setAlert(null);
            }).catch((error) => {
              SessionController.displayError(error, setAlert);
            });

          } 
        }
      }
    }
  }, [availableChannels.active]);

  const handleAddEvent = async (eventInfo) => {
    setAlert(<LoadingProgress />);
    try {
      let duration = 0
      duration = new Date(eventInfo.enddate.toISOString().split("T")[0] + "T" + eventInfo.endtime.toISOString().split("T")[1]).getTime() / 1000;
      duration -= (eventInfo.enddate.utcOffset() - eventInfo.endtime.utcOffset()) * 60;
      duration -= eventInfo.time / 1000;

      const response = await SessionController.query("/api/addParticipantAnnotation", {
        ParticipantId: participant_uid,
        EventName: eventInfo.name,
        EventTime: eventInfo.time / 1000,
        EventDuration: duration,
        EventType: "ChronicCustomEvent"
      });
      setAlert(null);

      if (response.status == 200) {
        setAnnotations([...annotations, response.data]);
      }
    } catch (error) {
      SessionController.displayError(error, setAlert);
    }
  };

  const handleDeleteEvent = async (eventInfo) => {
    if (annotations.length > 0) {
      eventInfo.targetInfo = eventInfo;
    }

    for (let i = 0; i < annotations.length; i++) {
      let absoluteDiffTime = Math.abs(annotations[i].Date - eventInfo.time/1000);
      if (!eventInfo.targetInfo.timeDiff || absoluteDiffTime < eventInfo.targetInfo.timeDiff) {
        eventInfo.targetInfo = annotations[i];
        eventInfo.targetInfo.timeDiff = absoluteDiffTime;
      }
    }
    
    if (eventInfo.targetInfo.timeDiff) {
      setAlert(<MuiAlertDialog 
        title={`Remove ${eventInfo.targetInfo.Name} Event`}
        message={`Are you sure you want to delete the entry [${eventInfo.targetInfo.Name}] @ ${new Date(eventInfo.targetInfo.Date*1000)} ?`}
        confirmText={"YES"}
        denyText={"NO"}
        denyButton
        handleClose={() => setAlert(null)}
        handleDeny={() => setAlert(null)}
        handleConfirm={() => {
          SessionController.query("/api/deleteParticipantAnnotation", {
            ParticipantId: participant_uid,
            EventId: eventInfo.targetInfo.Id
          }).then(() => {
            setAnnotations((annotations) => {
              return [...annotations.filter((a) => a.Id != eventInfo.targetInfo.Id)];
            });
            setAlert(null);
          }).catch((error) => {
            SessionController.displayError(error, setAlert);
          });
        }}
      />)
    }
  }

  const exportCurrentStream = () => {
    let downloader = document.createElement('a');
    downloader.href = SessionController.getDownloadLink("/api/downloadData", {
      ParticipantId: participant_uid,
      CacheType: "queryChronicTimeline"
    });
    downloader.target = '_blank';
    downloader.click();
  };

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
                              {"Multimodal Timeline"}
                            </MDTypography>
                            <MDBox>
                              <MDButton size="large" variant="contained" color="primary" style={{marginBottom: 3}} onClick={() => exportCurrentStream()}>
                                {dictionaryLookup(dictionary.FigureStandardText, "Export", language)}
                              </MDButton>
                              <MDButton size="large" variant="contained" color="info" style={{marginBottom: 3}} onClick={() => {
                                SessionController.query("/api/queryChronicTimeline", {
                                  ParticipantId: participant_uid, 
                                  RequestType: "DeleteCache"
                                }).then((response) => {
                                  window.location.reload()
                                });
                              }}>
                                {"Clear Cache"}
                              </MDButton>
                            </MDBox>
                          </MDBox>
                        </Grid>
                        <Grid item xs={12}>
                          <MDBox p={2}>
                            {data.filter(item => item.Status === "review_required").map(item => (
                              <Alert key={item.FormId || item.FormName} severity="warning" sx={{ mb: 2 }}>
                                {item.FormName}: {item.Message}
                              </Alert>
                            ))}
                            <ToggleButtonGroup exclusive value={dataView} onChange={changeDataView}
                              aria-label="Data view" sx={{mb: 2, flexWrap: "wrap"}}>
                              {timelineViews.map(view => <ToggleButton key={view.value} value={view.value}
                                disabled={channelsForView(data, view.value).length === 0}
                                title={channelsForView(data, view.value).length ? view.label : `No data available for ${view.label.toLowerCase()}`}>
                                {view.label}
                              </ToggleButton>)}
                            </ToggleButtonGroup>
                            <Autocomplete
                              multiple
                              value={availableChannels.active}
                              options={availableChannels.options}
                              getOptionLabel={currentTargetText}
                              onChange={(event, value) => setAvailableChannels({...availableChannels, active: value})}
                              renderInput={(params) => (
                                <FormField
                                  {...params}
                                  label={"Channel Selector"}
                                  InputLabelProps={{ shrink: true }}
                                />
                              )}
                            />
                            <FormControlLabel
                              control={<Switch checked={showEventOverlays} onChange={(event) => setShowEventOverlays(event.target.checked)} />}
                              label="Show event overlays"
                            />
                            <MDTypography variant="caption" display="block">
                              Show or hide recorded events such as High Pain across the selected charts.
                            </MDTypography>
                          </MDBox>
                        </Grid>
                        <Grid item xs={12} lg={12}>
                          {availableChannels.active.length === 0 && <MDBox p={2}>
                            <MDTypography variant="body2" role="status">{availableChannels.options.length
                              ? "Choose one or more channels above to display them on the timeline."
                              : "No channels are available for this data view. Choose another view."}</MDTypography>
                          </MDBox>}
                          {availableChannels.active.length > 0 && <GenericTimeline data={data} height={150} availableChannels={availableChannels} annotations={annotations} showEventOverlays={showEventOverlays} handleAddEvent={handleAddEvent} handleDeleteEvent={handleDeleteEvent} updateColor={updateAnnotationColor} figureTitle={"ChronicTimeline"}/>}
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

              {data ? (
                <Grid item xs={12}>
                  <Card sx={{width: "100%"}}>
                    <Grid container>
                      <Grid item xs={12}>
                        <MDBox p={2} display={"flex"} flexDirection={"row"} justifyContent={"space-between"}>
                          <MDTypography variant={"h6"} fontSize={24}>
                            {"Statistical Table"}
                          </MDTypography>
                        </MDBox>
                      </Grid>
                      <Grid item xs={12} lg={12}>
                        <StatisticalTable data={data} availableChannels={availableChannels} annotations={annotations} />
                      </Grid>
                    </Grid>
                  </Card>
                </Grid>
              ) : null}
            </Grid>
          </MDBox>
          <MDBox style={{
            position: 'sticky',
            bottom: 32,
            right: 32,
            pointerEvents: "none"
          }}>
            <SpeedDial
              ariaLabel={"SurveySpeedDial"}
              color={"info"}
              icon={<SpeedDialIcon sx={{display: "flex", justifyContent: "center", alignItems: "center", fontSize: 30}}/>}
              FabProps={{
                color: "info",
                sx: {display: "flex", marginLeft: "auto"}
              }}
              sx={{alignItems: "end"}}
              hidden={false}
            >
              <SpeedDialAction
                key={"GoToTop"}
                icon={<KeyboardDoubleArrowUpIcon sx={{display: "flex", justifyContent: "center", alignItems: "center", fontSize: 30}}/>}
                tooltipTitle={"Go to Top"}
                onClick={() => {
                  window.scrollTo({ top: 0, behavior: 'smooth' });
                }}
              />
              <SpeedDialAction
                key={"ClearCache"}
                icon={<CachedIcon sx={{display: "flex", justifyContent: "center", alignItems: "center", fontSize: 30}}/>}
                tooltipTitle={"Clear Cache (Reprocessing)"}
                onClick={() => {
                  SessionController.query("/api/queryChronicTimeline", {
                    ParticipantId: participant_uid, 
                    RequestType: "DeleteCache"
                  }).then((response) => {
                    window.location.reload()
                  });
                }}
              />
            </SpeedDial>
          </MDBox>
        </MDBox>
      </DatabaseLayout>
    </>
  );
}

export default ChronicTimeline;
