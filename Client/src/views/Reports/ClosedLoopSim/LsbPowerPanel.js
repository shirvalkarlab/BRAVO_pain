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
import { useEffect, useRef, useState } from "react";
import Plotly from "plotly.js-dist";

import { Card } from "@mui/material";
import MDBox from "components/MDBox";
import MDTypography from "components/MDTypography";

import { SessionController } from "database/session-control";
import PAL from "./palette";

const fmt = (v, d = 2) => (v == null || !Number.isFinite(Number(v)) ? "—" : Number(v).toFixed(d));

function LsbPowerPanel({ participantUid, bandCandidate, requestParams, cutpoint }) {
  const pwRef = useRef(null);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState(null);

  const bc = bandCandidate || {};
  const channelRaw = bc.contact;
  const centerHz = bc.center_freq_hz;
  const bandWidthHz = bc.bandwidth_hz || 5.0;
  const cutThr = cutpoint ? cutpoint.threshold : null;
  const matchDir = cutpoint ? cutpoint.matchDir : "prior";
  const cutDegenerate = !!(cutpoint && cutpoint.degenerate);

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
  const rvp = data && data.recommended_vs_programmed;   // audit C10: recommended-vs-programmed Δ

  // Draw the POWER-vs-N sufficiency curve once per payload: power to reject AUC=0.5 as the count of
  // independent ratings grows, with the 80% target line, and markers at the current N and the N
  // needed for 80% power. This replaces a 3-number readout a reviewer flagged — a clinician asking
  // "do I have enough pain ratings yet?" reads the answer off the curve's shape and the gap between
  // the two markers, not three separate figures. Plotly.react updates in place (no rebuild).
  useEffect(() => {
    const gd = pwRef.current;
    const curve = pw && pw.available && pw.curve;
    if (!gd || !curve || !Array.isArray(curve.n) || curve.n.length < 2) return;
    const tgt = pw.target_power != null ? pw.target_power : 0.80;
    const sufficient = !pw.more_data_needed;
    const curColor = sufficient ? PAL.pass : PAL.warn;            // marker FILL (area) — orange OK
    const curTextColor = sufficient ? PAL.pass : PAL.warnText;    // annotation TEXT — WCAG amber (C6)
    const nMax = Math.max(...curve.n);
    const traces = [
      // power curve
      { x: curve.n, y: curve.power.map((p) => p * 100), type: "scatter", mode: "lines",
        line: { color: PAL.accent, width: 2.2 }, hoverinfo: "skip", showlegend: false },
      // current N marker
      { x: [pw.n_ratings_current], y: [pw.power_current * 100], type: "scatter", mode: "markers",
        marker: { color: curColor, size: 12, line: { color: "#fff", width: 2 } },
        hovertemplate: `now: ${pw.n_ratings_current} ratings<br>power %{y:.0f}%<extra></extra>`,
        showlegend: false },
    ];
    const annotations = [
      { x: nMax * 1.02, y: tgt * 100, xanchor: "right", yanchor: "bottom",
        text: `${(tgt * 100).toFixed(0)}% target`, showarrow: false,
        font: { size: 9, color: PAL.pass } },
      // Static "now" annotation so the current marker is self-identifying in a printout / grayscale
      // (audit C7), not only on hover.
      { x: pw.n_ratings_current, y: pw.power_current * 100, xanchor: "center", yanchor: "top",
        yshift: -6, text: `now: ${pw.n_ratings_current}`, showarrow: false,
        font: { size: 8.5, color: curTextColor } },
    ];
    // needed-N marker (only when more data is needed and the number is known). Audit C5: place it at
    // the CURVE's own power at n_need (linear-interpolate the existing curve array) — NOT on the 80%
    // target line. The scalar n_ratings_needed comes from a closed-form SE²·N solve while the curve
    // is exact Hanley–McNeil, so pinning the marker to tgt made it sit visibly OFF the curve and read
    // as a glitch. Interpolating keeps marker and curve coincident.
    if (pw.more_data_needed && pw.n_ratings_needed != null) {
      const nNeed = pw.n_ratings_needed;
      const ns = curve.n; const ps = curve.power;
      let yNeed;
      if (nNeed <= ns[0]) {
        yNeed = ps[0];
      } else if (nNeed >= ns[ns.length - 1]) {
        yNeed = ps[ps.length - 1];
      } else {
        let j = 1;
        while (j < ns.length && ns[j] < nNeed) j += 1;
        const x0 = ns[j - 1]; const x1 = ns[j]; const y0 = ps[j - 1]; const y1 = ps[j];
        yNeed = x1 === x0 ? y1 : y0 + (y1 - y0) * ((nNeed - x0) / (x1 - x0));
      }
      traces.push({
        x: [nNeed], y: [yNeed * 100], type: "scatter", mode: "markers",
        marker: { color: PAL.neutral, size: 11, symbol: "circle-open", line: { width: 2 } },
        hovertemplate: `need ${nNeed} for ${(tgt * 100).toFixed(0)}% power<extra></extra>`,
        showlegend: false });
      annotations.push({ x: nNeed, y: yNeed * 100, xanchor: "center", yanchor: "bottom",
        yshift: 6, text: `need: ${nNeed}`, showarrow: false,
        font: { size: 8.5, color: PAL.neutral } });
    }
    const layout = {
      margin: { l: 44, r: 12, t: 8, b: 36 }, height: 170,
      xaxis: { title: { text: "independent pain ratings (N)", font: { size: 10.5 } },
        zeroline: false, tickfont: { size: 9.5 }, range: [0, nMax * 1.02] },
      yaxis: { title: { text: "Detection power for AUC > 0.5 (%)", font: { size: 10 } },
        range: [0, 102], zeroline: false, tickfont: { size: 9.5 }, dtick: 25 },
      shapes: [
        // 80% target line
        { type: "line", x0: 0, x1: nMax * 1.02, y0: tgt * 100, y1: tgt * 100,
          line: { color: PAL.pass, width: 1, dash: "dot" } },
      ],
      annotations,
    };
    Plotly.react(gd, traces, layout, PAL.MODEBAR);
  }, [data]);  // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => () => { if (pwRef.current) Plotly.purge(pwRef.current); }, []);

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
          <MDTypography variant="caption" sx={{ fontSize: 11, color: PAL.fail }}>
            {`Unavailable: ${err}.`}
          </MDTypography>
        ) : data ? (
          <>
            {/* Guard: a degenerate ROC operating point (alarm-always / alarm-never) must not be
                presented as a confident device threshold. Warn before the big number. */}
            {cutDegenerate ? (
              <MDBox p={1.2} mb={1.2} sx={{ backgroundColor: PAL.warnFill, borderRadius: "6px",
                border: `1px solid ${PAL.warnBorder}` }}>
                <MDTypography variant="caption" sx={{ fontSize: 11, fontWeight: "bold", color: PAL.warnText }}>
                  ⚠ The selected ROC operating point is degenerate (near-zero sensitivity or
                  specificity). The threshold below is not clinically deployable — return to the ROC
                  panel and choose a balanced cut-point before programming.
                </MDTypography>
              </MDBox>
            ) : null}

            {/* 1) THRESHOLD TO PROGRAM */}
            {tl && tl.available ? (
              <MDBox p={1.2} mb={1.2} sx={{ backgroundColor: PAL.accentFill, borderRadius: "6px",
                border: `1px solid ${PAL.accentBorder}` }}>
                <MDTypography variant="caption" sx={{ fontSize: 10, fontWeight: "bold", color: PAL.accent }}>
                  THRESHOLD TO PROGRAM (device LSB)
                </MDTypography>
                <MDTypography variant="h4" sx={{ fontSize: 26, color: PAL.accent, lineHeight: 1.1 }}>
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
              <MDBox p={1.2} mb={1.2} sx={{ backgroundColor: PAL.warnFill, borderRadius: "6px",
                border: `1px solid ${PAL.warnBorder}` }}>
                <MDTypography variant="caption" sx={{ fontSize: 10, fontWeight: "bold", color: PAL.warnText }}>
                  NO DEPLOYABLE LSB THRESHOLD
                </MDTypography>
                <MDTypography variant="caption" display="block" sx={{ fontSize: 11, mt: 0.3 }}>
                  {(tl && tl.reason) || "unavailable"}
                  {tl && tl.hint ? ` — ${tl.hint}` : ""}
                </MDTypography>
              </MDBox>
            )}

            {/* 1b) RECOMMENDED vs CURRENTLY-PROGRAMMED Δ (audit C10). Renders only when a closed-loop
                program is active on this hemisphere — the recommended number alone forces a programmer
                context-switch to know whether it is a small nudge or a large change. */}
            {rvp && rvp.available ? (
              <MDBox p={1.2} mb={1.2} sx={{ backgroundColor: PAL.neutralFill || "#6C757D12",
                borderRadius: "6px", border: `1px solid ${PAL.neutralBorder || "#6C757D44"}` }}>
                <MDTypography variant="caption" sx={{ fontSize: 10, fontWeight: "bold", color: PAL.neutral }}>
                  {`RECOMMENDED vs PROGRAMMED · ${rvp.hemisphere || ""} hemisphere`}
                </MDTypography>
                <MDTypography variant="caption" display="block" sx={{ fontSize: 12, mt: 0.3 }}>
                  {`recommended ${fmt(rvp.recommended_upper_lsb, 1)} LSB  ·  programmed `
                    + `${fmt(rvp.programmed_upper_lsb, 1)} LSB`}
                </MDTypography>
                {rvp.delta_lsb != null ? (
                  <MDTypography variant="caption" display="block" sx={{ fontSize: 13, fontWeight: "bold", mt: 0.2,
                    color: rvp.direction === "unchanged" ? PAL.pass : PAL.warnText }}>
                    {`Δ ${rvp.delta_lsb > 0 ? "+" : ""}${fmt(rvp.delta_lsb, 1)} LSB`
                      + `${rvp.delta_pct != null ? ` (${rvp.delta_pct > 0 ? "+" : ""}${fmt(rvp.delta_pct, 0)}%)` : ""}`
                      + ` — ${rvp.direction === "raise" ? "raise the upper threshold (stim engages later)"
                          : rvp.direction === "lower" ? "lower the upper threshold (stim engages sooner)"
                          : "no change from the programmed value"}`}
                  </MDTypography>
                ) : null}
                <MDTypography variant="caption" display="block" sx={{ fontSize: 9.5, color: "#777", mt: 0.4 }}>
                  {`Programmed ${rvp.programmed_status || "adaptive"}${rvp.programmed_date ? ` · ${String(rvp.programmed_date).slice(0, 10)}` : ""} · same device LFP-power units.`}
                </MDTypography>
              </MDBox>
            ) : rvp && rvp.programmed_upper_lsb != null ? (
              <MDBox p={1.0} mb={1.2} sx={{ backgroundColor: PAL.neutralFill || "#6C757D12", borderRadius: "6px" }}>
                <MDTypography variant="caption" sx={{ fontSize: 10.5, color: PAL.neutral }}>
                  {`Device currently programmed at ${fmt(rvp.programmed_upper_lsb, 1)} LSB `
                    + `(${rvp.hemisphere || ""}); no deployable recommendation to compare yet.`}
                </MDTypography>
              </MDBox>
            ) : null}

            {/* 2) POWER / SAMPLE-SIZE — a power-vs-N sufficiency curve instead of three numbers. */}
            {pw && pw.available ? (
              <MDBox mb={1.2}>
                <MDTypography variant="caption" sx={{ fontSize: 9.5, color: "#999", fontWeight: "bold" }}>
                  POWER vs SAMPLE SIZE
                  <span style={{ fontWeight: "normal", color: pw.power_current >= 0.8 ? PAL.pass : PAL.warnText }}>
                    {`  —  now ${fmt(pw.power_current * 100, 0)}% at ${pw.n_ratings_current} ratings`}
                  </span>
                </MDTypography>
                {/* curve when present (newer payloads); fall back to the readout line otherwise. */}
                <div ref={pwRef}
                  style={{ width: "100%", display: pw.curve ? "block" : "none" }} />
                <MDTypography variant="caption" display="block" color="text"
                  sx={{ fontSize: 9.5, mt: 0.2, textAlign: "center",
                    color: pw.more_data_needed ? PAL.warnText : PAL.pass, fontWeight: "bold" }}>
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
                  <span style={{ color: lr.confidence === "low" ? PAL.fail
                    : (lr.confidence === "high" ? PAL.pass : PAL.warnText), fontWeight: "bold" }}>
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
