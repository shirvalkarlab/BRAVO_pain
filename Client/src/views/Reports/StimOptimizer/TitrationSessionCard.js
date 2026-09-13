/**
 * "Titration session to run next": the card on the Stim Optimizer page, directly under "What to
 * test at the next visit", that turns open item 30 (the titration session that would let a
 * response peak be estimated) and decision 144 (the 20 s post-ramp margin, shipped OFF because on
 * 11-13 points it flips a verdict) into one sheet a clinician reads at the visit. The PI's decision
 * of 2026-09-12 evening: "make #4 a feature of next stim opt recommendation combined with 30".
 *
 * Everything here is READ from the `titration_plan` block the server returns
 * (`StimOptimizer/titration_plan.py` through `bravo_service.titration_plan_block`); nothing is
 * derived on the page. Two columns, Left | Right; numbers where numbers exist (rate, pulse width,
 * ceiling, the ladder as "0 → 0.5 → … → 5.0 → … → 0 mA", the hold, the contact in Medtronic
 * notation); the 22 band centres as a strip, clear ones in ink and the ones within 2.5 Hz of a
 * harmonic of the rate struck; the reasons folded under "Why this design". One line at the
 * bottom says what the record holds on that contact today against what the session yields, and
 * whether the margin can be switched on. The page's type scale (typeScale.js) and formatters
 * (stimFormat.js) are used throughout; nothing under 11 px.
 */
import { Card } from "@mui/material";

import MDBox from "components/MDBox";
import MDTypography from "components/MDTypography";

import PAL from "views/Reports/ClosedLoopSim/palette";

import { num, fmtHz, fmtMa, fmtUs, contactLabel } from "./stimFormat";
import { TYPE, HEAD, SMALL, MONO, NOWRAP, SizedFold as Fold } from "./typeScale";

export const TITRATION_CARD_TITLE = "Titration session to run next";

const LABEL = { ...HEAD, alignSelf: "baseline" };
const VALUE = { ...MONO, fontSize: TYPE.numLarge };
const VALUE_SMALL = { ...MONO, fontSize: TYPE.num };

/** One label + value row of a side's column. */
function Row({ label, children, sub }) {
  return (
    <MDBox sx={{ display: "grid", gridTemplateColumns: "minmax(88px, 0.45fr) 1fr", columnGap: "12px",
      alignItems: "baseline", py: 0.4 }}>
      <MDTypography variant="caption" sx={LABEL}>{label}</MDTypography>
      <MDBox>
        <div>{children}</div>
        {sub ? <MDTypography variant="caption" component="div" sx={SMALL}>{sub}</MDTypography> : null}
      </MDBox>
    </MDBox>
  );
}

/** The 22 centres as a strip: a clear centre in ink, an avoided one struck through and greyed. */
function BandStrip({ bands }) {
  if (!bands || !Array.isArray(bands.centres_hz)) return <span style={SMALL}>—</span>;
  const avoid = new Set((bands.avoid_hz || []).map((v) => Number(v)));
  return (
    <MDBox sx={{ display: "flex", flexWrap: "wrap", gap: "4px 6px", alignItems: "baseline" }}>
      {bands.centres_hz.map((c) => {
        const x = Number(c);
        const out = avoid.has(x);
        const reason = out ? (bands.avoid_reasons || {})[String(x)] || "" : "clear";
        return (
          <span key={x} title={`${x} Hz: ${reason}`}
            style={{ fontFamily: PAL.mono, fontSize: TYPE.num, whiteSpace: "nowrap",
              color: out ? "#9A9A9A" : "#1A1A1A", textDecoration: out ? "line-through" : "none" }}>
            {x}
          </span>
        );
      })}
      <span style={{ ...SMALL, marginLeft: 6 }}>
        {`Hz · ${bands.n_clear ?? "—"} clear, ${bands.n_avoid ?? "—"} struck`}
      </span>
    </MDBox>
  );
}

