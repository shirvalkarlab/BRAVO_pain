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
 */
import { Card, CircularProgress, Table, TableBody, TableCell, TableHead, TableRow } from "@mui/material";

import MDBox from "components/MDBox";
import MDTypography from "components/MDTypography";

import PAL from "views/Reports/ClosedLoopSim/palette";

import ClosedLoopChecks, { CHECK_LABELS } from "./ClosedLoopChecks";
import ExcludedSettingsChart from "./ExcludedSettingsChart";
import { num } from "./stimFormat";
import { TYPE, HEAD, SizedFold as Fold } from "./typeScale";

export const TWO_STAGE_CARD_TITLE = "Closed loop: may it start on the frozen setting?";

const fmt = (v, d = 1) => (num(v) === null ? "—" : num(v).toFixed(d));
const cell = (v) => {
  if (v === null || v === undefined) return "—";
  if (typeof v === "boolean") return v ? "yes" : "no";
  if (typeof v === "number") return Number.isInteger(v) ? String(v) : v.toFixed(3);
  return String(v);
};
const conditionLabel = (name) => CHECK_LABELS[name] || String(name || "").replace(/_/g, " ");

/** A small table from a list of records, showing only the named columns that are present. */
function RecordTable({ rows, columns, limit = 12 }) {
  if (!rows || !rows.length) return null;
  const present = columns.filter(([k]) => rows.some((r) => r && r[k] !== undefined));
  return (
    <MDBox sx={{ overflowX: "auto" }}>
      <Table size="small" sx={{ mt: 0.5 }}>
        <TableHead>
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
  ["optimum_resolved", "resolved"], ["incumbent_rate_supported", "rate in force was delivered here"],
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

const QUEUE_COLUMNS = [
  ["rank", "rank"], ["freq_hz", "rate (Hz)"],
  ["amp_mA_left", "left current (mA)"], ["amp_mA_right", "right current (mA)"],
  ["posterior_mean", "predicted (pts)"], ["posterior_sd", "±1 SD (pts)"],
  ["expected_improvement", "expected improvement"],
  ["prior_reports_at_this_cell", "prior reports"],
];
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
  const refusals = Array.isArray(stage2.refusal_reasons) ? stage2.refusal_reasons : [];
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

            {/* ---------- what adaptive mode ruled out ---------- */}
            {(envelope.statement || envelope.n_exclusions != null) && (
              <MDBox mt={3}>
                <MDTypography variant="h6" sx={{ fontSize: TYPE.section }}>What adaptive mode ruled out</MDTypography>
                <MDBox mt={0.6}>
                  <ExcludedSettingsChart envelope={envelope} strata={strata} />
                </MDBox>
                {envelope.override_ignored && (
                  <MDTypography variant="caption" component="div" sx={{ fontSize: TYPE.small, color: PAL.warnText }}>
                    {String(envelope.override_ignored)}
                  </MDTypography>
                )}
              </MDBox>
            )}

            {/* ---------- what closed loop would do ---------- */}
            <MDBox mt={3}>
              <MDTypography variant="h6" sx={{ fontSize: TYPE.section }}>If closed loop could start</MDTypography>
              {stage2.started ? (
                <>
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
                </>
              ) : (
                <MDTypography variant="caption" color="text" component="div" sx={{ fontSize: TYPE.body }}>
                  {refusals.length
                    ? `Nothing was drawn up: ${refusals.length} check${refusals.length === 1 ? "" : "s"} above block${refusals.length === 1 ? "s" : ""} (${refusals.map((r) => conditionLabel(r.condition)).join("; ")}).`
                    : "Nothing was drawn up."}
                </MDTypography>
              )}
              {Array.isArray(stage2.notes) && stage2.notes.length > 0 && (
                <Fold show="Notes" hide="Hide notes" dense>
                  <MDTypography variant="caption" color="text" component="div" sx={{ fontSize: TYPE.body }}>
                    {stage2.notes.map((n) => String(n)).join(" ")}
                  </MDTypography>
                </Fold>
              )}
            </MDBox>

            <MDTypography variant="caption" color="text" component="div" sx={{ mt: 2, fontSize: TYPE.small }}>
              An override with a stated reason can be sent with the request; there is no control
              for it here yet.
            </MDTypography>

            {/* ---------- what to test at the next visit, from the JOINT stratum that was
                actually frozen (2026-09-14). The replacement for the old per-arm queue: cells
                never tested, ranked by expected improvement, over both currents at once. ---------- */}
            {queue.length > 0 && (
              <MDBox mt={3}>
                <MDTypography variant="h6" sx={{ fontSize: TYPE.section }}>What to test at the next visit</MDTypography>
                <MDTypography variant="caption" color="text" component="div" sx={{ fontSize: TYPE.body, mb: 0.5 }}>
                  Cells never tested on the frozen (rate, left current, right current) surface,
                  ranked by expected improvement -- the joint replacement for the per-side queue.
                </MDTypography>
                <RecordTable rows={queue} columns={QUEUE_COLUMNS} limit={10} />
              </MDBox>
            )}

            {/* ---------- folded: how the answer was arrived at ---------- */}
            <Fold show="How this was arrived at (what each step read, and the fit for each pulse width and side)"
              hide="Hide how this was arrived at">
              {["stage1", "gate", "stage2"].filter((k) => provenance[k]).map((k) => (
                <MDTypography key={k} variant="caption" color="text" component="div" sx={{ fontSize: TYPE.body, mb: 0.6 }}>
                  {String(provenance[k])}
                </MDTypography>
              ))}
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
