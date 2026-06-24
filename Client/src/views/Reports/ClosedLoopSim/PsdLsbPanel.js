/**
 * PSD -> device-LSB conversion panel.
 *
 * Fetches /api/queryPsdLsbConversion for the committed band's channel. The Percept reports band power
 * in device "LSB" units; an offline Welch PSD reports physical uV^2/Hz. This panel pairs every offline
 * PSD epoch with the device's OWN LSB Timeline samples recorded within +/-1-2 h (chronic band power is
 * slowly varying, so a loose time-match is adequate) and fits the proportional law LSB = k*uV^2(band).
 *
 * It renders, in descending clinical weight:
 *   1) THE CONVERSION — k (LSB per uV^2) and its inverse (uV^2 per LSB), with a slope-near-1
 *      falsification check: a linear firmware gain MUST give a free log-log slope ~1.0; a slope far
 *      from 1 means the offline and on-device bands are not the same quantity and k is unreliable.
 *   2) A log-log scatter of the matched pairs with the proportional fit line + a +/-1sigma scatter band
 *      (the multiplicative residual the loose time-match produces).
 *
 * Imperative Plotly.react-once + restyle/relayout discipline — the figure is drawn once per dataset
 * and never rebuilt on interaction (module standard; see commit 255e0ef).
 */
import { useEffect, useRef, useState } from "react";
import Plotly from "plotly.js-dist";

import { Card } from "@mui/material";
import MDBox from "components/MDBox";
import MDTypography from "components/MDTypography";

import { SessionController } from "database/session-control";
import PAL from "./palette";

const fmt = (v, d = 2) => (v == null || !Number.isFinite(Number(v)) ? "—" : Number(v).toFixed(d));

