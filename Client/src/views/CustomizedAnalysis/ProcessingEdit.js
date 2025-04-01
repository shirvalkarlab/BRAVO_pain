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

import moment from "moment";
import { AdapterMoment } from '@mui/x-date-pickers/AdapterMoment';
import { LocalizationProvider } from '@mui/x-date-pickers/LocalizationProvider';
import { DatePicker } from '@mui/x-date-pickers/DatePicker';
import { TimePicker } from "@mui/x-date-pickers";

import { v4 as uuidv4 } from 'uuid';

import { SessionController } from "database/session-control";

function ProcessingEdit({editNode, onClose, onSetProcessingNode}) {

  const [nodeConfig, setNodeConfig] = useState({Configurations: []});
  const [timerange, setTimerange] = useState({start: null, end: null});

  useEffect(() => {
    if (!editNode) return;
    setNodeConfig(editNode.data);
  }, [editNode]);
  
  return (
    <DialogContent>
      <MDBox px={2} pt={2}>
        <MDTypography variant="h5">
          {"Edit "}{nodeConfig.Type}
        </MDTypography>
      </MDBox>
      
      {nodeConfig.Configurations.map((a, index) => {
        if (a.Type == "SelectSingle") {
          return (
            <MDBox key={a.Id} px={2} pt={2}>
              <Autocomplete selectOnFocus clearOnBlur disableClearable
                renderInput={(params) => (
                  <TextField {...params} variant="standard" label={a.Label}/>
                )}
                isOptionEqualToValue={(option, value) => {
                  return option === value;
                }}
                renderOption={(props, option) => <li {...props}>{option}</li>}
                value={a.Value === undefined ? a.Default : a.Value}
                options={a.Options}
                onChange={(event, newValue) => setNodeConfig((nodeConfig) => {
                  nodeConfig.Configurations[index].Value = newValue;
                  return {...nodeConfig}
                })}
              />
            </MDBox>
          );
        } else if (a.Type == "Input") {
          return (
            <MDBox key={a.Id} px={2} pt={2}>
              <TextField id={a.Type + "_" + a.Id} variant="standard" label={a.Label} fullWidth
                placeholder={a.Default}
                value={a.Value === undefined ? "" : a.Value}
                onChange={(event) => setNodeConfig((nodeConfig) => {
                  nodeConfig.Configurations[index].Value = event.target.value;
                  return {...nodeConfig}
                })}
              />
            </MDBox>
          );
        } else if (a.Type == "Date") {
          return (
            <MDBox key={a.Id} px={2} pt={2}>
              <MDBox p={2} display={"flex"} flexDirection={"row"}>
                <LocalizationProvider dateAdapter={AdapterMoment} adapterLocale={"us"}>
                  <DatePicker
                    label={a.Label + " Date"}
                    value={a.Value === undefined ? "" : a.Value}
                    onChange={(newDate) => {
                      setNodeConfig((nodeConfig) => {
                        nodeConfig.Configurations[index].Value = newDate;
                        return {...nodeConfig}
                      })
                    }}
                    renderInput={(params) => <TextField {...params} />}
                  />
                </LocalizationProvider>
                <LocalizationProvider dateAdapter={AdapterMoment}>
                  <TimePicker
                    label={a.Label + " Time"}
                    value={a.ValueTime === undefined ? "" : a.ValueTime}
                    onChange={(newDate) => {
                      setNodeConfig((nodeConfig) => {
                        nodeConfig.Configurations[index].ValueTime = newDate;
                        return {...nodeConfig}
                      })
                    }}
                    renderInput={(params) => <TextField {...params} />}
                  />
                </LocalizationProvider>
              </MDBox>
            </MDBox>
          );
        }
      })}
      
      <MDBox p={2} display={"flex"} flexDirection={"row"} justifyContent={"space-between"}>
        <MDBox p={2} display={"flex"} flexDirection={"row"}>
          <MDButton color={"secondary"} 
            onClick={onClose}
          >
            Cancel
          </MDButton>
          <MDButton color={"info"} 
            onClick={() => {
              nodeConfig.Configurations = nodeConfig.Configurations.map((a) => {
                if (a.Type == "Date") {
                  let date = 0;
                  if (a.Value && a.ValueTime) {
                    if (!a.Value.toISOString) {
                      a.Value = moment(a.Value);
                    } 
                    if (!a.ValueTime.toISOString) {
                      a.ValueTime = moment(a.ValueTime);
                    }
                    date = new Date(a.Value.toISOString().split("T")[0] + "T" + a.ValueTime.toISOString().split("T")[1]).getTime();
                    date -= (a.Value.utcOffset() - a.ValueTime.utcOffset()) * 60000;
                    a.Value = date; 
                    a.ValueTime = date;
                  }
                }
                return a;
              });

              onSetProcessingNode({
                ...editNode,
                data: nodeConfig
              });
            }} style={{marginLeft: 10}}
          >
            Update
          </MDButton>
        </MDBox>
        <MDBox p={2} display={"flex"} flexDirection={"row"}>
        <MDButton color={"error"} 
          onClick={() => {
            onSetProcessingNode(null);
          }}
        >
          Delete
        </MDButton>
        </MDBox>
      </MDBox>
    </DialogContent>
  )
}

export default ProcessingEdit;