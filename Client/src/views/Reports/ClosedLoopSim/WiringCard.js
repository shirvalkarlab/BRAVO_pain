/**
 * "Sense-to-control algorithm wiring" (the PI, 2026-10-08): which side's sensed band power drives
 * which stimulated side. On screen: Closed-Loop page, the card under "Stimulation program".
 *
 * The title and the choice in the device's own words above; under them ONE ROW of three buttons
 * (the PI, same day: "smaller ... three buttons arranged horizontally"), each a small drawing
 * (sensing dots on top, stimulators below, an arrow from the side that senses to each side it
 * drives) and its name. A line appears only when a choice cannot be set up with the band(s)
 * chosen. The choice decides which stimulators the decision card below answers for.
 */
import MDBox from "components/MDBox";
import MDTypography from "components/MDTypography";
import { T, TYPE, RADIUS, FOCUS_RING, GLYPH } from "assets/theme/base/tokens";

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

/** Props: `value` (a wiring key or null), `onChange(key)`, `bandSides` (sides with a chosen band). */
export default function WiringCard({ value, onChange, bandSides }) {
  const chosen = wiringOf(value);
  const problems = chosen ? wiringProblems(chosen.key, bandSides) : [];
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
          </MDBox>
        ))}
      </MDBox>
      {problems.map((p) => (
        <MDTypography key={p} data-testid="wiring-problem" sx={{ ...TYPE.body, color: T.notChecked, mt: 1 }}>
          {`${GLYPH.notChecked} ${p}`}
        </MDTypography>
      ))}
    </Section>
  );
}
