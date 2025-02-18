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

import LoadingProgress from "components/LoadingProgress";
import MDBox from "components/MDBox";
import MDTypography from "components/MDTypography";
import MDButton from "components/MDButton";
import MuiAlertDialog from "components/MuiAlertDialog";

import { IoMdCheckmarkCircle } from "react-icons/io";

import { SessionController } from "database/session-control";
import { select } from "react-cookies";

function AddStudy({onClose, onAddStudy, setAlert}) {

  const [studyCode, setStudyCode] = useState("");

  return (
    <DialogContent>
      <MDBox px={2} pt={2}>
        <MDTypography variant="h5">
          {"Add Study Access"}
        </MDTypography>
      </MDBox>
      
      <MDBox px={2} pt={2}>
        <TextField
          variant="standard" margin="dense" id="study-name"
          value={studyCode}
          onChange={(event) => setStudyCode(event.target.value)}
          label={"Study Code (Required)"} type="text"
          fullWidth
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
            onAddStudy(studyCode);
            onClose();
          }} style={{marginLeft: 10}}
        >
          Update
        </MDButton>
      </MDBox>
    </DialogContent>
  )
}

export default AddStudy;