function SideColumn({ side, plan }) {
  if (!plan) {
    return (
      <MDBox>
        <MDTypography variant="h6" sx={{ fontSize: TYPE.section }}>{side}</MDTypography>
        <MDTypography variant="caption" sx={SMALL}>no plan for this side</MDTypography>
      </MDBox>
    );
  }
  const c = plan.sensing_contact;
  const lad = plan.ladder || {};
  const hold = plan.hold || {};
  const src = plan.sources || {};
  const rec = (plan.yield || {}).record_today || {};
  const harm = (plan.bands || {}).harmonics_hz || {};
  const harmonicsText = ["folded_about_250_hz", "half_rate", "quarter_rate", "three_quarters_rate"]
    .map((k) => (num(harm[k]) === null ? null : `${num(harm[k])} Hz`)).filter(Boolean).join(", ");
  return (
    <MDBox>
      <MDTypography variant="h6" sx={{ fontSize: TYPE.section }}>{side}</MDTypography>
      <Row label="rate" sub={plan.rate_lifted ? plan.rate_why : null}>
        <span style={VALUE}>{fmtHz(plan.rate_hz)}</span>
        {plan.rate_lifted && num(plan.rate_in_force_hz) !== null && (
          <span style={{ ...SMALL, marginLeft: 8, color: PAL.warnText }}>
            {`(in force: ${fmtHz(plan.rate_in_force_hz)})`}
          </span>
        )}
      </Row>
      <Row label="pulse width" sub={plan.pulse_width_note || null}>
        <span style={VALUE}>{fmtUs(plan.pulse_width_us)}</span>
      </Row>
      <Row label="ceiling">
        <span style={VALUE}>{fmtMa(plan.ceiling_mA)}</span>
      </Row>
      <Row label="ladder" sub={lad.why || null}>
        <span style={{ ...VALUE_SMALL, whiteSpace: "normal" }}>{lad.compact || "—"}</span>
        {num(lad.n_steps) !== null && (
          <span style={{ ...SMALL, marginLeft: 8 }}>
            {`${lad.n_steps} steps, ${lad.n_distinct_currents} distinct currents`}
          </span>
        )}
      </Row>
      <Row label="hold per step" sub={hold.why || null}>
        <span style={VALUE}>{num(hold.seconds) === null ? "—" : `${num(hold.seconds)} s`}</span>
        {num(hold.usable_pieces_after_margin) !== null && (
          <span style={{ ...SMALL, marginLeft: 8 }}>
            {`${hold.usable_pieces_after_margin} usable ${num(hold.piece_s)} s pieces after the ${num(hold.post_ramp_margin_s)} s margin (${hold.min_pieces_required} needed)`}
          </span>
        )}
      </Row>
      <Row label="record from" sub={c ? (c.ipsilateral_alternative
        ? `${c.note}. The best contact on this side itself: ${contactLabel(c.ipsilateral_alternative)}, ${c.ipsilateral_alternative.n_responding ?? "—"} of ${c.ipsilateral_alternative.n_bands ?? "—"} bands respond${c.ipsilateral_alternative.deployable ? "" : " (did not pass the screen)"}`
        : c.note) : plan.sensing_contact_note}>
        {c ? (
          <span>
            <span style={{ ...VALUE, color: c.on_other_side ? PAL.warnText : VALUE.color }}>{contactLabel(c)}</span>
            {num(c.n_responding) !== null && (
              <span style={{ ...SMALL, marginLeft: 8 }}>
                {`${c.n_responding} of ${num(c.n_bands) === null ? "—" : c.n_bands} bands respond at ${fmtHz(c.rate_hz)}${c.deployable ? "" : " · did not pass the screen"}`}
              </span>
            )}
          </span>
        ) : <span style={{ ...VALUE, color: PAL.neutral }}>—</span>}
      </Row>
      <Row label="analyse at" sub={harmonicsText ? `the stimulator shows up at ${harmonicsText}; a centre within ±${num((plan.bands || {}).half_width_hz) ?? "—"} Hz of one is struck` : null}>
        <BandStrip bands={plan.bands} />
      </Row>
      <MDBox mt={0.6}>
        <MDTypography variant="caption" sx={LABEL}>during the session</MDTypography>
        <MDBox component="ul" sx={{ m: 0, mt: 0.3, pl: 2.2 }}>
          {(plan.conditions || []).map((t, i) => (
            <li key={i} style={{ fontSize: TYPE.body, lineHeight: 1.35 }}>{t}</li>
          ))}
        </MDBox>
      </MDBox>
      <MDTypography variant="caption" component="div" sx={{ ...SMALL, mt: 0.8 }}>
        {`today: ${rec.note || "—"}`}
      </MDTypography>
      <Fold show="Why this design" hide="Hide" mt={0.6}>
        <MDBox component="dl" sx={{ m: 0, "& dt": { ...HEAD, mt: 0.6 }, "& dd": { m: 0, fontSize: TYPE.small, lineHeight: 1.35, color: "#3E3E3E" } }}>
          <dt>rate</dt><dd>{plan.rate_why} — {src.rate_hz}</dd>
          <dt>pulse width</dt><dd>{src.pulse_width_us}</dd>
          <dt>ceiling</dt><dd>{src.ceiling_mA}</dd>
          <dt>ladder</dt><dd>{src.ladder}</dd>
          <dt>hold per step</dt><dd>{src.hold}</dd>
          <dt>sensing contact</dt><dd>{src.sensing_contact}</dd>
          <dt>band centres</dt><dd>{(plan.bands || {}).why} — {src.bands}</dd>
          <dt>what the record holds today</dt><dd>{src["yield.record_today"]}</dd>
          <dt>the margin</dt><dd>{src["yield.margin"]}</dd>
          <dt>the conditions</dt><dd>{src.conditions}</dd>
        </MDBox>
      </Fold>
    </MDBox>
  );
}

