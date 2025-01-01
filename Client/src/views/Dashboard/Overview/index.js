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
  Grid,
  Dialog,
  Autocomplete,
} from "@mui/material";

import MDBox from "components/MDBox";
import MDTypography from "components/MDTypography";
import MDInput from "components/MDInput";
import MDButton from "components/MDButton";

import FormField from "components/MDInput/FormField.js";
import SessionPasswordView from "./SessionPasswordView";
import ParticipantTable from "components/Tables/ParticipantTable";
import DatabaseLayout from "layouts/DatabaseLayout";

import { SessionController } from "database/session-control";
import { usePlatformContext, setContextState } from "context";
import { dictionary, dictionaryLookup } from "assets/translation";
import LoadingProgress from "components/LoadingProgress";

function DatabaseStatistic({title, description, value}) {
  return (
    <Card>
      <MDBox p={2}>
        <Grid container>
          <Grid item xs={7}>
            <MDBox mb={0.5} lineHeight={1}>
              <MDTypography
                variant="button"
                fontWeight="medium"
                color="text"
                textTransform="capitalize"
              >
                {title}
              </MDTypography>
            </MDBox>
            <MDBox lineHeight={1}>
              <MDTypography variant="h5" fontWeight="bold">
                {value}
              </MDTypography>
            </MDBox>
          </Grid>
          <Grid item xs={5}>
            <MDBox width="100%" textAlign="right" lineHeight={1}>
              <MDTypography
                variant="caption"
                color="secondary"
                fontWeight="regular"
                sx={{ cursor: "pointer" }}
              >
                {description}
              </MDTypography>
            </MDBox>
          </Grid>
        </Grid>
      </MDBox>
    </Card>
  );
}

export default function DashboardOverview() {
  const [controller, dispatch] = usePlatformContext();
  const { user, language } = controller;
  const [alert, setAlert] = useState(null);

  const [databaseInfo, setDatabaseInfo] = useState({
    participants: 0,
    totalRecordings: 0,
    totalStorage: "0 Bytes",
  });

  const [currentStudy, setCurrentStudy] = useState(false);
  const [filteredParticipants, setFilteredParticipants] = useState([]);
  const [filterOptions, setFilterOptions] = useState({});
  const [availableParticipants, setAvailableParticipants] = useState(false);
  const [uploadInterface, setUploadInterface] = useState(null);
  const [showDecryptionPassword, setShowDecryptionPassword] = useState(false);

  useEffect(() => {
    SessionController.query("/api/queryParticipants", {
      ParticipantGroupId: user.InstituteId
    }).then((response) => {
      setAvailableParticipants(response.data);
    }).catch((error) => {
      SessionController.displayError(error, setAlert);
    });
    setContextState(dispatch, "report", "");
  }, []);

  const handleParticipantFilter = (event) => {
    setFilterOptions({value: event.currentTarget.value});
  };

  const onEncryptionUpdated = (password) => {
    SessionController.query("/api/getFernetKey", {password: password}).then((response) => {
      SessionController.setDecryptionPassword(response.data.key, response.data.shift);
      setShowDecryptionPassword(false);

      setAvailableParticipants((availableParticipants) => {
        for (let i in availableParticipants.studies) {
          for (let j in availableParticipants.participants[availableParticipants.studies[i].uid]) {
            availableParticipants.participants[availableParticipants.studies[i].uid][j].name = SessionController.decodeMessage(availableParticipants.participants[availableParticipants.studies[i].uid][j].name);
          }
        }
        return {...availableParticipants};
      });
    })
  };
  
  useEffect(() => {
    const filterTimer = setTimeout(() => {
      if (availableParticipants.length == 0) return;
      
      if (filterOptions.value) {
        const options = filterOptions.value.split(" ");
        setFilteredParticipants(availableParticipants.filter((participant) => {
          let state = true;
          for (var option of options) {
            const optionLower = option.toLowerCase();
            state = state && (
              participant.Id.toLowerCase().includes(optionLower) || 
              participant.MRN.toLowerCase().includes(optionLower) || 
              participant.Name.toLowerCase().includes(optionLower) || 
              participant.Diagnosis.toLowerCase().includes(optionLower) || 
              participant.Tags.filter((tag) => tag.toLowerCase().includes(optionLower)).length > 0
            );
          }
          return state;
        }));
      } else {
        setFilteredParticipants([...availableParticipants]);
      }
    }, 200);
    return () => clearTimeout(filterTimer);
  }, [filterOptions, availableParticipants]);

  const currentDate = new Date();

  return (
    <DatabaseLayout>
      {alert}
      {availableParticipants ? (
      <MDBox mt={2}>
        <Card>
          <MDBox p={2}>
            <Grid container spacing={2}>
              <Grid item sm={12}>
                <MDTypography variant="h3">
                  {dictionary.Dashboard.ParticipantTable[language]}
                </MDTypography>
              </Grid>
              <Grid item sm={6} md={6} display="flex" sx={{
                justifyContent: {
                  sm: "space-between",
                  md: "end"
                }
              }}>
                <MDInput label={dictionary.Dashboard.SearchParticipant[language]} value={filterOptions.text} onChange={(value) => handleParticipantFilter(value)} sx={{paddingRight: 2, width: "100%"}}/>
              </Grid>
              <Grid item xs={12} sx={{marginTop: 2}}>
                <ParticipantTable data={filteredParticipants} />
              </Grid>
            </Grid>
          </MDBox>
        </Card>
      </MDBox>
      ) : ( <LoadingProgress /> )}
    </DatabaseLayout>
  );
};

