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
import { memo, useMemo, useState } from "react";
import { Card, Tooltip } from "@mui/material";
import MDBox from "components/MDBox";
import MDTypography from "components/MDTypography";

import { TYPE, WRAP, CARD } from "assets/theme/base/tokens";
import { DIVERGING, RANGE } from "assets/theme/base/dataColors";
import ColorKey from "views/Reports/paper/ColorKey";
import { orderContacts } from "views/Reports/Biomarkers/contactOrder";
import PAL from "./palette";
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
      {`Grid: ${line}`}
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

function BandSweepGridPanel({ grid, participantUid, committed, onCandidateChosen,
  onChoiceRecorded }) {
  // Memoised, because a fresh `{}` on every render (when there is no grid yet) would make every
  // memo below it recompute on every render.
  const sweeps = useMemo(() => (grid && grid.band_time_sweep) || {}, [grid]);
  const channels = useMemo(() => orderContacts(sweeps), [sweeps]);
  const [activeChannel, setActiveChannel] = useState(null);
  // Open on the committed band's contact when there is one, so the tick is visible on arrival.
  const channel = (activeChannel && channels.includes(activeChannel)) ? activeChannel
    : (committed && committed.contact && channels.includes(committed.contact)) ? committed.contact
      : channels[0];

  if (!grid || grid.available === false) {
    return (
      <Card sx={{ ...CARD, p: 3 }}>
        <MDTypography component="h2" sx={{ ...TYPE.title, ...WRAP.balance, color: PAL.ink }}>Which band?</MDTypography>
        <MDTypography sx={{ ...TYPE.lead, color: PAL.ink, mt: 1 }}>
          {(grid && grid.reason) || "no calibrated grid is available for this participant yet."}
          {" "}Open the Biomarkers page first, then return here.
        </MDTypography>
        <SettingsFinePrint gs={grid && grid.grid_settings} />
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
    // Written to this browser at once (so the page moves on the click) and recorded on the server
    // (the PI's ruling 8); the promise reports whether the server took it. `grid_settings` is the
    // server's own tag of the grid the band was picked from, carried so the sign-off sheet can say
    // which grid that was (panel D item 8). It reaches no request: the report is built from named
    // fields of the band, never from the band object whole.
    const recorded = recordChosenBand(participantUid, {
      contact: channel,
      contact_label: labelOf(channel),
      center_freq_hz: row.band_center_hz,
      bandwidth_hz: bandWidthHz,
      hemisphere,
      threshold_mode: "dual",
      schema_version: "bandcandidate_v1",
      label: {},
      grid_settings: (grid && grid.grid_settings) || null,
    }, "grid");
    if (onChoiceRecorded) recorded.then(onChoiceRecorded);
    if (onCandidateChosen) {
      onCandidateChosen({ channel, centerHz: row.band_center_hz, bandWidthHz,
        sensingHemisphere: hemisphere });
    }
  };

  // The tabs as one segmented control: the pairs the device allows today first, then the others,
  // greyed, each saying why it is refused; left before right within each group, the same order as
  // the Biomarkers thumbnails. Each tab's accessible name is its pair AND its region (decision 307):
  // the region alone read "Left GPi" three times and "Right VIM" three times to a screen reader.
  const refused = refusedByRule(channels, sweeps, grid && grid.sensing_rule, sideOf);
  const bySideOrder = (list) => [...list.filter((ch) => sideOf(ch) === "Left"),
    ...list.filter((ch) => sideOf(ch) === "Right"),
    ...list.filter((ch) => sideOf(ch) !== "Left" && sideOf(ch) !== "Right")];
  const tabOrder = [...bySideOrder(channels.filter((ch) => !refused[ch])),
    ...bySideOrder(channels.filter((ch) => refused[ch]))];
  const regionOf = (ch) => (sweeps[ch] && sweeps[ch].display_region) || null;
  const tab = (ch, i) => {
    const on = ch === channel;
    const no = !!refused[ch];
    return (
      <button key={ch} type="button" onClick={() => setActiveChannel(ch)}
        title={[regionOf(ch), refused[ch]].filter(Boolean).join("; ") || undefined}
        aria-label={regionOf(ch) ? `${labelOf(ch)}, ${regionOf(ch)}` : labelOf(ch)}
        aria-pressed={on}
        style={{ ...TYPE.body, fontFamily: "inherit", cursor: "pointer", padding: "6px 12px",
          minHeight: 36, border: `1px solid ${on ? PAL.accent : PAL.rule}`,
          marginLeft: i === 0 ? 0 : -1, position: "relative", zIndex: on ? 1 : 0,
          borderRadius: i === 0 ? "4px 0 0 4px" : (i === tabOrder.length - 1 ? "0 4px 4px 0" : 0),
          backgroundColor: on ? PAL.accentFill : (no ? PAL.fillMuted : PAL.surface),
          color: on ? PAL.accent : (no ? PAL.ink3 : PAL.ink), fontWeight: on ? 600 : 400 }}>
        {no ? <span aria-hidden="true" style={{ marginRight: 4 }}>✕</span> : null}
        {labelOf(ch)}
      </button>
    );
  };

  const corrTip = (row) => (row.pearson_r == null ? "no correlation for this band"
    : `correlation ${fmtNum(row.pearson_r, 3)}`
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

  const chosenRow = rows.find((r) => isCommitted(r));
  const answer = chosenRow
    ? `Chosen: ${labelOf(channel)} at ${fmtHz(chosenRow.band_center_hz)} Hz. Every section below is about this band.`
    : (committed && committed.contact
      ? `The chosen band is on another pair; open its tab to see it, or tick a band here to choose again.`
      : "No band chosen yet: tick one to check it against the device and the evidence below.");

  return (
    <Card sx={{ ...CARD, p: 3 }}>
      <MDTypography component="h2" sx={{ ...TYPE.title, ...WRAP.balance, color: PAL.ink }}>Which band?</MDTypography>
      <MDTypography sx={{ ...TYPE.lead, color: PAL.ink, mt: 1, maxWidth: "68ch" }}>{answer}</MDTypography>
      {!grid.cross_setting_stability_included ? (
        <MDTypography sx={{ ...TYPE.body, color: PAL.warnText, mt: 1 }}>
          <span aria-hidden="true" style={{ marginRight: 6 }}>▲</span>
          Per-setting consistency not computed yet.
        </MDTypography>
      ) : null}
      {/* The pain score and the matching and split settings this grid was built under, and when --
          the same entry the Biomarkers page shows for its controls (decision 131). */}
      <SettingsFinePrint gs={grid.grid_settings} />

      <MDBox display="flex" flexWrap="wrap" alignItems="center" mt={2} mb={2} role="group"
        aria-label="Sensing contact pair">
        {tabOrder.map(tab)}
      </MDBox>
      {refused[channel] ? (
        <MDTypography sx={{ ...TYPE.body, color: PAL.failText, mb: 2 }}>
          <span aria-hidden="true" style={{ marginRight: 6 }}>✕</span>
          {`${labelOf(channel)}: ${refused[channel]}.`}
        </MDTypography>
      ) : null}

      <MDBox display="flex" gap={4} flexWrap="wrap" mb={2}>
        <ColorKey scale={DIVERGING} range={RANGE.correlation} title="Correlation with pain"
          lowLabel="falls with pain" midLabel="0 no relationship" highLabel="rises with pain" width={300} />
        <ColorKey scale={DIVERGING} range={RANGE.areaUnderCurve} title="AUC"
          lowLabel="pain lower when power high" midLabel="0.5 no relationship"
          highLabel="pain higher when power high" width={300} />
      </MDBox>

      {/* The map. The two colour columns take the card's width between them; the mark and radio
          columns are fixed. */}
      <MDBox sx={{ display: "grid", gridTemplateColumns: "72px minmax(90px,1fr) minmax(90px,1fr) 96px 96px 64px",
        columnGap: "8px", rowGap: "4px", alignItems: "center", overflowX: "auto" }}>
        <MDTypography variant="caption" sx={{ ...HEAD, justifyContent: "flex-end" }}>Band centre</MDTypography>
        <MDTypography variant="caption" sx={HEAD}>Correlation with pain</MDTypography>
        <MDTypography variant="caption" sx={HEAD}>AUC</MDTypography>
        <MDTypography variant="caption" sx={HEAD}>Corrected, 22 bands</MDTypography>
        <MDTypography variant="caption" sx={HEAD}>Same at every setting</MDTypography>
        <MDTypography variant="caption" sx={HEAD}>Use this band</MDTypography>
        {rows.map((row) => {
          const on = isCommitted(row);
          const id = `cl-band-${String(channel)}-${row.band_center_hz}`;
          const ring = on ? `2px solid ${PAL.accent}` : "none";
          return [
            <MDTypography key={`${id}-lab`} variant="caption" component="label" htmlFor={id}
              sx={{ ...TYPE.caption, textAlign: "right", paddingRight: "4px",
                color: on ? PAL.accent : PAL.ink2, fontWeight: on ? 600 : 400, cursor: "pointer" }}>
              {`${fmtHz(row.band_center_hz)} Hz`}
            </MDTypography>,
            <div key={`${id}-r`} title={corrTip(row)} style={{ height: CELL_H, borderRadius: 2,
              background: cellFill(row.pearson_r, R_LO, R_HI), display: "flex", alignItems: "center",
              justifyContent: "center", fontSize: PAL.fs.caption,
              color: inkFor(row.pearson_r, R_LO, R_HI), outline: ring, outlineOffset: -1 }}>
              {row.pearson_r == null ? "" : fmtNum(row.pearson_r, 2)}
            </div>,
            <div key={`${id}-a`} title={aucTip(row)} style={{ height: CELL_H, borderRadius: 2,
              background: cellFill(row.auc, A_LO, A_HI), display: "flex", alignItems: "center",
              justifyContent: "center", fontSize: PAL.fs.caption,
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
              <input type="radio" id={id} name={`cl-use-band-${participantUid}`} checked={on}
                onChange={() => choose(row)} aria-label={`use the ${fmtHz(row.band_center_hz)} Hz band on ${labelOf(channel)}`}
                style={{ width: 16, height: 16, margin: 0, cursor: "pointer", accentColor: PAL.accent }} />
            </div>,
          ];
        })}
      </MDBox>

      <MDTypography sx={{ ...TYPE.body, color: PAL.ink2, mt: 2 }}>
        {"✓ passes (corrected, or same at every setting) · – fails correction · ✕ differs across "
          + "settings · ? unknown · ○ not tested"}
      </MDTypography>

      <Fold show="How to read this, and what it cannot tell you" hide="Hide how to read this" mt={2}>
        <MDTypography sx={{ ...TYPE.body, color: PAL.ink2, maxWidth: "68ch" }}>
          Each colour cell is the strongest of {countWord(nLengthsForChannel(sw, rows))} lengths of signal for that band, so it is
          optimistic by construction; hover a cell for its 95% range, the length it came from and
          the number of pain reports. The colours stop at ±0.5 for the correlation and at 0.25 and
          0.75 for telling high pain from low; a stronger value draws at the end colour and prints
          its true number. Every band is selectable, including one that is not clear after allowing
          for the 22 bands tested: the marks are labels, not checks that can refuse. The device&apos;s
          own rule check needs a stimulation current, pulse width, rate and impedance reading,
          none of which a band alone carries, so no refused or allowed mark is shown on a band here:
          that check runs, live, on the band you tick, in the sections below.
        </MDTypography>
      </Fold>
    </Card>
  );
}

// Rebuilt only when one of its inputs changes (speed-up item C6, 2026-10-02). The page re-renders on
// every answer and cache event while it loads, and this grid of 22 rows of coloured cells was
// rebuilt each time with the same inputs; the page now hands it the same objects between changes.
export default memo(BandSweepGridPanel);
