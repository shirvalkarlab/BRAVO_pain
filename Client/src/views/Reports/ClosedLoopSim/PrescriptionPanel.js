/**
 * The device-parameter prescription, rendered as a transcription checklist.
 *
 * THIS IS THE SURFACE WHERE A PATIENT CAN BE HARMED. A clinician reads this table and types the
 * numbers into a Medtronic A610, which then drives stimulation in someone's brain. Every design
 * choice below exists to prevent a specific transcription error, and each one is annotated with the
 * error it prevents, because a safeguard whose reason has been forgotten is the first thing a later
 * change removes.
 *
 * THE WHOLE TABLE IS WITHHELD WHILE THE DEVICE VERDICT IS NEGATIVE, and that is deliberate rather
 * than cautious. A greyed or disabled number is still a number, still legible, and still the largest
 * thing in its row; the failure mode being guarded against is a number being on screen during a
 * programming visit, because a number in that position gets typed. In place of the table the panel
 * prints how many values are being withheld and why, so a reader knows something exists and has
 * been held back rather than being absent. A read-only planning view is available behind an explicit
 * click, watermarked on every screen and with the read-back checklist disabled.
 *
 * IT FAILS CLOSED. An absent report, a report that has not loaded, and a report carrying no device
 * answer all withhold, exactly as the verdict strip does, because an absent verdict is not
 * permission.
 *
 * THE MODE TOGGLE IS THE CLINICIAN'S, NOT THE MODULE'S. The three threshold modes are selectable and
 * a selection is never overwritten by the module's recommendation. The recommendation stays visible
 * beside the toggle, including while a non-recommended mode is selected, so the reader can see both
 * what they chose and what was advised without one displacing the other. The field set genuinely
 * differs between modes — Dual Threshold has sixteen fields with two thresholds and two onset
 * durations, Single Threshold has fourteen with one threshold the device computes for itself, and
 * Single Threshold Inverse has none because it cannot drive therapy at all — so the table is
 * remounted on a mode change rather than having its numbers swapped. Remounting also clears the
 * read-back ticks, which is a safety requirement and not a side effect: a tick attesting that the
 * device displays a Dual Threshold value must not survive into a Single Threshold table.
 */
import { useState } from "react";
import { Card, Divider } from "@mui/material";
import MDBox from "components/MDBox";
import MDTypography from "components/MDTypography";
import MDButton from "components/MDButton";

import PAL from "./palette";
import { MODE_LABEL, MODE_ORDER, fmtFieldValue } from "./deployFormat";

/** What the reader is being asked to do with a row, keyed on the payload's `confirm` axis. */
const CONFIRM_COPY = {
  enterable: {
    label: "ENTER THIS VALUE",
    ink: "#2A2A2A",
    detail: null,
  },
  check_on_device: {
    label: "CHECK ON THE DEVICE",
    ink: PAL.warnText,
    detail: "The adjustable range for this field is not published, so confirm on the Advanced "
          + "Settings screen that the device actually accepts this value before relying on it.",
  },
  must_choose: {
    label: "YOU MUST CHOOSE THIS",
    ink: PAL.warnText,
    detail: "No value is suggested here on purpose. This is a clinical choice that the record "
          + "cannot make, and any number printed in a value column during a programming visit "
          + "gets entered.",
  },
  not_applicable: {
    label: "NOT A FIELD IN THIS MODE",
    ink: PAL.neutral,
    detail: null,
  },
};

/** Where the number came from, keyed on the payload's `origin` axis. */
const ORIGIN_COPY = {
  participant: { label: "from this participant's data", bar: PAL.originParticipant },
  manufacturer: { label: "manufacturer's default", bar: null },
  clinician: { label: "the clinician's to choose", bar: PAL.originClinician },
  none: { label: "no origin", bar: PAL.originNone },
};

/**
 * Rows the DEVICE computes, which must never carry an instruction to type a value.
 *
 * In Single Threshold the row named "Single LFP threshold" is not entered by hand: the device
 * computes it as 0.75 x (Upper - Lower) + Lower from the captured pair under rule D20, and the
 * number is shown only so a clinician can verify it against what the programmer displays. A
 * clinician who sees a number on a row that instructs them to enter it will reasonably enter it,
 * and this is the one field in the table where the transcription error runs in that direction.
 *
 * This used to be detected by matching the row's `why` prose, because the payload labelled the row
 * `confirm: "enterable"` — the one place where the axis the interface consumes disagreed with the
 * justification text beside it. That was flagged as a stopgap needing a backend fix, and the fix
 * landed on 2026-09-04: the row now carries `status: "device_computed"`, which derives
 * `origin: "device"` and `confirm: "verify_only"`. So this reads the axis, and the prose match is
 * gone rather than kept as a belt-and-braces fallback — leaving both in would mean a future row
 * whose `why` happened to contain similar wording would silently acquire this treatment.
 */
