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
 */
import { CircularProgress, Tooltip } from "@mui/material";

import MDBox from "components/MDBox";
import MDTypography from "components/MDTypography";

import Fold from "views/Reports/ClosedLoopSim/Fold";
import PAL from "views/Reports/ClosedLoopSim/palette";
import { TickGlyph, AmberGlyph, NotTestedGlyph } from "views/Reports/ClosedLoopSim/glyphs";

import { num, fmtMa, fmtHz, fmtUs, fmtPts, fmtDelta, contactLabel } from "./stimFormat";

const HEAD = { fontSize: 10, fontWeight: 700, letterSpacing: 0.4, color: "#8A8A8A",
  textTransform: "uppercase" };
const VALUE = { fontFamily: PAL.mono, fontSize: 13.5, color: "#1A1A1A" };
const SMALL = { fontSize: 10.5, color: "#6A6A6A" };

/** The gain and its one-standard-deviation band on a shared axis, 180 x 26 px. */
function GainBar({ gain, sd, halfRange }) {
  const W = 180, H = 26, PAD = 6;
  const g = num(gain), s = num(sd);
  const half = halfRange || 2;
  const x = (v) => PAD + ((v + half) / (2 * half)) * (W - 2 * PAD);
  const clamp = (v) => Math.max(-half, Math.min(half, v));
  if (g === null) {
    return (
      <svg width={W} height={H} role="img" aria-label="no gain could be formed">
        <line x1={x(0)} x2={x(0)} y1={3} y2={H - 3} stroke="#9A9A9A" strokeWidth="1" />
        <text x={x(0) + 4} y={H / 2 + 4} fontSize="9" fill="#9A9A9A">no difference formed</text>
      </svg>
    );
  }
  const lo = s === null ? g : g - s, hi = s === null ? g : g + s;
  return (
    <svg width={W} height={H} role="img"
      aria-label={`gain ${g.toFixed(2)} points, one standard deviation ${s === null ? "unknown" : s.toFixed(2)}`}>
      <line x1={x(-half)} x2={x(half)} y1={H / 2} y2={H / 2} stroke="#E0E0E0" strokeWidth="1" />
      <line x1={x(0)} x2={x(0)} y1={3} y2={H - 3} stroke="#6A6A6A" strokeWidth="1" />
      {s !== null && (
        <rect x={x(clamp(lo))} y={H / 2 - 5} width={Math.max(1, x(clamp(hi)) - x(clamp(lo)))} height={10}
          fill={PAL.neutralFill} stroke={PAL.neutralBorder} />
      )}
      <circle cx={x(clamp(g))} cy={H / 2} r={4.5} fill={PAL.accent} />
      <text x={x(-half)} y={H - 1} fontSize="8" fill="#9A9A9A">{`−${half}`}</text>
      <text x={x(half)} y={H - 1} fontSize="8" fill="#9A9A9A" textAnchor="end">{`+${half}`}</text>
    </svg>
  );
}

function VerdictGlyph({ resolved }) {
  if (resolved === true) return (
    <MDBox display="inline-flex" alignItems="center" gap={0.5}>
      <TickGlyph label="resolved" /><span style={{ fontSize: 11.5, color: PAL.pass, fontWeight: 600 }}>resolved</span>
    </MDBox>);
  if (resolved === false) return (
    <MDBox display="inline-flex" alignItems="center" gap={0.5}>
      <AmberGlyph label="not resolved" /><span style={{ fontSize: 11.5, color: PAL.warnText, fontWeight: 600 }}>not resolved</span>
    </MDBox>);
  return (
    <MDBox display="inline-flex" alignItems="center" gap={0.5}>
      <NotTestedGlyph label="not determinable" /><span style={{ fontSize: 11.5, color: PAL.neutral, fontWeight: 600 }}>not determinable</span>
    </MDBox>);
}

/** A setting as one line of digits with units: "55 Hz · 100 µs · 3.0 mA". */
function Setting({ rate, pw, amp, missingPw }) {
  return (
    <span style={VALUE}>
      {fmtHz(rate)}<span style={{ color: "#9A9A9A" }}> · </span>
      {missingPw ? <span style={{ color: "#9A9A9A" }}>— µs</span> : fmtUs(pw)}
      <span style={{ color: "#9A9A9A" }}> · </span>{fmtMa(amp)}
    </span>
  );
}

