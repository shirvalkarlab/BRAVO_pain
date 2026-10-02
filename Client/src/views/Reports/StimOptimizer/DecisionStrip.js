/**
 * The decision strip at the top of the Stim Optimizer page: one row per side, the setting
 * programmed now beside the setting the search prefers, the difference between them marked, and
 * the one number the verdict rests on -- the predicted gain against its own uncertainty -- drawn
 * rather than described.
 *
 * Added 2026-09-12 (PI: "prioritize display of actionable items and use visuals instead of text
 * when possible to communicate outcomes"). Everything here is READ from the two responses the page
 * already holds; nothing is recomputed:
 *
 *   - the setting in force: `in_force_by_side` when the response carries it (a later phase adds
 *     it), else the rate and current from the arm's `incumbent_xy` and the pulse width from the
 *     two-stage block's `incumbent_pulse_width_us`. That pulse width is read from the LEFT column
 *     by Stage 1 (`stage1_openloop.run_stage1`, `pw_col="pw_us_Left"`), so it is shown for the Left
 *     side only; the Right side prints "not given" until the response names its own.
 *   - the setting the search prefers: the two-stage block's frozen setting for that side (rate,
 *     pulse width, preferred current, delivered range, the stretches fitted), because that is the
 *     setting closed loop would freeze and it is held to what adaptive mode can use.
 *   - the gain, its uncertainty and the verdict: the frozen setting's own `gain`,
 *     `sd_of_difference` and `resolved` (rate and pulse-width pair, the verdict the gate reads),
 *     and the stopping rule from the stratum row of the JOINT pair that setting was chosen from
 *     (2026-09-26; before, the stratum row's rate-only `optimum_resolved`, matched on one side's
 *     pulse width).
 *
 * THREE STATES, as everywhere in this family (decision 122, and this page's own header note): a
 * tick for resolved; an amber disc for "not resolved" (measured and too small to call -- never the
 * failure ink, since no setting has been shown worse); an open dashed circle for "not determinable"
 * (the difference could not be formed). The words sit beside the symbols.
 *
 * Resized 2026-09-12 after the PI's review ("text running into images"): the three numbers of a
 * setting at 16 px, the sub-lines at 12 px, the gain in a cell of its own that cannot wrap, and
 * the gain bar's axis labels at 11 px.
 *
 * THE DESIGN REVIEW OF 2026-09-26 (the PI: "yes to all six, build them"):
 *   - the definition of "proven better", the exposure line and the stopping rule (decisions
 *     243(b), 243(d) and 245(b), which printed them in the open) sit in ONE fold under the strip;
 *   - the stopping rule prints once, "Both sides: ...", when the two sides read alike;
 *   - "resolved" is "proven better" everywhere, the word the headline already used;
 *   - "no current can be recommended" is ONE sentence under the rows, not one per side;
 *   - the columns fit a laptop's card (about 860 px at their minimum, was about 1,330 px): the gain
 *     bar sits under the gain's number, in the same cell.
 *
 * THE MINIMALIST REDESIGN OF 2026-09-26 (SPEC.md section 5.3, §1): per side, an aligned comparison
 * Today | Suggested | Difference with one row each for rate, pulse width and current, a zero
 * difference reading "same"; the gain as a sentence, then the gain bar (the interval in grey, the
 * point in the accent blue, "worse" and "better" at its ends, in pain points). Colours and sizes
 * come from the shared tokens; the verdict carries its glyph (✓ ▲ ○) as well as its words.
 */
import { memo } from "react";
import { Tooltip } from "@mui/material";

import MDBox from "components/MDBox";
import MDTypography from "components/MDTypography";

import { GainBar, VerdictGlyph } from "./GainBar";
import { T, TYPE, HEAD, SMALL, MONO, SUBHEAD, WEIGHT, HAIRLINE, Mark, Placeholder, SizedFold } from "./typeScale";

import { num, fmtMa, fmtHz, fmtUs, fmtPts, fmtDelta, contactLabel, EMPTY } from "./stimFormat";
import { BlockOfTimeMark, BlockOfTimeFootnote, blockOfTimeState, notCheckedText, rateRowForSetting } from "./blockOfTime";

