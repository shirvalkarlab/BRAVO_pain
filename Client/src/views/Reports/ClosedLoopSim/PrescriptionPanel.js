/**
 * The values to enter on the A610, as a transcription checklist, and the details behind them.
 *
 * Since decision 302 (the PI, 2026-09-26: "Combine the full parameter recommendation with the
 * deployment card to create one simple, streamlined card") this file no longer draws a card of its
 * own. `ParameterTable` (the default export) is the table the decision card shows in the open;
 * `ParameterDetails` is everything that explained the table, which the decision card folds under
 * "Details". Every safeguard of the old "Full parameter recommendation" card is kept, each with the
 * transcription error it prevents:
 *
 * THE TABLE IS WITHHELD WHILE THE DEVICE REFUSES THE CONFIGURATION. A greyed number is still a
 * number, and a number on screen during a programming visit gets typed. The count of what is held
 * back is printed instead, with an explicit button for a read-only planning view that is
 * watermarked, has its read-back disabled and never prints (`cl-prescription-planning`, removed by
 * the print stylesheet). It fails closed: no report, or no device answer, withholds.
 *
 * THE MODE TOGGLE IS THE CLINICIAN'S. The recommendation is marked on its button and never
 * overwrites a selection. The field set differs between modes, so the rows are remounted on a mode
 * change and every read-back tick is cleared with them.
 *
 * THE READ-BACK BOX IS IN THE LEFTMOST COLUMN and attests to what the programmer now DISPLAYS, which
 * catches a field that silently clamped or rounded a value.
 *
 * A CURRENT THE SAFE CEILING LOWERED SAYS SO ON ITS OWN ROW (decision 306): the server caps every
 * current it recommends at the participant's PI-stated ceiling and sends one sentence
 * (`ceiling_note`), printed under the parameter's name, never behind a fold.
 *
 * UNITS HAVE THEIR OWN COLUMN, so "1.50 mA" cannot be read as "150 mA"; values are monospaced and
 * right-aligned so decimal points line up.
 *
 * WHAT THE DEVICE RUNS TODAY IS ITS OWN COLUMN ("Programmed today"). It replaces the Closed-Loop
 * LSB panel's separate "recommended vs programmed" box (decision 302), which compared a different
 * threshold -- the percentile the ROC's cut-point falls at -- with the programmed one, so the page
 * showed two different "recommended" thresholds. The comparison now sits beside the value it is
 * about.
 */
import { useState } from "react";
import MDBox from "components/MDBox";
import MDTypography from "components/MDTypography";
import MDButton from "components/MDButton";

import PAL from "./palette";
import { MODE_LABEL, MODE_ORDER, fmtFieldValue } from "./deployFormat";

/** The heading over a row's check notes, counted on that row; null when the row carries none. */
const CHECK_NOTE_KEYS = ["design_rule_note", "occupancy_note", "startup_bias_note", "robustness_note"];
const COUNT_WORD = { 2: "Two", 3: "Three", 4: "Four" };
export function checksHeading(field) {
  const n = CHECK_NOTE_KEYS.filter((k) => field && field[k]).length;
  if (!n) return null;
  return n === 1 ? "A check on this number, measured on this participant's own record:"
    : `${COUNT_WORD[n]} separate checks on this number, each measured on this participant's own record:`;
}

/**
 * What the reader does with a row, in at most four words, keyed on the payload's `confirm` axis.
 * `verify_only` is the device-computed Single Threshold value (rule D20): it must never read as
 * an instruction to type it. `detail` is the longer sentence, printed under "Details".
 */
export const ACTION = {
  enterable: { label: "Enter", ink: "#2A2A2A", detail: null },
  check_on_device: { label: "Enter, check range", ink: PAL.warnText,
    detail: "The adjustable range for this field is not published, so confirm on the Advanced "
          + "Settings screen that the device accepts this value." },
  must_choose: { label: "Your choice", ink: PAL.warnText,
    detail: "No value is suggested on purpose: this is a clinical choice the record cannot make." },
  not_applicable: { label: "Not in this mode", ink: PAL.neutral, detail: null },
  verify_only: { label: "Device computes; don't type", ink: PAL.warnText,
    detail: "The device computes this value itself from the captured pair; it is shown only to "
          + "be checked against what the programmer displays." },
};

const ORIGIN_WORDS = {
  participant: "from this participant's data",
  manufacturer: "manufacturer's default",
  clinician: "the clinician's to choose",
  device: "computed by the device",
};

