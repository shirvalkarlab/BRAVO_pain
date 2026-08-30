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

import { Card, Grid, Slider, ToggleButton, ToggleButtonGroup } from "@mui/material";
import MDBox from "components/MDBox";
import MDTypography from "components/MDTypography";
import MDButton from "components/MDButton";
import BinarizationPreview from "./BinarizationPreview";
import { SessionController } from "database/session-control";
import { commitBandCandidate, downloadBandCandidate } from "../ClosedLoopSim/bandCandidateStore";

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

// DESIGN §8b — the exploratory spectral feature-importance scan, the centerpiece TD panel.
// One dual-axis curve per main bipolar channel: Pearson r vs the CONTINUOUS PRO (left axis) and
// cross-validated logistic AUC vs the BINARIZED PRO (right axis), both over the same 5 Hz sliding
// band-center x-axis, so the two complementary views of "which band tracks pain" overlay. The
// 8–30 Hz Percept-RC adaptive-valid range is shaded (that's the band the device can actually act
// on). CLICK any band on a curve to drop a scatter of that band's power vs the PRO below it.
// Click-validate readout — renders the mixed-effects OR + 95% CI, the stim-stability badge, and
// the per-era ORs from /queryBandValidation. Stays compact (three lines + one badge) so it tucks
// under the violin without pushing the layout. Empty-state and in-flight handled.
function ValidationReadout({ validation, validating, emitContext }) {
  // Commit-to-band: when the clicked band is VALIDATED, the user can export it as a §6
  // BandCandidate into the threshold-deployment (Closed-Loop Sim) view. We POST the IDENTICAL
  // band-feature envelope the validation used (emitContext), so the committed candidate is
  // byte-identical to what the readout shows.
  const [committing, setCommitting] = useState(false);
  const [committed, setCommitted] = useState(null);   // {ok, msg} after a commit attempt
  if (validating) {
    return (
      <MDTypography variant="caption" color="text" display="block" mt={0.5}
        sx={{ fontStyle: "italic", fontSize: 11 }}>
        Running mixed-effects validation (mixed-effects logistic fit + stim-era likelihood-ratio test)…
      </MDTypography>
    );
  }
  if (!validation || !validation.available) {
    if (validation && validation.reason) {
      return (
        <MDTypography variant="caption" color="text" display="block" mt={0.5}
          sx={{ fontStyle: "italic", fontSize: 11 }}>
          {`Click-validate: ${validation.reason}.`}
        </MDTypography>
      );
    }
    return null;
  }
  const g = validation.glmer || {};
  const s = validation.stim || {};
  const verdict = validation.verdict || "—";
  // Badge color: green for validated, amber for stim-dependent, grey for n.s./degenerate.
  const badgeColor =
    /VALIDATED \(stim-stable\)/.test(verdict) ? "#0a7f3f"
    : /VALIDATED \(stim-dependent\)/.test(verdict) ? "#B17500"
    : /failed/.test(verdict) ? "#9A3324"
    : "#6c757d";
  const fmt = (v, d = 2) => (v == null || !Number.isFinite(v) ? "—" : v.toFixed(d));
  const fmtP = (p) => (p == null || !Number.isFinite(p) ? "—"
    : p < 0.001 ? p.toExponential(1) : p.toFixed(3));
  // Effect direction in plain language for the headline.
  const direction = g.odds_ratio != null && Number.isFinite(g.odds_ratio)
    ? (g.odds_ratio < 1 ? "lower" : "higher") : null;
  const dirLine = direction
    ? `Higher band power → ${direction} odds of high pain.`
    : null;
  const erasArr = s.or_by_era ? ["OFF", "LOW", "HIGH"]
    .map((tag) => `${tag} (${(s.era_counts && s.era_counts[tag]) || 0}): ${fmt(s.or_by_era[tag])}`)
    .join("  ·  ") : null;
  return (
    <MDBox mt={1}>
      <MDBox display="flex" alignItems="center" gap={1.2} mb={0.5} flexWrap="wrap">
        <MDBox px={1.6} py={0.5} sx={{ backgroundColor: badgeColor, color: "white",
          borderRadius: "12px", fontSize: 14, fontWeight: "bold", letterSpacing: 0.3 }}>
          {verdict}
        </MDBox>
        {dirLine ? (
          <MDTypography color="dark" sx={{ fontSize: 15, fontWeight: "bold" }}>{dirLine}</MDTypography>
        ) : null}
      </MDBox>
      {/* Enlarged + bold headline of the mixed-effects result — the takeaway the PI wants to read at
          a glance (OR per 1 SD, 95% CI, p, cluster n). The full method prose stays below in small text. */}
      {g.available !== false && g.odds_ratio != null && (
        <MDTypography color="dark" display="block" mb={0.5}
          sx={{ fontSize: 16, fontWeight: "bold", lineHeight: 1.4 }}>
          {`OR = ${fmt(g.odds_ratio)} per 1 SD`
           + (g.or_lo != null && g.or_hi != null ? `  (95% CI ${fmt(g.or_lo)}–${fmt(g.or_hi)})` : "")
           + `  ·  p = ${fmtP(g.p)}`}
          <span style={{ fontSize: 12.5, fontWeight: 400, color: "#6c757d" }}>
            {`   across ${g.n_clusters} weekly eras (n = ${g.n})`}
          </span>
        </MDTypography>
      )}
      {g.available !== false ? (
        <MDTypography variant="caption" color="text" display="block" sx={{ fontSize: 11.5, lineHeight: 1.45 }}>
          {`Mixed-effects logistic regression (lme4::glmer, random intercept per weekly era). `
           + `Full fit: OR = ${fmt(g.odds_ratio)}`
           + (g.or_lo != null && g.or_hi != null
              ? ` (95% CI ${fmt(g.or_lo)}–${fmt(g.or_hi)}), ` : ", ")
           + `p = ${fmtP(g.p)}, n = ${g.n} across ${g.n_clusters} weekly eras.`}
        </MDTypography>
      ) : (
        <MDTypography variant="caption" color="text" display="block" sx={{ fontSize: 11.5 }}>
          {`Mixed-effects fit unavailable: ${g.reason || "no result"}.`}
        </MDTypography>
      )}
      {s.available !== false ? (
        <MDTypography variant="caption" color="text" display="block" sx={{ fontSize: 11.5, lineHeight: 1.45 }}>
          <strong style={{ fontSize: 13, color: s.stim_stable ? "#0a7f3f" : "#B17500" }}>
            {`Stim ${s.stim_stable ? "stable" : "dependent"}`}
          </strong>
          {` — band × stim-era interaction LRT: χ² = ${fmt(s.chisq)}, `}
          <strong>{`p = ${fmtP(s.lrt_p)}`}</strong>
          {`. Per-era OR (n): ${erasArr}. `
           + `Eras: OFF (<${fmt(s.thresholds_mA && s.thresholds_mA.off_max, 2)} mA), `
           + `LOW (≤${fmt(s.thresholds_mA && s.thresholds_mA.low_max, 2)} mA), HIGH (>${fmt(s.thresholds_mA && s.thresholds_mA.low_max, 2)} mA).`}
        </MDTypography>
      ) : (
        <MDTypography variant="caption" color="text" display="block" sx={{ fontSize: 11.5 }}>
          {`Stim-stability test unavailable: ${s.reason || "no result"}.`}
        </MDTypography>
      )}
      {/* Commit-to-band: only offered for a VALIDATED verdict and when the parent supplied the
          emit envelope. POSTs /api/emitBandCandidate with the SAME band feature the readout used,
          stashes the returned §6 BandCandidate for the threshold-deployment view, and offers a
          JSON download as the persistence escape hatch. */}
      {emitContext && /VALIDATED/.test(verdict) ? (
        <MDBox mt={1.2} display="flex" alignItems="center" gap={1} flexWrap="wrap">
          <MDButton
            size="small" color="info" variant="gradient"
            disabled={committing}
            onClick={() => {
              setCommitting(true); setCommitted(null);
              SessionController.query("/api/emitBandCandidate", {
                ParticipantId: emitContext.participantUid,
                Channel: emitContext.channelRaw,
                CenterHz: Number(emitContext.centerHz),
                BandWidthHz: emitContext.bandWidthHz,
                ...emitContext.requestParams,
              }).then((response) => {
                const data = response && response.data;
                if (data && data.available && data.band_candidate) {
                  commitBandCandidate(emitContext.participantUid, data.band_candidate);
                  downloadBandCandidate(emitContext.participantUid, data.band_candidate);
                  setCommitted({ ok: true, msg: "Committed → Closed-Loop Sim (JSON downloaded)." });
                } else {
                  setCommitted({ ok: false, msg: (data && data.reason) || "emit failed" });
                }
                setCommitting(false);
              }).catch(() => {
                setCommitted({ ok: false, msg: "emit request failed" });
                setCommitting(false);
              });
            }}
          >
            {committing ? "Committing…" : "Commit this band →"}
          </MDButton>
          {committed ? (
            <MDTypography variant="caption" sx={{ fontSize: 11,
              color: committed.ok ? "#0a7f3f" : "#9A3324" }}>
              {committed.msg}
            </MDTypography>
          ) : (
            <MDTypography variant="caption" color="text" sx={{ fontSize: 10.5, fontStyle: "italic" }}>
              Export this validated band as a deployment BandCandidate.
            </MDTypography>
          )}
        </MDBox>
      ) : null}
    </MDBox>
  );
}


