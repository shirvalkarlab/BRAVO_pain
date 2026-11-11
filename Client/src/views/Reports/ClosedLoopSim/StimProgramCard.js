/**
 * "Stimulation program": the program closed loop will run, defined by the user (the PI,
 * 2026-10-07; decision 467). On screen: Closed-Loop page, the first card under the page head.
 *
 * One rate for both sides (slider); each side its own card, left on the left: the lead's target,
 * Amp, PW, and the lowest and highest current closed loop may move between, beside the lead drawn
 * the way BRAVO's therapy-history page draws a SenSight lead (rings 0 and 3, segmented 1 and 2,
 * three squares each), with the case as a small rectangle under it. Clicking a contact cycles it
 * off -> negative -> positive -> off; the sign is printed on the contact. Under each side, the
 * program as the programmer writes it, and a red line only for what stops it being programmed.
 * "Inherit current settings" fills everything from the newest device export.
 *
 * Nothing here writes to the device.
 */
import { Slider, TextField } from "@mui/material";

import MDBox from "components/MDBox";
import MDTypography from "components/MDTypography";
import { T, TYPE, RADIUS, FOCUS_RING, GLYPH } from "assets/theme/base/tokens";

import Section from "../paper/Section";
import { LEAD } from "./palette";
import {
  SIDES, LEVELS, shownContact, nextSign, withContact, contactsText, blockingProblems,
} from "./stimProgram";

// Column of each segment (the therapy-history page's geometry: a on the right, c on the left).
const SEG_X = { a: 62, b: 31, c: 0 };
const LEVEL_Y = { 3: 12, 2: 62, 1: 112, 0: 162 };

function contactX(id) {
  return id.length === 2 ? SEG_X[id[1]] : 31;
}

/** The lead and its case, clickable. `pair` rings the band's sensing contacts. */
export function LeadDrawing({ side, contacts, pair, onToggle }) {
  const c = contacts || {};
  const fill = (v) => (v === -1 ? LEAD.neg : v === 1 ? LEAD.pos : LEAD.off);
  const sign = (v) => (v === -1 ? "−" : v === 1 ? "+" : "");
  const word = (v) => (v === -1 ? "negative" : v === 1 ? "positive" : "off");
  const key = (id) => (e) => {
    if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onToggle(id); }
  };
  const box = (id, x, y, w, h, rx = 0, label = null) => (
    <g key={id} role="button" tabIndex={0} data-testid={`contact-${side}-${id}`} data-sign={c[id] || 0}
       aria-label={`${side} ${shownContact(side, id)}, ${word(c[id])}`}
       onClick={() => onToggle(id)} onKeyDown={key(id)} style={{ cursor: "pointer", outline: "none" }}>
      <title>{`${shownContact(side, id)}: ${word(c[id])} (click to change)`}</title>
      <rect x={x} y={y} width={w} height={h} rx={rx} fill={fill(c[id])} stroke={LEAD.edge} strokeWidth={1} />
      <text x={x + w / 2} y={y + h / 2 + 1} textAnchor="middle" dominantBaseline="middle"
            fontSize={label ? 10 : 18} fontWeight={600} fill={c[id] ? LEAD.signOn : LEAD.signOff}
            style={{ pointerEvents: "none" }}>
        {label ? `${label}${sign(c[id]) ? ` ${sign(c[id])}` : ""}` : sign(c[id])}
      </text>
    </g>
  );
  const sensing = pair ? pair.map((r) => LEVEL_Y[r]) : [];
  return (
    <svg viewBox="0 0 86 236" width={86} height={236} role="group" aria-label={`${side} lead`}
         style={{ flex: "none", overflow: "visible" }}>
      <rect x="31" y="0" width="24" height="182" rx="12" fill={LEAD.shaft} />
      <path d="M 31 176 H 55 V 200 A 12 12 0 0 1 31 200 Z" fill={LEAD.tip} />
      {sensing.map((y) => (
        <rect key={`s${y}`} x="28" y={y - 3} width="30" height="31" fill="none" stroke={LEAD.sensing}
              strokeWidth={2} strokeDasharray="3 2" pointerEvents="none" />
      ))}
      {LEVELS.flatMap(({ level, ids }) => ids.map((id) => box(id, contactX(id), LEVEL_Y[level], 24, 25)))}
      {box("case", 18, 214, 50, 20, 3, "Case")}
    </svg>
  );
}

const LABEL = { ...TYPE.body, fontWeight: 600, color: T.ink, whiteSpace: "nowrap" };
const UNIT = { ...TYPE.body, color: T.ink3, whiteSpace: "nowrap" };

function NumberRow({ label, value, unit, step, min, max, onChange, testId }) {
  return (
    <>
      <MDTypography component="span" sx={LABEL}>{label}</MDTypography>
      <MDBox display="flex" alignItems="center" gap={0.5}>
        <TextField value={value == null ? "" : value} type="number" size="small" variant="outlined"
          onChange={(e) => onChange(e.target.value === "" ? null : Number(e.target.value))}
          inputProps={{ step, min, max, "aria-label": label, "data-testid": testId,
            style: { width: 52, padding: "3px 6px", fontSize: TYPE.body.fontSize } }} />
        <MDTypography component="span" sx={UNIT}>{unit}</MDTypography>
      </MDBox>
    </>
  );
}

