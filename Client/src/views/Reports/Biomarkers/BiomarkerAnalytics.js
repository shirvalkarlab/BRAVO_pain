/**
 * BiomarkerAnalytics -- reproduces Yiyuan Han's notebook biomarker figures, split into a
 * Time-domain section and a Chronic section:
 *   Time-domain: PSD correlation spectrum (R vs freq), mean PSD high-vs-low pain, PSD spectrogram.
 *   Chronic: sliding-window AUC+R+sens+spec+threshold, ROC curve, LFP/Otsu histogram, cluster scatter.
 * Channel labels use contact numbers + polarity + brain region (from the backend formatter).
 * Self-contained via plotly.js-dist.
 */

import { useEffect, useRef, useState } from "react";
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

// Vertical (threshold) average of several ROC curves onto a common FPR grid. Each input is a
// {fpr,tpr} object; curves are interpolated at a shared set of FPR points and averaged, the standard
// way to summarize a family of ROCs (Fawcett 2006). Returns {fpr,tpr} on the grid, or null if no
// usable curve. Used to draw the BOLD MEAN ROC over the per-contact curves in the pooled view.
const meanRoc = (curves, nGrid = 101) => {
  const valid = (curves || []).filter((c) => c && c.fpr && c.fpr.length >= 2 && c.tpr && c.tpr.length === c.fpr.length);
  if (!valid.length) return null;
  const grid = Array.from({ length: nGrid }, (_, i) => i / (nGrid - 1));
  // Linear interpolation of one monotone ROC (fpr ascending) at target x.
  const interp = (fpr, tpr, x) => {
    if (x <= fpr[0]) return tpr[0];
    if (x >= fpr[fpr.length - 1]) return tpr[tpr.length - 1];
    let j = 1;
    while (j < fpr.length && fpr[j] < x) j += 1;
    const x0 = fpr[j - 1], x1 = fpr[j], y0 = tpr[j - 1], y1 = tpr[j];
    return x1 === x0 ? y0 : y0 + ((y1 - y0) * (x - x0)) / (x1 - x0);
  };
  const tpr = grid.map((x) => {
    const ys = valid.map((c) => interp(c.fpr, c.tpr, x));
    return ys.reduce((a, b) => a + b, 0) / ys.length;
  });
  return { fpr: grid, tpr };
};

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

