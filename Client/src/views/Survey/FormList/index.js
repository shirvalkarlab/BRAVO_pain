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

import {
  Card,
  Grid,
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

import { AdapterMoment } from '@mui/x-date-pickers/AdapterMoment';
import { LocalizationProvider } from '@mui/x-date-pickers/LocalizationProvider';
import { TimePicker } from '@mui/x-date-pickers/TimePicker';

import MDBox from "components/MDBox";
import MDTypography from "components/MDTypography";
import MDInput from "components/MDInput";
import MDButton from "components/MDButton";
import MuiAlertDialog from "components/MuiAlertDialog";
import LoadingProgress from "components/LoadingProgress";

import DatabaseLayout from "layouts/DatabaseLayout";
import FormTable from "./FormTable";

import { SessionController } from "database/session-control";
import { usePlatformContext, setContextState } from "context";
import { dictionary, dictionaryLookup } from "assets/translation";

export default function FormList() {
  const [controller, dispatch] = usePlatformContext();
  const { user, language } = controller;

  const [filteredPatients, setFilteredPatients] = useState([]);
  const [filterOptions, setFilterOptions] = useState({});
  const [surveys, setSurveys] = useState([]);
  const [schedules, setSchedules] = useState([]);
  const [newSurveyDialog, setNewSurveyDialog] = useState({surveyName: "", surveyType: "", state: false});
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

  const handlePatientFilter = (event) => {
    setFilterOptions({value: event.currentTarget.value});
  };

  const addNewSurvey = () => {
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
      </MDBox>
      
      <Dialog open={newSurveyDialog.state} onClose={() => setNewSurveyDialog({surveyName: "", surveyType: "", state: false})}>
        <MDBox px={2} pt={2} style={{minWidth: 500}}>
          <MDTypography variant="h5">
            {dictionary.Surveys.AddNewSurvey[language]} 
          </MDTypography>
        </MDBox>
        <DialogContent>
          <TextField
            variant="standard"
            margin="dense" id="survey_name"
            value={newSurveyDialog.surveyName}
            onChange={(event) => setNewSurveyDialog({...newSurveyDialog, surveyName: event.target.value})}
            label={"Form Name"} type="text"
            fullWidth
          />
          <TextField
            variant="standard"
            margin="dense" id="survey_type"
            value={newSurveyDialog.surveyType}
            onChange={(event) => setNewSurveyDialog({...newSurveyDialog, surveyType: event.target.value})}
            placeholder={"Participant-oriented Survey or Researcher-conducted Questionnaires?"}
            label={"Form Type"} type="text"
            fullWidth
          />
        </DialogContent>
        <DialogActions>
          <MDButton color="secondary" onClick={() => setNewSurveyDialog({surveyName: "", surveyType: "", state: false})}>Cancel</MDButton>
          <MDButton color="info" onClick={() => addNewSurvey()}>Create</MDButton>
        </DialogActions>
      </Dialog>
      
    </DatabaseLayout>
  );
};

