/**
 * Choose a band -- the calibrated grid Biomarkers already built, as one compact heat map, redrawn
 * 2026-09-11 on the PI's brief ("the calibrated grid at the top is really ugly and takes up too
 * much space ... a visual depiction similar to the heat map from the biomarkers module, flipped 90
 * degrees so that the band centers are oriented vertically").
 *
 * WHAT THIS READS. `grid` is `report.band_sweep_grid`, computed server-side by
 * `ClosedLoopDeployment.adapter.band_sweep_grid_for_closed_loop`: the SAME stored entry the
 * Biomarkers exploration page reads (`biomarker_band_sweep`), read here as `consumer="closed_loop"`
 * rather than recomputed. Each sensing contact's sweep carries its Medtronic display label
 * (`display_short`, "L 0⁻2⁺"), its side, and the 22 best-of-lengths rows for correlation and for
 * AUC, which is everything drawn here. No new backend field was needed (measured on the live
 * payload, 2026-09-11).
 *
 * WHAT IS DRAWN, per contact tab: one row per band centre (22, 8.5-29.5 Hz, down the side), two
 * colour columns -- the correlation r (diverging around 0) and the AUC (diverging around 0.5,
 * never around 0; house rule) -- each carrying its value, then two symbol columns: whether the
 * correlation clears the 22-centre family-wise correction (decision 63), and the cross-setting
 * stability answer (behaves the same / differently / cannot tell / not tested), then one radio
 * per row under a single "Use this band" heading. The colour scale is the one definition the
 * Biomarkers heat maps use (`binarizationModel.diverging`), and the contact order is theirs too
 * (`contactOrder.orderContacts`: left before right, then by contact number).
 *
 * THE RADIO COMMITS THE BAND, one at a time (decision 2 of the redesign plan): ticking a row
 * commits a BandCandidate through the SAME mechanism the file-upload path uses
 * (`bandCandidateStore.commitBandCandidate`), so every panel below recomputes for the new point
 * exactly as it would for an uploaded candidate. Ticking another row moves the tick. The
 * hemisphere committed is the SWEEP'S OWN side (`display_hemisphere`), not the previously
 * committed band's -- the earlier version passed the old candidate's hemisphere down, so picking a
 * right-side contact while a left band was committed would have committed it as "Left".
 *
 * A row that does not clear the correction stays fully selectable -- the symbol is a label, never
 * a gate (decision 65). And no device-rule mark is drawn: the device's own 51-rule screen needs a
 * specific current, pulse width, rate and impedance reading, none of which a (contact, band) point
 * carries, so it runs live on the band you tick, below (decision 67).
 *
 * The stability symbol is real only when the server has computed it for that point; until then
 * the row shows the dashed "not tested" mark rather than a fabricated answer.
 */
import { useMemo, useState } from "react";
import { Card, Chip, Collapse, Tooltip } from "@mui/material";
import MDBox from "components/MDBox";
import MDTypography from "components/MDTypography";
import MDButton from "components/MDButton";

import { diverging, divergingRgb } from "views/Reports/Biomarkers/binarizationModel";
import { orderContacts } from "views/Reports/Biomarkers/contactOrder";
import PAL from "./palette";
import { fmtHz, fmtNum } from "./deployFormat";
import { commitBandCandidate } from "./bandCandidateStore";

