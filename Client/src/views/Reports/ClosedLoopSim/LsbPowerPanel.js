/**
 * Phase C panel: anchor the Phase-B cut-point to deployable device LSB units + power / sample-size.
 *
 * Fetches /api/queryLsbPower with the cut-point lifted from the Phase-B ROC panel and renders three
 * blocks, in descending order of how much weight the clinician should give them:
 *   1) THRESHOLD TO PROGRAM — the percentile-anchored device-LSB threshold (the deployable number),
 *      or an honest "device never sensed this band" notice for off-band candidates.
 *   2) Power / sample-size — current power vs AUC=0.5 on the count of independent ratings, and the
 *      ratings needed for 80% power (a clear "enough data yet?" verdict).
 *   3) Empirical µV²/LSB ratio — a confidence-rated FYI cross-check, explicitly NOT the deployable
 *      number.
 */
import { useEffect, useState } from "react";

import { Card, Grid } from "@mui/material";
import MDBox from "components/MDBox";
import MDTypography from "components/MDTypography";

import { SessionController } from "database/session-control";

const fmt = (v, d = 2) => (v == null || !Number.isFinite(Number(v)) ? "—" : Number(v).toFixed(d));

function StatBox({ label, value, sub, color }) {
  return (
    <MDBox sx={{ textAlign: "center", px: 1 }}>
      <MDTypography variant="caption" sx={{ fontSize: 9.5, color: "#999", fontWeight: "bold" }}>
        {label}
      </MDTypography>
      <MDTypography variant="h6" sx={{ fontSize: 17, color: color || "#344767", lineHeight: 1.1 }}>
        {value}
      </MDTypography>
      {sub ? (
        <MDTypography variant="caption" sx={{ fontSize: 9, color: "#999" }}>{sub}</MDTypography>
      ) : null}
    </MDBox>
  );
}

