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
 * TWO COLUMNS, ONE PER SIDE (the PI, 2026-10-08): Left and Right side by side, each narrowed, with
 * its own contact-pair tabs and its own "Use" radio, so one band can be chosen on each side for
 * "2 independent controllers". A side the sense-to-control wiring does not read is greyed.
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
import { memo, useMemo, useState } from "react";
import { Card, Tooltip } from "@mui/material";
import MDBox from "components/MDBox";
import MDTypography from "components/MDTypography";

import { TYPE, WRAP, CARD } from "assets/theme/base/tokens";
import { DIVERGING, RANGE } from "assets/theme/base/dataColors";
import ColorKey from "views/Reports/paper/ColorKey";
import { orderContacts } from "views/Reports/Biomarkers/contactOrder";
import PAL, { SIDE } from "./palette";
import Fold from "./Fold";
import { fmtHz, fmtNum } from "./deployFormat";
import { recordChosenBand } from "./bandCandidateStore";

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
    existing.auc_chosen_as_best_of_n_windows = r.chosen_as_best_of_n_windows;
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

// How many lengths of signal the sweep tried, read from the data and never typed here: a row's
// own `chosen_as_best_of_n_windows` first, then the channel's list of delivered lengths. The
// sweep tried ten lengths until decision 170 and nine since, and a typed "10" outlived the change
// on this card (referent audit 2026-09-15, items 1 and 5). The last-resort fallback is the count
// the sweep runs today, used only when a response carries neither field.
const N_LENGTHS_FALLBACK = 9;
const N_LENGTHS_WORDS = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight",
  "nine", "ten", "eleven", "twelve"];

function nLengthsForRow(row, fromAucSide) {
  const own = fromAucSide ? row.auc_chosen_as_best_of_n_windows : row.chosen_as_best_of_n_windows;
  const other = fromAucSide ? row.chosen_as_best_of_n_windows : row.auc_chosen_as_best_of_n_windows;
  const n = own != null ? own : other;
  return n != null && Number.isFinite(Number(n)) ? Number(n) : N_LENGTHS_FALLBACK;
}

function nLengthsForChannel(sweepForChannel, rows) {
  const delivered = sweepForChannel && sweepForChannel.integration_seconds_delivered;
  if (Array.isArray(delivered) && delivered.length > 0) return delivered.length;
  const row = (rows || []).find((r) => r.chosen_as_best_of_n_windows != null
    || r.auc_chosen_as_best_of_n_windows != null);
  return row ? nLengthsForRow(row, row.chosen_as_best_of_n_windows == null) : N_LENGTHS_FALLBACK;
}

/** "nine" for 9, "22" for 22: a word where English has a short one, digits otherwise. */
function countWord(n) {
  return Number.isInteger(n) && n >= 0 && n < N_LENGTHS_WORDS.length ? N_LENGTHS_WORDS[n] : String(n);
}

/**
 * The cell colour on the shared nine-stop diverging scale (SPEC 2026-09-26 section 3.1), over a
 * FIXED range: correlation -0.5 to +0.5, the high-versus-low reading 0.25 to 0.75 around the coin
 * toss. A value beyond the range draws at the end colour; the cell and its hover print the true
 * value, so saturating the colour hides no number.
 */
const hexRgb = (h) => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16));
export function cellRgb(v, lo, hi) {
  if (v == null || !Number.isFinite(Number(v))) return null;
  const t = Math.max(0, Math.min(1, (Number(v) - lo) / (hi - lo)));
  let k = 0;
  while (k < DIVERGING.length - 2 && t > DIVERGING[k + 1][0]) k += 1;
  const [s0, c0] = DIVERGING[k];
  const [s1, c1] = DIVERGING[k + 1];
  const f = s1 > s0 ? (t - s0) / (s1 - s0) : 0;
  const a = hexRgb(c0);
  const b = hexRgb(c1);
  return a.map((x, i) => Math.round(x + f * (b[i] - x)));
}
const cellFill = (v, lo, hi) => {
  const rgb = cellRgb(v, lo, hi);
  return rgb ? `rgb(${rgb.join(", ")})` : PAL.fillMuted;
};
const [R_LO, R_HI] = RANGE.correlation;
const [A_LO, A_HI] = RANGE.areaUnderCurve;