function deviceComputesThisField(f) {
  return !!f && f.confirm === "verify_only";
}

/** A ruled blank, for the one row whose value is absent on purpose. */
function BlankEntry() {
  return (
    <MDBox sx={{ display: "inline-block", minWidth: 92, borderBottom: `1.5px solid ${PAL.warnText}`,
      height: 15 }} />
  );
}

/**
 * One field row.
 *
 * The read-back checkbox is in the LEFTMOST column, ahead of the field name, so an untouched row
 * shows up as a gap in a vertical line of ticks rather than as something a reader has to hunt for.
 * It is worded to attest to what the device now DISPLAYS rather than to what was typed, because
 * confirming that you typed what you typed detects nothing, whereas reading the value back off the
 * programmer detects the case where the field silently clamped or rounded it — which is exactly the
 * failure the unpublished ranges make likely.
 */
function FieldRow({ f, index, ticked, onTick, readBackEnabled }) {
  const [openWhy, setOpenWhy] = useState(false);
  const origin = ORIGIN_COPY[f.origin] || ORIGIN_COPY.none;
  const confirm = CONFIRM_COPY[f.confirm] || CONFIRM_COPY.enterable;
  const value = fmtFieldValue(f);
  const mustChoose = f.confirm === "must_choose" || (f.value == null && f.confirm !== "not_applicable");
  const computed = deviceComputesThisField(f);

  return (
    <MDBox display="flex" flexDirection="row" alignItems="flex-start" py={0.55}
      sx={{
        borderTop: "1px solid rgba(0,0,0,0.08)",
        // The provenance bar down the left edge. A manufacturer default has NO bar, because the
        // absence of a mark needs nothing remembered in order to be read correctly.
        borderLeft: `4px solid ${origin.bar || "transparent"}`,
        background: f.origin === "clinician" && origin.bar
          ? PAL.hatch("#E69F0022", "transparent") : undefined,
        pl: 0.8,
      }}>
      {/* 1 — read-back */}
      <MDBox flex="0 0 34px" pt={0.1}>
        <input type="checkbox" checked={!!ticked} disabled={!readBackEnabled}
          onChange={() => onTick(!ticked)}
          aria-label={`The programmer now displays ${f.parameter} as `
            + `${value == null ? "the value I chose" : value} ${f.units || ""}`}
          title={readBackEnabled
            ? `Tick when the A610 itself displays ${f.parameter} as `
              + `${value == null ? "the value you chose" : `${value} ${f.units || ""}`}`
            : "Read-back is disabled because the device does not permit this configuration"}
          style={{ width: 15, height: 15, cursor: readBackEnabled ? "pointer" : "not-allowed",
            background: readBackEnabled ? undefined : PAL.hatch("#BBBBBB"),
            opacity: readBackEnabled ? 1 : 0.45 }} />
      </MDBox>

      {/* 2 — parameter name */}
      <MDBox flex="1 1 200px" pr={1}>
        <MDTypography variant="caption" sx={{ fontSize: 11.5, fontWeight: 600, color: "#2A2A2A" }}>
          {f.parameter}
        </MDTypography>
        <MDTypography variant="caption" sx={{ display: "block", fontSize: 10,
          color: origin.bar ? "#5A5A5A" : "#8A8A8A" }}>
          {origin.label}
        </MDTypography>
      </MDBox>

      {/* 3 — value, right-aligned and monospaced so decimal points line up down the column and a
             narrow digit cannot be mistaken for a wide one. The minutes-and-seconds gloss sits
             directly BENEATH the value rather than in an adjacent column, because an adjacent
             column can be read as belonging to a different field. */}
      <MDBox flex="0 0 130px" sx={{ textAlign: "right" }}>
        {mustChoose && value == null ? (
          <>
            <BlankEntry />
            <MDTypography variant="caption" sx={{ display: "block", fontSize: 10,
              color: PAL.warnText, fontWeight: 600 }}>
              to be chosen
            </MDTypography>
          </>
        ) : (
          <>
            <MDTypography variant="caption" sx={{ display: "block", fontSize: 13,
              fontFamily: PAL.mono, fontWeight: 700, color: "#111111", lineHeight: 1.15 }}>
              {value == null ? "not reported" : value}
            </MDTypography>
            {f.enter_as ? (
              <MDTypography variant="caption" sx={{ display: "block", fontSize: 10.5,
                fontFamily: PAL.mono, fontWeight: 700, color: PAL.warnText }}>
                {`enter as ${f.enter_as}`}
              </MDTypography>
            ) : null}
            {f.device_default != null && String(f.device_default) !== String(f.value) ? (
              <MDTypography variant="caption" sx={{ display: "block", fontSize: 9.5,
                color: "#8A8A8A" }}>
                {`default ${f.device_default}`}
              </MDTypography>
            ) : null}
          </>
        )}
      </MDBox>

      {/* 4 — units in their OWN column, never concatenated onto the number. "1.50 mA" set as one
             string can be read as "150 mA" at a glance on a bright screen; a column boundary
             cannot. */}
      <MDBox flex="0 0 84px" pl={1}>
        <MDTypography variant="caption" sx={{ fontSize: 11, color: "#5A5A5A" }}>
          {f.units || ""}
        </MDTypography>
      </MDBox>

      {/* 5 — what to do, and the qualifiers that must never be separated from the number. */}
      <MDBox flex="1 1 230px" pl={0.5}>
        <MDTypography variant="caption" sx={{ display: "block", fontSize: 10,
          fontWeight: "bold", letterSpacing: 0.3,
          color: computed ? PAL.warnText : confirm.ink }}>
          {computed ? "THE DEVICE COMPUTES THIS \u2014 DO NOT TYPE IT" : confirm.label}
        </MDTypography>
        {f.range_source ? (
          <MDTypography variant="caption" sx={{ display: "block", fontSize: 10.5,
            color: /NOT published/i.test(f.range_source) ? PAL.warnText : "#6A6A6A" }}>
            {f.range_source}
          </MDTypography>
        ) : null}
        {f.range && f.range.length === 2 ? (
          <MDTypography variant="caption" sx={{ display: "block", fontSize: 10.5,
            fontFamily: PAL.mono, color: "#6A6A6A" }}>
            {`published range ${f.range[0]} to ${f.range[1]}`}
          </MDTypography>
        ) : null}
        {confirm.detail ? (
          <MDTypography variant="caption" sx={{ display: "block", fontSize: 10.5,
            color: "#5A5A5A" }}>
            {confirm.detail}
          </MDTypography>
        ) : null}
        {f.why ? (
          <>
            <MDTypography variant="caption" onClick={() => setOpenWhy((o) => !o)}
              sx={{ fontSize: 10.5, color: PAL.accent, cursor: "pointer", display: "block",
                "&:hover": { textDecoration: "underline" } }}>
              {openWhy ? "Hide why this value" : "Why this value"}
            </MDTypography>
            {openWhy ? (
              <MDTypography variant="caption" sx={{ display: "block", fontSize: 10.5, mt: 0.2,
                pl: 0.8, borderLeft: "2px solid rgba(0,0,0,0.12)", color: "#3A3A3A" }}>
                {f.why}
              </MDTypography>
            ) : null}
          </>
        ) : null}
      </MDBox>

      {/* 6 — the row number, so a reader can keep their place in a sixteen-row table and so the
             field count in the banner can be checked against the last number in the column. */}
      <MDBox flex="0 0 26px" sx={{ textAlign: "right" }}>
        <MDTypography variant="caption" sx={{ fontSize: 9.5, fontFamily: PAL.mono,
          color: "#B0B0B0" }}>
          {index + 1}
        </MDTypography>
      </MDBox>
    </MDBox>
  );
}

