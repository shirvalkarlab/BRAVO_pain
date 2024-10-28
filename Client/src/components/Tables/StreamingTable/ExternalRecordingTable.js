/**
=========================================================
* UF BRAVO Platform
=========================================================

* Copyright 2023 by Jackson Cagle, Fixel Institute
* The source code is made available under a Creative Common NonCommercial ShareAlike License (CC BY-NC-SA 4.0) (https://creativecommons.org/licenses/by-nc-sa/4.0/) 

 =========================================================

* The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.
*/

import React from "react"
import { useHistory } from "react-router-dom";

import {
  Autocomplete,
  Box,
  Dialog,
  TextField,
  DialogContent,

  FormControl,
  Table,
  TableHead,
  TableBody,
  TableRow,
  TableCell,
  InputLabel,
  IconButton,
  Select,
  Switch,
  MenuItem,
  Tooltip,
  Checkbox,
} from "@mui/material"

import { SessionController } from "database/session-control.js";
import { formatSegmentString, matchArray } from "database/helper-function";
import { usePlatformContext, setContextState } from "context.js";
import { dictionary, dictionaryLookup } from "assets/translation.js";

import FormField from "components/MDInput/FormField.js";
import MDButton from "components/MDButton";
import MDBox from "components/MDBox";
import MDTypography from "components/MDTypography";