/** The report's prescription for the mode in force, and whether the device permits it. */
export function prescriptionState(report, mode) {
  const data = report && report.data ? report.data : null;
  const pres = data && data.prescriptions;
  if (!data || !pres || !pres.modes) return null;
  const recommended = pres.recommended;
  const activeMode = mode || pres.selected || recommended || MODE_ORDER[0];
  const m = pres.modes[activeMode] || {};
  const vd = data.verdict_detail || {};
  return {
    data, pres, recommended, activeMode, m,
    fields: m.fields || [],
    deviceOk: !!(data.available && vd.device_eligible === true),
    unevaluated: !data.available || vd.device_eligible == null,
  };
}

const COLS = [["0 0 30px", ""], ["1 1 170px", "Parameter"], ["0 0 112px", "Value"],
  ["0 0 62px", "Units"], ["0 0 118px", "Programmed today"], ["1 1 150px", "Action"]];

function Row({ f, index, ticked, onTick, readBackEnabled }) {
  const value = fmtFieldValue(f);
  const action = ACTION[f.confirm] || ACTION.enterable;
  const mustChoose = f.confirm === "must_choose" || (value == null && f.confirm !== "not_applicable");
  const prog = f.programmed != null ? String(f.programmed) : null;
  const same = prog != null && value != null && Number(prog) === Number(f.value);
  const cell = (i, children, sx = {}) => (
    <MDBox flex={COLS[i][0]} sx={{ px: 0.5, ...sx }}>{children}</MDBox>
  );
  return (
    <MDBox display="flex" flexDirection="row" alignItems="baseline" py={0.45} data-param-row=""
      sx={{ borderTop: index === 0 ? "none" : "1px solid rgba(0,0,0,0.07)" }}>
      {cell(0, (
        <input type="checkbox" checked={!!ticked} disabled={!readBackEnabled}
          onChange={() => onTick(!ticked)}
          aria-label={`The programmer now displays ${f.parameter} as `
            + `${value == null ? "the value I chose" : value} ${f.units || ""}`}
          style={{ width: 15, height: 15, cursor: readBackEnabled ? "pointer" : "not-allowed",
            opacity: readBackEnabled ? 1 : 0.45 }} />
      ))}
      {cell(1, (
        <>
          <MDTypography variant="caption" sx={{ display: "block", fontSize: 12.5, fontWeight: 600, color: "#1A1A1A" }}>
            {f.parameter}
          </MDTypography>
          {/* Decision 306: the server lowered this current to the participant's safe ceiling; the
              sentence sits on the row, in the open, so the value is never read without it. */}
          {f.ceiling_note ? (
            <MDTypography variant="caption" data-ceiling-note=""
              sx={{ display: "block", fontSize: 11.5, fontWeight: 600, color: PAL.warnText, lineHeight: 1.3 }}>
              {f.ceiling_note}
            </MDTypography>
          ) : null}
        </>
      ))}
      {cell(2, mustChoose && value == null ? (
        <MDTypography variant="caption" sx={{ fontSize: 12, color: PAL.warnText, fontWeight: 600 }}>
          to be chosen
        </MDTypography>
      ) : (
        <>
          <MDTypography variant="caption" sx={{ display: "block", fontSize: 13, fontFamily: PAL.mono,
            fontWeight: 700, color: "#111111", lineHeight: 1.2 }}>
            {value == null ? "not reported" : value}
          </MDTypography>
          {f.enter_as ? (
            <MDTypography variant="caption" sx={{ display: "block", fontSize: 11.5,
              fontFamily: PAL.mono, fontWeight: 700, color: PAL.warnText }}>
              {`enter as ${f.enter_as}`}
            </MDTypography>
          ) : null}
        </>
      ), { textAlign: "right" })}
      {cell(3, (
        <MDTypography variant="caption" sx={{ fontSize: 12, color: "#4A4A4A" }}>{f.units || ""}</MDTypography>
      ))}
      {cell(4, prog == null ? (
        <MDTypography variant="caption" sx={{ fontSize: 12, color: "#5E5E5E" }}>not read</MDTypography>
      ) : (
        <MDTypography variant="caption" sx={{ fontSize: 12.5, fontFamily: PAL.mono, color: "#2A2A2A" }}>
          {prog}
          {value == null ? null : (
            <span style={{ fontFamily: "inherit", color: same ? PAL.passText : PAL.warnText, fontWeight: 600 }}>
              {same ? "  same" : "  differs"}
            </span>
          )}
        </MDTypography>
      ), { textAlign: "right" })}
      {cell(5, (
        <MDTypography variant="caption" sx={{ fontSize: 12, fontWeight: 600, color: action.ink }}>
          {action.label}
        </MDTypography>
      ))}
    </MDBox>
  );
}