const VALUE = { ...MONO, fontSize: TYPE.num };
const NW = { whiteSpace: "nowrap" };

/** A difference in one unit, "same" when there is none (SPEC.md section 5.3), "not given" when
 *  either side of it is missing (TASTE_AUDIT.md C9: an empty cell is a word, never "—"). */
function diffText(v, unit, d) {
  const x = num(v);
  if (x === null) return EMPTY;
  if (Math.abs(x) < 1e-9) return "same";
  return fmtDelta(x, unit, d);
}

/**
 * The stratum row a side's frozen setting was chosen from. Strata are JOINT (left pulse width, right
 * pulse width) pairs, one row per side of each; the setting names its pair in
 * `detail.best_pw_us_left` / `best_pw_us_right`. A response without that pair falls back to this
 * side's own pulse width, and only when exactly one stratum matches it (2026-09-26: matching on one
 * side's width picked up another pair's gain and stopping rule).
 */
function stratumForSetting(strata, side, s) {
  const d = (s && s.detail) || {};
  const bl = num(d.best_pw_us_left), br = num(d.best_pw_us_right);
  const same = (a, b) => a !== null && b !== null && Math.abs(a - b) < 1e-9;
  if (bl !== null && br !== null) {
    return strata.find((r) => r && r.hemisphere === side
      && same(num(r.pw_us_left), bl) && same(num(r.pw_us_right), br)
      && (r.left_contact ?? null) === (d.left_contact ?? null)) || null;
  }
  const byOwn = strata.filter((r) => r && r.hemisphere === side && same(num(r.pw_us), num(s && s.pulse_width_us)));
  return byOwn.length === 1 ? byOwn[0] : null;
}

/**
 * A side's three-state verdict, read from the frozen setting the server computed it for
 * (`HemisphereSetting.resolved`: the rate AND the pulse-width pair resolved; the rate is downgraded
 * when no current can be recommended). true = proven better; false = measured and not shown (either
 * comparison measured and not cleared); null = not determinable (the rate comparison could not be
 * formed, or the rate cleared and the pulse-width pair could not be compared). A response that
 * predates the two parts reads its `resolved`; with no setting at all, the stratum row's own.
 */
function settingVerdict(s, st) {
  if (s) {
    if (s.resolved === true) return true;
    if (s.rate_resolved !== undefined || s.pulse_width_resolved !== undefined) {
      if (s.rate_resolved === null) return null;
      if (s.rate_resolved === false || s.pulse_width_resolved === false) return false;
      return null;
    }
    return s.resolved === false ? false : null;
  }
  if (st) return st.optimum_resolved === true ? true : (st.optimum_resolved === false ? false : null);
  return null;
}

/** The predicted change and its uncertainty a side prints and draws: the frozen setting's own,
 * else its stratum's; none when the server discarded it (the chosen stratum never delivered the rate
 * in force, so the difference is an extrapolation: `rate_resolved` null, the reasons say
 * "discarded rather than reported"). */
function sideGain(r) {
  const s = r.s, st = r.stratum;
  const discarded = (s && s.rate_resolved === null)
    || (st && st.incumbent_rate_supported === false)
    || (!s && st && st.optimum_resolved === null);
  if (discarded) return { gain: null, sd: null };
  const g = num(s && s.gain) ?? num(st && st.gain);
  const sd = num(s && s.sd_of_difference) ?? num(st && st.sd_of_difference);
  return { gain: g, sd: g === null ? null : sd };
}

function sideRows(arms, plan, inForce) {
  const fc = ((plan && plan.stage1) || {}).frozen_configuration || {};
  const settings = Array.isArray(fc.settings) ? fc.settings : [];
  const strata = Array.isArray(((plan && plan.stage1) || {}).strata) ? plan.stage1.strata : [];
  const sides = [];
  ["Left", "Right"].forEach((side) => {
    const armsOnSide = Object.values(arms || {}).filter((a) => a && a.hemisphere === side);
    const s = settings.find((x) => x && x.hemisphere === side) || null;
    if (!armsOnSide.length && !s) return;
    const inf = (inForce && inForce[side]) || null;
    const xy = (armsOnSide[0] && armsOnSide[0].incumbent_xy) || [null, null];
    const nowRate = num(inf && inf.rate_hz) ?? num(fc.incumbent_rate_hz) ?? num(xy[0]);
    const nowPw = num(inf && inf.pulse_width_us) ?? (side === "Left" ? num(fc.incumbent_pulse_width_us) : null);
    const nowAmp = num(inf && inf.amplitude_mA) ?? num(xy[1]);
    const stratum = s ? stratumForSetting(strata, side, s) : null;
    sides.push({ side, s, inf, nowRate, nowPw, nowAmp, stratum, contacts: inf ? contactLabel(inf) : null });
  });
  return sides;
}

