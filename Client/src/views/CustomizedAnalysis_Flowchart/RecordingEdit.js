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
  DialogActions,
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
import { Edit as EditIcon } from "@mui/icons-material"

import { FixedSizeList } from 'react-window';
import MDBox from "components/MDBox";
import MDTypography from "components/MDTypography";
import MDButton from "components/MDButton";
import MuiAlertDialog from "components/MuiAlertDialog";

import { v4 as uuidv4 } from 'uuid';

import { SessionController } from "database/session-control";

function RecordingEdit({editNode, onClose, onSetRecordingNode}) {

  const [nodeConfig, setNodeConfig] = useState({Alignment: 0, Metadata: {ChannelNames: []}});
  const [channelNameEdit, setChannelNameEdit] = useState({index: -1, name: ""})

  useEffect(() => {
    if (!editNode) return;
    setNodeConfig(editNode.data);
  }, [editNode]);
  
  const renderChannelLists = ({index, style}) => {
    let show = true;
    let customName = nodeConfig.Metadata.ChannelNames[index];
    
    const handleToggleSingle = () => {
      
    };

    const handleDoubleClick = () => {
      
    };

    var updateTimeout = null;
    var singleClicked = false;
    const onClick = () => {
      if (singleClicked) {
        singleClicked = false;
        handleDoubleClick();
        clearTimeout(updateTimeout);
      } else {
        singleClicked = true;
        updateTimeout = setTimeout(function() {
          handleToggleSingle();
          singleClicked = false
        }, 200);
      }
    };

    return (
      <ListItem style={style} key={index} 
        secondaryAction={
          <IconButton edge="end" aria-label="comments" onClick={() => {
            setChannelNameEdit({index: index, name: customName});
          }} sx={{marginRight: 1}}>
            <EditIcon />
          </IconButton>
        }
        disablePadding>
        <ListItemButton onClick={onClick} dense>
          <ListItemIcon>
            <Checkbox
              edge="start"
              checked={show}
              tabIndex={-1}
              disableRipple
            />
          </ListItemIcon>
          <ListItemText primary={customName} />
        </ListItemButton>
      </ListItem>
    )
  };

  return (
    <DialogContent>
      <MDBox px={2} pt={2}>
        <MDTypography variant="h5">
          {"Edit "}{nodeConfig.Name ? nodeConfig.Name : nodeConfig.Id}
        </MDTypography>
      </MDBox>
      
      <MDBox>
        <TextField
          variant="standard"
          margin="dense" type={"number"}
          value={nodeConfig.Alignment}
          placeholder={"0"}
          onChange={(event) => setNodeConfig((nodeConfig) => {
            nodeConfig.Alignment = parseFloat(event.target.value);
            return {...nodeConfig}
          })}
          label={"Time Adjustment (sec)"}
          autoComplete={"off"}
          fullWidth
        />
        <TextField
          variant="standard"
          margin="dense"
          value={nodeConfig.Metadata.Label}
          onChange={(event) => setNodeConfig((nodeConfig) => {
            nodeConfig.Metadata.Label = event.target.value;
            return {...nodeConfig}
          })}
          label={"Recording Label (Description)"} type={"text"}
          autoComplete={"off"}
          fullWidth
        />
      </MDBox>
      <MDBox style={{ width: '100%', height: 400, bgcolor: 'background.paper', marginTop: 15}}>
        <MDTypography variant="h5">
          {"Channels Selection"}
        </MDTypography>
        <FixedSizeList height={380} width={"100%"} itemSize={36} itemCount={nodeConfig.Metadata.ChannelNames.length} overscanCount={5}>
          {renderChannelLists}
        </FixedSizeList>
      </MDBox>

      <Dialog open={channelNameEdit.index >= 0} onClose={() => setChannelNameEdit({index: -1, name: ""})}>
        <DialogContent>
          <Grid container spacing={2}>
            <Grid item xs={12}>
              <TextField
                id="recording-channelname-edit"
                variant="standard"
                margin="dense"
                label="Channel Name"
                placeholder={nodeConfig.Metadata.ChannelNames[channelNameEdit.index]}
                value={channelNameEdit.name}
                onChange={(event) => setChannelNameEdit({...channelNameEdit, name: event.target.value})}
                fullWidth
              />
            </Grid>
            
          </Grid>
        </DialogContent>
        <DialogActions>
          <MDBox style={{marginLeft: "auto", paddingRight: 5}}>
            <MDButton color={"secondary"} 
              onClick={() => setChannelNameEdit({index: -1, name: ""})}
            >
              Cancel
            </MDButton>
            <MDButton color={"info"} style={{marginLeft: 10}}
              onClick={() => setNodeConfig((nodeConfig) => {
                nodeConfig.Metadata.ChannelNames[channelNameEdit.index] = channelNameEdit.name;
                setChannelNameEdit({index: -1, name: ""})
                return {...nodeConfig}
              })}
            >
              Update
            </MDButton>
          </MDBox>
        </DialogActions>
      </Dialog>
      
      <MDBox p={2}>
        <MDButton color={"success"} 
          onClick={() => {
            onSetRecordingNode({...editNode, data: {...nodeConfig}});
          }}
        >
          Update
        </MDButton>
      </MDBox>
    </DialogContent>
  )
}

export default RecordingEdit;