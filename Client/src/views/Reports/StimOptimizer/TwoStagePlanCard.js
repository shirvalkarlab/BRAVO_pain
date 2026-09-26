/**
 * The closed-loop card on the Stim Optimizer page: may closed loop start on the setting the
 * open-loop search froze, and if not, which of the 4 checks blocks; what adaptive mode ruled out,
 * drawn; and what closed loop would do if it were allowed to start.
 *
 * Rewritten 2026-09-12 (page redesign, phase 2) from the first two-stage card of the same day.
 * What moved where:
 *   - the frozen setting per side, the setting in force and the reasons: to the decision strip at
 *     the top of the page (DecisionStrip.js), so they are not printed twice;
 *   - the four conditions: to ClosedLoopChecks.js, symbols and numbers in the open, sentences
 *     folded;
 *   - the exclusions list: to ExcludedSettingsChart.js, drawn on a rate axis with the adaptive
 *     minimum marked;
 *   - the per-combination fit table, the skipped combinations and the provenance sentences: kept,
 *     folded, unchanged.
 * Everything on the card is READ from the `two_stage` block the server returns
 * (`_two_stage_payload` in `StimOptimizer/bravo_service.py`); nothing is recomputed here. The
 * rule this page's family follows (Closed-Loop page, decision 123): values, verdicts and reasons
 * are never inside a fold; only the sentences that say how they were arrived at fold.
 *
 * NO OVERRIDE CONTROL YET. The endpoint accepts an override with a stated reason
 * (`TwoStageOverrideReason` / `TwoStageOverrideBy`); this card does not send one, and says so.
 *
 * Resized 2026-09-12 after the PI's review: the title at 17 px, prose at 13 px, table rows at
 * 13 px under 11 px headers, and the loading line says what the first request really costs
 * (the whole optimiser reruns with the flag, about a minute; a few seconds afterwards).
 *
 * The design review of 2026-09-26 (the PI: "yes to all six, build them"): the excluded-settings
 * chart folds under its one-line summary; "If closed loop could start" is drawn only when closed
 * loop started (its "Nothing was drawn up: N checks above block" restated the checks); the
 * override note and the notes from the closed-loop step move into the "How this was arrived at"
 * fold; the sentence pointing at the titration card is gone.
 */
import { Card, CircularProgress, Table, TableBody, TableCell, TableHead, TableRow } from "@mui/material";

import MDBox from "components/MDBox";
import MDTypography from "components/MDTypography";

import PAL from "views/Reports/ClosedLoopSim/palette";

import ClosedLoopChecks from "./ClosedLoopChecks";
import ExcludedSettingsChart, { ExcludedSettingsSummary } from "./ExcludedSettingsChart";
import { num } from "./stimFormat";
import { TYPE, HEAD, SizedFold as Fold } from "./typeScale";

export const TWO_STAGE_CARD_TITLE = "Closed loop: may it start on the frozen setting?";

//: The folded table's "best left / right current" is read from ONE fit per pulse-width pairing
//: pooled across every stimulation rate (reference only; the page's recommended current is read
//: from each rate's own map, `stage1_openloop._freeze_joint`). Decision 253's block-of-time check is
//: NOT run on that fit, on purpose (2026-09-25, the PI's "deal with the Q4 edge cases"): it holds
//: one stretch of time out and predicts it from the rest, and rates are tried in different periods,
//: so a stretch held out is also a set of rates held out and a miss cannot be told apart from a
//: rate the fit had not learnt. Measured on RCS08: in the REDCap fit at 60/160 us, the one behind
//: 1.5 / 1.0 mA at 55 Hz, the first of its three stretches holds every epoch at 10 and 165 Hz and
//: the other two hold 55 Hz alone; in the clinic stream's 60/60 us fit the three stretches share
//: one rate between them. So the table says the currents are not checked, and why, and no dagger.
export const ACROSS_RATES_NOT_CHECKED =
  "The best currents in this table are read from one fit per pulse-width pairing pooled across every "
  + "stimulation rate, for reference, and are not checked for movement between blocks of time. That "
  + "check holds one stretch of time out and predicts it from the rest; because rates are tried in "
  + "different periods, a stretch held out of this fit is also a set of rates held out, and a miss "
  + "could not be told apart from a rate the fit had not learnt. The current this page recommends is "
  + "read from each rate's own map, which is checked (the current map card).";

