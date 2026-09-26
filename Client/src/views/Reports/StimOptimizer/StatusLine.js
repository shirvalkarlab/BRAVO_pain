/**
 * The Stim Optimizer page's status line: one sentence answering the page's two questions (should
 * today's setting change; can closed loop start), then short bullets saying why, red for what the
 * device refuses or a check blocks and yellow for evidence that was not evaluated, and the detail
 * behind each bullet folded underneath.
 *
 * Added 2026-09-26: the design review of the Stim Optimizer and Biomarkers pages (§1.4, S4), built
 * on the PI's "yes to all six, build them" of the same day, the pattern he ruled for the Closed-Loop
 * page: one status line; red bullets and yellow bullets, each five words or fewer, each with a
 * glyph as well as a colour (● red, ▲ yellow), so colour is never the only signal; details folded.
 * It sits above the readiness card, which amends decision 243's page order by one line; no card
 * moved.
 *
 * EVERYTHING IS READ, NOTHING RECOMPUTED. The sentence reads the per-side verdicts the decision
 * strip reads (`DecisionStrip.sideVerdicts`) and the four checks' own states (`gate.conditions`,
 * read as the checks card reads them, `ClosedLoopChecks.verdictState`); the bullets read:
 *   - the device's sensing rule (`closed_loop.sensing_rule`): no usable band on any pair the device
 *     allows today, or no pair allowed at all; an older response without the rule falls back to the
 *     screen's own `ready`;
 *   - each check that blocks (red) or was not assessed (yellow), by a short name of its own;
 *   - a pulse-width choice that was never put to the data (the choice check's per-side
 *     `pw_resolved` is null on every side);
 *   - what the next visit must deliver: the pairs still missing from the pain map the decision
 *     reads (`rate_strata` at the frozen setting's rate and pulse widths) or, when that map passes,
 *     from the next clinic session's merged record (`clinic_stream.next_session_coverage`);
 *   - decision 253's check on that same map: "moves between blocks of time" becomes a yellow
 *     bullet carrying decision 294's dagger, with the dagger's note in the fold.
 * A field the response does not carry produces no bullet: nothing is invented.
 */
import MDBox from "components/MDBox";
import MDTypography from "components/MDTypography";

import { num, fmtHz } from "./stimFormat";
import { TYPE, SMALL, SizedFold } from "./typeScale";
import { sideVerdicts } from "./DecisionStrip";
import { verdictState } from "./ClosedLoopChecks";
import {
  BLOCK_OF_TIME_NOTE, BLOCK_OF_TIME_SYMBOL, blockOfTimeState, rateRowForSetting,
} from "./blockOfTime";

/** The glyph each kind of bullet carries beside its colour. */
export const STATUS_GLYPH = { red: "●", yellow: "▲" };

/** Pale fill, glyph ink and the word a screen reader hears, per kind (minimalist-ui's muted tag
 *  pairs: the glyph measures 6.3:1 on its red fill and 4.6:1 on its yellow one; the words are
 *  near-black). */
const KIND = {
  red: { fill: "#FDEBEC", ink: "#9F2F2D", word: "blocked" },
  yellow: { fill: "#FBF3DB", ink: "#956400", word: "not evaluated" },
};

/** Short names, five words or fewer, for a check that blocks and one that was not assessed. */
const RED_NAME = {
  rate_at_or_above_adaptive_minimum: (c) => {
    const m = num(((c && c.evidence) || {}).min_rate_hz);
    return m === null ? "Rate below closed-loop minimum" : `Rate below ${fmtHz(m)} refused`;
  },
  openloop_choice_resolved: () => "Setting not proven better",
  adaptive_band_passes_lfp_response: () => "No band moves with current",
  amplitude_limits_inside_envelope_and_under_ceiling: () => "Current limits above ceiling",
};
const YELLOW_NAME = {
  rate_at_or_above_adaptive_minimum: () => "Rate check not assessed",
  openloop_choice_resolved: () => "Setting comparison not assessed",
  adaptive_band_passes_lfp_response: () => "Band response not assessed",
  amplitude_limits_inside_envelope_and_under_ceiling: () => "Current limits not proposed",
};