function PsdLsbPanel({ participantUid, bandCandidate, requestParams }) {
  const figRef = useRef(null);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState(null);

  const bc = bandCandidate || {};
  const channelRaw = bc.contact;
  const centerHz = bc.center_freq_hz;
  const bandWidthHz = bc.bandwidth_hz || 5.0;

  useEffect(() => {
    if (!participantUid || channelRaw == null) { setData(null); return; }
    setLoading(true); setErr(null);
    SessionController.query("/api/queryPsdLsbConversion", {
      ParticipantId: participantUid,
      Channel: channelRaw,
      // Fix the band centre to the committed candidate so the conversion matches the band on screen.
      CenterHz: centerHz == null ? undefined : Number(centerHz),
      BandWidthHz: Number(bandWidthHz),
      MatchWindowH: 1.0,
      ...requestParams,
    }).then((response) => {
      const d = response && response.data;
      if (d && d.available) setData(d);
      else { setData(null); setErr((d && d.reason) || "unavailable"); }
      setLoading(false);
    }).catch(() => { setData(null); setErr("request failed"); setLoading(false); });
  }, [participantUid, channelRaw, centerHz, bandWidthHz, requestParams]);

  // --- the log-log scatter + proportional fit + scatter band (drawn once per dataset) ---
  useEffect(() => {
    const gd = figRef.current;
    if (!gd || !data || !data.scatter || !data.scatter.psd_uv2) {
      if (gd) Plotly.purge(gd);
      return;
    }
    const xs = data.scatter.psd_uv2;
    const ys = data.scatter.lsb;
    const k = data.k_lsb_per_uv2;
    const sigma = data.resid_log_sigma_fold || 1.0;   // multiplicative 1sigma fold
    const xmin = Math.max(1e-6, Math.min(...xs));
    const xmax = Math.max(...xs);
    // fit line + band on a log grid
    const NG = 60; const gx = []; const gy = []; const gHi = []; const gLo = [];
    for (let i = 0; i < NG; i += 1) {
      const lx = Math.log10(xmin) + (Math.log10(xmax) - Math.log10(xmin)) * (i / (NG - 1));
      const x = 10 ** lx; gx.push(x); gy.push(k * x); gHi.push(k * x * sigma); gLo.push((k * x) / sigma);
    }
    const traces = [
      // +/-1sigma multiplicative scatter band (drawn first, behind)
      { x: gx.concat(gx.slice().reverse()), y: gHi.concat(gLo.slice().reverse()),
        type: "scatter", mode: "lines", fill: "toself", fillcolor: PAL.accentFill,
        line: { width: 0 }, hoverinfo: "skip", showlegend: false },
      // matched pairs
      { x: xs, y: ys, type: "scattergl", mode: "markers",
        marker: { color: PAL.neutral, size: 4, opacity: 0.5 },
        hovertemplate: "PSD %{x:.3g} uV^2<br>LSB %{y:.0f}<extra></extra>", showlegend: false },
      // proportional fit line
      { x: gx, y: gy, type: "scatter", mode: "lines",
        line: { color: PAL.accent, width: 2 },
        hovertemplate: `LSB = ${fmt(k, 0)} x uV^2<extra></extra>`, showlegend: false },
    ];
    const layout = {
      margin: { l: 50, r: 12, t: 8, b: 40 }, height: 220,
      xaxis: { title: { text: "Offline PSD band power (uV^2)", font: { size: 10.5 } },
        type: "log", zeroline: false, tickfont: { size: 9.5 } },
      yaxis: { title: { text: "Device band power (LSB)", font: { size: 10.5 } },
        type: "log", zeroline: false, tickfont: { size: 9.5 } },
      annotations: [
        { xref: "paper", yref: "paper", x: 0.03, y: 0.97, xanchor: "left", yanchor: "top",
          text: `shaded = +/-1sigma (x${fmt(sigma, 1)})`, showarrow: false,
          font: { size: 8.5, color: PAL.accent } },
      ],
    };
    Plotly.react(gd, traces, layout, PAL.MODEBAR);
  }, [data]);  // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => () => { if (figRef.current) Plotly.purge(figRef.current); }, []);

  const k = data && data.k_lsb_per_uv2;
  const inv = data && data.uv2_per_lsb;
  const slopeOk = data && data.slope_consistent_with_unity;
  const slope = data && data.loglog_slope;
  const slopeCi = data && data.loglog_slope_ci;

  return (
    <Card sx={{ height: "100%" }}>
      <MDBox p={2}>
        <MDTypography variant="h6" sx={{ fontSize: 13 }}>
          PSD → device-LSB conversion
        </MDTypography>
        <MDTypography variant="caption" color="text" sx={{ fontSize: 10.5 }}>
          {`${bc.contact || "—"} · time-matched chronic streams (±1 h)`}
        </MDTypography>

        {channelRaw == null ? (
          <MDTypography variant="caption" color="text" sx={{ display: "block", mt: 1, fontStyle: "italic", fontSize: 11 }}>
            Commit a band candidate to derive its PSD→LSB conversion.
          </MDTypography>
        ) : loading ? (
          <MDTypography variant="caption" color="text" sx={{ display: "block", mt: 1, fontStyle: "italic", fontSize: 11 }}>
            Pairing offline PSD with the device LSB Timeline…
          </MDTypography>
        ) : err ? (
          <MDTypography variant="caption" sx={{ display: "block", mt: 1, fontSize: 11, color: PAL.warnText }}>
            {`No conversion: ${err}.`}
          </MDTypography>
        ) : data ? (
          <>
            {/* 1) THE CONVERSION CONSTANT */}
            <MDBox mt={1.2} p={1.2} sx={{ backgroundColor: PAL.accentFill, borderRadius: "6px",
              border: `1px solid ${PAL.accentBorder}` }}>
              <MDTypography variant="caption" sx={{ fontSize: 10, fontWeight: "bold", color: PAL.accent }}>
                CONVERSION
              </MDTypography>
              <MDTypography variant="h5" sx={{ fontSize: 20, color: PAL.accent, lineHeight: 1.15 }}>
                {`1 µV² ≈ ${fmt(k, 0)} LSB`}
              </MDTypography>
              <MDTypography variant="caption" display="block" sx={{ fontSize: 10.5, color: "#555" }}>
                {`inverse: 1 LSB ≈ ${fmt(inv, 4)} µV²  ·  n=${data.n_pairs} pairs  ·  ρ=${fmt(data.spearman, 2)}`}
              </MDTypography>
            </MDBox>

            {/* 2) SLOPE FALSIFICATION CHECK — a linear firmware gain must give slope ~1 */}
            <MDBox mt={1.0} p={1.0} sx={{ borderRadius: "6px",
              backgroundColor: slopeOk ? PAL.passFill : PAL.warnFill,
              border: `1px solid ${slopeOk ? (PAL.passBorder || "#009E7344") : PAL.warnBorder}` }}>
              <MDTypography variant="caption" sx={{ fontSize: 10.5, fontWeight: "bold",
                color: slopeOk ? PAL.pass : PAL.warnText }}>
                {slopeOk
                  ? `✓ Linear gain confirmed — log-log slope ${fmt(slope, 2)} (95% CI ${fmt(slopeCi && slopeCi[0], 2)}–${fmt(slopeCi && slopeCi[1], 2)}) includes 1.0`
                  : `△ Slope ${fmt(slope, 2)} (95% CI ${fmt(slopeCi && slopeCi[0], 2)}–${fmt(slopeCi && slopeCi[1], 2)}) — near 1 but CI excludes it; treat k as approximate`}
              </MDTypography>
            </MDBox>

            {/* 3) the matched-pair scatter + fit */}
            <MDBox mt={1.2}>
              <div ref={figRef} style={{ width: "100%" }} />
            </MDBox>

            <MDTypography variant="caption" display="block" sx={{ fontSize: 9, color: "#888", mt: 0.5, fontStyle: "italic" }}>
              {`Cross-scale calibration (not a control law): ${data.center_hz_mode}, band ${fmt(data.band_width_hz, 1)} Hz, mains line-noise notched.`}
            </MDTypography>
          </>
        ) : null}
      </MDBox>
    </Card>
  );
}

export default PsdLsbPanel;