/**
 * The table the decision card shows in the open: the mode buttons, then either the rows or the
 * count of rows withheld. `className` on the root is what the print stylesheet keys on.
 */
export default function ParameterTable({ report, mode, onMode }) {
  const [planningFor, setPlanningFor] = useState(null);
  const [ticks, setTicks] = useState({});
  const st = prescriptionState(report, mode);
  if (report && report.loading) {
    return (
      <MDTypography variant="caption" sx={{ fontSize: 12, color: "#4A4A4A" }}>
        Building the values to enter…
      </MDTypography>
    );
  }
  if (!st) {
    return (
      <MDTypography variant="caption" sx={{ display: "block", fontSize: 12, color: "#4A4A4A" }}>
        {`No parameter table has been computed for this configuration${
          report && report.err ? ` (${report.err})` : ""}.`}
      </MDTypography>
    );
  }
  const { pres, recommended, activeMode, fields, deviceOk, unevaluated } = st;
  const cannotDrive = fields.length === 0;
  const readBackEnabled = deviceOk && !cannotDrive;
  const showValues = deviceOk || planningFor === activeMode;
  const nTicked = fields.filter((f) => ticks[`${activeMode}|${f.parameter}`]).length;

  return (
    <MDBox className={deviceOk ? "cl-prescription-authorised" : "cl-prescription-planning"}>
      <MDBox display="flex" flexDirection="row" alignItems="center" gap={0.8} flexWrap="wrap" mb={0.8}>
        <MDTypography variant="caption" sx={{ fontSize: 12, fontWeight: 600, color: "#2A2A2A", mr: 0.4 }}>
          Threshold mode
        </MDTypography>
        {MODE_ORDER.filter((k) => pres.modes[k]).map((k) => {
          const on = k === activeMode;
          return (
            <MDButton key={k} size="small" onClick={() => onMode && onMode(k)}
              variant={on ? "contained" : "outlined"} color={on ? "info" : "secondary"}
              aria-pressed={on} sx={{ textTransform: "none", fontSize: 12, py: 0.3 }}>
              {`${MODE_LABEL[k] || k}${k === recommended ? " (recommended)" : ""}`}
            </MDButton>
          );
        })}
      </MDBox>

      {cannotDrive ? (
        <MDTypography variant="caption" sx={{ display: "block", fontSize: 12.5, color: "#2A2A2A" }}>
          {st.m.note || `${MODE_LABEL[activeMode] || activeMode} cannot drive therapy: nothing to enter.`}
        </MDTypography>
      ) : !showValues ? (
        <MDBox>
          <MDTypography variant="caption" sx={{ display: "block", fontSize: 12.5, fontWeight: 600,
            color: PAL.failText }}>
            {`${fields.length} values withheld${unevaluated ? " until the device rules are evaluated" : ""}.`}
          </MDTypography>
          <MDButton size="small" variant="text" color="secondary" onClick={() => setPlanningFor(activeMode)}
            sx={{ textTransform: "none", fontSize: 12, px: 0, mt: 0.2 }}>
            Show the values for planning (not for programming)
          </MDButton>
        </MDBox>
      ) : (
        <MDBox sx={{ position: "relative" }}>
          {!deviceOk ? (
            <>
              <MDBox display="flex" justifyContent="space-between" alignItems="center" gap={1} mb={0.6}
                p={0.8} sx={{ border: `2px dashed ${PAL.warnBorder}`, borderRadius: "4px" }}>
                <MDTypography variant="caption" sx={{ fontSize: 12, fontWeight: 700, color: PAL.warnText }}>
                  {`PLANNING ONLY. ${unevaluated ? "The device rules have not been evaluated"
                    : "The device refuses this configuration"}; do not program these.`}
                </MDTypography>
                <MDButton size="small" variant="text" color="secondary" onClick={() => setPlanningFor(null)}
                  sx={{ textTransform: "none", fontSize: 12 }}>
                  Hide
                </MDButton>
              </MDBox>
              <MDBox sx={{ position: "absolute", inset: 0, zIndex: 2, pointerEvents: "none",
                display: "flex", alignItems: "center", justifyContent: "center", overflow: "hidden" }}>
                <MDTypography sx={{ transform: "rotate(-24deg)", fontSize: 44, fontWeight: 800,
                  color: "rgba(138,97,0,0.13)", letterSpacing: 3, whiteSpace: "nowrap" }}>
                  PLANNING ONLY
                </MDTypography>
              </MDBox>
            </>
          ) : null}
          <MDBox display="flex" flexDirection="row" pb={0.3} sx={{ borderBottom: "1px solid rgba(0,0,0,0.18)" }}>
            {COLS.map(([flex, h], i) => (
              <MDBox key={`h${h || i}`} flex={flex} sx={{ px: 0.5, textAlign: i === 2 || i === 4 ? "right" : "left" }}>
                <MDTypography variant="caption" sx={{ fontSize: 11.5, fontWeight: 700, color: "#4A4A4A" }}>
                  {h}
                </MDTypography>
              </MDBox>
            ))}
          </MDBox>
          <MDBox key={`rows-${activeMode}`}>
            {fields.map((f, i) => (
              <Row key={`${activeMode}-${f.parameter}`} f={f} index={i}
                ticked={!!ticks[`${activeMode}|${f.parameter}`]}
                onTick={(on) => setTicks((t) => ({ ...t, [`${activeMode}|${f.parameter}`]: on }))}
                readBackEnabled={readBackEnabled} />
            ))}
          </MDBox>
          {readBackEnabled ? (
            <MDTypography variant="caption" sx={{ display: "block", fontSize: 12, mt: 0.6, fontWeight: 600,
              color: nTicked === fields.length ? PAL.passText : PAL.warnText }}>
              {`${nTicked} of ${fields.length} read back off the programmer. Tick a box only when the `
                + "A610 itself displays that value."}
            </MDTypography>
          ) : null}
        </MDBox>
      )}
    </MDBox>
  );
}

