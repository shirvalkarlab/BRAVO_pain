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

import MDBox from "components/MDBox";
import MDTypography from "components/MDTypography";

import { SessionController } from "database/session-control";
import { useCachedResult } from "database/useCachedResult";

import { CL, recomputeSlots } from "views/Reports/moduleCacheKeys";
import PanelStaleNote from "views/Reports/ClosedLoopSim/PanelStaleNote";
import { T, TYPE } from "assets/theme/base/tokens";
import { SIDE } from "assets/theme/base/dataColors";
import { plotlyLayout, PLOTLY_CONFIG_WITH_TOOLBAR, directLabel } from "views/Reports/figureStyle";

import Fold from "./Fold";

const fmt = (v, d = 2) => (v == null || !Number.isFinite(Number(v)) ? "not given" : Number(v).toFixed(d));
const isoDate = (yyyymmdd) => (yyyymmdd && yyyymmdd.length === 8
  ? `${yyyymmdd.slice(0, 4)}-${yyyymmdd.slice(4, 6)}-${yyyymmdd.slice(6, 8)}` : yyyymmdd || "not given");

// The sensing pair in the clinic's own notation, with the side spelled out.
const contactLabel = (ch) => (ch || "")
  .replace("ZERO_THREE", "0–3").replace("ONE_THREE", "1–3").replace("ZERO_TWO", "0–2")
  .replace("ZERO_ONE", "0–1").replace("ONE_TWO", "1–2").replace("TWO_THREE", "2–3")
  .replace("_RIGHT", " Right").replace("_LEFT", " Left");

// One ink per side (the shared side colours: left blue, right orange), so no reader can take the
// cloud for a pooled electrode (never pool across electrodes: the hover names the contact pair and
// centre of every block).
const SIDE_INK = { Left: SIDE.left, Right: SIDE.right };
// A small filled dot in a side's colour, beside the words that name it (a mark, not text colour).
const DOT = { display: "inline-block", width: 8, height: 8, borderRadius: "50%", marginRight: 4 };

/** How the refit bridge ratio compares with the one in effect, and how far its medians spread, worked
 *  out from the payload (review of 2026-09-26: this used to be fixed text, "within 1 percent of the
 *  ratio in effect, and flat across centres and contact pairs", which a new table could contradict). */
function bridgeComparison(br, deployed) {
  const parts = [];
  const r = Number(br && br.ratio);
  const d = Number(deployed && deployed.bridge_ratio);
  if (Number.isFinite(r) && Number.isFinite(d) && d > 0) {
    const pct = (r / d - 1) * 100;
    parts.push(Math.abs(pct) < 0.05 ? ", the same as the ratio in effect"
      : `, ${Math.abs(pct).toFixed(1)} percent ${pct < 0 ? "below" : "above"} the ratio in effect`);
  }
  const span = (rows) => {
    const v = (rows || []).map((x) => Number(x.ratio)).filter(Number.isFinite);
    return v.length ? [Math.min(...v), Math.max(...v)] : null;
  };
  const c = span(br && br.per_centre);
  const p = span(br && br.per_channel);
  if (c && p) {
    parts.push(`; the median per band centre runs from ${c[0].toFixed(2)} to ${c[1].toFixed(2)} and per contact pair from ${p[0].toFixed(2)} to ${p[1].toFixed(2)}`);
  }
  return `${parts.join("")}.`;
}

/** The threshold streams' check of the PSD->LSB route, one line, from the served payload
 *  (decision 447): measured LSB ÷ the LSB the bridge predicts, median per source. */
export function thresholdCheckLine(tc) {
  if (!tc) return null;
  if (!tc.available) return `No threshold check: ${tc.reason || "not available"}`;
  const parts = Object.entries(tc.by_source || {})
    .filter(([, v]) => v && v.n > 0)
    .sort((a, b) => b[1].n - a[1].n)
    .map(([src, v]) => `${fmt(v.median_ratio, 2)} (${src}, n=${v.n})`);
  return `Checked on ${tc.n_streams} threshold streams: measured ÷ predicted LSB ${parts.join(", ")}`;
}