/**
 * The field-pair coupling banner.
 *
 * A table of independent rows cannot express this finding, because the conflict is a property of a
 * PAIR of fields and belongs to neither row alone. Both field names and both values go on one line
 * in a monospaced face, because the conflict is between them and a reader has to see the pair; the
 * arithmetic is spelled out beneath, because a clinician told that two fields conflict will
 * reasonably want to check it rather than take it on trust.
 */
function CouplingBanner({ c, duty }) {
  if (!c || !c.fields || c.fields.length < 2) return null;
  const [fA, fB] = c.fields;
  const vA = c.values && c.values[0];
  const vB = c.values && c.values[1];
  const uA = (c.units && c.units[0]) || "";
  const uB = (c.units && c.units[1]) || "";
  // The arithmetic is recomputed here from the two values rather than quoted, so that the number of
  // controller steps shown always follows from the two values displayed above it. The module's own
  // count is shown alongside when it is available, and a disagreement between the two would be
  // visible rather than silent.
  const steps = (vA != null && vB != null && Number(vB) > 0)
    ? Math.ceil(Number(vA) / Number(vB)) : null;
  const moduleSteps = duty && duty.onset_windows_upper != null ? duty.onset_windows_upper : null;

  return (
    <MDBox mt={1} p={1.2} sx={{ borderRadius: "4px", backgroundColor: PAL.warnFill,
      border: `1px solid ${PAL.warnBorder}` }}>
      <MDTypography variant="caption" sx={{ display: "block", fontSize: 10, fontWeight: "bold",
        letterSpacing: 0.4, color: PAL.warnText }}>
        {`TWO FIELDS INTERACT \u2014 ${String(c.severity || "noted").toUpperCase()}`}
      </MDTypography>
      <MDTypography variant="caption" sx={{ display: "block", fontSize: 12.5, fontFamily: PAL.mono,
        fontWeight: 700, color: "#111111", mt: 0.3 }}>
        {`${fA} = ${vA} ${uA}    \u00B7    ${fB} = ${vB} ${uB}`}
      </MDTypography>
      {steps != null ? (
        <MDTypography variant="caption" sx={{ display: "block", fontSize: 11.5,
          fontFamily: PAL.mono, color: "#3A3A3A" }}>
          {`ceil(${vA} / ${vB}) = ${steps} controller step${steps === 1 ? "" : "s"}`}
          {moduleSteps != null && moduleSteps !== steps
            ? `   (the module reports ${moduleSteps}; the two disagree and that is worth checking)`
            : ""}
        </MDTypography>
      ) : null}
      {c.consequence ? (
        <MDTypography variant="caption" sx={{ display: "block", fontSize: 11.5, mt: 0.5,
          color: "#2A2A2A" }}>
          {c.consequence}
        </MDTypography>
      ) : null}
      {c.resolution ? (
        <MDTypography variant="caption" sx={{ display: "block", fontSize: 11.5, mt: 0.5,
          color: "#2A2A2A" }}>
          <b>{"What can be done about it.  "}</b>{c.resolution}
        </MDTypography>
      ) : null}
      {/* The honesty about what no document settles has to survive into the interface. It is the
          reason the consequence above is a reading of the documents rather than a citation from
          them, and a reader deciding whether to act on it needs to know which of the two it is. */}
      {c.not_established ? (
        <MDBox mt={0.6} pl={1} sx={{ borderLeft: `3px solid ${PAL.neutral}` }}>
          <MDTypography variant="caption" sx={{ display: "block", fontSize: 10,
            fontWeight: "bold", letterSpacing: 0.3, color: PAL.neutral }}>
            NOT ESTABLISHED BY ANY SUPPLIED DOCUMENT
          </MDTypography>
          <MDTypography variant="caption" sx={{ display: "block", fontSize: 11,
            color: "#4A4A4A" }}>
            {c.not_established}
          </MDTypography>
        </MDBox>
      ) : null}
    </MDBox>
  );
}