/**
 * The search's own stopping rule for one side, in words (the PI, 2026-09-23: show its result; until
 * then it was computed on every request, serialised as `stop` / `stop_binding` / `queue_size` on the
 * stratum, and read by no card). Three answers:
 *   - stop: the best has stopped improving AND no untried combination still looks worth trying;
 *   - keep searching: untried combinations still look worth trying (the count is `queue_size`);
 *   - not assessable: the "has the best stopped improving" half needs a history of completed
 *     batches, and this platform proposes batches without running them in turn, so there is none
 *     (`routines.acquisition.NO_HISTORY_BINDING`). Said as that, never as a "no".
 */
export function stoppingLine(side, st) {
  const body = stoppingBody(st);
  return body === null ? null : `${side}: ${body}`;
}

/** The answer without its side, so two sides that read alike print it once. */
function stoppingBody(st) {
  if (!st || st.stop_binding === undefined) return null;
  const n = num(st.queue_size);
  const worth = n === null ? "" : ` ${Math.round(n).toLocaleString("en-US")} untried combination${n === 1 ? "" : "s"} still ${n === 1 ? "looks" : "look"} worth trying`;
  if (st.stop === true) {
    return "stop — the best has stopped improving and no untried combination still looks worth trying";
  }
  if (/not assessable/i.test(String(st.stop_binding || ""))) {
    return `not assessable — no batch of suggested settings has been run and rated in turn, so there is no history to tell whether the best has stopped improving;${worth}`;
  }
  return `keep searching —${worth}`;
}

/** The stopping rule for every side on the strip, ONCE when the sides read alike ("Both sides:
 * ..."), otherwise per side (the design review of 2026-09-26: the same 45 words printed twice). */
export function stoppingText(rows) {
  const per = rows.map((r) => ({ side: r.side, body: stoppingBody(r.stratum) })).filter((x) => x.body !== null);
  if (!per.length) return null;
  if (per.length > 1 && per.every((x) => x.body === per[0].body)) {
    return `${per.length === 2 ? "Both sides" : "Every side"}: ${per[0].body}`;
  }
  return per.map((x) => `${x.side}: ${x.body}`).join(". ");
}

/** A side's three-state verdict, read exactly as the row's glyph reads it. */
function sideResolved(r) {
  return settingVerdict(r.s, r.stratum);
}

/**
 * The decision card's title, COMPUTED from the per-side verdicts in the same render (panel C item
 * 5; report C §5.3; the figure convention that a headline states what the data show). It used to
 * read "What the joint search prefers, per side", a description of the method rather than the
 * answer. Three states, never two: a side whose comparison could not be formed is not "not
 * proven", and the title does not say it is.
 */
/** Each side's three-state verdict (true / false / null), the one the headline, the row's glyph
 * and the page's status line all read. */
export function sideVerdicts(plan, inForce) {
  return sideRows({}, plan, inForce).filter((r) => r.s || r.stratum)
    .map((r) => ({ side: r.side, res: sideResolved(r) }));
}

export function decisionHeadline(plan, inForce) {
  const v = sideVerdicts(plan, inForce);
  if (!v.length) return "Suggested setting, per side (one closed loop could use)";
  const yes = v.filter((x) => x.res === true).map((x) => x.side);
  const no = v.filter((x) => x.res === false).map((x) => x.side);
  const unformed = v.filter((x) => x.res === null).map((x) => x.side);
  if (yes.length === v.length) {
    return v.length === 1 ? `${yes[0]} has a setting proven better than today's`
      : "Both sides have a setting proven better than today's";
  }
  if (!yes.length && unformed.length === v.length) {
    return "No side's preferred setting could be compared with today's";
  }
  if (!yes.length) return "No side has a setting proven better than today's";
  const rest = v.filter((x) => x.res !== true).map((x) => (x.res === null
    ? `${x.side} could not be compared` : `${x.side} does not`));
  return `${yes.join(" and ")} has a setting proven better than today's; ${rest.join("; ")}`;
}

