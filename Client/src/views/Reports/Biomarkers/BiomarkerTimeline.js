/**
 * BiomarkerTimeline -- clean stacked-subplot timeline for the unified biomarker frame.
 * Each measure (time-domain biomarker, power-domain band power + threshold, pain, stim amplitude) gets
 * its own row sharing one time axis, with human-readable names -- avoids a cluttered single plot
 * with a long horizontal legend. Self-contained via plotly.js-dist.
 */

import { useEffect, useRef, useState } from "react";
import Plotly from "plotly.js-dist";

import MDBox from "components/MDBox";

// Okabe-Ito colorblind-safe palette, aligned with BiomarkerAnalytics.js. Pain uses vermillion
// (the HI color) so a viewer reading the histogram and the timeline together gets the same
// color identity for "pain" across panels.
const C = {
  td: "#0072B2",        // time-domain biomarker (blue)
  lfp: "#009E73",       // power-domain band power (green) -- legacy fallback only
  threshold: "#7E8794", // learned threshold
  pain: "#D55E00",      // NRS / pain (vermillion = HI)
  stim: "#E69F00",      // stim amplitude (orange)
  programmed: "#1A1A1A",// device's currently-programmed adaptive trigger (near-black solid, neutral
                        // so it doesn't collide with the violet/green hemisphere signal families)
};

// HEMISPHERE COLOR FAMILIES. The two implanted targets are physically distinct (Left GPi vs Right
// VIM), so every power row is colored by hemisphere: violet = Left/GPi, green = Right/VIM. Within a
// family the chronic 24/7 log is a deeper/saturated shade and the per-session streaming contacts are
// a lighter shade of the same hue, so hemisphere AND modality both read straight off the trace color.
const HEMI = {
  Left:  { chronic: "#4B2E83", stream: "#9F7BD0", accent: "#5E3C99", region: "GPi" },
  Right: { chronic: "#0B6B2E", stream: "#5AB48A", accent: "#117733", region: "VIM" },
};
function hemiColor(hemi, isChronic) {
  const h = HEMI[hemi];
  if (!h) return isChronic ? "#117733" : C.lfp;        // non-lateralized fallback
  return isChronic ? h.chronic : h.stream;
}

// Break a line across recording gaps: insert an explicit null where two consecutive samples are more
// than `maxGapMs` apart, so the trace does NOT draw a straight interpolation across days with no data
// (Tufte: don't draw data you don't have). Returns [xOut, yOut].
const SIX_HOURS_MS = 6 * 3600 * 1000;
function breakGaps(xs, ys, maxGapMs = SIX_HOURS_MS) {
  const X = [], Y = [];
  for (let i = 0; i < xs.length; i++) {
    const xi = xs[i];
    if (i > 0 && xi != null && xs[i - 1] != null && (+xi - +xs[i - 1]) > maxGapMs) {
      X.push(new Date((+xs[i - 1] + +xi) / 2)); Y.push(null);
    }
    X.push(xi); Y.push(ys[i]);
  }
  return [X, Y];
}

// Linear-interpolated percentile over finite values (for robust per-row y-windows).
function percentile(arr, p) {
  const a = arr.filter((v) => v != null && Number.isFinite(v)).sort((x, y) => x - y);
  if (!a.length) return null;
  const idx = ((a.length - 1) * p) / 100;
  const lo = Math.floor(idx), hi = Math.ceil(idx);
  return lo === hi ? a[lo] : a[lo] + (a[hi] - a[lo]) * (idx - lo);
}

// Compact value formatting for edge / off-scale labels.
function fmtVal(v) {
  if (v == null || !Number.isFinite(v)) return "";
  const av = Math.abs(v);
  if (av >= 1000) return v.toLocaleString(undefined, { maximumFractionDigits: 0 });
  if (av >= 10) return v.toFixed(0);
  if (av >= 1) return v.toFixed(1);
  return v.toFixed(2);
}

function parseTime(t) {
  if (t === null || t === undefined) return null;
  if (typeof t === "number") return new Date(t < 1e12 ? t * 1000 : t);
  return new Date(t);
}

// Centered moving average over the non-null values (PainScores report uses a 3-point smooth as a
// thick trend line over translucent raw markers). Skips nulls so gaps don't drag the average.
function movingAverage(y, win = 3) {
  const half = Math.floor(win / 2);
  return y.map((_, i) => {
    let s = 0, c = 0;
    for (let j = i - half; j <= i + half; j++) {
      const v = y[j];
      if (j >= 0 && j < y.length && v != null && Number.isFinite(v)) { s += v; c += 1; }
    }
    return c ? s / c : null;
  });
}

