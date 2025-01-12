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

import moment from "moment";
import { AdapterMoment } from '@mui/x-date-pickers/AdapterMoment';
import { LocalizationProvider } from '@mui/x-date-pickers/LocalizationProvider';
import { DatePicker } from '@mui/x-date-pickers/DatePicker';

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

import DatabaseLayout from "layouts/DatabaseLayout";

import { SessionController } from "database/session-control";
import { usePlatformContext, setContextState } from "context.js";
import { dictionary } from "assets/translation.js";
import { TimePicker } from "@mui/x-date-pickers";

function ParticipantSurveyRecords() {
  const navigate = useNavigate();
  const [controller, dispatch] = usePlatformContext();
  const { language } = controller;
  const { participant_uid } = useParams();

  const [availableForms, setAvailableForms] = useState({active: {}, options: [], forms: []});
  const [newLinkDialog, setNewLinkDialog] = useState({show: false, form: "", options: []});
  const [newRecordDialog, setNewRecordDialog] = useState({show: false, date: moment(new Date()), time: moment(new Date())});
  
  const [data, setData] = useState(false);

  const [alert, setAlert] = useState(null);

  useEffect(() => {
    if (!participant_uid) {
      navigate("/dashboard", {replace: false});
      return;
    }
    setContextState(dispatch, "report", "SurveyReports");

    setAlert(<LoadingProgress/>);
    SessionController.query("/api/queryParticipantSurveyRecords", {
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

        return {active: options.length > 0 ? options[0] : {}, options, forms: response.data.Forms}
      })
      setAlert(null);
    }).catch((error) => {
      SessionController.displayError(error, setAlert);
    });
  }, [participant_uid]);

  const addNewFormLink = () => {
    SessionController.query("/api/queryParticipantSurveyRecords", {
      RequestType: "AddLink",
      ParticipantId: participant_uid,
      FormId: newLinkDialog.form.Id
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
          <MDButton variant="contained" color="info" style={{minWidth: 200}} onClick={() => setNewLinkDialog(() => {
            return {active: {}, options: availableForms.forms, show: true}
          })}>
            {"Link New Form"} 
          </MDButton>
        </MDBox>

        <Dialog open={newLinkDialog.show} onClose={() => setNewLinkDialog({...newLinkDialog, show: false})}>
          <MDBox px={2} pt={2} style={{minWidth: 500}}>
            <MDTypography variant="h5">
              {"Add New Link"} 
            </MDTypography>
          </MDBox>
          <DialogContent>
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
          </DialogContent>
          <DialogActions>
            <MDButton color="secondary" onClick={() => setNewLinkDialog({...newLinkDialog, show: false})}>Cancel</MDButton>
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
                    <Grid item xs={12}>
                      <RecordScoreTimeline dataToRender={data} form={availableForms.active.Record} figureTitle={"RecordScoreTimeline"}/>
                    </Grid>
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
            <MDButton color="secondary" onClick={() => setNewRecordDialog({...newRecordDialog, show: false})}>Cancel</MDButton>
            <MDButton color="info" onClick={() => {
              let date = new Date(newRecordDialog.date.toISOString().split("T")[0] + "T" + newRecordDialog.time.toISOString().split("T")[1]).getTime();
              date -= (newRecordDialog.date.utcOffset() - newRecordDialog.time.utcOffset()) * 60000;
              window.open(window.location.origin + "/survey/" + availableForms.active.ShortLink + "?__passcode=" + availableForms.active.LinkCode + "&__date=" + (date/1000).toFixed(0), '_blank').focus();
            }}>Create</MDButton>
          </DialogActions>
        </Dialog>
        
      </MDBox>
    </DatabaseLayout>
  );
}

export default ParticipantSurveyRecords;