// Two side blocks next to each other on a wide card, one above the other on a narrow one.
// `min(320px, 100%)`: on a phone the one column is the card's own width, never wider.
const SIDES_GRID = "repeat(auto-fit, minmax(min(320px, 100%), 1fr))";
const COMPARE = "minmax(96px, 0.9fr) minmax(80px, 1fr) minmax(96px, 1.1fr) minmax(72px, 0.8fr)";
const GAIN_BAR_WIDTH = 240;

/** One side: the aligned comparison, the lines under it, the gain as a sentence and its bar. */
function SideBlock({ r, plan, planLoading, planErr, halfRange, timeState, timeNotChecked }) {
  const s = r.s;
  const prefRate = num(s && s.rate_hz), prefPw = num(s && s.pulse_width_us),
    prefAmp = num(s && s.amplitude_preferred_mA);
  const dMax = num(s && s.amplitude_delivered_max_mA), dMin = num(s && s.amplitude_delivered_min_mA);
  const aboveDelivered = prefAmp !== null && dMax !== null && prefAmp > dMax + 1e-9;
  const { gain, sd } = sideGain(r);
  const resolved = sideResolved(r);
  const nFit = num(s && s.n_epochs_fitted_on_the_chosen_stratum);
  const cellLine = { borderTop: HAIRLINE, py: 0.75 };
  const suggested = (row) => {
    // Still computing: a still grey block shaped like the value (TASTE_AUDIT.md C2), the waiting
    // words under the rate's block. No spinner; nothing moves.
    if (planLoading && !s) return row === "rate" ? (
      <MDBox>
        <Placeholder width={56} />
        <span style={{ ...SMALL, display: "block" }}>computing (about a minute the first time)</span>
      </MDBox>) : <Placeholder width={56} />;
    if (!s) return row === "rate" ? <span style={SMALL}>{planErr ? `plan unavailable: ${planErr}` : EMPTY}</span> : null;
    if (prefRate === null) return row === "rate"
      ? <span style={{ fontSize: TYPE.body, fontWeight: WEIGHT.strong, color: T.caution }}><span aria-hidden="true">▲ </span>no rate closed loop can use</span> : null;
    if (row === "rate") return <span style={VALUE}>{fmtHz(prefRate)}</span>;
    if (row === "pw") return <span style={VALUE}>{prefPw === null ? EMPTY : fmtUs(prefPw)}</span>;
    return prefAmp === null
      ? <span style={{ fontSize: TYPE.body, fontWeight: WEIGHT.strong, color: T.caution }}><span aria-hidden="true">▲ </span>no current</span>
      : <span style={VALUE}>{fmtMa(prefAmp)}{timeState(r) === "moves" && <BlockOfTimeMark />}</span>;
  };
  const difference = (row) => {
    if (planLoading && !s) return <Placeholder width={48} />;
    if (!s || prefRate === null) return <span style={VALUE}>{EMPTY}</span>;
    if (row === "rate") return <span style={VALUE}>{diffText(prefRate - (r.nowRate ?? prefRate), "Hz", 0)}</span>;
    if (row === "pw") return <span style={VALUE}>{r.nowPw === null || prefPw === null ? EMPTY : diffText(prefPw - r.nowPw, "µs", 0)}</span>;
    return (
      <MDBox display="inline-flex" alignItems="center" gap={0.6}>
        <span style={VALUE}>{prefAmp === null || r.nowAmp === null ? EMPTY : diffText(prefAmp - r.nowAmp, "mA", 1)}</span>
        {aboveDelivered && (
          <Tooltip title={`the suggested ${fmtMa(prefAmp)} is above the ${fmtMa(dMax)} ever delivered on this side, so it is a guess beyond any current this side has received`}>
            <span><Mark state="caution" label="above the highest current ever delivered on this side" /></span>
          </Tooltip>
        )}
      </MDBox>
    );
  };
  const rows = [
    ["rate", "Rate", <span key="t" style={VALUE}>{fmtHz(r.nowRate)}</span>],
    ["pw", "Pulse width", <span key="t" style={VALUE}>{r.nowPw === null ? EMPTY : fmtUs(r.nowPw)}</span>],
    ["amp", "Current", <span key="t" style={VALUE}>{fmtMa(r.nowAmp)}</span>],
  ];
  return (
    <MDBox data-testid="decision-side" data-side={r.side} sx={{ minWidth: 0 }}>
      <MDTypography component="div" sx={SUBHEAD}>
        {r.side}
        <span style={{ ...SMALL, fontWeight: WEIGHT.regular, marginLeft: 8 }}>
          {r.contacts ? <>contacts <span style={NW}>{r.contacts}</span></> : "contacts: not in the response"}
        </span>
      </MDTypography>
      {/* The Today | Suggested | Difference table scrolls inside its own wrapper when the card is
          narrower than its columns (a phone), so the page never scrolls sideways (SPEC 2.5). */}
      <MDBox data-compare-scroll="" data-scroll-x="" sx={{ overflowX: "auto", maxWidth: "100%" }}>
        <MDBox mt={1} sx={{ display: "grid", gridTemplateColumns: COMPARE, columnGap: "12px", alignItems: "baseline" }}>
          <span />
          <MDTypography variant="caption" sx={{ ...HEAD, pb: 0.5 }}>Today</MDTypography>
          <MDTypography variant="caption" sx={{ ...HEAD, pb: 0.5 }}>Suggested</MDTypography>
          <MDTypography variant="caption" sx={{ ...HEAD, pb: 0.5 }}>Difference</MDTypography>
          {rows.map(([key, label, today]) => [
            <MDBox key={`${key}-l`} sx={cellLine}><span style={{ fontSize: TYPE.body, color: T.ink2 }}>{label}</span></MDBox>,
            <MDBox key={`${key}-t`} sx={cellLine}>{today}</MDBox>,
            <MDBox key={`${key}-s`} sx={cellLine}>{suggested(key)}</MDBox>,
            <MDBox key={`${key}-d`} sx={cellLine}>{difference(key)}</MDBox>,
          ])}
        </MDBox>
      </MDBox>
      {r.nowPw === null && (
        <MDTypography variant="caption" component="div" sx={{ ...SMALL, mt: 0.5 }}>
          pulse width in force: not in the response for this side
        </MDTypography>
      )}
      {/* Review S7 (2026-09-12): the setting in force is the newest DEVICE setting, rated or not;
          when no rating has been filed under it yet the gains are still measured against the
          newest RATED setting, and the side says so. */}
      {r.inf && r.inf.has_ratings_yet === false && (
        <MDTypography variant="caption" component="div" sx={{ ...SMALL, mt: 0.5, color: T.caution }}>
          {`▲ no pain rating filed under this setting yet · gains are measured against the newest rated setting${num(r.inf.fitted_incumbent_epoch) !== null ? ` (stretch ${Math.round(num(r.inf.fitted_incumbent_epoch))})` : ""}`}
        </MDTypography>
      )}
      {timeNotChecked(r) && (
        <MDTypography variant="caption" component="div" sx={{ ...SMALL, mt: 0.5 }}>
          {`current ${timeNotChecked(r)}`}
        </MDTypography>
      )}
      {s && (dMin !== null || nFit !== null) && (
        <MDTypography variant="caption" component="div" sx={{ ...SMALL, mt: 0.5 }}>
          {dMin !== null && dMax !== null
            ? <>delivered so far <span style={NW}>{`${dMin.toFixed(1)}–${dMax.toFixed(1)} mA`}</span></> : ""}
          {nFit !== null
            ? <>{dMin !== null && dMax !== null ? " · " : ""}fitted on <span style={NW}>{`${Math.round(nFit)} stretches`}</span> of unchanged settings</> : ""}
        </MDTypography>
      )}
      <MDTypography variant="caption" component="div" sx={{ fontSize: TYPE.body, color: T.ink2, mt: 1.5, maxWidth: "68ch" }}>
        {gain === null
          ? "Predicted change in pain against today's setting: no difference could be formed."
          : <>Predicted change in pain against today&apos;s setting:{" "}
            <span style={{ ...VALUE, fontWeight: WEIGHT.strong }}>{fmtPts(gain).replace(/ pts$/, " pain points")}</span>
            {sd === null ? "." : <>, with an uncertainty of <span style={VALUE}>{`± ${sd.toFixed(2)}`}</span> (1 standard deviation).</>}</>}
      </MDTypography>
      <MDBox mt={0.5} display="flex" alignItems="center" columnGap={2} rowGap={0.5} flexWrap="wrap">
        <GainBar gain={gain} sd={sd} halfRange={halfRange} width={GAIN_BAR_WIDTH} />
        <VerdictGlyph resolved={resolved} />
      </MDBox>
    </MDBox>
  );
}

