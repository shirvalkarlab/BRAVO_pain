/**
 * BiomarkerAnalytics -- reproduces Yiyuan Han's notebook biomarker figures, split into a
 * Time-domain section and a Chronic section:
 *   Time-domain: PSD correlation spectrum (R vs freq), mean PSD high-vs-low pain, PSD spectrogram.
 *   Chronic: sliding-window AUC+R+sens+spec+threshold, ROC curve, LFP/Otsu histogram, cluster scatter.
 * Channel labels use contact numbers + polarity + brain region (from the backend formatter).
 * Self-contained via plotly.js-dist.
 */

import { useEffect, useRef, useState, useMemo } from "react";
import Plotly from "plotly.js-dist";

import { Card, Grid, ToggleButton, ToggleButtonGroup } from "@mui/material";
import MDBox from "components/MDBox";
import MDTypography from "components/MDTypography";

// Publication-quality shared style for every panel — one font, faint gridlines, generous
// axis-title spacing (standoff), readable tick fonts, x-unified hover. Per-panel props can override
// any field by setting it on `layout` (a panel that passes layout.xaxis merges into the base xaxis).
const AXIS_BASE = {
  automargin: true, gridcolor: "#EEF1F4", zerolinecolor: "#D0D7DE", linecolor: "#B0B7BF",
  showline: true, mirror: false, ticks: "outside", ticklen: 4, tickcolor: "#B0B7BF",
  tickfont: { size: 11, color: "#495057" },
  title: { font: { size: 12, color: "#344767" }, standoff: 12 },
};
const FIG_BASE = {
  paper_bgcolor: "white", plot_bgcolor: "white",
  font: { family: "Roboto, Helvetica, Arial, sans-serif", size: 12, color: "#344767" },
  margin: { l: 64, r: 28, t: 44, b: 56 },
  legend: { orientation: "h", x: 0, y: -0.18, font: { size: 11 } },
  hovermode: "closest",
  hoverlabel: { bgcolor: "white", bordercolor: "#B0B7BF",
                font: { family: "Roboto, Helvetica, Arial, sans-serif", size: 11 } },
};
const mergeAxis = (override = {}) => ({
  ...AXIS_BASE, ...override,
  title: typeof override.title === "string"
    ? { ...AXIS_BASE.title, text: override.title }
    : { ...AXIS_BASE.title, ...(override.title || {}) },
});

function Fig({ traces, layout = {}, height = 320 }) {
  const ref = useRef(null);
  useEffect(() => {
    if (!ref.current || !traces || traces.length === 0) return;
    const base = {
      ...FIG_BASE, autosize: true, height,
      ...layout,
      xaxis: mergeAxis(layout.xaxis),
      yaxis: mergeAxis(layout.yaxis),
      ...(layout.yaxis2 ? { yaxis2: { ...AXIS_BASE, ...layout.yaxis2,
        title: typeof layout.yaxis2.title === "string"
          ? { ...AXIS_BASE.title, text: layout.yaxis2.title }
          : { ...AXIS_BASE.title, ...(layout.yaxis2.title || {}) } } } : {}),
    };
    Plotly.react(ref.current, traces, base, {
      responsive: true, displaylogo: false,
      modeBarButtonsToRemove: ["select2d", "lasso2d", "autoScale2d", "toggleSpikelines"],
      toImageButtonOptions: { format: "png", scale: 2 },   // crisp 2x PNG export for figures/slides
    });
    return () => { if (ref.current) Plotly.purge(ref.current); };
  }, [traces, layout, height]);
  return <div ref={ref} style={{ width: "100%", height }} />;
}

function Panel({ title, children, lg = 6 }) {
  return (
    <Grid item xs={12} lg={lg}>
      <Card sx={{ width: "100%", height: "100%", scrollMarginTop: "96px" }}>
        <MDBox p={2}>
          <MDTypography variant="h6" fontSize={17} mb={0.5}>{title}</MDTypography>
          {children}
        </MDBox>
      </Card>
    </Grid>
  );
}

function Section({ title, subtitle, panels, header = null }) {
  if (!panels || panels.length === 0) return null;
  return (
    <Grid item xs={12}>
      <MDBox mt={4} mb={2}>
        {/* Section header at ~2x the prior size for clear hierarchy between TD / power-domain. */}
        <MDTypography variant="h3" fontSize={40} fontWeight="bold">{title}</MDTypography>
        {subtitle ? <MDTypography variant="body2" color="dark">{subtitle}</MDTypography> : null}
      </MDBox>
      <Grid container spacing={3}>
        {header}
        {panels}
      </Grid>
    </Grid>
  );
}

// Okabe-Ito colorblind-safe palette (8% of males have red-green color blindness; this set is
// distinguishable to every common type and remains legible in grayscale). HI/LO pair: orange/blue
// (orange = high pain, blue = low pain) — the strongest contrast in the palette.
const HI = "#D55E00", LO = "#0072B2";   // vermillion / blue
const PALETTE = ["#0072B2", "#D55E00", "#009E73", "#CC79A7", "#56B4E9", "#E69F00", "#F0E442", "#000000"];

// Compact p-value formatter (scientific for tiny p), matching the report card's style.
const fmtP = (x) => {
  if (x === null || x === undefined || Number.isNaN(Number(x))) return "—";
  const n = Number(x);
  if (n > 0 && n < 1e-3) return n.toExponential(1);
  return n.toFixed(3);
};

// Friendly display names for the raw PRO feature keys (fallback: title-case the key).
const FEATURE_LABELS = {
  nrs: "NRS", vas: "Overall VAS", left_leg_vas: "Left Leg VAS", back_vas: "Back VAS",
  mpq_sum: "MPQ Sum", mpq_sen: "MPQ Sensory", mpq_aff: "MPQ Affective",
};
const featLabel = (k) => FEATURE_LABELS[k] || String(k).replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());

