/**
=========================================================
* UF BRAVO Platform
=========================================================

* Copyright 2025 by Jackson Cagle, Fixel Institute
* The source code is made available under a Creative Common NonCommercial ShareAlike License (CC BY-NC-SA 4.0) (https://creativecommons.org/licenses/by-nc-sa/4.0/) 

 =========================================================

* The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.
*/

import { useEffect, useState, useRef } from "react";
import { useNavigate, useParams } from "react-router-dom";

import {
  Autocomplete,
  Card,
  Grid,
  IconButton,
  Stepper,
  Step,
  StepButton,
  Dialog,
  DialogContent,
  TextField
} from "@mui/material"

import SettingsIcon from '@mui/icons-material/Settings';
import OpenInBrowserIcon from '@mui/icons-material/OpenInBrowser';
import DeleteForeverIcon from '@mui/icons-material/DeleteForever';

import MuiAlertDialog from "components/MuiAlertDialog";
import MDButton from "components/MDButton";
import MDBox from "components/MDBox";
import MDTypography from "components/MDTypography";
import LoadingProgress from "components/LoadingProgress";

// core components
import DatabaseLayout from "layouts/DatabaseLayout";
import AnalysisBuilder from "./AnalysisBuilder";

import { SessionController } from "database/session-control";
import { usePlatformContext, setContextState } from "context.js";
import { dictionary } from "assets/translation.js";