/** The strip's shape, still, while the plan is computed: two sides, three rows, four columns. */
export function DecisionStripLoading() {
  const cellLine = { borderTop: HAIRLINE, py: 0.75 };
  return (
    <MDBox data-testid="decision-strip-loading" aria-busy="true">
      <MDBox sx={{ display: "grid", gridTemplateColumns: SIDES_GRID, columnGap: "48px", rowGap: "32px" }}>
        {["Left", "Right"].map((side) => (
          <MDBox key={side} sx={{ minWidth: 0 }}>
            <MDTypography component="div" sx={SUBHEAD}>{side}</MDTypography>
            <MDBox mt={1} sx={{ display: "grid", gridTemplateColumns: COMPARE, columnGap: "12px", alignItems: "baseline" }}>
              <span />
              <MDTypography variant="caption" sx={{ ...HEAD, pb: 0.5 }}>Today</MDTypography>
              <MDTypography variant="caption" sx={{ ...HEAD, pb: 0.5 }}>Suggested</MDTypography>
              <MDTypography variant="caption" sx={{ ...HEAD, pb: 0.5 }}>Difference</MDTypography>
              {["Rate", "Pulse width", "Current"].map((label) => [
                <MDBox key={`${label}-l`} sx={cellLine}><span style={{ fontSize: TYPE.body, color: T.ink2 }}>{label}</span></MDBox>,
                <MDBox key={`${label}-t`} sx={cellLine}><Placeholder width={56} /></MDBox>,
                <MDBox key={`${label}-s`} sx={cellLine}><Placeholder width={56} /></MDBox>,
                <MDBox key={`${label}-d`} sx={cellLine}><Placeholder width={48} /></MDBox>,
              ])}
            </MDBox>
            <Placeholder width={GAIN_BAR_WIDTH} height={12} mt={12} />
          </MDBox>
        ))}
      </MDBox>
      <MDTypography variant="caption" component="div" sx={{ ...SMALL, mt: 1.5 }}>
        computing (about a minute the first time)
      </MDTypography>
    </MDBox>
  );
}