const plural = (n, one, many) => `${n} ${n === 1 ? one : many}`;

/** The headline and the bullets, from the page's response and the two-stage plan. */
export function statusSummary(data, plan) {
  const d = data || {};
  // ---- the sentence ----------------------------------------------------------------------
  let decision;
  if (!plan) {
    decision = "Today's setting is still being compared";
  } else {
    const v = sideVerdicts(plan, d.in_force_by_side || null);
    const yes = v.filter((x) => x.res === true).map((x) => x.side);
    const keep = v.filter((x) => x.res !== true).map((x) => x.side);
    if (!v.length) decision = "No preferred setting could be formed";
    else if (!yes.length) decision = keep.length > 1 ? "Keep today's setting on both sides" : `Keep today's setting on ${keep[0]}`;
    else if (!keep.length) decision = yes.length > 1 ? "A better setting is proven on both sides" : `A better setting is proven on ${yes[0]}`;
    else decision = `A better setting is proven on ${yes.join(" and ")}; keep today's on ${keep.join(" and ")}`;
  }
  const gate = (plan && plan.gate) || {};
  const conditions = Array.isArray(gate.conditions) ? gate.conditions : [];
  let loop;
  if (!plan) loop = "closed loop not yet checked";
  else if (!conditions.length) loop = "closed loop was not checked";
  else loop = gate.passed === true ? "closed loop may start" : "closed loop cannot start";
  const headline = `${decision}; ${loop}.`;

  // ---- the bullets -----------------------------------------------------------------------
  const bullets = [];
  const add = (kind, text, detail, extra = {}) => {
    if (!bullets.some((b) => b.text === text)) bullets.push({ kind, text, detail: detail || null, ...extra });
  };

  // The device's sensing rule, read off the readiness screen.
  const cl = d.closed_loop || null;
  if (cl && cl.available) {
    const rule = cl.sensing_rule || null;
    const sides = rule && rule.by_side ? Object.values(rule.by_side).filter(Boolean) : [];
    const allowed = sides.filter((b) => b.allowed_channel);
    if (sides.some((b) => b.rule_applied) && !allowed.length) {
      add("red", "Device allows no sensing pair", rule.sentence);
    } else if (allowed.length && allowed.every((b) => !num(b.n_usable_on_allowed_pair))) {
      add("red", "No usable sensing pair", rule.sentence);
    } else if (!rule && cl.ready === false) {
      add("red", "No usable sensing pair",
        `${num(cl.n_cells_deployable) ?? 0} of ${num(cl.n_cells_screened) ?? "—"} contact-and-rate combinations are usable.`);
    }
  }

  // Each of the four checks: red when it blocks, yellow when it was not assessed.
  conditions.forEach((c) => {
    const st = verdictState(c);
    if (st === false && RED_NAME[c.name]) add("red", RED_NAME[c.name](c), c.detail);
    if (st === null && YELLOW_NAME[c.name]) add("yellow", YELLOW_NAME[c.name](c), c.detail);
  });
  // A pulse-width choice never put to the data, on every side.
  const choice = conditions.find((c) => c && c.name === "openloop_choice_resolved");
  const per = choice && choice.evidence && choice.evidence.per_hemisphere;
  if (per && verdictState(choice) !== null) {
    const sides = Object.values(per).filter(Boolean);
    if (sides.length && sides.every((p) => p.pw_resolved === null || p.pw_resolved === undefined)) {
      const why = sides.flatMap((p) => (Array.isArray(p.reasons) ? p.reasons : []))
        .find((t) => /pulse-width choice is NOT ASSESSED/i.test(String(t)));
      add("yellow", "Pulse width not assessed", why || null);
    }
  }

  // The pain map the decision reads: what the next visit must deliver, and whether it moves.
  const settings = (((plan && plan.stage1) || {}).frozen_configuration || {}).settings || [];
  const chosen = settings.find((s) => s && num(s.rate_hz) !== null) || null;
  const row = chosen ? rateRowForSetting(plan, chosen) : null;
  const clinicNext = ((((plan && plan.stage1) || {}).clinic_stream) || {}).next_session_coverage || null;
  if (row && row.fitted && row.coverage_passes === false) {
    const n = num((row.coverage_gap || {}).n_pairs_missing);
    add("yellow", n ? `Next visit: ${plural(n, "pair", "pairs")} short` : "Current map too thin",
      (row.coverage_gap || {}).cheapest_way || null);
  } else if (clinicNext && clinicNext.available && (clinicNext.coverage || {}).passes === false) {
    const n = num((clinicNext.gap || {}).n_pairs_missing);
    add("yellow", n ? `Next visit: ${plural(n, "pair", "pairs")} short` : "Current map too thin",
      [clinicNext.sentence, (clinicNext.gap || {}).cheapest_way].filter(Boolean).join(" "));
  }
  if (row && blockOfTimeState(row) === "moves") {
    add("yellow", "Pain map moves over time", BLOCK_OF_TIME_NOTE, { dagger: true });
  }

  // Red first, each kind in the order found.
  const ordered = [...bullets.filter((b) => b.kind === "red"), ...bullets.filter((b) => b.kind === "yellow")];
  return { headline, bullets: ordered };
}

