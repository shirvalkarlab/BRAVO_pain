/**
 * "Sense-to-control algorithm wiring" (the PI, 2026-10-08): which side's sensed band power drives
 * which stimulated side. On screen: Closed-Loop page, the card under "Stimulation program".
 *
 * Three choices side by side, each a small drawing (sensing on top, stimulation below, an arrow
 * from the side that senses to each side it drives) with the device's own words under it. A line
 * appears only when a choice cannot be set up with the band(s) chosen. The choice is remembered in
 * this browser; it does not change the checks or the simulation yet (see `wiring.js`).
 */
import MDBox from "components/MDBox";
import MDTypography from "components/MDTypography";
import { T, TYPE, RADIUS, FOCUS_RING, GLYPH } from "assets/theme/base/tokens";

import Section from "../paper/Section";
import { SIDE } from "./palette";
import { WIRINGS, wiringOf, wiringProblems } from "./wiring";

const X = { Left: 26, Right: 90 };
const FS = TYPE.caption.fontSize;   // 12 px, the smallest text on the page
const COLOUR = { Left: SIDE.left, Right: SIDE.right };

/** Sensing on top, stimulation below, one arrow per driven side. */
export function WiringDrawing({ drives }) {
  return (
    <svg viewBox="0 0 116 80" width={116} height={80} aria-hidden="true" style={{ flex: "none" }}>
      <defs>
        {["Left", "Right"].map((s) => (
          <marker key={s} id={`wire-arrow-${s}`} viewBox="0 0 8 8" refX="7" refY="4" markerWidth="6"
                  markerHeight="6" orient="auto-start-reverse">
            <path d="M0 0 L8 4 L0 8 Z" fill={COLOUR[s]} />
          </marker>
        ))}
      </defs>
      {["Left", "Right"].map((s) => (
        <g key={s}>
          <text x={X[s]} y={11} textAnchor="middle" fontSize={FS} fill={T.ink3}>{`${s[0]} sense`}</text>
          <circle cx={X[s]} cy={23} r={6} fill={Object.values(drives).includes(s) ? COLOUR[s] : T.surface}
                  stroke={COLOUR[s]} strokeWidth={1.5} />
          <rect x={X[s] - 12} y={52} width={24} height={12} rx={2} fill={T.surface} stroke={T.ink3} />
          <text x={X[s]} y={78} textAnchor="middle" fontSize={FS} fill={T.ink3}>{`${s[0]} stim`}</text>
        </g>
      ))}
      {Object.entries(drives).map(([stim, sense]) => (
        <line key={stim} x1={X[sense]} y1={30} x2={X[stim]} y2={50} stroke={COLOUR[sense]} strokeWidth={2}
              markerEnd={`url(#wire-arrow-${sense})`} />
      ))}
    </svg>
  );
}

const TILE = (on) => ({
  ...TYPE.body, fontFamily: "inherit", textAlign: "left", cursor: "pointer", color: T.ink,
  background: on ? T.accentTint : T.surface, border: `${on ? 2 : 1}px solid ${on ? T.accent : T.rule}`,
  borderRadius: `${RADIUS.sm}px`, p: on ? 1.25 : "11px", display: "flex", gap: 1.5, alignItems: "center",
  minWidth: 0, "&:focus-visible": FOCUS_RING,
});

/** Props: `value` (a wiring key or null), `onChange(key)`, `bandSides` (sides with a chosen band). */
export default function WiringCard({ value, onChange, bandSides }) {
  const chosen = wiringOf(value);
  const problems = chosen ? wiringProblems(chosen.key, bandSides) : [];
  return (
    <Section question="Sense-to-control algorithm wiring"
      answer={chosen ? chosen.medtronic : "Not chosen yet"}
      reading="Remembered in this browser. The checks and the simulation below still use one band; this choice does not change them yet.">
      <MDBox role="radiogroup" aria-label="Sense-to-control algorithm wiring"
        sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", md: "repeat(3, 1fr)" }, gap: 1.5 }}>
        {WIRINGS.map((w) => (
          <MDBox key={w.key} component="button" type="button" role="radio" aria-checked={value === w.key}
            data-testid={`wiring-${w.key}`} onClick={() => onChange(w.key)} sx={TILE(value === w.key)}>
            <WiringDrawing drives={w.drives} />
            <MDTypography component="span" sx={{ ...TYPE.body, fontWeight: 600, color: T.ink }}>{w.label}</MDTypography>
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
