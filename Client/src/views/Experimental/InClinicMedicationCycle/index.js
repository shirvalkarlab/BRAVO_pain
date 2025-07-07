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
  Dashboard as DashboardIcon,
  Cached as CachedIcon
} from "@mui/icons-material";

// core components
import MDBox from "components/MDBox";
import MDTypography from "components/MDTypography";
import MDButton from "components/MDButton";
import LoadingProgress from "components/LoadingProgress";
import MuiAlertDialog from "components/MuiAlertDialog";
import FormField from "components/MDInput/FormField";

import DatabaseLayout from "layouts/DatabaseLayout";
import ConfigurationDialog from "components/ConfigurationDialog";
import SnapshotPSDs from "./SnapshotPSDs";
import ChronicSnapshots from "./ChronicSnapshots";
import PowerBandBoxplot from "./PowerBandBoxplot";

import { SessionController } from "database/session-control";
import { usePlatformContext, setContextState } from "context.js";
import { dictionary, dictionaryLookup } from "assets/translation.js";

function InClinicMedicationCycle() {
  const navigate = useNavigate();
  const [controller, dispatch] = usePlatformContext();
  const { TherapeuticEffectLayout, language } = controller;
  const { participant_uid } = useParams();

  const [availableDates, setAvailableDates] = useState({Dates: [], Active: ""});
  const [powerbands, setPowerbands] = useState({});

  const [viewChronicChannel, setViewChronicChannel] = useState({active: "", options: []});

  const [snapshot, setSnapshot] = useState([]);
  const [chronicSnapshot, setChronicSnapshot] = useState([]);

  const [drawerOpen, setDrawerOpen] = useState({open: false, config: {}});
  const [channel, setChannel] = useState({active: "", options: []});

  const [alert, setAlert] = useState(null);

  useEffect(() => {
    if (!participant_uid) {
      navigate("/dashboard", {replace: false});
      return;
    }
    setContextState(dispatch, "report", "CustomizedAnalysis");

    setAlert(<LoadingProgress/>);
    SessionController.query("/api/queryMedicationCycleAnalysis", {
      RequestType: "RequestAll",
      ParticipantId: participant_uid
    }).then((response) => {
      console.log(response.data)
      setAvailableDates(() => {
        let uniqueDates = [];
        for (let i in response.data.Recordings) {
          const dateString = new Date(response.data.Recordings[i].Date*1000).toLocaleString("en-US", {...SessionController.getTimezoneName(response.data.Recordings[i].Timezone),
            year: "numeric",
            month: "2-digit",
            day: "2-digit",
            timeZoneName: "longGeneric"
          })
          response.data.Recordings[i].DateString = dateString;
          if (!uniqueDates.map((a) => a.dateString).includes(dateString)) uniqueDates.push({value: response.data.Recordings[i].Date, dateString});
        }
        uniqueDates = uniqueDates.sort((a,b) => b.value-a.value).map((a) => a.dateString);

        const findCommonItem = (arr1, arr2) => {
          const result = [];
          for (const el1 of arr1) {
            if (arr2.includes(el1)) {
              result.push(el1);
            }
          }
          return result;
        }

        return {Dates: uniqueDates, Recordings: response.data.Recordings, Active: uniqueDates.length > 0 ? uniqueDates[0] : ""};
      });
      setAlert(null);
    }).catch((error) => {
      SessionController.displayError(error, setAlert);
    });
    
  }, [participant_uid]);

  useEffect(() => {
    if (!availableDates.Active) return;
    
    setAlert(<LoadingProgress/>);
    SessionController.query("/api/queryMedicationCycleAnalysis", {
      RequestType: "RequestAnalysis",
      ParticipantId: participant_uid,
      RecordingIds: availableDates.Recordings.filter((a) => a.DateString == availableDates.Active).map((a) => a.Id)
    }).then((response) => {
      setPowerbands(response.data.PowerBands)
      setAlert(null);
    }).catch((error) => {
      SessionController.displayError(error, setAlert);
    });
  }, [availableDates.Active])

  const onCenterFrequencyChange = (side, freq) => {
    
  };

  const toggleCardiacFilter = () => {
    
  };

  const toggleWaveletTransform = () => {
    
  };

  const handlePSDUpdate = (reference, side) => {
    
  }

  const exportCurrentStream = () => {
    
  };

  const adaptiveClosedLoopParameters = (therapy) => {
    
  }

  return (
    <DatabaseLayout>
      {alert}
      <MDBox pt={3}>
        <MDBox>
          <Grid container spacing={2}>
            <Grid item xs={12}>
              <Card sx={{width: "100%"}}>
                {availableDates.Dates.length > 0 ? (
                <Grid container>
                  <Grid item xs={12}>
                    <MDBox p={2} lineHeight={1}>
                        <Autocomplete
                          value={availableDates.Active}
                          options={availableDates.Dates}
                          onChange={(event, value) => setAvailableDates({...availableDates, Active: value})}
                          renderInput={(params) => (
                            <FormField
                              {...params}
                              label={dictionary.TherapeuticAnalysis.Table.TableTitle[language]}
                              InputLabelProps={{ shrink: true }}
                            />
                          )}
                        />
                    </MDBox>
                  </Grid>
                  <Grid item xs={12}>
                    <PowerBandBoxplot dataToRender={powerbands} figureTitle={"Power Band Boxplot"} />
                  </Grid>
                </Grid>
                ) : (
                  <MDBox p={2} lineHeight={1}>
                    <MDTypography variant="h6" fontSize={24}>
                      {dictionary.WarningMessage.NoData[language]}
                    </MDTypography>
                  </MDBox>
                )}
              </Card>
            </Grid>
          </Grid>

          <ConfigurationDialog show={drawerOpen.open} setShow={(state) => setDrawerOpen({open: state})} setAlert={setAlert} />
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

export default InClinicMedicationCycle;
