/**
=========================================================
* UF BRAVO Platform -- Pain Biomarkers report (Shirvalkar Lab)
=========================================================
* Renders the selectable-source biomarker timeline (time-domain PSD<->pain and/or the
* ~10-min chronic LFP threshold detector) returned by /api/queryBiomarkerAnalysis.
*/

import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { Card, Grid, ToggleButton, ToggleButtonGroup } from "@mui/material";

import MDBox from "components/MDBox";
import MDTypography from "components/MDTypography";
import LoadingProgress from "components/LoadingProgress";

import BiomarkerTimeline from "./BiomarkerTimeline";
import BiomarkerAnalytics from "./BiomarkerAnalytics";

import DatabaseLayout from "layouts/DatabaseLayout";

import { SessionController } from "database/session-control";
import { usePlatformContext, setContextState } from "context.js";

function Biomarkers() {
  const navigate = useNavigate();
  const [controller, dispatch] = usePlatformContext();
  const { language } = controller;
  const { participant_uid } = useParams();

  const [data, setData] = useState(false);
  const [source, setSource] = useState("both");
  const [alert, setAlert] = useState(null);

  useEffect(() => {
    if (!participant_uid) {
      navigate("/database", { replace: false });
      return;
    }
    setContextState(dispatch, "report", "GeneralReports");

    setAlert(<LoadingProgress />);
    SessionController.query("/api/queryBiomarkerAnalysis", {
      ParticipantId: participant_uid,
      source: source,
    }).then((response) => {
      setData(response.data);
      setAlert(null);
    }).catch((error) => {
      SessionController.displayError(error, setAlert);
    });
  }, [participant_uid, source]);

  const summaryLine = (label, s) => {
    if (!s) return null;
    if (s.best_threshold !== undefined) {
      return (
        <MDTypography variant="button" fontWeight="regular" color="text" display="block">
          {`${label}: threshold=${fmt(s.best_threshold)}  sens=${fmt(s.sens)}  spec=${fmt(s.spec)}  n_windows=${s.n_windows}`}
        </MDTypography>
      );
    }
    if (s.band !== undefined || s.freq_hz !== undefined) {
      return (
        <MDTypography variant="button" fontWeight="regular" color="text" display="block">
          {`${label}: ${s.channel || ""} ${fmt(s.freq_hz)} Hz  r=${fmt(s.r)}  p=${fmt(s.p)}`}
        </MDTypography>
      );
    }
    return null;
  };

  return (
    <>
      {alert}
      <DatabaseLayout>
        <MDBox pt={3}>
          <Grid container spacing={2}>
            <Grid item xs={12}>
              <Card sx={{ width: "100%" }}>
                <Grid container>
                  <Grid item xs={12}>
                    <MDBox p={2} display="flex" flexDirection="row" justifyContent="space-between" alignItems="center">
                      <MDTypography variant="h6" fontSize={24}>
                        {"Pain Biomarkers"}
                      </MDTypography>
                      <ToggleButtonGroup
                        value={source}
                        exclusive
                        size="small"
                        onChange={(e, v) => { if (v) setSource(v); }}
                      >
                        <ToggleButton value="timedomain">Time-domain</ToggleButton>
                        <ToggleButton value="chronic">Chronic</ToggleButton>
                        <ToggleButton value="both">Both</ToggleButton>
                      </ToggleButtonGroup>
                    </MDBox>
                  </Grid>

                  {data && data.message ? (
                    <Grid item xs={12}>
                      <MDBox p={2}>
                        <MDTypography variant="h6" color="error" fontSize={18}>
                          {data.message}
                        </MDTypography>
                        <MDTypography variant="button" color="text">
                          {"Upload a Percept session for this participant and configure REDCap (REDCAP_API_URL / REDCAP_API_TOKEN), then reload."}
                        </MDTypography>
                      </MDBox>
                    </Grid>
                  ) : null}

                  {data && data.summary ? (
                    <Grid item xs={12}>
                      <MDBox px={2} pb={1}>
                        {summaryLine("Time-domain", data.summary.timedomain)}
                        {summaryLine("Chronic", data.summary.chronic)}
                      </MDBox>
                    </Grid>
                  ) : null}

                  {data && data.timeline && data.timeline.length > 0 ? (
                    <Grid item xs={12}>
                      <BiomarkerTimeline data={data} figureTitle={"BiomarkerTimeline"} height={420} />
                    </Grid>
                  ) : null}
                </Grid>
              </Card>
            </Grid>

            {data && data.analytics ? (
              <BiomarkerAnalytics analytics={data.analytics} />
            ) : null}
          </Grid>
        </MDBox>
      </DatabaseLayout>
    </>
  );
}

function fmt(x) {
  if (x === null || x === undefined || Number.isNaN(x)) return "—";
  if (typeof x === "number") return Math.abs(x) >= 100 ? x.toFixed(1) : x.toFixed(3);
  return String(x);
}

export default Biomarkers;