/** One label and its sentence, for the details list. */
function Note({ children, ink = "#3A3A3A", mt = 0.2 }) {
  return (
    <MDTypography variant="caption" sx={{ display: "block", fontSize: 11.5, color: ink, mt }}>
      {children}
    </MDTypography>
  );
}

function Heading({ children }) {
  return (
    <MDTypography variant="caption" sx={{ display: "block", fontSize: 11.5, fontWeight: 700,
      color: "#2A2A2A", mt: 1.2 }}>
      {children}
    </MDTypography>
  );
}

/**
 * Everything that explained the table, for the decision card's "Details" fold (and the printed
 * record): why the mode is recommended, the two fields that interact, each row's origin, its
 * checks on this participant's record and why it has its value, what the record cannot settle,
 * the fields that exist in another mode, and how the values are displayed.
 */
export function ParameterDetails({ report, mode }) {
  const st = prescriptionState(report, mode);
  if (!st) return null;
  const { pres, recommended, activeMode, m, fields, deviceOk } = st;
  const rec = pres.recommendation || {};
  // While the device refuses the configuration the table withholds every value, and so does this:
  // the two interacting fields and the per-value notes quote values, so neither is printed.
  const withheld = !deviceOk;
  const couplings = m.couplings || [];
  const unknowns = m.unknowns || [];
  const notApplicable = m.not_applicable || [];
  return (
    <MDBox>
      <Heading>{`Threshold mode: ${MODE_LABEL[recommended] || recommended || "none"} recommended`}</Heading>
      {rec.recommended_because ? <Note>{rec.recommended_because}</Note> : null}
      {rec.timescale_measured === false ? (
        <Note ink={PAL.warnText}>
          No biomarker timescale has been measured for this participant, so the recommendation rests
          on the nature of the outcome rather than on this person&apos;s data.
        </Note>
      ) : null}
      {(rec.problems || []).length ? (
        <Note ink={PAL.failText}>{`Problems with the recommended mode: ${rec.problems.join("; ")}.`}</Note>
      ) : null}
      {mode && recommended && activeMode !== recommended ? (
        <Note ink={PAL.warnText}>
          {`Showing ${MODE_LABEL[activeMode] || activeMode}, which is not the recommended mode.`}
        </Note>
      ) : null}
      <Note>
        {`${MODE_LABEL[activeMode] || activeMode}: ${fields.length} ${fields.length === 1 ? "field" : "fields"}`
          + (notApplicable.length ? `, and ${notApplicable.length} that exist only in another mode.` : ".")
          + " Count the rows before typing: a table that renders short looks like one with fewer fields."}
      </Note>

      {(withheld ? [] : couplings).map((c) => {
        const [fA, fB] = c.fields || [];
        const [vA, vB] = c.values || [];
        const steps = (vA != null && vB != null && Number(vB) > 0) ? Math.ceil(Number(vA) / Number(vB)) : null;
        return (
          <MDBox key={`cpl-${fA}-${fB}`}>
            <Heading>{`Two fields interact (${c.severity || "noted"}): ${fA} and ${fB}`}</Heading>
            <Note>
              {`${fA} = ${vA} ${(c.units || [])[0] || ""}, ${fB} = ${vB} ${(c.units || [])[1] || ""}`}
              {steps != null ? `; ceil(${vA} / ${vB}) = ${steps} controller step${steps === 1 ? "" : "s"}` : ""}
            </Note>
            {c.consequence ? <Note>{c.consequence}</Note> : null}
            {c.resolution ? <Note>{`What can be done: ${c.resolution}`}</Note> : null}
            {c.not_established ? <Note ink="#5E5E5E">{`Not established by any supplied document: ${c.not_established}`}</Note> : null}
          </MDBox>
        );
      })}

      <Heading>Each value, where it came from and how it was checked</Heading>
      {withheld ? (
        <Note>Withheld with the values while the device refuses this configuration.</Note>
      ) : fields.map((f) => {
        const action = ACTION[f.confirm] || ACTION.enterable;
        const heading = checksHeading(f);
        return (
          <MDBox key={`why-${f.parameter}`} mt={0.6} pl={1} sx={{ borderLeft: "2px solid rgba(0,0,0,0.10)" }}>
            <MDTypography variant="caption" sx={{ display: "block", fontSize: 11.5, fontWeight: 600, color: "#1A1A1A" }}>
              {`${f.parameter}: ${ORIGIN_WORDS[f.origin] || "no origin"}`
                + (f.device_default != null && String(f.device_default) !== String(f.value)
                  ? `; manufacturer default ${f.device_default}` : "")}
            </MDTypography>
            {f.ceiling_note ? <Note ink={PAL.warnText}>{f.ceiling_note}</Note> : null}
            {f.range_source ? <Note ink={/NOT published/i.test(f.range_source) ? PAL.warnText : "#4A4A4A"}>{f.range_source}</Note> : null}
            {f.range && f.range.length === 2 ? <Note>{`Documented range ${f.range[0]} to ${f.range[1]}.`}</Note> : null}
            {f.confidence ? <Note>{`Confidence ${f.confidence} (measured on this participant's record).`}</Note> : null}
            {action.detail ? <Note>{action.detail}</Note> : null}
            {heading ? <Note ink="#4A4A4A">{heading}</Note> : null}
            {CHECK_NOTE_KEYS.filter((k) => f[k]).map((k) => (
              <Note key={k} ink={PAL.warnText}>{f[k]}</Note>
            ))}
            {f.why ? <Note ink="#3A3A3A">{f.why}</Note> : null}
          </MDBox>
        );
      })}

      {unknowns.length ? (
        <>
          <Heading>{`${unknowns.length} thing${unknowns.length === 1 ? "" : "s"} the record cannot settle about these fields`}</Heading>
          {unknowns.map((u) => <Note key={u}>{u}</Note>)}
        </>
      ) : null}

      <Heading>{`Not in ${MODE_LABEL[activeMode] || activeMode}: ${notApplicable.length}`}</Heading>
      {notApplicable.map((f) => (
        <Note key={`na-${f.parameter}`}>
          <span style={{ textDecoration: "line-through" }}>{`${f.parameter}${f.units ? ` (${f.units})` : ""}`}</span>
          {f.why ? `: ${f.why}` : ""}
        </Note>
      ))}

      <Heading>How the values are displayed</Heading>
      {m.note && fields.length ? <Note>{m.note}</Note> : null}
      <Note>
        Amplitudes to two decimal places, durations as whole milliseconds, band-power thresholds to
        four decimal places. The four places are a reading aid: no supplied document publishes a
        resolution grid for these values, so the module does not round them. The module calls the
        threshold quantity &ldquo;LFP power&rdquo;, the quantity the device Timeline reports as LSB.
      </Note>
    </MDBox>
  );
}
