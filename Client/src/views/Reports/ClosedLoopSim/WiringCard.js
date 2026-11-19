/**
 * "Sense-to-control algorithm wiring" (the PI, 2026-10-08): which side's sensed band power drives
 * which stimulated side. On screen: Closed-Loop page, the card under "Stimulation program".
 *
 * The title and the choice in the device's own words above; under them ONE ROW of three buttons
 * (the PI, same day: "smaller ... three buttons arranged horizontally"), each a small drawing
 * (sensing dots on top, stimulators below, an arrow from the side that senses to each side it
 * drives) and its name. A line appears only when a choice cannot be set up with the band(s)
 * chosen. The choice decides which stimulators the decision card below answers for.
 *
 * THE SIMULATED COMPARISON (decision 472; `ClosedLoopDeployment/wiring_simulation.py`): once a band
 * is chosen on each side, the three wirings are run as the device's controllers over the time both
 * sides were recorded and scored on the same pain ratings. The recommended button carries
 * "Recommended"; one line under the buttons says the recommendation and why, or why there is none;
 * every number sits in a fold, closed by default. The choice stays the user's.
 */
import MDBox from "components/MDBox";
import MDTypography from "components/MDTypography";
import { T, TYPE, RADIUS, FOCUS_RING, GLYPH } from "assets/theme/base/tokens";

import Fold from "./Fold";

import Section from "../paper/Section";
import { SIDE } from "./palette";
import { WIRINGS, wiringOf, wiringProblems } from "./wiring";

const X = { Left: 8, Right: 30 };
const COLOUR = { Left: SIDE.left, Right: SIDE.right };

/** Sensing dots on top, stimulators below, one arrow per driven stimulator. No text: the label is beside it. */
export function WiringDrawing({ drives }) {
  return (
    <svg viewBox="0 0 38 30" width={38} height={30} aria-hidden="true" style={{ flex: "none" }}>
      {["Left", "Right"].map((s) => (
        <g key={s}>
          <circle cx={X[s]} cy={5} r={4} fill={Object.values(drives).includes(s) ? COLOUR[s] : T.surface}
                  stroke={COLOUR[s]} strokeWidth={1.5} />
          <rect x={X[s] - 6} y={22} width={12} height={7} rx={1.5} fill={T.surface} stroke={T.ink3} />
        </g>
      ))}
      {Object.entries(drives).map(([stim, sense]) => (
        <path key={stim} d={`M ${X[sense]} 10 L ${X[stim]} 21`} stroke={COLOUR[sense]} strokeWidth={1.75} />
      ))}
    </svg>
  );
}

const BUTTON = (on, i, n) => ({
  ...TYPE.body, fontFamily: "inherit", cursor: "pointer", whiteSpace: "nowrap",
  display: "inline-flex", alignItems: "center", gap: 1, px: 1.5, py: 0.5, minHeight: 40,
  color: on ? T.accent : T.ink, fontWeight: on ? 600 : 400,
  background: on ? T.accentTint : T.surface, border: `1px solid ${on ? T.accent : T.rule}`,
  ml: i === 0 ? 0 : "-1px", position: "relative", zIndex: on ? 1 : 0,
  borderRadius: i === 0 ? `${RADIUS.sm}px 0 0 ${RADIUS.sm}px` : (i === n - 1 ? `0 ${RADIUS.sm}px ${RADIUS.sm}px 0` : 0),
  "&:focus-visible": FOCUS_RING,
});

const fmt = (v, d = 2) => (v == null || !Number.isFinite(Number(v)) ? "–" : Number(v).toFixed(d));
const range = (iv) => (iv ? `${fmt(iv[0])}–${fmt(iv[1])}` : "–");
const capital = (t) => (t ? t[0].toUpperCase() + t.slice(1) : "");

/** The recommendation in one sentence, from the comparison's own words. */
export function recommendationLine(data) {
  const rec = (data && data.recommendation) || {};
  if (!rec.wiring) return `Simulation recommends none: ${rec.reason || "no wiring could be scored"}.`;
  const w = wiringOf(rec.wiring);
  return `Simulation recommends ${w ? w.label : rec.wiring}: ${rec.reason}`;
}