const fmt = (v, d = 1) => (num(v) === null ? "—" : num(v).toFixed(d));
const cell = (v) => {
  if (v === null || v === undefined) return "—";
  if (typeof v === "boolean") return v ? "yes" : "no";
  if (typeof v === "number") return Number.isInteger(v) ? String(v) : v.toFixed(3);
  return String(v);
};

/** A small table from a list of records, showing only the named columns that are present. */
function RecordTable({ rows, columns, limit = 12 }) {
  if (!rows || !rows.length) return null;
  const present = columns.filter(([k]) => rows.some((r) => r && r[k] !== undefined));
  return (
    <MDBox sx={{ overflowX: "auto" }}>
      <Table size="small" sx={{ mt: 0.5 }}>
        <TableHead sx={{ display: "table-header-group", p: 0 }}>
          <TableRow>
            {present.map(([k, label]) => (
              <TableCell key={k} sx={{ py: 0.6 }}>
                <MDTypography variant="caption" sx={HEAD}>{label}</MDTypography>
              </TableCell>
            ))}
          </TableRow>
        </TableHead>
        <TableBody>
          {rows.slice(0, limit).map((r, i) => (
            <TableRow key={i}>
              {present.map(([k]) => (
                <TableCell key={k} sx={{ py: 0.5 }}>
                  <MDTypography variant="caption" sx={{ fontSize: TYPE.body, fontFamily: PAL.mono, whiteSpace: "nowrap" }}>{cell(r[k])}</MDTypography>
                </TableCell>
              ))}
            </TableRow>
          ))}
        </TableBody>
      </Table>
      {rows.length > limit && (
        <MDTypography variant="caption" color="text" sx={{ fontSize: TYPE.small }}>
          {`${limit} of ${rows.length} rows shown.`}
        </MDTypography>
      )}
    </MDBox>
  );
}

// One row per JOINT (pulse-width-Left, pulse-width-Right) stratum (2026-09-14 joint redesign),
// not per side: the backend still serves two rows per stratum (a per-side VIEW so other readers
// need no change), so this table de-duplicates by `joint_stratum_key` before rendering -- see
// `dedupeJointStrata` below.
const STRATA_COLUMNS = [
  ["pw_us_left", "left pulse width (µs)"], ["pw_us_right", "right pulse width (µs)"],
  ["n_epochs", "stretches fitted"], ["n_reports", "pain reports"],
  ["opt_rate_hz", "best rate (Hz)"],
  ["opt_amp_mA_left", "best left current (mA)"], ["opt_amp_mA_right", "best right current (mA)"],
  ["gain", "predicted gain (pts)"], ["sd_of_difference", "1 SD of that gain (pts)"],
  ["optimum_resolved", "proven better"], ["incumbent_rate_supported", "rate in force was delivered here"],
  ["optimum_rate_supported", "best rate was delivered here"],
];

/** One row per joint stratum: the backend's `strata` list carries two rows per fitted stratum (a
 * Left view and a Right view of the same joint fit, for readers that still want a per-side row),
 * and this keeps only the first row seen per `joint_stratum_key`. */
function dedupeJointStrata(strata) {
  const seen = new Set();
  const out = [];
  for (const r of strata || []) {
    const key = r && r.joint_stratum_key;
    if (key == null || seen.has(key)) continue;
    seen.add(key);
    out.push(r);
  }
  return out;
}

const POLICY_COLUMNS = [
  ["hemisphere", "side"], ["mode", "mode"], ["center_hz", "band centre (Hz)"],
  ["band_lo_hz", "band from (Hz)"], ["band_hi_hz", "band to (Hz)"],
  ["amp_min_mA", "lowest current (mA)"], ["amp_max_mA", "highest current (mA)"],
  ["rate_hz", "rate (Hz)"], ["pw_us", "pulse width (µs)"],
  ["threshold_lower", "lower switching value"], ["threshold_upper", "upper switching value"],
  ["threshold_single", "single switching value"], ["thresholds_determined", "switching values set"],
];