function CustomizedAnalysis() {
  const navigate = useNavigate();
  const [controller, dispatch] = usePlatformContext();
  const { language } = controller;
  const { participant_uid } = useParams();

  const [data, setData] = useState(false);

  const [analysisList, setAnalysisList] = useState([]);
  const [analysisId, setAnalysisId] = useState(null);
  
  const [editAnalysis, setEditAnalysis] = useState({
    show: false,
    name: ""
  });

  const [alert, setAlert] = useState(null);

  useEffect(() => {
    
  }, []);

  useEffect(() => {
    if (!participant_uid) {
      navigate("/database", {replace: false});
      return;
    }
    setContextState(dispatch, "report", "CustomizedAnalysis");

    setAlert(<LoadingProgress/>);
    SessionController.query("/api/queryCustomizedAnalysis", {
      RequestType: "RequestList",
      ParticipantId: participant_uid
    }).then((response) => {
      setAnalysisList(response.data);
      setAlert(null);
    }).catch((error) => {
      SessionController.displayError(error, setAlert);
    });
  }, [participant_uid]);

  useEffect(() => {
    
  }, [analysisId]);

  const handleAddAnalysis = () => {
    setAlert(<LoadingProgress/>);
    SessionController.query("/api/queryCustomizedAnalysis", {
      RequestType: "NewAnalysis",
      ParticipantId: participant_uid
    }).then((response) => {
      setAnalysisList([...analysisList, response.data]);
      setAlert(null);
    }).catch((error) => {
      SessionController.displayError(error, setAlert);
    });
  };

  const handleDeleteAnalysis = (analysisId) => {
    setAlert(<MuiAlertDialog 
      title={"Remove Analysis"}
      message={"Are you sure you want to remove the analysis? All configurations for this analysis will be removed and is not recoverable"}
      confirmText={"YES"}
      denyText={"NO"}
      denyButton
      handleClose={() => setAlert(null)}
      handleDeny={() => setAlert(null)}
      handleConfirm={() => {
        setAlert(<LoadingProgress/>);
        SessionController.query("/api/queryCustomizedAnalysis", {
          RequestType: "DeleteAnalysis",
          ParticipantId: participant_uid,
          AnalysisId: analysisId
        }).then((response) => {
          setAnalysisList([...analysisList.filter((analysis) => analysis.Id != analysisId)]);
          setAlert(null);
        }).catch((error) => {
          SessionController.displayError(error, setAlert);
        });
      }}
    />);
  };

  const handleEditAnalysis = (analysisId) => {
    setAlert(<LoadingProgress/>);
    SessionController.query("/api/queryCustomizedAnalysis", {
      RequestType: "EditAnalysis",
      ParticipantId: participant_uid,
      AnalysisId: analysisId,
      AnalysisName: editAnalysis.name
    }).then((response) => {
      setAnalysisList((analysisList) => {
        for (let i in analysisList) {
          if (analysisList[i].Id == analysisId) {
            analysisList[i].Name = editAnalysis.name;
          }
        }
        return [...analysisList];
      });
      setEditAnalysis({...editAnalysis, show: false});
      setAlert(null);
    }).catch((error) => {
      SessionController.displayError(error, setAlert);
    });
  }

  return (
    <DatabaseLayout>
    {alert}
      <MDBox pt={3}>
        <MDBox>
          <Grid container spacing={2}>
            {analysisList.map((analysis) => {
              return (
                <Grid key={analysis.Id} item xs={6} md={4}>
                  <Card sx={{width: "100%", padding: 3, display: "flex", flexDirection: "column", justifyContent: "space-between", alignItems: "start"}}>
                    <MDBox>
                      <MDTypography fontWeight={"bold"}>
                        {analysis.Name}
                      </MDTypography>
                      <MDTypography fontSize={15}>
                        {new Date(analysis.Date*1000).toLocaleDateString()}
                      </MDTypography>
                    </MDBox>
                    <MDBox>
                      <IconButton color="info" size="small" onClick={() => setEditAnalysis({analysisId: analysis.Id, name: analysis.Name, show: true})} sx={{paddingX: 1}}>
                        <SettingsIcon fontSize={"large"} />
                      </IconButton>
                      <IconButton color="info" size="small" onClick={() => setAnalysisId(analysis.Id)} sx={{paddingX: 1}}>
                        <OpenInBrowserIcon fontSize={"large"} />
                      </IconButton>
                      <IconButton color="error" size="small" onClick={() => handleDeleteAnalysis(analysis.Id)} sx={{paddingX: 1}}>
                        <DeleteForeverIcon fontSize={"large"} />
                      </IconButton>
                    </MDBox>
                  </Card>
                </Grid>
              );
            })}

            <Dialog open={editAnalysis.show} onClose={() => setEditAnalysis({...editAnalysis, show: false})}>
              <MDBox px={2} pt={2}>
                <MDTypography variant="h5">
                  {"Edit Analysis Name"}
                </MDTypography>
              </MDBox>
              <DialogContent>
                <TextField
                  variant="standard"
                  margin="dense" id="name"
                  value={editAnalysis.name}
                  onChange={(event) => setEditAnalysis({...editAnalysis, name: event.target.value})}
                  fullWidth
                />
              </DialogContent>
              <MDBox style={{paddingLeft: 15, paddingRight: 15, paddingBottom: 15}}>
                <MDButton color={"secondary"} 
                  onClick={() => setEditAnalysis({...editAnalysis, show: false})}
                >
                  Cancel
                </MDButton>
                <MDButton color={"info"} 
                  onClick={() => handleEditAnalysis(editAnalysis.analysisId)} style={{marginLeft: 10}}
                >
                  Update
                </MDButton>
              </MDBox>
            </Dialog>

            <Grid item xs={6} md={3}>
              <Card sx={{width: "100%", height: "100%", borderStyle: "dashed", borderWidth: 1, padding: 3, justifyContent: "center", alignItems: "center", cursor: "pointer"}} onClick={handleAddAnalysis}>
                <MDTypography>
                  {"Add New Analysis"}
                </MDTypography>
              </Card>
            </Grid>
          </Grid>
        </MDBox>

        {analysisId ? (
        <MDBox pt={3}>
          <AnalysisBuilder analysisId={analysisId} />
        </MDBox>
        ) : null}

      </MDBox>
    </DatabaseLayout>
  );
}

export default CustomizedAnalysis;
