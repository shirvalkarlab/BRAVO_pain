/**
=========================================================
* UF BRAVO Platform
=========================================================

* Copyright 2025 by Jackson Cagle, Fixel Institute
* The source code is made available under a Creative Common NonCommercial ShareAlike License (CC BY-NC-SA 4.0) (https://creativecommons.org/licenses/by-nc-sa/4.0/) 

 =========================================================

* The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.
*/

import { useEffect, useState, memo } from "react";

import {
  Autocomplete,
  Card,
  Chip,
  Checkbox,
  Grid,
  Dialog,
  DialogContent,
  DialogActions,
  Divider,
  IconButton,
  Icon,
  Tabs,
  Tab,
  TextField,
  Table,
  TableHead,
  TableBody,
  TableCell,
  TableRow
} from "@mui/material";
import { createFilterOptions } from '@mui/material/Autocomplete';

import { AdapterMoment } from '@mui/x-date-pickers/AdapterMoment';
import { LocalizationProvider } from '@mui/x-date-pickers/LocalizationProvider';
import { DatePicker } from '@mui/x-date-pickers/DatePicker';

import FormField from "components/MDInput/FormField.js";
import MuiAlertDialog from "components/MuiAlertDialog";
import MDBox from "components/MDBox";
import MDTypography from "components/MDTypography";
import MDInput from "components/MDInput";
import MDButton from "components/MDButton";

import DatabaseLayout from "layouts/DatabaseLayout";

import { SessionController } from "database/session-control";
import { usePlatformContext, setContextState } from "context";

const filter = createFilterOptions();

