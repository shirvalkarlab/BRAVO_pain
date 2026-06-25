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
  const modeRef = useRef(null);
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

  // --- Plotly threshold-MODE figure with an updatemenus dropdown (client-side mode switch) ---------
  // The three Percept modes differ in FFT size (256-pt Dual/Single-Inverse vs 64-pt Single) and
  // averaging window. The bars show each mode's adaptive averaging (log ms); color encodes whether
  // THIS calibration (256-pt) applies to that mode. A native dropdown re-fired every panel's fetch;
  // here the dropdown is a Plotly updatemenus that just restyles the highlight + verdict annotation —
  // no refetch, no figure rebuild. All modes' verdicts arrive in one response (threshold_mode_compat).
  useEffect(() => {
    const gd = modeRef.current;
    const tm = data && data.threshold_mode_compat;
    if (!gd || !tm) { if (gd) Plotly.purge(gd); return; }
    const order = ["Dual", "Single", "SingleInverse"];
    const labels = { Dual: "Dual", Single: "Single", SingleInverse: "Single Inv." };
    const modes = order.filter((m) => tm[m]);
    const xs = modes.map((m) => labels[m]);
    const avg = modes.map((m) => tm[m].averaging_ms_adaptive);
    const conv = modes.map((m) => tm[m].convertible);
    // Okabe–Ito colorblind-safe: bluish-green = applies, vermillion = not convertible.
    const baseColors = conv.map((c) => (c ? PAL.pass : PAL.fail || "#D55E00"));
    const reason = (m) => (tm[m] && tm[m].reason) || "";

    const bar = {
      type: "bar", x: xs, y: avg, orientation: "v",
      marker: { color: baseColors, line: { color: "#fff", width: 1 } },
      text: modes.map((m) => `${tm[m].fft_size}-pt`), textposition: "outside",
      textfont: { size: 9 },
      hovertemplate: modes.map((m) =>
        `<b>${tm[m] && tm[m].label ? tm[m].label : m}</b><br>FFT ${tm[m].fft_size}-pt · `
        + `${Math.round(tm[m].averaging_ms_adaptive)} ms${tm[m].adaptive ? "" : " (sensing only)"}<br>`
        + `${tm[m].convertible ? "✓ calibration applies" : "✗ not convertible"}<extra></extra>`),
    };
    // updatemenus: one button per mode + an "all" reset, each restyling the marker emphasis and
    // swapping the verdict annotation to that mode's reason (pure client-side; no network).
    const buttons = modes.map((m, i) => {
      const emph = baseColors.map((c, j) => (j === i ? c : "#D9D9D9"));
      return {
        method: "update",
        args: [{ "marker.color": [emph] },
          { "annotations[0].text": `<b>${labels[m]}:</b> ${reason(m)}`,
            "annotations[0].font.color": conv[i] ? PAL.pass : (PAL.warnText || "#8A6100") }],
        label: labels[m],
      };
    });
    buttons.unshift({
      method: "update",
      args: [{ "marker.color": [baseColors] },
        { "annotations[0].text": "Select a mode to see whether this calibration applies",
          "annotations[0].font.color": "#777" }],
      label: "All modes",
    });

    const layout = {
      margin: { l: 38, r: 10, t: 8, b: 26 }, height: 150, bargap: 0.45,
      xaxis: { tickfont: { size: 9.5 }, fixedrange: true },
      yaxis: { title: { text: "avg (ms)", font: { size: 9 } }, type: "log",
        tickfont: { size: 8.5 }, fixedrange: true },
      annotations: [
        { xref: "paper", yref: "paper", x: 0, y: -0.32, xanchor: "left", yanchor: "top",
          text: "Select a mode to see whether this calibration applies", showarrow: false,
          font: { size: 8.5, color: "#777" }, align: "left" },
      ],
      updatemenus: [{
        type: "dropdown", direction: "down", showactive: true,
        x: 1.0, xanchor: "right", y: 1.32, yanchor: "top",
        bgcolor: "#fff", bordercolor: "#c4c4c4", font: { size: 9.5 },
        buttons,
      }],
    };
    Plotly.react(gd, [bar], layout, { displayModeBar: false, responsive: true });
  }, [data]);  // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => () => {
    if (figRef.current) Plotly.purge(figRef.current);
    if (modeRef.current) Plotly.purge(modeRef.current);
  }, []);

  const k = data && data.k_lsb_per_uv2;
  const inv = data && data.uv2_per_lsb;
  const sigma = (data && data.resid_log_sigma_fold) || 1.0;   // multiplicative 1σ fold factor
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
            {/* 1) THE CONVERSION CONSTANT with ±1σ error band */}
            <MDBox mt={1.2} p={1.2} sx={{ backgroundColor: PAL.accentFill, borderRadius: "6px",
              border: `1px solid ${PAL.accentBorder}` }}>
              <MDTypography variant="caption" sx={{ fontSize: 10, fontWeight: "bold", color: PAL.accent }}>
                CONVERSION
              </MDTypography>
              <MDTypography variant="h5" sx={{ fontSize: 20, color: PAL.accent, lineHeight: 1.15 }}>
                {`1 µV² ≈ ${fmt(k, 0)} LSB`}
                {sigma > 1.01 ? (
                  <span style={{ fontSize: 12, fontWeight: 400, color: "#777", marginLeft: 6 }}>
                    {`(±1σ: ${fmt(k / sigma, 0)}–${fmt(k * sigma, 0)})`}
                  </span>
                ) : null}
              </MDTypography>
              <MDTypography variant="caption" display="block" sx={{ fontSize: 10.5, color: "#555" }}>
                {`inverse: 1 LSB ≈ ${fmt(inv, 4)} µV²  ·  n=${data.n_pairs} pairs  ·  ρ=${fmt(data.spearman, 2)}`}
                {sigma > 1.01 ? ` · 1σ scatter: ×${fmt(sigma, 2)}` : ""}
              </MDTypography>
            </MDBox>

            {/* 1b) RECORDING-MODALITY BREAKDOWN — chronic (10-min) vs streaming (3000 ms) are
                   different averaging windows and are NEVER pooled (audit: the 8.8 Hz "drift" was a
                   pooling artifact). The controller-relevant gain is the streaming one. */}
            {data.by_modality && Object.keys(data.by_modality).length > 0 ? (
              <MDBox mt={1.0} p={1.0} sx={{ borderRadius: "6px", backgroundColor: "#F7F7F7",
                border: "1px solid #E0E0E0" }}>
                <MDTypography variant="caption" sx={{ fontSize: 10, fontWeight: "bold", color: "#555" }}>
                  BY RECORDING MODALITY (not pooled)
                </MDTypography>
                {Object.entries(data.by_modality).map(([src, m]) => {
                  const avgLabel = m.averaging_ms >= 60000
                    ? `${Math.round(m.averaging_ms / 60000)}-min` : `${Math.round(m.averaging_ms)} ms`;
                  return (
                    <MDTypography key={src} variant="caption" display="block"
                      sx={{ fontSize: 10.5, color: m.controller_relevant ? PAL.accent : "#777" }}>
                      {`${m.controller_relevant ? "▶ " : "   "}${src} (${avgLabel} avg): 1 µV² ≈ ${fmt(m.k_lsb_per_uv2, 0)} LSB · R²=${fmt(m.r2, 2)} · n=${m.n_pairs}${m.controller_relevant ? "  ← controller-relevant" : ""}`}
                    </MDTypography>
                  );
                })}
                {data.modality_gain_ratio ? (
                  <MDTypography variant="caption" display="block" sx={{ fontSize: 9.5, mt: 0.3, color: PAL.warnText, fontStyle: "italic" }}>
                    {`Gains differ ${fmt(data.modality_gain_ratio, 1)}× — deploy on the streaming-class gain (closest to the ${fmt(data.controller_averaging_ms, 0)} ms aDBS detector), not the chronic trend.`}
                  </MDTypography>
                ) : null}
              </MDBox>
            ) : null}

            {/* 1c) THRESHOLD-MODE (Percept RC) — a Plotly bar + updatemenus dropdown. Dual &
                   Single-Inverse are 256-pt (this calibration applies); Single is 64-pt (a different
                   band integral — not convertible). Switching modes is client-side (no refetch). */}
            {data.threshold_mode_compat ? (
              <MDBox mt={1.0} p={1.0} sx={{ borderRadius: "6px", backgroundColor: "#F7F7F7",
                border: "1px solid #E0E0E0" }}>
                <MDTypography variant="caption" sx={{ fontSize: 10, fontWeight: "bold", color: "#555" }}>
                  THRESHOLD MODE (Percept RC) · adaptive averaging window
                </MDTypography>
                <div ref={modeRef} style={{ width: "100%" }} />
              </MDBox>
            ) : null}

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
              {`Cross-scale calibration (not a control law): ${data.center_hz_mode}, band ${fmt(data.band_width_hz, 1)} Hz${data.primary_source ? `, headline gain = ${data.primary_source}` : ""}. No mains notch (implanted, battery-powered — no 60 Hz line coupling). `}
              <a href="/static/docs/METHODS_lsb_estimation.html" target="_blank" rel="noopener noreferrer"
                style={{ color: PAL.accent, textDecoration: "underline", fontWeight: 500 }}>
                Methods &amp; validation ↗
              </a>
            </MDTypography>
          </>
        ) : null}
      </MDBox>
    </Card>
  );
}

export default PsdLsbPanel;
