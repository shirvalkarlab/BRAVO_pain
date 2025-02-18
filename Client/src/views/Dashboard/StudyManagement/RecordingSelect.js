/**
=========================================================
* UF BRAVO Platform
=========================================================

* Copyright 2025 by Jackson Cagle, Fixel Institute
* The source code is made available under a Creative Common NonCommercial ShareAlike License (CC BY-NC-SA 4.0) (https://creativecommons.org/licenses/by-nc-sa/4.0/) 

 =========================================================

* The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.
*/

import { useEffect, useState, useCallback, useMemo } from "react";
import { useNavigate, useParams } from "react-router-dom";

import {
  Autocomplete,
  Dialog,
  DialogContent,
  TextField,
  Card,
  Icon,
  Drawer,
  SpeedDial,
  SpeedDialAction,
  SpeedDialIcon,
  Grid,
  ListItem,
  ListItemButton,
  ListItemIcon,
  ListItemText,
  Checkbox,
  IconButton,
  InputLabel,
  Input,
} from "@mui/material"

import LoadingProgress from "components/LoadingProgress";
import MDBox from "components/MDBox";
import MDTypography from "components/MDTypography";
import MDButton from "components/MDButton";
import MuiAlertDialog from "components/MuiAlertDialog";

import { IoMdCheckmarkCircle } from "react-icons/io";

import { SessionController } from "database/session-control";
import { select } from "react-cookies";

