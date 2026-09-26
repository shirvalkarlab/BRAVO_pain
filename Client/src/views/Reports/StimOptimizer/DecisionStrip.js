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
 *     side only; the Right side prints "—" until the response names its own.
 *   - the setting the search prefers: the two-stage block's frozen setting for that side (rate,
 *     pulse width, preferred current, delivered range, the stretches fitted), because that is the
 *     setting closed loop would freeze and it is held to what adaptive mode can use.
 *   - the gain and its uncertainty: the Stage 1 stratum row for that side and pulse width
 *     (`stage1.strata`), the same `gain` / `sd_of_difference` / `optimum_resolved` the verdict used.
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
 */
import { CircularProgress, Tooltip } from "@mui/material";

import MDBox from "components/MDBox";
import MDTypography from "components/MDTypography";

import PAL from "views/Reports/ClosedLoopSim/palette";
import { AmberGlyph } from "views/Reports/ClosedLoopSim/glyphs";

import { GainBar, VerdictGlyph } from "./GainBar";
import { TYPE, HEAD, SMALL, SizedFold } from "./typeScale";

import { num, fmtMa, fmtHz, fmtUs, fmtPts, fmtDelta, contactLabel } from "./stimFormat";
import { BlockOfTimeMark, BlockOfTimeFootnote, blockOfTimeState, notCheckedText, rateRowForSetting } from "./blockOfTime";

const VALUE = { fontFamily: PAL.mono, fontSize: TYPE.numLarge, color: "#1A1A1A", whiteSpace: "nowrap" };
const DELTA = { fontFamily: PAL.mono, fontSize: TYPE.num, color: "#1A1A1A", whiteSpace: "nowrap" };
const GAIN = { fontFamily: PAL.mono, fontSize: TYPE.num, color: "#1A1A1A", whiteSpace: "nowrap" };
const NW = { whiteSpace: "nowrap" };

/** A setting as one line of digits with units: "55 Hz · 100 µs · 3.0 mA". `missingAmp` is the
 * decision-158 case -- a rate (and usually a pulse width) WAS chosen, but the three-check honest
 * rule could not clear a current for it, so `amp` arrives as `null` on purpose, not as a gap in
 * the data. Printing a bare "—" there reads as missing data, so the current's place says "no
 * current" (never "NaN mA", never "None"), and ONE sentence under the rows says why for every side
 * at once (the design review of 2026-09-26: it used to be a sentence per side). */
