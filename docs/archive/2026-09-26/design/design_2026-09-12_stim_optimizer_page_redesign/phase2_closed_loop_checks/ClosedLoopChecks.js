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
 */
import MDBox from "components/MDBox";
import MDTypography from "components/MDTypography";

import Fold from "views/Reports/ClosedLoopSim/Fold";
import PAL from "views/Reports/ClosedLoopSim/palette";
import { TickGlyph, CrossGlyph, AmberGlyph, NotTestedGlyph } from "views/Reports/ClosedLoopSim/glyphs";

import { num, fmtHz, fmtMa, fmtOf, contactLabel } from "./stimFormat";

const SMALL = { fontSize: 10.5, color: "#6A6A6A" };
const MONO = { fontFamily: PAL.mono, fontSize: 12, color: "#1A1A1A" };

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
  if (state === true) return <TickGlyph label="passes" />;
  if (state === false) return <CrossGlyph label="fails" />;
  return <NotTestedGlyph label="not assessed" />;
}
function Sub({ ok, text }) {
  // A per-side sub-answer inside a check: resolved = tick, not resolved = amber (measured and too
  // small to call, never the failure ink), unknown = dashed.
  return (
    <MDBox display="inline-flex" alignItems="center" gap={0.4} mr={1}>
      {ok === true ? <TickGlyph label="resolved" size={11} />
        : (ok === false ? <AmberGlyph label="not resolved" size={11} /> : <NotTestedGlyph label="not assessed" size={11} />)}
      <span style={{ ...MONO, fontSize: 11 }}>{text}</span>
    </MDBox>
  );
}

/** The 18 tested band centres as a row of ticks and crosses, 8–30 Hz left to right. */
function BandTicks({ verdicts, best }) {
  const keys = Object.keys(verdicts || {}).map(Number).filter((k) => Number.isFinite(k)).sort((a, b) => a - b);
  if (!keys.length) return null;
  const W = 300, H = 30, PAD = 12;
  const lo = 8, hi = 30;
  const x = (c) => PAD + ((c - lo) / (hi - lo)) * (W - 2 * PAD);
  return (
    <svg width={W} height={H} role="img" aria-label="which band centres respond">
      <line x1={x(lo)} x2={x(hi)} y1={H - 9} y2={H - 9} stroke="#D8D8D8" />
      {[8, 12, 16, 20, 24, 28].map((t) => (
        <text key={t} x={x(t)} y={H - 1} fontSize="8" fill="#9A9A9A" textAnchor="middle">{t}</text>
      ))}
      {keys.map((c) => {
        const responds = String(verdicts[c] || verdicts[String(c)] || "").toUpperCase().startsWith("RESPONDS");
        const isBest = best != null && Math.abs(Number(best) - c) < 1e-9;
        return responds
          ? <circle key={c} cx={x(c)} cy={H - 19} r={isBest ? 5 : 3.2} fill={PAL.pass} stroke={isBest ? "#1A1A1A" : "none"} strokeWidth="1.2" />
          : <rect key={c} x={x(c) - 3} y={H - 22} width={6} height={6} fill={PAL.fail} />;
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
        <span style={MONO}>
          {["Left", "Right"].filter((h) => rates[h] != null).map((h) => `${h[0]} ${fmtHz(rates[h])}`).join(" · ")}
          <span style={SMALL}>{ev.min_rate_hz != null ? `  (minimum ${fmtHz(ev.min_rate_hz)})` : ""}</span>
        </span>
      );
    }
    case "openloop_choice_resolved": {
      const per = ev.per_hemisphere || {};
      return (
        <MDBox display="flex" flexWrap="wrap" alignItems="center">
          {["Left", "Right"].filter((h) => per[h]).map((h) => (
            <MDBox key={h} display="inline-flex" alignItems="center" mr={1.5}>
              <span style={{ ...MONO, fontSize: 11, marginRight: 6 }}>{h[0]}</span>
              <Sub ok={per[h].rate_resolved === true ? true : (per[h].rate_resolved === false ? false : null)} text="rate" />
              <Sub ok={per[h].pw_resolved === true ? true : (per[h].pw_resolved === false ? false : null)} text="pulse width" />
            </MDBox>
          ))}
        </MDBox>
      );
    }
    case "adaptive_band_passes_lfp_response": {
      const passing = Array.isArray(ev.passing_centers) ? ev.passing_centers : [];
      // The best-separated centre is the passing centre the server named first in its sentence;
      // the strip marks the largest-separation one only once verdict rows arrive (phase 3), so
      // here the marker is omitted rather than guessed.
      return (
        <MDBox>
          <span style={MONO}>{`${fmtOf(ev.n_passing, ev.n_tested)} bands respond`}</span>
          {ev.n_power_unavailable != null && num(ev.n_power_unavailable) > 0 && (
            <span style={SMALL}>{`  · ${Math.round(num(ev.n_power_unavailable))} not measurable`}</span>
          )}
          <MDBox><BandTicks verdicts={ev.verdicts} best={null} /></MDBox>
          {lfp && (
            <MDTypography variant="caption" component="div" sx={SMALL}>
              {lfp.selected
                ? `read on ${contactLabel({ display_short: lfp.selected_display_short }, Array.isArray(lfp.selected_key) ? lfp.selected_key[0] : null)}`
                  + (lfp.pinned_rate_hz != null ? ` at ${fmtHz(lfp.pinned_rate_hz)}` : "")
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
      // "Defaulted" is only said in the sentence today; a structured flag arrives in phase 3.
      const defaulted = /DEFAULTED/.test(String((c && c.detail) || ""));
      return (
        <span style={MONO}>
          {["Left", "Right"].filter((h) => checked[h]).map((h) => `${h[0]} ${fmtMa(checked[h].amp_min_mA)}–${fmtMa(checked[h].amp_max_mA)}`).join(" · ")}
          <span style={SMALL}>{ev.ceiling_mA != null ? `  (ceiling ${fmtMa(ev.ceiling_mA)})` : ""}{defaulted ? " · limits defaulted to the delivered range" : ""}</span>
        </span>
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
        {conditions.length ? (passed ? <TickGlyph label="may start" size={18} /> : <CrossGlyph label="may not start" size={18} />) : null}
        <MDTypography variant="h6" sx={{ fontSize: 15, color }}>{headline}</MDTypography>
      </MDBox>
      <MDBox mt={1} sx={{ display: "grid", gridTemplateColumns: "20px 2fr 3fr", columnGap: "10px", rowGap: "6px", alignItems: "start" }}>
        {conditions.map((c, i) => {
          const st = verdictState(c);
          return [
            <MDBox key={`${i}-g`} pt={0.2}><Glyph state={st} /></MDBox>,
            <MDBox key={`${i}-l`}>
              <MDTypography variant="caption" component="div" title={c.name}
                sx={{ fontSize: 11.5, fontWeight: 600, color: "#2A2A2A" }}>
                {CHECK_LABELS[c.name] || String(c.name || "").replace(/_/g, " ")}
                {c.overridden ? <span style={{ color: PAL.warnText, marginLeft: 6 }}>[overridden]</span> : null}
              </MDTypography>
              <Fold show="Sentence" hide="Hide" dense>
                <MDTypography variant="caption" color="text" component="div" sx={{ fontSize: 10.5 }}>
                  {c.detail || "no reason was returned"}
                </MDTypography>
              </Fold>
            </MDBox>,
            <MDBox key={`${i}-n`}><Numbers c={c} lfp={c.name === "adaptive_band_passes_lfp_response" ? lfp : null} /></MDBox>,
          ];
        })}
      </MDBox>
    </MDBox>
  );
}
