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
 *
 * THE MINIMALIST REDESIGN OF 2026-09-26 (SPEC.md sections 2.3, 4 and 5.3): three states, never two.
 * A device refusal or a value above the ceiling is red with ✕; a statistical or evidence result
 * that blocks is ink with ✕ (the PI's ruling of 2026-09-26, TASTE_AUDIT.md D14); a caution (more data needed, a map that moves over time) is
 * amber with ▲; a check that could not run is grey with ○ -- it still blocks, but it is counted
 * apart and never drawn as a pass. At most five items are shown: every ✕ and ▲ first, then the ○
 * items, and when these would overflow they are counted in one item ("3 checks not run"), each
 * named in the fold underneath. The glyph key reads "✕ blocks · ▲ needs more data or caution ·
 * ○ not checked".
 */
import MDBox from "components/MDBox";
import MDTypography from "components/MDTypography";

import { num, fmtHz } from "./stimFormat";
import { T, TYPE, WEIGHT, STATE, WRAP, SizedFold } from "./typeScale";
import { sideVerdicts } from "./DecisionStrip";
// Which of the four checks, failing, is the device refusing or the ceiling (red): one home.
import { verdictState, REFUSED_CHECKS } from "./ClosedLoopChecks";
import {
  BLOCK_OF_TIME_NOTE, BLOCK_OF_TIME_SYMBOL, blockOfTimeState, rateRowForSetting,
} from "./blockOfTime";

/** The glyph each kind of item carries beside its colour: ✕ refused (red) or blocks (ink), ▲ a
 *  caution, ○ could not be checked. */
export const STATUS_GLYPH = {
  refused: STATE.refused.glyph, blocked: STATE.blocked.glyph, yellow: STATE.caution.glyph, grey: STATE.notChecked.glyph,
};

/**
 * The token state, and the word a screen reader hears, per kind. RED MEANS ONE THING (the PI's
 * ruling of 2026-09-26, TASTE_AUDIT.md D14): `refused` -- the device refuses (no sensing pair it
 * allows, a rate below the closed-loop minimum the device needs) or a value is above the safe
 * current ceiling -- is red with ✕; `blocked` -- a statistical or evidence result that stops closed
 * loop ("Setting not proven better", "No usable sensing pair", "No band moves with current") -- is
 * ink with the same ✕, never red.
 */
const KIND = {
  refused: { state: STATE.refused, word: "refused" },
  blocked: { state: STATE.blocked, word: "blocked" },
  yellow: { state: STATE.caution, word: "caution" },
  grey: { state: STATE.notChecked, word: "not checked" },
};

/** At most this many items in the open (SPEC.md section 4, rule 1). */
export const MAX_ITEMS = 5;

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
const GREY_NAME = {
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
      add("refused", "Device allows no sensing pair", rule.sentence);
    } else if (allowed.length && allowed.every((b) => !num(b.n_usable_on_allowed_pair))) {
      add("blocked", "No usable sensing pair", rule.sentence);
    } else if (!rule && cl.ready === false) {
      add("blocked", "No usable sensing pair",
        `${num(cl.n_cells_deployable) ?? 0} of ${num(cl.n_cells_screened) ?? "—"} contact-and-rate combinations are usable.`);
    }
  }

  // Each of the four checks: refused (red) or blocked (ink) when it fails, grey when not assessed.
  conditions.forEach((c) => {
    const st = verdictState(c);
    if (st === false && RED_NAME[c.name]) add(REFUSED_CHECKS.has(c.name) ? "refused" : "blocked", RED_NAME[c.name](c), c.detail);
    if (st === null && GREY_NAME[c.name]) add("grey", GREY_NAME[c.name](c), c.detail);
  });
  // A pulse-width choice never put to the data, on every side.
  const choice = conditions.find((c) => c && c.name === "openloop_choice_resolved");
  const per = choice && choice.evidence && choice.evidence.per_hemisphere;
  if (per && verdictState(choice) !== null) {
    const sides = Object.values(per).filter(Boolean);
    if (sides.length && sides.every((p) => p.pw_resolved === null || p.pw_resolved === undefined)) {
      const why = sides.flatMap((p) => (Array.isArray(p.reasons) ? p.reasons : []))
        .find((t) => /pulse-width choice is NOT ASSESSED/i.test(String(t)));
      add("grey", "Pulse width not assessed", why || null);
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

  // Refusals first, then what blocks, then yellow, then grey, each kind in the order found.
  const ordered = ["refused", "blocked", "yellow", "grey"].flatMap((k) => bullets.filter((b) => b.kind === k));
  return { headline, bullets: ordered };
}

/**
 * The items drawn in the open: every refused, blocked and yellow one, then the grey ones while there is room;
 * when the grey ones would overflow, one item counts them ("3 checks not run"). Nothing is
 * dropped: each is named in the fold underneath.
 */
export function shownItems(bullets, max = MAX_ITEMS) {
  const strong = bullets.filter((b) => b.kind !== "grey");
  const grey = bullets.filter((b) => b.kind === "grey");
  const room = Math.max(0, max - strong.length);
  if (grey.length <= room) return [...strong, ...grey];
  const keep = Math.max(0, room - 1);
  const rest = grey.slice(keep);
  return [...strong, ...grey.slice(0, keep),
    { kind: "grey", text: `${rest.length} checks not run`, detail: null, counted: rest.map((b) => b.text) }];
}

function Bullet({ b }) {
  const k = KIND[b.kind];
  const label = b.counted ? `${b.text}: ${b.counted.join(", ")}` : b.text;
  return (
    <MDBox component="li" data-testid="status-bullet" data-kind={b.kind} aria-label={`${k.word}: ${label}`}
      sx={{ display: "inline-flex", alignItems: "baseline", gap: 0.75, listStyle: "none" }}>
      <span data-testid="status-glyph" aria-hidden="true"
        style={{ color: k.state.ink, fontSize: TYPE.body, fontWeight: WEIGHT.strong, lineHeight: 1 }}>
        {STATUS_GLYPH[b.kind]}
      </span>
      <span data-testid="status-text" style={{ color: k.state.ink, fontSize: TYPE.body,
        fontWeight: b.kind === "grey" ? WEIGHT.regular : WEIGHT.strong, whiteSpace: "nowrap" }}>
        {b.text}
        {b.dagger ? <sup style={{ fontWeight: WEIGHT.strong, marginLeft: 2 }}>{BLOCK_OF_TIME_SYMBOL}</sup> : null}
      </span>
    </MDBox>
  );
}

/** The one-line key of the three glyphs. */
function GlyphKey() {
  return (
    <MDTypography variant="caption" component="div" sx={{ fontSize: TYPE.small, color: T.ink3, mt: 1 }}>
      {["blocked", "yellow", "grey"].map((k, i) => (
        <span key={k}>
          {i > 0 ? " · " : ""}
          <span aria-hidden="true" style={{ color: KIND[k].state.ink }}>{STATUS_GLYPH[k]}</span>
          {` ${{ blocked: "blocks", yellow: "needs more data or caution", grey: "not checked" }[k]}`}
        </span>
      ))}
    </MDTypography>
  );
}

/** The status sentence alone, for the page head (22 px, the page's answer). */
export function StatusSentence({ data, plan, planLoading = false }) {
  const s = statusSummary(data, plan);
  return planLoading && !plan ? "Comparing with today's setting; the plan is still being computed." : s.headline;
}

/** The status list, its key and the fold naming what each item rests on. */
export default function StatusLine({ data, plan, planLoading = false, showHeadline = true }) {
  const s = statusSummary(data, plan);
  const items = shownItems(s.bullets);
  const withDetail = s.bullets.filter((b) => b.detail);
  return (
    <MDBox data-testid="status-line">
      {showHeadline && (
        <MDTypography variant="h6" component="p" role="status"
          sx={{ fontSize: TYPE.headline, lineHeight: "29px", fontWeight: WEIGHT.strong, color: T.ink, m: 0, ...WRAP.balance }}>
          {planLoading && !plan ? "Comparing with today's setting; the plan is still being computed." : s.headline}
        </MDTypography>
      )}
      {items.length > 0 && (
        <MDBox component="ul" aria-label="Status"
          sx={{ display: "flex", flexWrap: "wrap", columnGap: "24px", rowGap: "8px", m: 0, mt: 1.5, p: 0 }}>
          {items.map((b) => <Bullet key={b.text} b={b} />)}
        </MDBox>
      )}
      {items.length > 0 && <GlyphKey />}
      {withDetail.length > 0 && (
        <SizedFold show="What each item rests on" hide="Hide">
          <MDBox component="dl" data-testid="status-details"
            sx={{ m: 0, "& dt": { fontSize: TYPE.body, fontWeight: WEIGHT.strong, color: T.ink, mt: 1 },
              "& dd": { m: 0, fontSize: TYPE.body, lineHeight: 1.57, color: T.ink2 } }}>
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