function BiomarkerTimeline({ data, height }) {
  const ref = useRef(null);
  // LINK AXES: when true (default) every row shares one time axis, so panning/box-zooming any row
  // pans/zooms them all together (and the vertical gridlines re-tick in lockstep). When false each
  // row zooms independently. Implemented with Plotly per-row x-axes + `matches`.
  const [linked, setLinked] = useState(true);

  useEffect(() => {
    if (!ref.current || !data || !data.timeline || data.timeline.length === 0) return;

    const recs = data.timeline;
    const cols = new Set(data.channels || Object.keys(recs[0]));
    const x = recs.map((r) => parseTime(r.time));
    const col = (n) => recs.map((r) => (typeof r[n] === "number" ? r[n] : null));
    const has = (n) => cols.has(n) && col(n).some((v) => v !== null);
    const pick = (...names) => names.find((n) => has(n));

    // Rows, top -> bottom.
    const rows = [];
    if (has("td_biomarker_value")) {
      const b = data.summary && data.summary.timedomain && data.summary.timedomain.band;
      // Defensive: the biomarker is capped to < 50 Hz at selection time. If a stale/cached run still
      // carries an above-cap band, don't print a misleading >50 Hz frequency in the title.
      const fhz = b && typeof b[4] === "number" ? b[4] : null;
      const title = (fhz != null && fhz < 50)
        ? `Time-domain biomarker — ${fhz.toFixed(1)} Hz`
        : "Time-domain biomarker (PSD)";
      rows.push({
        title,
        unit: "PSD power",
        hemi: null,
        traces: [{ name: "PSD biomarker", y: col("td_biomarker_value"), color: C.td }],
      });
    }
    // POWER-DOMAIN ROWS. Each sensing contact gets its OWN row (no cross-channel pooling — you
    // program one contact at a time on the Percept RC, so a pooled trend has no implementation
    // meaning). The backend serializes data.power_channels (one entry per contact, each with its own
    // timestamps, band power, fitted threshold, hemisphere). Fall back to the legacy single pooled
    // series only if the per-channel split is absent (e.g. a stale cached run).
    const powerChannels = Array.isArray(data.power_channels) ? data.power_channels : [];
    // Device's currently-programmed adaptive thresholds, keyed by hemisphere — present ONLY for
    // hemispheres where closed-loop stim is active (backend gates this), so a row only shows the
    // programmed trigger when it is real and in force.
    const progByHemi = (data.programmed_thresholds && typeof data.programmed_thresholds === "object")
      ? data.programmed_thresholds : {};
    // Map each channel to its recorded center frequency (from recorded_powers) by matching the
    // contact label, so each row's title states the frequency the clinician actually senses on it.
    const rpAll = (data.recorded_powers || []).filter((p) => p && p.center_hz != null);
    const hzForChannel = (chName) => {
      const key = String(chName).trim();
      const hit = rpAll.find((p) => String(p.label).trim() === key);
      return hit ? Number(hit.center_hz) : null;
    };
    if (powerChannels.length) {
      powerChannels.forEach((pc) => {
        // A channel whose per-channel analytics failed comes through with empty_reason and no data.
        // Render it as a labeled EMPTY row so the clinician sees the contact was recorded but could
        // not be analyzed (rather than it silently vanishing from the timeline).
        if (pc.empty_reason && (!pc.time || pc.time.length === 0)) {
          const hemiE = pc.hemisphere && HEMI[pc.hemisphere] ? pc.hemisphere : null;
          const hzE = pc.center_hz != null && Number.isFinite(pc.center_hz)
            ? Number(pc.center_hz) : hzForChannel(pc.channel);
          const freqE = hzE != null ? `${hzE.toFixed(1)} Hz` : "sensing band";
          rows.push({
            title: `${pc.channel} @ ${freqE} — no analyzable data`,
            short: `Power ${pc.channel}`,
            unit: "Band power (a.u.)",
            ownX: true, hemi: hemiE, traces: [], refLines: [],
            emptyReason: String(pc.empty_reason),
            subtitle: `${pc.hemisphere ? pc.hemisphere + " · " : ""}recorded but not analyzable: ${pc.empty_reason}`,
          });
          return;
        }
        const cxRaw = (pc.time || []).map((t) => parseTime(t));
        const cyRaw = (pc.band_power || []).map((v) => (typeof v === "number" ? v : null));
        const isChronic = pc.around_the_clock === true || pc.source_modality === "chronic";
        const hemi = pc.hemisphere && HEMI[pc.hemisphere] ? pc.hemisphere : null;
        // Color by hemisphere family (violet Left / green Right), deeper for chronic, lighter for
        // streaming. Break the line across recording gaps so multi-day gaps aren't interpolated.
        const lineColor = hemiColor(pc.hemisphere, isChronic);
        const [cx, cy] = breakGaps(cxRaw, cyRaw);
        const tr = [{ name: isChronic ? "Chronic LFP power" : "Power", x: cx, y: cy,
                      color: lineColor, chronic: isChronic }];
        // Reference levels are carried as metadata and drawn as full-width SHAPES with a direct
        // right-edge label (not as legend traces) — cleaner, and they survive per-row zoom.
        const refLines = [];
        if (pc.threshold != null && Number.isFinite(pc.threshold)) {
          refLines.push({ y: pc.threshold, color: C.threshold, dash: "dash",
                          label: `thr ${fmtVal(pc.threshold)}` });
        }
        // Device's CURRENTLY-PROGRAMMED adaptive trigger for this hemisphere — ONLY when closed-loop
        // stim is active (backend sends programmed_thresholds[hemi] only then).
        const prog = pc.hemisphere ? progByHemi[pc.hemisphere] : null;
        const progActive = prog && prog.lower != null && Number.isFinite(prog.lower);
        if (progActive) {
          refLines.push({ y: prog.lower, color: C.programmed, dash: "solid",
                          label: `prog ${fmtVal(prog.lower)}`, opacity: 0.6 });
        }
        const hz = (pc.center_hz != null && Number.isFinite(pc.center_hz))
          ? Number(pc.center_hz) : hzForChannel(pc.channel);
        const freqText = hz != null ? `${hz.toFixed(1)} Hz` : "sensing band";
        const fin = cyRaw.filter((v) => v != null && Number.isFinite(v));
        const vmin = fin.length ? Math.min(...fin) : null;
        const vmax = fin.length ? Math.max(...fin) : null;
        const rangeText = vmin != null ? ` · range ${vmin.toFixed(0)}–${vmax.toFixed(0)} a.u.` : "";
        const hemiText = pc.hemisphere ? `${pc.hemisphere} · ` : "";
        const progText = progActive ? ` · programmed trigger ${prog.lower.toFixed(1)} (closed-loop active)` : "";
        const kindLbl = isChronic ? "Chronic ~10-min (around-the-clock)" : "Streaming band power";
        const srcTag = isChronic ? "Chronic 24/7" : "Streaming";
        rows.push({
          title: `${pc.channel} — ${srcTag} @ ${freqText}${rangeText}`,
          short: `Power ${pc.channel}`,
          unit: "Band power (a.u.)",
          ownX: true,                  // each channel carries its own x (timestamps differ per contact)
          hemi,
          traces: tr,
          refLines,
          subtitle: `${hemiText}${kindLbl} · recorded center ${freqText}${progText}`,
        });
      });
    } else if (has("powerdomain_biomarker_value")) {
      // Legacy fallback: single pooled series (only when no per-channel split is available).
      const tr = [{ name: "Power", y: col("powerdomain_biomarker_value"), color: C.lfp }];
      if (has("powerdomain_threshold")) {
        tr.push({ name: "Threshold", y: col("powerdomain_threshold"), color: C.threshold, dash: "dash", mode: "lines" });
      }
      const rp = rpAll;
      const hzList = Array.from(new Set(rp.map((p) => Number(p.center_hz))))
        .sort((a, b) => a - b).map((v) => v.toFixed(1));
      const contactList = Array.from(new Set(rp.map((p) => String(p.label).trim())));
      const freqText = hzList.length === 1 ? `${hzList[0]} Hz`
        : hzList.length > 1 ? `${hzList.join(" / ")} Hz` : "sensing band";
      const vals = col("powerdomain_biomarker_value").filter((v) => v !== null);
      const vmin = vals.length ? Math.min(...vals) : null;
      const vmax = vals.length ? Math.max(...vals) : null;
      const rangeText = vmin != null ? ` · range ${vmin.toFixed(0)}–${vmax.toFixed(0)} a.u.` : "";
      rows.push({
        title: `Power-domain band power @ ${freqText}${rangeText}`,
        short: "Power-domain band power",
        unit: "Band power (device units, a.u.)",
        traces: tr,
        subtitle: contactList.length ? `recorded center ${freqText}` : null,
      });
    }
    const m = data.label_metric || "nrs";
    const painCol = pick(`powerdomain_${m}`, `td_${m}_min`, `td_${m}_mean`, m, "powerdomain_nrs", "td_nrs_min", "nrs");
    // Always show the pain row as markers, not just a connecting line — each marker is one
    // pain observation (the standalone Pain Scores report renders them this way).
    if (painCol) rows.push({ title: `Pain (${m})`, unit: m, isPain: true, hemi: null,
      traces: [{ name: m, y: col(painCol), color: C.pain, forceMarkers: true }] });
    const stimCol = pick("powerdomain_stim_amplitude", "td_stim_amplitude");
    if (stimCol) rows.push({ title: "Stimulation", unit: "mA", hemi: null,
      traces: [{ name: "Amplitude", y: col(stimCol), color: C.stim }] });

    const n = Math.max(rows.length, 1);
    // Pixel-based row heights with a VARIABLE inter-row gap: each row is a fixed pixel band, and the
    // first row of a hemisphere block gets a larger gap above it to seat its big "LEFT/RIGHT
    // HEMISPHERE" signpost without overlapping the row above. Domains are computed cumulatively.
    const ROW_PX = 104, BASE_GAP = 0.007, BANNER_GAP = 0.052;
    const isStart = rows.map((row, i) => {
      let prev = null;
      for (let j = 0; j < i; j++) if (rows[j].hemi) prev = rows[j].hemi;
      return !!(row.hemi && row.hemi !== prev);
    });
    const nStarts = isStart.filter(Boolean).length;
    const totalGap = BASE_GAP * (n - 1) + BANNER_GAP * nStarts;
    const h = (1 - totalGap) / n;

    const traces = [];
    const layout = {
      height: height || ROW_PX * n + 70,
      margin: { l: 78, r: 104, t: 20, b: 42 },   // right margin holds edge ref-line labels + REAL/empty tag
      hovermode: "x unified",
      showlegend: false,                          // hemisphere color + direct edge labels replace the legend
      font: { family: "Roboto, Helvetica, Arial, sans-serif", size: 13, color: "#344767" },
      annotations: [],
      shapes: [],
    };

    let prevHemi = null;
    let cursor = 1.0;
    rows.forEach((row, di) => {
      const axisNum = n - di; // bottom row = y1
      const yk = axisNum === 1 ? "y" : "y" + axisNum;
      const xk = axisNum === 1 ? "x" : "x" + axisNum;
      const yaxisKey = axisNum === 1 ? "yaxis" : "yaxis" + axisNum;
      const xaxisKey = axisNum === 1 ? "xaxis" : "xaxis" + axisNum;
      if (di > 0) cursor -= (isStart[di] ? BANNER_GAP : BASE_GAP);
      const top = cursor;
      const bottom = Math.max(0, top - h);
      cursor = bottom;
      const hemi = row.hemi || null;
      const accent = hemi && HEMI[hemi] ? HEMI[hemi].accent : "#344767";

      // ROBUST y-window: scale to the signal's 0.5–99.5 percentile so the bulk of the trace fills the
      // row instead of being crushed by rare spikes; ALWAYS widen to include any reference level so
      // the threshold/programmed lines stay in view. Mark how many points fall above the window.
      const sig = row.traces.flatMap((tr) => (tr.y || [])).filter((v) => v != null && Number.isFinite(v));
      const refYs = (row.refLines || []).map((r) => r.y).filter((v) => v != null && Number.isFinite(v));
      let yrange = null, nOver = 0, peak = null;
      if (sig.length) {
        peak = Math.max(...sig);
        let plo = percentile(sig, 0.5), phi = percentile(sig, 99.5);
        if (phi <= plo) phi = plo + (Math.abs(plo) || 1);
        if (refYs.length) { plo = Math.min(plo, ...refYs); phi = Math.max(phi, ...refYs); }
        const span = phi - plo || Math.abs(phi) || 1;
        yrange = [plo - span * 0.06, phi + span * 0.10];
        nOver = sig.filter((v) => v > yrange[1]).length;
      }

      // Faint tint band for an unanalyzable placeholder row (cv_df=None) — marks it as "recorded but
      // not analyzable" so the empty band reads as intentional, not a rendering gap. Real data rows
      // are never tinted.
      if (row.emptyReason) {
        layout.shapes.push({ type: "rect", xref: `${xk} domain`, yref: `${yk} domain`,
          x0: 0, x1: 1, y0: 0, y1: 1, fillcolor: "#FBFBF4", line: { width: 0 }, layer: "below" });
      }
      layout[yaxisKey] = { domain: [bottom, top], title: { text: row.unit, font: { size: 11 }, standoff: 4 },
        zeroline: false, showgrid: false, automargin: true, nticks: 3, tickfont: { size: 10 },
        // colored y-axis spine = hemisphere accent (the accent IS the axis edge — no separate bar)
        showline: true, linewidth: hemi ? 4 : 1, linecolor: accent, mirror: false,
        ...(yrange ? { range: yrange } : { autorange: true }) };
      // Per-row x-axis. The bottom row owns the master x (`x`); all others `matches` it when LINKED so
      // pan/box-zoom moves every row together (and the vertical gridlines re-tick in lockstep). When
      // UNLINKED each row keeps its own independent zoom. Vertical gridlines are darker for visibility.
      layout[xaxisKey] = {
        domain: [0, 1], type: "date", anchor: yk,
        showgrid: true, gridcolor: "#C9CCD6", gridwidth: 1,
        showticklabels: di === n - 1,  // dates only on the bottom row; grid carries the time reference
        ticks: "", showline: false, tickfont: { size: 10.5 },
        ...(di === n - 1 ? { title: { text: "Time", font: { size: 12 } } } : {}),
        ...(axisNum !== 1 && linked ? { matches: "x" } : {}),
      };

      row.traces.forEach((tr) => {
        if (row.isPain) {
          const cx = [], cy = [];
          (tr.y || []).forEach((v, i) => {
            if (v != null && Number.isFinite(v)) { cx.push(x[i]); cy.push(v); }
          });
          traces.push({
            x: cx, y: cy, name: tr.name, type: "scatter", mode: "lines+markers",
            line: { color: tr.color, width: 1.5 },
            marker: { size: 5, color: tr.color, line: { color: "white", width: 0.5 } },
            opacity: 0.55, yaxis: yk, xaxis: xk, connectgaps: false, showlegend: false,
            hovertemplate: `${row.title} — ${tr.name}: %{y:.3g}<extra></extra>`,
          });
          if (cy.length >= 3) {
            traces.push({
              x: cx, y: movingAverage(cy, 3), name: `${tr.name} (3-pt avg)`, type: "scatter",
              mode: "lines", line: { color: tr.color, width: 3 },
              yaxis: yk, xaxis: xk, connectgaps: false, hoverinfo: "skip", showlegend: false,
            });
          }
          return;
        }
        // Chronic 24/7 logs are dense (~10-min sampling) — a thin line reads as an envelope and
        // markers would be noise; sparse streaming/biomarker/stim rows keep small markers so each
        // session is visible.
        const isChronic = tr.chronic === true;
        const mode = isChronic ? "lines" : "lines+markers";
        traces.push({
          x: tr.x || x, y: tr.y, name: tr.name, type: "scatter", mode,
          line: { color: tr.color, width: isChronic ? 0.9 : 1.5 },
          marker: { size: 3.4, color: tr.color },
          opacity: isChronic ? 0.9 : 1,
          yaxis: yk, xaxis: xk, connectgaps: false, showlegend: false,
          hovertemplate: `${row.short || row.title} — ${tr.name}: %{y:.3g}<extra></extra>`,
        });
      });

      // REFERENCE LINES as full-width shapes (paper-x, data-y) + a direct right-edge label. Dodge two
      // colliding labels so an equal thr/prog don't overprint.
      const refSorted = (row.refLines || []).slice().sort((a, b) => a.y - b.y);
      let lastLabelY = null;
      const ySpan = yrange ? yrange[1] - yrange[0] : 1;
      refSorted.forEach((rl) => {
        if (yrange && (rl.y < yrange[0] || rl.y > yrange[1])) return;  // skip out-of-window refs
        layout.shapes.push({
          type: "line", xref: "paper", x0: 0, x1: 1, yref: yk, y0: rl.y, y1: rl.y,
          line: { color: rl.color, width: rl.dash === "dash" ? 1.1 : 1.0, dash: rl.dash || "solid" },
          opacity: rl.opacity != null ? rl.opacity : 1, layer: "above",
        });
        let labelY = rl.y;
        if (lastLabelY != null && yrange && (labelY - lastLabelY) < 0.18 * ySpan) {
          labelY = lastLabelY + 0.18 * ySpan;
        }
        layout.annotations.push({
          xref: "paper", x: 1.007, yref: yk, y: labelY, xanchor: "left", yanchor: "middle",
          text: rl.label, showarrow: false, font: { size: 9.5, color: rl.color },
        });
        lastLabelY = labelY;
      });

      // OFF-SCALE caret: only when the peak meaningfully exceeds the visible window. Anchored TOP-LEFT
      // inside the row so it never collides with the right-edge ref-line labels or the REAL/empty tag.
      if (yrange && peak != null && peak > yrange[1] * 1.2) {
        layout.annotations.push({
          xref: `${xk} domain`, x: 0.013, yref: `${yk} domain`, y: 0.92,
          xanchor: "left", yanchor: "top",
          text: `▲ peak ${fmtVal(peak)} (off scale)`, showarrow: false,
          font: { size: 9.5, color: "#B06A00" },
        });
      }

      // EMPTY placeholder row: a centered note so the empty band reads as "recorded but not
      // analyzable" rather than a rendering glitch.
      if (row.emptyReason && (!row.traces || row.traces.length === 0)) {
        layout.annotations.push({
          xref: `${xk} domain`, x: 0.5, yref: `${yk} domain`, y: 0.5,
          xanchor: "center", yanchor: "middle",
          text: `no analyzable pain-aligned data — ${row.emptyReason}`,
          showarrow: false, font: { size: 10, color: "#9098A8", style: "italic" },
        });
      }

      // Row title — bigger, bold, colored to the hemisphere accent, anchored INSIDE the row (top-left)
      // with a halo so it reads over traces. The redundant provenance subtitle line was removed; the
      // title already carries hemisphere / center frequency / range.
      layout.annotations.push({
        xref: `${xk} domain`, yref: `${yk} domain`, x: 0.004, y: 0.97,
        xanchor: "left", yanchor: "top", text: `<b>${row.title}</b>`,
        showarrow: false, font: { size: 13.5, color: accent },
        bgcolor: "rgba(255,255,255,0.78)",
      });
      // BIG hemisphere signpost above the FIRST row of each hemisphere block.
      if (isStart[di] && hemi && HEMI[hemi]) {
        layout.annotations.push({
          xref: `${xk} domain`, yref: "paper", x: 0, y: top + 0.012,
          xanchor: "left", yanchor: "bottom",
          text: `<b>${hemi.toUpperCase()} HEMISPHERE</b>  ·  ${HEMI[hemi].region}`,
          showarrow: false, font: { size: 21, color: accent },
        });
      }
      if (hemi) prevHemi = hemi;
    });

    Plotly.react(ref.current, traces, layout, {
      responsive: true, displaylogo: false,
      modeBarButtonsToRemove: ["select2d", "lasso2d", "toggleSpikelines"],
      toImageButtonOptions: { format: "png", scale: 2 },
    });
    return () => { if (ref.current) Plotly.purge(ref.current); };
  }, [data, height, linked]);

  return (
    <MDBox p={1}>
      <div ref={ref} style={{ width: "100%" }} />
      <MDBox display="flex" alignItems="center" justifyContent="center" mt={1} mb={0.5}>
        <label style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer",
                        fontSize: 13, color: linked ? "#117733" : "#344767", userSelect: "none",
                        border: `1.5px solid ${linked ? "#117733" : "#C9CCD6"}`, borderRadius: 6,
                        padding: "5px 12px", background: linked ? "#F1F8F2" : "#FAFAFB",
                        transition: "all 0.15s" }}>
          <input type="checkbox" checked={linked} onChange={(e) => setLinked(e.target.checked)}
                 style={{ width: 15, height: 15, accentColor: "#117733", cursor: "pointer" }} />
          <b>🔗 LINK AXES</b>
          <span style={{ color: "#7E8794", fontWeight: 400 }}>
            {linked ? "— pan / zoom moves all rows together" : "— each row zooms independently"}
          </span>
        </label>
      </MDBox>
    </MDBox>
  );
}

export default BiomarkerTimeline;
