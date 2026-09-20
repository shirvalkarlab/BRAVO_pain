/**
 * The calibration IN EFFECT: how a band power in microvolts squared becomes the device's own
 * least-significant-bit (LSB) units, with the numbers the platform converts with today
 * (decision 212, the PI, 2026-09-20).
 *
 * Served by /api/queryPsdLsbConversionModel, which since 2026-09-20 runs the recipe in
 * `Biomarkers/routines/calibration.py` over the two tables in `Biomarkers/data/calibration/`:
 *
 *   (1) THE TRANSFORM CONSTANT. Every streaming block the device recorded two ways at once (its own
 *       band power in LSB, and the raw voltage trace the platform turns into band power in uV^2):
 *       device LSB against transform uV^2, raw axes, with the line LSB = k x uV^2 at the constant
 *       in effect. Blocks the recipe left out (too short, or a ratio outlier under the 5-MAD rule)
 *       are drawn hollow so the reader sees what the constant does and does not rest on.
 *   (2) THE BRIDGE. For a recording that carries only the device's onboard-FFT snapshot, the
 *       platform first divides the device's band power by a fixed ratio to reach the transform's
 *       units, then applies the constant above. The ratio per band centre (median over every
 *       survey and contact pair) sits beside the one ratio in effect.
 *
 * Every number printed here is read from the served payload; the source carries none of them, so
 * the day the constant moves again the panel cannot print a stale one
 * (`CalibrationInEffectPanel.test.js` reads this file to prove it). Both axes stay raw: log power
 * enters no plot or calculation (decision 202). Imperative Plotly.react-once discipline (commit
 * 255e0ef).
 */
import { useEffect, useRef } from "react";
import Plotly from "plotly.js-dist";

import { Card } from "@mui/material";
import MDBox from "components/MDBox";
import MDTypography from "components/MDTypography";

import { SessionController } from "database/session-control";
import { useCachedResult } from "database/useCachedResult";

import { CL, recomputeSlots } from "views/Reports/moduleCacheKeys";
import PanelStaleNote from "views/Reports/ClosedLoopSim/PanelStaleNote";
import PAL from "views/Reports/ClosedLoopSim/palette";

const fmt = (v, d = 2) => (v == null || !Number.isFinite(Number(v)) ? "—" : Number(v).toFixed(d));
const isoDate = (yyyymmdd) => (yyyymmdd && yyyymmdd.length === 8
  ? `${yyyymmdd.slice(0, 4)}-${yyyymmdd.slice(4, 6)}-${yyyymmdd.slice(6, 8)}` : yyyymmdd || "—");

// The sensing pair in the clinic's own notation, with the side spelled out.
const contactLabel = (ch) => (ch || "")
  .replace("ZERO_THREE", "0–3").replace("ONE_THREE", "1–3").replace("ZERO_TWO", "0–2")
  .replace("ZERO_ONE", "0–1").replace("ONE_TWO", "1–2").replace("TWO_THREE", "2–3")
  .replace("_RIGHT", " Right").replace("_LEFT", " Left");

// One ink per side, so no reader can take the cloud for a pooled electrode (never pool across
// electrodes: the hover names the contact pair and centre of every block).
const SIDE_INK = { Left: PAL.accent, Right: PAL.fail };