function RecordingSelect({participant, onClose, onSelectRecording, setAlert}) {

  const [surveys, setSurveys] = useState([]);
  const [recordings, setRecordings] = useState([]);
  const [selectedRecording, setSelectedRecording] = useState([]);
  const [recordingType, setRecordingType] = useState({active: "", options: []});
  const [recordingDate, setRecordingDate] = useState({active: "", options: []});
  const [availableRecordings, setAvailableRecordings] = useState([]);

  useEffect(() => {
    setAlert(<LoadingProgress/>);
    SessionController.query("/api/manageStudyInformation", {
      RequestType: "RequestRecordingList",
      ParticipantId: participant.Id,
    }).then((response) => {
      setSurveys(response.data.Surveys);
      setRecordings(response.data.Recordings);
      setSelectedRecording(() => {
        let selectedRecording = [];
        if (participant.Permissions.Recordings) {
          selectedRecording.push(...participant.Permissions.Recordings)
        }
        if (participant.Permissions.Surveys) {
          selectedRecording.push(...participant.Permissions.Surveys)
        }
        return selectedRecording;
      });
      setAlert(null);
    }).catch((error) => {
      SessionController.displayError(error, setAlert);
    });
  }, [participant]);

  useEffect(() => {
    setRecordingType(() => {
      let recordingTypes = [];
      for (let i in recordings) {
        if (!recordingTypes.includes(recordings[i].Type)) {
          recordingTypes.push(recordings[i].Type);
        }
      }
      for (let i in surveys) {
        if (!recordingTypes.includes(surveys[i].FormName)) {
          recordingTypes.push(surveys[i].FormName);
        }
      }
      if (recordingTypes.length > 0) return {active: recordingTypes[0], options: recordingTypes};
      return {active: "", options: []};
    });
  }, [recordings]);

  useEffect(() => {
    setRecordingDate(() => {
      let recordingDates = [];
      const recordingsSorted = recordings.sort((a,b) => a.Date - b.Date);
      for (let i in recordingsSorted) {
        if (recordingsSorted[i].Type == recordingType.active) {
          const dateString = new Date(recordingsSorted[i].Date*1000).toLocaleString("en-US", {...SessionController.getTimezoneName(recordingsSorted[i].Timezone),
            year: "numeric",
            month: "2-digit",
            day: "2-digit",
            timeZoneName: "longGeneric"
          })
          
          if (recordingsSorted[i].Type !== "Timeline") {
            if (!recordingDates.includes(dateString)) {
              recordingDates.push(dateString);
            }
          }
        }
      }
      if (recordingDates.length > 0) return {active: recordingDates[0], options: recordingDates};
      return {active: "", options: []};
    });
  }, [recordingType.active])

  useEffect(() => {
    setAvailableRecordings(() => {
      let availableRecordings = [];
      for (let i in recordings) {
        if (recordings[i].Type == recordingType.active) {
          const dateString = new Date(recordings[i].Date*1000).toLocaleString("en-US", {...SessionController.getTimezoneName(recordings[i].Timezone),
            year: "numeric",
            month: "2-digit",
            day: "2-digit",
            timeZoneName: "longGeneric"
          })
          
          if (recordings[i].Type === "Timeline") {
            availableRecordings.push({...recordings[i],
              Name: recordings[i].Metadata.ChannelNames[0],
            });
          } else if (recordingDate.active == dateString) {
            availableRecordings.push(recordings[i]);
          }
        }
      }
      for (let i in surveys) {
        if (surveys[i].FormName == recordingType.active) {
          const dateString = new Date(surveys[i].Date*1000).toLocaleString("en-US", {...SessionController.getTimezoneName(""),
            year: "numeric",
            month: "2-digit",
            day: "2-digit",
            timeZoneName: "longGeneric"
          })

          availableRecordings.push({...surveys[i],
            Name: dateString,
            Metadata: {
              Duration: 0
            }
          });
        }
      }
      return availableRecordings;
    });
  }, [recordingType.active, recordingDate.active])

  return (
    <DialogContent>
      <MDBox px={2} pt={2}>
        <MDTypography variant="h5">
          {"Add Recordings to Analysis"}
        </MDTypography>
      </MDBox>
      
      <MDBox px={2} pt={2}>
        <Autocomplete selectOnFocus clearOnBlur disableClearable
          renderInput={(params) => (
            <TextField {...params} variant="standard" label={"Select Recording Type"}/>
          )}
          isOptionEqualToValue={(option, value) => {
            return option === value;
          }}
          renderOption={(props, option) => <li {...props}>{option}</li>}
          value={recordingType.active}
          options={recordingType.options}
          onChange={(event, newValue) => setRecordingType({...recordingType, active: newValue})}
        />
      </MDBox>
      
      <MDBox px={2} pt={2}>
        <Autocomplete selectOnFocus clearOnBlur disableClearable
          renderInput={(params) => (
            <TextField {...params} variant="standard" label={"Select Recording Date"}/>
          )}
          isOptionEqualToValue={(option, value) => {
            return option === value;
          }}
          renderOption={(props, option) => <li {...props}>{option}</li>}
          value={recordingDate.active}
          options={recordingDate.options}
          onChange={(event, newValue) => setRecordingDate({...recordingDate, active: newValue})}
        />
      </MDBox>

      <MDBox px={2} pt={2}>
        <MDButton color={"info"} 
          onClick={() => setSelectedRecording((selectedRecording) => {
            let nonSelectedRecordings = [];
            for (let i in availableRecordings) {
              if (!selectedRecording.includes(availableRecordings[i].Id)) {
                nonSelectedRecordings.push(availableRecordings[i].Id);
              }
            }

            if (nonSelectedRecordings.length > 0) {
              selectedRecording.push(...nonSelectedRecordings);
            } else {
              const allIds = availableRecordings.map((a) => a.Id);
              selectedRecording = selectedRecording.filter((a) => !allIds.includes(a));
            }
            return [...selectedRecording];

          })} style={{marginLeft: 10}}
        >
          {"Toggle All"}
        </MDButton>
      </MDBox>
      
      <MDBox px={2} pt={2}>
        <Grid container spacing={1}>
          {availableRecordings.map((a) => (
            <Grid item key={a.Id} xs={6} sm={4} md={3}>
              <Card style={selectedRecording.includes(a.Id) ? {background: "#4caf50", cursor: "pointer"} : {cursor: "pointer"}} onClick={() => {
                setSelectedRecording((selectedRecording) => {
                  if (selectedRecording.includes(a.Id)) {
                    selectedRecording = selectedRecording.filter((b) => b != a.Id);
                  } else {
                    selectedRecording.push(a.Id);
                  }
                  return [...selectedRecording];
                })
              }}>
                {selectedRecording.includes(a.Id) ? (
                  <IoMdCheckmarkCircle color={"#357a38"} style={{position: "absolute", transform: "translate(-50%, -50%)", borderRadius: "50%"}} />
                ) : null}
                <MDBox p={2}>
                  <MDTypography variant={"h5"} fontWeight={"bold"}>
                    {a.Name.length > 0 ? a.Name : a.Id}
                  </MDTypography>
                  {a.Type === "Timeline" ? (
                    <MDTypography variant={"p"} fontSize={15}>
                      {"Session Date: "}{new Date(a.Date*1000).toLocaleString("en-US", {...SessionController.getTimezoneName(a.Timezone),
                        year: "numeric",
                        month: "2-digit",
                        day: "2-digit",
                      })}
                    </MDTypography>
                  ) : (
                    <MDTypography variant={"p"} fontSize={15}>
                      {new Date(a.Date*1000).toLocaleString("en-US", {...SessionController.getTimezoneName(a.Timezone),
                        hour: "numeric",
                        minute: "2-digit",
                        second: "2-digit",
                      })} {"-"} 
                      {new Date(a.Date*1000 + a.Metadata.Duration*1000).toLocaleString("en-US", {...SessionController.getTimezoneName(a.Timezone),
                        hour: "numeric",
                        minute: "2-digit",
                        second: "2-digit",
                      })}
                    </MDTypography>
                  )}
                </MDBox>
              </Card>
            </Grid>
          ))}
        </Grid>
      </MDBox>
      <MDBox p={2}>
        <MDButton color={"secondary"} 
          onClick={onClose}
        >
          Cancel
        </MDButton>
        <MDButton color={"info"} 
          onClick={() => {
            const RecordingList = recordings.filter((a) => selectedRecording.includes(a.Id));
            const SurveyList = surveys.filter((a) => selectedRecording.includes(a.Id));
            onSelectRecording({
              Recordings: RecordingList.map((a) => a.Id),
              Surveys: SurveyList.map((a) => a.Id)
            });
            onClose();
          }} style={{marginLeft: 10}}
        >
          Update
        </MDButton>
      </MDBox>
    </DialogContent>
  )
}

export default RecordingSelect;