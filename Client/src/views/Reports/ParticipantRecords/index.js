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
  TextField,
  Autocomplete,
  Card,
  Dialog,
  DialogContent,
  DialogActions,
  Grid,
} from "@mui/material";

import { FilePond } from 'react-filepond';
import 'filepond/dist/filepond.min.css';

import moment from "moment";
import { AdapterMoment } from '@mui/x-date-pickers/AdapterMoment';
import { LocalizationProvider } from '@mui/x-date-pickers/LocalizationProvider';
import { DatePicker } from '@mui/x-date-pickers/DatePicker';
import { TimePicker } from "@mui/x-date-pickers";

import colormap from "colormap";

import MDBox from "components/MDBox";
import MDTypography from "components/MDTypography";
import RadioButtonGroup from "components/RadioButtonGroup";
import MDBadge from "components/MDBadge";
import MDButton from "components/MDButton";
import FormField from "components/MDInput/FormField";
import LoadingProgress from "components/LoadingProgress";

// core components
import RecordScoreTimeline from "./RecordScoreTimeline";
import RecordCountBars from "./RecordCountBars";

import DatabaseLayout from "layouts/DatabaseLayout";

import { SessionController } from "database/session-control";
import { usePlatformContext, setContextState } from "context.js";
import { dictionary } from "assets/translation.js";
import MuiAlertDialog from "components/MuiAlertDialog";

