/**
=========================================================
* UF BRAVO Platform
=========================================================

* Copyright 2025 by Jackson Cagle, Fixel Institute
* The source code is made available under a Creative Common NonCommercial ShareAlike License (CC BY-NC-SA 4.0) (https://creativecommons.org/licenses/by-nc-sa/4.0/) 

 =========================================================

* The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.
*/

import { useEffect, useState, useCallback, useMemo } from "react";
import { useNavigate, useParams } from "react-router-dom";

import {
  Autocomplete,
  Dialog,
  DialogContent,
  TextField,
  Card,
  Icon,
  Drawer,
  SpeedDial,
  SpeedDialAction,
  SpeedDialIcon,
  Grid,
  ListItem,
  ListItemButton,
  ListItemIcon,
  ListItemText,
  Checkbox,
  IconButton,
  InputLabel,
  Input,
} from "@mui/material"

import MDBox from "components/MDBox";
import MDTypography from "components/MDTypography";
import MDButton from "components/MDButton";
import MuiAlertDialog from "components/MuiAlertDialog";

import { v4 as uuidv4 } from 'uuid';

import { SessionController } from "database/session-control";

function ProcessingSelect({processingNodes, onClose, onSetProcessingNode}) {

  const [nodeGroup, setNodeGroup] = useState({active: "", options: []});
  const [nodeType, setNodeType] = useState({active: "", options: []});

  useEffect(() => {
    setNodeGroup(() => {
      let options = [];
      for (let i in processingNodes) {
        if (!options.includes(processingNodes[i].Group)) {
          options.push(processingNodes[i].Group);
        }
      }
      if (options.length > 0) return {active: options[0], options: options};
      return {active: "", options: []}
    })
  }, [processingNodes])

  useEffect(() => {
    setNodeType(() => {
      let options = [];
      for (let i in processingNodes) {
        if (processingNodes[i].Group == nodeGroup.active) {
          options.push(processingNodes[i].Type);
        }
      }
      if (options.length > 0) return {active: options[0], options: options};
      return {active: "", options: []}
    })
  }, [nodeGroup.active])

  return (
    <DialogContent>
      <MDBox px={2} pt={2}>
        <MDTypography variant="h5">
          {"Add Processing Node to Analysis"}
        </MDTypography>
      </MDBox>
      
      <MDBox px={2} pt={2}>
        <Autocomplete selectOnFocus clearOnBlur disableClearable
          renderInput={(params) => (
            <TextField {...params} variant="standard" label={"Select Processing Type"}/>
          )}
          isOptionEqualToValue={(option, value) => {
            return option === value;
          }}
          renderOption={(props, option) => <li {...props}>{option}</li>}
          value={nodeGroup.active}
          options={nodeGroup.options}
          onChange={(event, newValue) => setNodeGroup({...nodeGroup, active: newValue})}
        />
      </MDBox>
      
      <MDBox px={2} pt={2}>
        <Autocomplete selectOnFocus clearOnBlur disableClearable
          renderInput={(params) => (
            <TextField {...params} variant="standard" label={"Select Processing Node"}/>
          )}
          isOptionEqualToValue={(option, value) => {
            return option === value;
          }}
          renderOption={(props, option) => <li {...props}>{option}</li>}
          value={nodeType.active}
          options={nodeType.options}
          onChange={(event, newValue) => setNodeType({...nodeType, active: newValue})}
        />
      </MDBox>
      
      <MDBox p={2}>
        <MDButton color={"secondary"} 
          onClick={onClose}
        >
          Cancel
        </MDButton>
        <MDButton color={"info"} 
          onClick={() => {
            for (let i in processingNodes) {
              if (processingNodes[i].Type == nodeType.active) {
                onSetProcessingNode(JSON.parse(JSON.stringify({
                  ...processingNodes[i],
                  Id: uuidv4(),
                })));
              }
            }
          }} style={{marginLeft: 10}}
        >
          Update
        </MDButton>
      </MDBox>
    </DialogContent>
  )
}

export default ProcessingSelect;