function DecisionStrip({ arms, plan, planLoading, planErr, inForce }) {
  const rows = sideRows(arms, plan, inForce);
  const halfRange = Math.max(2, ...rows.map((r) => {
    const { gain: g, sd } = sideGain(r);
    return g === null ? 0 : Math.ceil(Math.abs(g) + (sd || 0));
  }));
  const exposure = (((plan && plan.stage1) || {}).audit || {}).resolution_exposure || null;
  // Decision 253's check on the pain map each side's recommended current is read from (the PI,
  // 2026-09-25): a dagger beside the current when that map moves between blocks of time, "not
  // checked" when the response carries no check for it, nothing when it was checked and holds.
  const timeState = (r) => (r.s && num(r.s.amplitude_preferred_mA) !== null
    ? blockOfTimeState(rateRowForSetting(plan, r.s)) : null);
  const timeNotChecked = (r) => (r.s && num(r.s.amplitude_preferred_mA) !== null
    ? notCheckedText(rateRowForSetting(plan, r.s)) : null);
  const anyMoves = rows.some((r) => timeState(r) === "moves");
  const noCurrent = rows.filter((r) => r.s && num(r.s.rate_hz) !== null && num(r.s.amplitude_preferred_mA) === null)
    .map((r) => r.side);
  const stopping = stoppingText(rows);
  // While the plan is still computing and no side can be drawn yet, the strip is drawn as still
  // grey blocks in the shape of the Today | Suggested | Difference table it will become, with the
  // waiting words (TASTE_AUDIT.md C2; no spinner).
  if (!rows.length && planLoading) return <DecisionStripLoading />;
  return (
    <MDBox>
      <MDBox sx={{ display: "grid", gridTemplateColumns: SIDES_GRID, columnGap: "48px", rowGap: "32px" }}>
        {rows.map((r) => (
          <SideBlock key={r.side} r={r} plan={plan} planLoading={planLoading} planErr={planErr}
            halfRange={halfRange} timeState={timeState} timeNotChecked={timeNotChecked} />
        ))}
      </MDBox>
      {noCurrent.length > 0 && (
        <MDTypography variant="caption" component="div" data-testid="no-current-sentence"
          sx={{ fontSize: TYPE.body, fontWeight: WEIGHT.strong, color: T.caution, mt: 2 }}>
          {`▲ No current can be recommended from this record on ${noCurrent.join(" or ")}; the current map below shows which of its three checks fail.`}
        </MDTypography>
      )}
      <MDTypography variant="caption" component="div" sx={{ ...SMALL, mt: 1.5 }}>
        Pain points: lower is better; a positive change favours the suggested setting.
      </MDTypography>
      <BlockOfTimeFootnote show={anyMoves} />
      {/* ONE fold for three things the PI placed in the open in decisions 243(b), 243(d) and
          245(b), and moved into a fold on 2026-09-26 ("yes to all six"): what "proven better"
          means, how many times that comparison ran and what 1 SD exposes across them (the
          server's own sentence), and the search's own stopping rule. */}
      <SizedFold show="Superiority and stopping rule" hide="Hide">
        <MDTypography variant="caption" component="div" sx={{ fontSize: TYPE.body, color: T.ink2 }}>
          Proven better means the predicted change in pain against today's setting is larger than 1
          standard deviation of that difference; not proven means it was measured and is smaller; not
          determinable means the difference could not be formed at all.
        </MDTypography>
        {exposure && exposure.sentence ? (
          <MDTypography variant="caption" component="div" data-testid="resolution-exposure"
            sx={{ fontSize: TYPE.body, color: T.ink2, mt: 1 }}>
            {exposure.sentence}
          </MDTypography>
        ) : null}
        {/* Absent from a response that predates the fields. */}
        {stopping ? (
          <MDTypography variant="caption" component="div" data-testid="stopping-rule"
            sx={{ fontSize: TYPE.body, color: T.ink2, mt: 1 }}>
            {`When to stop searching, the search's own rule: ${stopping}.`}
          </MDTypography>
        ) : null}
      </SizedFold>
      {rows.some((r) => r.s && Array.isArray(r.s.reasons) && r.s.reasons.length) && (
        <SizedFold show={`Why each side reads as it does (${rows.reduce((n, r) => n + ((r.s && r.s.reasons) || []).length, 0)} reasons from the search)`}
          hide="Hide the reasons" mt={0.5}>
          {rows.map((r) => (r.s && Array.isArray(r.s.reasons) && r.s.reasons.length) ? (
            <MDBox key={r.side} mt={1}>
              <MDTypography variant="caption" component="div" sx={SUBHEAD}>{r.side}</MDTypography>
              <MDBox component="ul" sx={{ m: 0, pl: 2.5 }}>
                {r.s.reasons.map((t, i) => (
                  <li key={i}><MDTypography variant="caption" sx={{ fontSize: TYPE.body, color: T.ink2 }}>{String(t)}</MDTypography></li>
                ))}
              </MDBox>
            </MDBox>
          ) : null)}
        </SizedFold>
      )}
    </MDBox>
  );
}

// Rebuilt only when one of its inputs changes (speed-up item C6, 2026-10-02). The page re-renders
// several times while it loads and every card below it was rebuilt each time with the same inputs;
// the decision strip rebuilt each time.
export default memo(DecisionStrip);
