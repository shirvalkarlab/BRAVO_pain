/**
 * The two-stage plan card on the Stim Optimizer page: what the open-loop search froze on each
 * side, which settings it set aside because adaptive mode cannot use them, the check that decides
 * whether closed loop may start (four conditions, one verdict each), and what closed loop would
 * do if it were allowed to start -- or why it was not.
 *
 * Added 2026-09-12 at the PI's direction ("wire the front end"). Everything on the card is READ
 * from the `two_stage` block the server returns (`_two_stage_payload` in
 * `StimOptimizer/bravo_service.py`); nothing is recomputed here. The block was built while
 * another change was landing on the server (an adaptive-range constraint and an `exclusions`
 * list), so this card renders the exclusions when the list is present and nothing when it is
 * absent, and it ignores keys it does not know.
 *
 * WHAT IS IN THE OPEN AND WHAT FOLDS. The rule this page's family follows (Closed-Loop page,
 * 2026-09-11): values, verdicts, reasons and the exclusions are never inside a fold. Only the
 * per-combination fit table and the provenance sentences fold, because they say how the answer
 * was arrived at rather than what it is.
 *
 * NO OVERRIDE CONTROL YET. The endpoint accepts an override with a stated reason
 * (`TwoStageOverrideReason` / `TwoStageOverrideBy`); this card does not send one, and says so.
 */
import { Card, CircularProgress, Table, TableBody, TableCell, TableHead, TableRow } from "@mui/material";

import MDBox from "components/MDBox";
import MDTypography from "components/MDTypography";

import Fold from "views/Reports/ClosedLoopSim/Fold";
import PAL from "views/Reports/ClosedLoopSim/palette";

export const TWO_STAGE_CARD_TITLE = "Two-stage plan: open loop, then the gate, then closed loop";

const fmt = (v, d = 1) =>
  (v === null || v === undefined || Number.isNaN(Number(v))) ? "—" : Number(v).toFixed(d);
const num = (v) => (v === null || v === undefined || !Number.isFinite(Number(v)) ? null : Number(v));
const cell = (v) => {
  if (v === null || v === undefined) return "—";
  if (typeof v === "boolean") return v ? "yes" : "no";
  if (typeof v === "number") return Number.isInteger(v) ? String(v) : v.toFixed(3);
  return String(v);
};

/**
 * Plain-language names for the four conditions the server reports by their code names
 * (HOUSE_RULES §2: say what the check does, put the code name in brackets only where it helps).
 */
const CONDITION_LABELS = {
  rate_at_or_above_adaptive_minimum:
    "The frozen stimulation rate is at or above the lowest rate the device allows once adaptive mode is configured",
  openloop_choice_resolved:
    "The open-loop search has settled its rate and pulse width: the predicted gain over the setting in force is larger than the uncertainty of that difference",
  adaptive_band_passes_lfp_response:
    "A frequency band the device can use for adaptive control shows brain-signal power that responds to stimulation current",
  amplitude_limits_inside_envelope_and_under_ceiling:
    "The closed-loop current limits sit inside the range of currents already delivered and under the 5 mA ceiling",
};
const conditionLabel = (name) => CONDITION_LABELS[name] || String(name || "").replace(/_/g, " ");

/** The verdict of one condition, normalised to one of three states whatever spelling arrives. */
function verdictState(c) {
  const v = String((c && c.verdict) || "").trim().toUpperCase();
  if (v === "PASS") return "pass";
  if (v === "FAIL") return "fail";
  if (v.startsWith("NOT")) return "not_assessed";
  if (c && c.passed === true) return "pass";
  if (c && c.passed === false) return "fail";
  return "not_assessed";
}
const VERDICT = {
  pass: { glyph: "✓", word: "passes", color: PAL.pass },
  fail: { glyph: "✗", word: "fails", color: PAL.fail },
  not_assessed: { glyph: "○", word: "not assessed", color: PAL.indeterminate },
};

