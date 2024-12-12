/**
=========================================================
* UF BRAVO Platform
=========================================================

* Copyright 2023 by Jackson Cagle, Fixel Institute
* The source code is made available under a Creative Common NonCommercial ShareAlike License (CC BY-NC-SA 4.0) (https://creativecommons.org/licenses/by-nc-sa/4.0/) 

 =========================================================

* The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.
*/

import { useEffect, useState, memo } from "react";

import {
  Card,
  Chip,
  Checkbox,
  Grid,
  Dialog,
  DialogContent,
  DialogActions,
  TextField,
  Table,
  TableHead,
  TableBody,
  TableCell,
  TableRow
} from "@mui/material";

import { AdapterMoment } from '@mui/x-date-pickers/AdapterMoment';
import { LocalizationProvider } from '@mui/x-date-pickers/LocalizationProvider';
import { DatePicker } from '@mui/x-date-pickers/DatePicker';

import MDBox from "components/MDBox";
import MDTypography from "components/MDTypography";
import MDInput from "components/MDInput";
import MDButton from "components/MDButton";

import TextFilter from "./TextFilter";
import DatabaseLayout from "layouts/DatabaseLayout";
import MuiAlertDialog from "components/MuiAlertDialog";

import { SessionController } from "database/session-control";
import { usePlatformContext, setContextState } from "context";
import { dictionary, dictionaryLookup } from "assets/translation";
import { setAnimated } from "@react-spring/animated";

export default function ExportDataManager() {
  const [controller, dispatch] = usePlatformContext();
  const { user, language } = controller;

  const [alert, setAlert] = useState(null);
  const [filteredPatients, setFilteredPatients] = useState([]);
  const [filterOptions, setFilterOptions] = useState({});
  const [patients, setPatients] = useState([]);
  const [passphrase, setPassphrase] = useState("");
  const [patientsConfiguration, setPatientsConfiguration] = useState({});
  const [addPatientInterface, setAddPatientInterface] = useState({show: false});
  const [editPermissionRange, setEditPermissionRange] = useState({show: false});
  const [showUpload, setShowUpload] = useState(false);

  useEffect(() => {
    SessionController.query("/api/queryDatabaseExport", {
      "RequestType": "Query"
    }).then((response) => {
      if (response.status == 200) {
        setPassphrase(response.data.Passphrase);
        setPatients(response.data.Data);
        setFilteredPatients(response.data.Data);
      }
    }).catch((error) => {
      SessionController.displayError(error, setAlert);
    });
  }, []);

  const handlePatientFilter = (options) => {
    if (patients.length > 0) {
      if (options.length == 0) setFilteredPatients(patients);
      else setFilteredPatients(patients.filter((patient) => {
        console.log(patient)
        var state = true;
        for (var option of options) {
          const optionLower = option.toLowerCase();
          state = state && (
            patient.Name.toLowerCase().includes(optionLower) ||
            patient.Id.toLowerCase().includes(optionLower)
          );
        }
        return state;
      }));
    }
  };

  return (
    <DatabaseLayout>
      {alert}
      <MDBox pt={5}>
        <Card>
          <MDBox p={2}>
            <Grid container spacing={2}>
              <Grid item sm={12} md={6}>
                <MDTypography variant="h3">
                  {dictionary.ResearchAccess.AccessTable[language]}
                </MDTypography>
                <MDTypography variant="h5">
                  {"Passkey: " + passphrase}
                </MDTypography>
              </Grid>
              <Grid item sm={12} md={6} display="flex" sx={{
                justifyContent: {
                  sm: "space-between",
                  md: "end"
                }
              }}>
                <TextFilter onFilter={handlePatientFilter} language={language} />
              </Grid>
              <Grid item xs={12} sx={{marginTop: 2}}>
                <MDBox style={{overflowX: "auto", overflowY: "auto", maxHeight: "70vh"}}>
                  <Table size="small">
                    <TableHead sx={{display: "table-header-group"}}>
                      <TableRow>
                        {["PatientTableName", "File Size", "Date Created", ""].map((col) => {
                          return (
                            <TableCell key={col} variant="head" style={{width: "25%", minWidth: 200, verticalAlign: "bottom", paddingBottom: 0, paddingTop: 0}}>
                              <MDTypography variant="span" fontSize={12} fontWeight={"bold"}>
                                {dictionaryLookup(dictionary.ResearchAccess, col, language)}
                              </MDTypography>
                            </TableCell>
                        )})}
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {filteredPatients.map((patient) => {
                        return <TableRow key={patient.Id}>
                          <TableCell style={{paddingBottom: 1, display: "flex", flexDirection: "row", borderBottom: "0px solid rgba(224, 224, 224, 0.4)"}}>
                            <MDTypography variant="h6" fontSize={15} style={{marginBottom: 0}}>
                              {patient.Name}
                            </MDTypography>
                          </TableCell>
                          <TableCell style={{paddingBottom: 1, borderBottom: "0px solid rgba(224, 224, 224, 0.4)"}}>
                            <MDTypography variant="h6" fontSize={15} style={{marginBottom: 0}}>
                              {(patient.Size/1000000).toFixed(2)} {" MB"}
                            </MDTypography>
                          </TableCell>
                          <TableCell style={{paddingBottom: 1, borderBottom: "0px solid rgba(224, 224, 224, 0.4)"}}>
                            <MDTypography variant="h6" fontSize={15} style={{marginBottom: 0}}>
                              {new Date(patient.Date*1000).toLocaleString()}
                            </MDTypography>
                          </TableCell>
                          <TableCell style={{paddingBottom: 1, borderBottom: "0px solid rgba(224, 224, 224, 0.4)"}}>
                            <MDButton color={"info"} variant={"contained"} onClick={() => {
                              setAlert(<MuiAlertDialog 
                                title={"Currently Processing"}
                                message={"Please wait for data to be retrieved from Server."}
                                confirmText={"Confirm"}
                                handleClose={() => setAlert(null)}
                                handleDeny={() => setAlert(null)}
                                handleConfirm={() => setAlert(null)}
                              />);
                              SessionController.query("/api/queryDatabaseExport", {
                                "RequestType": "Download",
                                "Id": patient.Id
                              }, {}, null, "arraybuffer").then((response) => {
                                var blob = new Blob([response.data]);
                                const url = URL.createObjectURL(blob);
                                const a = document.createElement('a');
                                a.href = url;
                                a.download = patient.Path;
                                a.click();
                                URL.revokeObjectURL(url);
                                setAlert(null);
                              }).catch((error) => {
                                SessionController.displayError(error, setAlert);
                              });
                            }}>
                              {"Download"}
                            </MDButton>
                          </TableCell>
                        </TableRow>
                      })}
                    </TableBody>
                  </Table>
                </MDBox>
              </Grid>
            </Grid>
          </MDBox>
        </Card>
      </MDBox>
    </DatabaseLayout>
  );
};