function LsbPowerPanel({ participantUid, bandCandidate, requestParams, cutpoint }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState(null);

  const bc = bandCandidate || {};
  const channelRaw = bc.contact;
  const centerHz = bc.center_freq_hz;
  const bandWidthHz = bc.bandwidth_hz || 5.0;
  const cutThr = cutpoint ? cutpoint.threshold : null;
  const matchDir = cutpoint ? cutpoint.matchDir : "prior";

  useEffect(() => {
    if (!participantUid || channelRaw == null || centerHz == null || cutThr == null) {
      setData(null);
      return;
    }
    setLoading(true); setErr(null);
    SessionController.query("/api/queryLsbPower", {
      ParticipantId: participantUid,
      Channel: channelRaw,
      CenterHz: Number(centerHz),
      BandWidthHz: Number(bandWidthHz),
      MatchDirection: matchDir,
      Cutpoint: Number(cutThr),
      ...requestParams,
    }).then((response) => {
      const d = response && response.data;
      if (d && d.available) setData(d);
      else { setData(null); setErr((d && d.reason) || "unavailable"); }
      setLoading(false);
    }).catch(() => { setData(null); setErr("request failed"); setLoading(false); });
  }, [participantUid, channelRaw, centerHz, bandWidthHz, matchDir, cutThr, requestParams]);

  const tl = data && data.threshold_lsb;
  const pw = data && data.power;
  const lr = data && data.lsb_ratio;

  return (
    <Card sx={{ width: "100%" }}>
      <MDBox p={2}>
        <MDTypography variant="h6" sx={{ fontSize: 14, mb: 1 }}>
          LSB threshold + power / sample-size
        </MDTypography>

        {cutThr == null ? (
          <MDTypography variant="caption" color="text" sx={{ fontStyle: "italic", fontSize: 11 }}>
            Choose a cut-point in the ROC panel — the deployable LSB threshold and power readout
            anchor to it.
          </MDTypography>
        ) : loading ? (
          <MDTypography variant="caption" color="text" sx={{ fontStyle: "italic", fontSize: 11 }}>
            Anchoring to device Timeline LSB + computing power…
          </MDTypography>
        ) : err ? (
          <MDTypography variant="caption" sx={{ fontSize: 11, color: "#9A3324" }}>
            {`Unavailable: ${err}.`}
          </MDTypography>
        ) : data ? (
          <>
            {/* 1) THRESHOLD TO PROGRAM */}
            {tl && tl.available ? (
              <MDBox p={1.2} mb={1.2} sx={{ backgroundColor: "#eef5ff", borderRadius: "6px",
                border: "1px solid #cfe0fb" }}>
                <MDTypography variant="caption" sx={{ fontSize: 10, fontWeight: "bold", color: "#1A73E8" }}>
                  THRESHOLD TO PROGRAM (device LSB)
                </MDTypography>
                <MDTypography variant="h4" sx={{ fontSize: 26, color: "#1A73E8", lineHeight: 1.1 }}>
                  {`power ≥ ${fmt(tl.upper_lsb, 1)} LSB`}
                </MDTypography>
                <MDTypography variant="caption" display="block" color="text" sx={{ fontSize: 10, mt: 0.3 }}>
                  {`p${fmt(tl.percentile, 0)} of the device's own Timeline band power · `
                    + `${tl.n_timeline_samples} in-band samples · device LSB p10/median/p90 `
                    + `${fmt(tl.device_lsb_p10, 0)} / ${fmt(tl.device_lsb_median, 0)} / ${fmt(tl.device_lsb_p90, 0)}`}
                </MDTypography>
                <MDTypography variant="caption" display="block" sx={{ fontSize: 9.5, color: "#777", mt: 0.4 }}>
                  Percentile-anchored on the device Timeline — no µV²↔LSB conversion needed.
                </MDTypography>
              </MDBox>
            ) : (
              <MDBox p={1.2} mb={1.2} sx={{ backgroundColor: "#fff6e6", borderRadius: "6px",
                border: "1px solid #f3d99b" }}>
                <MDTypography variant="caption" sx={{ fontSize: 10, fontWeight: "bold", color: "#B17500" }}>
                  NO DEPLOYABLE LSB THRESHOLD
                </MDTypography>
                <MDTypography variant="caption" display="block" sx={{ fontSize: 11, mt: 0.3 }}>
                  {(tl && tl.reason) || "unavailable"}
                  {tl && tl.hint ? ` — ${tl.hint}` : ""}
                </MDTypography>
              </MDBox>
            )}

            {/* 2) POWER / SAMPLE-SIZE */}
            {pw && pw.available ? (
              <MDBox mb={1.2}>
                <Grid container alignItems="center">
                  <Grid item xs={4}>
                    <StatBox label="POWER (vs AUC 0.5)" value={`${fmt(pw.power_current * 100, 0)}%`}
                      color={pw.power_current >= 0.8 ? "#0a7f3f" : "#B17500"}
                      sub={`α=${fmt(pw.alpha, 2)}`} />
                  </Grid>
                  <Grid item xs={4}>
                    <StatBox label="RATINGS NOW" value={pw.n_ratings_current}
                      sub="independent" />
                  </Grid>
                  <Grid item xs={4}>
                    <StatBox label="NEED FOR 80%" value={pw.n_ratings_needed ?? "—"}
                      color={pw.more_data_needed ? "#B17500" : "#0a7f3f"}
                      sub={pw.more_data_needed ? "more data" : "sufficient"} />
                  </Grid>
                </Grid>
                <MDTypography variant="caption" display="block" color="text" sx={{ fontSize: 9.5, mt: 0.4, textAlign: "center" }}>
                  {pw.more_data_needed
                    ? `Underpowered: ~${(pw.n_ratings_needed - pw.n_ratings_current)} more independent pain ratings needed for 80% power.`
                    : "Adequately powered at the current rating count."}
                </MDTypography>
              </MDBox>
            ) : (
              <MDTypography variant="caption" color="text" sx={{ fontSize: 10 }}>
                {`Power: ${(pw && pw.reason) || "unavailable"}.`}
              </MDTypography>
            )}

            {/* 3) µV²/LSB RATIO (FYI) */}
            <MDBox p={1} sx={{ backgroundColor: "#f7f7f8", borderRadius: "6px" }}>
              <MDTypography variant="caption" sx={{ fontSize: 9.5, fontWeight: "bold", color: "#999" }}>
                EMPIRICAL µV²/LSB RATIO — FYI cross-check, not the deployable number
              </MDTypography>
              {lr && lr.available ? (
                <MDTypography variant="caption" display="block" sx={{ fontSize: 10.5, mt: 0.2 }}>
                  {`median ${lr.median.toExponential(2)} µV²/LSB `}
                  <span style={{ color: lr.confidence === "low" ? "#9A3324" : "#B17500", fontWeight: "bold" }}>
                    {`(confidence: ${lr.confidence})`}
                  </span>
                  {` · CV ${fmt(lr.cv)} · ${fmt(lr.fold_off_rule, 2)}× the 0.01 rule · n=${lr.n} paired sessions`}
                </MDTypography>
              ) : (
                <MDTypography variant="caption" display="block" sx={{ fontSize: 10.5, mt: 0.2, color: "#777" }}>
                  {(lr && lr.reason) || "unavailable"}
                </MDTypography>
              )}
            </MDBox>
          </>
        ) : null}
      </MDBox>
    </Card>
  );
}

export default LsbPowerPanel;