/** What the comparison was run on, in one line. */
export function recordLine(data) {
  const r = (data && data.record) || {};
  const n = (r.n_ratings_high || 0) + (r.n_ratings_low || 0);
  return `Replay of ${fmt(r.hours_both_sides, 1)} h recorded on both sides; ${n} pain ratings `
    + `(high and low thirds) on ${r.n_days || 0} days.`;
}

const HEAD = { ...TYPE.caption, fontWeight: 600, color: T.ink3, textAlign: "right", padding: "4px 8px",
  borderBottom: `1px solid ${T.rule}`, whiteSpace: "nowrap" };
const CELL = { ...TYPE.body, color: T.ink, textAlign: "right", padding: "4px 8px",
  fontVariantNumeric: "tabular-nums", whiteSpace: "nowrap" };

/** Every number of the comparison, for the fold. */
function ComparisonTable({ data }) {
  const ws = data.wirings || {};
  const allowWord = (v) => (v === true ? "allows" : (v === false ? `${GLYPH.refused} refuses` : "not known"));
  const k = data.response_per_mA || {};
  const kLine = (key, words) => {
    const e = k[key] || {};
    return `${words}: ${fmt(e.slope_per_mA, 1)} per mA (${e.source || "not known"})`;
  };
  return (
    <MDBox>
      <MDBox sx={{ overflowX: "auto" }}>
        <table style={{ borderCollapse: "collapse" }} data-testid="wiring-comparison-table">
          <thead>
            <tr>
              <th style={{ ...HEAD, textAlign: "left" }}>Wiring</th>
              <th style={HEAD}>Score (95% range)</th>
              <th style={HEAD}>Left AUC</th>
              <th style={HEAD}>Right AUC</th>
              <th style={HEAD}>Switches per hour</th>
              <th style={HEAD}>Time at highest, L / R</th>
              <th style={HEAD}>Mean mA, L / R</th>
              <th style={HEAD}>Device today</th>
            </tr>
          </thead>
          <tbody>
            {WIRINGS.map((w) => {
              const r = ws[w.key] || {};
              const pct = (v) => (v == null ? "–" : `${Math.round(100 * v)}%`);
              return (
                <tr key={w.key} data-testid={`wiring-row-${w.key}`}>
                  <td style={{ ...CELL, textAlign: "left" }}>{w.label}</td>
                  <td style={CELL}>{r.scored ? `${fmt(r.score)} (${range(r.score_interval)})` : (r.reason || "–")}</td>
                  <td style={CELL}>{fmt(r.auc && r.auc.Left)}</td>
                  <td style={CELL}>{fmt(r.auc && r.auc.Right)}</td>
                  <td style={CELL}>{fmt(r.switches_per_hour, 1)}</td>
                  <td style={CELL}>{`${pct(r.share_at_highest && r.share_at_highest.Left)} / ${pct(r.share_at_highest && r.share_at_highest.Right)}`}</td>
                  <td style={CELL}>{`${fmt(r.mean_current_mA && r.mean_current_mA.Left, 1)} / ${fmt(r.mean_current_mA && r.mean_current_mA.Right, 1)}`}</td>
                  <td style={CELL}>{allowWord(r.device_allows)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </MDBox>
      <MDBox component="ul" sx={{ ...TYPE.body, color: T.ink2, mt: 1.5, pl: 2.5, maxWidth: "80ch" }}>
        <li>{"Score: AUC of each stimulator's simulated current (as a share of its own range) between "
          + "high and low pain, averaged over the two stimulators; 0.5 = no relationship, above 0.5 = "
          + "more current at high pain. Range: visit days resampled."}</li>
        <li>{`${capital((data.pain_split && data.pain_split.why) || "")}.`}</li>
        <li>{`Ratings within ${fmt(data.rating_tol_s, 0)} s of the record; ${(data.record || {}).n_ratings_in_opening || 0} `
          + `left out because they fell in a stretch's first ${fmt((data.record || {}).opening_s, 0)} s, before `
          + "the controllers could move from mid-range."}</li>
        <li>{kLine("Left<Left", "Left band, left current")}</li>
        <li>{kLine("Left<Right", "Left band, right current")}</li>
        <li>{kLine("Right<Right", "Right band, right current")}</li>
        <li>{kLine("Right<Left", "Right band, left current")}</li>
        <li>{`Timing for all three: ${data.timing_source || "the device's defaults"}.`}</li>
        <li>{"A replay of past recordings with each stimulator's thresholds and limits from its own "
          + "deployment report; not a test of closed loop. It changes no check on this page."}</li>
      </MDBox>
    </MDBox>
  );
}

/** Props: `value` (a wiring key or null), `onChange(key)`, `bandSides` (sides with a chosen band),
 *  `comparison` (`{ data, loading, err }` from `useWiringComparison`, or null). */
export default function WiringCard({ value, onChange, bandSides, comparison = null }) {
  const chosen = wiringOf(value);
  const problems = chosen ? wiringProblems(chosen.key, bandSides) : [];
  const data = comparison && comparison.data;
  const recommended = data && data.recommendation ? data.recommendation.wiring : null;
  const both = (bandSides || []).length === 2;
  return (
    <Section question="Sense-to-control algorithm wiring"
      answer={chosen ? chosen.medtronic : "Not chosen: the decision below checks the band's own side only"}>
      <MDBox role="radiogroup" aria-label="Sense-to-control algorithm wiring"
        sx={{ display: "flex", flexWrap: "nowrap", overflowX: "auto", maxWidth: "100%" }}>
        {WIRINGS.map((w, i) => (
          <MDBox key={w.key} component="button" type="button" role="radio" aria-checked={value === w.key}
            data-testid={`wiring-${w.key}`} onClick={() => onChange(w.key)} sx={BUTTON(value === w.key, i, WIRINGS.length)}>
            <WiringDrawing drives={w.drives} />
            <span>{w.label}</span>
            {recommended === w.key ? (
              <span data-testid="wiring-recommended" style={{ color: T.accent, fontWeight: 600 }}>
                {` ${GLYPH.pass} Recommended`}
              </span>
            ) : null}
          </MDBox>
        ))}
      </MDBox>
      {problems.map((p) => (
        <MDTypography key={p} data-testid="wiring-problem" sx={{ ...TYPE.body, color: T.notChecked, mt: 1 }}>
          {`${GLYPH.notChecked} ${p}`}
        </MDTypography>
      ))}
      <MDBox data-testid="wiring-comparison" mt={1.5}>
        {!both ? (
          <MDTypography sx={{ ...TYPE.body, color: T.ink3 }}>
            {`${GLYPH.notChecked} Choose a band on each side to compare the three wirings by simulation.`}
          </MDTypography>
        ) : comparison && comparison.loading && !data ? (
          <MDTypography sx={{ ...TYPE.body, color: T.ink3 }}>
            Simulating the three wirings on the recorded data (about two minutes the first time)…
          </MDTypography>
        ) : data ? (
          <>
            <MDTypography data-testid="wiring-recommendation" sx={{ ...TYPE.body, color: T.ink }}>
              {recommendationLine(data)}
            </MDTypography>
            <MDTypography sx={{ ...TYPE.body, color: T.ink2 }}>{recordLine(data)}</MDTypography>
            <Fold show="Simulated comparison, every number" hide="Hide the comparison" mt={1}>
              <ComparisonTable data={data} />
            </Fold>
          </>
        ) : comparison && comparison.err ? (
          <MDTypography sx={{ ...TYPE.body, color: T.ink3 }}>
            {`${GLYPH.notChecked} Not compared: ${comparison.err}`}
          </MDTypography>
        ) : null}
      </MDBox>
    </Section>
  );
}