export default function BiomarkerAnalytics({ analytics, summary, metricLabel, recordedPowers }) {
  // Hooks MUST be called unconditionally before any early return (React rules-of-hooks).
  const td = analytics ? (analytics.timedomain || {}) : {};
  const pdRoot = analytics ? (analytics.powerdomain || analytics.chronic || {}) : {};
  const perChannel = pdRoot.per_channel || {};
  const channelKeys = Object.keys(perChannel);
  // Hemisphere + kind of each per_channel entry. Prefer the backend tags (summary.hemisphere /
  // summary.kind); fall back to a name parse so this still works against the older backend that
  // doesn't tag yet ("…Hemisphere LFP" = pooled chronic aggregate; leading L/R = bipolar contact).
  const hemiOf = (k) => {
    const s = perChannel[k] && perChannel[k].summary;
    if (s && s.hemisphere) return s.hemisphere;
    if (/hemisphere/i.test(k)) return /^left/i.test(k) ? "Left" : (/^right/i.test(k) ? "Right" : null);
    const f = (k || "").trim()[0];
    return f === "L" ? "Left" : (f === "R" ? "Right" : null);
  };
  const kindOf = (k) => {
    const s = perChannel[k] && perChannel[k].summary;
    if (s && s.kind) return s.kind;
    return /hemisphere/i.test(k) ? "aggregate" : "contact";
  };
  // Bipolar sensing contacts only (exclude the pooled "Hemisphere LFP" aggregates), grouped by
  // hemisphere and ordered LEFT first, then RIGHT — so every plot's legend reads Left group then
  // Right group rather than interleaved (anatomical grouping aids interpretation; do not mix the
  // two stimulation targets — Left GPi vs Right VIM — into one mean).
  const leftContacts = channelKeys.filter((k) => kindOf(k) === "contact" && hemiOf(k) === "Left").sort();
  const rightContacts = channelKeys.filter((k) => kindOf(k) === "contact" && hemiOf(k) === "Right").sort();
  const orderedContacts = [...leftContacts, ...rightContacts];
  const hasLeft = leftContacts.length > 0;
  const hasRight = rightContacts.length > 0;
  // Aggregate (pooled chronic-trend) key for a hemisphere, if the backend emitted one — used to
  // bind the histogram / sliding-window / honest-perf panels when a hemisphere is selected.
  const aggKeyFor = (h) => channelKeys.find((k) => kindOf(k) === "aggregate" && hemiOf(k) === h) || null;

  const [chSel, setChSel] = useState("pooled");
  const isHemiSel = typeof chSel === "string" && chSel.startsWith("hemi:");
  const selHemi = isHemiSel ? chSel.slice(5) : null;
  const isContactSel = !!perChannel[chSel] && kindOf(chSel) === "contact";
  const validSel = chSel === "pooled" || isContactSel ||
    (isHemiSel && ((selHemi === "Left" && hasLeft) || (selHemi === "Right" && hasRight)));
  const safeChSel = validSel ? chSel : "pooled";
  // Which underlying per_channel entry drives the single-summary panels: the contact itself for a
  // contact selection, the hemisphere aggregate for a hemisphere selection, else pooled (null).
  // Plain derivations (cheap, recomputed each render) — kept as plain consts so they sit cleanly
  // before the early return without tripping rules-of-hooks; nothing downstream needs a stable ref.
  const boundKey = safeChSel === "pooled" ? null : (isHemiSel ? aggKeyFor(selHemi) : safeChSel);
  const chronic = boundKey && perChannel[boundKey]
    ? { ...pdRoot, ...perChannel[boundKey] } : pdRoot;

  if (!analytics) return null;

  // Human-readable pain score these correlations / AUCs are computed against (biological best
  // practice: every correlation/AUC panel should say what it is correlated WITH). Falls back gracefully.
  const pain = metricLabel || "pain";
  const tdSum = (summary && summary.timedomain) || {};
  const pdSum = (summary && summary.powerdomain) || {};
  // When a per-channel view is active, overlay its summary on the pooled one so the honest-perf
  // bar reflects the selected channel's AUC. IMPORTANT: per-channel/aggregate summaries carry
  // `auc_in_sample` but NOT the top-level `auc` key that the pooled summary has — so a naive spread
  // leaves `pdSumEff.auc` pinned to the POOLED value and the in-sample-AUC bar never moves with the
  // toggle. Derive `auc` from the bound summary's `auc_in_sample` (falling back to its own `auc`).
  const pdSumEff = (() => {
    if (!boundKey) return pdSum;
    const cs = chronic.summary || {};
    const merged = { ...pdSum, ...cs };
    const csAuc = cs.auc != null ? cs.auc : cs.auc_in_sample;
    if (csAuc != null) merged.auc = csAuc;
    else delete merged.auc;   // bound channel has no AUC (e.g. single-class) -> don't show pooled AUC
    return merged;
  })();
  const chSuffix = safeChSel === "pooled" ? ""
    : (isHemiSel ? ` · ${selHemi} hemisphere` : ` · ${safeChSel}`);
  // View mode (declared HERE, not in the ROC block, because the honest-perf bar plot above the ROC
  // panel also reads these — a later `const` would be in the temporal dead zone there and crash render):
  //   - contact view: a single bipolar contact is selected → one curve, no mean/swarm.
  //   - group view (pooled OR a hemisphere): draw per-hemisphere MEAN ROCs + per-contact curves and
  //     the swarm. Pooled shows both hemispheres (Left group then Right group); a hemisphere shows one.
  const isContactView = isContactSel;
  const groupHemis = isContactView ? []
    : (isHemiSel ? [selHemi] : [...(hasLeft ? ["Left"] : []), ...(hasRight ? ["Right"] : [])]);
  // Hemisphere color families: Left = blues, Right = vermillion/orange (Okabe-Ito-derived, colorblind
  // safe). Shades distinguish contacts within a hemisphere; the bold mean uses the darkest shade.
  const LEFT_SHADES = ["#56B4E9", "#0072B2", "#3A93C9", "#005C8A"];
  const RIGHT_SHADES = ["#E69F00", "#D55E00", "#F0A830", "#A84A00"];
  const LEFT_MEAN = "#003A5C";
  const RIGHT_MEAN = "#7A3300";
  const shadesFor = (h) => (h === "Left" ? LEFT_SHADES : RIGHT_SHADES);
  const meanColorFor = (h) => (h === "Left" ? LEFT_MEAN : RIGHT_MEAN);
  const contactsFor = (h) => (h === "Left" ? leftContacts : rightContacts);

  // Chronic-trend sensing CENTER FREQUENCY per hemisphere (from the device's group-level sensing
  // config). The chronic 10-min trend is band power at a FIXED frequency, so state it. Different
  // from the streaming power-domain center frequencies shown per recorded-power channel.
  const chronicHz = pdRoot.chronic_center_hz || {};
  const chronicHzText = Object.keys(chronicHz).length
    ? " Chronic 10-min trend sensing frequency (distinct from the per-contact recorded bands below): "
        + Object.keys(chronicHz).map((h) => `${h.replace("Hemisphere", "")} ${chronicHz[h]} Hz`).join(", ") + "."
    : "";

  // Short on-plot provenance string: which sensing band (center frequency) and which contact the
  // power-domain signal comes from, so a reader never has to ask "power from WHERE?".
  //
  // CRITICAL: the ROC/distribution/sliding panels are computed from each CONTACT's recorded
  // streaming band power, so the provenance MUST report that contact's OWN recorded center
  // frequency (from `recorded_powers`) — NOT `chronic_center_hz`, which is the chronic 10-min
  // TREND's fixed sensing frequency (a separate series, often a different value, and not what the
  // ROC was computed on). Earlier this fell back to chronic_center_hz and so claimed e.g. "Right
  // hemisphere @ 28.3 Hz" when the plotted Right contacts actually recorded at 23.4 / 26.4 Hz.
  const recHzByContact = {};   // contact label -> recorded center_hz
  (recordedPowers || []).forEach((p) => {
    if (p && p.label != null && p.center_hz != null) recHzByContact[String(p.label).trim()] = p.center_hz;
  });
  const recHzFor = (k) => {
    if (k == null) return null;
    const key = String(k).trim();
    return recHzByContact[key] != null ? recHzByContact[key] : null;
  };
  // Distinct recorded frequencies across a set of contacts, formatted "23.4 / 26.4 Hz" (or a single
  // value). Returns null if none of the contacts carried a recorded frequency.
  const recHzSummary = (keys) => {
    const hzs = (keys || []).map(recHzFor).filter((v) => v != null).map((v) => Number(v));
    const uniq = Array.from(new Set(hzs)).sort((a, b) => a - b).map((v) => v.toFixed(1));
    return uniq.length ? `${uniq.join(" / ")} Hz` : null;
  };
  const hzForHemi = (h) => {
    const k = Object.keys(chronicHz).find((kk) => kk.replace("Hemisphere", "").trim().toLowerCase() === (h || "").toLowerCase());
    return k ? chronicHz[k] : null;
  };
  const powerProvenance = (() => {
    if (isHemiSel) {
      const ks = contactsFor(selHemi);
      const hzText = recHzSummary(ks);
      return `${selHemi} hemisphere (${ks.length} contact${ks.length === 1 ? "" : "s"})${hzText ? ` @ ${hzText}` : ""}`;
    }
    if (safeChSel !== "pooled") {
      const hz = recHzFor(safeChSel);
      return `${safeChSel}${hz != null ? ` @ ${Number(hz).toFixed(1)} Hz` : ""}`;
    }
    // Pooled: report each hemisphere's recorded contact frequencies (fall back to chronic Hz only
    // if no recorded frequencies are present at all).
    const sides = [["Left", leftContacts], ["Right", rightContacts]]
      .filter(([, ks]) => ks.length)
      .map(([h, ks]) => { const t = recHzSummary(ks); return `${h} @ ${t || (hzForHemi(h) != null ? `${Number(hzForHemi(h)).toFixed(1)} Hz` : "?")}`; });
    if (sides.length) return sides.join(" · ");
    const parts = Object.keys(chronicHz).map((h) => `${h.replace("Hemisphere", "")} @ ${Number(chronicHz[h]).toFixed(1)} Hz`);
    return parts.length ? parts.join(" · ") : null;
  })();
  // A short plotly annotation object pinning the provenance text to the top-left of a panel.
  const provenanceAnn = powerProvenance ? [{
    xref: "paper", yref: "paper", x: 0.0, y: 1.06, xanchor: "left", yanchor: "bottom",
    text: `Source: ${powerProvenance}`, showarrow: false,
    font: { size: 11, color: "#344767" },
  }] : [];
  // Panels that POOL every contact's samples (distribution, power-vs-pain scatter) list all recorded
  // contacts — unlike the ROC, which shows per-contact curves and drops single-class contacts. Make
  // that explicit so the two source lines don't read as a contradiction, and so the pooled scatter's
  // r isn't mistaken for a single-contact correlation when it actually mixes targets/frequencies.
  const pooledContactN = leftContacts.length + rightContacts.length;
  const poolSuffix = safeChSel === "pooled" && pooledContactN > 1
    ? ` · pooled across ${pooledContactN} contacts` : "";
  const pooledProvAnn = powerProvenance ? [{
    xref: "paper", yref: "paper", x: 0.0, y: 1.06, xanchor: "left", yanchor: "bottom",
    text: `Source: ${powerProvenance}${poolSuffix}`, showarrow: false,
    font: { size: 11, color: "#344767" },
  }] : [];

  // ---------------- TIME-DOMAIN ----------------
  const tdPanels = [];
  const spectrum = td.corr_spectrum || null;
  if (spectrum && spectrum.channels && spectrum.channels.length) {
    const f = spectrum.freqs;
    const traces = [];
    // Order the spectrum channels by hemisphere — LEFT group first, then RIGHT — and color each
    // by its hemisphere family (blue = Left, orange = Right), so the legend reads anatomically
    // grouped rather than interleaved (same principle as the power-domain ROC panel). Hemisphere
    // from the channel's short label (leading L/R); anything else falls to an "Other" group last.
    const specHemi = (ch) => {
      const s = (ch.short || ch.name || "").trim();
      return s[0] === "L" ? "Left" : (s[0] === "R" ? "Right" : "Other");
    };
    const OTHER_SHADES = ["#009E73", "#CC79A7", "#7E8794"];
    const specShades = (h) => (h === "Left" ? LEFT_SHADES : h === "Right" ? RIGHT_SHADES : OTHER_SHADES);
    const ordered = [];
    ["Left", "Right", "Other"].forEach((h) => {
      spectrum.channels.forEach((ch) => { if (specHemi(ch) === h) ordered.push({ ch, h }); });
    });
    const idxInHemi = {};
    ordered.forEach(({ ch, h }, oi) => {
      idxInHemi[h] = (idxInHemi[h] ?? -1) + 1;
      const shades = specShades(h);
      const color = shades[idxInHemi[h] % shades.length];
      const isFirstInHemi = ordered.findIndex((o) => o.h === h) === oi;
      // Hover (not fixed labels) gives the value on demand. The curve and its peaks share a color +
      // legendgroup, so toggling the curve in the legend also hides its stars. Legend grouped by
      // hemisphere (Left group, then Right) with a per-group title on the first member.
      traces.push({ x: f, y: ch.r, name: ch.name, type: "scatter", mode: "lines",
        line: { width: 2, color }, connectgaps: false, legendgroup: h,
        legendgrouptitle: isFirstInHemi ? { text: `${h} hemisphere` } : undefined,
        hovertemplate: "%{x:.1f} Hz · R=%{y:.2f}<extra>%{fullData.name}</extra>" });
      if (ch.peaks && ch.peaks.length) {
        // Stars MARK the peaks (the strongest |R| local maxima — positive OR negative — so a strong
        // negative correlation is starred too); the value is read by hovering.
        traces.push({ x: ch.peaks.map((p) => p.freq), y: ch.peaks.map((p) => p.r),
          type: "scatter", mode: "markers", legendgroup: h, showlegend: false,
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
          legend: { orientation: "h", y: -0.22, groupclick: "togglegroup" },
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
  // When the sliding window is OFF the backend returns a single all-data window (`all_data:true`) —
  // a "performance over time" line of one point conveys nothing, so suppress the whole panel in that
  // case (per user: no sliding-window-over-time plot when sliding is off). The panel is meaningful
  // only for a genuine sliding run (>=1 real time window). A sliding run that produced no scorable
  // window (sparse one-class test folds) still renders, with the coverage caption explaining why.
  const isAllDataOnly = swWindows.length > 0 && swWindows.every((w) => w && w.all_data);
  const slidingActive = !isAllDataOnly && (swWindows.length > 0 || (swSummary && swSummary.n_total > 1));
  if (slidingActive) {
    const x = swWindows.map((w) => w.test_start);
    // One dot per computed window, connected by a line (connectgaps spans honest one-class skips).
    const mk = (key, name, opts = {}) => ({ x, y: swWindows.map((w) => w[key]), name, type: "scatter",
      mode: "lines+markers", marker: { size: 6 }, connectgaps: true, ...opts });
    const traces = swWindows.length ? [
      mk("auc", "AUC", { line: { width: 3, color: PALETTE[0] } }),
      mk("r", "Pearson R", { line: { width: 3, color: PALETTE[1] } }),
      mk("sens", "Sensitivity", { line: { width: 1.5, color: PALETTE[2], dash: "dot" } }),
      mk("spec", "Specificity", { line: { width: 1.5, color: PALETTE[5], dash: "dot" } }),
      mk("threshold", "Threshold", { yaxis: "y2", mode: "lines",
        line: { width: 1.5, color: "#7E8794", dash: "dash" }, hovertemplate: "thr=%{y:.1f}<extra></extra>" }),
    ] : [];
    const xLo = x.length ? x[0] : 0;
    const xHi = x.length ? x[x.length - 1] : 1;
    chPanels.push(
      <Panel key="sw" title={`Sliding-window performance over time — power vs ${pain}${chSuffix}`} lg={12}>
        {swWindows.length ? (
          <Fig height={360} traces={traces} layout={{
            xaxis: { type: "date", title: "Test window start" },
            yaxis: { title: "AUC / R / Sensitivity / Specificity", range: [-1.05, 1.05],
                     zeroline: true, zerolinewidth: 1 },
            yaxis2: { title: "Power threshold (device units)", overlaying: "y", side: "right",
                      showgrid: false },
            hovermode: "x unified",
            // 0.5 reference for the AUC ceiling-vs-chance read.
            shapes: [{ type: "line", x0: xLo, x1: xHi, y0: 0.5, y1: 0.5, yref: "y",
                       line: { color: "#C8CED5", width: 1, dash: "dot" } }],
            annotations: provenanceAnn,
          }} />
        ) : (
          <MDTypography variant="button" color="dark" display="block" mt={2} mb={2} sx={{ fontSize: 13 }}>
            {"No sliding window produced a scorable test fold for this selection — every candidate " +
             "window had only one pain class in its test period (common with tertile binarization on " +
             "sparse data). Try a longer window, a coarser binarization (median/cutoff), or turn the " +
             "sliding window off to score the detector on all data at once."}
          </MDTypography>
        )}
        {swSummary ? (
          <MDTypography variant="caption" color="dark" display="block" mt={1} fontStyle="italic" sx={{ fontSize: 11 }}>
            {(powerProvenance ? `Power signal from ${powerProvenance}. ` : "") +
             `Reporting ${swSummary.n_with_auc} of ${swSummary.n_total} candidate windows where both pain classes appeared in the test fold (within an expansion cap of ${swSummary.max_test_days} days). ` +
             `Skipped: ${swSummary.n_skipped_test_one_class} for one-class test folds (common with tertile binarization — the excluded middle leaves stretches of all-low or all-high days) and ${swSummary.n_skipped_no_data} for empty/degenerate folds.`}
          </MDTypography>
        ) : null}
      </Panel>
    );
  }

  // Honest performance vs overfit: the threshold-free in-sample AUC looks strong, but the
  // cross-validated balanced accuracy (the generalization estimate) sits near the chance baseline.
  // Plotting them side by side makes the generalization gap explicit. Two added overlays:
  //   - SWARM: in the pooled view with >=2 contacts, each bar carries jittered dots, one per
  //     bipolar contact, so the bar is visibly a mean over the contacts (matches the mean ROC).
  //   - PERMUTATION NULL: a red dashed ceiling at the 95th-percentile AUC under block-permuted
  //     daily pain labels, with the empirical p — so "above 0.5" is backed by an empirical test
  //     that preserves pain autocorrelation, not just the analytic 0.5 line.
  if (pdSumEff.auc != null || pdSumEff.balanced_accuracy != null) {
    const chanceLvl = pdSumEff.chance_accuracy != null ? pdSumEff.chance_accuracy : 0.5;
    // Numeric x (0,1,2) so the swarm dots can be jittered around each bar center.
    const ticktext = ["In-sample AUC", "CV balanced accuracy", "Chance"];
    const xpos = [0, 1, 2];
    const vals = [pdSumEff.auc, pdSumEff.balanced_accuracy, chanceLvl];
    const colors = [PALETTE[0], PALETTE[2], "#7E8794"];
    const barTraces = [{ x: xpos, y: vals.map((v) => (v == null ? null : v)),
      type: "bar", width: 0.55, marker: { color: colors, line: { color: "#344767", width: 0.5 } },
      text: vals.map((v) => (v == null ? "" : v.toFixed(2))), textposition: "outside",
      textfont: { size: 12, color: "#344767" }, showlegend: false,
      hovertemplate: "%{text}<extra></extra>", customdata: ticktext }];
    // Swarm: per-contact AUC + balanced-accuracy dots, in group view (pooled or hemisphere). Only
    // bipolar CONTACTS (never the chronic aggregates), ordered Left-then-Right and colored by
    // hemisphere (blue = Left, orange = Right) so each dot is attributable to a side. One legend
    // entry per hemisphere, Left first.
    const swarmKeys = isContactView ? []
      : orderedContacts.filter((k) => (isHemiSel ? hemiOf(k) === selHemi : true) && perChannel[k] && perChannel[k].summary);
    // A dot is plotted per bar ONLY where that contact has a finite value for that metric — a
    // single-class contact (auc_in_sample/balanced_accuracy = null) must not be silently dropped by
    // Plotly while still being counted in the caption. Track the distinct contacts that contribute
    // AT LEAST ONE dot, so the caption count matches what's actually shown.
    const finiteFor = (k, field) => { const v = perChannel[k].summary[field]; return typeof v === "number" && isFinite(v); };
    const aucDotKeys = swarmKeys.filter((k) => finiteFor(k, "auc_in_sample"));
    const baDotKeys = swarmKeys.filter((k) => finiteFor(k, "balanced_accuracy"));
    const shownContacts = Array.from(new Set([...aucDotKeys, ...baDotKeys]));
    if (swarmKeys.length >= 2) {
      const jitter = (i, n) => (n === 1 ? 0 : -0.16 + (0.32 * i) / (n - 1));
      const drawSide = (h) => {
        const mean = meanColorFor(h);
        const sumOf = (k) => perChannel[k].summary;
        const mk = (xc, field, keysAll, showLegend) => {
          const keys = keysAll.filter((k) => hemiOf(k) === h);
          if (!keys.length) return;
          barTraces.push({
            x: keys.map((k, i) => xc + jitter(i, keys.length)),
            y: keys.map((k) => sumOf(k)[field]), type: "scatter", mode: "markers",
            name: `${h} contacts`, legendgroup: `swarm-${h}`, showlegend: showLegend,
            marker: { size: 9, color: "#FFFFFF", line: { color: mean, width: 1.8 }, symbol: "circle" },
            text: keys, hovertemplate: `%{text}<br>${field === "auc_in_sample" ? "in-sample AUC" : "CV balanced acc"}=%{y:.3f}<extra></extra>` });
        };
        // Legend entry shows once per side, on the first (AUC) trace that has any dot for that side.
        const sideHasAuc = aucDotKeys.some((k) => hemiOf(k) === h);
        mk(0, "auc_in_sample", aucDotKeys, sideHasAuc);
        mk(1, "balanced_accuracy", baDotKeys, !sideHasAuc && baDotKeys.some((k) => hemiOf(k) === h));
      };
      // Left first, then Right — keeps the legend anatomically grouped.
      ["Left", "Right"].forEach(drawSide);
    }
    const swarmContacts = shownContacts; // contacts that actually contribute >=1 dot (caption/legend)
    // Permutation-null ceiling over the AUC bar (block-permuted daily labels).
    const ap = pdSumEff.auc_perm || null;
    // Permuted-null swarm over the CHANCE bar (x=2): each dot is one block-permuted-label AUC, so the
    // reader sees the actual null DISTRIBUTION the chance level summarizes, not just the 0.5 line.
    // The bar height is the analytic chance (0.50 for balanced AUC); the dots scatter around it.
    if (ap && Array.isArray(ap.null_sample) && ap.null_sample.length) {
      const ns = ap.null_sample;
      // Deterministic spread so dots don't redraw differently each render.
      const jit = (i) => -0.22 + (0.44 * ((i * 2654435761) % ns.length)) / Math.max(ns.length - 1, 1);
      barTraces.push({
        x: ns.map((_, i) => 2 + jit(i)), y: ns, type: "scatter", mode: "markers",
        name: `null AUC (${ns.length} of ${ap.n_perm} perms)`, legendgroup: "permnull", showlegend: true,
        marker: { size: 5, color: "rgba(126,135,148,0.45)", line: { width: 0 }, symbol: "circle" },
        hovertemplate: "permuted-null AUC=%{y:.3f}<extra></extra>" });
    }
    const shapes = [{ type: "line", x0: -0.5, x1: 2.5, y0: chanceLvl, y1: chanceLvl,
      line: { color: "#7E8794", width: 1, dash: "dot" } }];
    const annotations = [];
    if (ap && ap.null_q && ap.null_q.p95 != null) {
      shapes.push({ type: "line", x0: -0.32, x1: 0.32, y0: ap.null_q.p95, y1: ap.null_q.p95,
        line: { color: "#D55E00", width: 2, dash: "dash" } });
      annotations.push({ x: 0, y: ap.null_q.p95, yanchor: "bottom", xanchor: "center",
        text: `null 95th pct = ${ap.null_q.p95.toFixed(2)} · p=${fmtP(ap.p_value)}`,
        showarrow: false, font: { size: 10, color: "#D55E00" } });
    }
    chPanels.push(
      <Panel key="honest" title={`Honest performance: in-sample vs cross-validated — power vs ${pain}${chSuffix}`}>
        <Fig height={320} traces={barTraces}
          layout={{ yaxis: { title: "Score", range: [0, 1.08] },
            xaxis: { title: "", tickmode: "array", tickvals: xpos, ticktext, range: [-0.5, 2.5] },
            legend: { orientation: "h", y: -0.18 },
            showlegend: swarmContacts.length >= 2 || !!(ap && ap.null_sample && ap.null_sample.length),
            shapes, annotations }} />
        <MDTypography variant="caption" color="dark" display="block" mt={1} sx={{ fontSize: 11 }}>
          {`Chance for BALANCED accuracy is 0.50 regardless of class imbalance (sens & spec each ` +
           `0.5 at chance). ` +
           (pdSumEff.majority_accuracy != null
             ? `The majority-class baseline (${pdSumEff.majority_accuracy.toFixed(2)}) is the chance level for RAW accuracy only and is NOT the comparator here. `
             : "") +
           (ap && ap.p_value != null
             ? `Dashed orange line = 95th-percentile AUC under ${ap.n_perm} circular-block label permutations (block=${ap.block} days, preserving pain autocorrelation); empirical p=${fmtP(ap.p_value)} for the observed AUC=${(ap.observed ?? 0).toFixed(2)}. `
             : "") +
           (ap && ap.null_sample && ap.null_sample.length
             ? `Gray dots over the Chance bar are individual permuted-null AUCs (the null DISTRIBUTION the chance line summarizes). `
             : "") +
           (swarmContacts.length >= 2
             ? `Open dots show the per-contact value for each of the ${swarmContacts.length} bipolar contacts (one dot per contact that has that metric; single-class contacts have no value and are omitted). The bar is the POOLED detector, not the mean of the dots. `
             : "") +
           `In-sample AUC has no train/test split (optimistic); CV balanced accuracy is the held-out ` +
           `generalization estimate — near 0.5 means the in-sample AUC is not reproduced out-of-fold.` +
           `${pdSumEff.overfit_warning ? "  ⚠ " + pdSumEff.overfit_warning : ""}`}
        </MDTypography>
      </Panel>
    );
  }
  // ROC panel. Layout depends on the toggle:
  //   GROUP view (All contacts, or a single hemisphere): for EACH hemisphere in view (Left first,
  //     then Right), draw a BOLD MEAN ROC (vertical average over that hemisphere's bipolar contacts)
  //     with the individual contact curves as thin lines behind it. Left contacts use the blue
  //     family, Right the orange family, and the legend is emitted Left-group-then-Right-group so it
  //     reads anatomically. The two hemispheres are NEVER averaged together (different targets:
  //     Left GPi vs Right VIM).
  //   CONTACT view: just the selected contact's ROC (filled).
  //   In BOTH, when a sliding window is active, overlay each window's ROC as a faint orange line.
  const roc = chronic.roc || null;
  const rocTraces = [];
  const rocFor = (k) => (perChannel[k] && perChannel[k].roc) || null;
  const meanAucLabels = []; // for the caption: per-hemisphere mean AUCs
  const drawnByHemi = {};   // hemisphere -> [contact keys actually plotted] (for honest provenance)
  if (!isContactView && groupHemis.length) {
    groupHemis.forEach((h) => {
      const shades = shadesFor(h);
      const curves = contactsFor(h)
        .map((k) => ({ k, r: rocFor(k) }))
        .filter((c) => c.r && c.r.fpr && c.r.fpr.length >= 2);
      if (!curves.length) return;
      drawnByHemi[h] = curves.map((c) => c.k);
      // (a) Individual contacts, thin, drawn FIRST so the mean sits on top. Grouped per hemisphere.
      curves.forEach((c, i) => {
        rocTraces.push({ x: c.r.fpr, y: c.r.tpr, name: `${c.k} (AUC=${(c.r.auc ?? 0).toFixed(3)})`,
          type: "scatter", mode: "lines",
          line: { width: 1.5, color: shades[i % shades.length], dash: "solid" }, opacity: 0.6,
          legendgroup: h, legendgrouptitle: i === 0 ? { text: `${h} hemisphere` } : undefined,
          hovertemplate: `${c.k}<br>FPR=%{x:.2f} · TPR=%{y:.2f}<extra></extra>` });
      });
      // (b) Bold MEAN ROC over this hemisphere's contacts (vertical average; AUC = mean of contact AUCs).
      if (curves.length >= 2) {
        const mean = meanRoc(curves.map((c) => c.r));
        const meanAuc = curves.reduce((a, c) => a + (c.r.auc ?? 0), 0) / curves.length;
        if (mean) {
          rocTraces.push({ x: mean.fpr, y: mean.tpr,
            name: `${h} mean of ${curves.length} contacts (AUC=${meanAuc.toFixed(3)})`,
            type: "scatter", mode: "lines", line: { width: 4, color: meanColorFor(h) },
            legendgroup: h,
            hovertemplate: `${h} mean ROC<br>FPR=%{x:.2f} · TPR=%{y:.2f}<extra></extra>` });
          meanAucLabels.push(`${h} ${meanAuc.toFixed(3)}`);
        }
      }
    });
  } else if (roc && roc.fpr && roc.fpr.length) {
    // Single contact selected (or backend never split) — one curve.
    rocTraces.push({ x: roc.fpr, y: roc.tpr,
      name: `${isContactView ? safeChSel : "All contacts"} (AUC=${(roc.auc ?? 0).toFixed(3)})`,
      type: "scatter", mode: "lines",
      line: { width: 3, color: meanColorFor(hemiOf(safeChSel) || "Left") },
      fill: "tozeroy", fillcolor: "rgba(0,114,178,0.12)",
      hovertemplate: "FPR=%{x:.2f}<br>TPR=%{y:.2f}<extra></extra>" });
  }
  // Per-window curves (only for a genuine sliding run). Drawn faint; first one labeled, rest grouped.
  // Exclude the all-data window (sliding OFF) — its single ROC is already the main curve, and
  // overlaying it as a date-labeled "window" curve is what produced the confusing "Window <date>"
  // legend entry.
  const swForRoc = Array.isArray(chronic.sliding_window)
    ? chronic.sliding_window : (chronic.sliding_window && chronic.sliding_window.windows) || [];
  const windowRocs = swForRoc.filter((w) => w.roc && w.roc.fpr && w.roc.fpr.length && !w.all_data);
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
    const isMeanView = meanAucLabels.length > 0;
    const titleNote = isMeanView ? ` · mean ${meanAucLabels.join(", ")}` : "";
    const perWinNote = windowRocs.length ? ` · ${windowRocs.length} per-window curves` : "";
    // Provenance for THIS panel must describe only the contacts actually DRAWN — a hemisphere
    // contact that is single-class (no ROC) is dropped from the curves and the mean, so it must not
    // appear in the frequency list either (else "@ 3 Hz values" disagrees with "mean of 2 contacts").
    // Built from drawnByHemi (group view) or the single selected contact.
    const rocProvenance = (() => {
      const hemis = Object.keys(drawnByHemi);
      if (hemis.length) {
        return ["Left", "Right"].filter((h) => drawnByHemi[h] && drawnByHemi[h].length)
          .map((h) => { const t = recHzSummary(drawnByHemi[h]); const n = drawnByHemi[h].length;
            return `${h} (${n} contact${n === 1 ? "" : "s"})${t ? ` @ ${t}` : ""}`; })
          .join(" · ");
      }
      if (isContactView) { const hz = recHzFor(safeChSel); return `${safeChSel}${hz != null ? ` @ ${Number(hz).toFixed(1)} Hz` : ""}`; }
      return powerProvenance;
    })();
    const rocProvAnn = rocProvenance ? [{ xref: "paper", yref: "paper", x: 0.0, y: 1.06,
      xanchor: "left", yanchor: "bottom", text: `Source: ${rocProvenance}`, showarrow: false,
      font: { size: 11, color: "#344767" } }] : [];
    chPanels.push(
      <Panel key="roc" title={`ROC curve — power vs ${pain}${chSuffix} (in-sample)${titleNote}${perWinNote}`}>
        <Fig height={380} traces={rocTraces} layout={{
          xaxis: { title: "False positive rate", range: [-0.02, 1.02], scaleanchor: "y", scaleratio: 1 },
          yaxis: { title: "True positive rate", range: [-0.02, 1.02] },
          legend: { orientation: "h", y: -0.22, groupclick: "toggleitem" },
          annotations: rocProvAnn }} />
        {rocProvenance ? (
          <MDTypography variant="caption" color="dark" display="block" mt={1} sx={{ fontSize: 11 }}>
            {`Power signal from ${rocProvenance}.` +
             (isMeanView
               ? " Bold line = per-hemisphere mean ROC (vertical average of that hemisphere's plotted bipolar contacts); thin lines behind it are the individual contacts (blue = Left, orange = Right). Contacts with only one pain class (no ROC) are omitted. The two hemispheres are never averaged together (separate stimulation targets)."
               : "") +
             (windowRocs.length ? " Faint orange curves are individual sliding-window ROCs." : "")}
          </MDTypography>
        ) : null}
      </Panel>
    );
  }
  // Dynamic power-vs-pain correlation scatter — the selected power biomarker against ONLY the
  // selected pain score, with Pearson r and p, in its own panel. Binds to `chronic.power_pain_scatter`
  // so it follows the contact/hemisphere toggle (pooled / hemisphere aggregate / single contact).
  const pps = chronic.power_pain_scatter || null;
  if (pps && Array.isArray(pps.x) && pps.x.length >= 3) {
    const sx = pps.x, sy = pps.y;
    // Least-squares fit for an overlaid trend line (purely visual; r/p come from the backend).
    const n = sx.length;
    const mx = sx.reduce((a, b) => a + b, 0) / n;
    const my = sy.reduce((a, b) => a + b, 0) / n;
    let sxy = 0, sxx = 0;
    for (let i = 0; i < n; i += 1) { sxy += (sx[i] - mx) * (sy[i] - my); sxx += (sx[i] - mx) ** 2; }
    const slope = sxx > 0 ? sxy / sxx : 0;
    const intercept = my - slope * mx;
    const xMin = Math.min(...sx), xMax = Math.max(...sx);
    const hemiColor = isContactView || isHemiSel ? meanColorFor(hemiOf(safeChSel) || selHemi || "Left") : PALETTE[0];
    const rTxt = pps.r != null ? pps.r.toFixed(3) : "—";
    const pTxt = pps.p != null ? fmtP(pps.p) : "—";
    chPanels.push(
      <Panel key="ppscatter" title={`Power vs ${pain} correlation${chSuffix} — r=${rTxt}, p=${pTxt}`}>
        <Fig height={340} traces={[
          { x: sx, y: sy, type: "scatter", mode: "markers", name: "sessions",
            marker: { size: 5, color: hemiColor, opacity: 0.45, line: { width: 0 } },
            hovertemplate: `band power=%{x:.1f}<br>${pain}=%{y:.2f}<extra></extra>` },
          ...(sxx > 0 ? [{ x: [xMin, xMax], y: [intercept + slope * xMin, intercept + slope * xMax],
            type: "scatter", mode: "lines", name: "linear fit",
            line: { color: "#111111", width: 2, dash: "solid" }, hoverinfo: "skip" }] : []),
        ]} layout={{
          xaxis: { title: "Band power (device units, a.u.)" },
          yaxis: { title: `${pain}` },
          showlegend: false,
          annotations: [...pooledProvAnn, {
            xref: "paper", yref: "paper", x: 0.98, y: 0.04, xanchor: "right", yanchor: "bottom",
            text: `Pearson r = ${rTxt} · p = ${pTxt} · n = ${pps.n}`,
            showarrow: false, font: { size: 12, color: "#344767" },
            bgcolor: "rgba(255,255,255,0.7)" }] }} />
        <MDTypography variant="caption" color="dark" display="block" mt={1} sx={{ fontSize: 11 }}>
          {(powerProvenance ? `Power signal from ${powerProvenance}. ` : "") +
           `Each dot is one chronic sample: smoothed band power vs the selected pain score (${pain}). ` +
           `Pearson r = ${rTxt} (p = ${pTxt}, n = ${pps.n}` +
           (pps.n_clipped ? `; ${pps.n_clipped} power outlier(s) excluded` : "") +
           `). Pain is kept CONTINUOUS here (the ROC/Otsu panels binarize it); p is the ordinary ` +
           `Pearson p, not corrected for the band search — the headline inference is the ` +
           `permutation test on the AUC. ` +
           (poolSuffix
             ? `This pooled view mixes all ${pooledContactN} contacts (two stimulation targets at ` +
               `different sensing frequencies), so the pooled r is a blend, not one electrode's ` +
               `correlation; the large n makes even a near-zero r look "significant" (r is the effect ` +
               `size — select a single contact to read a meaningful association). `
             : "")}
        </MDTypography>
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
            xaxis: { title: "Power band power (device units, outlier-free 1st–99th pct range)" },
            yaxis: { title: "Sample count" }, bargap: 0.04,
            shapes: dist.otsu != null ? [{ type: "line", x0: dist.otsu, x1: dist.otsu, yref: "paper",
              y0: 0, y1: 1, line: { color: PALETTE[1], width: 2.5, dash: "dash" } }] : [],
            annotations: [
              ...(dist.otsu != null ? [{ x: dist.otsu, yref: "paper", y: 1.02,
                text: `Otsu = ${dist.otsu.toFixed(1)}`, showarrow: false,
                font: { color: PALETTE[1], size: 11 }, xanchor: "left", yanchor: "bottom" }] : []),
              ...pooledProvAnn,
            ] }} />
        <MDTypography variant="caption" color="dark" display="block" mt={1} sx={{ fontSize: 11 }}>
          {(powerProvenance ? `Power signal from ${powerProvenance}. ` : "") +
           `${(dist.n_total || 0).toLocaleString()} samples total. ` +
           (dist.n_clipped
             ? `${dist.n_clipped.toLocaleString()} extreme outlier sample(s) (\u22653 MADs from the median) ` +
               `are excluded from BOTH the histogram and the Otsu threshold, so the bars and the split ` +
               `describe the same outlier-free distribution. `
             : `No outliers were excluded (all samples within 3 MADs of the median). `) +
           `Bars are trimmed to the inlier 1st\u201399th percentile for display.`}
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
          {hasLeft ? <ToggleButton value="hemi:Left">Left hemisphere</ToggleButton> : null}
          {leftContacts.map((k) => (
            <ToggleButton key={k} value={k}>{k}</ToggleButton>
          ))}
          {hasRight ? <ToggleButton value="hemi:Right">Right hemisphere</ToggleButton> : null}
          {rightContacts.map((k) => (
            <ToggleButton key={k} value={k}>{k}</ToggleButton>
          ))}
        </ToggleButtonGroup>
        <MDTypography variant="caption" color="dark" fontStyle="italic" sx={{ fontSize: 11 }}>
          {safeChSel === "pooled"
            ? "All bipolar contacts, grouped by hemisphere — per-hemisphere mean ROC over each side's contacts (Left and Right shown separately, never averaged together)."
            : isHemiSel
              ? `${selHemi} hemisphere — mean over its bipolar contacts, with the individual contacts behind it.`
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
               subtitle={(slidingActive
                 ? "Sliding-window classifier (AUC / R / sensitivity / specificity / threshold), ROC, power distribution, and pain clusters."
                 : "ROC, power distribution, and pain clusters (turn on the sliding window for performance-over-time).") + chronicHzText}
               panels={chPanels}
               header={channelToggle} />
    </>
  );
}
