/**
=========================================================
* UF BRAVO Platform
=========================================================

* Copyright 2025 by Jackson Cagle, Fixel Institute
* The source code is made available under a Creative Common NonCommercial ShareAlike License (CC BY-NC-SA 4.0) (https://creativecommons.org/licenses/by-nc-sa/4.0/) 

 =========================================================

* The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.
*/

import { createRef, useState, useMemo, useEffect } from "react";

import {
  Autocomplete,
  Grid,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  TextField,
  Tooltip, IconButton
} from "@mui/material";

import { createFilterOptions } from "@mui/material/Autocomplete";

import MDBox from "components/MDBox";
import MDTypography from "components/MDTypography";
import MDInput from "components/MDInput";
import MDButton from "components/MDButton";
import DropzoneUploader from "components/DropzoneUploader";

import { FaCopy } from "react-icons/fa";

import { SessionController } from "database/session-control";
import { usePlatformContext, setContextState } from "context";
import { dictionary, dictionaryLookup } from "assets/translation";

const filter = createFilterOptions();

function EditDeviceInfoView({show, deviceInfo, onUpdate, onCancel}) {
  const [controller, dispatch] = usePlatformContext();
  const { language, participant_uid } = controller;

  const [editDeviceInfo, setEditDeviceInfo] = useState({});
  
  useEffect(() => {
    if (!deviceInfo) return;
    setEditDeviceInfo({...deviceInfo});
  }, [deviceInfo]);

  return useMemo(() => Object.keys(editDeviceInfo).length > 0 ? (
    <Dialog open={show} onClose={() => {
      onCancel();
      setEditDeviceInfo({...deviceInfo});
    }}>
      
      <MDBox px={2} pt={2} display={"flex"} flexDirection={"row"} justifyContent={"center"} alignItems={"center"}>
        <MDTypography variant="h5">
          {"Edit Device Information"}
        </MDTypography>
        <Tooltip title={"Click to Copy Device Unique Identifier"}>
          <IconButton onClick={() => {
            navigator.clipboard.writeText(editDeviceInfo.Id);
          }}>
            <FaCopy />
          </IconButton>
        </Tooltip>
      </MDBox>
      <DialogContent>
        <Grid container spacing={2}>
          <Grid item xs={12}>
            <TextField
              id="device-name"
              name="device-name"
              variant="standard"
              margin="dense"
              label="Device Name"
              placeholder="Device Name"
              value={editDeviceInfo.Name}
              onChange={(event) => setEditDeviceInfo({...editDeviceInfo, Name: event.target.value})}
              fullWidth
              autoComplete="off"
            />
          </Grid>
          {editDeviceInfo.Electrodes.map((lead, index) => (
            <Grid key={lead.Target} item xs={6}>
              <TextField
                id={`lead-name-${index}`}
                name={`lead-name-${index}`}
                variant="standard"
                margin="dense"
                label={`Lead #${index+1}`}
                placeholder={lead.Target}
                value={lead.CustomName}
                onChange={(event) => setEditDeviceInfo({...editDeviceInfo, Electrodes: editDeviceInfo.Electrodes.map((oldLead, oldIndex) => {
                  if (index == oldIndex) return {...oldLead, CustomName: event.target.value};
                  return oldLead;
                })})}
                fullWidth
                autoComplete="off"
              />
            </Grid>
          ))}
        </Grid>
      </DialogContent>
      <DialogActions>
        <MDBox style={{marginLeft: "auto", paddingRight: 5}}>
          <MDButton color={"secondary"} 
            onClick={onCancel}
          >
            Cancel
          </MDButton>
          <MDButton color={"info"} 
            onClick={() => onUpdate(editDeviceInfo)} style={{marginLeft: 10}}
          >
            Update
          </MDButton>
        </MDBox>
      </DialogActions>
    </Dialog>
  ) : null, [editDeviceInfo, show]);
}

export default EditDeviceInfoView;