function CalibrationInEffectPanel({ participantUid }) {
  const blocksRef = useRef(null);
  const bridgeRef = useRef(null);
  const thresholdRef = useRef(null);

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
          name: `${side}, left out as too short or far from the rest (${out.length})`,
          marker: { color: SIDE_INK[side], size: 6, symbol: "circle-open", opacity: 0.8 },
          text: out.map((b) => `${hover(b)}<br>${b.status === "gated" ? "left out: too short" : b.status === "flagged" ? "left out: ratio outlier (5 MAD)" : "no usable pair"}`),
          hovertemplate: "%{text}<extra></extra>" });
      }
    });
    const xmax = Math.max(...blocks.map((b) => b.uv2)) * 1.04;
    traces.push({ x: [0, xmax], y: [0, deployed.k * xmax], type: "scatter", mode: "lines",
      name: `in effect: LSB = ${fmt(deployed.k, 2)} × µV²`,
      line: { color: T.ink, width: 1.5 }, hoverinfo: "name" });
    // Direct labels at the lines' right ends, instead of a legend box (SPEC.md section 5.1).
    const annotations = [directLabel(xmax, deployed.k * xmax, `in effect ×${fmt(deployed.k, 2)}`)];
    // The 1-MAD band either side of the line (ruling C1): the same raw scatter the Closed-Loop
    // page draws either side of a modelled threshold (ruling A2).
    if (tr.scatter_mad != null) {
      [[deployed.k - tr.scatter_mad, "−"], [deployed.k + tr.scatter_mad, "+"]].forEach(([kk, sign]) => {
        traces.push({ x: [0, xmax], y: [0, kk * xmax], type: "scatter", mode: "lines",
          name: `${sign}typical spread of the ratio (${fmt(kk, 1)})`, showlegend: sign === "+",
          line: { color: T.ink3, width: 1, dash: "dot" }, hoverinfo: "name" });
        if (sign === "+") annotations.push(directLabel(xmax, kk * xmax, "typical spread", T.ink3));
      });
    }
    const layout = plotlyLayout({
      margin: { l: 60, r: 110, t: 8, b: 44 }, height: 280,
      xaxis: { title: { text: "TD band power (µV²)" }, rangemode: "tozero" },
      yaxis: { title: { text: "device band power (LSB)" }, rangemode: "tozero" },
      annotations,
    });
    Plotly.react(gd, traces, layout, PLOTLY_CONFIG_WITH_TOOLBAR);
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
      marker: { color: T.ink, size: 7 }, line: { color: T.ink, width: 1 },
      customdata: br.per_centre.map((p) => p.n),
      hovertemplate: "%{x:.1f} Hz · ratio %{y:.3f} · n=%{customdata}<extra></extra>" });
    const xs = br.per_centre.map((p) => p.center_hz);
    traces.push({ x: [Math.min(...xs) - 0.5, Math.max(...xs) + 0.5], y: [deployed.bridge_ratio, deployed.bridge_ratio],
      type: "scatter", mode: "lines", name: `in effect: ratio ${fmt(deployed.bridge_ratio, 3)}`,
      line: { color: T.graphic, width: 1.5, dash: "dash" }, hoverinfo: "name" });
    const xEnd = Math.max(...xs) + 0.5;
    const layout = plotlyLayout({
      margin: { l: 60, r: 110, t: 8, b: 44 }, height: 240,
      xaxis: { title: { text: "band centre (Hz)" } },
      yaxis: { title: { text: "PSD band power ÷ TD band power" }, rangemode: "tozero" },
      annotations: [directLabel(xEnd, deployed.bridge_ratio, `in effect ${fmt(deployed.bridge_ratio, 3)}`, T.ink3)],
    });
    Plotly.react(gd, traces, layout, PLOTLY_CONFIG_WITH_TOOLBAR);
  }, [data]);  // eslint-disable-line react-hooks/exhaustive-deps

  // ---- (3) the threshold streams: measured LSB against the LSB predicted from a device spectrum ----
  const tc = raw ? raw.threshold_check : null;
  useEffect(() => {
    const gd = thresholdRef.current;
    const rows = tc && tc.available ? (tc.rows || []) : [];
    if (!gd || !rows.length) { if (gd) Plotly.purge(gd); return; }
    const sources = Object.keys(tc.by_source || {});
    const SYMBOL = { "signal check": "circle", montage: "diamond", "run unknown": "square" };
    const traces = sources.map((src) => {
      const pts = rows.filter((r) => r.predicted_lsb && r.predicted_lsb[src] != null && r.measured_lsb != null);
      return { x: pts.map((r) => r.predicted_lsb[src]), y: pts.map((r) => r.measured_lsb),
        type: "scatter", mode: "markers", name: `${src} (${pts.length})`,
        marker: { color: pts.map((r) => SIDE_INK[r.side === "LEFT" ? "Left" : "Right"]), size: 6,
          symbol: SYMBOL[src] || "circle", opacity: 0.8 },
        text: pts.map((r) => `${contactLabel(r.channel)} · ${fmt(r.center_hz, 1)} Hz`),
        hovertemplate: `%{text}<br>predicted %{x:.0f} LSB (${src}) · measured %{y:.0f} LSB<extra></extra>` };
    });
    const all = rows.flatMap((r) => [r.measured_lsb, ...Object.values(r.predicted_lsb || {})])
      .filter((v) => v != null && Number.isFinite(v));
    const top = Math.max(...all) * 1.04;
    traces.push({ x: [0, top], y: [0, top], type: "scatter", mode: "lines", name: "measured = predicted",
      line: { color: T.ink, width: 1.5 }, hoverinfo: "name" });
    const layout = plotlyLayout({
      margin: { l: 60, r: 110, t: 8, b: 44 }, height: 280,
      xaxis: { title: { text: "predicted from the device's PSD (LSB)" }, rangemode: "tozero" },
      yaxis: { title: { text: "threshold stream, measured (LSB)" }, rangemode: "tozero" },
      annotations: [directLabel(top, top, "measured = predicted")],
    });
    Plotly.react(gd, traces, layout, PLOTLY_CONFIG_WITH_TOOLBAR);
  }, [raw]);  // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => () => {
    if (blocksRef.current) Plotly.purge(blocksRef.current);
    if (bridgeRef.current) Plotly.purge(bridgeRef.current);
    if (thresholdRef.current) Plotly.purge(thresholdRef.current);
  }, []);

  const nBlocks = tr && tr.blocks ? tr.blocks.length : 0;
  const nLeftOut = tr && tr.blocks ? tr.blocks.filter((b) => b.status !== "kept").length : 0;
  const june = tr && tr.june_reference;

  // One card, one open status line with the two constants, and one fold for how they were fitted
  // (decision 304; the design review of 2026-09-26, B2). The page used to add an intro paragraph and
  // an italic caption around this panel that each said again that the bridge is composed; the
  // panel now says it once on view ("the bridge constant (composed)") and once, with its
  // arithmetic, in the fold. No box inside the card: the two sections in the fold are separated by
  // a thin rule, not bordered and tinted boxes of their own.
  const SUB = T.ink2;
  const RULE = T.rule;
  const LINE = { ...TYPE.body, color: SUB, display: "block" };
  const HEAD = { ...TYPE.body, fontWeight: 600, color: T.ink, display: "block" };
  return (
    // A plain row of the page's Background group, not a card (taste audit C12, 2026-09-26): a
    // hairline above it separates it from the row before; nothing boxes it.
    <MDBox component="section" data-paper="background-row"
      sx={{ borderTop: `1px solid ${T.rule}`, pt: 3 }}>
      <MDBox>
        <MDTypography component="h3" sx={{ ...TYPE.title, color: T.ink, m: 0 }}>
          Calibration in effect: µV² to device units
        </MDTypography>
        <PanelStaleNote stale={cached.stale} staleReasons={cached.staleReasons}
          loading={cached.loading} notKept={cached.notKept}
          onRecompute={() => recomputeSlots(participantUid, [CL.conversionModel])} />

        {loading ? (
          <MDTypography variant="caption" sx={{ ...TYPE.body, display: "block", mt: 1, color: T.ink3 }}>
            Loading the calibration tables…
          </MDTypography>
        ) : err ? (
          <MDTypography variant="caption" sx={{ ...TYPE.body, display: "block", mt: 1, color: T.caution }}>
            {`\u25b2 No calibration: ${err}.`}
          </MDTypography>
        ) : data ? (
          <>
            {/* THE STATUS: the two numbers every calibrated LSB on the platform is computed with. */}
            <MDBox mt={1} data-testid="calibration-status">
              <MDTypography variant="button" display="block" sx={{ ...TYPE.body, color: T.ink2 }}>
                <b style={{ color: T.ink, fontWeight: 600 }}>Time domain (TD) → device units: </b>
                {`1 µV² = ${fmt(deployed.k, 2)} LSB, the transform constant, measured on ${tr.n} paired blocks.`}
              </MDTypography>
              <MDTypography variant="button" display="block" sx={{ ...TYPE.body, color: T.ink2 }}>
                <b style={{ color: T.ink, fontWeight: 600 }}>PSD (the device's 30 s snapshot) → device units: </b>
                {`1 device-µV² = ${fmt(deployed.bridge_lsb_per_device_uv2, 2)} LSB, the bridge constant (composed).`}
              </MDTypography>
              {tc ? (
                <MDTypography variant="button" display="block" data-testid="threshold-check-status"
                  sx={{ ...TYPE.body, color: T.ink2 }}>
                  {thresholdCheckLine(tc)}
                </MDTypography>
              ) : null}
            </MDBox>

            <Fold show="Constant fit and use"
              hide="Hide how the constants were fitted">
              {/* 1) THE TRANSFORM CONSTANT */}
              <MDBox mt={0.5} pt={1} sx={{ borderTop: `1px solid ${RULE}` }}>
                <MDTypography variant="caption" sx={HEAD}>
                  The transform constant
                </MDTypography>
                {tr.k_interval ? (
                  <MDTypography variant="caption" sx={LINE}>
                    {`95% interval ${fmt(tr.k_interval[0], 1)}–${fmt(tr.k_interval[1], 1)} (${tr.k_interval_method}); `
                      + `the typical spread of the ratio is ${fmt(tr.scatter_mad, 1)} LSB per µV² (${fmt(100 * tr.scatter_mad_frac, 0)}% of the constant), `
                      + "the dotted lines below. "
                      + (tr.proportionality ? tr.proportionality.sentence : "")}
                  </MDTypography>
                ) : null}
                <MDTypography variant="caption" sx={LINE}>
                  {`The median ratio over ${tr.n} blocks the device recorded both ways at once `
                    + `(r = ${fmt(tr.r, 2)}, median fold error ${fmt(tr.median_fold_error, 2)}); `
                    + `${nBlocks} paired blocks through ${data.table_date}, ${nLeftOut} left out by the recipe: `
                    + `a block needs at least 3 s of signal and 6 device readings, and a block whose ratio `
                    + `falls more than 5 MAD from the rest is dropped (the platform's one outlier rule).`}
                </MDTypography>
                {june && june.k != null ? (
                  <MDTypography variant="caption" sx={LINE}>
                    {`The June 2026 reference, ${fmt(june.k, 2)} on ${june.n} blocks through ${isoDate(june.last_date)} `
                      + "with no gate and no rule, comes back from the same table; the constant in effect adds "
                      + "the blocks recorded since, under the recipe above."}
                  </MDTypography>
                ) : null}
              </MDBox>
              <MDBox mt={1}>
                <MDTypography variant="caption" sx={HEAD}>
                  Every paired block, device LSB against TD band power
                </MDTypography>
                <MDTypography variant="caption" sx={{ ...TYPE.body, color: T.ink3, display: "block" }}>
                  <span aria-hidden="true" style={{ ...DOT, background: SIDE.left }} />{"left lead \u00b7 "}
                  <span aria-hidden="true" style={{ ...DOT, background: SIDE.right }} />{"right lead \u00b7 "}
                  {"\u25cb hollow: left out as too short or far from the rest (LSB: the device's own units)"}
                </MDTypography>
                <div ref={blocksRef} style={{ width: "100%" }} />
              </MDBox>

              {/* 2) THE BRIDGE */}
              <MDBox mt={1.2} pt={1} sx={{ borderTop: `1px solid ${RULE}` }}>
                <MDTypography variant="caption" sx={HEAD}>
                  The bridge constant
                </MDTypography>
                <MDTypography variant="caption" sx={LINE}>
                  {`Composed, not measured: ${fmt(deployed.k, 2)} ÷ ${fmt(deployed.bridge_ratio, 3)}, the ratio in effect between the `
                    + `PSD band power and TD band power on the same survey and contact. `
                    + `Refit on ${br.n_surveys} surveys, ${br.n} of ${br.n_pairs} contact-and-centre pairs after the same 5 MAD rule: `
                    + `${fmt(br.ratio, 3)}${bridgeComparison(br, deployed)}`}
                </MDTypography>
              </MDBox>
              <MDBox mt={1}>
                <MDTypography variant="caption" sx={HEAD}>
                  The ratio per band centre: small points one contact pair each (blue left, orange right), large points the median; dashed = in effect
                </MDTypography>
                <div ref={bridgeRef} style={{ width: "100%" }} />
              </MDBox>

              {/* 3) THE THRESHOLD STREAMS (decision 447) */}
              {tc && tc.available ? (
                <MDBox mt={1.2} pt={1} sx={{ borderTop: `1px solid ${RULE}` }}>
                  <MDTypography variant="caption" sx={HEAD}>
                    Threshold streams against the PSD route
                  </MDTypography>
                  <MDTypography variant="caption" sx={LINE}>
                    {"Each threshold stream's median LSB, as the device read it while thresholds were set, "
                      + "against the LSB the bridge constant predicts from a device PSD of the same session "
                      + "and contact pair at the stream's sensing frequency. Current was being stepped, so "
                      + "single streams scatter; the medians test the constant."}
                  </MDTypography>
                  <div ref={thresholdRef} style={{ width: "100%" }} />
                </MDBox>
              ) : null}

              <MDTypography variant="caption" sx={{ ...LINE, mt: 1 }}>
                {`Where these are used: the Biomarkers timeline's modeled points (○ TD × ${fmt(deployed.k, 2)}, `
                  + `◇ PSD × ${fmt(deployed.bridge_lsb_per_device_uv2, 2)}); the Closed-Loop page's threshold for a band the device `
                  + "never sensed, and its three-source response panel. The Stim Optimizer reads device-native "
                  + "power and needs neither."}
              </MDTypography>
            </Fold>
          </>
        ) : null}
      </MDBox>
    </MDBox>
  );
}

export default CalibrationInEffectPanel;