export default function BiomarkerAnalytics({ analytics, summary, metricLabel }) {
  // Hooks MUST be called unconditionally before any early return (React rules-of-hooks).
  const td = analytics ? (analytics.timedomain || {}) : {};
  const pdRoot = analytics ? (analytics.powerdomain || analytics.chronic || {}) : {};
  const perChannel = pdRoot.per_channel || {};
  const channelKeys = Object.keys(perChannel);
  const [chSel, setChSel] = useState("pooled");
  const safeChSel = (chSel === "pooled" || perChannel[chSel]) ? chSel : "pooled";
  const chronic = useMemo(() => (
    safeChSel === "pooled" ? pdRoot : { ...pdRoot, ...perChannel[safeChSel] }
  ), [safeChSel, pdRoot, perChannel]);

  if (!analytics) return null;

  // Human-readable pain score these correlations / AUCs are computed against (biological best
  // practice: every correlation/AUC panel should say what it is correlated WITH). Falls back gracefully.
  const pain = metricLabel || "pain";
  const tdSum = (summary && summary.timedomain) || {};
  const pdSum = (summary && summary.powerdomain) || {};
  // When a per-channel view is active, overlay its summary on the pooled one so the honest-perf
  // bar reflects the selected channel's AUC.
  const pdSumEff = safeChSel === "pooled" ? pdSum : { ...pdSum, ...(chronic.summary || {}) };
  const chSuffix = safeChSel === "pooled" ? "" : ` · ${safeChSel}`;

  // Chronic-trend sensing CENTER FREQUENCY per hemisphere (from the device's group-level sensing
  // config). The chronic 10-min trend is band power at a FIXED frequency, so state it. Different
  // from the streaming power-domain center frequencies shown per recorded-power channel.
  const chronicHz = pdRoot.chronic_center_hz || {};
  const chronicHzText = Object.keys(chronicHz).length
    ? " Chronic sensing band: " + Object.keys(chronicHz)
        .map((h) => `${h.replace("Hemisphere", "")} ${chronicHz[h]} Hz`).join(", ") + "."
    : "";

  // Short on-plot provenance string: which sensing band (center frequency) and which contact/
  // channel the power-domain signal comes from, so a reader never has to ask "power from WHERE?".
  // When a single channel is selected, name it; pooled view lists each hemisphere's chronic Hz.
  const powerProvenance = (() => {
    if (safeChSel !== "pooled") {
      const hzKey = Object.keys(chronicHz).find((h) => safeChSel.startsWith(h.replace("Hemisphere", "")));
      const hz = hzKey ? chronicHz[hzKey] : null;
      return `${safeChSel}${hz != null ? ` @ ${Number(hz).toFixed(1)} Hz` : ""}`;
    }
    const parts = Object.keys(chronicHz).map((h) => `${h.replace("Hemisphere", "")} @ ${Number(chronicHz[h]).toFixed(1)} Hz`);
    return parts.length ? parts.join(" · ") : null;
  })();
  // A short plotly annotation object pinning the provenance text to the top-left of a panel.
  const provenanceAnn = powerProvenance ? [{
    xref: "paper", yref: "paper", x: 0.0, y: 1.06, xanchor: "left", yanchor: "bottom",
    text: `Source: ${powerProvenance}`, showarrow: false,
    font: { size: 11, color: "#344767" },
  }] : [];

  // Time-ordered sensing reconfiguration timeline (center frequency or channel changed mid-record).
  // Emitted by the backend only when a real post-initial change occurred. Used to draw dashed
  // vertical change-markers over the sliding-window-over-time plot.
  const configChanges = (pdRoot.sensing_config_changes || [])
    .filter((c) => Array.isArray(c.changed) && !(c.changed.length === 1 && c.changed[0] === "initial"));

  // ---------------- TIME-DOMAIN ----------------
  const tdPanels = [];
  const spectrum = td.corr_spectrum || null;
  if (spectrum && spectrum.channels && spectrum.channels.length) {
    const f = spectrum.freqs;
    const traces = [];
    spectrum.channels.forEach((ch, ci) => {
      const color = PALETTE[ci % PALETTE.length];
      // Hover (not fixed labels) gives the value on demand, matching the other panels. The curve and
      // its peaks share a color + legendgroup, so toggling the curve in the legend also hides its stars.
      traces.push({ x: f, y: ch.r, name: ch.name, type: "scatter", mode: "lines",
        line: { width: 2, color }, connectgaps: false, legendgroup: ch.name,
        hovertemplate: "%{x:.1f} Hz · R=%{y:.2f}<extra>%{fullData.name}</extra>" });
      if (ch.peaks && ch.peaks.length) {
        // Stars only MARK the peaks (no permanent text); the value is read by hovering.
        traces.push({ x: ch.peaks.map((p) => p.freq), y: ch.peaks.map((p) => p.r),
          type: "scatter", mode: "markers", legendgroup: ch.name, showlegend: false,
          marker: { symbol: "star", size: 12, color, line: { width: 1, color: "#fff" } },
          name: `${ch.name} peak`,
          hovertemplate: "peak · %{x:.1f} Hz · R=%{y:.2f}<extra>%{fullData.name}</extra>" });
      }
    });
    // Biomarker frequency cap: the band selection and peak picking are restricted to < 50 Hz
    // (the validated theta/alpha/beta/low-gamma sensing range). Shade ≥ 50 Hz so the limit is
    // visible; the spectrum curve is still drawn full-range for context.
    const FCAP = 50;
    const fMax = (spectrum.freqs && spectrum.freqs.length) ? spectrum.freqs[spectrum.freqs.length - 1] : 100;
    tdPanels.push(
      <Panel key="spec" title={`PSD correlation with ${pain} (Pearson R vs frequency) — peaks marked with ★ (significance FDR-corrected)`} lg={12}>
        <Fig traces={traces} height={380} layout={{ xaxis: { title: "Frequency (Hz)" },
          yaxis: { title: `Correlation with ${pain} (R)`, range: [-1.05, 1.05], zeroline: true },
          legend: { orientation: "h", y: -0.2, groupclick: "togglegroup" },
          shapes: fMax > FCAP ? [{ type: "rect", xref: "x", yref: "paper", x0: FCAP, x1: fMax,
            y0: 0, y1: 1, fillcolor: "#9E9E9E", opacity: 0.12, line: { width: 0 } },
            { type: "line", xref: "x", yref: "paper", x0: FCAP, x1: FCAP, y0: 0, y1: 1,
              line: { color: "#7E8794", width: 1.5, dash: "dot" } }] : [],
          annotations: fMax > FCAP ? [{ x: FCAP, yref: "paper", y: 1.0, yanchor: "bottom",
            xanchor: "left", text: " ≥50 Hz excluded from biomarker selection", showarrow: false,
            font: { size: 10, color: "#7E8794" } }] : [] }} />
      </Panel>
    );
  }

  // Permutation null + per-session scatter — one row per hemisphere (Left, then Right).
  // Each row: LEFT panel = perm-null histogram with THIS channel's observed |R| marked;
  //           RIGHT panel = scatter of per-session log-power at peak freq vs pain label.
  // The "observed" line uses the channel's own max-|R| peak (argmax |R| for that electrode),
  // NOT the family-max perm_obs — so the title correctly shows e.g. "R Med. Thal @ 27.7 Hz".
  // The global perm_null (family-max under block-permuted labels) is still the background null;
  // a channel-specific |R| that exceeds the family-max null is very conservative and fair.
  if (tdSum.perm_null && tdSum.perm_null.length && spectrum && spectrum.channels) {
    const pStr = tdSum.perm_p == null ? "—" : fmtP(tdSum.perm_p);
    const nCells = spectrum.channels.length * (spectrum.freqs ? spectrum.freqs.length : 0);

    // Group channels by hemisphere so Left and Right each get their own row.
    const hemiOrder = ["Left", "Right"];
    const byHemi = {};
    spectrum.channels.forEach((ch) => {
      const h = ch.short && ch.short.startsWith("L") ? "Left"
              : ch.short && ch.short.startsWith("R") ? "Right" : "Other";
      if (!byHemi[h]) byHemi[h] = [];
      byHemi[h].push(ch);
    });

    hemiOrder.forEach((hemi) => {
      const hChans = byHemi[hemi] || [];
      if (!hChans.length) return;
      // Best channel for this hemisphere = highest |peak_r| (or highest |r| anywhere).
      const best = hChans.reduce((a, b) => {
        const ar = a.peak_scatter ? Math.abs(a.peak_scatter.peak_r || 0)
                                   : Math.max(...(a.r || [0]).map(Math.abs));
        const br = b.peak_scatter ? Math.abs(b.peak_scatter.peak_r || 0)
                                   : Math.max(...(b.r || [0]).map(Math.abs));
        return br > ar ? b : a;
      });
      const ps = best.peak_scatter;
      const peakFreq = ps ? ps.peak_freq : null;
      const peakR    = ps ? ps.peak_r    : null;
      const obsR     = peakR != null ? Math.abs(peakR) : tdSum.perm_obs;
      const chLabel  = best.region ? `${best.short} (${best.region})` : best.short;
      const freqLabel = peakFreq != null ? ` @ ${peakFreq.toFixed(1)} Hz` : "";
      const permColor = hemi === "Left" ? LO : HI;

      // Perm-null panel (left half of row).
      tdPanels.push(
        <Panel key={`perm_${hemi}`} lg={6}
          title={`${hemi} — perm. null vs observed: ${chLabel}${freqLabel} (p=${pStr})`}>
          <Fig height={300} traces={[
            { x: tdSum.perm_null, type: "histogram", name: "null (shuffled labels)",
              marker: { color: "#90A4AE" }, opacity: 0.82, nbinsx: 40,
              hovertemplate: "max|R|≈%{x:.2f} · %{y} shuffles<extra></extra>" },
          ]} layout={{
            xaxis: { title: "Family-max |R| (all contacts × freqs)", range: [0, 1] },
            yaxis: { title: "Permutations" }, bargap: 0.02, showlegend: false,
            shapes: obsR != null ? [{ type: "line", x0: obsR, x1: obsR,
              yref: "paper", y0: 0, y1: 1, line: { color: permColor, width: 2.5 } }] : [],
            annotations: obsR != null ? [{ x: obsR, yref: "paper", y: 1.04,
              yanchor: "bottom", xanchor: "center",
              text: `|R|=${obsR.toFixed(2)}${freqLabel}`,
              showarrow: false, font: { color: permColor, size: 10 } }] : [],
          }} />
          <MDTypography variant="caption" color="dark" display="block" mt={0.5}>
            {obsR != null
              ? `${chLabel}${freqLabel}: |R|=${obsR.toFixed(2)}, perm p=${pStr} ` +
                `(${tdSum.perm_n || tdSum.perm_null.length} block-shuffles, ~${nCells}-cell search).`
              : `Permutation null (${tdSum.perm_null.length} shuffles, perm p=${pStr}).`}
          </MDTypography>
        </Panel>
      );

      // Scatter panel (right half of row) — per-session log-power at peak freq vs pain.
      // Require a finite peakFreq too: the title/axis format it with .toFixed and would throw on null.
      if (ps && ps.x && ps.x.length && peakFreq != null && Number.isFinite(peakFreq)) {
        const trendLine = (() => {
          // Filter x/y JOINTLY: independent .filter() calls misalign the pair when a null sits at
          // different indices in x vs y (and make the two arrays different lengths), corrupting the
          // slope. Keep only sessions where BOTH coordinates are finite.
          const xs = [], ys = [];
          (ps.x || []).forEach((vx, i) => {
            const vy = ps.y ? ps.y[i] : null;
            if (vx != null && Number.isFinite(vx) && vy != null && Number.isFinite(vy)) { xs.push(vx); ys.push(vy); }
          });
          if (xs.length < 3) return null;
          const n = xs.length;
          const mx = xs.reduce((s, v) => s + v, 0) / n;
          const my = ys.reduce((s, v) => s + v, 0) / n;
          const num = xs.reduce((s, v, i) => s + (v - mx) * (ys[i] - my), 0);
          const den = xs.reduce((s, v) => s + (v - mx) ** 2, 0);
          if (den === 0) return null;
          const slope = num / den, int = my - slope * mx;
          const xmin = Math.min(...xs), xmax = Math.max(...xs);
          return { x: [xmin, xmax], y: [xmin * slope + int, xmax * slope + int] };
        })();
        const scatterTraces = [
          { x: ps.x, y: ps.y, type: "scatter", mode: "markers", name: "sessions",
            marker: { color: permColor, size: 6, opacity: 0.7 },
            text: ps.dates || [],
            hovertemplate: `log power=%{x:.2f}<br>${pain}=%{y:.2f}%{text}<extra></extra>` },
        ];
        if (trendLine) scatterTraces.push({
          x: trendLine.x, y: trendLine.y, type: "scatter", mode: "lines",
          name: "linear fit", line: { color: permColor, width: 1.5, dash: "dot" },
          hoverinfo: "skip", showlegend: false,
        });
        tdPanels.push(
          <Panel key={`scatter_${hemi}`} lg={6}
            title={`${hemi} — log power at ${peakFreq.toFixed(1)} Hz vs ${pain}: ${chLabel}`}>
            <Fig height={300} traces={scatterTraces} layout={{
              xaxis: { title: `Log PSD at ${peakFreq.toFixed(1)} Hz` },
              yaxis: { title: pain },
              legend: { orientation: "h", y: -0.2 },
            }} />
            <MDTypography variant="caption" color="dark" display="block" mt={0.5}>
              {`Each dot = one recording session. R=${(peakR || 0).toFixed(2)} at the peak frequency.`}
            </MDTypography>
          </Panel>
        );
      }
    });
  }

  // Mean PSD by pain state, per contact — grouped into a LEFT-hemisphere column and a
  // RIGHT-hemisphere column, each wrapped in a thick black border (so the three left contacts
  // and three right contacts read as two anatomical blocks). yaxis autorange + a small headroom
  // pad fixes the previous top-of-curve clipping.
  const spectra = td.psd_spectra || null;
  if (spectra && spectra.channels) {
    const oneSpectrum = (ch, i) => {
      const traces = [
        { x: spectra.freqs, y: ch.high, name: `High ${pain}`, type: "scatter", mode: "lines", line: { color: HI, width: 2 }, connectgaps: false },
        { x: spectra.freqs, y: ch.low, name: `Low ${pain}`, type: "scatter", mode: "lines", line: { color: LO, width: 2 }, connectgaps: false },
      ];
      return (
        <MDBox key={"psd" + i} mb={1.5}>
          <MDTypography variant="h6" fontSize={15} mb={0.25}>
            {`${ch.short}${ch.region ? ` · ${ch.region}` : ""}`}
          </MDTypography>
          <Fig height={260} traces={traces} layout={{
            xaxis: { title: "Frequency (Hz)" },
            yaxis: { title: `Power (${spectra.unit})`, autorange: true, rangemode: "normal", automargin: true },
            margin: { l: 64, r: 20, t: 16, b: 44 },
            legend: { orientation: "h", y: -0.28 } }} />
        </MDBox>
      );
    };
    const leftCh = [], rightCh = [], otherCh = [];
    spectra.channels.forEach((ch, i) => {
      const s = ch.short || "";
      (s.startsWith("L") ? leftCh : s.startsWith("R") ? rightCh : otherCh).push(oneSpectrum(ch, i));
    });
    const hemiColumn = (figs, label, key) => figs.length ? (
      <Grid item xs={12} lg={6} key={key}>
        <Card sx={{ width: "100%", height: "100%", border: "2.5px solid #1A1A1A", boxShadow: "none", borderRadius: 2 }}>
          <MDBox p={2}>
            <MDTypography variant="h6" fontSize={17} mb={1} fontWeight="bold">
              {`Mean PSD by ${pain} — ${label}`}
            </MDTypography>
            {figs}
          </MDBox>
        </Card>
      </Grid>
    ) : null;
    const lcol = hemiColumn(leftCh, "Left hemisphere", "psd-left");
    const rcol = hemiColumn(rightCh, "Right hemisphere", "psd-right");
    if (lcol) tdPanels.push(lcol);
    if (rcol) tdPanels.push(rcol);
    if (otherCh.length) tdPanels.push(
      <Grid item xs={12} key="psd-other">
        <Card sx={{ width: "100%", border: "2.5px solid #1A1A1A", boxShadow: "none", borderRadius: 2 }}>
          <MDBox p={2}>
            <MDTypography variant="h6" fontSize={17} mb={1} fontWeight="bold">{`Mean PSD by ${pain}`}</MDTypography>
            {otherCh}
          </MDBox>
        </Card>
      </Grid>
    );
  }

  // (PSD spectrograms removed — they added little over the correlation spectrum + mean-PSD panels.)

  const scs = td.sliding_corr_spectrum || null;
  if (scs && scs.channels && scs.channels.length) {
    scs.channels.forEach((ch, i) => {
      if (!Array.isArray(ch.freqs) || !ch.freqs.length) return;   // skip channels with no freq axis
      const traces = [{ type: "heatmap", z: ch.r, x: ch.window_starts, y: ch.freqs,
        colorscale: "RdBu", reversescale: true, zmid: 0, zmin: -1, zmax: 1,
        colorbar: { title: { text: "R", side: "right" }, thickness: 12, len: 0.9 },
        hovertemplate: "%{x|%b %d %Y} · %{y:.1f} Hz · R=%{z:.2f}<extra></extra>" }];
      // 50 Hz biomarker cap: never display a sliding-correlation axis above 50 Hz.
      const fLo = Math.min(...ch.freqs);
      tdPanels.push(
        <Panel key={"scs" + i} lg={12}
          title={`Sliding correlation with ${pain} (R: frequency × time) — ${ch.channel}`}>
          <Fig traces={traces} height={360}
            layout={{ xaxis: { title: "Window start", type: "date" },
              yaxis: { title: "Frequency (Hz)", range: [Number.isFinite(fLo) ? fLo : 0, 50] } }} />
        </Panel>
      );
    });
  }

  // ---------------- CHRONIC ----------------
  const chPanels = [];
  // sliding_window is now {windows, summary} (was a bare list). Tolerate both shapes for back-compat.
  const swRaw = chronic.sliding_window;
  const swWindows = Array.isArray(swRaw) ? swRaw : (swRaw && swRaw.windows) || [];
  const swSummary = (swRaw && !Array.isArray(swRaw) && swRaw.summary) || null;
  if (swWindows.length) {
    const x = swWindows.map((w) => w.test_start);
    // connectgaps=true keeps the trace continuous across skipped windows. The skips are honest
    // (one-class test folds) and the backend caption below tells the reader the coverage.
    const mk = (key, name, opts = {}) => ({ x, y: swWindows.map((w) => w[key]), name, type: "scatter",
      mode: "lines+markers", marker: { size: 6 }, connectgaps: true, ...opts });
    const traces = [
      mk("auc", "AUC", { line: { width: 3, color: PALETTE[0] } }),
      mk("r", "Pearson R", { line: { width: 3, color: PALETTE[1] } }),
      mk("sens", "Sensitivity", { line: { width: 1.5, color: PALETTE[2], dash: "dot" } }),
      mk("spec", "Specificity", { line: { width: 1.5, color: PALETTE[5], dash: "dot" } }),
      mk("threshold", "Threshold", { yaxis: "y2", mode: "lines",
        line: { width: 1.5, color: "#7E8794", dash: "dash" }, hovertemplate: "thr=%{y:.1f}<extra></extra>" }),
    ];
    // Dashed vertical change-markers: a line + label at each timepoint where the sensing center
    // frequency or source channel changed during the record. Each marker is annotated with what
    // changed and the new config, so a mid-record reconfiguration is unmistakable on the time axis.
    // When a single channel is selected, show only that hemisphere's changes.
    const relChanges = configChanges.filter((c) =>
      safeChSel === "pooled" || safeChSel.startsWith(c.hemi.replace("Hemisphere", "")));
    const changeShapes = relChanges.map((c) => ({
      type: "line", x0: c.t, x1: c.t, yref: "paper", y0: 0, y1: 1,
      line: { color: "#111111", width: 1.5, dash: "dash" },
    }));
    const changeAnns = relChanges.map((c, i) => {
      const what = c.changed.join(" + ");
      const hzTxt = c.center_hz != null ? `${Number(c.center_hz).toFixed(1)} Hz` : "";
      const detail = [c.channel, hzTxt].filter(Boolean).join(" · ");
      return {
        x: c.t, yref: "paper", y: i % 2 === 0 ? 1.02 : 0.92, xanchor: "left", yanchor: "bottom",
        text: `▸ ${c.hemi.replace("Hemisphere", "")} ${what} change<br>${detail}`,
        showarrow: false, align: "left", font: { size: 9, color: "#111111" },
        bgcolor: "rgba(255,255,255,0.7)",
      };
    });
    chPanels.push(
      <Panel key="sw" title={`Sliding-window performance over time — power vs ${pain}${chSuffix}`} lg={12}>
        <Fig height={360} traces={traces} layout={{
          xaxis: { type: "date", title: "Test window start" },
          yaxis: { title: "AUC / R / Sensitivity / Specificity", range: [-1.05, 1.05],
                   zeroline: true, zerolinewidth: 1 },
          yaxis2: { title: "Power threshold (device units)", overlaying: "y", side: "right",
                    showgrid: false },
          hovermode: "x unified",
          // 0.5 reference for the AUC ceiling-vs-chance read, plus any sensing-config change markers.
          shapes: [{ type: "line", x0: x[0], x1: x[x.length - 1], y0: 0.5, y1: 0.5, yref: "y",
                     line: { color: "#C8CED5", width: 1, dash: "dot" } }, ...changeShapes],
          annotations: [...provenanceAnn, ...changeAnns],
        }} />
        {swSummary ? (
          <MDTypography variant="caption" color="dark" display="block" mt={1} fontStyle="italic" sx={{ fontSize: 11 }}>
            {(powerProvenance ? `Power signal from ${powerProvenance}. ` : "") +
             `Reporting ${swSummary.n_with_auc} of ${swSummary.n_total} candidate windows where both pain classes appeared in the test fold (within an expansion cap of ${swSummary.max_test_days} days). ` +
             `Skipped: ${swSummary.n_skipped_test_one_class} for one-class test folds (common with tertile binarization — the excluded middle leaves stretches of all-low or all-high days) and ${swSummary.n_skipped_no_data} for empty/degenerate folds.` +
             (relChanges.length ? ` Dashed vertical lines mark ${relChanges.length} sensing-config change(s) (center frequency or channel).` : "")}
          </MDTypography>
        ) : null}
      </Panel>
    );
  }

  // Honest performance vs overfit: the threshold-free in-sample AUC looks strong, but the
  // cross-validated balanced accuracy (the generalization estimate) sits near the chance baseline.
  // Plotting them side by side makes the generalization gap explicit. (new honest-stats panel)
  if (pdSumEff.auc != null || pdSumEff.balanced_accuracy != null) {
    const chanceLvl = pdSumEff.chance_accuracy != null ? pdSumEff.chance_accuracy : 0.5;
    const labels = ["In-sample AUC", "CV balanced accuracy", "Chance"];
    const vals = [pdSumEff.auc, pdSumEff.balanced_accuracy, chanceLvl];
    const colors = [PALETTE[0], PALETTE[2], "#7E8794"];
    chPanels.push(
      <Panel key="honest" title={`Honest performance: in-sample vs cross-validated — power vs ${pain}${chSuffix}`}>
        <Fig height={320} traces={[{ x: labels, y: vals.map((v) => (v == null ? null : v)),
          type: "bar", marker: { color: colors, line: { color: "#344767", width: 0.5 } },
          text: vals.map((v) => (v == null ? "" : v.toFixed(2))), textposition: "outside",
          textfont: { size: 12, color: "#344767" },
          hovertemplate: "%{x}: %{y:.3f}<extra></extra>" }]}
          layout={{ yaxis: { title: "Score", range: [0, 1.05] }, xaxis: { title: "" },
            showlegend: false,
            shapes: [{ type: "line", x0: -0.5, x1: 2.5,
              y0: chanceLvl, y1: chanceLvl,
              line: { color: "#7E8794", width: 1, dash: "dot" } }] }} />
        <MDTypography variant="caption" color="dark" display="block" mt={1} sx={{ fontSize: 11 }}>
          {`Chance for BALANCED accuracy is 0.50 regardless of class imbalance (sens & spec each ` +
           `0.5 at chance). ` +
           (pdSumEff.majority_accuracy != null
             ? `The majority-class baseline (${pdSumEff.majority_accuracy.toFixed(2)}) is the chance level for RAW accuracy only and is NOT the comparator here. `
             : "") +
           `In-sample AUC has no train/test split (optimistic); CV balanced accuracy is the held-out ` +
           `generalization estimate — near 0.5 means the in-sample AUC is not reproduced out-of-fold.` +
           `${pdSumEff.overfit_warning ? "  ⚠ " + pdSumEff.overfit_warning : ""}`}
        </MDTypography>
      </Panel>
    );
  }
  // ROC panel. Build it whenever there is at least one curve to draw. Two overlays, each a labeled
  // legend entry so the reader can tell the signals apart:
  //   (1) PER-SIGNAL — when "All contacts" is selected and the backend split the stream per
  //       channel, draw one ROC per channel (its own AUC in the legend) plus the pooled curve.
  //       When a single channel is selected, draw just that channel's curve.
  //   (2) PER-WINDOW — when a sliding window is active, overlay each window's ROC as a faint line,
  //       so the spread of operating curves over time is visible (one representative window labeled
  //       in the legend; the rest share a legend group to avoid a 30-entry legend).
  const roc = chronic.roc || null;
  const rocTraces = [];
  // (1) Per-signal curves.
  if (safeChSel === "pooled" && channelKeys.length >= 1) {
    channelKeys.forEach((k, i) => {
      const r = perChannel[k] && perChannel[k].roc;
      if (r && r.fpr && r.fpr.length) {
        rocTraces.push({ x: r.fpr, y: r.tpr, name: `${k} (AUC=${(r.auc ?? 0).toFixed(3)})`,
          type: "scatter", mode: "lines", line: { width: 2.5, color: PALETTE[i % PALETTE.length] },
          hovertemplate: `${k}<br>FPR=%{x:.2f} · TPR=%{y:.2f}<extra></extra>` });
      }
    });
    if (roc && roc.fpr && roc.fpr.length) {
      rocTraces.push({ x: roc.fpr, y: roc.tpr, name: `All contacts (AUC=${(roc.auc ?? 0).toFixed(3)})`,
        type: "scatter", mode: "lines", line: { width: 3, color: "#000000", dash: "solid" },
        hovertemplate: "All contacts<br>FPR=%{x:.2f} · TPR=%{y:.2f}<extra></extra>" });
    }
  } else if (roc && roc.fpr && roc.fpr.length) {
    rocTraces.push({ x: roc.fpr, y: roc.tpr,
      name: `${safeChSel === "pooled" ? "All contacts" : safeChSel} (AUC=${(roc.auc ?? 0).toFixed(3)})`,
      type: "scatter", mode: "lines", line: { width: 3, color: PALETTE[0] },
      fill: "tozeroy", fillcolor: "rgba(0,114,178,0.12)",
      hovertemplate: "FPR=%{x:.2f}<br>TPR=%{y:.2f}<extra></extra>" });
  }
  // (2) Per-window curves (sliding window active). Drawn faint; first one labeled, rest grouped.
  const swForRoc = Array.isArray(chronic.sliding_window)
    ? chronic.sliding_window : (chronic.sliding_window && chronic.sliding_window.windows) || [];
  const windowRocs = swForRoc.filter((w) => w.roc && w.roc.fpr && w.roc.fpr.length);
  if (windowRocs.length) {
    windowRocs.forEach((w, i) => {
      const dateLbl = (w.test_start || "").slice(0, 10);
      rocTraces.push({ x: w.roc.fpr, y: w.roc.tpr,
        name: i === 0 ? `Per-window ROC (${windowRocs.length} windows)` : "per-window",
        legendgroup: "perwindow", showlegend: i === 0,
        type: "scatter", mode: "lines",
        line: { width: 1, color: "rgba(213,94,0,0.45)" },
        hovertemplate: `window ${dateLbl}<br>FPR=%{x:.2f} · TPR=%{y:.2f}<extra></extra>` });
    });
  }
  if (rocTraces.length) {
    rocTraces.push({ x: [0, 1], y: [0, 1], name: "chance", type: "scatter", mode: "lines",
      line: { width: 1, color: "#7E8794", dash: "dash" }, hoverinfo: "skip" });
    const perWinNote = windowRocs.length
      ? ` · ${windowRocs.length} per-window curves` : "";
    chPanels.push(
      <Panel key="roc" title={`ROC curve — power vs ${pain}${chSuffix} (in-sample)${perWinNote}`}>
        <Fig height={360} traces={rocTraces} layout={{
          xaxis: { title: "False positive rate", range: [-0.02, 1.02], scaleanchor: "y", scaleratio: 1 },
          yaxis: { title: "True positive rate", range: [-0.02, 1.02] },
          legend: { orientation: "h", y: -0.2 },
          annotations: provenanceAnn }} />
        {powerProvenance ? (
          <MDTypography variant="caption" color="dark" display="block" mt={1} sx={{ fontSize: 11 }}>
            {`Power signal from ${powerProvenance}.` +
             (channelKeys.length >= 1 && safeChSel === "pooled"
               ? " Each colored curve is one bipolar sensing contact; the black curve pools all contacts."
               : "") +
             (windowRocs.length ? " Faint orange curves are individual sliding-window ROCs." : "")}
          </MDTypography>
        ) : null}
      </Panel>
    );
  }
  const dist = chronic.lfp_distribution || null;
  // Need one more edge than counts to form bin centers; without it every center is NaN.
  if (dist && dist.counts && dist.counts.length
      && Array.isArray(dist.bin_edges) && dist.bin_edges.length >= dist.counts.length + 1) {
    const edges = dist.bin_edges;
    const centers = dist.counts.map((_, i) => (edges[i] + edges[i + 1]) / 2);
    chPanels.push(
      <Panel key="dist" title={`Power band-power distribution + Otsu split${chSuffix}`}>
        <Fig height={340} traces={[{
          x: centers, y: dist.counts, type: "bar",
          marker: { color: PALETTE[0], line: { width: 0 } }, opacity: 0.85,
          hovertemplate: "band power=%{x:.1f}<br>%{y:,} samples<extra></extra>",
        }]}
          layout={{
            xaxis: { title: "Power band power (device units, 1st–99th pct display range)" },
            yaxis: { title: "Sample count" }, bargap: 0.04,
            shapes: dist.otsu != null ? [{ type: "line", x0: dist.otsu, x1: dist.otsu, yref: "paper",
              y0: 0, y1: 1, line: { color: PALETTE[1], width: 2.5, dash: "dash" } }] : [],
            annotations: [
              ...(dist.otsu != null ? [{ x: dist.otsu, yref: "paper", y: 1.02,
                text: `Otsu = ${dist.otsu.toFixed(1)}`, showarrow: false,
                font: { color: PALETTE[1], size: 11 }, xanchor: "left", yanchor: "bottom" }] : []),
              ...provenanceAnn,
            ] }} />
        <MDTypography variant="caption" color="dark" display="block" mt={1} sx={{ fontSize: 11 }}>
          {(powerProvenance ? `Power signal from ${powerProvenance}. ` : "") +
           `${(dist.n_total || 0).toLocaleString()} samples; histogram is plotted over the robust ` +
           `1st–99th percentile so the bulk is visible. ` +
           (dist.n_clipped ? `${dist.n_clipped.toLocaleString()} extreme outlier sample(s) sit off-range (Otsu still computed on all data).` : "")}
        </MDTypography>
      </Panel>
    );
  }
  // (The "Pain-level clusters" panel was removed — it duplicated the binarization preview card
  // at the top of the report, which already shows the high/low split on the selected metric.)

  // ---------------- PAIN-LABEL BINARIZATION (top of the report) ----------------
  // Show the raw distribution of the SELECTED pain score and exactly how it is split into the binary
  // high/low pain_level the detector is trained against — the foundation for every correlation/AUC below.
  const binData = chronic.pain_binarization || null;
  const binStrategy = (binData && binData.strategy) || "kmeans";
  const isTertile = binStrategy === "tertile" || binStrategy === "percentile";
  const STRAT_LABEL = { tertile: "tertile split (drop middle)", percentile: "percentile split (drop middle)",
    median: "median split", kmeans: "2-cluster KMeans labeler", cutoff: "fixed cutoff" };
  const binPanels = [];
  if (binData && binData.features && binData.features.length) {
    binData.features.forEach((ft, i) => {
      const name = featLabel(ft.name);
      // Tertile: the two cuts are the low/high percentile lines; the middle band is excluded.
      // Single-threshold strategies (median/kmeans/cutoff): one empirical boundary.
      let loCut = ft.boundary, hiCut = ft.boundary;
      if (isTertile && ft.p_low != null && ft.p_high != null) { loCut = ft.p_low; hiCut = ft.p_high; }
      const lo = ft.values.filter((v) => loCut != null && v <= loCut);
      const hi = ft.values.filter((v) => hiCut != null && v >= hiCut);
      const mid = isTertile ? ft.values.filter((v) => loCut != null && hiCut != null && v > loCut && v < hiCut) : [];
      const shapes = [];
      const anns = [];
      if (isTertile && loCut != null && hiCut != null) {
        // shade the excluded middle band
        shapes.push({ type: "rect", x0: loCut, x1: hiCut, yref: "paper", y0: 0, y1: 1,
          fillcolor: "#9E9E9E", opacity: 0.12, line: { width: 0 } });
        [[loCut, "low cut"], [hiCut, "high cut"]].forEach(([val, lbl]) => {
          shapes.push({ type: "line", x0: val, x1: val, yref: "paper", y0: 0, y1: 1,
            line: { color: "#111", width: 2 } });
          anns.push({ x: val, yref: "paper", y: 1, yanchor: "bottom", xanchor: "center",
            text: `${lbl} ${val.toFixed(1)}`, showarrow: false, font: { size: 10, color: "#111" } });
        });
      } else if (ft.boundary != null) {
        shapes.push({ type: "line", x0: ft.boundary, x1: ft.boundary, yref: "paper", y0: 0, y1: 1,
          line: { color: "#111", width: 2.5 } });
        anns.push({ x: ft.boundary, yref: "paper", y: 1, yanchor: "bottom", xanchor: "center",
          text: `cut ${ft.boundary.toFixed(1)}${ft.boundary_percentile != null ? ` (${ft.boundary_percentile.toFixed(0)}th pct)` : ""}`,
          showarrow: false, font: { size: 10, color: "#111" } });
      }
      [["30th", ft.p30], ["70th", ft.p70]].forEach(([lbl, val]) => {
        if (val != null && !isTertile) {
          shapes.push({ type: "line", x0: val, x1: val, yref: "paper", y0: 0, y1: 1,
            line: { color: "#9E9E9E", width: 1, dash: "dot" } });
          anns.push({ x: val, yref: "paper", y: 0.9, yanchor: "top", xanchor: "center",
            text: lbl, showarrow: false, font: { size: 9, color: "#9E9E9E" } });
        }
      });
      const traces = [
        { x: lo, type: "histogram", name: "low pain", marker: { color: LO }, opacity: 0.65,
          hovertemplate: `${name}=%{x}<br>low pain · %{y} day(s)<extra></extra>` },
        { x: hi, type: "histogram", name: "high pain", marker: { color: HI }, opacity: 0.65,
          hovertemplate: `${name}=%{x}<br>high pain · %{y} day(s)<extra></extra>` },
      ];
      if (isTertile && mid.length) {
        traces.push({ x: mid, type: "histogram", name: "excluded (middle)", marker: { color: "#9E9E9E" }, opacity: 0.45,
          hovertemplate: `${name}=%{x}<br>excluded · %{y} day(s)<extra></extra>` });
      }
      // Daily excluded-middle count — matches the histogram bars (drawn over ft.values, n_obs days).
      // (binData.n_excluded_middle is the PER-SAMPLE excluded count and does not match these bars.)
      const nMid = isTertile ? mid.length : 0;
      binPanels.push(
        <Panel key={"bin" + i} lg={binData.features.length > 1 ? 6 : 12}
          title={`Pain-score binarization — ${name}`}>
          <Fig height={320} traces={traces}
            layout={{ barmode: "overlay", xaxis: { title: name },
            yaxis: { title: "PRO observations (days)" }, legend: { orientation: "h", y: -0.25 },
            shapes, annotations: anns }} />
          <MDTypography variant="caption" color="dark" display="block" mt={1}>
            {`Daily ${name} split into high vs low pain by the ${STRAT_LABEL[binStrategy] || binStrategy}, ` +
             `with the cut computed on the daily distribution (not the density-weighted samples). ` +
             (isTertile
               ? (binData.low_pct != null && binData.high_pct != null
                   ? `Days ≤ ${binData.low_pct.toFixed(0)}th pct → low, ≥ ${binData.high_pct.toFixed(0)}th pct → high; ` +
                     `the shaded middle band (${nMid.toLocaleString()} of ${ft.n_obs} days) is excluded from training. `
                   : `The shaded middle band is excluded from training. `)
               : (ft.boundary != null
                   ? `The cut falls at ${ft.boundary.toFixed(1)}` +
                     `${ft.boundary_percentile != null ? ` — the ${ft.boundary_percentile.toFixed(0)}th percentile` : ""} ` +
                     `(${ft.n_low} low / ${ft.n_high} high of ${ft.n_obs} days). Dotted lines mark the 30th/70th percentiles for reference. `
                   : ""))}
          </MDTypography>
        </Panel>
      );
    });
  }

  if (tdPanels.length === 0 && chPanels.length === 0) return null;

  // Channel selector — visible only when the backend split the chronic stream into per-channel
  // analytics. Default "Pooled" preserves the legacy single-detector view; the other buttons swap
  // the LFP histogram / sliding window / ROC / honest-perf panels to that channel.
  const channelToggle = channelKeys.length >= 1 ? (
    <Grid item xs={12}>
      <MDBox mt={2} mb={0.5} display="flex" flexDirection="row" alignItems="center" gap={2} flexWrap="wrap">
        <MDTypography variant="button" fontWeight="medium" color="dark" sx={{ fontSize: 13 }}>
          {"Sensing contact (bipolar):"}
        </MDTypography>
        <ToggleButtonGroup value={safeChSel} exclusive size="small"
          onChange={(_, v) => { if (v) setChSel(v); }}>
          <ToggleButton value="pooled">All contacts</ToggleButton>
          {channelKeys.map((k) => (
            <ToggleButton key={k} value={k}>{k}</ToggleButton>
          ))}
        </ToggleButtonGroup>
        <MDTypography variant="caption" color="dark" fontStyle="italic" sx={{ fontSize: 11 }}>
          {safeChSel === "pooled"
            ? "All bipolar sensing contacts merged into one threshold (legacy view)."
            : `Showing only contact ${safeChSel} — independent threshold, AUC, and sliding-window curve for that bipolar pair.`}
        </MDTypography>
      </MDBox>
    </Grid>
  ) : null;

  return (
    <>
      <Section title="Time-domain analysis (250 Hz streaming PSD)"
               subtitle="Pearson-R spectrum, permutation null + per-session scatter, and mean PSD by pain state per contact pair."
               panels={tdPanels} />
      <Section title="Power-domain analysis (Chronic 10-min trend + per-session band power)"
               subtitle={"Sliding-window classifier (AUC / R / sensitivity / specificity / threshold), ROC, power distribution, and pain clusters." + chronicHzText}
               panels={chPanels}
               header={channelToggle} />
    </>
  );
}
