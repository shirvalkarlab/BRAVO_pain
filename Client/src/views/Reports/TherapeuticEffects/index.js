/**
=========================================================
* UF BRAVO Platform
=========================================================

* Copyright 2025 by Jackson Cagle, Fixel Institute
* The source code is made available under a Creative Common NonCommercial ShareAlike License (CC BY-NC-SA 4.0) (https://creativecommons.org/licenses/by-nc-sa/4.0/) 

 =========================================================

* The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.
*/

import { useEffect, useState, useMemo } from "react";
import { useNavigate, useParams } from "react-router-dom";

import {
  Autocomplete,
  Drawer,
  Divider,
  ToggleButton,
  ToggleButtonGroup,
  Card,
  Grid,
  IconButton,
  SpeedDial,
  SpeedDialAction,
  SpeedDialIcon,
  Slider
} from "@mui/material"

import { 
  ChevronRight as ChevronRightIcon,
  Settings as SettingsIcon,
  KeyboardDoubleArrowUp as KeyboardDoubleArrowUpIcon, 
  Dashboard as DashboardIcon
} from "@mui/icons-material";

// core components
import MDBox from "components/MDBox";
import MDTypography from "components/MDTypography";
import MDButton from "components/MDButton";
import LoadingProgress from "components/LoadingProgress";
import MuiAlertDialog from "components/MuiAlertDialog";
import FormField from "components/MDInput/FormField";

import DatabaseLayout from "layouts/DatabaseLayout";
import LayoutOptions from "./LayoutOptions";

import TherapeuticAnalysisTable from "./TherapeuticAnalysisTable";
import TimeFrequencyAnalysis from "./TimeFrequencyAnalysis";
import StimulationPSD from "./StimulationPSD";

import { SessionController } from "database/session-control";
import { usePlatformContext, setContextState } from "context.js";
import { dictionary, dictionaryLookup } from "assets/translation.js";
import ConfigurationDialog from "components/ConfigurationDialog";