export default function StudyManagement() {
  const [controller, dispatch] = usePlatformContext();
  const { user, language } = controller;

  const [alert, setAlert] = useState(null);
  const [availableStudies, setAvailableStudies] = useState([]);
  const [availableParticipants, setAvailableParticipants] = useState([]);
  const [activeStudy, setActiveStudy] = useState({Participants: []});
  const [activeParticipant, setActiveParticipant] = useState({});
  const [studyInformation, setStudyInformation] = useState({});
  const [participantInformation, setParticipantInformation] = useState({});
  const [uploadDataType, setUploadDataType] = useState("");
  
  useEffect(() => {
    SessionController.query("/api/queryParticipants", {
      ParticipantGroupId: user.InstituteId
    }).then((response) => {
      setAvailableParticipants(response.data);
    }).catch((error) => {
      SessionController.displayError(error, setAlert);
    });

    SessionController.query("/api/manageStudyInformation", {
      RequestType: "GetStudies"
    }).then((response) => {
      setAvailableStudies(response.data);
      if (response.data.length == 0) {
        setStudyInformation({
          name: "", 
        })
        setActiveStudy({value: "create", label: "Create New Study"});
      } else {
        setActiveStudy({...response.data[0], value: response.data[0].Id, label: response.data[0].Name});
      }
    }).catch((error) => {
      SessionController.displayError(error, setAlert);
    });
  }, []);

  const handleCreateStudy = () => {
    if (!studyInformation.name) {
      SessionController.displayError("Name is required.", setAlert);
      return;
    }

    SessionController.query("/api/manageStudyInformation", {
      RequestType: "CreateStudy",
      StudyName: studyInformation.name,
    }).then((response) => {
      setAvailableStudies((availableStudies) => [...availableStudies, response.data]);
      setActiveStudy({
        ...response.data,
        value: response.data.Id, label: response.data.Name
      });
    }).catch((error) => {
      SessionController.displayError(error, setAlert);
    });
  };

  const handleLeaveStudy = (id) => {
    SessionController.query("/api/manageStudyInformation", {
      RequestType: "LeaveStudy",
      StudyId: id,
    }).then((response) => {
      setAvailableStudies((availableStudies) => {
        availableStudies = availableStudies.filter((a) => a.Id != id);
        if (availableStudies.length == 0) {
          setStudyInformation({
            name: "", 
          })
          setActiveStudy({value: "create", label: "Create New Study"});
        } else {
          setActiveStudy({...availableStudies[0], value: availableStudies[0].Id, label: availableStudies[0].Name});
        }
        return [...availableStudies];
      });
    }).catch((error) => {
      SessionController.displayError(error, setAlert);
    });
  };

  const handleAddParticipant = (id, participant_uid) => {
    SessionController.query("/api/manageStudyInformation", {
      RequestType: "AddParticipant",
      StudyId: id,
      ParticipantId: participant_uid,
    }).then((response) => {
      
    }).catch((error) => {
      SessionController.displayError(error, setAlert);
    });
  };

  const handleRemoveParticipant = (id, participant_uid) => {
    SessionController.query("/api/manageStudyInformation", {
      RequestType: "RemoveParticipant",
      StudyId: id,
      ParticipantId: participant_uid,
    }).then((response) => {
      
    }).catch((error) => {
      SessionController.displayError(error, setAlert);
    });
  };

  return (
    <DatabaseLayout>
      <MDBox pt={5}>
        <Card>
          {alert}
          <MDBox p={2}>
            <Grid container spacing={2}>
              <Grid item xs={12}>
                <MDTypography variant="h3">
                  {"Study Manager"}
                </MDTypography>
                <MDTypography variant="h6">
                  {"Current Active Institute: " + user.Institute}
                </MDTypography>
              </Grid>
              <Grid item sm={12}>
                <Autocomplete 
                  disableClearable
                  options={[{value: "create", label: "Create New Study"},
                    ...availableStudies.map((study) => ({...study, value: study.Id, label: study.Name})).sort((a,b) => a.label.localeCompare(b.label))]} 
                  value={activeStudy}
                  onChange={(event, newValue) => {
                    if (newValue.value == "create") {
                      setStudyInformation({
                        name: "", 
                      })
                    }
                    setActiveStudy(newValue);
                  }}
                  getOptionLabel={(option) => {
                    if (typeof option === 'string') { return option; }
                    if (option.inputValue) { return option.label; }
                    if (!option.label) { return "Not Available" }
                    return option.label;
                  }}
                  isOptionEqualToValue={(option, value) => option.value == value.value}
                  renderOption={(props, option) => {
                    const { key, ...optionProps } = props;
                    return (
                      <MDBox key={key} component="li" sx={{ '& > img': { mr: 2, flexShrink: 0 } }} {...optionProps} >
                        {option.value === "batch-upload" || option.value === "create" ? (
                          <MDTypography variant="button" fontWeight="bold">
                            {option.label}
                          </MDTypography>
                        ) : (
                          <MDBox>
                            {option.label}
                          </MDBox>
                        )}
                      </MDBox>
                    );
                  }}
                  renderInput={(params) => (
                    <FormField {...params} label={"Available Studies"} InputLabelProps={{ shrink: true }} fullWidth />
                  )}
                />
              </Grid>
              {activeStudy.value == "create" ? (
                <Grid item sm={12}>
                  <Divider variant="insert" />
                  <MDTypography variant="h5">
                    {"Create New Study"}
                  </MDTypography>
                  <Grid container spacing={2}>
                    <Grid item xs={12}>
                      <TextField
                        variant="standard" margin="dense" id="study-name"
                        value={studyInformation.name}
                        onChange={(event) => setStudyInformation({...studyInformation, name: event.target.value})}
                        label={"Study Name (Required)"} type="text"
                        fullWidth
                      />
                    </Grid>
                    <Grid item xs={12} style={{marginTop: "auto"}}>
                      <MDButton variant={"contained"} color={"success"} style={{marginLeft: "auto"}} onClick={handleCreateStudy}>
                        {"Create Study"}
                      </MDButton>
                    </Grid>
                  </Grid>
                </Grid>
              ) : (
                <Grid item sm={12}>
                  <Grid container spacing={2}>
                    <Grid item sm={12}>
                      <MDTypography variant="h5">
                        {"Current Study Participant"}
                      </MDTypography>
                    </Grid>
                    <Grid item sm={12}>
                      <Autocomplete 
                        disableClearable
                        options={availableParticipants.map((participant) => ({...participant, value: participant.Id, label: participant.Name})).sort((a,b) => a.label.localeCompare(b.label))} 
                        value={activeParticipant}
                        onChange={(event, newValue) => {
                          setActiveStudy((activeStudy) => {
                            if (activeStudy.Participants.filter((a)=>a.Id == newValue.Id).length == 0) {
                              activeStudy.Participants.push({
                                Id: newValue.Id, Name: newValue.Name
                              });
                              handleAddParticipant(activeStudy.Id, newValue.Id);
                            }
                            return {...activeStudy};
                          });
                          setActiveParticipant(newValue);
                        }}
                        getOptionLabel={(option) => {
                          if (typeof option === 'string') { return option; }
                          if (option.inputValue) { return option.label; }
                          if (!option.label) { return "Not Available" }
                          return option.label;
                        }}
                        isOptionEqualToValue={(option, value) => option.value == value.value}
                        renderOption={(props, option) => {
                          const { key, ...optionProps } = props;
                          return (
                            <MDBox key={key} component="li" sx={{ '& > img': { mr: 2, flexShrink: 0 } }} {...optionProps} >
                              {option.value === "batch-upload" || option.value === "create" ? (
                                <MDTypography variant="button" fontWeight="bold">
                                  {option.label}
                                </MDTypography>
                              ) : (
                                <MDBox>
                                  {option.label}
                                </MDBox>
                              )}
                            </MDBox>
                          );
                        }}
                        renderInput={(params) => (
                          <FormField {...params} label={"Add Participant In Study"} InputLabelProps={{ shrink: true }} fullWidth />
                        )}
                      />
                    </Grid>
                    <Grid item sm={12}>
                      {activeStudy.Participants.map((a, i) => {
                        return <MDBox key={a.Id}>
                          <MDTypography variant="p">
                            {(i+1).toFixed(0)}{": "}{a.Name}
                          </MDTypography>
                          <IconButton size="small" aria-label="close" color="inherit" onClick={() => {
                            setActiveStudy((activeStudy) => {
                              activeStudy.Participants = activeStudy.Participants.filter((b) => b.Id != a.Id);
                              handleRemoveParticipant(activeStudy.Id, a.Id);
                              return {...activeStudy};
                            });
                          }}>
                            <Icon fontSize="small">close</Icon>
                          </IconButton>
                        </MDBox>
                      })}
                    </Grid>
                    <Grid item xs={12} style={{marginTop: "auto"}}>
                      <MDButton variant={"contained"} color={"error"} style={{marginLeft: "auto"}} onClick={() => handleLeaveStudy(activeStudy.Id)}>
                        {"Leave Study"}
                      </MDButton>
                    </Grid>
                  </Grid>
                </Grid>
              )}

            </Grid>
          </MDBox>
        </Card>
      </MDBox>
    </DatabaseLayout>
  );
}
