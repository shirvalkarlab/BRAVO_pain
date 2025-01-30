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
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";

import {
  Autocomplete,
  Card,
  Divider,
  Dialog,
  DialogContent,
  DialogActions,
  Grid,
  Table,
  TableHead,
  TableBody,
  TableRow,
  TableCell,
  Tooltip,
  TextField,
  Icon,
  IconButton,
} from "@mui/material";

import { createFilterOptions } from "@mui/material/Autocomplete";

import BoltIcon from '@mui/icons-material/Bolt';
import AssessmentIcon from '@mui/icons-material/Assessment';
import PollIcon from '@mui/icons-material/Poll';
import SensorsIcon from '@mui/icons-material/Sensors';
import TimelineIcon from '@mui/icons-material/Timeline';
import BatchPredictionIcon from '@mui/icons-material/BatchPrediction';
import FlashAutoIcon from "@mui/icons-material/FlashAuto";
import PhotoIcon from "@mui/icons-material/Photo";
import WatchIcon from "@mui/icons-material/Watch";
import ArticleIcon from '@mui/icons-material/Article';

import { FaBrain } from "react-icons/fa6";

import MDBox from "components/MDBox";
import MDTypography from "components/MDTypography";
import MDInput from "components/MDInput";
import MDButton from "components/MDButton";

import DatabaseLayout from "layouts/DatabaseLayout";
import EditParticipantInfoView from "./EditParticipantInfoView";
import EditDeviceInfoView from "./EditDeviceInfoView";
import UploadDataView from "./UploadDataView";

import { SessionController } from "database/session-control";
import { usePlatformContext, setContextState } from "context";
import { dictionary } from "assets/translation";

import {
  experimentalRoutes
} from "views/Experimental/plugins";
import MuiAlertDialog from "components/MuiAlertDialog";
import LoadingProgress from "components/LoadingProgress";

import routes from "routes.js";
import SetExperimentView from "./SetExperimentView";

const filter = createFilterOptions();