export default function TitrationSessionCard({ plan }) {
  if (!plan) return null;
  const sides = plan.sides || {};
  const margin = plan.margin || {};
  const left = sides.Left || null;
  const right = sides.Right || null;
  const marginLine = (() => {
    if (!plan.available) return plan.reason || "the plan could not be built";
    const need = num(margin.min_settled_settings);
    if (need === null) return "whether the 20 s post-ramp margin can be switched on could not be judged (no per-run table is stored)";
    if (margin.available) {
      return `A run with at least ${need} settled settings exists (${margin.run} on ${margin.sensing_contact}: ${margin.max_settled_settings_in_one_run}), so the 20 s post-ramp margin ${margin.switch_on ? "is switched on" : "can be switched on; it is off today"}.`;
    }
    const most = num(margin.max_settled_settings_in_one_run);
    return `No run in the record holds the ${need} settled settings the 20 s post-ramp margin needs${most === null ? "" : ` (the most in any one run is ${most}, ${margin.run} on ${margin.sensing_contact})`}; the margin stays off until this session is recorded, and its rising leg alone gives ${num((left || right || {}).yield ? (left || right).yield.distinct_currents_up_leg : null) ?? "—"}.`;
  })();
  return (
    <Card>
      <MDBox p={2}>
        <MDBox display="flex" alignItems="baseline" gap={1} flexWrap="wrap">
          <MDTypography variant="h6" sx={{ fontSize: TYPE.section }}>{TITRATION_CARD_TITLE}</MDTypography>
          <MDTypography variant="caption" sx={SMALL}>
            {`one rate, 0 mA to the ceiling in ${num(plan.step_mA) ?? 0.5} mA steps, up and then down, ${num(plan.hold_s) ?? 60} s a step, streaming on`}
          </MDTypography>
        </MDBox>
        {!plan.available ? (
          <MDTypography variant="caption" component="div" sx={{ ...SMALL, mt: 1, color: PAL.warnText }}>
            {plan.reason || "the plan could not be built"}
          </MDTypography>
        ) : (
          <MDBox mt={1} sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", md: "1fr 1fr" }, columnGap: "28px", rowGap: "16px" }}>
            <SideColumn side="Left" plan={left} />
            <SideColumn side="Right" plan={right} />
          </MDBox>
        )}
        {plan.available && (
          <MDBox mt={1.2} sx={{ borderTop: `1px solid ${PAL.neutralBorder}`, pt: 0.8 }}>
            <MDTypography variant="caption" component="div" sx={{ fontSize: TYPE.body, lineHeight: 1.4 }}>
              {[left, right].filter(Boolean).map((p) => (
                <span key={p.side} style={{ display: "block" }}>
                  <b style={NOWRAP}>{p.side}:</b> {(p.yield || {}).sentence || "—"}
                </span>
              ))}
              <span style={{ display: "block", marginTop: 4, color: margin.available ? PAL.pass : PAL.warnText }}>{marginLine}</span>
            </MDTypography>
            <MDTypography variant="caption" component="div" sx={{ ...SMALL, mt: 0.5 }}>
              {`protocol: ${plan.protocol_source || "—"}`}
            </MDTypography>
          </MDBox>
        )}
      </MDBox>
    </Card>
  );
}
