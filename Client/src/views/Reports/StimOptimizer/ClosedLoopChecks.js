/**
 * The 4 checks that decide whether closed loop may start, as a symbol strip: one row per check,
 * the symbol and the numbers in the open, the sentence one click away.
 *
 * Added 2026-09-12 (page redesign, phase 2). Reads `two_stage.gate` and `two_stage.lfp_evidence`
 * from the server; recomputes nothing. The four conditions arrive by their code names and are
 * shown by what they check (HOUSE_RULES §2); the numbers beside each come from the condition's own
 * `evidence` block, which is structured, and never from parsing its sentence. The one exception is
 * marked below (the "defaulted limits" note), and a later phase replaces it with a field.
 *
 * The verdict wording is the page's own, computed from `gate.passed`, `gate.n_conditions` and the
 * failed list, so the strip never prints the server's "Stage 2 MUST NOT START" (a code name).
 *
 * Laid out again 2026-09-12 after the PI's review: a two-column grid (the check's name at 14 px
 * bold with its folded sentence under it; the evidence at 13-14 px), comfortable row spacing, the
 * per-side symbols labelled at 13 px with a legend line saying what each symbol means.
 */
import MDBox from "components/MDBox";
import MDTypography from "components/MDTypography";

import PAL from "views/Reports/ClosedLoopSim/palette";
import { TickGlyph, CrossGlyph, AmberGlyph, NotTestedGlyph } from "views/Reports/ClosedLoopSim/glyphs";

import BandResponseStrip from "./BandResponseStrip";
import { num, fmtHz, fmtMa, fmtOf, contactLabel } from "./stimFormat";
import { TYPE, SMALL, SizedFold } from "./typeScale";

const MONO = { fontFamily: PAL.mono, fontSize: TYPE.num, color: "#1A1A1A" };
const NOTE = { ...SMALL, whiteSpace: "nowrap" };

/** Plain-language names for the four conditions (their code names are in the tooltip). */
export const CHECK_LABELS = {
  rate_at_or_above_adaptive_minimum: "Rate at or above the adaptive minimum",
  openloop_choice_resolved: "Rate and pulse width resolved against their own uncertainty",
  adaptive_band_passes_lfp_response: "A sensed band inside 8–30 Hz responds to stimulation current",
  amplitude_limits_inside_envelope_and_under_ceiling: "Closed-loop current limits inside the delivered range and under the ceiling",
};

function verdictState(c) {
  const v = String((c && c.verdict) || "").trim().toUpperCase();
  if (v === "PASS" || (c && c.passed === true)) return true;
  if (v === "FAIL" || (c && c.passed === false)) return false;
  return null;
}
function Glyph({ state }) {
  if (state === true) return <TickGlyph label="passes" size={18} />;
  if (state === false) return <CrossGlyph label="fails" size={18} />;
  return <NotTestedGlyph label="not assessed" size={18} />;
}
function Sub({ ok, text }) {
  // A per-side sub-answer inside a check: resolved = tick, not resolved = amber (measured and too
  // small to call, never the failure ink), unknown = dashed.
  return (
    <MDBox display="inline-flex" alignItems="center" gap={0.6} mr={2}>
      {ok === true ? <TickGlyph label="resolved" size={14} />
        : (ok === false ? <AmberGlyph label="not resolved" size={14} /> : <NotTestedGlyph label="not assessed" size={14} />)}
      <span style={{ fontSize: TYPE.body, color: "#1A1A1A", whiteSpace: "nowrap" }}>{text}</span>
    </MDBox>
  );
}
/** What the three symbols in the per-side answers mean, printed once under them. */
function SubLegend() {
  const item = { display: "inline-flex", alignItems: "center", gap: 5, whiteSpace: "nowrap" };
  return (
    <MDBox display="flex" flexWrap="wrap" columnGap={2} rowGap={0.4} mt={0.6} sx={SMALL}>
      <span style={item}><TickGlyph label="" size={13} /> resolved: the gain exceeds its own uncertainty</span>
      <span style={item}><AmberGlyph label="" size={13} /> not resolved: measured, too small to call</span>
      <span style={item}><NotTestedGlyph label="" size={13} /> not assessed: the comparison could not be formed</span>
    </MDBox>
  );
}