function ExternalRecordingTable({data, deleteRecordingData, children}) {
  const [controller, dispatch] = usePlatformContext();
  const { patientID, language } = controller;

  const [editRecordingName, setEditRecordingName] = React.useState({
    show: false,
    name: "",
    recordingId: "",
  });

  const [toggleMerge, setToggleMerge] = React.useState({show: false, merge: []});
  const [selectedDate, setSelectedDate] = React.useState([]);
  const [availableDates, setAvailableDates] = React.useState([]);
  
  const [displayData, setDisplayData] = React.useState([]);

  const tableHeader = [{
    title: "StreamingTableDate",
    minWidth: 100,
    width: "60%"
  },{
    title: "StreamingTableRecordingDuration",
    minWidth: 100,
    width: "15%"
  }]

  React.useEffect(() => {
    var uniqueDates = [];
    for (var i = 0; i < data.length; i++) {
      var timestruct = new Date(data[i]["Time"]*1000);
      if (data[i].Duration >= 30) {
        var found = false
        for (var date of uniqueDates) {
          if (date.value == timestruct.toLocaleDateString(language)) {
            found = true;
            break;
          }
        }
        if (!found) {
          uniqueDates.push({
            time: data[i]["Time"]*1000,
            value: timestruct.toLocaleDateString(language),
            label: timestruct.toLocaleDateString(language)
          });
        }
      }
    }

    if (uniqueDates.length > 0) {
      setAvailableDates(uniqueDates.sort((a,b) => b.time - a.time));
      setViewDate(uniqueDates[0]);
    }
  }, [data])
  
  const setViewDate = (date) => {
    setSelectedDate(date);
    var collectiveData = [];
    for (var i = 0; i < data.length; i++) {
      var timestruct = new Date(data[i]["Time"]*1000);
      if (timestruct.toLocaleDateString(language) == date.value) {
        collectiveData.push({...data[i], state: false});
      }
    }
    setDisplayData(collectiveData);
  };

  const handleEditRecordingName = (editRecordingName) => {
    SessionController.query("/api/updateBrainSenseStream", {
      id: patientID,
      updateRecordingName: editRecordingName.recordingId,
      recordingName: editRecordingName.name,
    }).then((response) => {
      setDisplayData((displayData) => {
        for (let i in displayData) {
          if (displayData[i].AnalysisID == editRecordingName.recordingId) {
            displayData[i].AnalysisLabel = editRecordingName.name;
            return [...displayData];
          }
        }
        return displayData;
      });
      setEditRecordingName({recordingId: "", name: "", show: false});
    }).catch((error) => {
      console.log(error);
    });
  }

  return (
    <>
      <MDBox p={2}>
        <Autocomplete
          value={selectedDate}
          options={availableDates}
          onChange={(event, value) => setViewDate(value)}
          getOptionLabel={(option) => {
            return option.label || "";
          }}
          renderInput={(params) => (
            <FormField
              {...params}
              label={dictionary.BrainSenseStreaming.Table.TableTitle[language]}
              InputLabelProps={{ shrink: true }}
            />
          )}
        />
      </MDBox>
      <MDBox style={{overflowX: "auto"}}>
        <Dialog open={editRecordingName.show} onClose={() => setEditRecordingName({...editRecordingName, show: false})}>
          <MDBox px={2} pt={2}>
            <MDTypography variant="h5">
              {"Edit Recording Name"}
            </MDTypography>
          </MDBox>
          <DialogContent>
            <TextField
              variant="standard"
              margin="dense" id="name"
              value={editRecordingName.name}
              onChange={(event) => setEditRecordingName({...editRecordingName, name: event.target.value})}
              fullWidth
            />
          </DialogContent>
          <MDBox style={{paddingLeft: 15, paddingRight: 15, paddingBottom: 15}}>
            <MDButton color={"secondary"} 
              onClick={() => setEditRecordingName({...editRecordingName, show: false})}
            >
              Cancel
            </MDButton>
            <MDButton color={"info"} 
              onClick={() => handleEditRecordingName(editRecordingName)} style={{marginLeft: 10}}
            >
              Update
            </MDButton>
          </MDBox>
        </Dialog>
        <Table size="large" style={{marginTop: 20}}>
          <TableHead sx={{display: "table-header-group"}}>
            <TableRow>
              {tableHeader.map((col) => (
                <TableCell key={col.title} variant="head" style={{width: col.width, minWidth: col.minWidth, verticalAlign: "bottom", paddingBottom: 0, paddingTop: 0}}>
                  <MDTypography variant="span" fontSize={12} fontWeight={"bold"} style={{cursor: "pointer"}} onClick={()=>console.log({col})}>
                    {dictionary.BrainSenseStreaming.Table[col.title][language]}
                  </MDTypography>
                </TableCell>
              ))}
              <TableCell key={"viewedit"} variant="head" style={{width: "100px", minWidth: 100, verticalAlign: "bottom", paddingBottom: 0, paddingTop: 0}}>
                <MDTypography variant="span" fontSize={12} fontWeight={"bold"} style={{cursor: "pointer"}}>{" "}</MDTypography>
              </TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {displayData.map((recording) => {
              return <TableRow key={recording.RecordingId}>
                <TableCell style={{borderBottom: "1px solid rgba(224, 224, 224, 0.4)"}}>
                  {recording.RecordingLabel ? (
                    <MDTypography variant="h5" fontSize={18} style={{marginBottom: 0}}>
                      {recording.RecordingLabel}
                    </MDTypography>
                  ) : null}
                  <MDTypography variant="h5" fontSize={recording.RecordingLabel ? 12 : 15} style={{marginBottom: 0}}>
                    {new Date(recording.Time*1000).toLocaleString(language)}
                  </MDTypography>
                  <MDTypography variant="h6" style={{marginBottom: 0}} fontSize={12} fontWeight={"bold"}>
                    {recording.RecordingType}
                  </MDTypography>
                  <MDButton color={"info"} 
                    onClick={() => setEditRecordingName({show: true, recordingId: recording.AnalysisID, name: recording.AnalysisLabel})}
                  >
                    Edit Label
                  </MDButton>
                </TableCell>
                <TableCell style={{borderBottom: "1px solid rgba(224, 224, 224, 0.4)"}}>
                  <MDTypography variant="p" fontSize={15} style={{marginBottom: 0}}>
                    {recording.Duration.toFixed(2)} {" " + dictionary.Time.Seconds[language]}  
                  </MDTypography>
                </TableCell>
                <TableCell style={{borderBottom: "1px solid rgba(224, 224, 224, 0.4)"}}>
                  <MDButton variant={"contained"} color="info" onClick={() => deleteRecordingData(recording.RecordingId)} style={{padding: 0}}>
                    {"Delete"}
                  </MDButton>
                </TableCell>
              </TableRow>
            })}
          </TableBody>
        </Table>
      </MDBox>
    </>
  );
}

export default ExternalRecordingTable;