export default function ParticipantOverview() {
  const navigate = useNavigate();
  const [controller, dispatch] = usePlatformContext();
  const { user, language, experiment, report } = controller;

  const [participantInfo, setParticipantInfo] = useState(false);
  const [editParticipantInfo, setEditParticipantInfo] = useState(false);
  const [editDeviceInfo, setEditDeviceInfo] = useState({show: false});
  const [uploadView, setUploadView] = useState({show: false});
  const [activeExperiment, setActiveExperiment] = useState({show: false, options: [], active: experiment});
  const [uploadNewJson, setUploadNewJson] = useState({show: false});
  const [mergeRecords, setMergeRecords] = useState({show: false});
  const [addNewDevice, setAddNewDevice] = useState({show: false});
  const [availableTags, setAvailableTags] = useState([]);

  const [alert, setAlert] = useState(null);
  const { participant_uid } = useParams();

  const initialSetup = async () => {
    try {
      let response = await SessionController.query("/api/queryParticipantInformation", {
        ParticipantId: participant_uid
      })
      
      setContextState(dispatch, "participant_uid", participant_uid);
      setEditParticipantInfo(false);
      setParticipantInfo(response.data);
      setAvailableTags([]);

    } catch (error) {
      SessionController.displayError(error, setAlert, () => {
        navigate("/dashboard", {replace: true});
      });
    }
  }

  useEffect(() => {
    if (!participant_uid) {
      navigate("/dashboard", {replace: false});
      return
    }

    initialSetup();
  }, [participant_uid]);

  const removeDevice = (device_uid) => {
    setAlert(<MuiAlertDialog 
      title={"Remove Device"}
      message={"Are you sure you want to delete the device entry and all associated data?"}
      confirmText={"YES"}
      denyText={"NO"}
      denyButton
      handleClose={() => setAlert(null)}
      handleDeny={() => setAlert(null)}
      handleConfirm={() => {
        setAlert(<LoadingProgress />);
        SessionController.query("/api/deleteDeviceInformation", {
          ParticipantId: participant_uid,
          DeviceId: device_uid
        }).then((response) => {
          setParticipantInfo(response.data);
          setAlert(null);
        }).catch((error) => {
          SessionController.displayError(error, setAlert);
        });
      }}
    />)
  };

  const removeParticipant = () => {
    setAlert(<MuiAlertDialog 
      title={"Remove Participant"}
      message={"Are you sure you want to delete the participant entry and all associated data?"}
      confirmText={"YES"}
      denyText={"NO"}
      denyButton
      handleClose={() => setAlert(null)}
      handleDeny={() => setAlert(null)}
      handleConfirm={() => {
        setEditParticipantInfo(false);
        setAlert(<LoadingProgress />);
        SessionController.query("/api/deleteParticipantInformation", {
          ParticipantId: participant_uid
        }).then(() => {
          setContextState(dispatch, "participant_uid", null);
          navigate("/dashboard", {replace: true});
        }).catch((error) => {
          SessionController.displayError(error, setAlert);
        });
      }}
    />)
  };

  const updateParticipantInformation = (editParticipantInfo) => {
    setAlert(<LoadingProgress />);
    SessionController.query("/api/updateParticipantInformation", {
      ParticipantId: participant_uid,
      Name: editParticipantInfo.Name,
      Diagnosis: editParticipantInfo.Diagnosis,
      Sex: editParticipantInfo.Sex,
      Tags: editParticipantInfo.Tags
    }).then((response) => {
      setParticipantInfo(response.data);
      setEditParticipantInfo(false);
      setAlert(null);
    }).catch((error) => {
      SessionController.displayError(error, setAlert);
    });
  };

  const updateDeviceInformation = (deviceInfo) => {
    setAlert(<LoadingProgress />);
    SessionController.query("/api/updateDeviceInformation", {
      ParticipantId: participant_uid,
      DeviceId: deviceInfo.Id,
      Name: deviceInfo.Name,
      Electrodes: deviceInfo.Electrodes,
    }).then((response) => {
      setParticipantInfo(response.data);
      setEditDeviceInfo({...editDeviceInfo, show: false});
      setAlert(null);
    }).catch((error) => {
      SessionController.displayError(error, setAlert);
    });
  }

  return (
    <DatabaseLayout>
      {alert}
      <MDBox py={3}>
        {participantInfo ? (
        <MDBox mb={3}>
          <Grid container spacing={2}>
            <Grid item xs={12} lg={4} display={"flex"} alignItems={"stretch"}>
              <Card sx={{width: "100%"}}>
                <MDBox p={2}>
                  <Grid container spacing={1}>
                    <Grid item xs={12}>
                      <MDBox mb={0.5} lineHeight={1}>
                        <MDTypography
                          variant="h5"
                          fontWeight="bold"
                          textTransform="capitalize"
                        >
                          {participantInfo.Name}
                        </MDTypography>
                      </MDBox>
                      <MDBox mb={2} lineHeight={1}>
                        <MDTypography
                          variant="p"
                          fontWeight="medium"
                          fontSize={15}
                          color="text"
                          textTransform="capitalize"
                        >
                          {participantInfo.Diagnosis ? (
                            dictionary.ParticipantOverview.ParticipantInformation[participantInfo.Diagnosis] ? dictionary.ParticipantOverview.ParticipantInformation[participantInfo.Diagnosis][language] : participantInfo.Diagnosis
                          ) : "Diagnosis: N/A"}
                        </MDTypography>
                      </MDBox>
                      {participantInfo.DOB !== 0 ? (
                      <MDBox mb={0.5} lineHeight={1}>
                        <MDTypography
                          variant="p"
                          fontWeight="medium"
                          fontSize={13}
                          textTransform="capitalize"
                        >
                          {dictionary.ParticipantOverview.ParticipantInformation.DOB[language]}: {new Date(participantInfo.DOB*1000).toLocaleDateString(language, SessionController.getDateTimeOptions("DateLong"))}
                        </MDTypography>
                      </MDBox>
                      ) : null}
                    </Grid>
                    <Grid item xs={12}>
                      <Divider variant="middle" />
                      <MDButton variant="contained" color="warning" fullWidth 
                        onClick={() => setEditParticipantInfo(true)}
                      >
                        {dictionary.ParticipantOverview.EditParticipantInfo[language]}
                      </MDButton>
                      <MDButton variant="contained" color="info" fullWidth 
                        onClick={() => setUploadView({show: true, participant: participant_uid})}
                      >
                        {"Upload Data to Participant"}
                      </MDButton>
                    </Grid>
                  </Grid>
                </MDBox>
              </Card>
              <EditParticipantInfoView 
                show={editParticipantInfo} 
                participantInfo={participantInfo} 
                removeParticipant={removeParticipant}
                onCancel={() => setEditParticipantInfo(false)} 
                onUpdate={updateParticipantInformation} 
              />
              <UploadDataView 
                show={uploadView.show}
                participant_uid={participant_uid} 
                onCancel={() => setUploadView({show: false})} 
              />
            </Grid>
            <Grid item xs={12} lg={8} display={"flex"} alignItems={"stretch"}>
              <Card sx={{width: "100%", overflowX: "auto"}}>
                <Grid container spacing={2}>
                  <Grid item xs={3}>
                          
                  </Grid>
                </Grid>
                <MDBox style={{overflowX: "auto", maxHeight: 200}}>
                  <Table size="large" style={{marginTop: 10, display: "block", height: "fit-content"}}>
                    <TableHead sx={{display: "table-header-group", position: "sticky", top: 0, zIndex: 1}}>
                      <TableRow sx={{background: "white"}}>
                        {["DeviceType", "DeviceName", "Electrodes", "ImplantDate"].map((col) => {
                          return (
                            <TableCell key={col} variant="head" style={{width: "25%", minWidth: 150, verticalAlign: "bottom", paddingBottom: 5, paddingTop: 5, textAlign: "center", lineHeight: 1}}>
                              <MDTypography variant="p" fontSize={12} fontWeight={"bold"} style={{cursor: "pointer"}} onClick={()=>console.log({col})}>
                                {dictionary.ParticipantOverview.DeviceTable[col][language]}
                              </MDTypography>
                            </TableCell>
                        )})}
                        <TableCell key={"viewdelete"} variant="head" style={{width: "15%", verticalAlign: "bottom", paddingBottom: 5, paddingTop: 5, textAlign: "center", lineHeight: 1}}>
                          <MDTypography variant="span" fontSize={12} fontWeight={"bold"} style={{cursor: "pointer"}}> {" "} </MDTypography>
                        </TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {participantInfo.DBSDevices.sort((a,b) => b.Date-a.Date).map((device) => {
                        const deviceName = device.Name;
                        return <TableRow key={device.Id}>
                          <TableCell key={"devicetype"} style={{borderBottom: "1px solid rgba(224, 224, 224, 0.4)"}}>
                            <MDTypography align="center" style={{marginBottom: 0}} fontSize={12}>
                              {device.Type}
                            </MDTypography>
                          </TableCell>
                          <TableCell key={"devicename"} style={{borderBottom: "1px solid rgba(224, 224, 224, 0.4)"}}>
                            <MDTypography align="center" style={{marginBottom: 0}} fontSize={12}>
                              {deviceName.length > 32 ? deviceName.slice(0,32) : deviceName}
                            </MDTypography>
                          </TableCell>
                          <TableCell key={"leadname"} style={{borderBottom: "1px solid rgba(224, 224, 224, 0.4)"}}>
                            {device.Electrodes.map((lead) => {
                              return <MDBox key={lead.Id} style={{marginBottom: 5}}>
                              <MDTypography style={{marginBottom: 0, marginTop: 0}} align="center" fontSize={8}>
                                {lead.Type}
                              </MDTypography>
                              <MDTypography style={{marginBottom: 0, marginTop: 0}} align="center" fontSize={11}>
                                {lead.CustomName ? lead.CustomName : lead.Target}
                              </MDTypography>
                            </MDBox>
                            })}
                          </TableCell>
                          <TableCell key={"implantdate"} style={{borderBottom: "1px solid rgba(224, 224, 224, 0.4)"}}>
                            <MDTypography align="center" style={{marginBottom: 0}} fontSize={12}>
                              {new Date(SessionController.decodeTimestamp(device.Date*1000)).toLocaleString(language, SessionController.getDateTimeOptions("DateNumeric"))}
                            </MDTypography>
                          </TableCell>
                          <TableCell key={"viewedit"} style={{borderBottom: "1px solid rgba(224, 224, 224, 0.4)"}}>
                            <MDBox style={{display: "flex", flexDirection: "row"}}>
                              <Tooltip title="Delete Device" placement="top">
                                <IconButton variant="contained" color="error" onClick={() => removeDevice(device.Id)}>
                                  <i className="fa-solid fa-xmark" style={{fontSize: 10}}></i>
                                </IconButton>
                              </Tooltip>
                              <Tooltip title="Edit Device" placement="top">
                                <IconButton variant="contained" color="info" onClick={() => setEditDeviceInfo({deviceInfo: device, show: true})}>
                                  <i className="fa-solid fa-pen" style={{fontSize: 10}}></i>
                                </IconButton>
                              </Tooltip>
                            </MDBox>
                          </TableCell>
                        </TableRow>
                      })}
                    </TableBody>
                  </Table>
                </MDBox>
              </Card>

              <EditDeviceInfoView 
                show={editDeviceInfo.show} 
                deviceInfo={editDeviceInfo.deviceInfo} 
                onCancel={() => setEditDeviceInfo({show: false})} 
                onUpdate={updateDeviceInformation} 
              />
            </Grid>
          </Grid>
        </MDBox>
        ) : null}
        <MDBox mb={3}>
          <Grid container spacing={2}>
            <Grid item xs={12} display={"flex"} alignItems={"stretch"}>
              <MDTypography variant={"span"} fontSize={15} fontWeight={"bold"}>
                {dictionary.Routes.Reports[language]}
              </MDTypography>
            </Grid>
            {Object.keys(routes).map((key) => {
              if (key === "Main") return;
              return <Grid key={key} item xs={6} md={4} lg={3} xl={2} display={"flex"} alignItems={"stretch"}>
                <Card sx={{width: "100%"}}>
                  <MDBox p={2} mx={3} display="flex" justifyContent="center">
                    <MDBox
                      display="grid" justifyContent="center" alignItems="center"
                      width="4rem" height="4rem" shadow="md"
                      borderRadius="lg" variant="gradient"
                    >
                      <Icon fontSize="large">
                        {routes[key].icon}
                      </Icon>
                    </MDBox>
                  </MDBox>
                  <MDBox pb={6} px={2} textAlign="center" lineHeight={1.25}>
                    <MDTypography variant="h6" fontWeight="medium" textTransform="capitalize" pb={2}>
                      {routes[key].name}
                    </MDTypography>
                  </MDBox>
                  <MDBox pb={2} px={2} lineHeight={1.25} sx={{position: "absolute", bottom: 0, width: "100%"}}>
                    <MDButton variant={"contained"} color={"info"} fullWidth onClick={() => {
                      setContextState(dispatch, "report", key);
                    }}>
                      {dictionary.ParticipantOverview.ParticipantInformation.View[language]}
                    </MDButton>
                  </MDBox>
                </Card>
              </Grid>
            })}
          </Grid>
        </MDBox>
        {routes[report] ? (
          <MDBox mb={3}>
            <Grid container spacing={2}>
              <Grid item xs={12} display={"flex"} alignItems={"stretch"}>
                <MDTypography variant={"span"} fontSize={15} fontWeight={"bold"}>
                  {dictionary.Routes[report] ? dictionary.Routes[report][language] : report}
                </MDTypography>
              </Grid>
              {routes[report].children.map((subreport) => {
                if (subreport.hide) return;
                return <Grid key={subreport.route} item xs={6} md={4} lg={3} xl={2} display={"flex"} alignItems={"stretch"}>
                  <Card sx={{width: "100%"}}>
                    <MDBox p={2} mx={3} display="flex" justifyContent="center">
                      <MDBox
                        display="grid" justifyContent="center" alignItems="center"
                        width="4rem" height="4rem"
                        shadow="md" borderRadius="lg" variant="gradient"
                      >
                        <Icon fontSize="large">
                          {subreport.icon}
                        </Icon>
                      </MDBox>
                    </MDBox>
                    <MDBox pb={6} px={2} textAlign="center" lineHeight={1.25}>
                      <MDTypography variant="h6" fontWeight="medium" textTransform="capitalize" pb={2}>
                        {subreport.name}
                      </MDTypography>
                    </MDBox>
                    <MDBox pb={2} px={2} lineHeight={1.25} sx={{position: "absolute", bottom: 0, width: "100%"}}>
                      <MDButton variant={"contained"} color={"info"} fullWidth onClick={() => {
                        navigate(subreport.route.replace(":participant_uid", participant_uid), {replace: false})
                      }}>
                        {dictionary.ParticipantOverview.ParticipantInformation.View[language]}
                      </MDButton>
                    </MDBox>
                  </Card>
                </Grid>
              })}
            </Grid>
          </MDBox>
        ) : null}
      </MDBox>
    </DatabaseLayout>
  );
};