function CalibrationInEffectPanel({ participantUid }) {
  const blocksRef = useRef(null);
  const bridgeRef = useRef(null);

  // The endpoint takes the participant and nothing else: the tables are a property of the
  // participant, and only a new table or a new constant can change the answer.
  const cached = useCachedResult({
    moduleKey: CL.conversionModel,
    uid: participantUid,
    settings: {},
    enabled: !!participantUid,
    fetcher: () => SessionController.query("/api/queryPsdLsbConversionModel",
      { ParticipantId: participantUid })
      .then((response) => (response && response.data) || null),
  });

  const raw = cached.data;
  const data = raw && raw.available ? raw : null;
  const loading = cached.loading;
  const err = cached.err || (raw && !raw.available ? (raw.reason || "no calibration table") : null);

  const deployed = data ? data.deployed : null;
  const tr = data ? data.transform : null;
  const br = data ? data.bridge : null;

  // ---- (1) device LSB against transform uV^2, every block, the line at the constant in effect ----
  useEffect(() => {
    const gd = blocksRef.current;
    if (!gd || !tr || !tr.blocks || !tr.blocks.length) { if (gd) Plotly.purge(gd); return; }
    const blocks = tr.blocks.filter((b) => b.uv2 != null && b.lsb != null);
    const hover = (b) => `${contactLabel(b.channel)} · ${fmt(b.center_hz, 1)} Hz · ${isoDate(b.date)}`
      + `<br>${fmt(b.uv2, 2)} µV² → ${fmt(b.lsb, 0)} LSB · ${fmt(b.td_seconds, 1)} s, `
      + `${fmt(b.n_lfp_points, 0)} device readings, ${fmt(b.median_ma, 1)} mA`;
    const traces = [];
    ["Left", "Right"].forEach((side) => {
      const kept = blocks.filter((b) => b.side === side && b.status === "kept");
      if (kept.length) {
        traces.push({ x: kept.map((b) => b.uv2), y: kept.map((b) => b.lsb), type: "scatter", mode: "markers",
          name: `${side}, kept (${kept.length})`,
          marker: { color: SIDE_INK[side], size: 6, opacity: 0.8 },
          text: kept.map(hover), hovertemplate: "%{text}<extra>kept</extra>" });
      }
      const out = blocks.filter((b) => b.side === side && b.status !== "kept");
      if (out.length) {
        traces.push({ x: out.map((b) => b.uv2), y: out.map((b) => b.lsb), type: "scatter", mode: "markers",
          name: `${side}, gated or flagged (${out.length})`,
          marker: { color: SIDE_INK[side], size: 6, symbol: "circle-open", opacity: 0.8 },
          text: out.map((b) => `${hover(b)}<br>${b.status === "gated" ? "left out: too short" : b.status === "flagged" ? "left out: ratio outlier (5 MAD)" : "no usable pair"}`),
          hovertemplate: "%{text}<extra></extra>" });
      }
    });
    const xmax = Math.max(...blocks.map((b) => b.uv2)) * 1.04;
    traces.push({ x: [0, xmax], y: [0, deployed.k * xmax], type: "scatter", mode: "lines",
      name: `in effect: LSB = ${fmt(deployed.k, 2)} × µV²`,
      line: { color: "#222", width: 1.5 }, hoverinfo: "name" });
    const layout = {
      margin: { l: 56, r: 12, t: 8, b: 40 }, height: 260,
      xaxis: { title: { text: "band power from the voltage trace (µV²)", font: { size: 10.5 } },
        rangemode: "tozero", zeroline: false, tickfont: { size: 9.5 } },
      yaxis: { title: { text: "device band power (LSB)", font: { size: 10.5 } },
        rangemode: "tozero", zeroline: false, tickfont: { size: 9.5 } },
      legend: { font: { size: 9 }, orientation: "h", y: -0.22, x: 0 },
    };
    Plotly.react(gd, traces, layout, PAL.MODEBAR);
  }, [data]);  // eslint-disable-line react-hooks/exhaustive-deps

  // ---- (2) the bridge ratio per band centre, the ratio in effect as a line ----
  useEffect(() => {
    const gd = bridgeRef.current;
    if (!gd || !br || !br.per_centre || !br.per_centre.length) { if (gd) Plotly.purge(gd); return; }
    const traces = [];
    const byChannel = {};
    (br.per_channel_centre || []).forEach((p) => { (byChannel[p.channel] = byChannel[p.channel] || []).push(p); });
    Object.keys(byChannel).sort().forEach((ch) => {
      const pts = byChannel[ch].slice().sort((a, b) => a.center_hz - b.center_hz);
      const side = /LEFT/.test(ch) ? "Left" : "Right";
      traces.push({ x: pts.map((p) => p.center_hz), y: pts.map((p) => p.ratio), type: "scatter", mode: "markers",
        name: contactLabel(ch), legendgroup: side, showlegend: false,
        marker: { color: SIDE_INK[side], size: 4, opacity: 0.45 },
        hovertemplate: `${contactLabel(ch)} · %{x:.1f} Hz · ratio %{y:.2f}<extra></extra>` });
    });
    traces.push({ x: br.per_centre.map((p) => p.center_hz), y: br.per_centre.map((p) => p.ratio),
      type: "scatter", mode: "markers+lines", name: "median over every survey and contact pair",
      marker: { color: "#222", size: 7 }, line: { color: "#222", width: 1 },
      customdata: br.per_centre.map((p) => p.n),
      hovertemplate: "%{x:.1f} Hz · ratio %{y:.3f} · n=%{customdata}<extra></extra>" });
    const xs = br.per_centre.map((p) => p.center_hz);
    traces.push({ x: [Math.min(...xs) - 0.5, Math.max(...xs) + 0.5], y: [deployed.bridge_ratio, deployed.bridge_ratio],
      type: "scatter", mode: "lines", name: `in effect: ratio ${fmt(deployed.bridge_ratio, 3)}`,
      line: { color: PAL.neutral, width: 1.5, dash: "dash" }, hoverinfo: "name" });
    const layout = {
      margin: { l: 56, r: 12, t: 8, b: 40 }, height: 220,
      xaxis: { title: { text: "band centre (Hz)", font: { size: 10.5 } }, tickfont: { size: 9.5 } },
      yaxis: { title: { text: "device FFT ÷ transform band power", font: { size: 10.5 } },
        rangemode: "tozero", zeroline: false, tickfont: { size: 9.5 } },
      legend: { font: { size: 9 }, orientation: "h", y: -0.28, x: 0 },
    };
    Plotly.react(gd, traces, layout, PAL.MODEBAR);
  }, [data]);  // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => () => {
    if (blocksRef.current) Plotly.purge(blocksRef.current);
    if (bridgeRef.current) Plotly.purge(bridgeRef.current);
  }, []);

  const nBlocks = tr && tr.blocks ? tr.blocks.length : 0;
  const nLeftOut = tr && tr.blocks ? tr.blocks.filter((b) => b.status !== "kept").length : 0;
  const june = tr && tr.june_reference;

  return (
    <Card sx={{ height: "100%" }}>
      <MDBox p={2}>
        <MDTypography variant="h6" sx={{ fontSize: 13 }}>
          Calibration in effect: microvolts squared to device units
        </MDTypography>
        <MDTypography variant="caption" color="text" sx={{ fontSize: 10.5 }}>
          The two fixed numbers every calibrated LSB on the platform is computed with, and the paired
          recordings they rest on.
        </MDTypography>
        <PanelStaleNote stale={cached.stale} staleReasons={cached.staleReasons}
          loading={cached.loading} notKept={cached.notKept}
          onRecompute={() => recomputeSlots(participantUid, [CL.conversionModel])} />

        {loading ? (
          <MDTypography variant="caption" color="text" sx={{ display: "block", mt: 1, fontStyle: "italic", fontSize: 11 }}>
            Loading the calibration tables…
          </MDTypography>
        ) : err ? (
          <MDTypography variant="caption" sx={{ display: "block", mt: 1, fontSize: 11, color: PAL.warnText }}>
            {`No calibration: ${err}.`}
          </MDTypography>
        ) : data ? (
          <>
            {/* 1) THE TRANSFORM CONSTANT */}
            <MDBox mt={1.2} p={1.2} sx={{ backgroundColor: PAL.accentFill, borderRadius: "6px",
              border: `1px solid ${PAL.accentBorder}` }}>
              <MDTypography variant="caption" sx={{ fontSize: 10, fontWeight: "bold", color: PAL.accent }}>
                VOLTAGE TRACE → DEVICE UNITS (measured)
              </MDTypography>
              <MDTypography variant="h5" sx={{ fontSize: 20, color: PAL.accent, lineHeight: 1.15 }}>
                {`1 µV² = ${fmt(deployed.k, 2)} LSB`}
              </MDTypography>
              <MDTypography variant="caption" display="block" sx={{ fontSize: 10.5, color: "#555" }}>
                {`The median ratio over ${tr.n} blocks the device recorded both ways at once `
                  + `(r = ${fmt(tr.r, 2)}, typical miss ×${fmt(tr.median_fold_error, 2)}); `
                  + `${nBlocks} paired blocks through ${data.table_date}, ${nLeftOut} left out by the recipe: `
                  + `a block needs at least 3 s of signal and 6 device readings, and a block whose ratio `
                  + `falls more than 5 MAD from the rest is dropped (the platform's one outlier rule).`}
              </MDTypography>
              {june && june.k != null ? (
                <MDTypography variant="caption" display="block" sx={{ fontSize: 10.5, color: "#555" }}>
                  {`The June 2026 reference, ${fmt(june.k, 2)} on ${june.n} blocks through ${isoDate(june.last_date)} `
                    + "with no gate and no rule, comes back from the same table; the constant in effect adds "
                    + "the blocks recorded since, under the recipe above."}
                </MDTypography>
              ) : null}
            </MDBox>
            <MDBox mt={1}>
              <MDTypography variant="caption" sx={{ fontSize: 10.5, fontWeight: "bold", color: "#555" }}>
                Every paired block, device LSB against band power from the voltage trace; hollow = left out
              </MDTypography>
              <div ref={blocksRef} style={{ width: "100%" }} />
            </MDBox>

            {/* 2) THE BRIDGE */}
            <MDBox mt={1.2} p={1.2} sx={{ backgroundColor: PAL.neutralFill || "#f4f4f4", borderRadius: "6px",
              border: `1px solid ${PAL.neutralBorder}` }}>
              <MDTypography variant="caption" sx={{ fontSize: 10, fontWeight: "bold", color: "#555" }}>
                DEVICE FFT SNAPSHOT → DEVICE UNITS (composed)
              </MDTypography>
              <MDTypography variant="h5" sx={{ fontSize: 20, color: "#444", lineHeight: 1.15 }}>
                {`1 device-µV² = ${fmt(deployed.bridge_lsb_per_device_uv2, 2)} LSB`}
              </MDTypography>
              <MDTypography variant="caption" display="block" sx={{ fontSize: 10.5, color: "#555" }}>
                {`Composed, not measured: ${fmt(deployed.k, 2)} ÷ ${fmt(deployed.bridge_ratio, 3)}, the ratio in effect between the `
                  + `device's onboard-FFT band power and the transform's on the same survey and contact. `
                  + `Refit on ${br.n_surveys} surveys, ${br.n} of ${br.n_pairs} contact-and-centre pairs after the same 5 MAD rule: `
                  + `${fmt(br.ratio, 3)}, within 1 percent of the ratio in effect, and flat across centres and contact pairs.`}
              </MDTypography>
            </MDBox>
            <MDBox mt={1}>
              <MDTypography variant="caption" sx={{ fontSize: 10.5, fontWeight: "bold", color: "#555" }}>
                The ratio per band centre: small points one contact pair each, large points the median; dashed = in effect
              </MDTypography>
              <div ref={bridgeRef} style={{ width: "100%" }} />
            </MDBox>

            <MDTypography variant="caption" display="block" sx={{ fontSize: 9.5, color: "#666", mt: 0.8 }}>
              {`Where these are used: the Biomarkers timeline's modeled points (○ voltage trace × ${fmt(deployed.k, 2)}, `
                + `◇ FFT snapshot × ${fmt(deployed.bridge_lsb_per_device_uv2, 2)}); the Closed-Loop page's threshold for a band the device `
                + "never sensed, and its three-source response panel. The Stim Optimizer reads device-native "
                + "power and needs neither."}
            </MDTypography>
          </>
        ) : null}
      </MDBox>
    </Card>
  );
}

export default CalibrationInEffectPanel;