function sideRows(arms, plan, inForce) {
  const fc = ((plan && plan.stage1) || {}).frozen_configuration || {};
  const settings = Array.isArray(fc.settings) ? fc.settings : [];
  const strata = Array.isArray((plan && plan.stage1 || {}).strata) ? plan.stage1.strata : [];
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

export default function DecisionStrip({ arms, plan, planLoading, planErr, inForce }) {
  const rows = sideRows(arms, plan, inForce);
  const halfRange = Math.max(2, ...rows.map((r) => {
    const g = num(r.stratum && r.stratum.gain), sd = num(r.stratum && r.stratum.sd_of_difference);
    return g === null ? 0 : Math.ceil(Math.abs(g) + (sd || 0));
  }));
  return (
    <MDBox>
      <MDBox sx={{ display: "grid", gridTemplateColumns: "56px 1.35fr 24px 1.35fr 1fr 1.2fr 1fr",
        columnGap: "10px", rowGap: "4px", alignItems: "center" }}>
        <span />
        <MDTypography variant="caption" sx={HEAD}>programmed now</MDTypography>
        <span />
        <MDTypography variant="caption" sx={HEAD}>search prefers (usable in adaptive mode)</MDTypography>
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
          return [
            <MDTypography key={`${r.side}-a`} variant="button" fontWeight="medium" sx={{ fontSize: 13 }}>{r.side}</MDTypography>,
            <MDBox key={`${r.side}-b`}>
              <Setting rate={r.nowRate} pw={r.nowPw} amp={r.nowAmp} missingPw={r.nowPw === null} />
              <MDTypography variant="caption" component="div" sx={SMALL}>
                {r.contacts ? `contacts ${r.contacts}` : "contacts: not in the response"}
                {r.nowPw === null ? " · pulse width: not in the response for this side" : ""}
              </MDTypography>
            </MDBox>,
            <span key={`${r.side}-c`} style={{ color: "#9A9A9A", fontSize: 16, textAlign: "center" }}>→</span>,
            <MDBox key={`${r.side}-d`}>
              {planLoading && !s ? (
                <MDBox display="flex" alignItems="center" gap={1}>
                  <CircularProgress size={12} />
                  <MDTypography variant="caption" sx={SMALL}>computing the plan (about 10 s more)</MDTypography>
                </MDBox>
              ) : (s ? (
                prefRate === null ? (
                  <MDTypography variant="caption" sx={{ fontSize: 12, color: PAL.warnText, fontWeight: 600 }}>
                    no rate adaptive mode can use
                  </MDTypography>
                ) : <Setting rate={prefRate} pw={prefPw} amp={prefAmp} missingPw={prefPw === null} />
              ) : (
                <MDTypography variant="caption" sx={SMALL}>{planErr ? `plan unavailable: ${planErr}` : "—"}</MDTypography>
              ))}
              {s && (
                <MDTypography variant="caption" component="div" sx={SMALL}>
                  {dMin !== null && dMax !== null ? `delivered so far ${dMin.toFixed(1)}–${dMax.toFixed(1)} mA` : ""}
                  {num(s.n_epochs_fitted_on_the_chosen_stratum) !== null
                    ? ` · fitted on ${Math.round(num(s.n_epochs_fitted_on_the_chosen_stratum))} stretches of unchanged settings` : ""}
                </MDTypography>
              )}
            </MDBox>,
            <MDBox key={`${r.side}-e`}>
              {s && prefRate !== null ? (
                <MDBox sx={{ fontFamily: PAL.mono, fontSize: 12 }}>
                  <div>{fmtDelta(prefRate - (r.nowRate ?? prefRate), "Hz", 0)}</div>
                  <div>{r.nowPw === null || prefPw === null ? "— µs" : fmtDelta(prefPw - r.nowPw, "µs", 0)}</div>
                  <MDBox display="flex" alignItems="center" gap={0.5}>
                    <span>{fmtDelta(prefAmp - (r.nowAmp ?? prefAmp), "mA", 1)}</span>
                    {aboveDelivered && (
                      <Tooltip title={`the preferred ${fmtMa(prefAmp)} is above the ${fmtMa(dMax)} ever delivered on this side, so it is an extrapolation`}>
                        <span><AmberGlyph label="above the highest current ever delivered on this side" size={12} /></span>
                      </Tooltip>
                    )}
                  </MDBox>
                </MDBox>
              ) : <MDTypography variant="caption" sx={SMALL}>—</MDTypography>}
            </MDBox>,
            <MDBox key={`${r.side}-f`} display="flex" alignItems="center" gap={1}>
              <GainBar gain={gain} sd={sd} halfRange={halfRange} />
              <span style={{ fontFamily: PAL.mono, fontSize: 11.5 }}>
                {gain === null ? "—" : `${fmtPts(gain)}${sd === null ? "" : ` ± ${sd.toFixed(2)}`}`}
              </span>
            </MDBox>,
            <MDBox key={`${r.side}-g`}><VerdictGlyph resolved={resolved} /></MDBox>,
          ];
        })}
      </MDBox>
      <MDTypography variant="caption" component="div" sx={{ ...SMALL, mt: 0.6 }}>
        Pain objective: lower is better; a positive gain favours the preferred setting. Resolved
        means the gain is larger than 1 standard deviation of the difference itself.
      </MDTypography>
      {rows.some((r) => r.s && Array.isArray(r.s.reasons) && r.s.reasons.length) && (
        <Fold show={`Why each side reads as it does (${rows.reduce((n, r) => n + ((r.s && r.s.reasons) || []).length, 0)} reasons from the search)`}
          hide="Hide the reasons">
          {rows.map((r) => (r.s && Array.isArray(r.s.reasons) && r.s.reasons.length) ? (
            <MDBox key={r.side} mt={0.4}>
              <MDTypography variant="caption" fontWeight="medium" component="div" sx={{ fontSize: 11 }}>{r.side}</MDTypography>
              <MDBox component="ul" sx={{ m: 0, pl: 2.5 }}>
                {r.s.reasons.map((t, i) => (
                  <li key={i}><MDTypography variant="caption" color="text" sx={{ fontSize: 10.5 }}>{String(t)}</MDTypography></li>
                ))}
              </MDBox>
            </MDBox>
          ) : null)}
        </Fold>
      )}
    </MDBox>
  );
}