/** The mode toggle, with the module's recommendation beside it rather than replacing it. */
function ModeToggle({ modes, mode, onMode, recommended, recommendation }) {
  return (
    <MDBox display="flex" flexDirection="row" gap={2} flexWrap="wrap" alignItems="flex-start">
      <MDBox flex="0 0 auto">
        <MDTypography variant="caption" sx={{ display: "block", fontSize: 10, fontWeight: "bold",
          letterSpacing: 0.4, color: "#8A8A8A", mb: 0.4 }}>
          THRESHOLD MODE — YOUR SELECTION
        </MDTypography>
        <MDBox display="flex" flexDirection="row" gap={0.6} flexWrap="wrap">
          {MODE_ORDER.filter((m) => modes && modes[m]).map((m) => {
            const on = m === mode;
            return (
              <MDButton key={m} size="small" onClick={() => onMode(m)}
                variant={on ? "contained" : "outlined"} color={on ? "info" : "secondary"}
                sx={{ textTransform: "none", fontSize: 11.5, py: 0.4 }}>
                {MODE_LABEL[m] || m}
                {m === recommended ? " \u00B7 recommended" : ""}
              </MDButton>
            );
          })}
        </MDBox>
        <MDTypography variant="caption" sx={{ display: "block", fontSize: 10.5, color: "#7A7A7A",
          mt: 0.4 }}>
          Selecting a mode changes which fields exist, not only their values, so the table below is
          rebuilt and any read-back ticks are cleared.
        </MDTypography>
      </MDBox>

      <MDBox flex="1 1 320px" p={1} sx={{ backgroundColor: PAL.accentFill, borderRadius: "4px",
        border: `1px solid ${PAL.accentBorder}` }}>
        <MDTypography variant="caption" sx={{ display: "block", fontSize: 10, fontWeight: "bold",
          letterSpacing: 0.4, color: PAL.accent }}>
          {`THE MODULE RECOMMENDS ${String(MODE_LABEL[recommended] || recommended || "no mode")
            .toUpperCase()}`}
        </MDTypography>
        {recommendation && recommendation.recommended_because ? (
          <MDTypography variant="caption" sx={{ display: "block", fontSize: 11,
            color: "#2A2A2A" }}>
            {recommendation.recommended_because}
          </MDTypography>
        ) : null}
        {recommendation && recommendation.timescale_measured === false ? (
          <MDTypography variant="caption" sx={{ display: "block", fontSize: 10.5, mt: 0.3,
            color: PAL.warnText }}>
            No biomarker timescale has been measured for this participant, so the recommendation
            rests on the nature of the outcome rather than on this person's data.
          </MDTypography>
        ) : null}
        {mode && recommended && mode !== recommended ? (
          <MDTypography variant="caption" sx={{ display: "block", fontSize: 10.5, mt: 0.3,
            color: PAL.warnText, fontWeight: 600 }}>
            {`You are looking at ${MODE_LABEL[mode] || mode}, which is not the recommended mode. `
              + "The recommendation above is unchanged and your selection will not be reset."}
          </MDTypography>
        ) : null}
        {recommendation && (recommendation.problems || []).length > 0 ? (
          <MDTypography variant="caption" sx={{ display: "block", fontSize: 10.5, mt: 0.3,
            color: PAL.fail }}>
            {`Problems with the recommended mode: ${recommendation.problems.join("; ")}.`}
          </MDTypography>
        ) : null}
      </MDBox>
    </MDBox>
  );
}