/** One channel's rows, correlation and AUC merged by band centre so one row = one grid point. */
function mergedRows(sweepForChannel) {
  const corr = (sweepForChannel && sweepForChannel.best_correlation_rows) || [];
  const auc = (sweepForChannel && sweepForChannel.best_auc_rows) || [];
  const byCenter = new Map();
  corr.forEach((r) => {
    if (r && r.band_center_hz != null) byCenter.set(r.band_center_hz, { ...r });
  });
  auc.forEach((r) => {
    if (r == null || r.band_center_hz == null) return;
    const existing = byCenter.get(r.band_center_hz) || { band_center_hz: r.band_center_hz };
    existing.auc = r.auc;
    existing.auc_low = r.auc_low;
    existing.auc_high = r.auc_high;
    existing.auc_n_pain_reports = r.n_pain_reports;
    existing.auc_seconds = r.integration_seconds_delivered;
    existing.auc_answer = r.answer;
    existing.family_wise_q_auc = r.family_wise_q_8_to_30hz;
    existing.family_wise_significant_auc = r.family_wise_significant_8_to_30hz;
    // The stability field is attached identically to both grids by
    // `Biomarkers.bravo_service._attach_grid_export_columns`, so either side's copy is the answer;
    // prefer whichever side actually carries it in case only one grid's row was ever built.
    if (existing.cross_setting_stability == null && r.cross_setting_stability != null) {
      existing.cross_setting_stability = r.cross_setting_stability;
    }
    byCenter.set(r.band_center_hz, existing);
  });
  return Array.from(byCenter.values()).sort((a, b) => a.band_center_hz - b.band_center_hz);
}

/** Near-black on a pale cell, white on a saturated one, so the value reads on every fill. */
function inkFor(v, center, half) {
  if (v == null || !Number.isFinite(Number(v))) return "#9A9A9A";
  const [r, g, b] = divergingRgb(v, center, half);
  const luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255;
  return luminance > 0.62 ? "#1A1A1A" : "#FFFFFF";
}

// ---------------------------------------------------------------------------------------------
// THE FOUR SYMBOLS. Distinct shapes as well as distinct inks, because about eight per cent of men
// cannot separate these hues and this page prints: a filled disc with a tick, a filled square with
// a cross, a plain amber disc, and an open dashed circle for "not tested".
// ---------------------------------------------------------------------------------------------
const GLYPH = 15;
function TickGlyph({ label }) {
  return (
    <svg width={GLYPH} height={GLYPH} viewBox="0 0 16 16" role="img" aria-label={label}>
      <circle cx="8" cy="8" r="7" fill={PAL.pass} />
      <path d="M4.5 8.3 L7 10.8 L11.5 5.5" stroke="#fff" strokeWidth="1.9" fill="none"
        strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
function CrossGlyph({ label }) {
  return (
    <svg width={GLYPH} height={GLYPH} viewBox="0 0 16 16" role="img" aria-label={label}>
      <rect width="16" height="16" rx="2" fill={PAL.fail} />
      <path d="M4.5 4.5 L11.5 11.5 M11.5 4.5 L4.5 11.5" stroke="#fff" strokeWidth="1.9"
        strokeLinecap="round" />
    </svg>
  );
}
function AmberGlyph({ label }) {
  return (
    <svg width={GLYPH} height={GLYPH} viewBox="0 0 16 16" role="img" aria-label={label}>
      <circle cx="8" cy="8" r="7" fill={PAL.warn} />
    </svg>
  );
}
function NotTestedGlyph({ label }) {
  return (
    <svg width={GLYPH} height={GLYPH} viewBox="0 0 16 16" role="img" aria-label={label}>
      <circle cx="8" cy="8" r="6.5" fill="none" stroke={PAL.neutral} strokeWidth="1.4"
        strokeDasharray="2 2" />
    </svg>
  );
}

function FamilyWiseMark({ significant, q }) {
  const qTxt = q != null ? ` (q = ${fmtNum(q, 3)})` : "";
  if (significant == null) {
    return (
      <Tooltip title="the 22-centre family-wise correction has not been computed for this row">
        <span><NotTestedGlyph label="correction not assessed" /></span>
      </Tooltip>
    );
  }
  return (
    <Tooltip title={significant
      ? `clears the Benjamini-Hochberg correction across this contact pair's 22 band centres${qTxt}`
      : `does not clear the 22-centre correction${qTxt} — still selectable; this is a label, not a gate`}>
      <span>{significant ? <TickGlyph label="clears correction" />
        : <CrossGlyph label="does not clear correction" />}</span>
    </Tooltip>
  );
}

function StabilityMark({ stability }) {
  const answer = (stability && stability.answer) || "not tested";
  const reason = (stability && stability.reason) || "";
  const tip = stability
    ? `${answer}${reason ? ` — ${reason}` : ""}`
    : "the cross-setting-stability answer has not been computed for this point yet";
  let glyph;
  if (answer === "behaves the same") glyph = <TickGlyph label="behaves the same at every setting" />;
  else if (answer === "behaves differently") glyph = <CrossGlyph label="behaves differently across settings" />;
  else if (answer === "cannot tell") glyph = <AmberGlyph label="cannot tell" />;
  else glyph = <NotTestedGlyph label="not tested" />;
  return <Tooltip title={tip}><span>{glyph}</span></Tooltip>;
}

/** A thin gradient bar with its three anchor values, for the legend line. */
function ScaleBar({ center, half, lo, mid, hi }) {
  const stops = [-1, -0.5, 0, 0.5, 1].map((t) => diverging(center + t * half, center, half));
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 5 }}>
      <span style={{ fontFamily: PAL.mono, fontSize: 10 }}>{lo}</span>
      <span style={{ display: "inline-block", width: 72, height: 9, borderRadius: 2,
        background: `linear-gradient(90deg, ${stops.join(", ")})` }} />
      <span style={{ fontFamily: PAL.mono, fontSize: 10 }}>{hi}</span>
      <span style={{ color: "#8A8A8A", fontSize: 10 }}>{`(${mid} = no relationship)`}</span>
    </span>
  );
}