function SpectralFeatureImportance({ scan, pain, HI, LO, participantUid, requestParams, matchDirty }) {
  const ref = useRef(null);
  const [sel, setSel] = useState(null);   // {ci, bi} selected (channel, band-center) for the scatter
  // Click-triggered VALIDATION bundle: { available, glmer:{...}, stim:{...}, verdict } from the
  // /queryBandValidation endpoint. Re-fetched whenever the user clicks a new band so the readout
  // matches the band the violin is showing. `validating` flags the in-flight state for the spinner.
  const [validation, setValidation] = useState(null);
  const [validating, setValidating] = useState(false);
  const channels = (scan && scan.channels) || [];
  const centers = (scan && scan.centers) || [];
  const adaptive = scan && scan.adaptive_band;            // [lo, hi] | null
  const fmax = (scan && scan.fmax) || 100;
  // Feature the scan ran on: "lsb_cs14" (CS-1…CS-4 transform/bridge, k=352.62/73.63, new as of
  // 2026-06-27) or legacy "lsb_calibrated" (269 × TD Welch band integral, kept for back-compat) vs
  // "logpsd_db". Drives every axis/hover label so the panel states the unit the numbers carry.
  const isLsb = scan && (scan.feature === "lsb_cs14" || scan.feature === "lsb_calibrated");
  // LSB is shown on the RAW (linear) scale — the Percept device applies no onboard log10, so the
  // axis matches the scale the closed-loop threshold operates on (2026-06-28). Power features stay on
  // the log/dB scale they are computed on.
  const featAxis = isLsb ? "Calibrated LSB" : "Std. log band power";
  const featHover = isLsb ? "LSB" : "log power";
  // Correlation statistic shown for this feature: Spearman ρ for LSB (rank-based, robust to the
  // heavy-tailed LSB distribution), Pearson r for the log-power feature. Backend stamps corr_method
  // per channel; fall back to the feature type when absent.
  const corrName = isLsb ? "Spearman ρ" : "Pearson r";

  // Hemisphere coloring: Left = blue family, Right = vermillion family (matches the rest of the card).
  const hemiOf = (ch) => { const s = (ch.short || ch.name || "").trim(); return s[0] === "R" ? "Right" : "Left"; };

  // Click-triggered VALIDATION fetch (mixed-effects logistic + band x stim-era LRT). Fires only
  // when the user has clicked a band AND we have the request envelope from the parent (carries
  // LabelMetric / binarization / match knobs so the band feature is defined identically to the
  // clicked scan dot). selChannelRaw/selCenterHz are the two coordinates the endpoint keys on.
  const selChannel = sel && channels[sel.ci];
  const selChannelRaw = selChannel ? (selChannel.raw || selChannel.short) : null;
  const selCenterHz = sel != null ? centers[sel.bi] : null;
  useEffect(() => {
    if (!participantUid || !requestParams || sel == null || selChannelRaw == null
        || selCenterHz == null) {
      setValidation(null); return undefined;
    }
    let cancelled = false;
    setValidating(true);
    setValidation(null);
    SessionController.query("/api/queryBandValidation", {
      ParticipantId: participantUid,
      Channel: selChannelRaw,
      CenterHz: Number(selCenterHz),
      BandWidthHz: scan && scan.band_width_hz ? Number(scan.band_width_hz) : 5.0,
      ...requestParams,
    }).then((response) => {
      if (cancelled) return;
      setValidation(response && response.data ? response.data : null);
      setValidating(false);
    }).catch(() => {
      if (cancelled) return;
      // Network/API failure -> empty-state caption; never block the rest of the panel.
      setValidation({ available: false, reason: "validation request failed" });
      setValidating(false);
    });
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [participantUid, requestParams, selChannelRaw, selCenterHz]);

  useEffect(() => {
    if (!ref.current || !channels.length || !centers.length) return;
    const traces = [];
    // Legend order: all LEFT-hemisphere contacts first, then all RIGHT, each block alphabetized,
    // so the key reads as two tidy hemisphere groups. Keep the ORIGINAL channel index (ci) for the
    // band-click customdata so selection still maps to the right channel after reordering.
    const orderedChannels = channels
      .map((ch, ci) => ({ ch, ci }))
      .sort((a, b) => {
        const ha = hemiOf(a.ch), hb = hemiOf(b.ch);
        if (ha !== hb) return ha === "Left" ? -1 : 1;
        return String(a.ch.short || "").localeCompare(String(b.ch.short || ""));
      });
    orderedChannels.forEach(({ ch, ci }) => {
      const color = hemiOf(ch) === "Right" ? HI : LO;
      // Per-channel count shown in the legend AND echoed into the curve hover (the hovertemplate's
      // <extra> renders fullData.name). The honest count is the number of INDEPENDENT LSB vectors
      // feeding this channel's analysis, split into the only two sources the PI wants surfaced:
      // time-domain-derived (n_td) vs PSD-derived (n_psd_bridge). This is NOT ch.n_channel — that
      // counts matched PSD ROWS (e.g. 278) and massively overstates the independent vectors (e.g.
      // 17 TD + 3 PSD = 20), which is exactly why the old hover N never matched rendered points.
      const nch = (ch.n_td != null || ch.n_psd_bridge != null)
        ? ` (${ch.n_td || 0} TD · ${ch.n_psd_bridge || 0} PSD)`
        : (ch.n_channel != null ? ` (n=${ch.n_channel})` : "");   // logpsd fallback
      // r curve (solid, left axis) + AUC curve (dashed, right axis), shared legend group per channel.
      traces.push({ x: centers, y: ch.r, name: `${ch.short}${nch} · r`, type: "scattergl", mode: "lines",
        line: { width: 2, color }, connectgaps: false, legendgroup: ch.short, yaxis: "y",
        customdata: centers.map((c, bi) => [ci, bi]),
        hovertemplate: "%{x:.1f} Hz · r=%{y:.2f}<extra>%{fullData.name}</extra>" });
      // R1/A1: plot the SIGNED AUC (oriented by the band's correlation sign) so a band whose power
      // FALLS with pain reads below the 0.5 chance line and a null band sits at ~0.5 — the folded
      // `auc` (always >= 0.5) made every band look discriminative. Fall back to folded auc if absent.
      traces.push({ x: centers,
        y: (ch.auc_signed && ch.auc_signed.length === centers.length) ? ch.auc_signed : ch.auc,
        name: `${ch.short}${nch} · AUC (signed)`, type: "scattergl", mode: "lines",
        line: { width: 1.6, color, dash: "dot" }, connectgaps: false, legendgroup: ch.short, yaxis: "y2",
        customdata: centers.map((c, bi) => [ci, bi]),
        hovertemplate: "%{x:.1f} Hz · signed AUC=%{y:.2f}<extra>%{fullData.name}</extra>" });
      // Rigor-pass overlay: solid black-outlined markers at every band whose rating-clustered
      // logit p survives BH-FDR over the band x channel grid (`is_fdr_sig` from the backend).
      // The markers sit on the r curve (left axis) — same color as the channel, with a black ring
      // so they read as "validated under proper clustered inference" against the unstyled
      // pooled-by-default points the line implies. legendgroup ties them to the channel toggle so
      // hiding a channel hides its FDR markers too. showlegend=false (channel curve already
      // identifies the channel; a separate "FDR" entry is in the style legend up top).
      const fdrMask = ch.is_fdr_sig || [];
      const fdrCenters = [], fdrRs = [], fdrCustom = [], fdrHover = [];
      for (let bi = 0; bi < centers.length; bi += 1) {
        if (fdrMask[bi] && ch.r && ch.r[bi] != null) {
          fdrCenters.push(centers[bi]); fdrRs.push(ch.r[bi]);
          fdrCustom.push([ci, bi]);
          const q = ch.q && ch.q[bi];
          fdrHover.push(`${centers[bi].toFixed(1)} Hz · r=${ch.r[bi].toFixed(2)} · q=${q != null ? q.toFixed(3) : "—"}`);
        }
      }
      if (fdrCenters.length) {
        traces.push({ x: fdrCenters, y: fdrRs, name: `${ch.short} · FDR`, type: "scattergl", mode: "markers",
          marker: { size: 9, color, line: { width: 1.2, color: "#000" } },
          legendgroup: ch.short, yaxis: "y", showlegend: false,
          customdata: fdrCustom,
          hovertext: fdrHover, hoverinfo: "text" });
      }
    });
    // Single dedicated legend entry explaining the FDR-marker style — drawn invisibly off-axis
    // with `visible: 'legendonly'` so it never plots data, just adds a labeled swatch to the
    // legend. Placed at the end of `traces` so it appears as the last legend item.
    traces.push({
      x: [null], y: [null], type: "scattergl", mode: "markers",
      name: "● False Discovery Rate-significant (q<0.05, rating-clustered logistic)",
      marker: { size: 9, color: "#777", line: { width: 1.2, color: "#000" } },
      showlegend: true, hoverinfo: "skip",
    });
    // Marker for the currently-selected band (vertical guide).
    const shapes = [];
    if (adaptive && adaptive.length === 2) {
      shapes.push({ type: "rect", xref: "x", yref: "paper", x0: adaptive[0], x1: adaptive[1],
        y0: 0, y1: 1, fillcolor: "#009E73", opacity: 0.10, line: { width: 0 }, layer: "below" });
    }
    // R1/A1: chance line at signed-AUC 0.5 (right axis) so direction reads against an explicit
    // reference — bands below discriminate in the pain-DOWN direction, above it pain-UP.
    shapes.push({ type: "line", xref: "paper", x0: 0, x1: 1, yref: "y2", y0: 0.5, y1: 0.5,
      line: { width: 1, color: "#9AA0A6", dash: "dash" }, layer: "below" });
    // The selected-band vertical guide is NOT drawn here. It is applied by a separate
    // Plotly.relayout effect keyed on `sel` (below), so that clicking a band never rebuilds the
    // traces — a rebuild is what used to wipe the user's legend on/off state (the cleanup purge
    // emptied gd.data before the visibility carry-over could read it). This effect omits `sel`.

    const layout = {
      ...FIG_BASE, autosize: true, height: 575,
      margin: { ...FIG_BASE.margin, b: 96 },   // room for the larger two-group legend
      xaxis: { ...AXIS_BASE, title: { ...AXIS_BASE.title, text: "Band-center frequency (Hz)" },
        // ALWAYS show the full 0–fmax (0–100 Hz) spectrum in both LSB and log-PSD modes. The scan
        // now runs the full range in every mode (centers 2.5–97.5 Hz); the 8–30 Hz deployable band
        // is marked by the green tint + annotation below, not by cropping the axis. (Was previously
        // clamped to [adaptive[0], fmax] in LSB mode, which hid the out-of-band spectrum entirely.)
        range: [0, fmax] },
      yaxis: { ...AXIS_BASE, title: { ...AXIS_BASE.title, text: `${corrName} vs ${pain}` },
        range: [-1.05, 1.05], zeroline: true },
      yaxis2: { ...AXIS_BASE, title: { ...AXIS_BASE.title, text: "Signed logistic AUC (binarized · 0.5 = chance)" },
        overlaying: "y", side: "right", range: [0.0, 1.0], showgrid: false },
      legend: { orientation: "h", y: -0.20, groupclick: "togglegroup",
                // Single-click toggles a group on/off; that's the only legend gesture that changes
                // visibility. Double-click-to-isolate is disabled — without this, a double-click
                // isolates one item (hides all others) and a second restores everything, which
                // surprises users who expect their hidden curves to STAY hidden. To restore
                // everything the user uses the modebar Reset Axes button (an explicit gesture).
                itemclick: "toggle",
                itemdoubleclick: false,
                font: { size: 13 }, tracegroupgap: 14 },
      // Larger, higher-contrast hover tooltip on the scan curves (the per-band r=… / AUC=… readout):
      // 14 px dark text on a near-opaque white card with a darker (less washed-out) gray border, so
      // the label reads clearly even where it sits near the cursor.
      hoverlabel: { bgcolor: "rgba(255,255,255,0.97)", bordercolor: "#5A6470",
                    font: { family: "Roboto, Helvetica, Arial, sans-serif", size: 14, color: "#1A1A1A" } },
      shapes,
      // Plotly preserves user UI state (legend visibility, zoom, axis ranges, selections) across
      // Plotly.react calls whenever `uirevision` is unchanged. We use a constant string here so
      // every re-render of this effect (e.g. a band click that re-builds traces with new
      // customdata) keeps whichever channels the user has toggled off in the legend. The toolbar
      // "Reset axes" button still works — it's a user action, not a react call.
      uirevision: "biomarker-scan",
      // Legend group selection follows the same rule — explicit so a band click doesn't reset it.
      legend_uirevision: "biomarker-scan-legend",
      annotations: (adaptive ? [{ x: (adaptive[0] + adaptive[1]) / 2, yref: "paper", y: 1.02,
        yanchor: "bottom", xanchor: "center", text: "Percept-RC adaptive band (8–30 Hz)",
        showarrow: false, font: { size: 10, color: "#1B7837" } }] : []),
    };
    // Preserve per-trace legend on/off state across renders. Two layers:
    //  (a) layout.uirevision (set below) — Plotly's canonical mechanism; when the revision string
    //      is unchanged, plotly preserves user UI state (legend visibility, zoom, axis ranges)
    //      across Plotly.react calls.
    //  (b) explicit visibility carry-over keyed by trace `name` — belt-and-suspenders for cases
    //      where plotly's uirevision doesn't catch (older versions; trace insertions/deletions
    //      that shift indices). We DO NOT gate on prevData.length === traces.length because the
    //      FDR-marker overlay traces flip on per-channel based on backend output, so the count
    //      changes between renders. Keying purely by `name` survives that: matched names get
    //      their previous visibility; new traces get plotly's default (visible).
    //
    // We treat anything that's NOT explicitly `true` as a hide signal — that catches
    // "legendonly" (the value plotly sets on legend click) and any other non-true sentinel.
    const prevData = ref.current.data;
    if (prevData && prevData.length) {
      const visByName = {};
      prevData.forEach((t) => { if (t && t.name != null) visByName[t.name] = t.visible; });
      traces.forEach((t) => {
        if (Object.prototype.hasOwnProperty.call(visByName, t.name)) {
          const prev = visByName[t.name];
          if (prev !== undefined && prev !== true) t.visible = prev;
        }
      });
    }
    Plotly.react(ref.current, traces, layout, {
      responsive: true, displaylogo: false,
      modeBarButtonsToRemove: ["select2d", "lasso2d", "autoScale2d", "toggleSpikelines"],
    });
    const gd = ref.current;
    const onClick = (ev) => {
      const pt = ev && ev.points && ev.points[0];
      if (pt && pt.customdata) setSel({ ci: pt.customdata[0], bi: pt.customdata[1] });
    };
    gd.on("plotly_click", onClick);
    return () => { if (gd) { gd.removeAllListeners && gd.removeAllListeners("plotly_click"); Plotly.purge(gd); } };
    // NOTE: `sel` is intentionally NOT in this dependency list. A band click only updates `sel`,
    // and the selected-band guide line is applied by the relayout effect below — so a click never
    // re-runs this effect, never triggers the cleanup purge, and therefore never resets the user's
    // legend visibility toggles. (That purge-on-every-click was the cause of hidden curves coming
    // back when isolating a single curve.)
  }, [scan, pain, HI, LO]);   // eslint-disable-line react-hooks/exhaustive-deps

  // Selected-band vertical guide — applied without rebuilding traces, so legend on/off state set by
  // the user survives every band click. Re-applies the adaptive-band shaded rect alongside it
  // (Plotly.relayout replaces the whole `shapes` array, so both must be specified together).
  useEffect(() => {
    const gd = ref.current;
    if (!gd || !gd.data || !centers.length) return;
    const shapes = [];
    if (adaptive && adaptive.length === 2) {
      shapes.push({ type: "rect", xref: "x", yref: "paper", x0: adaptive[0], x1: adaptive[1],
        y0: 0, y1: 1, fillcolor: "#009E73", opacity: 0.10, line: { width: 0 }, layer: "below" });
    }
    if (sel && centers[sel.bi] != null) {
      shapes.push({ type: "line", xref: "x", yref: "paper", x0: centers[sel.bi], x1: centers[sel.bi],
        y0: 0, y1: 1, line: { color: "#444", width: 1.5, dash: "dash" } });
    }
    Plotly.relayout(gd, { shapes });
    // Depends on `scan` too so that after the draw effect rebuilds the plot (scan/pain change), the
    // current selected-band guide is re-applied on top. relayout never touches trace visibility, so
    // the user's legend toggles are unaffected.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sel, scan]);

  // Scatter for the selected (channel, band): band power vs continuous PRO.
  let scatterNode = null;
  if (sel && channels[sel.ci]) {
    const ch = channels[sel.ci];
    const sc = ch.scatter && ch.scatter[sel.bi];
    const center = centers[sel.bi];
    const r = ch.r && ch.r[sel.bi];
    const pBand = ch.p && ch.p[sel.bi];       // rating-clustered logistic Wald p (AUC's inference twin)
    const pPearson = ch.p_pearson && ch.p_pearson[sel.bi];   // Pearson r's own p-value (independence-assuming)
    if (sc && sc.x && sc.x.length) {
      const color = hemiOf(ch) === "Right" ? HI : LO;
      // Fixed pain-group identity colors (DESIGN §8d/§8e idiom): high = vermillion, low = blue,
      // excluded-middle = grey. Shared by the scatter point colors and the violin fills.
      const GRP = { high: "#D55E00", low: "#0072B2", mid: "#9AA0A6" };
      const gArr = sc.g || [];
      const ptColors = gArr.length ? gArr.map((g) => GRP[g] || color) : color;

      // LEFT — band power vs continuous PRO, points colored by pain group (keeps the original view).
      const scTraces = [{ x: sc.x, y: sc.y, type: "scatter", mode: "markers", name: "matched samples",
        marker: { color: ptColors, size: 6, opacity: 0.72 }, text: sc.dates || [],
        hovertemplate: `${featHover}=%{x:.2f}<br>${pain}=%{y:.2f}<extra></extra>` }];

      // RIGHT — violin of THIS band's power split by pain group, with jittered raw points + box +
      // median, so you SEE how low vs high segregate (the comparison the scatter only implies).
      // One violin trace per group; excluded-middle drawn last in grey so it never dominates.
      const order = ["low", "high", "mid"];
      const glabel = { low: "Low pain", high: "High pain", mid: "Excluded (middle)" };
      const vioTraces = order
        .map((g) => {
          const ys = sc.x.filter((_, i) => gArr[i] === g);
          if (!ys.length) return null;
          // Darker shade of the group color for the jittered dots so they pop against the fill
          // (which is the same hue at low opacity). White outline draws the eye to individual
          // observations without competing with the violin silhouette.
          const dotColor = { low: "#053D6E", high: "#7A2C00", mid: "#3C3F45" }[g] || GRP[g];
          return {
            type: "violin", y: ys, x: ys.map(() => glabel[g]), name: glabel[g],
            legendgroup: g, scalemode: "width", width: 0.85, spanmode: "soft",
            points: "all", jitter: 0.5, pointpos: 0,
            marker: { color: dotColor, size: 6, opacity: 0.85,
                      line: { color: "#fff", width: 0.8 } },
            line: { color: GRP[g], width: 1.4 }, fillcolor: GRP[g], opacity: g === "mid" ? 0.28 : 0.42,
            box: { visible: true, width: 0.18 }, meanline: { visible: false },
            hovertemplate: `${glabel[g]}<br>${featHover}=%{y:.2f}<extra></extra>` };
        })
        .filter(Boolean);

      // Effect-size annotation (computed server-side on this band's matched samples): Cohen's d
      // (pooled-SD standardized mean diff, high−low), median delta in SD units, and the
      // rating-clustered logistic p already in the payload. The headline of the right panel.
      const cd = sc.cohens_d, md = sc.median_delta;
      const nlo = (sc.n_grp && sc.n_grp.low) || 0, nhi = (sc.n_grp && sc.n_grp.high) || 0;
      const nmid = (sc.n_grp && sc.n_grp.mid) || 0;
      const dMag = cd == null ? "" : (Math.abs(cd) >= 0.8 ? " (large)"
        : Math.abs(cd) >= 0.5 ? " (medium)" : Math.abs(cd) >= 0.2 ? " (small)" : " (negligible)");
      const effLine = `Low vs high ${isLsb ? "LSB" : "band power"}:  Cohen's d = ${cd != null ? cd.toFixed(2) : "—"}${dMag}`
        + `,  median Δ = ${md != null ? md.toFixed(2) : "—"} SD,  `
        + `${scan && scan.auc_mode === "rating_grouped" ? "rating-clustered " : ""}p = ${fmtP(pBand)}`;

      // Headline n = DISTINCT observations actually rendered. The server de-duplicates the scatter
      // to one point per rating in rating-grouped (LSB) mode, so n_obs == sc.x.length == the violin's
      // jittered-point count == nlo+nhi+nmid. This is the honest count the title must show — NOT the
      // pre-dedup matched-PSD-row count (sc.n_rows) and NOT the montage match ceiling (ch.n_channel),
      // both of which were previously printed as the headline and exceeded the rendered dots (the
      // "n=84 but 2 dots" bug). Those two are kept as SECONDARY context only.
      const nShown = nlo + nhi + nmid;                 // == sc.n_obs by construction
      // LSB-source split of the rendered points — the two counts the PI wants on every label:
      // how many rendered LSB vectors are time-domain-derived vs PSD-derived. null in logpsd mode.
      const nTD = (sc.n_td != null) ? sc.n_td : null;
      const nPSD = (sc.n_psd != null) ? sc.n_psd : null;
      const hasSrc = nTD != null && nPSD != null;
      const srcLbl = hasSrc ? `${nTD} TD · ${nPSD} PSD` : null;   // e.g. "16 TD · 83 PSD"
      const subsampled = (sc.n_distinct != null) && (sc.n_distinct > nShown); // display cap fired
      scatterNode = (
        <MDBox mt={1}>
          {/* Big, bold two-line title centered over BOTH the left scatter and the right violin, so
              it reads as the heading for the whole selected-band readout below it. Line 1: contact
              + samples shown + center frequency. Line 2: the correlation (Spearman ρ for LSB,
              Pearson r for log-power) with its p-value when available. */}
          {/* pt gives the first line room so its ascenders aren't clipped by the panel edge; the
              generous lineHeight (1.45) keeps each line's glyph box taller than the bumped-up
              fontSize so neither line is cut at the top (the MUI variant's default line-height is
              tighter than these sizes, which was clipping the second line). */}
          {/* mt + extra pt give the super-title clearance from the panel/card edge above it. At narrow
              widths line 1 wraps to two physical lines, which previously pushed the block into the
              edge and clipped the top line's ascenders; the added top space keeps it clear at every
              window size. */}
          <MDBox sx={{ textAlign: "center", mb: 1, mt: 2, pt: 1.5 }}>
            {/* Line 1: contact + sample count + center frequency (the WHAT). Line 2: the Pearson
                statistic (the RESULT). Grouping the band identity on line 1 and the stat on line 2
                reads cleaner than splitting freq onto the stat line. */}
            <MDTypography fontWeight="bold" color="dark"
              sx={{ fontSize: 22, lineHeight: 1.45, display: "block" }}>
              {`${ch.short} (n=${nShown}${srcLbl ? `: ${srcLbl}` : ""}${subsampled ? ` of ${sc.n_distinct}` : ""}) @ ${center.toFixed(1)} Hz`}
              {matchDirty && <span style={{ fontSize: 13, fontWeight: 400, color: "#6c757d", marginLeft: 6 }}>{"· scan at prior window"}</span>}
            </MDTypography>
            <MDTypography fontWeight="bold" color="dark"
              sx={{ fontSize: 18, lineHeight: 1.45, display: "block" }}>
              {`${(ch.corr_method === "spearman" ? "Spearman ρ" : (ch.corr_method === "pearson" ? "Pearson r" : corrName))} = ${r != null ? r.toFixed(2) : "—"}`
               + (pPearson != null ? ` (p = ${fmtP(pPearson)})` : "")}
            </MDTypography>
          </MDBox>
          <Grid container spacing={2} mt={0}>
            <Grid item xs={12} lg={6}>
              {/* Taller (was 300) so the panel is closer to SQUARE: at lg the column is ~half the
                  card width (~450–520 px), so ~440 px tall makes the scatter near-1:1 — the right
                  aspect for reading a correlation cloud rather than a wide, flat strip. */}
              <Fig height={440} traces={scTraces} layout={{
                xaxis: { title: `${featAxis} @ ${center.toFixed(1)} Hz` },
                yaxis: { title: pain }, showlegend: false }} />
            </Grid>
            <Grid item xs={12} lg={6}>
              <Fig height={440} traces={vioTraces} layout={{
                xaxis: { title: "" },
                yaxis: { title: `${featAxis} @ ${center.toFixed(1)} Hz` },
                showlegend: false, violingap: 0.25, violinmode: "group" }} />
              <MDTypography variant="caption" display="block" mt={0.5}
                sx={{ color: "#344767", fontWeight: "bold", fontSize: 12.5 }}>
                {effLine}
              </MDTypography>
              <MDTypography variant="caption" color="text" display="block" sx={{ fontSize: 11.5 }}>
                {`n=${nShown}: ${nlo} low · ${nhi} high · ${nmid} excluded-middle`
                 + (srcLbl ? ` · LSB source: ${srcLbl}` : "")
                 + (subsampled ? ` (subsampled from ${sc.n_distinct} for display). ` : ". ")
                 + "Power is z-scored within channel/source, so Δ is in SD units; "
                 + "d>0 means the band is higher when pain is high."}
              </MDTypography>
              <ValidationReadout validation={validation} validating={validating}
                emitContext={(participantUid && requestParams && selChannelRaw != null
                              && selCenterHz != null) ? {
                  participantUid,
                  channelRaw: selChannelRaw,
                  centerHz: Number(selCenterHz),
                  bandWidthHz: scan && scan.band_width_hz ? Number(scan.band_width_hz) : 5.0,
                  requestParams,
                } : null} />
            </Grid>
          </Grid>
        </MDBox>
      );
    } else {
      scatterNode = (
        <MDTypography variant="caption" color="text" mt={1} display="block">
          {`No scatter for ${ch.short} @ ${center.toFixed(1)} Hz (fewer than 3 matched samples in this band).`}
        </MDTypography>
      );
    }
  }

  if (!channels.length) return null;
  return (
    <Grid item xs={12}>
      <Card sx={{ width: "100%", scrollMarginTop: "96px" }}>
        <MDBox p={2}>
          <MDTypography variant="h6" fontSize={19} fontWeight="bold" mb={0.25}>
            {`Spectral feature importance — which band tracks ${pain}? (click a band for its scatter)`}
          </MDTypography>
          {/* LSB-SOURCE INDICATOR: every value feeding this panel is a modeled/real LSB vector derived
              from a time-domain recording (TD-transform, k=352.62) OR a PSD-only patient event (CS-3
              bridge, k≈73.63), computed across the full 0–100 Hz. The chip below pools the independent
              TD- vs PSD-derived LSB counts across the displayed channels so the provenance mix is
              explicit (the per-channel split is in the summary above and on each scatter title). */}
          {(() => {
            const ch = channels || [];
            const tdN = ch.reduce((a, c) => a + (c.n_td || 0), 0);
            const psdN = ch.reduce((a, c) => a + (c.n_psd_bridge || 0), 0);
            if (tdN + psdN === 0) return null;
            return (
              <MDBox display="inline-flex" alignItems="center" gap={0.75} mb={0.75} px={1} py={0.4}
                sx={{ backgroundColor: "rgba(44,82,130,0.06)", border: "1px solid rgba(44,82,130,0.25)",
                      borderRadius: "8px" }}>
                <span style={{ fontSize: 13, fontWeight: 700, color: "#2C5282" }}>{"LSB source"}</span>
                <span style={{ fontSize: 12.5, color: "#33475b" }}>
                  {`derived from TD + PSD sections (0–100 Hz):  `}
                  <strong>{`${tdN} TD-transform`}</strong>{`  ·  `}
                  <strong>{`${psdN} PSD-bridge`}</strong>
                  {`  independent LSB vectors`}
                </span>
              </MDBox>
            );
          })()}
          {/* Bold one-line takeaway: state exactly what the two curves are and the headline caveat,
              before the detailed (backend-supplied) note. Font bumped from caption (~12px) to 14px
              with key phrases bold so the caveats are not lost in a wall of small grey text. */}
          <MDTypography variant="body2" color="text" display="block" fontSize={14} mb={0.5}>
            <strong>Each frequency band is screened two ways</strong>:{` ${corrName} vs the`}
            {` continuous ${pain} score (all matched samples) and a cross-validated logistic `}
            <strong>AUC</strong> on the high-vs-low split.{" "}
            {isLsb && <span>{"LSB is shown on the raw (linear) device scale; ρ is rank-based, robust to its heavy tail. "}</span>}
            <strong>Exploratory screen — neither the correlation nor AUC is a validated biomarker.</strong>
          </MDTypography>
          {/* R2/A2: per-contact biomarker selection — the pain-tracking band AND its direction are
              contact-specific, so name each contact's own best band rather than implying one global
              biomarker. Direction from the sign of ρ; ✓ marks bands clearing rigorous BH-FDR. Built
              as a self-contained IIFE (the proven JSX pattern here) to avoid the react-hooks eslint
              false-positive that a component-body const+map triggers. */}
          {(() => {
            const rows = ((scan && Array.isArray(scan.channels)) ? scan.channels : [])
              .filter((c) => c.selected_band);
            if (!rows.length) return null;
            return (
              <MDBox mb={1} mt={0.5} sx={{ overflowX: "auto" }}>
                <MDTypography variant="caption" display="block" fontWeight="bold" mb={0.5} sx={{ fontSize: 12.5 }}>
                  {"Per-contact best band (no single global biomarker — band & direction differ by contact):"}
                </MDTypography>
                <table style={{ borderCollapse: "collapse", fontSize: 12.5 }}>
                  <thead>
                    <tr style={{ borderBottom: "1px solid #cfd6dd", textAlign: "left" }}>
                      {["Contact", "Band", "Direction", "\u03c1", "Signed AUC", "q (FDR)"].map((h) => (
                        <th key={h} style={{ padding: "2px 10px 2px 0", fontWeight: 600 }}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((c) => {
                      const sb = c.selected_band;
                      const dc = sb.sign === "positive" ? "#D55E00" : sb.sign === "negative" ? "#0072B2" : "#9AA0A6";
                      const dl = sb.direction === "elevation" ? "\u2191 elevation"
                        : sb.direction === "suppression" ? "\u2193 suppression" : "\u2014 flat";
                      return (
                        <tr key={c.short} style={{ borderBottom: "1px solid #eef1f4" }}>
                          <td style={{ padding: "2px 10px 2px 0", fontWeight: 600 }}>{c.short}</td>
                          <td style={{ padding: "2px 10px 2px 0" }}>{`${sb.center_hz.toFixed(1)} Hz`}</td>
                          <td style={{ padding: "2px 10px 2px 0", color: dc, fontWeight: 600 }}>{dl}</td>
                          <td style={{ padding: "2px 10px 2px 0" }}>{sb.rho == null ? "\u2014" : sb.rho.toFixed(2)}</td>
                          <td style={{ padding: "2px 10px 2px 0" }}>{sb.auc_signed == null ? "\u2014" : sb.auc_signed.toFixed(2)}</td>
                          <td style={{ padding: "2px 10px 2px 0", fontWeight: sb.fdr_significant ? 700 : 400,
                                       color: sb.fdr_significant ? "#0a7f3f" : "#6c757d" }}>
                            {sb.q == null ? "\u2014" : `${sb.q.toFixed(3)}${sb.fdr_significant ? " \u2713" : ""}`}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
                <MDTypography variant="caption" display="block" mt={0.3} sx={{ fontSize: 11, fontStyle: "italic", color: "#6c757d" }}>
                  {"\u2713 = survives band\u00d7channel BH-FDR (q<0.05); others are the contact's strongest exploratory band. Signed AUC <0.5 = power falls with pain."}
                </MDTypography>
              </MDBox>
            );
          })()}
          {scan && scan.note && (
            <MDTypography variant="body2" color="text" display="block" fontSize={14} mb={0.5}>
              {scan.note}
            </MDTypography>
          )}
          {/* Condensed methods line: matching policy + survey usage in ONE compact statement. The
              per-channel high/low/excluded + TD/PSD-LSB counts now live in the summary above the
              scan and on each scatter title, so this line states only the pooled method facts. */}
          {scan && scan.max_per_rating != null && (
            <MDTypography variant="body2" display="block" mb={0.5} fontSize={13.5}
              sx={{ color: "#2C5282" }}>
              <strong>{"Matching: "}</strong>
              {(scan.match_direction === "pro_first"
                  ? `PRO-first — each rating claims ≤${scan.max_per_rating} closest PSD${scan.max_per_rating > 1 ? "s" : ""}/channel in the window`
                  : scan.match_direction === "nearest"
                    ? "each PSD → nearest rating either direction"
                    : scan.match_direction === "prior"
                      ? "each PSD → next rating after it (forecasting)"
                      : `≤${scan.max_per_rating} PSD${scan.max_per_rating > 1 ? "s" : ""}/rating (legacy payload)`)
               + (scan.max_per_rating > 1 && scan.refractory_min ? `, ≥${scan.refractory_min} min apart` : "")
               + (scan.n_capped_dropped ? `, ${scan.n_capped_dropped} excess dropped` : "")
               + ". "
               + (scan.auc_mode === "rating_grouped"
                  ? "AUC folds grouped by rating (effective n = independent ratings)."
                  : "Every matched sample treated as independent.")
               + (scan.survey_usage
                  ? ` Surveys used: ${scan.survey_usage.n_pro_used}/${scan.survey_usage.n_pro_total} (${scan.survey_usage.pct_pro_used}%).`
                  : "")}
            </MDTypography>
          )}
          {/* One-line LSB provenance + validated-range note (only in LSB mode). */}
          {scan && scan.feature === "lsb_cs14" && (
            <MDTypography variant="body2" color="text" display="block" mb={0.5} fontSize={13.5} sx={{ fontStyle: "italic" }}>
              {"LSB per rating: TD-transform (k\u202f=\u202f352.62) when a time-domain recording covers it, "
               + "else CS-3 PSD bridge (k\u202f\u2248\u202f73.63). Full 0\u2013100\u202fHz; green shading = validated 7.8\u201330\u202fHz."}
            </MDTypography>
          )}
          {/* Double-dipping: only suppress when PRO-first + rating-grouped AUC already handles it.
              In PRO-first mode each rating is the unit of analysis and the AUC groups folds by rating,
              so multi-PSD-per-rating is intentional and the AUC n is already the independent count.
              Show the warning for every other direction — INCLUDING legacy payloads with no
              match_direction field (cached prior/nearest scans), where double-dipping is real and
              hiding it would mislead the clinician. Only the explicit "pro_first" string suppresses. */}
          {scan && scan.pro_independence && scan.pro_independence.n_excess_matches > 0
            && scan.match_direction !== "pro_first" && (
            <MDTypography variant="body2" display="block" mb={0.5} fontSize={14}
              sx={{ color: scan.pro_independence.pct_nonindependent >= 50 ? "#B7791F" : "text.secondary",
                    fontWeight: scan.pro_independence.pct_nonindependent >= 50 ? "bold" : "regular" }}>
              {`⚠ PRO double-dipping: ${scan.pro_independence.n_matched} matched samples `
               + `cover only ${scan.pro_independence.n_unique_pro} unique pain scores `
               + `(${scan.pro_independence.pct_nonindependent}% non-independent; worst score reused `
               + `${scan.pro_independence.max_reuse}×). `
               + (scan.auc_mode === "rating_grouped"
                  ? `AUC folds are grouped by rating so AUC is corrected; ${corrName} still pools all samples — treat the correlation as exploratory.`
                  : `Effective sample size is well below the matched n — treat both the correlation and AUC as exploratory.`)}
            </MDTypography>
          )}
          <div ref={ref} style={{ width: "100%", height: 420 }} />
          {scatterNode}
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
        {/* Section header at ~2x the prior size for clear hierarchy between TD / power-domain.
            The MUI h3 variant ships a line-height TIGHTER than this bumped-up 40px fontSize, so the
            first line's ascenders/caps were clipped at the top until a zoom forced a reflow. Set an
            explicit lineHeight (1.3) ≥ the font box and a little top padding so the glyphs always
            have room and the title renders fully at default zoom. */}
        <MDTypography variant="h3" fontWeight="bold"
          sx={{ fontSize: 40, lineHeight: 1.3, pt: 0.5, overflow: "visible" }}>{title}</MDTypography>
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

export default function BiomarkerAnalytics({ analytics, summary, metricLabel, recordedPowers, programmedThresholds,
  binStrategy: previewStrategy, binMetricKey: previewMetricKey,
  binPercentileLow: previewPctLow, binPercentileHigh: previewPctHigh,
  participantUid, requestParams, matchDirty }) {
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
  // Source modality of each per_channel entry — the RELIABLE discriminator between the two
  // physically distinct recordings (more robust than the kind/name parse):
  //   "chronic"     = BrainSense Timeline ~10-min around-the-clock LFP power (one stream per
  //                   hemisphere — the most critical biomarker series, sampled 24/7).
  //   "powerdomain" = per-session BrainSense streaming band power (bipolar sensing contacts).
  const srcModOf = (k) => {
    const s = perChannel[k] && perChannel[k].summary;
    return (s && s.source_modality) || null;
  };
  const isChronicKey = (k) => srcModOf(k) === "chronic";
  // A STREAMING bipolar contact: powerdomain source + contact kind (or, for legacy runs with no
  // source tag, just contact kind). These are the curves the per-hemisphere mean ROC averages over.
  const isStreamContactKey = (k) =>
    (srcModOf(k) === "powerdomain" && kindOf(k) === "contact") ||
    (srcModOf(k) == null && kindOf(k) === "contact");
  // Both modalities are individually implementable and BOTH must be analyzable (ROC, threshold,
  // distribution, sliding window). Grouped LEFT first then RIGHT; never mix the two stimulation
  // targets (Left GPi vs Right VIM) into one mean.
  const leftContacts = channelKeys.filter((k) => isStreamContactKey(k) && hemiOf(k) === "Left").sort();
  const rightContacts = channelKeys.filter((k) => isStreamContactKey(k) && hemiOf(k) === "Right").sort();
  const leftChronic = channelKeys.filter((k) => isChronicKey(k) && hemiOf(k) === "Left").sort();
  const rightChronic = channelKeys.filter((k) => isChronicKey(k) && hemiOf(k) === "Right").sort();
  const orderedContacts = [...leftContacts, ...rightContacts];
  // Every individually-selectable channel: chronic streams AND streaming contacts (chronic listed
  // first per hemisphere since it is the around-the-clock biomarker). A true powerdomain pool
  // (source=powerdomain, kind=aggregate) is intentionally NOT selectable.
  const selectableKeys = [...leftChronic, ...leftContacts, ...rightChronic, ...rightContacts];
  const isSelectableKey = (k) => selectableKeys.indexOf(k) !== -1;
  const hasLeft = leftContacts.length > 0;
  const hasRight = rightContacts.length > 0;
  // Aggregate (pooled powerdomain) key for a hemisphere, if any — used to bind the histogram /
  // sliding-window panels when a hemisphere MEAN is selected. Chronic streams are NOT aggregates.
  const aggKeyFor = (h) => channelKeys.find(
    (k) => kindOf(k) === "aggregate" && !isChronicKey(k) && hemiOf(k) === h) || null;

  // Default to a single IMPLEMENTABLE contact — the one with the highest in-sample AUC (best
  // discrimination), since you program one bipolar contact at a time on the Percept RC. We never
  // default to a cross-channel pool. If no per-contact split exists (legacy single-detector run),
  // fall back to "pooled" — which in that case IS the only channel, not a cross-channel average.
  const aucOf = (k) => {
    const s = perChannel[k] && perChannel[k].summary;
    const a = s && (s.auc_in_sample != null ? s.auc_in_sample : s.auc);
    return typeof a === "number" && Number.isFinite(a) ? a : -Infinity;
  };
  // Default to the single most DISCRIMINATIVE implementable channel — highest in-sample AUC across
  // BOTH chronic streams and streaming contacts (we never default to a cross-channel pool). This
  // lets the around-the-clock chronic biomarker be the default when it separates pain best.
  const bestContact = selectableKeys.length
    ? selectableKeys.reduce((best, k) => (aucOf(k) > aucOf(best) ? k : best), selectableKeys[0])
    : null;
  const defaultSel = bestContact || (hasLeft ? "hemi:Left" : (hasRight ? "hemi:Right" : "pooled"));

  // null = "user hasn't picked yet" → fall through to defaultSel. Using a sentinel (rather than
  // seeding useState with defaultSel) means the default tracks the data once `analytics` loads after
  // mount, instead of locking in the empty-data fallback captured on the first render.
  const [chSelRaw, setChSel] = useState(null);
  const chSel = chSelRaw == null ? defaultSel : chSelRaw;
  // Cost-sensitive ROC operating-point control. The optimal threshold under (FP, FN) costs (cFP, cFN)
  // and disease prevalence p is the ROC point where the tangent slope equals m = (cFP/cFN)·((1-p)/p);
  // the picker maximizes TPR - m·FPR. The slider exposes log2(cFP/cFN), so the midpoint (0 ⇒ cFP/cFN=1)
  // reproduces the cost-symmetric Youden default. Negative log2 ⇒ false negatives cost more
  // (high-sensitivity regime: don't miss real pain); positive ⇒ false positives cost more
  // (high-specificity regime: don't stimulate when pain is actually low).
  const [logCostRatio, setLogCostRatio] = useState(0);
  // Frequency sub-selection within the chosen channel. The analysis unit is (channel, frequency):
  // a contact sensed at 7.8 Hz and the SAME contact at 22.5 Hz are different biomarkers and are
  // decoded separately (chronic + streaming pooled only WITHIN a band). null = "all bands of this
  // channel" (the legacy whole-channel ROC/threshold over every sample regardless of band).
  const [freqSelRaw, setFreqSel] = useState(null);
  const isHemiSel = typeof chSel === "string" && chSel.startsWith("hemi:");
  const selHemi = isHemiSel ? chSel.slice(5) : null;
  // A single-channel selection: any individually-selectable channel (a streaming contact OR a
  // chronic around-the-clock stream). Both drive the single-curve ROC / single-channel panels.
  const isContactSel = !!perChannel[chSel] && isSelectableKey(chSel);
  const validSel = chSel === "pooled" || isContactSel ||
    (isHemiSel && ((selHemi === "Left" && hasLeft) || (selHemi === "Right" && hasRight)));
  // Fall back to the default single channel (never the cross-hemisphere pool) on an invalid selection.
  const safeChSel = validSel ? chSel : defaultSel;
  // Which underlying per_channel entry drives the single-summary panels: the contact itself for a
  // contact selection, the hemisphere aggregate for a hemisphere selection, else pooled (null).
  // Plain derivations (cheap, recomputed each render) — kept as plain consts so they sit cleanly
  // before the early return without tripping rules-of-hooks; nothing downstream needs a stable ref.
  const boundKey = safeChSel === "pooled" ? null : (isHemiSel ? aggKeyFor(selHemi) : safeChSel);
  const chronic = boundKey && perChannel[boundKey]
    ? { ...pdRoot, ...perChannel[boundKey] } : pdRoot;

  // Per-(channel, frequency) decoding. The frequency sub-selector is meaningful ONLY for a single
  // implementable channel (a streaming contact or a chronic 24/7 stream) — not the hemisphere mean
  // or the legacy pool, which span multiple contacts/bands. `availFreqs` lists the bands present in
  // this channel (chronic + streaming pooled) with their sample/day counts; `freqDecode` is the
  // backend's per-band ROC/Otsu/binarization map keyed by the snapped Hz string.
  const boundEntry = boundKey ? perChannel[boundKey] : null;
  const freqSelectable = isContactSel && !isHemiSel && safeChSel !== "pooled";
  const availFreqs = (freqSelectable && boundEntry && boundEntry.summary
                      && Array.isArray(boundEntry.summary.available_frequencies))
    ? boundEntry.summary.available_frequencies : [];
  const freqDecode = (freqSelectable && boundEntry && boundEntry.frequency_decode
                      && typeof boundEntry.frequency_decode === "object")
    ? boundEntry.frequency_decode : {};
  // Key helper: the backend keys freqDecode by `${hz:g}` (e.g. "7.8", "10"). Match a selected numeric
  // Hz to that string form so 10.0 -> "10" and 7.8 -> "7.8".
  const freqKey = (hz) => (hz == null ? null : (Number.isInteger(hz) ? String(hz) : String(Number(hz))));
  // Valid frequency selection only when it exists in this channel's decode map; else null = all bands.
  const freqSel = (freqSelRaw != null && freqDecode[freqKey(freqSelRaw)]) ? freqSelRaw : null;
  const selFreqDecode = freqSel != null ? freqDecode[freqKey(freqSel)] : null;
  // Device's CURRENTLY-PROGRAMMED adaptive trigger for the selected channel's hemisphere — present
  // ONLY when closed-loop stim is active there (backend gates this; {} otherwise). Used to overlay
  // "what's set on the device now" on the ROC operating point and the band-power distribution, in
  // the same LFP-power units as the recommendation. null when no active program or no hemisphere.
  const progAll = (programmedThresholds && typeof programmedThresholds === "object") ? programmedThresholds : {};
  const selHemiForProg = isHemiSel ? selHemi : hemiOf(safeChSel);
  const progThr = (selHemiForProg && progAll[selHemiForProg]
                   && progAll[selHemiForProg].lower != null
                   && isFinite(progAll[selHemiForProg].lower))
    ? progAll[selHemiForProg] : null;
  const PROG_COLOR = "#6E0F8A";   // muted purple — the device's programmed trigger (matches timeline)

  if (!analytics) return null;

  // Human-readable pain score these correlations / AUCs are computed against (biological best
  // practice: every correlation/AUC panel should say what it is correlated WITH). Falls back gracefully.
  const pain = metricLabel || "pain";
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
  // chronicHzText REMOVED with the Power-domain section (2026-06-28, PI).

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
    if (recHzByContact[key] != null) return recHzByContact[key];
    // Fall back to the channel's own recorded center frequency from the per_channel summary — this
    // is how the chronic 24/7 stream (absent from recordedPowers) reports its sensing frequency.
    const s = perChannel[k] && perChannel[k].summary;
    return s && s.center_hz != null ? s.center_hz : null;
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
  // DESIGN §8b: the three former TD panels (Pearson-R spectrum, permutation-null + per-session
  // scatter, and mean-PSD-by-pain-state) are replaced by ONE exploratory scan over ALL pooled
  // full-spectrum PSDs (TD streaming + montage/survey) per channel — r vs continuous PRO and CV
  // logistic AUC vs binarized PRO over a 5 Hz sliding band, click-to-scatter.
  const scan = td.spectral_feature_importance || null;
  if (scan && scan.channels && scan.channels.length) {
    tdPanels.push(
      <SpectralFeatureImportance key="sfi" scan={scan} pain={pain} HI={HI} LO={LO}
        participantUid={participantUid} requestParams={requestParams} matchDirty={matchDirty} />
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
  // When a single sensing band is selected, the ROC is the per-(channel,frequency) decode (chronic +
  // streaming pooled AT THAT BAND); otherwise the whole-channel ROC over all bands.
  const roc = (selFreqDecode && selFreqDecode.roc) ? selFreqDecode.roc : (chronic.roc || null);
  const rocTraces = [];
  const rocFor = (k) => (perChannel[k] && perChannel[k].roc) || null;
  const meanAucLabels = []; // for the caption: per-hemisphere mean AUCs
  const drawnByHemi = {};   // hemisphere -> [contact keys actually plotted] (for honest provenance)
  // Optimal operating points — picked LIVE from each curve at the slope set by the cost slider, so
  // dragging the slider re-picks every dot without a backend roundtrip. The picker maximizes
  // TPR - m·FPR over the curve vertices, where m = (cFP/cFN)·((1-p)/p). When the backend payload
  // includes thr+prevalence we use them; otherwise we fall back to the backend's pre-computed
  // Youden operating_point (old payload shape).
  const costRatio = Math.pow(2, logCostRatio);             // cFP / cFN (≥ 0)
  const pickOp = (rocLike) => {
    if (!rocLike || !rocLike.fpr || !rocLike.tpr) return null;
    const fprA = rocLike.fpr, tprA = rocLike.tpr, thrA = rocLike.thr;
    const p = rocLike.prevalence;
    // Falls back to the backend's symmetric Youden point when the payload predates the cost-aware
    // payload (no thr/prevalence) — preserves the dot in that case.
    if (!Array.isArray(thrA) || !Number.isFinite(p) || p <= 0 || p >= 1) {
      const op = rocLike.operating_point;
      return op && Number.isFinite(op.fpr) ? op : null;
    }
    const slope = costRatio * (1 - p) / p;
    let bestK = -1, bestU = -Infinity;
    for (let i = 0; i < fprA.length; i += 1) {
      if (thrA[i] == null) continue;                       // skip the +inf sentinel vertex at (0,0)
      const u = tprA[i] - slope * fprA[i];
      if (u > bestU) { bestU = u; bestK = i; }
    }
    if (bestK < 0) return null;
    return { fpr: fprA[bestK], tpr: tprA[bestK], threshold: thrA[bestK],
             sensitivity: tprA[bestK], specificity: 1 - fprA[bestK],
             slope, direction: "ge" };
  };
  const opMarkers = [];      // marker traces, drawn LAST so the dots sit on top of every curve
  const opLabels = [];       // caption strings: "<curve>: threshold = X (sens, spec)"
  const opAnnotations = [];  // on-dot callout pills showing the device threshold to PROGRAM
  const pushOp = (rocLike, color, label, big) => {
    const op = pickOp(rocLike);
    if (!op || !Number.isFinite(op.fpr) || !Number.isFinite(op.tpr)) return;
    // Each operating point is its OWN legend entry, colored to its curve, with the device-unit
    // threshold to PROGRAM shown bold + underlined right in the legend label (Plotly rich text).
    const thrLabel = op.threshold != null
      ? `${label}: <b><u>power \u2265 ${op.threshold.toFixed(1)}</u></b> (sens ${(op.sensitivity ?? op.tpr).toFixed(2)}, spec ${(op.specificity ?? (1 - op.fpr)).toFixed(2)})`
      : `${label}: optimal threshold`;
    opMarkers.push({
      x: [op.fpr], y: [op.tpr], type: "scatter", mode: "markers",
      name: thrLabel, legendgroup: "oppoint",
      legendgrouptitle: opMarkers.length === 0 ? { text: "Optimal thresholds to program (device units)" } : undefined,
      showlegend: true,
      marker: { color, size: big ? 12 : 8, symbol: "circle",
                line: { color: "#FFFFFF", width: big ? 2 : 1.5 } },
      hovertemplate: `${label} — PROGRAM THIS THRESHOLD<br>power \u2265 ${op.threshold != null ? op.threshold.toFixed(1) : "\u2014"} device units` +
                     `<br>sensitivity=${(op.sensitivity ?? op.tpr).toFixed(2)} · specificity=${(op.specificity ?? (1 - op.fpr)).toFixed(2)}<extra></extra>`,
    });
    // Callout pill anchored to the dot: the device-unit threshold is the number the clinician types
    // into the Percept RC, so it is annotated DIRECTLY on the operating point (not just in the
    // caption/hover). The primary curve (big) gets a filled, prominent pill; per-contact dots get a
    // smaller matching-color pill so a multi-contact plot stays legible.
    if (op.threshold != null) {
      opAnnotations.push({
        x: op.fpr, y: op.tpr, xref: "x", yref: "y",
        text: big ? `<b>Set power \u2265 ${op.threshold.toFixed(1)}</b>` : `<b>\u2265 ${op.threshold.toFixed(1)}</b>`,
        showarrow: true, arrowhead: 0, arrowwidth: 1.2, arrowcolor: color,
        ax: 26, ay: big ? 30 : 22,                 // offset down-right of the dot so it clears the curve
        font: { size: big ? 12.5 : 10.5, color: big ? "#FFFFFF" : color },
        bgcolor: big ? color : "rgba(255,255,255,0.92)",
        bordercolor: color, borderwidth: 1.2, borderpad: big ? 4 : 2.5, opacity: 0.97,
        xanchor: "left", yanchor: "top",
      });
      opLabels.push(`${label}: power \u2265 ${op.threshold.toFixed(1)} device units ` +
        `(sens ${(op.sensitivity ?? op.tpr).toFixed(2)}, spec ${(op.specificity ?? (1 - op.fpr)).toFixed(2)})`);
    }
  };
  // Device's CURRENTLY-PROGRAMMED operating point — where the threshold ALREADY set on the device
  // lands on this ROC curve. Drawn as a HOLLOW marker (vs the filled recommendation dot) in the
  // programmed-trigger purple, so the clinician reads current-vs-recommended at a glance. Only when
  // closed loop is active on this hemisphere (progThr non-null) and the curve carries aligned thr.
  let progMarkerAdded = false;
  const pushProgrammed = (rocLike, label) => {
    if (!progThr || !rocLike || !Array.isArray(rocLike.thr) || !rocLike.fpr) return;
    const thrA = rocLike.thr, fprA = rocLike.fpr, tprA = rocLike.tpr;
    // Find the curve vertex whose threshold is closest to the programmed lower trigger.
    let bestK = -1, bestD = Infinity;
    for (let i = 0; i < thrA.length; i += 1) {
      if (thrA[i] == null || !Number.isFinite(thrA[i])) continue;
      const d = Math.abs(thrA[i] - progThr.lower);
      if (d < bestD) { bestD = d; bestK = i; }
    }
    if (bestK < 0) return;
    const fpr = fprA[bestK], tpr = tprA[bestK];
    opMarkers.push({
      x: [fpr], y: [tpr], type: "scatter", mode: "markers",
      name: `${label}: <b>currently programmed</b> power \u2265 ${progThr.lower.toFixed(1)} (sens ${tpr.toFixed(2)}, spec ${(1 - fpr).toFixed(2)})`,
      legendgroup: "progpoint",
      legendgrouptitle: !progMarkerAdded ? { text: "Currently programmed on device (closed-loop active)" } : undefined,
      showlegend: true,
      marker: { color: "rgba(0,0,0,0)", size: 13, symbol: "circle-open",
                line: { color: PROG_COLOR, width: 2.5 } },
      hovertemplate: `${label} \u2014 CURRENTLY PROGRAMMED on the device<br>power \u2265 ${progThr.lower.toFixed(1)} device units` +
                     `<br>achieves sensitivity=${tpr.toFixed(2)} \u00b7 specificity=${(1 - fpr).toFixed(2)}<extra></extra>`,
    });
    opAnnotations.push({
      x: fpr, y: tpr, xref: "x", yref: "y",
      text: `currently set: \u2265 ${progThr.lower.toFixed(1)}`,
      showarrow: true, arrowhead: 0, arrowwidth: 1.2, arrowcolor: PROG_COLOR,
      ax: -28, ay: -26,                 // offset up-left so it sits opposite the recommendation pill
      font: { size: 10.5, color: PROG_COLOR },
      bgcolor: "rgba(255,255,255,0.92)", bordercolor: PROG_COLOR, borderwidth: 1.2,
      borderpad: 2.5, opacity: 0.97, xanchor: "right", yanchor: "bottom",
    });
    progMarkerAdded = true;
  };
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
        // Optimal operating point for this contact's own ROC, colored to match the curve. Picked
        // LIVE from the curve at the slope set by the cost slider.
        pushOp(c.r, shades[i % shades.length], c.k, false);
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
          // If closed loop is active on THIS hemisphere, show where the programmed trigger lands on
          // its mean curve (progThr is already scoped to the selected hemisphere when isHemiSel).
          if (progThr && selHemiForProg === h) pushProgrammed(mean, `${h} mean`);
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
    // Optimal operating point for the displayed curve — a prominent dot, picked live from the curve
    // at the cost slider's slope (defaults to the cost-symmetric Youden point at the slider midpoint).
    pushOp(roc, meanColorFor(hemiOf(safeChSel) || "Left"),
           isContactView ? safeChSel : "All contacts", true);
    // Where the device's CURRENT programmed trigger lands on this curve (only if closed loop active).
    pushProgrammed(roc, isContactView ? safeChSel : "All contacts");
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
    // Operating-point dots LAST so they sit on top of every curve. One shared legend entry (a black
    // ringed marker) explains what the dots are without cluttering the legend with one per contact.
    // Each operating-point dot carries its OWN legend entry (curve label + bold/underlined device
    // threshold), grouped under one "Optimal thresholds to program" title. No separate shared entry.
    if (opMarkers.length) {
      rocTraces.push(...opMarkers);
    }
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
    // Cost slider for the operating point. log2(cFP/cFN) on [-3, 3] => cost ratios 1:8 .. 8:1.
    // Midpoint (0) reproduces the cost-symmetric Youden default. Labeled with three reference marks.
    const costMarks = [
      { value: -3, label: "1 : 8\u00A0FP:FN" },
      { value: 0, label: "1 : 1" },
      { value: 3, label: "8 : 1\u00A0FP:FN" },
    ];
    const costPrettyRatio = costRatio < 1
      ? `1 : ${(1 / costRatio).toFixed(2)} (FP : FN) — high-sensitivity regime (don't miss real pain)`
      : costRatio > 1
        ? `${costRatio.toFixed(2)} : 1 (FP : FN) — high-specificity regime (don't stimulate when pain is low)`
        : `1 : 1 (cost-symmetric — Youden's J)`;
    // Provenance for the prevalence/slope readout. Use the pooled or selected curve's prevalence if
    // exposed by the backend (the backend includes it on every roc payload from this fix onward).
    const prevForRead = (roc && Number.isFinite(roc.prevalence)) ? roc.prevalence : null;
    const slopeForRead = prevForRead != null ? costRatio * (1 - prevForRead) / prevForRead : null;
    chPanels.push(
      <Panel key="roc" title={`ROC curve — power vs ${pain}${chSuffix} (in-sample)${titleNote}${perWinNote}`}>
        {/* Cost-sensitive operating-point control. The dots on the curves below re-pick live as the
            slider moves — no backend roundtrip — by maximizing TPR - m·FPR over each curve's vertices
            at the cost slope m = (cFP/cFN)·((1-p)/p). */}
        <MDBox px={1} pt={0.5} pb={0.5}>
          <MDBox display="flex" flexDirection="row" alignItems="baseline" gap={2} flexWrap="wrap" mb={0.25}>
            <MDTypography variant="button" fontWeight="bold" color="dark" sx={{ fontSize: 12.5 }}>
              {"Clinical cost ratio (false positive : false negative)"}
            </MDTypography>
            <MDTypography variant="caption" color="dark" sx={{ fontSize: 12 }}>
              {`Now: ${costPrettyRatio}` +
                (prevForRead != null
                  ? ` · prevalence = ${(prevForRead * 100).toFixed(1)}% high-pain · ROC tangent slope m = ${slopeForRead.toFixed(2)}`
                  : "")}
            </MDTypography>
          </MDBox>
          <MDBox px={1.5}>
            <Slider value={logCostRatio} min={-3} max={3} step={0.25} marks={costMarks}
              onChange={(_, v) => setLogCostRatio(Array.isArray(v) ? v[0] : v)}
              valueLabelDisplay="off" size="small"
              sx={{ "& .MuiSlider-markLabel": { fontSize: 10.5 } }} />
          </MDBox>
        </MDBox>
        <Fig height={380} traces={rocTraces} layout={{
          xaxis: { title: "False positive rate", range: [-0.02, 1.02], scaleanchor: "y", scaleratio: 1 },
          yaxis: { title: "True positive rate", range: [-0.02, 1.02] },
          legend: { orientation: "h", y: -0.22, groupclick: "toggleitem" },
          annotations: [...rocProvAnn, ...opAnnotations] }} />
        {rocProvenance ? (
          <MDTypography variant="caption" color="dark" display="block" mt={1} sx={{ fontSize: 11 }}>
            {`Power signal from ${rocProvenance}.` +
             (isMeanView
               ? " Bold line = per-hemisphere mean ROC (vertical average of that hemisphere's plotted bipolar contacts); thin lines behind it are the individual contacts (blue = Left, orange = Right). Contacts with only one pain class (no ROC) are omitted. The two hemispheres are never averaged together (separate stimulation targets)."
               : "") +
             (windowRocs.length ? " Faint orange curves are individual sliding-window ROCs." : "")}
          </MDTypography>
        ) : null}
        {opLabels.length ? (
          <MDTypography variant="caption" color="dark" display="block" mt={0.5} fontWeight="medium" sx={{ fontSize: 11.5 }}>
            {(Math.abs(logCostRatio) < 1e-6
              ? `Optimal device threshold at the COST-SYMMETRIC operating point (Youden's J — equal cost for false positives and false negatives): `
              : `Optimal device threshold at the SELECTED cost ratio ${costPrettyRatio.split(" — ")[0]} — the ROC point where the curve's tangent slope equals m = (cFP/cFN)·((1-p)/p)` +
                (slopeForRead != null ? ` = ${slopeForRead.toFixed(2)}` : "") + `: `) +
             opLabels.join(" · ") +
             `. Classify pain-high when band power \u2265 this value on the Percept RC.`}
          </MDTypography>
        ) : null}
        {progThr ? (
          <MDTypography variant="caption" display="block" mt={0.5} sx={{ fontSize: 11.5, color: PROG_COLOR }}>
            {`Hollow purple marker = the threshold CURRENTLY programmed on the device (closed-loop active on ${selHemiForProg}): power \u2265 ${progThr.lower.toFixed(1)} device units. Compare its sensitivity/specificity against the filled recommendation dot to decide whether to re-program.`}
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
  // Band-scoped distribution when a sensing band is selected, else the whole-channel histogram.
  const dist = (selFreqDecode && selFreqDecode.distribution)
    ? selFreqDecode.distribution : (chronic.lfp_distribution || null);
  // Need one more edge than counts to form bin centers; without it every center is NaN.
  if (dist && dist.counts && dist.counts.length
      && Array.isArray(dist.bin_edges) && dist.bin_edges.length >= dist.counts.length + 1) {
    const edges = dist.bin_edges;
    const centers = dist.counts.map((_, i) => (edges[i] + edges[i + 1]) / 2);
    // The ROC-optimal threshold is the value actually programmed on the device; overlay it on the
    // same band-power axis as a second reference line so the clinician can compare the unsupervised
    // Otsu split (ignores the pain label) against the supervised, label-driven optimum. This pulls
    // from the LIVE cost-sensitive picker so it tracks the cost slider above (defaults to the
    // cost-symmetric Youden point when the slider sits at 1:1).
    const distOp = roc ? pickOp(roc) : null;
    const distOpThr = distOp && Number.isFinite(distOp.threshold) ? distOp.threshold : null;
    // Only show it if it lands within the displayed (inlier) range, else the line floats off-axis.
    const distOpInRange = distOpThr != null && distOpThr >= edges[0] && distOpThr <= edges[edges.length - 1];
    // Device's currently-programmed adaptive trigger (only when closed loop is active on this
    // hemisphere) — a third, lighter reference so the clinician sees where the CURRENT device
    // setting sits relative to the recommended optimum and the unsupervised Otsu valley.
    const progThrVal = progThr ? progThr.lower : null;
    const progInRange = progThrVal != null && progThrVal >= edges[0] && progThrVal <= edges[edges.length - 1];
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
            shapes: [
              ...(dist.otsu != null ? [{ type: "line", x0: dist.otsu, x1: dist.otsu, yref: "paper",
                y0: 0, y1: 1, line: { color: PALETTE[1], width: 2.5, dash: "dash" } }] : []),
              ...(distOpInRange ? [{ type: "line", x0: distOpThr, x1: distOpThr, yref: "paper",
                y0: 0, y1: 1, line: { color: "#117733", width: 2.5, dash: "dot" } }] : []),
              ...(progInRange ? [{ type: "line", x0: progThrVal, x1: progThrVal, yref: "paper",
                y0: 0, y1: 1, line: { color: PROG_COLOR, width: 1.5, dash: "solid" }, opacity: 0.6 }] : []),
            ],
            annotations: [
              ...(dist.otsu != null ? [{ x: dist.otsu, yref: "paper", y: 1.02,
                text: `Otsu = ${dist.otsu.toFixed(1)}`, showarrow: false,
                font: { color: PALETTE[1], size: 11 }, xanchor: "left", yanchor: "bottom" }] : []),
              ...(distOpInRange ? [{ x: distOpThr, yref: "paper", y: 1.10,
                text: `ROC optimum = ${distOpThr.toFixed(1)}`, showarrow: false,
                font: { color: "#117733", size: 11 }, xanchor: "left", yanchor: "bottom" }] : []),
              ...(progInRange ? [{ x: progThrVal, yref: "paper", y: 1.18,
                text: `Programmed = ${progThrVal.toFixed(1)} (active)`, showarrow: false,
                font: { color: PROG_COLOR, size: 11 }, xanchor: "left", yanchor: "bottom" }] : []),
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
           `Bars are trimmed to the inlier 1st\u201399th percentile for display. ` +
           `Orange dashed line = Otsu split (unsupervised, label-free — minimizes within-class variance of the power distribution). ` +
           (distOpInRange
             ? `Green dotted line = ROC-optimal (Youden) threshold = ${distOpThr.toFixed(1)} device units, the supervised cut that jointly maximizes true positives and minimizes false positives against the pain label — this is the value to program for closed loop.`
             : `The ROC-optimal (Youden) threshold for closed-loop programming is shown on the ROC panel above.`)}
        </MDTypography>
      </Panel>
    );
  }

  // PER-(CHANNEL, FREQUENCY) BINARIZATION PREVIEW. When a single sensing band is selected, show what
  // pain-score data is present for THAT (channel, frequency) and how the high/low split falls — the
  // same histogram + cut markers + day/sample class counts as the report-level BinarizationPreview,
  // but scoped to the band's decoding set (chronic + streaming pooled at this band only). The daily
  // means come pre-aggregated from the backend decode so heavy chronic bands stay light on the wire.
  if (selFreqDecode && selFreqDecode.binarization
      && Array.isArray(selFreqDecode.binarization.daily) && selFreqDecode.binarization.daily.length) {
    const bz = selFreqDecode.binarization;
    chPanels.push(
      <Panel key="freq-binarization"
             title={`Pain binarization @ ${Number(freqSel).toFixed(1)} Hz${chSuffix}`}>
        <BinarizationPreview
          dailyAgg={bz.daily}
          strategy={previewStrategy || "median"}
          percentileLow={previewPctLow}
          percentileHigh={previewPctHigh}
          metricLabel={metricLabel}
          metricKey={previewMetricKey}
          loading={false}
        />
        <MDTypography variant="caption" color="dark" display="block" mt={1} sx={{ fontSize: 11 }}>
          {`Pain-score days available for ${safeChSel} @ ${Number(freqSel).toFixed(1)} Hz: ` +
           `${bz.n_days_labeled.toLocaleString()} labeled day(s) across ` +
           `${selFreqDecode.n_labeled.toLocaleString()} band-power samples (chronic + streaming combined at this band). ` +
           `Decode-time split: ${bz.n_pos_days.toLocaleString()} high-pain / ${bz.n_neg_days.toLocaleString()} low-pain days ` +
           `(${bz.n_pos_samples.toLocaleString()} / ${bz.n_neg_samples.toLocaleString()} samples). ` +
           `The histogram and cut lines above recompute live from the binarization controls at the top of the report; ` +
           `the high/low day and sample counts are the data this (channel, frequency) detector is trained on.`}
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

  if (tdPanels.length === 0) return null;

  // Channel selector (channelToggle) REMOVED with the Power-domain section (2026-06-28, PI):
  // it only drove the chronic ROC / distribution / sliding-window panels, which are gone.

  // Rigor-pass annotation: if the backend supplied a band x channel BH-FDR summary, append the
  // naive-vs-rigorous count contrast to the subtitle. This is the headline pseudoreplication
  // honesty number. The naive family treats every matched neural sample as independent, but each
  // pain rating contributes UP TO MaxPerRating samples (the cap on the slider) — so the naive FDR
  // over-reports. The rating-clustered logistic q accounts for the samples that share a rating. This
  // holds whether or not LSB vectors are reused: the no-reuse rule changes each sample's FEATURE
  // VALUE, not how many samples a rating contributes (that is the MaxPerRating cap). Reads as e.g.
  // "[N bands survive rating-clustered FDR vs M under naive FDR; ringed dots mark the survivors]".
  const fdrSummary = scan && scan.fdr_summary;
  const rigorAnnotation = fdrSummary
    ? ` ${fdrSummary.n_rigorous_fdr} of ${fdrSummary.n_bands_total} bands survive BH-FDR under rating-clustered logistic (the inferential headline); ${fdrSummary.n_naive_fdr} survive the naive per-sample FDR, which treats each matched sample as independent and over-reports because one rating contributes up to MaxPerRating samples. Ringed dots above mark the rigorous-FDR survivors.`
    : "";

  // Outlier exclusion (PI, 2026-08-30). Stated here rather than buried, because every statistic in
  // this section — the correlation, the cross-validated AUC, the rating-clustered logistic p and the
  // click-panel effect size — is computed AFTER these samples are dropped, from ONE shared exclusion
  // set per (channel, band). The count is reported so the reader can judge whether the rule is
  // trimming a few artefacts or reshaping the sample.
  const outl = scan && scan.outliers;
  const outlierAnnotation = (outl && outl.enabled)
    ? ` Outlier exclusion: a sample is dropped when its band power lies ${outl.n_mad}` +
      ` or more median absolute deviations (MAD) from that band's median, evaluated on the` +
      ` ${outl.scale} scale and applied separately to each (channel, band).` +
      ` ${(outl.n_removed || 0).toLocaleString()} of ${(outl.n_samples_considered || 0).toLocaleString()}` +
      ` samples were removed` +
      (outl.pct_removed != null ? ` (${outl.pct_removed.toFixed(2)}%)` : "") +
      `, affecting ${outl.n_bands_with_removal} of ${outl.n_bands_evaluated} bands.` +
      ` The same excluded samples are held out of every statistic here — correlation, AUC,` +
      ` rating-clustered logistic p and the click-panel effect size — so no two numbers are computed` +
      ` on different samples. The rule is applied to the band-power feature only; the pain score is` +
      ` left intact, because it is a bounded ordinal scale on which extreme values are signal rather` +
      ` than contamination. The MAD is used raw, without the 1.4826 consistency rescaling, so` +
      ` ${outl.n_mad} MAD is about ${(outl.n_mad * 0.6745).toFixed(2)} standard deviations for` +
      ` Gaussian data.` +
      (outl.n_bands_skipped_zero_mad
        ? ` ${outl.n_bands_skipped_zero_mad} band(s) were skipped because their MAD was zero (a` +
          ` majority of samples sharing one value), where the rule would otherwise have deleted all` +
          ` remaining variation.`
        : "") +
      (outl.pct_removed != null && outl.pct_removed > 2.0
        ? ` Note that removing ${outl.pct_removed.toFixed(1)}% is far more than the ~0.1% a` +
          ` well-behaved unimodal distribution would yield at this threshold, which indicates the` +
          ` feature is a mixture across recording sessions rather than a clean distribution with a` +
          ` few artefacts. Treat the excluded points as possibly-real physiological states, not` +
          ` confirmed noise.`
        : "")
    : (outl ? " Outlier exclusion is DISABLED for this view, so all matched samples are included." : "");

  return (
    <>
      <Section title="Full-spectrum exploration (all PSDs pooled per channel)"
               subtitle={(scan && (scan.feature === "lsb_cs14" || scan.feature === "lsb_calibrated")
                 ? (scan.feature === "lsb_cs14"
                   ? "One LSB per matched (channel, rating) pair: 30 s rating-centred window through the transform DSP (k\u202f=\u202f352.62) when a time-domain recording covers the rating, else the CS-3 PSD bridge (k\u202f\u2248\u202f73.63) for PSD-only patient events. Raw (linear) LSB on the device scale, full 0\u2013100\u202fHz in a 5\u202fHz sliding band; green shading marks the validated 7.8\u201330\u202fHz range. Per band: Spearman \u03c1 vs the continuous score and cross-validated logistic AUC vs the binarized score; click a band for its scatter."
                   : "Every neural recording matched to the nearest pain report, scanned in a 5\u202fHz sliding band. Feature: raw calibrated LSB (269\u202f\u00d7 TD Welch band integral). Per band: Spearman \u03c1 and logistic AUC; click a band for its scatter.")
                 : "Every full-spectrum PSD (time-domain streaming + montage/survey sweeps) matched to the nearest pain report within the chosen window, then scanned in a 5\u202fHz sliding band. Per band: Pearson r vs the continuous score and cross-validated logistic AUC vs the binarized score; click a band for its scatter.") + rigorAnnotation + outlierAnnotation}
               panels={tdPanels} />
      {/* Power-domain analysis section (chronic 10-min trend + per-session band power) REMOVED
          (2026-06-28, PI): chronic LSB averaging is irrelevant to closed-loop deployment, so the
          ROC / power-distribution / sliding-window / pain-cluster panels and their builders were
          dropped. The closed-loop signal is the per-rating LSB scanned above. */}
    </>
  );
}