/** The mode banner: the field count is the guard against a half-rendered list. */
function ModeBanner({ mode, fields, notApplicable }) {
  return (
    <MDBox mt={1} p={1} sx={{ backgroundColor: PAL.neutralFill, borderRadius: "4px",
      border: `1px solid ${PAL.neutralBorder}` }}>
      <MDTypography variant="caption" sx={{ display: "block", fontSize: 11.5, color: "#2A2A2A" }}>
        <b>{`${MODE_LABEL[mode] || mode}: ${fields.length} `
          + `${fields.length === 1 ? "field" : "fields"}`}</b>
        {notApplicable.length > 0
          ? `, and ${notApplicable.length} field${notApplicable.length === 1 ? "" : "s"} that `
            + `exist${notApplicable.length === 1 ? "s" : ""} in another mode and not in this one.`
          : "."}
        {" Count the rows against that number before you start typing; a table that renders short "
          + "looks the same as a table with fewer fields."}
      </MDTypography>
    </MDBox>
  );
}

export default function PrescriptionPanel({ report, mode, onMode }) {
  // WHICH MODE THE PLANNING VIEW WAS OPENED FOR, rather than a plain open/closed flag.
  //
  // Holding the mode instead of a boolean means the planning view closes by itself when the
  // clinician switches modes, so opening it is a deliberate act once per mode rather than once per
  // page. Without that, a reader who opened the planning view for Dual Threshold and then moved to
  // Single Threshold would find fourteen new parameter values already on screen, having taken no
  // action that acknowledged the device still refuses the configuration. The remounting of the row
  // subtree already clears the read-back ticks on a mode change for the same reason.
  const [planningFor, setPlanningFor] = useState(null);
  const [ticks, setTicks] = useState({});

  const { data, loading, err } = report || { data: null, loading: false, err: null };

  if (loading) {
    return (
      <Card><MDBox p={2}>
        <MDTypography variant="button">Building the device parameter table…</MDTypography>
      </MDBox></Card>
    );
  }

  const pres = data && data.prescriptions;
  if (!data || !pres || !pres.modes) {
    return (
      <Card><MDBox p={2}>
        <MDTypography variant="h6" sx={{ fontSize: 15 }}>Device parameters to transcribe</MDTypography>
        <MDTypography variant="caption" sx={{ display: "block", fontSize: 11.5,
          color: PAL.neutral }}>
          {`No parameter table has been computed for this configuration${err ? ` (${err})` : ""}. `}
          Nothing is being withheld here; the table does not exist yet.
        </MDTypography>
      </MDBox></Card>
    );
  }

  const recommended = pres.recommended;
  const activeMode = mode || pres.selected || recommended || MODE_ORDER[0];
  const m = pres.modes[activeMode] || {};
  const fields = m.fields || [];
  const notApplicable = m.not_applicable || [];
  const couplings = m.couplings || [];
  const unknowns = m.unknowns || [];

  // Fail closed. The device answer, not the statistical one, decides whether values are shown.
  const vd = (data && data.verdict_detail) || {};
  const deviceOk = !!(data.available && vd.device_eligible === true);
  const nFail = ((data.eligibility || {}).failures || []).length;
  const nUnknown = ((data.eligibility || {}).unknowns || []).length;

  // A mode that cannot drive therapy has no prescription, and that is a different state from a
  // prescription that is being withheld. It renders its own note rather than an empty table,
  // because an empty table invites a reader to conclude the values failed to load.
  const cannotDrive = fields.length === 0;

  const readBackEnabled = deviceOk && !cannotDrive;
  const showValues = deviceOk || planningFor === activeMode;

  return (
    <Card className={deviceOk ? "cl-prescription-authorised" : "cl-prescription-planning"}
      sx={{ width: "100%" }}>
      <MDBox p={2}>
        <MDTypography variant="h6" sx={{ fontSize: 15 }}>Device parameters to transcribe</MDTypography>
        <MDTypography variant="caption" sx={{ display: "block", fontSize: 11.5, color: "#4A4A4A" }}>
          Read each value off this table, enter it on the A610, then read it back off the programmer
          and tick the box on the left. The tick attests to what the device now displays, not to
          what was typed, because a field that silently clamped or rounded a value is the failure
          this step exists to catch.
        </MDTypography>

        {/* The toggle sits at the top, above everything the mode governs. */}
        <MDBox mt={1.2}>
          <ModeToggle modes={pres.modes} mode={activeMode} onMode={onMode}
            recommended={recommended} recommendation={pres.recommendation} />
        </MDBox>

        <Divider sx={{ my: 1.2 }} />

        {cannotDrive ? (
          // Single Threshold Inverse. Not an empty table and never presented as programmable.
          <MDBox p={1.2} sx={{ backgroundColor: PAL.neutralFill, borderRadius: "4px",
            border: `1px solid ${PAL.neutralBorder}` }}>
            <MDTypography variant="caption" sx={{ display: "block", fontSize: 10,
              fontWeight: "bold", letterSpacing: 0.4, color: PAL.neutral }}>
              {`${String(MODE_LABEL[activeMode] || activeMode).toUpperCase()} `
                + "\u2014 NOTHING TO TRANSCRIBE"}
            </MDTypography>
            <MDTypography variant="caption" sx={{ display: "block", fontSize: 11.5,
              color: "#2A2A2A", mt: 0.3 }}>
              {m.note || "This mode carries no fields."}
            </MDTypography>
          </MDBox>
        ) : !showValues ? (
          // WITHHELD. The count of what is being held back, the reason, and an explicit way to open
          // a planning view. No value appears anywhere in this branch.
          <MDBox p={1.4} sx={{ backgroundColor: PAL.failFill, borderRadius: "4px",
            border: `1px solid ${PAL.failBorder}` }}>
            <MDTypography variant="caption" sx={{ display: "block", fontSize: 10.5,
              fontWeight: "bold", letterSpacing: 0.4, color: PAL.fail }}>
              {`${fields.length} PARAMETER VALUES WITHHELD`}
            </MDTypography>
            <MDTypography variant="caption" sx={{ display: "block", fontSize: 11.5,
              color: "#2A2A2A", mt: 0.4 }}>
              {!data.available || vd.device_eligible == null
                ? "The device rules have not been evaluated for this configuration, so no value to "
                  + "program is shown. An absent verdict is not permission."
                : `The device does not permit this configuration`
                  + `${nFail ? `: ${nFail} rule${nFail === 1 ? "" : "s"} violated` : ""}`
                  + `${nUnknown ? `, ${nUnknown} that could not be evaluated` : ""}. `
                  + "The values exist and are being held back rather than being missing, because a "
                  + "number on screen during a programming visit gets typed. Clear the device "
                  + "rules first; the ledger above names each one."}
            </MDTypography>
            <MDBox mt={0.8}>
              <MDButton size="small" variant="outlined" color="secondary"
                onClick={() => setPlanningFor(activeMode)}
                sx={{ textTransform: "none", fontSize: 11.5 }}>
                {`Open a read-only planning view of all ${fields.length} values`}
              </MDButton>
              <MDTypography variant="caption" sx={{ display: "block", fontSize: 10.5,
                color: "#6A6A6A", mt: 0.4 }}>
                The planning view is watermarked, its read-back checklist is disabled, and it is
                excluded from the printed sign-off record. It is for deciding what to do next, not
                for programming from.
              </MDTypography>
            </MDBox>
          </MDBox>
        ) : (
          <>
            {/* The planning-view banner, on screen the whole time the values are visible without a
                device permission. */}
            {!deviceOk ? (
              <MDBox mb={1} p={1} sx={{ backgroundColor: PAL.warnFill, borderRadius: "4px",
                border: `2px dashed ${PAL.warnBorder}` }}>
                <MDBox display="flex" justifyContent="space-between" alignItems="center" gap={1}
                  flexWrap="wrap">
                  <MDTypography variant="caption" sx={{ fontSize: 11, fontWeight: "bold",
                    letterSpacing: 0.4, color: PAL.warnText }}>
                    PLANNING VIEW ONLY — NOT AUTHORISED TO PROGRAM. THE DEVICE REFUSES THIS
                    CONFIGURATION.
                  </MDTypography>
                  <MDButton size="small" variant="text" color="secondary"
                    onClick={() => setPlanningFor(null)}
                    sx={{ textTransform: "none", fontSize: 11 }}>
                    Hide these values again
                  </MDButton>
                </MDBox>
              </MDBox>
            ) : null}

            <ModeBanner mode={activeMode} fields={fields} notApplicable={notApplicable} />

            {couplings.map((c, i) => (
              <CouplingBanner key={`cpl${i}`} c={c} duty={m.duty} />
            ))}

            {/* The table. Positioned so the planning watermark can be laid over it. */}
            <MDBox mt={1} sx={{ position: "relative" }}>
              {!deviceOk ? (
                <MDBox sx={{ position: "absolute", inset: 0, zIndex: 2, pointerEvents: "none",
                  display: "flex", alignItems: "center", justifyContent: "center",
                  overflow: "hidden" }}>
                  <MDTypography sx={{ transform: "rotate(-24deg)", fontSize: 44, fontWeight: 800,
                    color: "rgba(138,97,0,0.13)", letterSpacing: 3, whiteSpace: "nowrap",
                    textAlign: "center", lineHeight: 1.1 }}>
                    PLANNING ONLY
                  </MDTypography>
                </MDBox>
              ) : null}

              {/* Column headings. The value column is headed "Value" and NOT "value to enter": what
                  to do with a row lives in its own column, read from the payload, so a row the
                  device computes for itself cannot be turned into an instruction to type it by a
                  column heading. */}
              <MDBox display="flex" flexDirection="row" pb={0.3}>
                {[["34px", ""], ["1 1 200px", "read back \u2192 parameter"], ["0 0 130px", "value"],
                  ["0 0 84px", "units"], ["1 1 230px", "what to do with it"], ["0 0 26px", ""]]
                  .map(([flex, h], i) => (
                    <MDBox key={`ph${i}`} flex={flex.indexOf(" ") > 0 ? flex : `0 0 ${flex}`}
                      sx={{ textAlign: i === 2 ? "right" : "left" }}>
                      <MDTypography variant="caption" sx={{ fontSize: 9.5, fontWeight: "bold",
                        letterSpacing: 0.3, color: "#8A8A8A" }}>
                        {h.toUpperCase()}
                      </MDTypography>
                    </MDBox>
                ))}
              </MDBox>

              {/* Remounted on a mode change: `key` includes the mode, so React discards the row
                  subtree and every read-back tick with it. A tick attesting to a Dual Threshold
                  value must not survive into a Single Threshold table. */}
              <MDBox key={`rows-${activeMode}`}>
                {fields.map((f, i) => (
                  <FieldRow key={`${activeMode}-${f.parameter}`} f={f} index={i}
                    ticked={!!ticks[`${activeMode}|${f.parameter}`]}
                    onTick={(on) => setTicks((t) => ({ ...t,
                      [`${activeMode}|${f.parameter}`]: on }))}
                    readBackEnabled={readBackEnabled} />
                ))}
              </MDBox>
            </MDBox>

            {/* Fields that exist in another mode and not in this one, struck through rather than
                omitted. An omitted row is indistinguishable from a row somebody forgot, and two
                modes rendered as the same table with different numbers would hide the fact that
                the field SET differs. */}
            <MDBox mt={1.4}>
              <MDTypography variant="caption" sx={{ display: "block", fontSize: 10,
                fontWeight: "bold", letterSpacing: 0.4, color: PAL.neutral }}>
                {`NOT APPLICABLE IN ${String(MODE_LABEL[activeMode] || activeMode).toUpperCase()}`
                  + ` \u00B7 ${notApplicable.length}`}
              </MDTypography>
              {notApplicable.length === 0 ? (
                <MDTypography variant="caption" sx={{ display: "block", fontSize: 11,
                  color: "#8A8A8A" }}>
                  No field from another mode is excluded in this one.
                </MDTypography>
              ) : notApplicable.map((f) => (
                <MDBox key={`na-${f.parameter}`} display="flex" flexDirection="row" py={0.35}
                  sx={{ borderTop: "1px solid rgba(0,0,0,0.06)" }}>
                  <MDBox flex="1 1 220px">
                    <MDTypography variant="caption" sx={{ fontSize: 11.5, color: "#9A9A9A",
                      textDecoration: "line-through" }}>
                      {`${f.parameter}${f.units ? ` (${f.units})` : ""}`}
                    </MDTypography>
                  </MDBox>
                  <MDBox flex="2 1 380px">
                    <MDTypography variant="caption" sx={{ fontSize: 10.5, color: "#6A6A6A" }}>
                      {f.why}
                    </MDTypography>
                  </MDBox>
                </MDBox>
              ))}
            </MDBox>
          </>
        )}

        {/* Everything the module says it does not know about this table, kept with the table. */}
        {unknowns.length > 0 ? (
          <MDBox mt={1.4} p={1} sx={{ backgroundColor: PAL.warnFill, borderRadius: "4px",
            border: `1px solid ${PAL.warnBorder}` }}>
            <MDTypography variant="caption" sx={{ display: "block", fontSize: 10,
              fontWeight: "bold", letterSpacing: 0.4, color: PAL.warnText }}>
              {`${unknowns.length} THING${unknowns.length === 1 ? "" : "S"} THE RECORD CANNOT `
                + "SETTLE ABOUT THESE FIELDS"}
            </MDTypography>
            {unknowns.map((u, i) => (
              <MDTypography key={`unk${i}`} variant="caption"
                sx={{ display: "block", fontSize: 11, color: "#2A2A2A", mt: 0.2 }}>
                {`\u00B7 ${u}`}
              </MDTypography>
            ))}
          </MDBox>
        ) : null}

        {/* The mode note, but NOT when the mode cannot drive therapy: that branch already renders
            the same note as its whole content, and a rendering test against the real payload caught
            it appearing twice on one card. A note repeated verbatim reads as two separate findings
            about the mode rather than one. */}
        {m.note && !cannotDrive ? (
          <MDTypography variant="caption" sx={{ display: "block", fontSize: 10.5, mt: 1,
            color: "#6A6A6A" }}>
            {m.note}
          </MDTypography>
        ) : null}

        {/* One statement about display precision, beneath the table rather than repeated per row.
            The module states that it does not round these values, because no supplied document
            publishes a resolution grid for the threshold fields to round to. Four decimal places
            here is therefore a reading aid and not a claim about what the device accepts. */}
        <MDTypography variant="caption" sx={{ display: "block", fontSize: 10.5, mt: 0.5,
          color: "#6A6A6A" }}>
          Amplitudes are shown to two decimal places always, durations as whole milliseconds, and
          band-power thresholds to four decimal places. The four-place display is a reading aid: the
          module deliberately does not round these values, because no supplied document publishes a
          resolution grid for them. The module labels the threshold quantity &ldquo;LFP power&rdquo;,
          which is the same quantity the device Timeline reports as LSB; the payload&rsquo;s own
          wording is used here rather than substituting one name for the other.
        </MDTypography>

        {/* A count of the read-back progress, so the checklist has a completion state rather than
            only a set of boxes. */}
        {readBackEnabled && fields.length > 0 ? (
          <MDTypography variant="caption" sx={{ display: "block", fontSize: 11, mt: 0.8,
            fontWeight: 600,
            color: fields.every((f) => ticks[`${activeMode}|${f.parameter}`])
              ? PAL.pass : PAL.warnText }}>
            {`${fields.filter((f) => ticks[`${activeMode}|${f.parameter}`]).length} of `
              + `${fields.length} fields read back off the programmer.`}
          </MDTypography>
        ) : null}
      </MDBox>
    </Card>
  );
}
