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
  Autocomplete,
  Card,
  Grid,
  Dialog,
  Stack,
  Switch,
} from "@mui/material"
import { styled } from '@mui/material/styles';

import MDButton from "components/MDButton";
import MDBox from "components/MDBox";
import MDTypography from "components/MDTypography";
import FormField from "components/MDInput/FormField";
import LoadingProgress from "components/LoadingProgress";
import MuiAlertDialog from "components/MuiAlertDialog";

// core components
import JobTable from "./JobTable";
import DatabaseLayout from "layouts/DatabaseLayout";

import { SessionController } from "database/session-control";
import { usePlatformContext, setContextState } from "context.js";
import { dictionary, dictionaryLookup } from "assets/translation.js";

 function AsyncJobSchedule() {
  const navigate = useNavigate();
  const [controller, dispatch] = usePlatformContext();
  const { language } = controller;
  const { study_uid } = useParams();

  const [data, setData] = useState([]);
  const [alert, setAlert] = useState(null);

  useEffect(() => {
    setContextState(dispatch, "report", "GroupAnalysis");
    
    setAlert(<LoadingProgress/>);
    SessionController.query("/api/queryAsyncJobQueue", {
      RequestType: "GetAllStatus"
    }).then((response) => {
      setData(response.data);
      setAlert(null);
    }).catch((error) => {
      SessionController.displayError(error, setAlert);
    });
  }, [study_uid]);
  
  const updateJobStatus = (job_id) => {
    SessionController.query("/api/queryAsyncJobQueue", {
      RequestType: "GetJobStatus",
      JobId: job_id
    }).then((response) => {
      setData((prevData) => {
        const newData = [...prevData];
        for (let i in newData) {
          if (newData[i].Id === job_id) {
            newData[i] = response.data;
          }
        }
        return newData;
      });
    }).catch((error) => {
      SessionController.displayError(error, setAlert);
    });
  }

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
                    {data.length > 0 ? (
                      <>
                        <Grid item xs={12}>
                          <MDBox p={2} display={"flex"} flexDirection={"row"} justifyContent={"space-between"}>
                            <MDTypography variant={"h6"} fontSize={24}>
                              {"Asynchronous Job Scheduling List"}
                            </MDTypography>
                          </MDBox>
                          <MDBox px={2} pb={2} display={"flex"} flexDirection={"row"} justifyContent={"space-between"}>
                            <MDButton variant="gradient" color="info" onClick={() => {
                              setAlert(<LoadingProgress/>);
                              SessionController.query("/api/queryAsyncJobQueue", {
                                RequestType: "ClearCompletedJobs"
                              }).then((response) => {
                                setData(response.data);
                                setAlert(null);
                              }).catch((error) => {
                                SessionController.displayError(error, setAlert);
                              });
                            }}>
                              {"Clear All Finished Jobs"}
                            </MDButton>
                          </MDBox>
                        </Grid>
                        <Grid item xs={12} lg={12}>
                          <JobTable data={data} updateJobStatus={updateJobStatus}/>
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
            </Grid>
          </MDBox>
        </MDBox>
      </DatabaseLayout>
    </>
  );
}

export default AsyncJobSchedule;
