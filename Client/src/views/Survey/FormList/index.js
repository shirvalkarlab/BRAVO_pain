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
import { useNavigate } from "react-router-dom";

import {
  Autocomplete,
  Card,
  Grid,
  Dialog,
  DialogContent,
  DialogActions,
  TextField,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Tooltip,
  Chip,
} from "@mui/material";

import { FilePond } from 'react-filepond';
import 'filepond/dist/filepond.min.css';

import MDBox from "components/MDBox";
import MDTypography from "components/MDTypography";
import MDInput from "components/MDInput";
import MDButton from "components/MDButton";
import MuiAlertDialog from "components/MuiAlertDialog";
import FormField from "components/MDInput/FormField";

import LoadingProgress from "components/LoadingProgress";

import DatabaseLayout from "layouts/DatabaseLayout";
import FormTable from "./FormTable";

import { SessionController } from "database/session-control";
import { usePlatformContext, setContextState } from "context";
import { dictionary, dictionaryLookup } from "assets/translation";

export default function FormList() {
  const [controller, dispatch] = usePlatformContext();
  const { user, language } = controller;
  const navigate = useNavigate();

  const [filteredPatients, setFilteredPatients] = useState([]);
  const [filterOptions, setFilterOptions] = useState({});
  const [surveys, setSurveys] = useState([]);
  const [schedules, setSchedules] = useState([]);
  const [newSurveyDialog, setNewSurveyDialog] = useState({surveyName: "", surveyType: "", state: false});
  const [csvImportDialog, setCsvImportDialog] = useState({participant: null, files: [], state: false});
  const [availableParticipants, setAvailableParticipants] = useState([]);
  const [scheduleSurveyLinkDialog, setScheduleSurveyLinkDialog] = useState({activeStep: 0, verified: false, surveyId: "", redcapServer: "", redcapToken: "", redcapSurveyName: "", patientId: "", accountId: "", authToken: "", serviceId: "", frequency: {repeat: "daily", timestamps: []}, receiver: {type: "mobile", value: ""}, messageFormat: "", state: false});
  const [alert, setAlert] = useState(null);

  useEffect(() => {
    SessionController.query("/api/querySurveyForms", {
      RequestType: "RequestAll"
    }).then((response) => {
      setSurveys(response.data);
    }).catch((error) => {
      SessionController.displayError(error, setAlert);
    });
  }, []);

  const [availabilityMatrix, setAvailabilityMatrix] = useState({Instruments: [], Participants: []});

  useEffect(() => {
    if (!user || !user.InstituteId) return;
    SessionController.query("/api/queryParticipants", {
      ParticipantGroupId: user.InstituteId
    }).then((response) => {
      setAvailableParticipants(response.data);
    }).catch(() => {
      // non-fatal: the CSV-import participant picker simply has no options
    });
  }, [user]);

  const loadAvailabilityMatrix = () => {
    SessionController.query("/api/querySurveyForms", {
      RequestType: "RequestAvailabilityMatrix"
    }).then((response) => {
      setAvailabilityMatrix(response.data);
    }).catch((error) => {
      SessionController.displayError(error, setAlert);
    });
  };

  useEffect(() => {
    if (!user || !user.InstituteId) return;
    loadAvailabilityMatrix();
  }, [user]);

  const handlePatientFilter = (event) => {
    setFilterOptions({value: event.currentTarget.value});
  };

  // Multipart CSV upload for the offline REDCap import (XHR, mirrors ExternalCSVUploader's
  // CSRF null-guard since the SPA does not render the csrfmiddlewaretoken hidden input).
  const handleCsvUpload = (fieldName, file, upload_metadata, load, error, progress, abort) => {
    const formData = new FormData();
    formData.append("File", file, file.name);
    formData.append("ParticipantId", csvImportDialog.participant ? csvImportDialog.participant.value : "");
    formData.append("InstrumentName", csvImportDialog.instrumentName || "");

    const request = new XMLHttpRequest();
    request.open('POST', "/api/importRedcapCSV");
    let csrftoken = "";
    if (document.querySelector('[name=csrfmiddlewaretoken]')) {
      csrftoken = document.querySelector('[name=csrfmiddlewaretoken]').value;
    }
    request.setRequestHeader("X-CSRFToken", csrftoken);
    request.upload.onprogress = (e) => { progress(e.lengthComputable, e.loaded, e.total); };
    request.onload = function () {
      if (request.status >= 200 && request.status < 300) {
        load(request.responseText);
        try {
          const data = JSON.parse(request.responseText);
          setAlert(
            <MuiAlertDialog title={"Import Complete"}
              message={`Imported ${data.TotalRecords} record(s) across ${data.Instruments.length} instrument(s). They are now available in the Form Records tab.`}
              handleClose={() => setAlert()} handleConfirm={() => setAlert()}/>);
        } catch (e) { /* ignore parse */ }
        // refresh the form list + availability summary so the new imported form appears
        SessionController.query("/api/querySurveyForms", { RequestType: "RequestAll" })
          .then((response) => setSurveys(response.data)).catch(() => {});
        loadAvailabilityMatrix();
      } else {
        let msg = "Unknown Error Code: " + request.status.toFixed(0);
        if (request.status == 403) {
          msg = "Permission Denied";
        } else if (request.status == 400) {
          try { msg = JSON.parse(request.response).message; } catch (e) { msg = "Bad Request"; }
        }
        error(msg);
      }
    };
    request.send(formData);
    return { abort: () => { request.abort(); abort(); } };
  };

  const addNewSurvey = () => {
    if (newSurveyDialog.surveyType == "Redcap Linked Survey") {
      if (newSurveyDialog.surveyName == "" || newSurveyDialog.redcapApiEndpoint == "" || newSurveyDialog.redcapApiCode == "") {
        setAlert(
          <MuiAlertDialog title={"Incomplete Information"} message={"Please fill out all fields before creating the survey."}
            handleClose={() => setAlert()} 
            handleConfirm={() => setAlert()}/>)
        return;
      }
      
      SessionController.query("/api/setSurveyForms", {
        RequestType: "Create",
        Institute: user.InstituteId,
        FormName: newSurveyDialog.surveyName,
        FormType: newSurveyDialog.surveyType,
        FormContent: [],
        RedcapInfo: {
          API: newSurveyDialog.redcapApiEndpoint,
          Token: newSurveyDialog.redcapApiCode
        }
      }).then((response) => {
        setSurveys([...surveys, response.data]);
        setNewSurveyDialog({surveyName: "", surveyType: "", state: false});
      }).catch((error) => {
        SessionController.displayError(error, setAlert);
      });

    } else {
      SessionController.query("/api/setSurveyForms", {
        RequestType: "Create",
        Institute: user.InstituteId,
        FormName: newSurveyDialog.surveyName,
        FormType: newSurveyDialog.surveyType,
        FormContent: []
      }).then((response) => {
        setSurveys([...surveys, response.data]);
        setNewSurveyDialog({surveyName: "", surveyType: "", state: false});
      }).catch((error) => {
        SessionController.displayError(error, setAlert);
      });
    }
  };

  const deleteSurvey = (id) => {
    SessionController.query("/api/deleteSurveyForms", {
      FormId: id
    }).then((response) => {
      setSurveys([...surveys.filter((value) => value.Id != id)]);
    }).catch((error) => {
      SessionController.displayError(error, setAlert);
    });
  };

  const verifyRedcapConnectivity = () => {
    setAlert(<LoadingProgress/>);
    SessionController.query("/api/verifyRedcapLink", {
      redcapServer: scheduleSurveyLinkDialog.redcapServer,
      redcapSurveyName: scheduleSurveyLinkDialog.redcapSurveyName,
      redcapToken: scheduleSurveyLinkDialog.redcapToken,
      surveyId: scheduleSurveyLinkDialog.surveyId,
    }).then((response) => {
      setScheduleSurveyLinkDialog({...scheduleSurveyLinkDialog, linkageId: response.data.linkageId, verified: true});
      setAlert(
        <MuiAlertDialog title={"Success"} message={"Verification Success"}
          handleClose={() => setAlert()} 
          handleConfirm={() => setAlert()}/>)
    }).catch((error) => {
      setAlert(
        <MuiAlertDialog title={"Cannot Verify"} message={"Please make sure information is correct"}
          handleClose={() => setAlert()} 
          handleConfirm={() => setAlert()}/>)
    });
  };

  const skipRedcapConnectivity = () => {
    setScheduleSurveyLinkDialog({...scheduleSurveyLinkDialog, linkageId: "skip",  activeStep: scheduleSurveyLinkDialog.activeStep + 1});
  };

  const handleLastPage = () => {
    setScheduleSurveyLinkDialog({...scheduleSurveyLinkDialog, activeStep: scheduleSurveyLinkDialog.activeStep - 1});
  };

  const handleNextPage = () => {
    if (scheduleSurveyLinkDialog.activeStep == 2) {
      setAlert(<LoadingProgress/>);
      SessionController.query("/api/surveySchedulerSetup", {
        linkageId: scheduleSurveyLinkDialog.linkageId,
        receiver: {
          ...scheduleSurveyLinkDialog.receiver,
          patientId: scheduleSurveyLinkDialog.patientId,
          messageFormat: scheduleSurveyLinkDialog.messageFormat
        },
        twilio: {
          authToken: scheduleSurveyLinkDialog.authToken,
          accountId: scheduleSurveyLinkDialog.accountId,
          serviceId: scheduleSurveyLinkDialog.serviceId
        },
        frequency: scheduleSurveyLinkDialog.frequency
      }).then((response) => {
        setScheduleSurveyLinkDialog({...scheduleSurveyLinkDialog, show: false});
        setAlert(null);
      }).catch((error) => {
        setAlert(
          <MuiAlertDialog title={"Cannot Verify"} message={"Please make sure information is correct"}
            handleClose={() => setAlert()} 
            handleConfirm={() => setAlert()}/>)
      });
    } else {
      setScheduleSurveyLinkDialog({...scheduleSurveyLinkDialog, activeStep: scheduleSurveyLinkDialog.activeStep + 1});
    }
  };

  useEffect(() => {
    const filterTimer = setTimeout(() => {
      
    }, 200);
    return () => clearTimeout(filterTimer);
  }, [filterOptions, surveys]);

  return (
    <DatabaseLayout>
      {alert}
      <MDBox>
        <Card sx={{marginTop: 5}}>
          <MDBox p={2}>
            <Grid container spacing={2}>
              <Grid item sm={12} md={6}>
                <MDTypography variant="h3">
                  {"Available Surveys or Questionnaires"}
                </MDTypography>
              </Grid>
              <Grid item sm={12} md={6} display="flex" sx={{
                justifyContent: {
                  sm: "space-between",
                  md: "end"
                }
              }}>
                <MDInput label={dictionary.Surveys.SearchSurvey[language]} value={filterOptions.text} onChange={(value) => handlePatientFilter(value)} sx={{paddingRight: 2}}/>
                <MDButton variant="contained" color="success" sx={{marginRight: 2}} onClick={() => setCsvImportDialog({participant: null, files: [], instrumentName: "", state: true})}>
                  {"Import REDCap CSV"}
                </MDButton>
                <MDButton variant="contained" color="info" onClick={() => setNewSurveyDialog({surveyName: "", surveyType: "", state: true})}>
                  {"Add New"} 
                </MDButton>
              </Grid>
              <Grid item xs={12} sx={{marginTop: 2}}>
                <FormTable data={surveys} onDelete={deleteSurvey} />
              </Grid>
            </Grid>
          </MDBox>
        </Card>

        {availabilityMatrix.Participants && availabilityMatrix.Participants.length > 0 ? (
        <Card sx={{marginTop: 3}}>
          <MDBox p={2}>
            <Grid container spacing={1}>
              <Grid item xs={12}>
                <MDTypography variant="h4">
                  {"Score Availability by Patient"}
                </MDTypography>
                <MDTypography variant="body2" color="text" fontSize={14}>
                  {"Which instruments have records for each patient (record count). Hover a cell to see the field list."}
                </MDTypography>
              </Grid>
              <Grid item xs={12} sx={{overflowX: "auto"}}>
                <Table size="small">
                  <TableHead sx={{display: "table-header-group"}}>
                    <TableRow>
                      <TableCell><MDTypography variant="caption" fontWeight="bold">{"Patient"}</MDTypography></TableCell>
                      {availabilityMatrix.Instruments.map((inst) => (
                        <TableCell key={inst} align="center">
                          <MDTypography variant="caption" fontWeight="bold">{inst}</MDTypography>
                        </TableCell>
                      ))}
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {availabilityMatrix.Participants.map((row) => {
                      const byName = {};
                      row.Instruments.forEach((it) => { byName[it.Instrument] = it; });
                      return (
                        <TableRow key={row.ParticipantId} hover>
                          <TableCell>
                            <MDTypography variant="button" fontWeight="medium"
                              sx={{cursor: "pointer", color: "info.main"}}
                              onClick={() => navigate(`/form-records/${row.ParticipantId}`)}>
                              {row.ParticipantName}
                            </MDTypography>
                          </TableCell>
                          {availabilityMatrix.Instruments.map((inst) => {
                            const cell = byName[inst];
                            if (!cell) {
                              return <TableCell key={inst} align="center"><MDTypography variant="caption" color="text">{"\u2013"}</MDTypography></TableCell>;
                            }
                            return (
                              <TableCell key={inst} align="center">
                                <Tooltip arrow placement="top" title={
                                  <div style={{maxWidth: 260}}>
                                    <div style={{fontWeight: "bold", marginBottom: 4}}>{cell.RecordType}</div>
                                    {cell.Fields.map((f) => (<div key={f}>{"\u2022 " + f}</div>))}
                                  </div>
                                }>
                                  <Chip label={cell.Count + " (" + cell.Fields.length + " fields)"}
                                    size="small" color="success" variant="outlined"
                                    sx={{cursor: "default"}}/>
                                </Tooltip>
                              </TableCell>
                            );
                          })}
                        </TableRow>
                      );
                    })}
                  </TableBody>
                </Table>
              </Grid>
            </Grid>
          </MDBox>
        </Card>
        ) : null}
      </MDBox>
      
      <Dialog open={newSurveyDialog.state} onClose={() => setNewSurveyDialog({surveyName: "", surveyType: "", state: false})}>
        <MDBox px={2} pt={2} style={{minWidth: 500}}>
          <MDTypography variant="h5">
            {dictionary.Surveys.AddNewSurvey[language]} 
          </MDTypography>
        </MDBox>
        <DialogContent>
          <MDBox px={2} lineHeight={1}>
            <Autocomplete
              value={newSurveyDialog.surveyType}
              options={["Normal Survey", "Redcap Linked Survey"]}
              onChange={(event, value) => {
                setNewSurveyDialog({...newSurveyDialog, surveyType: value})
              }}
              renderInput={(params) => (
                <FormField
                  {...params}
                  label={"Survey Type"}
                  InputLabelProps={{ shrink: true }}
                />
              )}
              disableClearable
            />
          </MDBox>
          {newSurveyDialog.surveyType == "Redcap Linked Survey" ? (
            <MDBox px={2} lineHeight={1} component="form" autoComplete="off">
              <TextField
                variant="standard"
                margin="dense" id="survey_name"
                value={newSurveyDialog.surveyName}
                onChange={(event) => setNewSurveyDialog({...newSurveyDialog, surveyName: event.target.value})}
                label={"Form Name"} type="text"
                fullWidth
                autoComplete="off"
                inputProps={{ autoComplete: 'off' }}
              />
              <TextField
                variant="standard"
                margin="dense" id="redcap_api_endpoint"
                value={newSurveyDialog.redcapApiEndpoint}
                onChange={(event) => setNewSurveyDialog({...newSurveyDialog, redcapApiEndpoint: event.target.value})}
                label={"Redcap API Endpoint"} type="text"
                fullWidth
                autoComplete="off"
                inputProps={{ autoComplete: 'off' }}
              />
              <TextField
                variant="standard"
                margin="dense" id="redcap_api_code"
                value={newSurveyDialog.redcapApiCode}
                onChange={(event) => setNewSurveyDialog({...newSurveyDialog, redcapApiCode: event.target.value})}
                label={"Redcap API Code"} type="text"
                fullWidth
                // use a non-standard autocomplete value to discourage password managers
                autoComplete="new-password"
                inputProps={{ autoComplete: 'new-password' }}
              />
            </MDBox>
          ) : (
            <MDBox px={2} lineHeight={1} component="form" autoComplete="off">
              <TextField
                variant="standard"
                margin="dense" id="survey_name"
                value={newSurveyDialog.surveyName}
                onChange={(event) => setNewSurveyDialog({...newSurveyDialog, surveyName: event.target.value})}
                label={"Form Name"} type="text"
                fullWidth
                autoComplete="off"
                inputProps={{ autoComplete: 'off' }}
              />
            </MDBox>
          )}
        </DialogContent>
        <DialogActions>
          <MDButton color="secondary" onClick={() => setNewSurveyDialog({surveyName: "", surveyType: "", state: false})}>Cancel</MDButton>
          <MDButton color="info" onClick={() => addNewSurvey()}>Create</MDButton>
        </DialogActions>
      </Dialog>

      <Dialog open={csvImportDialog.state} onClose={() => setCsvImportDialog({...csvImportDialog, state: false})}>
        <MDBox px={2} pt={2} style={{minWidth: 520}}>
          <MDTypography variant="h5">
            {"Import REDCap CSV"}
          </MDTypography>
          <MDTypography variant="body2" color="dark" fontSize={14} mt={1}>
            {"Upload a tidy REDCap export (the pipeline's chronic_pro_df, or a tidy-long export). "}
            {"Each instrument is stored as a form; each report becomes a record available in the Form Records tab and to customized analysis."}
          </MDTypography>
        </MDBox>
        <DialogContent>
          <MDBox px={2} pt={1} lineHeight={1}>
            <Autocomplete
              value={csvImportDialog.participant}
              options={availableParticipants.map((p) => ({value: p.Id, label: p.Name})).sort((a, b) => a.label.localeCompare(b.label))}
              isOptionEqualToValue={(option, value) => option.value === value.value}
              onChange={(event, value) => setCsvImportDialog({...csvImportDialog, participant: value})}
              renderInput={(params) => (
                <FormField {...params} label={"Participant"} InputLabelProps={{ shrink: true }} />
              )}
            />
          </MDBox>
          <MDBox px={2} pt={2} lineHeight={1}>
            <TextField
              variant="standard" margin="dense"
              value={csvImportDialog.instrumentName || ""}
              onChange={(event) => setCsvImportDialog({...csvImportDialog, instrumentName: event.target.value})}
              label={"Instrument / Form Name (optional)"} type="text" fullWidth
              helperText={"Used for a wide export (one instrument). Long exports are auto-split per instrument."}
            />
          </MDBox>
          <MDBox px={2} pt={2}>
            {csvImportDialog.participant ? (
              <FilePond
                files={csvImportDialog.files}
                onupdatefiles={(fileItems) => setCsvImportDialog({...csvImportDialog, files: fileItems.map((f) => f.file)})}
                allowMultiple={false}
                maxFiles={1}
                acceptedFileTypes={["text/csv", "application/vnd.ms-excel", ".csv"]}
                server={{ process: handleCsvUpload }}
                name="File"
                labelIdle={'Drag & drop a REDCap CSV or <span class="filepond--label-action">Browse</span>'}
              />
            ) : (
              <MDTypography variant="body2" color="dark" fontSize={14}>
                {"Select a participant to enable the CSV upload."}
              </MDTypography>
            )}
          </MDBox>
        </DialogContent>
        <DialogActions>
          <MDButton color="secondary" onClick={() => setCsvImportDialog({...csvImportDialog, state: false})}>Close</MDButton>
        </DialogActions>
      </Dialog>

    </DatabaseLayout>
  );
};