export default function TwoStagePlanCard({ plan, loading, err }) {
  const stage1 = (plan && plan.stage1) || {};
  const frozen = stage1.frozen_configuration || {};
  const envelope = frozen.adaptive_envelope || stage1.adaptive_envelope || {};
  const stage2 = (plan && plan.stage2) || {};
  const provenance = (plan && plan.provenance) || {};
  const strata = dedupeJointStrata(stage1.strata);
  const skipped = stage1.strata_skipped || {};
  const policies = Array.isArray(stage2.policies) ? stage2.policies : [];
  const queue = Array.isArray(stage1.queue) ? stage1.queue : [];

  return (
    <Card>
      <MDBox p={2}>
        <MDTypography variant="h6" sx={{ fontSize: TYPE.section }}>{TWO_STAGE_CARD_TITLE}</MDTypography>

        {loading && (
          <MDBox mt={1.5} display="flex" alignItems="center" gap={1.5}>
            <CircularProgress size={18} />
            <MDTypography variant="caption" color="text" sx={{ fontSize: TYPE.body }}>
              computing the two-stage plan (about a minute the first time; a few seconds afterwards)&hellip;
            </MDTypography>
          </MDBox>
        )}

        {!loading && err && (
          <MDBox mt={1.5} p={1} sx={{ borderRadius: "6px", border: `1px solid ${PAL.warn}`, backgroundColor: "#fdf6e7" }}>
            <MDTypography variant="caption" sx={{ color: PAL.warnText, fontSize: TYPE.body }} component="div">
              {`The plan is not available: ${err}`}
            </MDTypography>
          </MDBox>
        )}

        {!loading && !err && plan && (
          <>
            {frozen.overridden && (
              <MDTypography variant="caption" sx={{ color: PAL.warnText, fontSize: TYPE.body }} component="div" mt={0.5}>
                {`A clinician override was recorded with the request`
                  + (frozen.override && frozen.override.reason ? `: ${frozen.override.reason}` : ".")
                  + (frozen.override && frozen.override.by ? ` (${frozen.override.by})` : "")}
              </MDTypography>
            )}

            {/* ---------- the 4 checks ---------- */}
            <MDBox mt={1.5}>
              <ClosedLoopChecks plan={plan} />
            </MDBox>

            {/* ---------- what closed loop ruled out: the summary in the open, the drawing folded
                (the design review of 2026-09-26, S5) ---------- */}
            {(envelope.statement || envelope.n_exclusions != null) && (
              <MDBox mt={3}>
                <MDTypography variant="h6" sx={{ fontSize: TYPE.section }}>What closed loop ruled out</MDTypography>
                <MDBox mt={0.6}>
                  <ExcludedSettingsSummary envelope={envelope} />
                </MDBox>
                <Fold show="Show the ruled-out settings, drawn" hide="Hide the drawing" dense mt={0.4}>
                  <ExcludedSettingsChart envelope={envelope} strata={strata} />
                  {envelope.override_ignored && (
                    <MDTypography variant="caption" component="div" sx={{ fontSize: TYPE.small, color: PAL.warnText }}>
                      {String(envelope.override_ignored)}
                    </MDTypography>
                  )}
                </Fold>
              </MDBox>
            )}

            {/* ---------- what closed loop would do: drawn only when it started. Until 2026-09-26
                a refused start printed "Nothing was drawn up: N checks above block (...)", which
                restated the checks above it. ---------- */}
            {stage2.started && (
              <MDBox mt={3}>
                <MDTypography variant="h6" sx={{ fontSize: TYPE.section }}>What closed loop would do</MDTypography>
                <MDTypography variant="caption" color="text" component="div" sx={{ fontSize: TYPE.body }}>
                  {`${stage2.n_valid_policies != null ? stage2.n_valid_policies : policies.length} closed-loop `
                    + `settings could be drawn up`
                    + (stage2.n_rejected != null ? `; ${stage2.n_rejected} were rejected` : "")
                    + (stage2.ranking_basis ? `. Ranked by: ${stage2.ranking_basis}` : "")
                    + (stage2.ranking_assessed === false ? " (ranking not assessed)" : "")
                    + "."}
                </MDTypography>
                <RecordTable rows={policies} columns={POLICY_COLUMNS} limit={10} />
                {policies.length === 0 && (
                  <MDTypography variant="caption" color="text" component="div" sx={{ fontSize: TYPE.body }}>
                    Closed loop started but returned no settings.
                  </MDTypography>
                )}
              </MDBox>
            )}

            {/* ---------- the in-clinic plan lives on ONE card. Until 2026-09-15 this card also
                printed the joint model's "What to test at the next visit" queue (decision 157: cells
                never tested on the frozen surface, ranked by expected improvement). On this record
                every row's predicted value is identical to three decimals, so the ranking is noise
                (decision 158 found the picture flat), and the page then carried two in-clinic
                recommendations that disagreed -- the PI's own titration session (decisions 146, 160,
                163) and this queue. The PI's instruction, 2026-09-15: one. The queue stays on the
                response (`two_stage.stage1.queue`, stored as the exploration ladder) and is drawn
                nowhere. ---------- */}

            {/* ---------- folded: how the answer was arrived at ---------- */}
            <Fold show="How this was arrived at (what each step read, and the fit for each pulse width and side)"
              hide="Hide how this was arrived at">
              {["stage1", "gate", "stage2"].filter((k) => provenance[k]).map((k) => (
                <MDTypography key={k} variant="caption" color="text" component="div" sx={{ fontSize: TYPE.body, mb: 0.6 }}>
                  {String(provenance[k])}
                </MDTypography>
              ))}
              {Array.isArray(stage2.notes) && stage2.notes.length > 0 && (
                <MDTypography variant="caption" color="text" component="div" sx={{ fontSize: TYPE.body, mb: 0.6 }}>
                  {`Notes from the closed-loop step: ${stage2.notes.map((n) => String(n)).join(" ")}`}
                </MDTypography>
              )}
              {queue.length > 0 && (
                <MDTypography variant="caption" color="text" component="div" sx={{ fontSize: TYPE.body, mb: 0.6 }}>
                  {`The joint search's ${queue.length} untested cells are on the response and are not a second in-clinic plan.`}
                </MDTypography>
              )}
              <MDTypography variant="caption" color="text" component="div" sx={{ fontSize: TYPE.body, mb: 0.6 }}>
                An override with a stated reason can be sent with the request; there is no control
                for it here yet.
              </MDTypography>
              {(plan.backend || plan.seconds != null) && (
                <MDTypography variant="caption" color="text" component="div" sx={{ fontSize: TYPE.body, mb: 0.6 }}>
                  {plan.backend ? `Fitted with: ${plan.backend}. ` : ""}
                  {plan.seconds != null ? `The plan took ${fmt(plan.seconds, 1)} s of the request.` : ""}
                </MDTypography>
              )}
              {strata.length > 0 && (
                <MDBox mt={0.8}>
                  <MDTypography variant="caption" fontWeight="medium" component="div" sx={{ fontSize: TYPE.num }}>
                    The fit for each pulse width and side
                  </MDTypography>
                  <MDTypography variant="caption" color="text" component="div" sx={{ fontSize: TYPE.small, mt: 0.3 }}>
                    {ACROSS_RATES_NOT_CHECKED}
                  </MDTypography>
                  <RecordTable rows={strata} columns={STRATA_COLUMNS} limit={20} />
                </MDBox>
              )}
              {Object.keys(skipped).length > 0 && (
                <MDBox mt={0.8}>
                  <MDTypography variant="caption" fontWeight="medium" component="div" sx={{ fontSize: TYPE.num }}>
                    Combinations that could not be fitted
                  </MDTypography>
                  <MDBox component="ul" sx={{ m: 0, pl: 2.5 }}>
                    {Object.entries(skipped).map(([k, v]) => (
                      <li key={k}>
                        <MDTypography variant="caption" color="text" sx={{ fontSize: TYPE.body }}>
                          {`${String(k).replace("__pw", " at ").replace(/_/g, " ")} µs: ${String(v)}`}
                        </MDTypography>
                      </li>
                    ))}
                  </MDBox>
                </MDBox>
              )}
            </Fold>
          </>
        )}
      </MDBox>
    </Card>
  );
}