/** One side's headline sentence, built from the frozen setting's own numbers and reasons. */
function sideHeadline(s) {
  const side = s.hemisphere || "?";
  const rate = num(s.rate_hz);
  const pw = num(s.pulse_width_us);
  const amp = num(s.amplitude_preferred_mA);
  const lo = num(s.amplitude_delivered_min_mA);
  const hi = num(s.amplitude_delivered_max_mA);
  const n = num(s.n_epochs_fitted_on_the_chosen_stratum);
  const parts = [];
  // A side with no rate is the server's honest "no setting adaptive mode can use exists in this
  // record" (the adaptive-range constraint, 2026-09-12), arriving as null; it is said, not dashed.
  parts.push(rate == null
    ? `${side}: the open-loop search found no rate adaptive mode can use`
      + (pw == null ? "" : ` (pulse width ${fmt(pw, 0)} µs)`)
      + (amp == null ? "" : `, preferred ${fmt(amp, 1)} mA`)
    : `${side}: the open-loop search freezes ${fmt(rate, 0)} Hz `
      + `at ${pw == null ? "a pulse width not observed" : `${fmt(pw, 0)} µs`}, preferred ${fmt(amp, 1)} mA`);
  const extras = [];
  if (lo != null && hi != null) extras.push(`currents delivered so far ${fmt(lo, 1)}–${fmt(hi, 1)} mA`);
  if (n != null) extras.push(`fitted on ${fmt(n, 0)} stretches of unchanged settings`);
  const status = s.resolved ? "resolved" : "not yet resolved";
  return { head: parts[0] + (extras.length ? ` (${extras.join("; ")})` : ""), status };
}

/**
 * The exclusions, wherever the server puts them. The block builder was being extended while this
 * card was written (an adaptive-range constraint, PI 2026-09-12), so the list is looked for as a
 * flat list under `stage1.exclusions` / the frozen configuration / the block itself, and as a
 * mapping by side under `adaptive_envelope.exclusions` (each entry `{what, reason}`). The first
 * non-empty one wins; an absent or empty list renders nothing.
 */
function collectExclusions(plan, stage1, frozen) {
  const env = frozen.adaptive_envelope || stage1.adaptive_envelope || {};
  const candidates = [stage1.exclusions, frozen.exclusions, plan && plan.exclusions, env.exclusions];
  for (let i = 0; i < candidates.length; i += 1) {
    const c = candidates[i];
    if (Array.isArray(c)) {
      if (c.length) return c;
    } else if (c && typeof c === "object") {
      const out = [];
      Object.keys(c).forEach((side) => {
        const list = Array.isArray(c[side]) ? c[side] : [c[side]];
        list.forEach((e) => out.push(e && typeof e === "object" ? { hemisphere: side, ...e }
          : { hemisphere: side, what: e }));
      });
      if (out.length) return out;
    }
  }
  return [];
}

/** Describe one excluded setting from whichever keys the server put on it. */
function exclusionText(e) {
  if (e === null || e === undefined) return "";
  if (typeof e === "string") return e;
  const bits = [];
  if (e.hemisphere) bits.push(String(e.hemisphere));
  if (e.what != null) bits.push(String(e.what));
  const rate = num(e.rate_hz);
  if (rate != null) bits.push(`${fmt(rate, 0)} Hz`);
  const pw = num(e.pulse_width_us != null ? e.pulse_width_us : e.pw_us);
  if (pw != null) bits.push(`${fmt(pw, 0)} µs`);
  const amp = num(e.amplitude_mA != null ? e.amplitude_mA : e.amp_mA);
  if (amp != null) bits.push(`${fmt(amp, 1)} mA`);
  const setting = e.setting || e.label || e.name;
  if (!bits.length && setting) bits.push(String(setting));
  const reason = e.reason || e.detail || e.note || e.why;
  return { setting: bits.join(", ") || "a setting", reason: reason ? String(reason) : null };
}

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
              <TableCell key={k} sx={{ py: 0.4 }}>
                <MDTypography variant="caption" fontWeight="medium" sx={{ fontSize: 10.5 }}>{label}</MDTypography>
              </TableCell>
            ))}
          </TableRow>
        </TableHead>
        <TableBody>
          {rows.slice(0, limit).map((r, i) => (
            <TableRow key={i}>
              {present.map(([k]) => (
                <TableCell key={k} sx={{ py: 0.3 }}>
                  <MDTypography variant="caption" sx={{ fontSize: 10.5 }}>{cell(r[k])}</MDTypography>
                </TableCell>
              ))}
            </TableRow>
          ))}
        </TableBody>
      </Table>
      {rows.length > limit && (
        <MDTypography variant="caption" color="text" sx={{ fontSize: 10 }}>
          {`${limit} of ${rows.length} rows shown.`}
        </MDTypography>
      )}
    </MDBox>
  );
}

