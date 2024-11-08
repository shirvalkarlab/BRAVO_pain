/**
=========================================================
* UF BRAVO Platform
=========================================================

* Copyright 2023 by Jackson Cagle, Fixel Institute
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
} from "@mui/material"

import MDBox from "components/MDBox";
import MDTypography from "components/MDTypography";
import MDButton from "components/MDButton";
import FormField from "components/MDInput/FormField";
import LoadingProgress from "components/LoadingProgress";

// core components
import ObjectiveMarkerTrend from "./ObjectiveMarkerTrend";

import DatabaseLayout from "layouts/DatabaseLayout";

import { SessionController } from "database/session-control";
import { usePlatformContext, setContextState } from "context.js";
import { dictionary } from "assets/translation.js";

function ObjectiveMarkerModel() {
  const navigate = useNavigate();
  const [controller, dispatch] = usePlatformContext();
  const { patientID, language } = controller;

  const [data, setData] = useState(false);

  const [eventList, setEventList] = useState({current: null, list: []});
  const [availableDevice, setAvailableDevices] = useState({current: null, list: []});
  const [markerModel, setMarkerModel] = useState({model: false, timestamp: [], probability: [], params: {}});

  const [alert, setAlert] = useState(null);

  useEffect(() => {
    if (!patientID) {
      navigate("/dashboard", {replace: false});
    } else {
      setAlert(<LoadingProgress/>);
      SessionController.query("/api/queryObjectiveMarkerModel", {
        id: patientID, 
        request: "Overview",
      }).then((response) => {
        console.log(response.data)
        setData(response.data.ChronicData);
        setAlert(null);
      }).catch((error) => {
        SessionController.displayError(error, setAlert);
      });
    }
  }, [patientID]);


  useEffect(() => {
    setAvailableDevices(() => {
      let therapyList = [];
      for (let i in data) {
        for (let j in data[i].TherapyList) {
          therapyList.push({
            label: data[i].Device + " " + data[i].CustomName + " " + data[i].TherapyList[j],
            device: data[i].Device,
            target: data[i].Hemisphere,
            therapy: data[i].TherapyList[j]
          });
        }
      }
      return {current: therapyList.length > 0 ? therapyList[0] : null, list: therapyList};
    })
  }, [data]);

  useEffect(() => {
    if (availableDevice.current) {
      setEventList(() => {
        let eventList = [];
        for (let i in data) {
          for (let j in data[i].EventName) {
            for (let k in data[i].EventName[j]) {
              if (!eventList.includes(data[i].EventName[j][k])) eventList.push(data[i].EventName[j][k]);
            }
          }
        }
        
        if (eventList.length > 0) checkObjectiveMarkerModel(eventList[0])
        return {current: eventList.length > 0 ? eventList[0] : null, list: eventList }
      })
    }
  }, [availableDevice]);

  const checkObjectiveMarkerModel = (event) => {
    setAlert(<LoadingProgress/>);
    SessionController.query("/api/queryObjectiveMarkerModel", {
      id: patientID, 
      request: "CheckModel",
      device: availableDevice.current.device,
      target: availableDevice.current.target,
      therapy: availableDevice.current.therapy,
      event: event
    }).then((response) => {
      setMarkerModel({...markerModel, model: response.data.Model})
      setAlert(null);
    }).catch((error) => {
      SessionController.displayError(error, setAlert);
    });
  }

  const generateObjectiveMarkerModel = (event) => {
    setAlert(<LoadingProgress/>);
    SessionController.query("/api/queryObjectiveMarkerModel", {
      id: patientID, 
      request: "GenerateModel",
      device: availableDevice.current.device,
      target: availableDevice.current.target,
      therapy: availableDevice.current.therapy,
      event: event
    }).then((response) => {
      console.log(response.data)
      setAlert(null);
    }).catch((error) => {
      SessionController.displayError(error, setAlert);
    });
  }

  const queryObjectiveMarkerModel = (event) => {
    setAlert(<LoadingProgress/>);
    SessionController.query("/api/queryObjectiveMarkerModel", {
      id: patientID, 
      request: "GetModel",
      device: availableDevice.current.device,
      target: availableDevice.current.target,
      therapy: availableDevice.current.therapy,
      event: event
    }).then((response) => {
      setMarkerModel((markerModel) => {
        markerModel.params = {
          device: availableDevice.current.device,
          target: availableDevice.current.target,
          therapy: availableDevice.current.therapy,
          event: event
        };
        markerModel.timestamp = response.data.Time;
        markerModel.probability = response.data.Probability;
        return {...markerModel}
      });
      
      setAlert(null);
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
                  <Grid container mb={2}>
                    <Grid item xs={12}>
                      <MDBox p={2}>
                        <MDTypography variant={"h6"} fontSize={24}>
                          {dictionary.AdaptiveStimulation.Figure.ChronicAdaptive[language]}
                        </MDTypography>
                      </MDBox>
                    </Grid>
                    <Grid item xs={12}>
                      <MDBox p={2}>
                        <Autocomplete
                          value={availableDevice.current}
                          options={availableDevice.list}
                          onChange={(event, value) => setAvailableDevices({...availableDevice, current: value})}
                          renderOption={(props, option) => <li {...props}>{option.label}</li>}
                          renderInput={(params) => (
                            <FormField
                              {...params}
                              label={"Select Unique Recording Configuration"}
                              InputLabelProps={{ shrink: true }}
                            />
                          )}
                        />
                      </MDBox>
                      <MDBox px={2}>
                        <Autocomplete
                          value={eventList.current}
                          options={eventList.list}
                          onChange={(event, value) => {
                            setEventList({...eventList, current: value});
                            checkObjectiveMarkerModel(value);
                          }}
                          renderInput={(params) => (
                            <FormField
                              {...params}
                              label={"Select Objective Marker"}
                              InputLabelProps={{ shrink: true }}
                            />
                          )}
                        />
                      </MDBox>
                    </Grid>
                    <Grid item xs={12} lg={12}>
                      <MDBox display={"flex"} flexDirection={"row"} p={2}>
                        <MDButton color={"secondary"} style={{marginRight: 15}}
                          onClick={() => generateObjectiveMarkerModel(eventList.current)}
                        >
                          {markerModel.model ? "Regenerate Model" : "Generate Model"}
                        </MDButton>
                        <MDButton color={"info"} 
                          onClick={() => queryObjectiveMarkerModel(eventList.current)}
                        >
                          {"Query Object Markers"}
                        </MDButton>
                      </MDBox>
                    </Grid>
                  </Grid>
                </Card>
              </Grid>
              {data ? (
              <Grid item xs={12}>
                <Card sx={{width: "100%"}}>
                  <MDBox p={2}>
                    <ObjectiveMarkerTrend dataToRender={data.filter((a) => a.Device == markerModel.params.device)} objectiveMarker={markerModel} height={600} figureTitle={"Objective Marker Labels"} />
                  </MDBox>
                </Card>
              </Grid>
              ) : null}
            </Grid>
          </MDBox>
        </MDBox>
      </DatabaseLayout>
    </>
  );
}

export default ObjectiveMarkerModel;