/** The 18 tested band centres as a row of ticks and crosses, 8–30 Hz left to right. */
function BandTicks({ verdicts, best }) {
  const keys = Object.keys(verdicts || {}).map(Number).filter((k) => Number.isFinite(k)).sort((a, b) => a - b);
  if (!keys.length) return null;
  const W = 560, H = 44, PAD = 18;
  const lo = 8, hi = 30;
  const x = (c) => PAD + ((c - lo) / (hi - lo)) * (W - 2 * PAD);
  return (
    <svg width={W} height={H} role="img" aria-label="which band centres respond">
      <line x1={x(lo)} x2={x(hi)} y1={H - 18} y2={H - 18} stroke="#D8D8D8" />
      {[8, 10, 12, 14, 16, 18, 20, 22, 24, 26, 28, 30].map((t) => (
        <text key={t} x={x(t)} y={H - 3} fontSize={TYPE.axis} fill="#7A7A7A" textAnchor="middle">{t}</text>
      ))}
      {keys.map((c) => {
        const responds = String(verdicts[c] || verdicts[String(c)] || "").toUpperCase().startsWith("RESPONDS");
        const isBest = best != null && Math.abs(Number(best) - c) < 1e-9;
        return responds
          ? <circle key={c} cx={x(c)} cy={H - 30} r={isBest ? 6 : 4} fill={PAL.pass} stroke={isBest ? "#1A1A1A" : "none"} strokeWidth="1.2" />
          : <rect key={c} x={x(c) - 4} y={H - 34} width={8} height={8} fill={PAL.fail} />;
      })}
    </svg>
  );
}

