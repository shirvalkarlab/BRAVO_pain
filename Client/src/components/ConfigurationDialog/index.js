/**
=========================================================
* UF BRAVO Platform
=========================================================

* Copyright 2025 by Jackson Cagle, Fixel Institute
* The source code is made available under a Creative Common NonCommercial ShareAlike License (CC BY-NC-SA 4.0) (https://creativecommons.org/licenses/by-nc-sa/4.0/) 

 =========================================================

* The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.
*/

import { useEffect, useState, useCallback, useMemo, memo } from "react";
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

function ConfigurationDialog({show, setShow, setAlert}) {
  
  const [configGroup, setConfigGroup] = useState({active: "", options: []});
  const [config, setConfig] = useState({});

  useEffect(() => {
    SessionController.query("/api/queryAnalysisConfigurations", {
      RequestType: "QueryConfigurations"
    }).then((response) => {
      setConfig(response.data);
      const groupOptions = Object.keys(response.data);
      setConfigGroup({active: groupOptions[0], options: groupOptions});
    }).catch((error) => {
      SessionController.displayError(error, setAlert);
    });
  }, [])

  useEffect(() => {
    
  }, [])

  return useMemo(() => (
    <Dialog open={show} onClose={() => setShow(false)} 
      PaperProps={{ sx: {minWidth: { xs: "100vw", sm: 900 }, maxHeight: "100vh"} }}
    >
      <DialogContent>
        <MDBox px={2} pt={2}>
          <MDTypography variant="h5">
          {"Change Global Processing Configurations"}
          </MDTypography>
        </MDBox>
        
        <MDBox px={2} pt={2}>
          <Autocomplete selectOnFocus clearOnBlur disableClearable
            renderInput={(params) => (
              <TextField {...params} variant="standard" label={"Select Configuration Group"}/>
            )}
            isOptionEqualToValue={(option, value) => {
              return option === value;
            }}
            renderOption={(props, option) => <li {...props}>{option}</li>}
            value={configGroup.active}
            options={configGroup.options}
            onChange={(event, newValue) => setConfigGroup({...configGroup, active: newValue})}
          />
        </MDBox>

        <MDBox px={2} pt={4}>
          <Grid container spacing={1}>
            {config[configGroup.active] ? (
              Object.keys(config[configGroup.active]).map((key) => {
                return <Grid item xs={12} key={key}>
                  <Autocomplete selectOnFocus clearOnBlur disableClearable
                    renderInput={(params) => (
                      <TextField {...params} variant="standard" label={config[configGroup.active][key].name}/>
                    )}
                    isOptionEqualToValue={(option, value) => {
                      return option === value;
                    }}
                    renderOption={(props, option) => <li {...props}>{option}</li>}
                    value={config[configGroup.active][key].value}
                    options={config[configGroup.active][key].options}
                    onChange={(event, newValue) => setConfig((config) => {
                      config[configGroup.active][key].value = newValue;
                      return {...config};
                    })}
                  />
                </Grid>
              })
            ) : null}
          </Grid>
        </MDBox>
        
        <MDBox p={2}>
          <MDButton color={"secondary"} 
            onClick={() => setShow(false)}
          >
            {"Cancel"}
          </MDButton>
          <MDButton color={"info"} 
            onClick={() => {
              SessionController.query("/api/queryAnalysisConfigurations", {
                RequestType: "UpdateConfigurations",
                Configurations: config
              }).then((response) => {
                setConfig(response.data);
                setShow(false)
              }).catch((error) => {
                SessionController.displayError(error, setAlert);
              });
            }} style={{marginLeft: 10}}
          >
            {"Update"}
          </MDButton>
        </MDBox>
      </DialogContent>
    </Dialog>
  ), [show, configGroup, config])
}

export default ConfigurationDialog;