const STRATA_COLUMNS = [
  ["hemisphere", "side"], ["pw_us", "pulse width (µs)"], ["n_epochs", "stretches fitted"],
  ["n_reports", "pain reports"], ["opt_rate_hz", "best rate (Hz)"], ["opt_amp_mA", "best current (mA)"],
  ["gain", "predicted gain (points)"], ["sd_of_difference", "uncertainty of that gain"],
  ["optimum_resolved", "resolved"], ["incumbent_rate_supported", "setting in force was delivered here"],
  ["optimum_rate_supported", "best rate was delivered here"],
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
  const settings = Array.isArray(frozen.settings) ? frozen.settings : [];
  const exclusions = collectExclusions(plan, stage1, frozen);
  const envelope = frozen.adaptive_envelope || stage1.adaptive_envelope || {};
  const gate = (plan && plan.gate) || {};
  const conditions = Array.isArray(gate.conditions) ? gate.conditions : [];
  const stage2 = (plan && plan.stage2) || {};
  const lfp = (plan && plan.lfp_evidence) || {};
  const provenance = (plan && plan.provenance) || {};
  const strata = Array.isArray(stage1.strata) ? stage1.strata : [];
  const skipped = stage1.strata_skipped || {};
  const policies = Array.isArray(stage2.policies) ? stage2.policies : [];
  const refusals = Array.isArray(stage2.refusal_reasons) ? stage2.refusal_reasons : [];

  const gatePassed = gate.passed === true;
  const gateColor = gatePassed ? PAL.pass : (conditions.length ? PAL.fail : PAL.indeterminate);

  return (
    <Card>
      <MDBox p={2}>
        <MDTypography variant="h6">{TWO_STAGE_CARD_TITLE}</MDTypography>
        <MDTypography variant="caption" color="text" component="div">
          The open-loop search freezes a stimulation rate, pulse width and preferred current on each
          side. A check then decides whether closed loop may start on that frozen setting. Only if
          it may are closed-loop policies drawn up. Every number here is read from the server&apos;s
          own answer; nothing is recomputed on the page.
        </MDTypography>

        {loading && (
          <MDBox mt={1.5} display="flex" alignItems="center" gap={1.5}>
            <CircularProgress size={16} />
            <MDTypography variant="caption" color="text">computing the two-stage plan&hellip;</MDTypography>
          </MDBox>
        )}

        {!loading && err && (
          <MDBox mt={1.5} p={1} sx={{ borderRadius: "6px", border: `1px solid ${PAL.warn}`, backgroundColor: "#fdf6e7" }}>
            <MDTypography variant="caption" sx={{ color: PAL.warnText }} component="div">
              {`The two-stage plan is not available: ${err}`}
            </MDTypography>
          </MDBox>
        )}

        {!loading && !err && plan && (
          <>
            {/* ---------- Stage 1: what was frozen on each side ---------- */}
            <MDBox mt={1.5}>
              <MDTypography variant="button" fontWeight="medium">Open loop: what the search froze</MDTypography>
              {(frozen.incumbent_rate_hz != null || frozen.primary_item) && (
                <MDTypography variant="caption" color="text" component="div">
                  {`Setting in force today: ${fmt(frozen.incumbent_rate_hz, 0)} Hz at `
                    + `${fmt(frozen.incumbent_pulse_width_us, 0)} µs. `}
                  {frozen.primary_item ? `Pain score the search judged by: ${String(frozen.primary_item).replace(/_/g, " ")}. ` : ""}
                  {frozen.data_horizon ? `Data used: ${frozen.data_horizon}.` : ""}
                </MDTypography>
              )}
              {settings.length === 0 && (
                <MDTypography variant="caption" color="text" component="div">
                  No side was frozen: the search returned no setting.
                </MDTypography>
              )}
              {settings.map((s, i) => {
                const h = sideHeadline(s);
                const reasons = Array.isArray(s.reasons) ? s.reasons : [];
                return (
                  <MDBox key={i} mt={0.8}>
                    <MDTypography variant="body2" component="div" sx={{ fontSize: 13 }}>
                      {h.head}
                      {" — "}
                      <span style={{ color: s.resolved ? PAL.pass : PAL.warnText, fontWeight: 600 }}>{h.status}</span>
                      {reasons.length ? `: ${reasons[0]}` : "."}
                    </MDTypography>
                    {reasons.length > 1 && (
                      <MDBox component="ul" sx={{ m: 0, mt: 0.3, pl: 2.5 }}>
                        {reasons.slice(1).map((r, j) => (
                          <li key={j}>
                            <MDTypography variant="caption" color="text" sx={{ fontSize: 10.5 }}>{String(r)}</MDTypography>
                          </li>
                        ))}
                      </MDBox>
                    )}
                  </MDBox>
                );
              })}
              {frozen.overridden && (
                <MDTypography variant="caption" sx={{ color: PAL.warnText }} component="div" mt={0.5}>
                  {`A clinician override was recorded with the request`
                    + (frozen.override && frozen.override.reason ? `: ${frozen.override.reason}` : ".")
                    + (frozen.override && frozen.override.by ? ` (${frozen.override.by})` : "")}
                </MDTypography>
              )}
            </MDBox>

            {/* ---------- The settings adaptive mode can use: statement, then the exclusions ---------- */}
            {(envelope.statement || envelope.override_ignored) && (
              <MDBox mt={1}>
                {envelope.statement && (
                  <MDTypography variant="caption" color="text" component="div" sx={{ fontSize: 10.5 }}>
                    {`Settings adaptive mode can use: ${String(envelope.statement)}`}
                  </MDTypography>
                )}
                {envelope.override_ignored && (
                  <MDTypography variant="caption" component="div" sx={{ fontSize: 10.5, color: PAL.warnText }}>
                    {String(envelope.override_ignored)}
                  </MDTypography>
                )}
              </MDBox>
            )}
            {exclusions.length > 0 && (
              <MDBox mt={1.5}>
                <MDTypography variant="button" fontWeight="medium">
                  Settings the search excluded because adaptive mode cannot use them
                </MDTypography>
                <MDBox component="ul" sx={{ m: 0, mt: 0.3, pl: 2.5 }}>
                  {exclusions.map((e, i) => {
                    const t = exclusionText(e);
                    return (
                      <li key={i}>
                        <MDTypography variant="caption" component="div" sx={{ fontSize: 11 }}>
                          {typeof t === "string" ? t : (
                            <>
                              <strong>{t.setting}</strong>
                              {t.reason ? ` — ${t.reason}` : ""}
                            </>
                          )}
                        </MDTypography>
                      </li>
                    );
                  })}
                </MDBox>
              </MDBox>
            )}

            {/* ---------- The check that decides whether closed loop may start ---------- */}
            <MDBox mt={2}>
              <MDTypography variant="button" fontWeight="medium">
                The check that decides whether closed loop may start
              </MDTypography>
              <MDTypography variant="h5" component="div" sx={{ color: gateColor, mt: 0.3 }}>
                {gate.verdict || (conditions.length ? "no verdict was returned" : "the check did not run")}
              </MDTypography>
              {conditions.map((c, i) => {
                const st = verdictState(c);
                const v = VERDICT[st];
                return (
                  <MDBox key={i} mt={0.8} display="flex" alignItems="flex-start" gap={1}>
                    <MDTypography variant="body2" component="span" aria-label={v.word}
                      sx={{ color: v.color, fontWeight: 700, fontSize: 16, lineHeight: 1.2, minWidth: 18 }}>
                      {v.glyph}
                    </MDTypography>
                    <MDBox>
                      <MDTypography variant="caption" fontWeight="medium" component="div" sx={{ fontSize: 11.5 }}>
                        {conditionLabel(c.name)}
                        <span style={{ color: v.color, marginLeft: 6 }}>{`[${v.word}]`}</span>
                        {c.overridden ? <span style={{ color: PAL.warnText, marginLeft: 6 }}>[overridden]</span> : null}
                      </MDTypography>
                      <MDTypography variant="caption" color="text" component="div" sx={{ fontSize: 10.5 }}>
                        {c.detail || "no reason was returned"}
                      </MDTypography>
                    </MDBox>
                  </MDBox>
                );
              })}
              {(lfp.selection_note || lfp.refusal_class || lfp.selected != null) && (
                <MDTypography variant="caption" color="text" component="div" sx={{ mt: 0.8, fontSize: 10.5 }}>
                  {"Brain-signal evidence the check read: "}
                  {lfp.selected
                    ? `one sensing contact and band was selected (${Array.isArray(lfp.selected_key) ? lfp.selected_key.join(", ") : String(lfp.selected_key)})`
                    : `none could be used${lfp.selection_note ? ` — ${lfp.selection_note}` : ""}`}
                  {lfp.pinned_rate_hz != null ? `; evidence was restricted to recordings at the frozen rate ${fmt(lfp.pinned_rate_hz, 0)} Hz` : ""}
                  {lfp.n_cells_screened != null ? `; ${lfp.n_cells_screened} contact-and-band combinations screened` : ""}
                  {lfp.n_cells_unbuildable != null ? `, ${lfp.n_cells_unbuildable} could not be built` : ""}
                  {lfp.unbuildable_reasons && Object.keys(lfp.unbuildable_reasons).length
                    ? ` (${Object.entries(lfp.unbuildable_reasons).map(([k, n]) => `${n}: ${k}`).join("; ")})` : ""}
                  .
                </MDTypography>
              )}
            </MDBox>

            {/* ---------- Stage 2: closed loop ---------- */}
            <MDBox mt={2}>
              <MDTypography variant="button" fontWeight="medium">Closed loop</MDTypography>
              {stage2.started ? (
                <>
                  <MDTypography variant="caption" color="text" component="div">
                    {`${stage2.n_valid_policies != null ? stage2.n_valid_policies : policies.length} closed-loop `
                      + `policies could be drawn up`
                      + (stage2.n_rejected != null ? `; ${stage2.n_rejected} were rejected` : "")
                      + (stage2.ranking_basis ? `. Ranked by: ${stage2.ranking_basis}` : "")
                      + (stage2.ranking_assessed === false ? " (ranking not assessed)" : "")
                      + "."}
                  </MDTypography>
                  <RecordTable rows={policies} columns={POLICY_COLUMNS} limit={10} />
                  {policies.length === 0 && (
                    <MDTypography variant="caption" color="text" component="div">
                      Closed loop started but returned no policy rows.
                    </MDTypography>
                  )}
                </>
              ) : (
                <>
                  <MDTypography variant="caption" color="text" component="div">
                    {stage2.reason
                      ? `Closed loop did not start: ${stage2.reason}`
                      : "Closed loop did not start."}
                  </MDTypography>
                  {refusals.length > 0 && (
                    <MDBox component="ul" sx={{ m: 0, mt: 0.3, pl: 2.5 }}>
                      {refusals.map((r, i) => (
                        <li key={i}>
                          <MDTypography variant="caption" component="div" sx={{ fontSize: 10.5 }}>
                            <strong>{conditionLabel(r.condition)}</strong>
                            {r.reason ? ` — ${r.reason}` : ""}
                          </MDTypography>
                        </li>
                      ))}
                    </MDBox>
                  )}
                </>
              )}
              {Array.isArray(stage2.notes) && stage2.notes.length > 0 && (
                <MDTypography variant="caption" color="text" component="div" sx={{ mt: 0.4, fontSize: 10.5 }}>
                  {stage2.notes.map((n) => String(n)).join(" ")}
                </MDTypography>
              )}
            </MDBox>

            <MDTypography variant="caption" color="text" component="div" sx={{ mt: 1.5, fontSize: 10.5 }}>
              An override with a stated reason can be sent with the request; there is no control
              for it here yet.
            </MDTypography>

            {/* ---------- folded: how the answer was arrived at ---------- */}
            <Fold show="How this plan was arrived at (what each stage read, and the fit for each combination of pulse width and side)"
              hide="Hide how this plan was arrived at">
              {["stage1", "gate", "stage2"].filter((k) => provenance[k]).map((k) => (
                <MDTypography key={k} variant="caption" color="text" component="div" sx={{ fontSize: 10.5, mb: 0.4 }}>
                  {String(provenance[k])}
                </MDTypography>
              ))}
              {(plan.backend || plan.seconds != null) && (
                <MDTypography variant="caption" color="text" component="div" sx={{ fontSize: 10.5, mb: 0.4 }}>
                  {plan.backend ? `Fitted with: ${plan.backend}. ` : ""}
                  {plan.seconds != null ? `The plan took ${fmt(plan.seconds, 1)} s of the request.` : ""}
                </MDTypography>
              )}
              {strata.length > 0 && (
                <MDBox mt={0.8}>
                  <MDTypography variant="caption" fontWeight="medium" component="div">
                    The fit for each combination of pulse width and side
                  </MDTypography>
                  <RecordTable rows={strata} columns={STRATA_COLUMNS} limit={20} />
                </MDBox>
              )}
              {Object.keys(skipped).length > 0 && (
                <MDBox mt={0.8}>
                  <MDTypography variant="caption" fontWeight="medium" component="div">
                    Combinations that could not be fitted
                  </MDTypography>
                  <MDBox component="ul" sx={{ m: 0, pl: 2.5 }}>
                    {Object.entries(skipped).map(([k, v]) => (
                      <li key={k}>
                        <MDTypography variant="caption" color="text" sx={{ fontSize: 10.5 }}>
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