function Bullet({ b }) {
  const k = KIND[b.kind];
  return (
    <MDBox component="li" data-testid="status-bullet" data-kind={b.kind} aria-label={`${k.word}: ${b.text}`}
      sx={{ display: "inline-flex", alignItems: "center", gap: 0.7, px: 1, py: 0.4, borderRadius: "4px",
        backgroundColor: k.fill, listStyle: "none" }}>
      <span data-testid="status-glyph" aria-hidden="true" style={{ color: k.ink, fontSize: 13, lineHeight: 1 }}>
        {STATUS_GLYPH[b.kind]}
      </span>
      <span data-testid="status-text" style={{ color: "#1A1A1A", fontSize: TYPE.body, fontWeight: 600, whiteSpace: "nowrap" }}>
        {b.text}
        {b.dagger ? <sup style={{ color: k.ink, fontWeight: 700, marginLeft: 2 }}>{BLOCK_OF_TIME_SYMBOL}</sup> : null}
      </span>
    </MDBox>
  );
}

export default function StatusLine({ data, plan, planLoading = false }) {
  const s = statusSummary(data, plan);
  const withDetail = s.bullets.filter((b) => b.detail);
  return (
    <MDBox data-testid="status-line">
      <MDTypography variant="h6" component="div" sx={{ fontSize: TYPE.headline, color: "#1A1A1A", lineHeight: 1.3 }}>
        {planLoading && !plan ? "Comparing with today's setting; the plan is still being computed." : s.headline}
      </MDTypography>
      {s.bullets.length > 0 && (
        <MDBox component="ul" sx={{ display: "flex", flexWrap: "wrap", gap: "8px", m: 0, mt: 1, p: 0 }}>
          {s.bullets.map((b) => <Bullet key={b.text} b={b} />)}
        </MDBox>
      )}
      {s.bullets.length > 0 && (
        <MDTypography variant="caption" component="div" sx={{ ...SMALL, mt: 0.6 }}>
          <span aria-hidden="true" style={{ color: KIND.red.ink }}>{STATUS_GLYPH.red}</span> blocks closed loop
          {"   "}
          <span aria-hidden="true" style={{ color: KIND.yellow.ink, marginLeft: 10 }}>{STATUS_GLYPH.yellow}</span> not evaluated
        </MDTypography>
      )}
      {withDetail.length > 0 && (
        <SizedFold show="What each item rests on" hide="Hide">
          <MDBox component="dl" data-testid="status-details"
            sx={{ m: 0, "& dt": { fontSize: TYPE.small, fontWeight: 700, color: "#1A1A1A", mt: 0.6 },
              "& dd": { m: 0, fontSize: TYPE.small, lineHeight: 1.4, color: "#3E3E3E" } }}>
            {withDetail.map((b) => (
              <MDBox key={b.text}>
                <dt>{`${STATUS_GLYPH[b.kind]} ${b.text}${b.dagger ? ` ${BLOCK_OF_TIME_SYMBOL}` : ""}`}</dt>
                <dd>{String(b.detail).replace(/ -- /g, " — ")}</dd>
              </MDBox>
            ))}
          </MDBox>
        </SizedFold>
      )}
    </MDBox>
  );
}
