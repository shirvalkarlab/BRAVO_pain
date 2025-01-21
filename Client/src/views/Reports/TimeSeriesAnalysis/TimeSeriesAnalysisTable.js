/**
=========================================================
* UF BRAVO Platform
=========================================================

* Copyright 2025 by Jackson Cagle, Fixel Institute
* The source code is made available under a Creative Common NonCommercial ShareAlike License (CC BY-NC-SA 4.0) (https://creativecommons.org/licenses/by-nc-sa/4.0/) 

 =========================================================

* The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.
*/

import React, { useMemo } from "react"
import { useHistory } from "react-router-dom";

import {
  Autocomplete,
  Box,
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
  Collapse,
} from "@mui/material"

import { SessionController } from "database/session-control.js";
import { formatSegmentString, matchArray } from "database/helper-function";
import { usePlatformContext, setContextState } from "context.js";
import { dictionary, dictionaryLookup } from "assets/translation.js";

import FormField from "components/MDInput/FormField.js";
import MDButton from "components/MDButton";
import MDBox from "components/MDBox";
import MDTypography from "components/MDTypography";
import MDInput from "components/MDInput";

function TimeSeriesAnalysisTable({data, getRecordingData, children}) {
  const [controller, dispatch] = usePlatformContext();
  const { language } = controller;

  const [showTable, setShowTable] = React.useState(true);
  const [selectedDate, setSelectedDate] = React.useState([]);
  const [availableDates, setAvailableDates] = React.useState([]);
  
  const [filterOptions, setFilterOptions] = React.useState({Type: "", Keyword: "", TypeOptions: []});
  const [displayData, setDisplayData] = React.useState([]);

  const tableHeader = [{
    title: "Recording Time",
    minWidth: 100,
    width: "40%"
  },{
    title: "Recording Channels", 
    minWidth: 200,
    width: "35%"
  },{
    title: "Recording Duration", 
    minWidth: 200,
    width: "20%"
  }]

  React.useEffect(() => {
    var uniqueDates = [];
    let typeOptions = ["All"]; 
    for (var i = 0; i < data.length; i++) {
      const dateString = new Date(data[i].Date*1000).toLocaleString("en-US", {...SessionController.getTimezoneName(data[i].Timezone),
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
        timeZoneName: "longGeneric"
      })

      if (!uniqueDates.map((a) => a.label).includes(dateString)) uniqueDates.push({
        label: dateString,
        value: data[i].Date
      });

      if (!typeOptions.includes(data[i].Type)) typeOptions.push(data[i].Type);
    }

    if (uniqueDates.length > 0) {
      setAvailableDates(uniqueDates.sort((a,b) => a.value - b.value));
      setViewDate(uniqueDates[0]);
      setFilterOptions({TypeOptions: typeOptions, Type: "All", Keyword: ""})
    }
  }, [data]);
  
  React.useEffect(() => {
    var collectiveData = [];
    for (var i = 0; i < data.length; i++) {
      const dateString = new Date(data[i].Date*1000).toLocaleString("en-US", {...SessionController.getTimezoneName(data[i].Timezone),
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
        timeZoneName: "longGeneric"
      })

      let filterState = dateString == selectedDate.label && (data[i].Type == filterOptions.Type || filterOptions.Type == "All");
      if (filterState) {
        if (filterOptions.Keyword.length > 0) {
          let contents = filterOptions.Keyword.split(" ");
          for (let content of contents) {
            const optionLower = content.toLowerCase();
            filterState = filterState && (
              data[i].Type.toLowerCase().includes(optionLower) || 
              data[i].Name.toLowerCase().includes(optionLower) || 
              data[i].Id.toLowerCase().includes(optionLower)
            );
          }
        }
        
        if (filterState) {
          collectiveData.push({...data[i], 
          state: false});
        }
      }
    }
    setDisplayData(collectiveData);
  }, [filterOptions]);
  
  const setViewDate = (date) => {
    setSelectedDate(date);
    var collectiveData = [];
    for (var i = 0; i < data.length; i++) {
      const dateString = new Date(data[i].Date*1000).toLocaleString("en-US", {...SessionController.getTimezoneName(data[i].Timezone),
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
        timeZoneName: "longGeneric"
      })

      if (dateString == date.label) {
        collectiveData.push({...data[i],
        state: false});
      }
    }
    setDisplayData(collectiveData);
  };

  const setStimMode = (recordingID, index, event) => {
    for (var i in displayData) {
      if (displayData[i].RecordingIDs == recordingID) {
        displayData[i].ContactType[index] = event.target.value;
        SessionController.query("/api/updateBrainSenseStream", {
          requestData: displayData[i].DeviceID,
          updateRecordingContactType: recordingID,
          contactIndex: index,
          contactType: event.target.value
        }).then((response) => {
          setDisplayData([...displayData]);
        }).catch((error) => {
          console.log(error);
        });
      }
    }
  }
  
  const toggleSelection = (value, timestamp) => {
    for (var i in displayData) {
      if (displayData[i].Timestamp == timestamp || !timestamp) {
        displayData[i].state = value;
      }
    }
    setDisplayData([...displayData]);
  };

  const compareSelected = () => {
    let recordingList = [];
    for (var i in displayData) {
      if (displayData[i].state) {
        recordingList.push(displayData[i].RecordingID);
      }
    }
    getRecordingData(recordingList);
  };

  return useMemo(() => (
    <>
      <MDBox p={2}>
        <Autocomplete
          value={selectedDate}
          options={availableDates}
          onChange={(event, value) => setViewDate(value)}
          isOptionEqualToValue={(option, value) => {
            return option.label === value.label;
          }}
          renderOption={(props, option) => <li {...props}>{option.label}</li>}
          renderInput={(params) => (
            <FormField
              {...params}
              label={dictionary.TherapeuticAnalysis.Table.TableTitle[language]}
              InputLabelProps={{ shrink: true }}
            />
          )}
        />
      </MDBox>
      <Collapse in={showTable} >
        <MDBox p={2} sx={{display: "flex", flexDirection: {xs: "column", sm: "row"}, justifyContent: "space-between"}}>
          <MDInput label={"Search for Analysis"} value={filterOptions.Keyword} onChange={(value) => setFilterOptions({...filterOptions, Keyword: value.target.value})} fullWidth sx={{marginRight: {xs: 0, sm: 3}, marginBottom: {xs: 3, sm: 0}}}/>
          <Autocomplete
            fullWidth
            value={filterOptions.Type}
            options={filterOptions.TypeOptions}
            onChange={(event, value) => setFilterOptions({...filterOptions, Type: value})}
            renderInput={(params) => (
              <FormField
                {...params}
                label={"Filter by Analysis Type"}
                InputLabelProps={{ shrink: true }}
              />
            )}
          />
        </MDBox>
        <MDBox style={{overflowX: "auto", maxHeight: "60vh"}}>
          <Table size="large" style={{marginTop: 20, display: "block", height: "fit-content"}}>
            <TableHead sx={{display: "table-header-group", position: "sticky", top: 0, zIndex: 1}}>
              <TableRow sx={{background: "white"}}>
                {tableHeader.map((col) => (
                  <TableCell key={col.title} variant="head" style={{width: col.width, minWidth: col.minWidth, verticalAlign: "bottom", paddingBottom: 0, paddingTop: 0}}>
                    <MDTypography variant="span" fontSize={12} fontWeight={"bold"} style={{cursor: "pointer"}} onClick={()=>console.log({col})}>
                      {col.title}
                    </MDTypography>
                  </TableCell>
                ))}
                <TableCell key={"viewedit"} variant="head" style={{width: "100px", minWidth: 100, verticalAlign: "bottom", paddingBottom: 0, paddingTop: 0}}>
                  <MDTypography variant="span" fontSize={12} fontWeight={"bold"} style={{cursor: "pointer"}}>{" "}</MDTypography>
                </TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {displayData.sort((a,b) => a.Date - b.Date).map((analysis) => {
                for (let i in analysis.DataId) {
                  
                }
                return <TableRow key={analysis.Id}>
                  <TableCell style={{borderBottom: "1px solid rgba(224, 224, 224, 0.4)"}}>
                    <MDTypography variant="h5" style={{marginBottom: 0}} fontSize={18} fontWeight={"bold"}>
                      {analysis.Name}
                    </MDTypography>
                    <MDTypography variant="h5" fontSize={13} style={{marginBottom: 0}}>
                      {new Date(analysis.Date*1000).toLocaleString("en-US", {...SessionController.getTimezoneName(analysis.Timezone),
                        hour: "2-digit",
                        minute: "2-digit",
                        second: "2-digit",
                        timeZoneName: "longGeneric"
                      })}
                    </MDTypography>
                    <MDTypography variant="h6" style={{marginBottom: 0}} fontSize={12} fontWeight={"bold"}>
                      {analysis.Type}
                    </MDTypography>
                  </TableCell>
                  <TableCell style={{borderBottom: "1px solid rgba(224, 224, 224, 0.4)"}}>
                    <MDBox style={{display: "flex", flexDirection: "column"}}>
                      {analysis.Metadata.ChannelNames.filter((a,i) => i < 3).map((a) => (
                        <MDTypography key={a} variant="h6" fontSize={12} style={{marginBottom: 0}}>
                          {a}
                        </MDTypography>
                      ))} 
                      {analysis.Metadata.ChannelNames.length > 3 ? (
                        <MDTypography variant="h6" fontSize={12} style={{marginBottom: 0}}>
                          {"... Total "}{analysis.Metadata.ChannelNames.length.toFixed(0)}{" Channels"}
                        </MDTypography>
                      ) : null}
                    </MDBox>
                  </TableCell>
                  <TableCell style={{borderBottom: "1px solid rgba(224, 224, 224, 0.4)"}}>
                    <MDBox style={{display: "flex", flexDirection: "column"}}>
                      <MDTypography variant="p" style={{marginBottom: 0}} fontSize={12} fontWeight={"bold"}>
                        {analysis.Metadata.Duration.toFixed(0)}{" seconds"}
                      </MDTypography>
                    </MDBox>
                  </TableCell>
                  <TableCell style={{borderBottom: "1px solid rgba(224, 224, 224, 0.4)"}}>
                    <MDButton variant={"contained"} color="info" onClick={() => {
                      getRecordingData(analysis);
                      setShowTable(false);
                    }} style={{width: 100, padding: 0, marginTop: 3}} fullWidth>
                      {dictionary.ParticipantOverview.ParticipantInformation.View[language]}
                    </MDButton>
                    
                  </TableCell>
                </TableRow>
              })}
            </TableBody>
          </Table>
        </MDBox>
      </Collapse>
      <MDBox p={2}>
        <MDButton variant={"contained"} color="info" onClick={() => setShowTable(!showTable)} >
          {showTable ? "Hide Table" : "Show Table"}
        </MDButton>
      </MDBox>
    </>
  ), [data, showTable, displayData]);
}

export default TimeSeriesAnalysisTable;