/**
 * The settings the served grid was built under, in one fine-print line (the PI, 2026-09-11: "very
 * brief concise stats of what match window was used, if it's PRO-first discovery or not, a median
 * split or what kind of split"). Every value comes from the server's own tag of the stored entry
 * (`grid_settings`), never from this page's state, so a mismatch would be visible rather than
 * silent. Nothing here is a threshold.
 */
const DIRECTION_TEXT = { pro_first: "PRO-first match", prior: "recording-before-rating match",
  nearest: "nearest-in-time match" };
export function gridSettingsLine(gs) {
  if (!gs) return null;
  const parts = [];
  parts.push(gs.metric_label || gs.sweep_metric || "pain score ?");
  parts.push(gs.match_tolerance_min != null ? `\u00b1${fmtNum(gs.match_tolerance_min, 0)} min window`
    : "same-day match");
  parts.push(DIRECTION_TEXT[gs.match_direction] || `${gs.match_direction || "?"} match`);
  if (gs.allow_window_reuse) parts.push("windows reused");
  const lo = gs.percentile_low != null ? fmtNum(gs.percentile_low, 0) : "?";
  const hi = gs.percentile_high != null ? fmtNum(gs.percentile_high, 0) : "?";
  const split = { tertile: `tertile split ${lo}/${hi} %`, percentile: `percentile split ${lo}/${hi} %`,
    median: "median split", kmeans: "k-means split", cutoff: "fixed cut-off split" };
  parts.push(split[gs.label_strategy] || `${gs.label_strategy || "?"} split`);
  return parts.join(" \u00b7 ");
}
function gridBuiltText(gs) {
  if (!gs) return null;
  if (gs.built_now) return "built just now";
  if (!gs.stored_utc) return null;
  const d = new Date(gs.stored_utc);
  if (Number.isNaN(d.getTime())) return `built ${gs.stored_utc}`;
  return `built ${d.toLocaleDateString(undefined, { day: "numeric", month: "short" })} `
    + d.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
}
function SettingsFinePrint({ gs }) {
  const line = gridSettingsLine(gs);
  if (!line) return null;
  const built = gridBuiltText(gs);
  return (
    <MDTypography variant="caption" sx={{ fontSize: 10, color: "#8A8A8A", textAlign: "right",
      lineHeight: 1.35, maxWidth: "62ch" }}>
      {line}{built ? <><br />{built}</> : null}
    </MDTypography>
  );
}