/** The numbers for one check, read from its evidence block. */
function Numbers({ c, lfp }) {
  const ev = (c && c.evidence) || {};
  switch (c && c.name) {
    case "rate_at_or_above_adaptive_minimum": {
      const rates = ev.rates || {};
      return (
        <MDBox display="flex" alignItems="baseline" columnGap={1.5} flexWrap="wrap">
          <span style={{ ...MONO, whiteSpace: "nowrap" }}>
            {["Left", "Right"].filter((h) => rates[h] != null).map((h) => `${h[0]} ${fmtHz(rates[h])}`).join(" · ")}
          </span>
          {ev.min_rate_hz != null && <span style={NOTE}>{`minimum ${fmtHz(ev.min_rate_hz)}`}</span>}
        </MDBox>
      );
    }
    case "openloop_choice_resolved": {
      const per = ev.per_hemisphere || {};
      return (
        <MDBox>
          <MDBox display="flex" flexWrap="wrap" alignItems="center" rowGap={0.6}>
            {["Left", "Right"].filter((h) => per[h]).map((h) => (
              <MDBox key={h} display="inline-flex" alignItems="center" mr={3}>
                <span style={{ ...MONO, fontWeight: 600, marginRight: 10 }}>{h[0]}</span>
                <Sub ok={per[h].rate_resolved === true ? true : (per[h].rate_resolved === false ? false : null)} text="rate" />
                <Sub ok={per[h].pw_resolved === true ? true : (per[h].pw_resolved === false ? false : null)} text="pulse width" />
              </MDBox>
            ))}
          </MDBox>
          <SubLegend />
        </MDBox>
      );
    }
    case "adaptive_band_passes_lfp_response": {
      const passing = Array.isArray(ev.passing_centers) ? ev.passing_centers : [];
      // With the structured rows (phase 3) the strip is bars of separation against the required
      // minimum, the best band labelled; a response from before those rows falls back to the
      // tick row built from the sentences' prefixes.
      const rows = Array.isArray(ev.verdict_rows) ? ev.verdict_rows : null;
      // PER SIDE (review S3, 2026-09-12): the check is judged on each frozen side's own sensing
      // evidence, by the readiness screen's rule (decision 199: at least one band that falls with
      // current once time is removed AND rises with pain on the Biomarkers grid). One block per
      // side, each with its
      // own count, strip and the contact it was read on; a side with no evidence says so.
      const per = ev.per_hemisphere && typeof ev.per_hemisphere === "object" ? ev.per_hemisphere : null;
      const bySide = (lfp && lfp.selected_by_side && typeof lfp.selected_by_side === "object") ? lfp.selected_by_side : {};
      if (per) {
        const sides = ["Left", "Right"].filter((h) => per[h]);
        return (
          <MDBox>
            {sides.map((h) => {
              const b = per[h] || {};
              const sel = bySide[h] || null;
              const k = sel && Array.isArray(sel.selected_key) ? sel.selected_key : null;
              const state = b.passed === true ? "responds" : (b.passed === false ? "does not respond" : "not assessed");
              return (
                <MDBox key={h} mb={1.2}>
                  <MDBox display="flex" alignItems="baseline" columnGap={1.5} flexWrap="wrap">
                    <span style={{ ...MONO, fontWeight: 600 }}>{h[0]}</span>
                    <span style={{ ...MONO, whiteSpace: "nowrap" }}>
                      {b.n_tested
                        ? `${fmtOf(b.n_era_negative_significant, b.n_tested)} fall with current once time is removed · ${b.n_pain_positive == null ? "rise with pain: not known" : `${fmtOf(b.n_pain_positive, b.n_tested)} rise with pain`} · ${fmtOf(b.n_qualifying, b.n_tested)} do both${Array.isArray(b.qualifying_centers_hz) && b.qualifying_centers_hz.length ? ` (${b.qualifying_centers_hz.map((v) => Number(v)).join(", ")} Hz)` : ""}`
                        : state}
                    </span>
                    {b.n_tested ? <span style={NOTE}>{state}</span> : null}
                    {b.n_power_unavailable != null && num(b.n_power_unavailable) > 0 && (
                      <span style={NOTE}>{`${Math.round(num(b.n_power_unavailable))} not measurable`}</span>
                    )}
                  </MDBox>
                  {Array.isArray(b.verdict_rows) && b.verdict_rows.length > 0 && (
                    <MDBox mt={0.6}>
                      <BandResponseStrip rows={b.verdict_rows} minSep={ev.min_sep_d} best={b.best_center_hz} />
                    </MDBox>
                  )}
                  <MDTypography variant="caption" component="div" sx={{ ...SMALL, mt: 0.4 }}>
                    {sel && sel.selected
                      ? <>read on <span style={{ whiteSpace: "nowrap" }}>{contactLabel({ display_short: sel.selected_display_short }, k ? k[0] : null)}</span>
                        {sel.pinned_rate_hz != null ? <> at <span style={{ whiteSpace: "nowrap" }}>{fmtHz(sel.pinned_rate_hz)}</span></> : null}
                        {b.laterality === "contralateral" ? <span style={{ color: PAL.warnText }}> · a contact on the other side (none on this side passed)</span> : null}</>
                      : (b.reason || (sel && sel.selection_note) || "no sensing contact could be used on this side")}
                  </MDTypography>
                </MDBox>
              );
            })}
            {lfp && (
              <MDTypography variant="caption" component="div" sx={{ ...SMALL, mt: 0.2 }}>
                {lfp.n_cells_screened != null ? `${lfp.n_cells_screened} contact-and-rate combinations screened` : ""}
                {lfp.n_cells_unbuildable != null ? `, ${lfp.n_cells_unbuildable} could not be built` : ""}
                {" · one side's sensing contact licenses only that side"}
              </MDTypography>
            )}
          </MDBox>
        );
      }
      return (
        <MDBox>
          <MDBox display="flex" alignItems="baseline" columnGap={1.5} flexWrap="wrap">
            <span style={{ ...MONO, whiteSpace: "nowrap" }}>{`${fmtOf(ev.n_passing, ev.n_tested)} bands respond`}</span>
            {ev.n_power_unavailable != null && num(ev.n_power_unavailable) > 0 && (
              <span style={NOTE}>{`${Math.round(num(ev.n_power_unavailable))} not measurable`}</span>
            )}
          </MDBox>
          <MDBox mt={0.6}>
            {rows
              ? <BandResponseStrip rows={rows} minSep={ev.min_sep_d} best={ev.best_center_hz} />
              : <BandTicks verdicts={ev.verdicts} best={null} />}
          </MDBox>
          {lfp && (
            <MDTypography variant="caption" component="div" sx={{ ...SMALL, mt: 0.4 }}>
              {lfp.selected
                ? <>read on <span style={{ whiteSpace: "nowrap" }}>{contactLabel({ display_short: lfp.selected_display_short }, Array.isArray(lfp.selected_key) ? lfp.selected_key[0] : null)}</span>
                  {lfp.pinned_rate_hz != null ? <> at <span style={{ whiteSpace: "nowrap" }}>{fmtHz(lfp.pinned_rate_hz)}</span></> : null}</>
                : "no sensing contact could be used"}
              {lfp.n_cells_screened != null ? ` · ${lfp.n_cells_screened} contact-and-rate combinations screened` : ""}
              {lfp.n_cells_unbuildable != null ? `, ${lfp.n_cells_unbuildable} could not be built` : ""}
              {passing.length ? ` · responding centres ${passing.map((v) => Number(v).toFixed(1)).join(", ")} Hz` : ""}
            </MDTypography>
          )}
        </MDBox>
      );
    }
    case "amplitude_limits_inside_envelope_and_under_ceiling": {
      const checked = ev.checked || {};
      // `evidence.defaulted` names the sides whose limits were never proposed (phase 3); an
      // older response says it only in the sentence, which is read for the word as a fallback.
      const defaulted = Array.isArray(ev.defaulted)
        ? ev.defaulted.length > 0
        : /DEFAULTED/.test(String((c && c.detail) || ""));
      return (
        <MDBox display="flex" alignItems="baseline" columnGap={1.5} flexWrap="wrap">
          <span style={{ ...MONO, whiteSpace: "nowrap" }}>
            {["Left", "Right"].filter((h) => checked[h]).map((h) => `${h[0]} ${fmtMa(checked[h].amp_min_mA)}–${fmtMa(checked[h].amp_max_mA)}`).join(" · ")}
          </span>
          {ev.ceiling_by_side
            // 2026-09-12: the ceiling is the current the PI stated as not acceptable, per side,
            // with its provenance; an older response carries only the one number.
            ? (<span style={NOTE} title={["Left", "Right"].filter((h) => ev.ceiling_by_side[h]).map((h) => `${h}: ${ev.ceiling_by_side[h].provenance}`).join(" · ")}>
                {`ceiling ${["Left", "Right"].filter((h) => ev.ceiling_by_side[h]).map((h) => `${h[0]} ${fmtMa(ev.ceiling_by_side[h].ceiling_mA)}`).join(" · ")}`}
              </span>)
            : (ev.ceiling_mA != null && <span style={NOTE}>{`ceiling ${fmtMa(ev.ceiling_mA)}`}</span>)}
          {defaulted && <span style={NOTE}>limits defaulted to the delivered range</span>}
          {/* Review 2026-09-15, S1: a DEFAULTED limit is the highest current the device has ever
              delivered, not a proposal. When it sits above the PI's ceiling the backend now
              returns "not assessed" and names both numbers here; a reader must not take the
              4.8 mA as the plan asking for an unsafe current. */}
          {Object.entries(ev.history_above_ceiling || {}).map(([h, v]) => (
            <span key={h} style={{ ...NOTE, color: PAL.warnText, flexBasis: "100%" }}>
              {`${h[0]}: ${fmtMa(v.delivered_max_mA)} delivered in the past is above today's ${fmtMa(v.ceiling_mA)} ceiling — history, not a proposal; no limit has been proposed yet`}
            </span>
          ))}
          {/* Review 2026-09-15, S2: the side-effect-versus-current statistic the gate recomputes on
              every request (decision 166), printed with its n whether the check passes or fails,
              so "does not move with current" is never read without the 15 rows behind it. */}
          {ev.side_effect_vs_current && (
            <span style={{ ...NOTE, flexBasis: "100%" }}>
              {ev.side_effect_vs_current.sentence
                ? `Side effects versus current: ${ev.side_effect_vs_current.sentence}`
                : `Side effects versus current: not assessable${ev.side_effect_vs_current.reason ? ` (${ev.side_effect_vs_current.reason})` : ""}`}
            </span>
          )}
        </MDBox>
      );
    }
    default:
      return null;
  }
}

