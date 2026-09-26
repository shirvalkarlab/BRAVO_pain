/**
 * The block-of-time mark: a small dagger beside every current the page recommends whose fitted
 * pain map "moves between blocks of time", and one note per card saying what that means (the PI,
 * 2026-09-25, answer 4 of the revised plan: show decision 253's warning next to every recommended
 * current; "Format elegantly (e.g., asterisks); label exists elsewhere"). A dagger, not an
 * asterisk, because the current map already draws a star on the best cell and the two would read
 * as one symbol.
 *
 * WHAT IT READS, NOTHING RECOMPUTED. Every fitted (pulse-width pair, rate) row the server returns
 * carries decision 253's check as `calibration.diagnosis.verdict` (`stage1_openloop.calibration_
 * diagnosis`, attached to the row in `bravo_service._attach_rate_stratum_surfaces`). The check's own
 * label is the verdict string itself, used here as it arrives. A current recommended on the
 * decision strip is read from the row at the chosen rate and the chosen pulse-width PAIR
 * (`stage1_openloop`: the current comes from that rate's own surface, `rs_chosen`), which is the
 * row this file finds. The fits pooled across pulse widths (decision 222's REDCap fit, decision
 * 255's clinic-stream fit, and the back site's copies) carry the SAME check since 2026-09-25, run
 * where each is fitted (`stage1_openloop._fit_pooled_rate_stratum`) and attached where their rows
 * are built (`bravo_service._pulse_width_pooling_block`), so the current map card marks a current
 * read from one of them exactly as it marks the others. "Not checked" is kept for a row that carries
 * no check at all, and for a check that ran and could not reach a reading (no block of time could be
 * held out and predicted), which then says why.
 *
 * WHAT THE NOTE SAYS follows decision 275, not decision 253's first sentence ("the setting did not
 * change and the patient's response to it did"), which 275 withdrew: the one map that reads so on
 * RCS08 moved because the whole group's readings moved over those weeks. It changes no
 * recommendation and blocks nothing.
 */
import MDTypography from "components/MDTypography";

import PAL from "views/Reports/ClosedLoopSim/palette";

import { num } from "./stimFormat";
import { TYPE, SMALL } from "./typeScale";

/** Decision 253's own label for a map whose held-out misses are shared by whole blocks of time. */
export const BLOCK_OF_TIME_VERDICT = "moves between blocks of time";

export const BLOCK_OF_TIME_SYMBOL = "†";

export const BLOCK_OF_TIME_NOTE =
  `${BLOCK_OF_TIME_SYMBOL} The pain map this current is read from (its square on the current map card) `
  + `${BLOCK_OF_TIME_VERDICT}: when the record is split into blocks of time and each block is predicted `
  + "from the others, its misses are shared by whole blocks, beyond chance. "
  + "Where this has been examined further, the whole group's readings moved over those "
  + "weeks, whether by regression to the mean or a shared calendar effect, which the check cannot tell "
  + "apart; it was not something about one current. A warning only: it changes no recommendation. The "
  + "follow-up check is “Regression to the mean at one setting”, in the control analyses at the "
  + "foot of this page.";

export const NOT_CHECKED_NOTE = "not checked for movement between blocks of time";

/**
 * Four states, read from one fitted row: "moves" (the check's label), "checked" (any other
 * reading), "not computable" (the check ran and reached no reading; its reason says why), "not
 * checked" (no check on the row at all).
 */
export function blockOfTimeState(row) {
  const cal = row && row.calibration;
  const d = cal && cal.diagnosis;
  if (!d) return "not checked";
  if (d.verdict === null || d.verdict === undefined) return "not computable";
  return d.verdict === BLOCK_OF_TIME_VERDICT ? "moves" : "checked";
}

/**
 * The words for a current whose map carries no reading: "not checked for movement between blocks
 * of time", and, when the check ran and could not reach one, its own reason after a colon (the
 * server's "not computable: " prefix dropped, since the sentence already says so). Null when the
 * map was checked.
 */
export function notCheckedText(row) {
  const state = blockOfTimeState(row);
  if (state === "not checked") return NOT_CHECKED_NOTE;
  if (state !== "not computable") return null;
  const reason = String((row.calibration.diagnosis || {}).reason || "").replace(/^not computable:\s*/i, "");
  return reason ? `${NOT_CHECKED_NOTE}: ${reason}` : NOT_CHECKED_NOTE;
}

const same = (a, b) => num(a) !== null && num(b) !== null && Math.abs(num(a) - num(b)) < 1e-6;

/**
 * The `rate_strata` row a frozen setting's recommended current is read from: the chosen rate at
 * the chosen (left, right) pulse-width pair, `detail.best_pw_us_left` / `best_pw_us_right`.
 */
export function rateRowForSetting(plan, setting) {
  const rows = (((plan && plan.stage1) || {}).rate_strata) || [];
  const d = (setting && setting.detail) || {};
  if (!setting) return null;
  return rows.find((r) => r && r.fitted && same(r.rate_hz, setting.rate_hz)
    && same(r.pw_us_left, d.best_pw_us_left) && same(r.pw_us_right, d.best_pw_us_right)) || null;
}

/** The dagger, beside a recommended current whose map moves. */
export function BlockOfTimeMark() {
  return (
    <sup data-testid="block-of-time-mark" title="its pain map moves between blocks of time; see the note on this card"
      aria-label="its pain map moves between blocks of time; see the note on this card"
      style={{ fontSize: TYPE.small, color: PAL.warnText, fontWeight: 700, marginLeft: 2 }}>
      {BLOCK_OF_TIME_SYMBOL}
    </sup>
  );
}

/** The one note per card, printed only when a mark is on the card. */
export function BlockOfTimeFootnote({ show }) {
  if (!show) return null;
  return (
    <MDTypography variant="caption" component="div" data-testid="block-of-time-footnote"
      sx={{ ...SMALL, mt: 1 }}>
      {BLOCK_OF_TIME_NOTE}
    </MDTypography>
  );
}