const HEAD = { fontSize: 10, fontWeight: 700, letterSpacing: 0.4, color: "#8A8A8A",
  textTransform: "uppercase", lineHeight: 1.2, textAlign: "center", paddingBottom: 4 };
const CELL_H = 19;

export default function BandSweepGridPanel({ grid, participantUid, committed, onCandidateChosen }) {
  // Memoised, because a fresh `{}` on every render (when there is no grid yet) would make every
  // memo below it recompute on every render.
  const sweeps = useMemo(() => (grid && grid.band_time_sweep) || {}, [grid]);
  const channels = useMemo(() => orderContacts(sweeps), [sweeps]);
  const [activeChannel, setActiveChannel] = useState(null);
  const [showHelp, setShowHelp] = useState(false);
  // Open on the committed band's contact when there is one, so the tick is visible on arrival.
  const channel = (activeChannel && channels.includes(activeChannel)) ? activeChannel
    : (committed && committed.contact && channels.includes(committed.contact)) ? committed.contact
      : channels[0];

  if (!grid || grid.available === false) {
    return (
      <Card sx={{ p: 2, mb: 2 }}>
        <MDBox display="flex" alignItems="flex-start" justifyContent="space-between" gap={1}>
          <MDTypography variant="h6" fontWeight="bold">Choose a band</MDTypography>
          <SettingsFinePrint gs={grid && grid.grid_settings} />
        </MDBox>
        <MDTypography variant="body2" color="text" mt={1}>
          {(grid && grid.reason) || "no calibrated grid is available for this participant yet."}
          {" "}Visit the Biomarkers exploration page first, then return here.
        </MDTypography>
      </Card>
    );
  }

  const sw = sweeps[channel] || {};
  const rows = mergedRows(sw);
  const bandWidthHz = Number(sw.band_width_hz || 5.0);
  const sideOf = (ch) => {
    const s = sweeps[ch] || {};
    return s.display_hemisphere || (/LEFT/i.test(ch) ? "Left" : (/RIGHT/i.test(ch) ? "Right" : null));
  };
  const labelOf = (ch) => {
    const s = sweeps[ch] || {};
    return s.display_short || String(ch || "").replace(/_/g, " ");
  };
  const isCommitted = (row) => !!(committed && committed.contact === channel
    && committed.centerHz != null && Math.abs(Number(committed.centerHz) - row.band_center_hz) < 1e-6);

  const choose = (row) => {
    const hemisphere = sideOf(channel);
    commitBandCandidate(participantUid, {
      contact: channel,
      contact_label: labelOf(channel),
      center_freq_hz: row.band_center_hz,
      bandwidth_hz: bandWidthHz,
      hemisphere,
      threshold_mode: "dual",
      schema_version: "bandcandidate_v1",
      label: {},
    });
    if (onCandidateChosen) {
      onCandidateChosen({ channel, centerHz: row.band_center_hz, bandWidthHz,
        sensingHemisphere: hemisphere });
    }
  };

  // The tabs: left group, a gap, right group -- the same order as the Biomarkers thumbnails.
  const leftTabs = channels.filter((ch) => sideOf(ch) === "Left");
  const rightTabs = channels.filter((ch) => sideOf(ch) === "Right");
  const otherTabs = channels.filter((ch) => sideOf(ch) !== "Left" && sideOf(ch) !== "Right");
  const tab = (ch) => (
    <Chip key={ch} label={labelOf(ch)} size="small" onClick={() => setActiveChannel(ch)}
      title={sw && sweeps[ch] && sweeps[ch].display_region ? sweeps[ch].display_region : undefined}
      sx={{
        fontWeight: ch === channel ? 700 : 400, fontSize: 12,
        backgroundColor: ch === channel ? PAL.accentFill : "transparent",
        border: `1px solid ${ch === channel ? PAL.accentBorder : PAL.neutralBorder}`,
      }} />
  );

  const corrTip = (row) => (row.pearson_r == null ? "no correlation for this band"
    : `r = ${fmtNum(row.pearson_r, 3)}`
      + (row.pearson_r_low != null && row.pearson_r_high != null
        ? ` (95% interval ${fmtNum(row.pearson_r_low, 3)} to ${fmtNum(row.pearson_r_high, 3)})` : "")
      + (row.integration_seconds_delivered != null
        ? `, best of ${row.chosen_as_best_of_n_windows || 10} lengths at ${fmtNum(row.integration_seconds_delivered, 0)} s` : "")
      + (row.n_pain_reports != null ? `, ${row.n_pain_reports} pain reports` : ""));
  const aucTip = (row) => (row.auc == null ? "no AUC for this band"
    : `AUC = ${fmtNum(row.auc, 3)}`
      + (row.auc_low != null && row.auc_high != null
        ? ` (95% interval ${fmtNum(row.auc_low, 3)} to ${fmtNum(row.auc_high, 3)})` : "")
      + (row.auc_seconds != null ? `, best of 10 lengths at ${fmtNum(row.auc_seconds, 0)} s` : "")
      + (row.auc_n_pain_reports != null ? `, ${row.auc_n_pain_reports} pain reports` : ""));

  return (
    <Card sx={{ p: 2, mb: 2 }}>
      <MDBox display="flex" alignItems="flex-start" justifyContent="space-between" flexWrap="wrap" gap={1}>
        <MDBox display="flex" alignItems="center" gap={1} flexWrap="wrap">
          <MDTypography variant="h6" fontWeight="bold">Choose a band</MDTypography>
          {!grid.cross_setting_stability_included && (
            <Chip size="small" label="stability across settings not yet computed for this grid"
              sx={{ opacity: 0.6 }} />
          )}
        </MDBox>
        {/* Top right, in fine print: the pain score and the matching and split settings this grid
            was built under, and when -- the same entry the Biomarkers page shows for its controls
            (decision 131). */}
        <SettingsFinePrint gs={grid.grid_settings} />
      </MDBox>

      <MDBox display="flex" gap={0.6} flexWrap="wrap" alignItems="center" mt={1} mb={1.25}>
        {leftTabs.map(tab)}
        {leftTabs.length && rightTabs.length ? <span style={{ width: 14 }} /> : null}
        {rightTabs.map(tab)}
        {otherTabs.map(tab)}
      </MDBox>

      {/* The map. r and AUC take the card's width between them (the PI: "make r and AUC bands 2x
          wider; use right-side whitespace"); the symbol and radio columns are fixed. */}
      <MDBox sx={{ display: "grid", gridTemplateColumns: "64px minmax(90px,1fr) minmax(90px,1fr) 84px 84px 72px",
        columnGap: "6px", rowGap: "2px", alignItems: "center", fontSize: 11 }}>
        <MDTypography variant="caption" sx={{ ...HEAD, textAlign: "right" }}>Band<br />centre</MDTypography>
        <MDTypography variant="caption" sx={HEAD}>Correlation r</MDTypography>
        <MDTypography variant="caption" sx={HEAD}>AUC</MDTypography>
        <MDTypography variant="caption" sx={HEAD}>Clears<br />correction</MDTypography>
        <MDTypography variant="caption" sx={HEAD}>Stable across<br />settings</MDTypography>
        <MDTypography variant="caption" sx={HEAD}>Use this<br />band</MDTypography>
        {rows.map((row) => {
          const on = isCommitted(row);
          const id = `cl-band-${String(channel)}-${row.band_center_hz}`;
          return [
            <MDTypography key={`${id}-lab`} variant="caption" component="label" htmlFor={id}
              sx={{ textAlign: "right", fontFamily: PAL.mono, fontSize: 10.5, paddingRight: "4px",
                color: on ? PAL.accent : "#6A6A6A", fontWeight: on ? 700 : 400, cursor: "pointer" }}>
              {`${fmtHz(row.band_center_hz)} Hz`}
            </MDTypography>,
            <div key={`${id}-r`} title={corrTip(row)} style={{ height: CELL_H, borderRadius: 2,
              background: diverging(row.pearson_r, 0, 1), display: "flex", alignItems: "center",
              justifyContent: "center", fontFamily: PAL.mono, fontSize: 10.5,
              color: inkFor(row.pearson_r, 0, 1), outline: on ? `2px solid ${PAL.accent}` : "none",
              outlineOffset: -1 }}>
              {row.pearson_r == null ? "" : fmtNum(row.pearson_r, 2)}
            </div>,
            <div key={`${id}-a`} title={aucTip(row)} style={{ height: CELL_H, borderRadius: 2,
              background: diverging(row.auc, 0.5, 0.5), display: "flex", alignItems: "center",
              justifyContent: "center", fontFamily: PAL.mono, fontSize: 10.5,
              color: inkFor(row.auc, 0.5, 0.5), outline: on ? `2px solid ${PAL.accent}` : "none",
              outlineOffset: -1 }}>
              {row.auc == null ? "" : fmtNum(row.auc, 2)}
            </div>,
            <div key={`${id}-fw`} style={{ textAlign: "center", lineHeight: `${CELL_H}px` }}>
              <FamilyWiseMark significant={row.family_wise_significant_8_to_30hz}
                q={row.family_wise_q_8_to_30hz} />
            </div>,
            <div key={`${id}-st`} style={{ textAlign: "center", lineHeight: `${CELL_H}px` }}>
              <StabilityMark stability={row.cross_setting_stability} />
            </div>,
            <div key={`${id}-use`} style={{ textAlign: "center" }}>
              <input type="radio" id={id} name={`cl-use-band-${participantUid}`} checked={on}
                onChange={() => choose(row)} aria-label={`use the ${fmtHz(row.band_center_hz)} Hz band on ${labelOf(channel)}`}
                style={{ width: 14, height: 14, margin: 0, cursor: "pointer", accentColor: PAL.accent }} />
            </div>,
          ];
        })}
      </MDBox>

      <MDBox display="flex" gap={2} flexWrap="wrap" alignItems="center" mt={1.25}
        sx={{ fontSize: 10.5, color: "#6A6A6A" }}>
        <ScaleBar center={0} half={1} lo="−1" mid="0" hi="+1" />
        <ScaleBar center={0.5} half={0.5} lo="0" mid="0.5" hi="1" />
        <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
          <TickGlyph label="tick" /> clears the correction / behaves the same
        </span>
        <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
          <CrossGlyph label="cross" /> does not clear / behaves differently
        </span>
        <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
          <AmberGlyph label="amber" /> cannot tell
        </span>
        <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
          <NotTestedGlyph label="not tested" /> not tested
        </span>
      </MDBox>

      <MDBox mt={1}>
        <MDButton size="small" variant="text" color="info" onClick={() => setShowHelp((s) => !s)}
          sx={{ textTransform: "none", fontSize: 11, padding: "2px 6px", minHeight: 0 }}>
          {showHelp ? "Hide how to read this" : "How to read this, and what it cannot tell you"}
        </MDButton>
        <Collapse in={showHelp}>
          <MDTypography variant="caption" color="text" display="block" mt={0.5}
            sx={{ fontSize: 11, maxWidth: "80ch" }}>
            Each colour cell is the strongest of ten lengths of signal for that band, so it is
            optimistic by construction; hover a cell for its interval, the length it came from and
            the number of pain reports. Every band is selectable, including one that does not clear
            the 22-centre correction &mdash; the marks are labels, not permissions. The device&apos;s
            own 51-rule check needs a stimulation current, pulse width, rate and impedance reading,
            none of which a band alone carries, so no blocked/allowed mark is shown here: that check
            runs, live, on the band you tick, in the panels below.
          </MDTypography>
        </Collapse>
      </MDBox>
    </Card>
  );
}