/** Near-black on a pale cell, white on a saturated one, so the value reads on every fill. */
function inkFor(v, lo, hi) {
  const rgb = cellRgb(v, lo, hi);
  if (!rgb) return PAL.ink3;   // the placeholder where a cell has no value: text, so legible (2026-09-24)
  const luminance = (0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2]) / 255;
  return luminance > 0.55 ? PAL.ink : PAL.onFill;
}

/** "q 0.002 (fdr 22 bands)": the number the server sends (`family_wise_q_8_to_30hz`) is a
 *  Benjamini-Hochberg q, not a p -- the PI, 2026-09-26: printing it as "p" is a mislabel; 2026-09-27:
 *  shortened to the "fdr" shorthand. Exported for its own test. */
export const allowanceWords = (q, n = 22) => (q != null ? `q ${fmtNum(q, 3)} (fdr ${n} bands)` : null);

/** A mark drawn by SHAPE only, in the ink (SPEC section 3.2): no green, no red. */
function ShapeMark({ glyph, label }) {
  return (
    <span role="img" aria-label={label} style={{ ...TYPE.body, color: PAL.ink, fontWeight: 600 }}>{glyph}</span>
  );
}

function FamilyWiseMark({ significant, q }) {
  const words = allowanceWords(q);
  if (significant == null) {
    return (
      <Tooltip title="the allowance for testing 22 bands at once has not been computed for this row">
        <span><ShapeMark glyph="○" label="allowance not assessed" /></span>
      </Tooltip>
    );
  }
  return (
    <Tooltip title={significant
      ? `still clear after allowing for the 22 bands tested${words ? `: ${words}` : ""}`
      : `not clear after allowing for the 22 bands tested${words ? `: ${words}` : ""}; still selectable; this is a label, not a check that can refuse`}>
      <span>{significant ? <ShapeMark glyph="✓" label="still clear after allowing for 22 bands" />
        : <ShapeMark glyph="–" label="not clear after allowing for 22 bands" />}</span>
    </Tooltip>
  );
}

function StabilityMark({ stability }) {
  const answer = (stability && stability.answer) || "not tested";
  const reason = (stability && stability.reason) || "";
  const tip = stability
    ? `${answer}${reason ? `: ${reason}` : ""}`
    : "whether the band behaves the same at every setting has not been computed for this band yet";
  let glyph;
  if (answer === "behaves the same") glyph = <ShapeMark glyph="✓" label="behaves the same at every setting" />;
  else if (answer === "behaves differently") glyph = <ShapeMark glyph="✕" label="behaves differently across settings" />;
  else if (answer === "cannot tell") glyph = <ShapeMark glyph="?" label="cannot tell" />;
  else glyph = <ShapeMark glyph="○" label="not tested" />;
  return <Tooltip title={tip}><span>{glyph}</span></Tooltip>;
}

const DIRECTION_TEXT = { pro_first: "each report picks its nearest recordings",
  prior: "each recording picks the next report after it", nearest: "each recording picks its nearest report" };
