/**
=========================================================
* UF BRAVO Platform
=========================================================

* Copyright 2023 by Jackson Cagle, Fixel Institute
* The source code is made available under a Creative Common NonCommercial ShareAlike License (CC BY-NC-SA 4.0) (https://creativecommons.org/licenses/by-nc-sa/4.0/) 

 =========================================================

* The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.
*/

import { createRef, useState, memo, useMemo, useEffect } from "react";

import {
  Autocomplete,
  Grid,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  TextField,
  Icon,
  IconButton,
  Tooltip,
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

function EditParticipantInfoView({show, participantInfo, onUpdate, onCancel, removeParticipant}) {
  const [controller, dispatch] = usePlatformContext();
  const { language, participant_uid } = controller;

  const [tagOptions, setTagOptions] = useState([]);
  const [editParticipantInfo, setEditParticipantInfo] = useState({});

  useEffect(() => {
    setEditParticipantInfo({...participantInfo, MergeWith: ""});
  }, [participantInfo])

  return useMemo(() => (
    <Dialog open={show} onClose={() => {
      onCancel();
      setEditParticipantInfo({...participantInfo});
    }}>
      
      <MDBox px={2} pt={2} display={"flex"} flexDirection={"row"} justifyContent={"center"} alignItems={"center"}>
        <MDTypography variant="h5">
          {"Edit Participant Information"}
        </MDTypography>
        <Tooltip title={"Click to Copy Participant Unique Identifier"}>
          <IconButton onClick={() => {
            navigator.clipboard.writeText(participant_uid);
          }}>
            <FaCopy />
          </IconButton>
        </Tooltip>
      </MDBox>
      <DialogContent>
        <Grid container spacing={2}>
          <Grid item xs={12} md={6}>
            <TextField
              variant="standard"
              margin="dense" id="participant_name"
              value={editParticipantInfo.Name}
              onChange={(event) => setEditParticipantInfo({...editParticipantInfo, Name: event.target.value})}
              label={"Participant Name"} type="text"
              fullWidth
            />
          </Grid>
          <Grid item xs={12} md={6}>
            <TextField
              variant="standard"
              margin="dense" id="participant_diagnosis"
              value={editParticipantInfo.Diagnosis}
              onChange={(event) => setEditParticipantInfo({...editParticipantInfo, Diagnosis: event.target.value})}
              label={"Diagnosis"} type="text"
              fullWidth
            />
          </Grid>
          <Grid item xs={12} md={6}>
            <Autocomplete selectOnFocus clearOnBlur
              renderInput={(params) => (
                <TextField {...params} variant="standard" placeholder={"Select Sex/Gender (Optional)"} />
              )}
              isOptionEqualToValue={(option, value) => {
                return option === value;
              }}
              renderOption={(props, option) => <li {...props}>{option}</li>}
              value={editParticipantInfo.Sex ? editParticipantInfo.Sex : "Other"}
              options={["Male", "Female", "Other"]}
              onChange={(event, newValue) => setEditParticipantInfo({...editParticipantInfo, Sex: newValue})}
            />
          </Grid>
          <Grid item xs={12}>
            <Autocomplete
              multiple freeSolo
              value={editParticipantInfo.Tags}
              options={tagOptions}
              onChange={(event, newValue) => setEditParticipantInfo({...editParticipantInfo, Tags: newValue})}
              renderInput={(params) => {
                return <TextField
                  {...params}
                  variant="standard" id="participant_tags"
                  placeholder={dictionary.ParticipantOverview.TagNames[language]}
                />
              }}
            />
          </Grid>
          <Grid item xs={12}>
            <TextField
              variant="outlined"
              margin="dense" id="participant_mergedwith"
              value={editParticipantInfo.MergeWith}
              onChange={(event) => setEditParticipantInfo({...editParticipantInfo, MergeWith: event.target.value})}
              label={"Merge with (Enter Target Participant's BRAVO ID to move this record to another Participant Entry)"} type="text"
              fullWidth
            />
          </Grid>
          <Grid item xs={12} sx={{display: "flex", justifyContent: "space-between"}}>
            <MDBox style={{paddingLeft: 5}}>
              <MDButton color={"error"} 
                onClick={() => removeParticipant()}
              >
                Delete
              </MDButton>
            </MDBox>
            <MDBox style={{marginLeft: "auto", paddingRight: 5}}>
              <MDButton color={"secondary"} style={{marginLeft: 10}} 
                onClick={onCancel}
              >
                Cancel
              </MDButton>
              <MDButton color={"info"} 
                onClick={() => onUpdate(editParticipantInfo)} style={{marginLeft: 10}}
              >
                Update
              </MDButton>
            </MDBox>
          </Grid>
        </Grid>
      </DialogContent>
    </Dialog>
  ), [editParticipantInfo, show])
}

export default EditParticipantInfoView;