export default function ClosedLoopChecks({ plan }) {
  const gate = (plan && plan.gate) || {};
  const conditions = Array.isArray(gate.conditions) ? gate.conditions : [];
  const lfp = (plan && plan.lfp_evidence) || {};
  const nFail = Array.isArray(gate.failed) ? gate.failed.length : conditions.filter((c) => verdictState(c) === false).length;
  const nNot = Array.isArray(gate.not_assessed) ? gate.not_assessed.length : conditions.filter((c) => verdictState(c) === null).length;
  const n = num(gate.n_conditions) ?? conditions.length;
  const passed = gate.passed === true;
  const color = passed ? PAL.pass : (conditions.length ? PAL.fail : PAL.neutral);
  const headline = !conditions.length
    ? "The check did not run"
    : (passed
      ? `Closed loop may start: ${n} of ${n} checks pass`
      : `Closed loop may not start: ${nFail} of ${n} checks block${nNot ? `, ${nNot} not assessed` : ""}`);
  return (
    <MDBox>
      <MDBox display="flex" alignItems="center" gap={1}>
        {conditions.length ? (passed ? <TickGlyph label="may start" size={20} /> : <CrossGlyph label="may not start" size={20} />) : null}
        <MDTypography variant="h6" sx={{ fontSize: TYPE.section, color }}>{headline}</MDTypography>
      </MDBox>
      {/* Two columns: the check (symbol, name, folded sentence) and its evidence. */}
      <MDBox mt={1.5} sx={{ display: "grid", gridTemplateColumns: "minmax(300px, 1fr) minmax(360px, 1.5fr)",
        columnGap: "28px", rowGap: "22px", alignItems: "start" }}>
        {conditions.map((c, i) => {
          const st = verdictState(c);
          return [
            <MDBox key={`${i}-l`} display="flex" alignItems="flex-start" gap={1}>
              <MDBox pt={0.2} sx={{ flex: "0 0 auto" }}><Glyph state={st} /></MDBox>
              <MDBox>
                <MDTypography variant="caption" component="div" title={c.name}
                  sx={{ fontSize: TYPE.num, fontWeight: 700, color: "#2A2A2A", lineHeight: 1.35 }}>
                  {CHECK_LABELS[c.name] || String(c.name || "").replace(/_/g, " ")}
                  {c.overridden ? <span style={{ color: PAL.warnText, marginLeft: 6 }}>[overridden]</span> : null}
                </MDTypography>
                <SizedFold show="Sentence" hide="Hide" dense mt={0.3}>
                  <MDTypography variant="caption" color="text" component="div" sx={{ fontSize: TYPE.body }}>
                    {c.detail || "no reason was returned"}
                  </MDTypography>
                </SizedFold>
              </MDBox>
            </MDBox>,
            <MDBox key={`${i}-n`} pt={0.2}><Numbers c={c} lfp={c.name === "adaptive_band_passes_lfp_response" ? lfp : null} /></MDBox>,
          ];
        })}
      </MDBox>
    </MDBox>
  );
}