export function gridSettingsLine(gs) {
  if (!gs) return null;
  const parts = [];
  parts.push(gs.metric_label || gs.sweep_metric || "pain score ?");
  parts.push(gs.match_tolerance_min != null ? `\u00b1${fmtNum(gs.match_tolerance_min, 0)} min window`
    : "same-day match");
  parts.push(DIRECTION_TEXT[gs.match_direction] || `${gs.match_direction || "?"} match`);
  if (gs.allow_window_reuse) parts.push("one stretch of recording may answer more than one report");
  if (gs.include_clinic_sheet_ratings) parts.push("clinic-sheet ratings included");
  const lo = gs.percentile_low != null ? fmtNum(gs.percentile_low, 0) : "?";
  const hi = gs.percentile_high != null ? fmtNum(gs.percentile_high, 0) : "?";
  const split = { tertile: `lowest and highest thirds of ratings (${lo}/${hi} %), the middle third left out`,
    percentile: `ratings below ${lo} % and above ${hi} %, the middle left out`,
    median: "ratings split at the median", kmeans: "ratings split into two clusters (older rule)",
    cutoff: "ratings split at a fixed cut-off" };
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
/** The grid's settings in a few words (2026-10-02, minimalist: the long form stays in the signed
 *  record, `gridSettingsLine`). The build time is in the hover. */
export function gridSettingsShort(gs) {
  if (!gs) return null;
  const lo = gs.percentile_low != null ? fmtNum(gs.percentile_low, 0) : "?";
  const hi = gs.percentile_high != null ? fmtNum(gs.percentile_high, 0) : "?";
  const dir = { pro_first: "report picks nearest", prior: "next report", nearest: "nearest" };
  const split = { tertile: `tertile ${lo}/${hi}%`, percentile: `split ${lo}/${hi}%`, median: "median split",
    kmeans: "2-cluster split", cutoff: "fixed cut-off" };
  const parts = [gs.metric_label || gs.sweep_metric || "pain score ?",
    gs.match_tolerance_min != null ? `\u00b1${fmtNum(gs.match_tolerance_min, 0)} min` : "same day",
    dir[gs.match_direction] || `${gs.match_direction || "?"}`];
  if (gs.allow_window_reuse) parts.push("reuse");
  if (gs.include_clinic_sheet_ratings) parts.push("clinic sheets in");
  parts.push(split[gs.label_strategy] || `${gs.label_strategy || "?"} split`);
  return parts.join(" \u00b7 ");
}
function SettingsFinePrint({ gs }) {
  const line = gridSettingsShort(gs);
  if (!line) return null;
  const built = gridBuiltText(gs);
  return (
    <MDTypography title={built || undefined} sx={{ ...TYPE.body, color: PAL.ink2, maxWidth: "68ch", mt: 1 }}>
      {`Grid now: ${line}`}
    </MDTypography>
  );
}

/**
 * Which pairs the device refuses today, READ from the grid response's `sensing_rule` block when the
 * server sends one (decisions 217, 305: `by_side[side].allowed_channel`). Nothing is worked out
 * here: with no block, no pair is marked and the tabs keep their usual order.
 */
export function refusedByRule(channels, sweeps, rule, sideOf) {
  const bySide = rule && rule.by_side;
  const refused = {};
  if (!bySide) return refused;
  channels.forEach((ch) => {
    const r = bySide[sideOf(ch)];
    if (r && r.rule_applied && r.allowed_channel !== ch) {
      refused[ch] = `refused today: ${r.why || "the device senses only on the pair flanking the stimulating contact"}`
        + `${r.allowed_display ? `, so this lead senses on ${r.allowed_display} only` : ""}`;
    }
  });
  return refused;
}

/** Column headings: 12 px, sentence case, grey, on the muted band (SPEC section 4 rule 5). */
const HEAD = { ...TYPE.caption, fontWeight: 600, color: PAL.ink3, backgroundColor: PAL.fillMuted,
  textAlign: "center", padding: "4px 4px", alignSelf: "stretch", display: "flex",
  alignItems: "flex-end", justifyContent: "center" };
const CELL_H = 22;

/** Every band centre on one contact's grid, ascending (the rows a reader can tick). */
export function gridCentres(grid, channel) {
  const sw = ((grid && grid.band_time_sweep) || {})[channel] || {};
  return mergedRows(sw).map((r) => Number(r.band_center_hz)).filter(Number.isFinite)
    .sort((a, b) => a - b);
}

/**
 * THE BAND A GRID ROW RECORDS when ticked, in one place (decision 425): the tick writes it, and the
 * neighbour pre-compute builds the same record for the bands either side, so the requests it sends
 * are exactly the ones a tick would send and the server's saved answers match.
 */
export function bandRecordFromGrid(grid, channel, centreHz) {
  const s = ((grid && grid.band_time_sweep) || {})[channel] || {};
  const hemisphere = s.display_hemisphere
    || (/LEFT/i.test(channel) ? "Left" : (/RIGHT/i.test(channel) ? "Right" : null));
  return {
    contact: channel,
    contact_label: s.display_short || String(channel || "").replace(/_/g, " "),
    center_freq_hz: centreHz,
    bandwidth_hz: Number(s.band_width_hz || 5.0),
    hemisphere,
    threshold_mode: "dual",
    schema_version: "bandcandidate_v1",
    label: {},
    grid_settings: (grid && grid.grid_settings) || null,
  };
}

const SIDES = ["Left", "Right"];
const SIDE_INK = { Left: SIDE.left, Right: SIDE.right };

/**
 * The band chosen on each side, as `{ Left, Right }` of `{ contact, centerHz }` or null. Taken from
 * `committedBySide` when the page passes it, and the page's own band always counts for its side.
 */
export function chosenBySide(committed, committedBySide, sideOf) {
  const out = { Left: null, Right: null };
  SIDES.forEach((s) => {
    const c = committedBySide && committedBySide[s];
    if (c && c.contact) out[s] = c;
  });
  const side = committed && committed.contact ? sideOf(committed.contact) : null;
  if (side && out[side] == null) out[side] = committed;
  return out;
}

/**
 * The page's answer line for Band selection: the band on each side, and which band the sections
 * below the decision describe when there are two.
 */
export function bandSelectionAnswer(bySide, committed, labelOf, activeSides) {
  const say = (c) => `${labelOf(c.contact)} at ${fmtHz(c.centerHz)} Hz`;
  const used = activeSides || SIDES;
  if (!SIDES.some((s) => bySide[s])) {
    return "No band chosen yet: tick one to check it against the device and the evidence below.";
  }
  const parts = used.map((s) => `${s}: ${bySide[s] ? say(bySide[s]) : "none chosen"}`);
  const both = bySide.Left && bySide.Right;
  return `${parts.join(" · ")}.`
    + (both && committed && committed.contact
      ? ` The sections below the decision describe ${say(committed)}, the band ticked last.` : "");
}

/**
 * ONE SIDE'S COLUMN (the PI, 2026-10-08: "horizontally compressed ... one on the left and one on the
 * right"): that side's contact-pair tabs, then the band centres down the side with r, AUC, the two
 * marks and a "Use" radio. A side the wiring does not read is greyed and cannot be ticked.
 */
function SideColumn({ side, channels, sweeps, refused, chosen, active, offNote, labelOf, regionOf,
  participantUid, onChoose }) {
  const [activeChannel, setActiveChannel] = useState(null);
  const allowed = channels.filter((ch) => !refused[ch]);
  const tabOrder = [...allowed, ...channels.filter((ch) => refused[ch])];
  const channel = (activeChannel && channels.includes(activeChannel)) ? activeChannel
    : (chosen && channels.includes(chosen.contact)) ? chosen.contact
      : (allowed[0] || channels[0]);
  const sw = sweeps[channel] || {};
  const rows = mergedRows(sw);
  const isChosen = (row) => !!(active && chosen && chosen.contact === channel && chosen.centerHz != null
    && Math.abs(Number(chosen.centerHz) - row.band_center_hz) < 1e-6);

  const corrTip = (row) => (row.pearson_r == null ? "no correlation for this band"
    : `correlation with pain ${fmtNum(row.pearson_r, 3)}`
      + (row.pearson_r_low != null && row.pearson_r_high != null
        ? ` (95% range ${fmtNum(row.pearson_r_low, 3)} to ${fmtNum(row.pearson_r_high, 3)})` : "")
      + (row.integration_seconds_delivered != null
        ? `, best of ${nLengthsForRow(row, false)} lengths at ${fmtNum(row.integration_seconds_delivered, 0)} s` : "")
      + (row.n_pain_reports != null ? `, ${row.n_pain_reports} pain reports` : ""));
  const aucTip = (row) => (row.auc == null ? "no high-versus-low reading for this band"
    : `tells high pain from low: ${fmtNum(row.auc, 3)} (0.5 = coin toss, 1 = perfect)`
      + (row.auc_low != null && row.auc_high != null
        ? `, 95% range ${fmtNum(row.auc_low, 3)} to ${fmtNum(row.auc_high, 3)}` : "")
      + (row.auc_seconds != null ? `, best of ${nLengthsForRow(row, true)} lengths at ${fmtNum(row.auc_seconds, 0)} s` : "")
      + (row.auc_n_pain_reports != null ? `, ${row.auc_n_pain_reports} pain reports` : ""));

  const tab = (ch, i) => {
    const on = ch === channel;
    const no = !!refused[ch];
    return (
      <button key={ch} type="button" onClick={() => setActiveChannel(ch)} disabled={!active}
        title={[regionOf(ch), refused[ch]].filter(Boolean).join("; ") || undefined}
        aria-label={regionOf(ch) ? `${labelOf(ch)}, ${regionOf(ch)}` : labelOf(ch)}
        aria-pressed={on}
        style={{ ...TYPE.body, fontFamily: "inherit", cursor: active ? "pointer" : "default",
          padding: "4px 8px", minHeight: 32, border: `1px solid ${on ? PAL.accent : PAL.rule}`,
          marginLeft: i === 0 ? 0 : -1, position: "relative", zIndex: on ? 1 : 0,
          borderRadius: i === 0 ? "4px 0 0 4px" : (i === tabOrder.length - 1 ? "0 4px 4px 0" : 0),
          backgroundColor: on ? PAL.accentFill : (no ? PAL.fillMuted : PAL.surface),
          color: on ? PAL.accent : (no ? PAL.ink3 : PAL.ink), fontWeight: on ? 600 : 400,
          whiteSpace: "nowrap" }}>
        {no ? <span aria-hidden="true" style={{ marginRight: 4 }}>✕</span> : null}
        {labelOf(ch)}
      </button>
    );
  };

  return (
    <MDBox data-testid={`band-side-${side}`} aria-disabled={!active}
      sx={{ border: `1px solid ${PAL.rule}`, borderRadius: "4px", p: 1.5, minWidth: 0,
        opacity: active ? 1 : 0.45 }}>
      <MDBox display="flex" justifyContent="space-between" alignItems="baseline" gap={1} flexWrap="wrap">
        <MDTypography component="h3" sx={{ ...TYPE.body, fontWeight: 600, color: PAL.ink }}>
          <span aria-hidden="true"
            style={{ display: "inline-block", width: 10, height: 10, borderRadius: "50%", background: SIDE_INK[side], marginRight: 6 }} />
          {`${side} sensing`}
        </MDTypography>
        {active && chosen ? (
          <MDTypography data-testid={`band-side-${side}-chosen`}
            sx={{ ...TYPE.body, fontWeight: 600, color: PAL.accent }}>
            {`Chosen: ${labelOf(chosen.contact)} at ${fmtHz(chosen.centerHz)} Hz`}
          </MDTypography>
        ) : null}
      </MDBox>
      {channels.length ? (
        <MDBox display="flex" flexWrap="wrap" mt={1} mb={1} role="group"
          aria-label={`${side} sensing contact pair`}>
          {tabOrder.map(tab)}
        </MDBox>
      ) : (
        <MDTypography sx={{ ...TYPE.body, color: PAL.ink3, mt: 1 }}>No recordings on this side.</MDTypography>
      )}
      {refused[channel] ? (
        <MDTypography sx={{ ...TYPE.body, color: PAL.failText, mb: 1 }}>
          <span aria-hidden="true" style={{ marginRight: 6 }}>✕</span>
          {`${labelOf(channel)}: ${refused[channel]}.`}
        </MDTypography>
      ) : null}
      {channels.length ? (
        <MDBox sx={{ display: "grid",
          gridTemplateColumns: "60px minmax(44px,1fr) minmax(44px,1fr) 40px 40px 36px",
          columnGap: "4px", rowGap: "2px", alignItems: "center", overflowX: "auto" }}>
          <MDTypography variant="caption" sx={{ ...HEAD, justifyContent: "flex-end" }}>Hz</MDTypography>
          <MDTypography variant="caption" title="correlation with pain" sx={HEAD}>r</MDTypography>
          <MDTypography variant="caption" sx={HEAD}>AUC</MDTypography>
          <MDTypography variant="caption" title="corrected for the 22 bands tested" sx={HEAD}>Corr.</MDTypography>
          <MDTypography variant="caption" title="same at every setting" sx={HEAD}>Same</MDTypography>
          <MDTypography variant="caption" title="use this band" sx={HEAD}>Use</MDTypography>
          {rows.map((row) => {
            const on = isChosen(row);
            const id = `cl-band-${String(channel)}-${row.band_center_hz}`;
            const ring = on ? `2px solid ${PAL.accent}` : "none";
            return [
              <MDTypography key={`${id}-lab`} variant="caption" component="label" htmlFor={id}
                sx={{ ...TYPE.body, textAlign: "right", paddingRight: "4px",
                  color: on ? PAL.accent : PAL.ink2, fontWeight: on ? 600 : 400,
                  cursor: active ? "pointer" : "default" }}>
                {fmtHz(row.band_center_hz)}
              </MDTypography>,
              <div key={`${id}-r`} title={corrTip(row)} style={{ height: CELL_H, borderRadius: 2,
                background: cellFill(row.pearson_r, R_LO, R_HI), display: "flex", alignItems: "center",
                justifyContent: "center", fontSize: PAL.fs.body,
                color: inkFor(row.pearson_r, R_LO, R_HI), outline: ring, outlineOffset: -1 }}>
                {row.pearson_r == null ? "" : fmtNum(row.pearson_r, 2)}
              </div>,
              <div key={`${id}-a`} title={aucTip(row)} style={{ height: CELL_H, borderRadius: 2,
                background: cellFill(row.auc, A_LO, A_HI), display: "flex", alignItems: "center",
                justifyContent: "center", fontSize: PAL.fs.body,
                color: inkFor(row.auc, A_LO, A_HI), outline: ring, outlineOffset: -1 }}>
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
                <input type="radio" id={id} name={`cl-use-band-${participantUid}-${side}`} checked={on}
                  disabled={!active} onChange={() => onChoose(channel, row)}
                  aria-label={`use the ${fmtHz(row.band_center_hz)} Hz band on ${labelOf(channel)}`}
                  style={{ width: 16, height: 16, margin: 0, cursor: active ? "pointer" : "default",
                    accentColor: PAL.accent }} />
              </div>,
            ];
          })}
        </MDBox>
      ) : null}
      {!active && offNote ? (
        <MDTypography data-testid={`band-side-${side}-off`} sx={{ ...TYPE.body, color: PAL.ink3, mt: 1 }}>
          {offNote}
        </MDTypography>
      ) : null}
    </MDBox>
  );
}

/**
 * Props: `committed` (the page's band, `{ contact, centerHz }`), `committedBySide` (`{ Left, Right }`,
 * the band chosen on each side), `activeSides` (the sides the wiring reads; null for both) and
 * `offNote` (why a side not read is greyed), plus the grid and the two callbacks.
 */
function BandSweepGridPanel({ grid, participantUid, committed, committedBySide, activeSides,
  offNote, onCandidateChosen, onChoiceRecorded }) {
  // Memoised, because a fresh `{}` on every render (when there is no grid yet) would make every
  // memo below it recompute on every render.
  const sweeps = useMemo(() => (grid && grid.band_time_sweep) || {}, [grid]);
  const channels = useMemo(() => orderContacts(sweeps), [sweeps]);

  if (!grid || grid.available === false) {
    return (
      <Card sx={{ ...CARD, p: 3 }}>
        <MDTypography component="h2" sx={{ ...TYPE.title, ...WRAP.balance, color: PAL.ink }}>Band selection</MDTypography>
        <MDTypography sx={{ ...TYPE.lead, color: PAL.ink, mt: 1 }}>
          {(grid && grid.reason) || "no calibrated grid is available for this participant yet."}
          {" "}Open the Biomarkers page first, then return here.
        </MDTypography>
        <SettingsFinePrint gs={grid && grid.grid_settings} />
      </Card>
    );
  }

  const sideOf = (ch) => {
    const s = sweeps[ch] || {};
    return s.display_hemisphere || (/LEFT/i.test(ch) ? "Left" : (/RIGHT/i.test(ch) ? "Right" : null));
  };
  const labelOf = (ch) => {
    const s = sweeps[ch] || {};
    return s.display_short || String(ch || "").replace(/_/g, " ");
  };
  const regionOf = (ch) => (sweeps[ch] && sweeps[ch].display_region) || null;
  const refused = refusedByRule(channels, sweeps, grid && grid.sensing_rule, sideOf);
  const bySide = chosenBySide(committed, committedBySide, sideOf);
  const active = (s) => !activeSides || activeSides.includes(s);

  const choose = (channel, row) => {
    const hemisphere = sideOf(channel);
    // Written to this browser at once (so the page moves on the click) and recorded on the server
    // (the PI's ruling 8); the promise reports whether the server took it. `grid_settings` is the
    // server's own tag of the grid the band was picked from, carried so the sign-off sheet can say
    // which grid that was (panel D item 8). The record is `bandRecordFromGrid`'s, the one the
    // neighbour pre-compute builds too (decision 425). The band ticked becomes the page's band and
    // the band of its side (one band per side, the PI, 2026-10-08).
    const recorded = recordChosenBand(participantUid,
      bandRecordFromGrid(grid, channel, row.band_center_hz), "grid");
    if (onChoiceRecorded) recorded.then(onChoiceRecorded);
    if (onCandidateChosen) {
      onCandidateChosen({ channel, centerHz: row.band_center_hz,
        bandWidthHz: Number((sweeps[channel] || {}).band_width_hz || 5.0), sensingHemisphere: hemisphere });
    }
  };

  const anySweep = channels.length ? sweeps[channels[0]] : {};
  const answer = bandSelectionAnswer(bySide, committed, labelOf, activeSides);

  return (
    <Card sx={{ ...CARD, p: 3 }}>
      <MDTypography component="h2" sx={{ ...TYPE.title, ...WRAP.balance, color: PAL.ink }}>Band selection</MDTypography>
      <MDTypography data-testid="band-selection-answer" sx={{ ...TYPE.lead, color: PAL.ink, mt: 1, maxWidth: "68ch" }}>
        {answer}
      </MDTypography>
      {!grid.cross_setting_stability_included ? (
        <MDTypography sx={{ ...TYPE.body, color: PAL.warnText, mt: 1 }}>
          <span aria-hidden="true" style={{ marginRight: 6 }}>▲</span>
          Per-setting consistency not computed yet.
        </MDTypography>
      ) : null}
      {/* The pain score and the matching and split settings this grid was built under, and when --
          the same entry the Biomarkers page shows for its controls (decision 131). */}
      <SettingsFinePrint gs={grid.grid_settings} />

      <MDBox display="flex" gap={4} flexWrap="wrap" mt={2} mb={2}>
        <ColorKey scale={DIVERGING} range={RANGE.correlation} title="r: correlation with pain"
          lowLabel="falls with pain" midLabel="0 no relationship" highLabel="rises with pain" width={240} />
        <ColorKey scale={DIVERGING} range={RANGE.areaUnderCurve} title="AUC"
          lowLabel="pain lower when power high" midLabel="0.5 no relationship"
          highLabel="pain higher when power high" width={240} />
      </MDBox>

      {/* The two sides side by side, stacked when the page is narrow. */}
      <MDBox sx={{ display: "grid", gridTemplateColumns: { xs: "minmax(0,1fr)", md: "repeat(2, minmax(0,1fr))" },
        gap: 2.5 }}>
        {SIDES.map((side) => (
          <SideColumn key={side} side={side} channels={channels.filter((ch) => sideOf(ch) === side)}
            sweeps={sweeps} refused={refused} chosen={bySide[side]} active={active(side)}
            offNote={offNote} labelOf={labelOf} regionOf={regionOf}
            participantUid={participantUid} onChoose={choose} />
        ))}
      </MDBox>

      <MDTypography sx={{ ...TYPE.body, color: PAL.ink2, mt: 2 }}>
        {"Corr.: corrected for 22 bands · Same: same at every setting · ✓ passes · – fails "
          + "correction · ✕ differs across settings · ? unknown · ○ not tested"}
      </MDTypography>

      <Fold show="Reading guide, limits" hide="Hide how to read this" mt={2}>
        <MDTypography sx={{ ...TYPE.body, color: PAL.ink2, maxWidth: "68ch" }}>
          Each colour cell is the strongest of {countWord(nLengthsForChannel(anySweep || {}, mergedRows(anySweep || {})))} lengths of signal for that band, so
          optimistic by construction; hover for its 95% range, length and number of reports. Colours
          stop at ±0.5 (correlation) and 0.25/0.75 (AUC); stronger values draw at the end colour and
          print their true number. Every band is selectable, including those failing the 22-band
          correction: marks are labels, not refusals. One band can be chosen on each side; the
          sense-to-control wiring above decides which side drives which stimulator, and a side it
          does not read is greyed. The device rule check needs current, pulse width, rate and
          impedance, which a band alone lacks, so no allowed or refused mark is shown here; it runs
          on the bands you tick, in the deployment decision above.
        </MDTypography>
      </Fold>
    </Card>
  );
}

// Rebuilt only when one of its inputs changes (speed-up item C6, 2026-10-02). The page re-renders on
// every answer and cache event while it loads, and this grid of 22 rows of coloured cells was
// rebuilt each time with the same inputs; the page now hands it the same objects between changes.
export default memo(BandSweepGridPanel);
