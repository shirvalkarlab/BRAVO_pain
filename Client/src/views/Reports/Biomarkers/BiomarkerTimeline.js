/**
 * BiomarkerTimeline -- clean stacked-subplot timeline for the unified biomarker frame.
 * Each measure (time-domain biomarker, power-domain band power + threshold, pain, stim amplitude) gets
 * its own row sharing one time axis, with human-readable names -- avoids a cluttered single plot
 * with a long horizontal legend. Self-contained via plotly.js-dist.
 */

import { useEffect, useRef } from "react";
import Plotly from "plotly.js-dist";

import MDBox from "components/MDBox";

// Okabe-Ito colorblind-safe palette, aligned with BiomarkerAnalytics.js. Pain uses vermillion
// (the HI color) so a viewer reading the histogram and the timeline together gets the same
// color identity for "pain" across panels.
const C = {
  td: "#0072B2",        // time-domain biomarker (blue)
  lfp: "#009E73",       // power-domain band power (green)
  threshold: "#7E8794", // learned threshold
  pain: "#D55E00",      // NRS / pain (vermillion = HI)
  stim: "#E69F00",      // stim amplitude (orange)
  programmed: "#6E0F8A",// device's currently-programmed adaptive trigger (muted purple, distinct
                        // from the grey learned threshold and the green/blue signals)
};

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
        const cx = (pc.time || []).map((t) => parseTime(t));
        const cy = (pc.band_power || []).map((v) => (typeof v === "number" ? v : null));
        const isChronic = pc.around_the_clock === true || pc.source_modality === "chronic";
        // Chronic (around-the-clock) and streaming series are physically different recordings; give
        // the chronic LFP-power log a distinct color so the two are not read as one trace.
        const lineColor = isChronic ? "#117733" : C.lfp;   // chronic green vs Okabe-Ito streaming green
        const tr = [{ name: isChronic ? "Chronic LFP power" : "Power", x: cx, y: cy, color: lineColor }];
        if (pc.threshold != null && Number.isFinite(pc.threshold)) {
          // Flat per-channel threshold line spanning this channel's own time extent.
          tr.push({ name: "Threshold", x: cx, y: cx.map(() => pc.threshold),
                    color: C.threshold, dash: "dash", mode: "lines" });
        }
        // Device's CURRENTLY-PROGRAMMED adaptive trigger for this hemisphere — drawn ONLY when
        // closed-loop stimulation is active (backend sends programmed_thresholds[hemi] only then).
        // A light, thin solid line in the units of band power: "this is what the device switches on now."
        const prog = pc.hemisphere ? progByHemi[pc.hemisphere] : null;
        if (prog && prog.lower != null && Number.isFinite(prog.lower)) {
          tr.push({ name: "Programmed trigger", x: cx, y: cx.map(() => prog.lower),
                    color: C.programmed, dash: "solid", mode: "lines", width: 1, opacity: 0.55 });
        }
        // Prefer the channel's own recorded center frequency (from the backend summary); fall back to
        // matching the recorded_powers card entry by label.
        const hz = (pc.center_hz != null && Number.isFinite(pc.center_hz))
          ? Number(pc.center_hz) : hzForChannel(pc.channel);
        const freqText = hz != null ? `${hz.toFixed(1)} Hz` : "sensing band";
        const fin = cy.filter((v) => v != null && Number.isFinite(v));
        const vmin = fin.length ? Math.min(...fin) : null;
        const vmax = fin.length ? Math.max(...fin) : null;
        const rangeText = vmin != null ? ` · range ${vmin.toFixed(0)}–${vmax.toFixed(0)} a.u.` : "";
        const hemiText = pc.hemisphere ? `${pc.hemisphere} · ` : "";
        const thrText = (pc.threshold != null && Number.isFinite(pc.threshold))
          ? ` · threshold ${pc.threshold.toFixed(1)}` : "";
        const progText = (prog && prog.lower != null && Number.isFinite(prog.lower))
          ? ` · programmed trigger ${prog.lower.toFixed(1)} (closed-loop active)` : "";
        // Chronic = BrainSense Timeline sampled ~every 10 min around the clock; streaming = per-session
        // BrainSense Power-Domain. Name the modality so the clinician knows which log a row is.
        const kindLbl = isChronic ? "Chronic ~10-min (around-the-clock)" : "Streaming band power";
        const srcTag = isChronic ? "Chronic" : "Streaming";
        rows.push({
          title: `Power [${srcTag}] — ${pc.channel} @ ${freqText}${rangeText}`,
          short: `Power ${pc.channel}`,
          unit: "Band power (a.u.)",
          ownX: true,                  // each channel carries its own x (timestamps differ per contact)
          traces: tr,
          subtitle: `${hemiText}${kindLbl} · recorded center ${freqText}${thrText}${progText}`,
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
    if (painCol) rows.push({ title: `Pain (${m})`, unit: m, isPain: true,
      traces: [{ name: m, y: col(painCol), color: C.pain, forceMarkers: true }] });
    const stimCol = pick("powerdomain_stim_amplitude", "td_stim_amplitude");
    if (stimCol) rows.push({ title: "Stimulation", unit: "mA", traces: [{ name: "Amplitude", y: col(stimCol), color: C.stim }] });

    const n = Math.max(rows.length, 1);
    const gap = 0.09;   // tighter inter-row gap fills vertical whitespace; titles still clear (halo)
    const h = (1 - gap * (n - 1)) / n;

    const traces = [];
    const layout = {
      height: height || 200 * n + 70,
      margin: { l: 64, r: 18, t: 24, b: 48 },   // tight top margin — kills the whitespace above the first row
      hovermode: "x unified",
      font: { family: "Roboto, Helvetica, Arial, sans-serif", size: 12, color: "#344767" },
      legend: { orientation: "h", y: 1.012, x: 0, font: { size: 11 } },
      annotations: [],
    };

    rows.forEach((row, di) => {
      const axisNum = n - di; // bottom row = y1
      const yk = axisNum === 1 ? "y" : "y" + axisNum;
      const yaxisKey = axisNum === 1 ? "yaxis" : "yaxis" + axisNum;
      const top = 1 - di * (h + gap);
      const bottom = Math.max(0, top - h);
      // Explicit padded y-range so the top data value never touches the row's upper edge (where the
      // row title sits) — auto-range alone clipped the peak of the first row. Pad 12% above max and
      // a small margin below min; fall back to autorange if the row has no finite data.
      const allY = row.traces.flatMap((tr) => (tr.y || [])).filter((v) => v != null && Number.isFinite(v));
      let yrange = null;
      if (allY.length) {
        const ymin = Math.min(...allY), ymax = Math.max(...allY);
        const span = ymax - ymin || Math.abs(ymax) || 1;
        yrange = [ymin - span * 0.06, ymax + span * 0.12];
      }
      layout[yaxisKey] = { domain: [bottom, top], title: { text: row.unit, font: { size: 11 } },
        zeroline: false, showgrid: true, gridcolor: "#F0F0F0", automargin: true,
        ...(yrange ? { range: yrange } : { autorange: true }) };
      row.traces.forEach((tr) => {
        // PAIN ROW (isPain): render exactly like the standalone Pain Scores report — translucent
        // thin raw markers+line plus a thick moving-average trend over the top. CRITICAL: the pain
        // column is sparse (one value per survey) embedded in a per-sample array full of nulls, so
        // a moving average over ARRAY indices just re-traces the raw values (a redundant double
        // line). Compact to the non-null (x, y) observations FIRST, then smooth over consecutive
        // observations — that produces a real trend identical to the PainScores report (which is
        // fed one point per survey with no gaps).
        if (row.isPain) {
          const cx = [], cy = [];
          (tr.y || []).forEach((v, i) => {
            if (v != null && Number.isFinite(v)) { cx.push(x[i]); cy.push(v); }
          });
          traces.push({
            x: cx, y: cy, name: tr.name, type: "scatter", mode: "lines+markers",
            line: { color: tr.color, width: 1.5 },
            marker: { size: 5, color: tr.color, line: { color: "white", width: 0.5 } },
            opacity: 0.55, yaxis: yk, xaxis: "x", connectgaps: false,
            hovertemplate: `${row.title} — ${tr.name}: %{y:.3g}<extra></extra>`,
          });
          if (cy.length >= 3) {
            traces.push({
              x: cx, y: movingAverage(cy, 3), name: `${tr.name} (3-pt avg)`, type: "scatter",
              mode: "lines", line: { color: tr.color, width: 3 },
              yaxis: yk, xaxis: "x", connectgaps: false, hoverinfo: "skip", showlegend: false,
            });
          }
          return;
        }
        // Biomarker/LFP rows are sparse session series (streaming PSD only runs on some days), so
        // rendering them as pure lines with connectgaps=false turns isolated sessions into thin
        // vertical spikes separated by whitespace. Always include markers (small dots) so each
        // session is visible and the plot reads as data rather than empty space; dashed reference
        // traces (threshold) stay lines-only.
        const isDashRef = tr.dash === "dash";
        const mode = tr.mode || (isDashRef ? "lines" : "lines+markers");
        traces.push({
          x: tr.x || x, y: tr.y, name: tr.name, type: "scatter", mode,
          line: { color: tr.color, width: tr.width != null ? tr.width : (isDashRef ? 2 : 1.4),
                  dash: tr.dash || "solid" },
          marker: { size: 3.5, color: tr.color },
          opacity: tr.opacity != null ? tr.opacity : 1,
          yaxis: yk, xaxis: "x", connectgaps: false,
          hovertemplate: `${row.short || row.title} — ${tr.name}: %{y:.3g}<extra></extra>`,
        });
      });
      layout.annotations.push({
        xref: "paper", yref: "paper", x: 0.004, y: Math.min(top + 0.02, 1),
        xanchor: "left", yanchor: "bottom", text: `<b>${row.title}</b>`,
        showarrow: false, font: { size: 12, color: "#344767" },
        bgcolor: "rgba(255,255,255,0.7)",   // halo so the title reads over traces
      });
      // Optional second line under the title (provenance detail) — smaller, same halo.
      if (row.subtitle) {
        layout.annotations.push({
          xref: "paper", yref: "paper", x: 0.004, y: Math.min(top + 0.02, 1),
          xanchor: "left", yanchor: "top", text: row.subtitle,
          showarrow: false, font: { size: 10, color: "#7E8794" },
          bgcolor: "rgba(255,255,255,0.7)",
        });
      }
    });

    layout.xaxis = { domain: [0, 1], type: "date", anchor: "y", title: { text: "Time", font: { size: 12 } },
      showgrid: true, gridcolor: "#F0F0F0" };

    Plotly.react(ref.current, traces, layout, {
      responsive: true, displaylogo: false,
      modeBarButtonsToRemove: ["select2d", "lasso2d", "autoScale2d", "toggleSpikelines"],
      toImageButtonOptions: { format: "png", scale: 2 },
    });
    return () => { if (ref.current) Plotly.purge(ref.current); };
  }, [data, height]);

  return (
    <MDBox p={1}>
      <div ref={ref} style={{ width: "100%" }} />
    </MDBox>
  );
}

export default BiomarkerTimeline;