function Setting({ rate, pw, amp, missingPw, missingAmp, ampMoves = false }) {
  return (
    <span style={VALUE}>
      {fmtHz(rate)}<span style={{ color: "#6E6E6E" }}> · </span>
      {missingPw ? <span style={{ color: "#6E6E6E" }}>— µs</span> : fmtUs(pw)}
      <span style={{ color: "#6E6E6E" }}> · </span>
      {missingAmp
        ? <span style={{ fontFamily: "inherit", fontSize: TYPE.body, fontWeight: 600, color: PAL.warnText }}>no current</span>
        : <>{fmtMa(amp)}{ampMoves && <BlockOfTimeMark />}</>}
    </span>
  );
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
    const stratum = s ? strata.find((r) => r && r.hemisphere === side
      && num(r.pw_us) !== null && num(s.pulse_width_us) !== null
      && Math.abs(num(r.pw_us) - num(s.pulse_width_us)) < 1e-9) : null;
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
  const st = r.stratum, s = r.s;
  if (st) return st.optimum_resolved === true ? true : (st.optimum_resolved === false ? false : null);
  if (s) return s.resolved === true ? true : (s.resolved === false ? false : null);
  return null;
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
  if (!v.length) return "What the joint search prefers, per side";
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

// The columns: side | programmed now | arrow | search prefers | change | gain (the number, the bar
// under it) | verdict. The gain's number cannot wrap ("+0.00 pts ± 0.85" at 14 px in the tabular
// font is about 150 px) and its bar sits UNDER it in the same cell (2026-09-26): side by side,
// the two fixed cells made the strip about 1,330 px wide and it scrolled sideways on a laptop.
const COLUMNS = "48px minmax(170px, 1.2fr) 20px minmax(170px, 1.2fr) minmax(80px, 0.6fr) minmax(170px, 1fr) minmax(120px, 0.8fr)";
const GAIN_BAR_WIDTH = 170;

export default function DecisionStrip({ arms, plan, planLoading, planErr, inForce }) {
  const rows = sideRows(arms, plan, inForce);
  const halfRange = Math.max(2, ...rows.map((r) => {
    const g = num(r.stratum && r.stratum.gain), sd = num(r.stratum && r.stratum.sd_of_difference);
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
  return (
    <MDBox>
      <MDBox sx={{ overflowX: "auto" }}>
        <MDBox sx={{ display: "grid", gridTemplateColumns: COLUMNS,
          columnGap: "14px", rowGap: "14px", alignItems: "center" }}>
          <span />
          <MDTypography variant="caption" sx={HEAD}>programmed now</MDTypography>
          <span />
          <MDTypography variant="caption" sx={HEAD}>search prefers (usable in closed loop)</MDTypography>
          <MDTypography variant="caption" sx={HEAD}>change</MDTypography>
          <MDTypography variant="caption" sx={HEAD}>gain over the setting in force ± 1 SD</MDTypography>
          <MDTypography variant="caption" sx={HEAD}>verdict</MDTypography>

          {rows.map((r) => {
            const s = r.s;
            const st = r.stratum;
            const prefRate = num(s && s.rate_hz), prefPw = num(s && s.pulse_width_us),
              prefAmp = num(s && s.amplitude_preferred_mA);
            const dMax = num(s && s.amplitude_delivered_max_mA), dMin = num(s && s.amplitude_delivered_min_mA);
            const aboveDelivered = prefAmp !== null && dMax !== null && prefAmp > dMax + 1e-9;
            const gain = num(st && st.gain), sd = num(st && st.sd_of_difference);
            const resolved = st ? (st.optimum_resolved === true ? true : (st.optimum_resolved === false ? false : null))
              : (s ? (s.resolved === true ? true : null) : null);
            const nFit = num(s && s.n_epochs_fitted_on_the_chosen_stratum);
            return [
              <MDTypography key={`${r.side}-a`} variant="button" fontWeight="medium" sx={{ fontSize: TYPE.num }}>{r.side}</MDTypography>,
              <MDBox key={`${r.side}-b`}>
                <Setting rate={r.nowRate} pw={r.nowPw} amp={r.nowAmp} missingPw={r.nowPw === null} />
                <MDTypography variant="caption" component="div" sx={{ ...SMALL, mt: 0.3 }}>
                  {r.contacts ? <>contacts <span style={NW}>{r.contacts}</span></> : "contacts: not in the response"}
                  {r.nowPw === null ? " · pulse width: not in the response for this side" : ""}
                </MDTypography>
                {/* Review S7 (2026-09-12): the setting in force is the newest DEVICE setting, rated
                    or not; when no rating has been filed under it yet the gains on this row are
                    still measured against the newest RATED setting, and the row says so. */}
                {r.inf && r.inf.has_ratings_yet === false && (
                  <MDTypography variant="caption" component="div" sx={{ ...SMALL, mt: 0.2, color: PAL.warnText }}>
                    {`no pain rating filed under this setting yet · gains below are measured against the newest rated setting${num(r.inf.fitted_incumbent_epoch) !== null ? ` (stretch ${Math.round(num(r.inf.fitted_incumbent_epoch))})` : ""}`}
                  </MDTypography>
                )}
              </MDBox>,
              <span key={`${r.side}-c`} style={{ color: "#6E6E6E", fontSize: 20, textAlign: "center" }}>→</span>,
              <MDBox key={`${r.side}-d`}>
                {planLoading && !s ? (
                  <MDBox display="flex" alignItems="center" gap={1}>
                    <CircularProgress size={14} />
                    <MDTypography variant="caption" sx={SMALL}>
                      computing the two-stage plan (about a minute the first time; a few seconds afterwards)
                    </MDTypography>
                  </MDBox>
                ) : (s ? (
                  prefRate === null ? (
                    <MDTypography variant="caption" sx={{ fontSize: TYPE.body, color: PAL.warnText, fontWeight: 600 }}>
                      no rate closed loop can use
                    </MDTypography>
                  ) : <Setting rate={prefRate} pw={prefPw} amp={prefAmp} missingPw={prefPw === null}
                         missingAmp={prefAmp === null} ampMoves={timeState(r) === "moves"} />
                ) : (
                  <MDTypography variant="caption" sx={SMALL}>{planErr ? `plan unavailable: ${planErr}` : "—"}</MDTypography>
                ))}
                {timeNotChecked(r) && (
                  <MDTypography variant="caption" component="div" sx={{ ...SMALL, mt: 0.2 }}>
                    {`current ${timeNotChecked(r)}`}
                  </MDTypography>
                )}
                {s && (
                  <MDTypography variant="caption" component="div" sx={{ ...SMALL, mt: 0.3 }}>
                    {dMin !== null && dMax !== null
                      ? <>delivered so far <span style={NW}>{`${dMin.toFixed(1)}–${dMax.toFixed(1)} mA`}</span></> : ""}
                    {nFit !== null
                      ? <>{dMin !== null && dMax !== null ? " · " : ""}fitted on <span style={NW}>{`${Math.round(nFit)} stretches`}</span> of unchanged settings</> : ""}
                  </MDTypography>
                )}
              </MDBox>,
              <MDBox key={`${r.side}-e`}>
                {s && prefRate !== null ? (
                  <MDBox sx={{ ...DELTA, lineHeight: 1.5 }}>
                    <div>{fmtDelta(prefRate - (r.nowRate ?? prefRate), "Hz", 0)}</div>
                    <div>{r.nowPw === null || prefPw === null ? "— µs" : fmtDelta(prefPw - r.nowPw, "µs", 0)}</div>
                    <MDBox display="flex" alignItems="center" gap={0.6}>
                      <span>{prefAmp === null || r.nowAmp === null ? "— mA" : fmtDelta(prefAmp - r.nowAmp, "mA", 1)}</span>
                      {aboveDelivered && (
                        <Tooltip title={`the preferred ${fmtMa(prefAmp)} is above the ${fmtMa(dMax)} ever delivered on this side, so it is an extrapolation`}>
                          <span><AmberGlyph label="above the highest current ever delivered on this side" size={14} /></span>
                        </Tooltip>
                      )}
                    </MDBox>
                  </MDBox>
                ) : <MDTypography variant="caption" sx={SMALL}>—</MDTypography>}
              </MDBox>,
              <MDBox key={`${r.side}-f`}>
                <span style={GAIN}>
                  {gain === null ? "—" : `${fmtPts(gain)}${sd === null ? "" : ` ± ${sd.toFixed(2)}`}`}
                </span>
                <MDBox mt={0.3}><GainBar gain={gain} sd={sd} halfRange={halfRange} width={GAIN_BAR_WIDTH} /></MDBox>
              </MDBox>,
              <MDBox key={`${r.side}-h`}><VerdictGlyph resolved={resolved} /></MDBox>,
            ];
          })}
        </MDBox>
      </MDBox>
      {noCurrent.length > 0 && (
        <MDTypography variant="caption" component="div" data-testid="no-current-sentence"
          sx={{ fontSize: TYPE.body, fontWeight: 600, color: PAL.warnText, mt: 1.2 }}>
          {`No current can be recommended from this record on ${noCurrent.join(" or ")}; the current map shows which of its three checks fail.`}
        </MDTypography>
      )}
      <MDTypography variant="caption" component="div" sx={{ ...SMALL, mt: 1.2 }}>
        Pain objective: lower is better; a positive gain favours the preferred setting.
      </MDTypography>
      <BlockOfTimeFootnote show={anyMoves} />
      {/* ONE fold for three things the PI placed in the open in decisions 243(b), 243(d) and
          245(b), and moved into a fold on 2026-09-26 ("yes to all six"): what "proven better"
          means, how many times that comparison ran and what 1 SD exposes across them (the
          server's own sentence), and the search's own stopping rule. */}
      <SizedFold show="What “proven better” means, and when to stop searching" hide="Hide">
        <MDTypography variant="caption" component="div" sx={{ ...SMALL, fontSize: TYPE.body }}>
          Proven better means the predicted gain over the setting in force is larger than 1 standard
          deviation of that difference; not proven means it was measured and is smaller; not
          determinable means the difference could not be formed at all.
        </MDTypography>
        {exposure && exposure.sentence ? (
          <MDTypography variant="caption" component="div" data-testid="resolution-exposure"
            sx={{ ...SMALL, fontSize: TYPE.body, mt: 0.6 }}>
            {exposure.sentence}
          </MDTypography>
        ) : null}
        {/* Absent from a response that predates the fields. */}
        {stopping ? (
          <MDTypography variant="caption" component="div" data-testid="stopping-rule"
            sx={{ ...SMALL, fontSize: TYPE.body, mt: 0.6 }}>
            {`When to stop searching, the search's own rule: ${stopping}.`}
          </MDTypography>
        ) : null}
      </SizedFold>
      {rows.some((r) => r.s && Array.isArray(r.s.reasons) && r.s.reasons.length) && (
        <SizedFold show={`Why each side reads as it does (${rows.reduce((n, r) => n + ((r.s && r.s.reasons) || []).length, 0)} reasons from the search)`}
          hide="Hide the reasons">
          {rows.map((r) => (r.s && Array.isArray(r.s.reasons) && r.s.reasons.length) ? (
            <MDBox key={r.side} mt={0.6}>
              <MDTypography variant="caption" fontWeight="medium" component="div" sx={{ fontSize: TYPE.body }}>{r.side}</MDTypography>
              <MDBox component="ul" sx={{ m: 0, pl: 2.5 }}>
                {r.s.reasons.map((t, i) => (
                  <li key={i}><MDTypography variant="caption" color="text" sx={{ fontSize: TYPE.body }}>{String(t)}</MDTypography></li>
                ))}
              </MDBox>
            </MDBox>
          ) : null)}
        </SizedFold>
      )}
    </MDBox>
  );
}