function TherapeuticEffects() {
  const navigate = useNavigate();
  const [controller, dispatch] = usePlatformContext();
  const { experiment, TherapeuticEffectLayout, language } = controller;
  const { participant_uid } = useParams();

  const [recordingId, setRecordingId] = useState([]);

  const [availableAnalysis, setAvailableAnalysis] = useState({Analyses: [], Recordings: []});
  const [data, setData] = useState(false);
  const [dataToRender, setDataToRender] = useState(false);

  const [annotations, setAnnotations] = useState([]);
  const [drawerOpen, setDrawerOpen] = useState({open: false, config: {}});
  const [channel, setChannel] = useState({active: "", options: []});

  const [channelInfos, setChannelInfos] = useState([]);

  const [therapyLabel, setTherapyLabel] = useState({active: "Default", options: ["Default"]});
  
  const [eventPSDs, setEventPSDs] = useState(false);
  const [eventPSDSelector, setEventPSDSelector] = useState({
    type: "Channels",
    options: [],
    value: ""
  });
  const [eventSpectrograms, setEventSpectrograms] = useState(false);
  const [eventSpectrogramSelector, setEventSpectrogramSelector] = useState({
    options: [],
    value: ""
  });

  const [referenceType, setReferenceType] = useState([]);
  
  const [alert, setAlert] = useState(null);

  useEffect(() => {
    if (!participant_uid) {
      navigate("/dashboard", {replace: false});
      return;
    }
    setContextState(dispatch, "report", "GeneralReports");

    setAlert(<LoadingProgress/>);
    SessionController.query("/api/queryTherapeuticEffectAnalysis", {
      RequestType: "Overview",
      ParticipantId: participant_uid
    }).then((response) => {
      setAvailableAnalysis(response.data);
      setAlert(null);
    }).catch((error) => {
      SessionController.displayError(error, setAlert);
    });
    
  }, [participant_uid]);

  const getRecordingData = async (analysis, channel) => {
    let newQueryChannel = [];
    for (let i in channel) {
      if (!data.CachedChannel.includes(channel[i])) {
        newQueryChannel.push(channel[i])
      }
    }

    setAlert(<LoadingProgress />)
    if (!channel || newQueryChannel.length > 0) {
      try {
        const response = await SessionController.query("/api/queryTherapeuticEffectAnalysis", {
          RequestType: "RequestData",
          ParticipantId: participant_uid,
          AnalysisId: analysis.Id,
          ActiveChannels: newQueryChannel
        });

        setTherapyLabel((currentLabel) => {
          let newOptions = ["Default"];
          for (let i in response.data.Therapy) {
            for (let j in response.data.Therapy[i].TherapySeries) {
              for (let name in response.data.Therapy[i].TherapySeries[j].TherapyOverview) {
                if (!newOptions.includes(name)) {
                  newOptions.push(name);
                }
              }
            }
          }
          if (newOptions.length === currentLabel.options.length) {
            for (let i in newOptions) {
              if (!currentLabel.options.includes(newOptions[i])) {
                return {active: newOptions.includes(currentLabel.active) ? currentLabel.active : newOptions[0], options: newOptions};
              }
            }
            return currentLabel;
          } else {
            return {active: newOptions.includes(currentLabel.active) ? currentLabel.active : newOptions[0], options: newOptions};
          }
        })

        if (!channel) {
          setAnnotations(response.data.Annotations);
          setData({...response.data, CachedChannel: response.data.ActiveChannel, Analysis: analysis});
          setChannel({active: response.data.ActiveChannel, options: response.data.AllChannels})
        } else {
          setData((data) => {
            data.CachedChannel.push(...newQueryChannel);
            data.ActiveChannel = channel;
            data.Signal.push(...response.data.Signal);
            setChannel((oldChannel) => {
              oldChannel.active = channel;
              return {...oldChannel}
            });
            setAnnotations((annotations) => {
              annotations.push(...response.data.Annotations);
              return [...new Set(annotations)];
            });
            return {...data};
          });
        }
        setAlert(null);
      } catch (error) {
        SessionController.displayError(error, setAlert);
      }
    } else {
      setChannel((oldChannel) => {
        oldChannel.active = channel;
        return {...oldChannel}
      });
      setAlert(null);
    }
  };

  const updateRecordingData = async (analysisUpdate) => {
    setAlert(<LoadingProgress />)
    try {
      const response = await SessionController.query("/api/queryTherapeuticEffectAnalysis", {
        RequestType: "UpdateData",
        ParticipantId: participant_uid,
        AnalysisId: analysisUpdate.analysisId,
        RecordingName: analysisUpdate.name,
        StimulationLabel: analysisUpdate.therapy.map((a) => a.SegmentMode ? a.SegmentMode : "Ring")
      });
      
      setAvailableAnalysis((availableAnalysis) => {
        for (let i in availableAnalysis.Analyses) { 
          if (availableAnalysis.Analyses[i].Id == analysisUpdate.analysisId) {
            availableAnalysis.Analyses[i].Name = analysisUpdate.name;
            for (let j in availableAnalysis.Recordings) {
              if (availableAnalysis.Analyses[i].DataId.includes(availableAnalysis.Recordings[j].Id) && availableAnalysis.Recordings[j].Metadata.Therapy) {
                availableAnalysis.Recordings[j].Metadata.Therapy = analysisUpdate.therapy;
                availableAnalysis.Recordings[j].Name = analysisUpdate.name;
                break;
              }
            }
            break;
          }
        }
        return {...availableAnalysis};
      });
      setAlert(null);
    } catch (error) {
      SessionController.displayError(error, setAlert);
    }
  };

  const handleRequestServerAnalysis = async () => {
    
  }
  
  const addNewAnalysis = (newGroupView) => {
    setAlert(<LoadingProgress />)
    SessionController.query("/api/queryTherapeuticEffectAnalysis", {
      RequestType: "AddNewAnalysis",
      ParticipantId: participant_uid,
      TherapyIds: newGroupView.therapies.map((a) => a.Id),
      RecordingIds: newGroupView.timeseries.map((a) => a.Id)
    }).then((response) => {
      setAvailableAnalysis({...availableAnalysis, Analyses: [...availableAnalysis.Analyses, response.data]});
      setAlert(null);
    }).catch((error) => {
      SessionController.displayError(error, setAlert);
    });
  };

  const deleteAnalysis = (analysisId) => {
    setAlert(<LoadingProgress />)
    SessionController.query("/api/queryTherapeuticEffectAnalysis", {
      RequestType: "DeleteAnalysis",
      ParticipantId: participant_uid,
      AnalysisId: analysisId,
    }).then((response) => {
      setAvailableAnalysis({...availableAnalysis, Analyses: [...availableAnalysis.Analyses.filter((a) => a.Id != analysisId)]});
      setAlert(null);
    }).catch((error) => {
      SessionController.displayError(error, setAlert);
    });
  };

  const toggleCardiacFilter = () => {
    
  };

  const toggleWaveletTransform = () => {
    
  };

  const handlePSDUpdate = (reference, side) => {
    
  }

  const exportCurrentStream = () => {
    let downloader = document.createElement('a');
    downloader.href = SessionController.getDownloadLink("/api/downloadData", {
      ParticipantId: participant_uid,
      CacheType: "queryTherapeuticEffectAnalysis",
      AnalysisId: data.Analysis.Id
    });
    downloader.target = '_blank';
    downloader.click();
  };

  const adaptiveClosedLoopParameters = (therapy) => {
    
  }

  const handleAddEvent = async (eventInfo) => {
    setAlert(<LoadingProgress />);
    try {
      const response = await SessionController.query("/api/addParticipantAnnotation", {
        ParticipantId: participant_uid,
        EventName: eventInfo.name,
        EventTime: eventInfo.time / 1000,
        EventDuration: parseFloat(eventInfo.duration),
        EventType: "RecordingCustomEvent"
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
      eventInfo.targetInfo.timeDiff = 10;
    }

    for (let i = 0; i < annotations.length; i++) {
      let absoluteDiffTime = Math.abs(annotations[i].Date - eventInfo.time/1000);
      if (absoluteDiffTime < eventInfo.targetInfo.timeDiff) {
        eventInfo.targetInfo = annotations[i];
        eventInfo.targetInfo.timeDiff = absoluteDiffTime;
      }
    }
    
    if (eventInfo.targetInfo.timeDiff < 10) {
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

  const handleAdjustAlignment = async (alignment, eventInfo) => {
    setAlert(<LoadingProgress />)
    const Alignment = parseFloat(alignment.alignment)/1000;
    try {
      const response = await SessionController.query("/api/setRecordingTimeShift", {
        ParticipantId: participant_uid,
        RequestType: "Analysis",
        AnalysisId: data.Analysis.Id,
        RecordingId: eventInfo.channel,
        Alignment: Alignment
      })
      setAlert(null);
      
      if (response.status == 200) {
        setData((data) => {
          for (let i in data.Signal) {
            if (data.Signal[i].RecordingId == eventInfo.channel) {
              data.Signal[i].Alignment = Alignment
            }
          }
          for (let i in data.Therapy) {
            if (data.Therapy[i].RecordingId == eventInfo.channel) {
              data.Therapy[i].Alignment = Alignment
            }
          }
          return {...data};
        });
      }
      return response
    } catch (error) {
      SessionController.displayError(error, setAlert);
    }
  }

  return (
    <DatabaseLayout>
      {alert}
      <MDBox pt={3}>
        <MDBox>
          <Grid container spacing={2}>
            <Grid item xs={12}>
              <Card sx={{width: "100%"}}>
                <Grid container>
                  <Grid item xs={12}>
                    <MDBox p={2} lineHeight={1}>
                      {availableAnalysis.Analyses.length > 0 ? (
                        <TherapeuticAnalysisTable data={availableAnalysis.Analyses} recordings={availableAnalysis.Recordings} getRecordingData={getRecordingData} updateRecordingData={updateRecordingData}
                          addNewAnalysis={addNewAnalysis} deleteAnalysis={deleteAnalysis}
                        />
                      ) : (
                        <MDTypography variant="h6" fontSize={24}>
                          {dictionary.WarningMessage.NoData[language]}
                        </MDTypography>
                      )}
                    </MDBox>
                  </Grid>
                </Grid>
              </Card>
            </Grid>
            {data ? (
              <Grid item xs={12}>
                <Card sx={{width: "100%"}}>
                  <Grid container>
                    <Grid item xs={12}>
                      <MDBox display={"flex"} justifyContent={"space-between"} p={3}>
                        <MDBox display={"flex"} flexDirection={"column"}>
                          <MDTypography variant="h5" fontWeight={"bold"} fontSize={24}>
                            {"Therapeutic Effect Analysis"}
                          </MDTypography>
                        </MDBox>
                        <MDBox display={"flex"} flexDirection={"column"}>
                          <MDButton size="large" variant="contained" color="primary" style={{marginBottom: 3}} onClick={() => exportCurrentStream()}>
                            {dictionaryLookup(dictionary.FigureStandardText, "Export", language)}
                          </MDButton>
                        </MDBox>
                      </MDBox>
                    </Grid>
                    <Grid item xs={12}>
                      <MDBox px={3} pb={3} pt={0}>
                        <Autocomplete
                          multiple
                          value={channel.active}
                          options={channel.options}
                          onChange={(event, value) => {
                            getRecordingData(data.Analysis, value);
                          }}
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
                      <TimeFrequencyAnalysis dataToRender={data} activeChannels={channel.active} annotations={annotations}
                        handleAddEvent={handleAddEvent} handleDeleteEvent={handleDeleteEvent} handleAdjustAlignment={handleAdjustAlignment} 
                        figureTitle={"TimeFrequencyAnalysis"} height={700}/>
                    </Grid>
                  </Grid>
                </Card>
              </Grid>
            ) : null}
            {data ? (
              <Grid item xs={12}>
                <Card>
                  <Grid container>
                    <Grid item xs={12}>
                      <MDBox display={"flex"} flexDirection={"column"}>
                        <StimulationPSD dataToRender={data} activeChannels={channel.active} onRequestServerAnalysis={handleRequestServerAnalysis} figureTitle={"StimulationPSDs"} />
                      </MDBox>
                    </Grid>
                  </Grid>
                </Card>
              </Grid>
            ) : null}
          </Grid>
          <ConfigurationDialog show={drawerOpen.open} setShow={(state) => setDrawerOpen({open: false})} setAlert={setAlert} />
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
                key={"ChangeSettings"}
                icon={<SettingsIcon sx={{display: "flex", justifyContent: "center", alignItems: "center", fontSize: 30}}/>}
                tooltipTitle={"Edit Processing Configurations"}
                onClick={() => setDrawerOpen({...drawerOpen, open: true})}
              />
            </SpeedDial>
          </MDBox>
        </MDBox>
      </MDBox>
    </DatabaseLayout>
  );
}

export default TherapeuticEffects;