function SideCard({ side, program, pair, onChange }) {
  const s = program || {};
  const set = (k) => (v) => onChange({ ...s, [k]: v });
  const problems = blockingProblems(s, pair, side);
  const text = contactsText(side, s.contacts || {});
  return (
    <MDBox data-testid={`stim-side-${side}`} sx={{ border: `1px solid ${T.rule}`, borderRadius: `${RADIUS.sm}px`,
      p: 1.5, minWidth: 0, display: "flex", flexDirection: "column", gap: 1 }}>
      <MDBox display="flex" gap={2} alignItems="flex-start" justifyContent="space-between">
        <MDBox sx={{ display: "grid", gridTemplateColumns: "auto auto", columnGap: 1.5, rowGap: 0.75,
          alignItems: "center", minWidth: 0 }}>
          <MDTypography component="span" sx={LABEL}>Target</MDTypography>
          <MDTypography component="span" sx={{ ...TYPE.body, fontWeight: 600, color: T.accent, whiteSpace: "nowrap" }}
                        data-testid={`stim-target-${side}`}>
            {s.target || `${side} lead`}
          </MDTypography>
          <NumberRow label="Amp" value={s.amp_mA} unit="mA" step={0.1} min={0} max={10.5}
                     onChange={set("amp_mA")} testId={`amp-${side}`} />
          <NumberRow label="PW" value={s.pw_us} unit="µs" step={10} min={20} max={450}
                     onChange={set("pw_us")} testId={`pw-${side}`} />
          <NumberRow label="Lowest current" value={s.lower_limit_mA} unit="mA" step={0.1} min={0} max={10.5}
                     onChange={set("lower_limit_mA")} testId={`lo-${side}`} />
          <NumberRow label="Highest current" value={s.upper_limit_mA} unit="mA" step={0.1} min={0} max={10.5}
                     onChange={set("upper_limit_mA")} testId={`hi-${side}`} />
        </MDBox>
        <LeadDrawing side={side} contacts={s.contacts} pair={pair}
                     onToggle={(id) => onChange(withContact(s, id, nextSign((s.contacts || {})[id])))} />
      </MDBox>
      <MDTypography data-testid={`stim-text-${side}`} sx={{ ...TYPE.body, color: T.ink }}>
        {text || "No contact on"}
      </MDTypography>
      {problems.map((p) => (
        <MDTypography key={p} data-testid="stim-problem" sx={{ ...TYPE.body, color: T.refused }}>
          {`${GLYPH.refused} ${p}`}
        </MDTypography>
      ))}
    </MDBox>
  );
}

const BUTTON = {
  ...TYPE.body, fontFamily: "inherit", fontWeight: 600, color: T.accent, background: T.surface,
  border: `2px solid ${T.accent}`, borderRadius: `${RADIUS.sm}px`, px: 1.5, py: 0.5, cursor: "pointer",
  "&:hover": { background: T.accentTint }, "&:focus-visible": FOCUS_RING,
};

/**
 * Props: `program` ({rate_hz, Left, Right}), `onChange(program)`, `onInherit()`, `inheritedFrom`
 * (the export's date, or null), `edited` (bool), `sensing` ({side, pair} of the chosen band).
 */
export default function StimProgramCard({ program, onChange, onInherit, inheritedFrom, edited, sensing,
  unavailable }) {
  const p = program || {};
  const rate = p.rate_hz == null ? "" : p.rate_hz;
  const source = edited ? "Your program: the checks and the parameter table use it"
    : inheritedFrom ? `As the device runs today (export of ${inheritedFrom})` : (unavailable || "Reading the device's settings…");
  return (
    <Section question="Stimulation program" answer={source}
      actions={(
        <MDBox component="button" type="button" onClick={onInherit} sx={BUTTON} data-testid="inherit-current">
          Inherit current settings
        </MDBox>
      )}>
      <MDBox display="flex" flexDirection="column" gap={1.5}>
        <MDBox display="flex" alignItems="center" gap={1.5} sx={{ maxWidth: 520 }}>
          <MDTypography component="span" sx={LABEL}>Rate</MDTypography>
          <Slider value={Number(rate) || 0} min={2} max={250} step={1} size="small" sx={{ flex: 1 }}
            aria-label="rate in hertz, both sides" valueLabelDisplay="auto"
            onChange={(e, v) => onChange({ ...p, rate_hz: v })} />
          <TextField value={rate} type="number" size="small" variant="outlined"
            onChange={(e) => onChange({ ...p, rate_hz: e.target.value === "" ? null : Number(e.target.value) })}
            inputProps={{ min: 2, max: 250, step: 1, "aria-label": "rate in hertz", "data-testid": "rate-box",
              style: { width: 52, padding: "3px 6px", fontSize: TYPE.body.fontSize } }} />
          <MDTypography component="span" sx={UNIT}>Hz, both sides</MDTypography>
        </MDBox>
        <MDBox sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", md: "1fr 1fr" }, gap: 2 }}>
          {SIDES.map((side) => (
            <SideCard key={side} side={side} program={p[side]}
              pair={sensing && sensing.side === side ? sensing.pair : null}
              onChange={(next) => onChange({ ...p, [side]: next })} />
          ))}
        </MDBox>
      </MDBox>
    </Section>
  );
}