function ParticipantSurveyRecords() {
  const navigate = useNavigate();
  const [controller, dispatch] = usePlatformContext();
  const { language } = controller;
  const { participant_uid } = useParams();

  const [availableForms, setAvailableForms] = useState({active: {}, options: [], forms: []});
  const [newLinkDialog, setNewLinkDialog] = useState({show: false, form: "", options: []});
  const [newRecordDialog, setNewRecordDialog] = useState({show: false, date: moment(new Date()), time: moment(new Date())});
  const [csvImportDialog, setCsvImportDialog] = useState({show: false, files: [], instrumentName: "", serverExports: [], suggested: null});
  
  const [data, setData] = useState(false);

  const [alert, setAlert] = useState(null);

  const loadForms = (preferFormId) => {
    setAlert(<LoadingProgress/>);
    return SessionController.query("/api/queryParticipantSurveyRecords", {
      RequestType: "RequestAll",
      ParticipantId: participant_uid
    }).then((response) => {
      setAvailableForms(() => {
        let options = [];
        for (let i in response.data.Links) {
          for (let j in response.data.Forms) {
            if (response.data.Forms[j].Id == response.data.Links[i].FormId) {
              const form = {
                ...response.data.Forms[j],
                LinkCode: response.data.Links[i].Id,
              }
              options.push(form);
            }
          }
        }

        const includedForms = options.map((a) => a.Id);
        for (let i in response.data.Forms) {
          if (!includedForms.includes(response.data.Forms[i].Id) && response.data.Forms[i].Count > 0) {
            const form = {
              ...response.data.Forms[i],
            }
            options.push(form);
          }
        }

        const preferred = preferFormId ? options.find((a) => a.Id == preferFormId) : null;
        return {active: preferred ? preferred : (options.length > 0 ? options[0] : {}), options, forms: response.data.Forms}
      })
      setAlert(null);
    }).catch((error) => {
      SessionController.displayError(error, setAlert);
    });
  };

  useEffect(() => {
    if (!participant_uid) {
      navigate("/database", {replace: false});
      return;
    }
    setContextState(dispatch, "report", "SurveyReports");
    // Silently auto-import every server-side REDCap export that matches this participant, THEN load
    // the form list. The import is content-aware server-side: a no-op when nothing changed, and a
    // re-import when the upstream export was refreshed with new reports -- so the user never has to
    // click anything to see up-to-date PROs. Failures are non-fatal; we still load whatever exists.
    SessionController.query("/api/importRedcapCSV", {
      RequestType: "AutoImport",
      ParticipantId: participant_uid
    }).then(() => {
      loadForms();
    }).catch(() => {
      loadForms();
    });
  }, [participant_uid]);

  // Multipart CSV upload for the offline REDCap import, scoped to THIS participant (XHR mirrors
  // ExternalCSVUploader's CSRF null-guard — the SPA doesn't render the csrfmiddlewaretoken input).
  const handleCsvUpload = (fieldName, file, upload_metadata, load, error, progress, abort) => {
    const formData = new FormData();
    formData.append("File", file, file.name);
    formData.append("ParticipantId", participant_uid);
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
        let importedFormId = null;
        try {
          const resp = JSON.parse(request.responseText);
          if (resp.Instruments && resp.Instruments.length > 0) importedFormId = resp.Instruments[0].FormId;
          setAlert(
            <MuiAlertDialog title={"Import Complete"}
              message={`Imported ${resp.TotalRecords} record(s) across ${resp.Instruments.length} instrument(s) for this participant.`}
              handleClose={() => setAlert(null)} handleConfirm={() => setAlert(null)}/>);
        } catch (e) { /* ignore parse */ }
        setCsvImportDialog({show: false, files: [], instrumentName: ""});
        loadForms(importedFormId);
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

  // Ask the server which PRO exports already exist for this participant, so the dialog can offer a
  // one-click import instead of forcing a manual file pick.
  const openImportDialog = () => {
    setCsvImportDialog({show: true, files: [], instrumentName: "", serverExports: [], suggested: null});
    SessionController.query("/api/importRedcapCSV", {
      RequestType: "ListServerExports",
      ParticipantId: participant_uid
    }).then((response) => {
      setCsvImportDialog((d) => ({...d, serverExports: response.data.Exports || [], suggested: response.data.Suggested || null}));
    }).catch(() => {
      // non-fatal: the manual uploader is always available
    });
  };

  const importFromServer = (serverPath) => {
    setAlert(<LoadingProgress/>);
    SessionController.query("/api/importRedcapCSV", {
      ParticipantId: participant_uid,
      ServerPath: serverPath,
      InstrumentName: csvImportDialog.instrumentName || ""
    }).then((response) => {
      const importedFormId = (response.data.Instruments && response.data.Instruments.length > 0) ? response.data.Instruments[0].FormId : null;
      setCsvImportDialog({show: false, files: [], instrumentName: "", serverExports: [], suggested: null});
      setAlert(
        <MuiAlertDialog title={"Import Complete"}
          message={`Imported ${response.data.TotalRecords} record(s) from ${serverPath}.`}
          handleClose={() => setAlert(null)} handleConfirm={() => setAlert(null)}/>);
      loadForms(importedFormId);
    }).catch((error) => {
      SessionController.displayError(error, setAlert);
    });
  };

  const addNewFormLink = () => {
    if (!newLinkDialog.form) return;

    if (newLinkDialog.form.Type == "Redcap Linked Survey" && !newLinkDialog.redcapId) {
      setAlert(
        <MuiAlertDialog open={true} type={"error"}
          title={"Redcap Record Id Required"}
          message={"Please enter the Redcap Record Id to link this form."}
          handleClose={() => setAlert(null)}
          handleConfirm={() => setAlert(null)}
        />
      );
      return;
    }

    SessionController.query("/api/queryParticipantSurveyRecords", {
      RequestType: "AddLink",
      ParticipantId: participant_uid,
      FormId: newLinkDialog.form.Id,
      RecordId: newLinkDialog.redcapId ? newLinkDialog.redcapId : null,
    }).then((response) => {
      setAvailableForms((availableForms) => {
        for (let i in availableForms.forms) {
          if (availableForms.forms[i].Id == newLinkDialog.form.Id) {
            const form = {
              ...availableForms.forms[i],
              LinkCode: response.data
            };
            return {...availableForms, active: form, options: [...availableForms.options, form]}
          }
        }
        return {...availableForms}
      })
      setNewLinkDialog({...newLinkDialog, show: false})

    }).catch((error) => {
      SessionController.displayError(error, setAlert);
    });
  };

  useEffect(() => {
    if (!availableForms.active.Id) return;

    SessionController.query("/api/queryParticipantSurveyRecords", {
      RequestType: "RequestRecords",
      ParticipantId: participant_uid,
      FormId: availableForms.active.Id
    }).then((response) => {
      setData(response.data);
    }).catch((error) => {
      SessionController.displayError(error, setAlert);
    });
  }, [availableForms.active])

  return (
    <DatabaseLayout>
    {alert}
      <MDBox pt={3}>
        <MDBox display={"flex"} flexDirection={"row"} justifyContent={"space-between"}>
          <Autocomplete
            value={availableForms.active}
            options={availableForms.options}
            onChange={(event, value) => {
              setAvailableForms({...availableForms, active: value})
            }}
            isOptionEqualToValue={(option, value) => {
              return option.Id === value.Id;
            }}
            renderOption={(props, option) => <li {...props}>{option.Name + " (Version: " + option.Version + ")"}</li>}
            getOptionLabel={(option) => {
              if (typeof option === 'string') {
                return option;
              }
              if (option.inputValue) {
                return option.inputValue;
              }
              return option.Name + " (Version: " + option.Version + ")";
            }}
            renderInput={(params) => (
              <FormField
                {...params}
                label={"Choose Available Form for View"}
                InputLabelProps={{ shrink: true }}
              />
            )}
            fullWidth
            disableClearable
          />
          <MDBox display="flex" flexDirection="row">
            <MDButton variant="contained" color="success" style={{minWidth: 200, marginRight: 12}} onClick={() => openImportDialog()}>
              {"Import REDCap CSV"}
            </MDButton>
            <MDButton variant="contained" color="info" style={{minWidth: 200}} onClick={() => setNewLinkDialog(() => {
              return {active: {}, options: availableForms.forms, show: true}
            })}>
              {"Link New Form"} 
            </MDButton>
          </MDBox>
        </MDBox>

        <Dialog open={newLinkDialog.show} onClose={() => setNewLinkDialog({...newLinkDialog, show: false})}>
          <MDBox px={2} pt={2} style={{minWidth: 500}}>
            <MDTypography variant="h5">
              {"Add New Link"} 
            </MDTypography>
          </MDBox>
          <DialogContent>
            <MDBox>
              <Autocomplete
                value={newLinkDialog.form}
                options={newLinkDialog.options}
                onChange={(event, value) => {
                  setNewLinkDialog({...newLinkDialog, form: value})
                }}
                isOptionEqualToValue={(option, value) => {
                  return option.Id === value.Id;
                }}
                renderOption={(props, option) => <li {...props}>{option.Name + " (Version: " + option.Version + ")"}</li>}
                getOptionLabel={(option) => {
                  if (typeof option === 'string') {
                    return option;
                  }
                  if (option.inputValue) {
                    return option.inputValue;
                  }
                  return option.Name + " (Version: " + option.Version + ")";
                }}
                renderInput={(params) => (
                  <FormField
                    {...params}
                    label={"Choose Available Form for Participant"}
                    InputLabelProps={{ shrink: true }}
                  />
                )}
                disableClearable
              />
            </MDBox>
            {newLinkDialog.form && newLinkDialog.form.Type == "Redcap Linked Survey" ? (
              <MDBox mt={2}>
                <TextField variant={"standard"} value={newLinkDialog.redcapId} label={"Please Enter the Redcap Record Id here"} onChange={(event) => setNewLinkDialog({...newLinkDialog, redcapId: event.target.value})} rows={1} sx={{marginX: 1}} fullWidth>
                </TextField>
              </MDBox>
            ) : null}
          </DialogContent>
          <DialogActions>
            <MDButton color="secondary" onClick={() => setNewLinkDialog({...newLinkDialog, show: false})}>Close</MDButton>
            <MDButton color="info" onClick={() => addNewFormLink()}>Create</MDButton>
          </DialogActions>
        </Dialog>
        
        <MDBox pt={2}>
          <Grid container spacing={2}>
            <Grid item xs={12}>
              <Card sx={{width: "100%"}}>
                <Grid container>
                  <Grid item xs={12}>
                    <MDBox p={2} display={"flex"} flexDirection={"row"} justifyContent={"space-between"} alignItems={"center"}>
                      <MDTypography variant={"h6"} fontSize={24}>
                        {"Record Timeline"}
                      </MDTypography>
                      
                      {availableForms.active.Type === "Redcap Linked Survey" ? (
                        <MDButton variant="contained" color="error" style={{minWidth: 200}} onClick={() => setAlert(<MuiAlertDialog open={true} type={"warning"}
                          title={"Remove Form Link"}
                          message={"Are you sure you want to remove the link to this form for the participant? This will delete any existing records."}
                          denyButton={true}
                          handleDeny={() => setAlert(null)}
                          handleClose={() => setAlert(null)}
                          handleConfirm={() => {
                            SessionController.query("/api/queryParticipantSurveyRecords", {
                              RequestType: "RemoveLink",
                              ParticipantId: participant_uid,
                              FormId: availableForms.active.Id
                            }).then((response) => {
                              setAvailableForms((availableForms) => {
                                const newOptions = availableForms.options.filter((a) => a.Id != availableForms.active.Id);
                                return {...availableForms, active: newOptions.length > 0 ? newOptions[0] : {}, options: newOptions}
                              })
                              setAlert(null);
                            }).catch((error) => {
                              SessionController.displayError(error, setAlert);
                            });
                          }}
                        />)}>
                          {"Remove Link"} 
                        </MDButton>
                      ) : null}
                      {availableForms.active.LinkCode ? (
                        <MDButton variant="contained" color="success" style={{minWidth: 200}} onClick={() => setNewRecordDialog((newRecordDialog) => {
                          return {...newRecordDialog, show: true}
                        })}>
                          {"Add New Record"} 
                        </MDButton>
                      ) : null}
                    </MDBox>
                  </Grid>
                  {data.length > 0 ? (
                    <>
                    <Grid item xs={12}>
                      <RecordCountBars dataToRender={data} form={availableForms.active.Record}/>
                    </Grid>
                    <Grid item xs={12}>
                      <RecordScoreTimeline dataToRender={data} form={availableForms.active.Record} figureTitle={"RecordScoreTimeline"}/>
                    </Grid>
                    </>
                  ) : (
                    <Grid item xs={12}>
                      <MDBox px={2} pb={2}>
                        <MDTypography variant={"p"} fontSize={20}>
                          {"No Available Records"}
                        </MDTypography>
                      </MDBox>
                    </Grid>
                  )}
                </Grid>
              </Card>
            </Grid>
          </Grid>
        </MDBox>

        <Dialog open={newRecordDialog.show} onClose={() => setNewRecordDialog({...newRecordDialog, show: false})}>
          <MDBox px={2} pt={2} style={{minWidth: 500}}>
            <MDTypography variant="h5">
              {"Add New Record"} 
            </MDTypography>
          </MDBox>
          <DialogContent>
            <MDBox p={2} display={"flex"} flexDirection={"row"}>
              <MDTypography variant={"h6"} fontSize={24} pr={2}>
                {"Date: "}
              </MDTypography>
              <LocalizationProvider dateAdapter={AdapterMoment} adapterLocale={"us"}>
                <DatePicker
                  label="Date"
                  value={newRecordDialog.date}
                  onChange={(newDate) => {
                    setNewRecordDialog({...newRecordDialog, date: newDate});
                  }}
                  renderInput={(params) => <TextField {...params} />}
                />
              </LocalizationProvider>
              <MDTypography variant={"h6"} fontSize={24} px={2}>
                {"Time: "}
              </MDTypography>
              <LocalizationProvider dateAdapter={AdapterMoment}>
                <TimePicker
                  label="Time"
                  value={newRecordDialog.time}
                  onChange={(newDate) => {
                    setNewRecordDialog({...newRecordDialog, time: newDate});
                  }}
                  renderInput={(params) => <TextField {...params} />}
                />
              </LocalizationProvider>
            </MDBox>
          </DialogContent>
          <DialogActions>
            <MDButton color="secondary" onClick={() => setNewRecordDialog({...newRecordDialog, show: false})}>Close</MDButton>
            <MDButton color="info" onClick={() => {
              let date = new Date(newRecordDialog.date.toISOString().split("T")[0] + "T" + newRecordDialog.time.toISOString().split("T")[1]).getTime();
              date -= (newRecordDialog.date.utcOffset() - newRecordDialog.time.utcOffset()) * 60000;
              window.open(window.location.origin + "/survey/" + availableForms.active.ShortLink + "?__passcode=" + availableForms.active.LinkCode + "&__date=" + (date/1000).toFixed(0), '_blank').focus();
            }}>Create</MDButton>
          </DialogActions>
        </Dialog>

        <Dialog open={csvImportDialog.show} onClose={() => setCsvImportDialog({...csvImportDialog, show: false})}>
          <MDBox px={2} pt={2} style={{minWidth: 520}}>
            <MDTypography variant="h5">
              {"Import REDCap CSV"}
            </MDTypography>
            <MDTypography variant="body2" color="text" fontSize={14} mt={1}>
              {"Upload a tidy REDCap export (the pipeline's chronic_pro_df, or a tidy-long export) for this participant. "}
              {"Each instrument is stored as a form; each report becomes a record shown in the timeline below. Re-importing the same instrument replaces its prior records."}
            </MDTypography>
          </MDBox>
          <DialogContent>
            <MDBox px={1} pt={1}>
              <TextField
                variant="standard" margin="dense"
                value={csvImportDialog.instrumentName || ""}
                onChange={(event) => setCsvImportDialog({...csvImportDialog, instrumentName: event.target.value})}
                label={"Instrument / Form Name (optional)"} type="text" fullWidth
                helperText={"Used for a wide export (one instrument). Long exports are auto-split per instrument."}
              />
            </MDBox>
            {csvImportDialog.serverExports && csvImportDialog.serverExports.length > 0 ? (
              <MDBox px={1} pt={2}>
                <MDTypography variant="button" fontWeight="medium" color="text">
                  {"Found on server"}
                </MDTypography>
                {csvImportDialog.serverExports.map((exp) => (
                  <MDBox key={exp.ServerPath} mt={1} display="flex" flexDirection="row" justifyContent="space-between" alignItems="center"
                    sx={{border: "1px solid #e0e0e0", borderRadius: 1, p: 1}}>
                    <MDBox>
                      <MDTypography variant="button" fontWeight={exp.MatchesParticipant ? "bold" : "regular"}>
                        {exp.ServerPath}
                      </MDTypography>
                      {exp.MatchesParticipant ? (
                        <MDBadge badgeContent={"matches this patient"} color="success" variant="gradient" size="xs" container sx={{ml: 1}}/>
                      ) : null}
                      <MDTypography variant="caption" color="text" display="block">
                        {exp.SizeBytes ? (exp.SizeBytes/1024).toFixed(0) + " KB" : ""}
                      </MDTypography>
                    </MDBox>
                    <MDButton variant={exp.MatchesParticipant ? "contained" : "outlined"} color="success" size="small"
                      onClick={() => importFromServer(exp.ServerPath)}>
                      {"Import"}
                    </MDButton>
                  </MDBox>
                ))}
                <MDTypography variant="caption" color="text" display="block" mt={2}>
                  {"\u2014 or upload a file manually \u2014"}
                </MDTypography>
              </MDBox>
            ) : null}
            <MDBox px={1} pt={2}>
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
            </MDBox>
          </DialogContent>
          <DialogActions>
            <MDButton color="secondary" onClick={() => setCsvImportDialog({...csvImportDialog, show: false})}>Close</MDButton>
          </DialogActions>
        </Dialog>

      </MDBox>
    </DatabaseLayout>
  );
}

export default ParticipantSurveyRecords;
