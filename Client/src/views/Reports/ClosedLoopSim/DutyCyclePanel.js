/**
 * The predicted duty cycle, and the caveats that must not be separable from it.
 *
 * WHY THE TITLE IS A CONDITIONAL SENTENCE. A title reading "Predicted duty cycle" invites a reader
 * to treat the numbers below it as a forecast. They are not a forecast: the band power they are
 * computed from was recorded while the amplitude followed this participant's ACTUAL programming, so
 * using it to predict time-in-state assumes the same power would have occurred under closed-loop
 * control — and that assumption is false exactly when the band responds to amplitude, which is the
 * whole reason for wanting to deploy the band. Putting the if-clause in the title is the only
 * placement a reader cannot scroll away from, and it costs nothing.
 *
 * WHY THE BAR IS HATCHED. The hatch is this page's caveat channel and is used for nothing else. It
 * is not possible to read a percentage off the bar without also seeing that the bar is hatched, and
 * the legend keys the hatch to the open-loop assumption above. That is the strongest available way
 * of making a caveat travel with a number rather than sitting in a footnote — and a footnote would
 * be the wrong home regardless, because this page prints into the sign-off record.
 *
 * WHY THE WHOLE CARD HAS A DASHED FRAME. Proposed as a page-wide convention: a solid frame means the
 * quantity was observed, and a dashed frame means a model says it would happen. A reader learns the
 * convention once and then never has to ask which kind of number they are looking at. This is the
 * only dashed card on the clinician route, which is itself informative.
 *
 * THE ONE HARD RULE THE BACKEND ENFORCES AND THIS PANEL HAS TO RESPECT. When
 * `fractions_are_of_observed_samples` is true, the three state fractions are fractions of the
 * SAMPLES ON RECORD and not of the day, and the panel must not print a percentage of the day
 * anywhere. For RCS08 the two differ by roughly four orders of magnitude: the record holds about
 * 1.2 hours of signal spread across about 9,936 hours of elapsed time. A chronic Percept record is
 * sampled in short bursts minutes apart, and the bursts are not a random sample of the day either,
 * because streaming happens when the participant or the clinic starts it. So the labels say what
 * the denominator is, in words, on the bar itself.
 */
import { Card } from "@mui/material";
import MDBox from "components/MDBox";
import MDTypography from "components/MDTypography";

import PAL from "./palette";
import { MODE_LABEL, fmtNum, fmtPct } from "./deployFormat";

const isNum = (v) => v != null && Number.isFinite(Number(v));

/**
 * The three-state split as one stacked horizontal bar.
 *
 * A stacked bar rather than three separate bars because the three fractions are parts of one whole,
 * and a stacked bar is the encoding that makes summing to one visible. Sequential shades of one blue
 * rather than three hues because the three states are ordinally related — below the lower threshold,
 * between the two, above the upper — and a single-hue ramp encodes that order where categorical
 * hues would assert that the three states are unrelated kinds.
 */
function StateBar({ below, between, above, denominatorPhrase }) {
  const parts = [
    { key: "below", label: "below the lower threshold", v: below, ink: PAL.dutyBelow, text: "#123" },
    { key: "between", label: "between the thresholds", v: between, ink: PAL.dutyBetween,
      text: "#fff" },
    { key: "above", label: "above the upper threshold", v: above, ink: PAL.dutyAbove, text: "#fff" },
  ];
  const total = parts.reduce((s, p) => s + (isNum(p.v) ? Number(p.v) : 0), 0);
  if (total <= 0) {
    return (
      <MDTypography variant="caption" sx={{ display: "block", fontSize: 11.5, color: PAL.neutral }}>
        The three band-power state fractions are not reported for this configuration, so no split is
        drawn. An empty bar would read as three states of zero, which is a different claim.
      </MDTypography>
    );
  }

  return (
    <MDBox>
      <MDBox display="flex" flexDirection="row" sx={{ width: "100%", height: 42,
        borderRadius: "3px", overflow: "hidden", border: "1px solid rgba(0,0,0,0.25)" }}>
        {parts.map((p) => {
          const frac = isNum(p.v) ? Number(p.v) / total : 0;
          if (frac <= 0) return null;
          return (
            <MDBox key={p.key} sx={{
              width: `${frac * 100}%`,
              // The fill, with the caveat hatch laid over it. Two backgrounds in one declaration so
              // the hatch cannot be styled off independently of the fill it qualifies.
              background: `repeating-linear-gradient(45deg, rgba(255,255,255,0.55) 0 3px, `
                + `rgba(255,255,255,0) 3px 7px), ${p.ink}`,
              display: "flex", alignItems: "center", justifyContent: "center",
            }}>
              <MDTypography variant="caption" sx={{ fontSize: 11, fontWeight: 700, color: p.text,
                fontFamily: PAL.mono }}>
                {frac >= 0.08 ? fmtPct(p.v, 1) : ""}
              </MDTypography>
            </MDBox>
          );
        })}
      </MDBox>

      {/* The legend names each state AND states the denominator in words on the same line, so a
          percentage can never be read off the bar without its denominator. */}
      <MDBox mt={0.6}>
        {parts.map((p) => (
          <MDBox key={`lg-${p.key}`} display="flex" flexDirection="row" alignItems="center"
            gap={0.7} py={0.15}>
            <MDBox sx={{ width: 14, height: 11, flex: "0 0 auto", borderRadius: "2px",
              border: "1px solid rgba(0,0,0,0.25)",
              background: `repeating-linear-gradient(45deg, rgba(255,255,255,0.55) 0 3px, `
                + `rgba(255,255,255,0) 3px 7px), ${p.ink}` }} />
            <MDTypography variant="caption" sx={{ fontSize: 11, color: "#2A2A2A" }}>
              <b style={{ fontFamily: PAL.mono }}>{fmtPct(p.v, 1)}</b>
              {` of ${denominatorPhrase} \u2014 band power ${p.label}`}
            </MDTypography>
          </MDBox>
        ))}
        <MDBox display="flex" flexDirection="row" alignItems="center" gap={0.7} pt={0.3}>
          <MDBox sx={{ width: 14, height: 11, flex: "0 0 auto", borderRadius: "2px",
            border: "1px solid rgba(0,0,0,0.25)",
            background: "repeating-linear-gradient(45deg, rgba(0,0,0,0.45) 0 3px, "
              + "rgba(0,0,0,0) 3px 7px)" }} />
          <MDTypography variant="caption" sx={{ fontSize: 10.5, color: "#5A5A5A" }}>
            The hatch across every segment marks the open-loop assumption: this band power was
            recorded under the participant&rsquo;s actual programming, not under closed-loop
            control.
          </MDTypography>
        </MDBox>
      </MDBox>
    </MDBox>
  );
}

/** A labelled figure with its own qualifier, for the counts beside the bar. */
function Stat({ label, value, qualifier, ink }) {
  return (
    <MDBox py={0.4} sx={{ borderTop: "1px solid rgba(0,0,0,0.07)" }}>
      <MDTypography variant="caption" sx={{ display: "block", fontSize: 10,
        fontWeight: "bold", letterSpacing: 0.3, color: "#8A8A8A" }}>
        {label.toUpperCase()}
      </MDTypography>
      <MDTypography variant="caption" sx={{ display: "block", fontSize: 13, fontFamily: PAL.mono,
        fontWeight: 700, color: ink || "#111111" }}>
        {value}
      </MDTypography>
      {qualifier ? (
        <MDTypography variant="caption" sx={{ display: "block", fontSize: 10.5,
          color: ink || "#5A5A5A" }}>
          {qualifier}
        </MDTypography>
      ) : null}
    </MDBox>
  );
}

export default function DutyCyclePanel({ report, mode }) {
  const { data, loading, err } = report || { data: null, loading: false, err: null };

  if (loading) {
    return (
      <Card><MDBox p={2}>
        <MDTypography variant="button">Computing the predicted duty cycle…</MDTypography>
      </MDBox></Card>
    );
  }

  const pres = data && data.prescriptions;
  const activeMode = mode || (pres && (pres.selected || pres.recommended)) || "dual";
  // The duty cycle is a property of the selected mode, because the thresholds and the timing
  // parameters it is computed from differ between modes. The per-mode block is preferred, and the
  // top-level prescription's copy is the fallback for a payload that predates the per-mode split.
  const modeBlock = (pres && pres.modes && pres.modes[activeMode]) || null;

  // A MODE THAT CANNOT DRIVE THERAPY GETS NO DUTY CYCLE, whatever the payload carries for it.
  //
  // This guard was added because a rendering test against the real payload showed the panel
  // reporting a full duty cycle under a heading naming Single Threshold Inverse. The payload sets
  // that mode's own `duty` to null, correctly, but the fallback below then reached the top-level
  // `prescription.duty` — which is the DUAL Threshold duty cycle — and rendered its three
  // band-power state fractions as though they belonged to the inverse mode. A reader comparing
  // modes would have seen three plausible percentages and reasonably concluded the mode does
  // something, when it has no programmable fields and cannot drive therapy at all.
  //
  // The field count is the test rather than the presence of a duty block, because the field count
  // is what determines whether there is a controller to model, and because that is the check that
  // keeps the fallback from reintroducing the same defect.
  const modeCanDrive = !modeBlock || (modeBlock.fields || []).length > 0;
  const duty = modeCanDrive
    ? ((modeBlock && modeBlock.duty) || (data && data.prescription && data.prescription.duty) || null)
    : null;
  const replay = (data && data.replay) || null;

  if (!data || !duty) {
    return (
      <Card sx={{ border: "2px dashed rgba(0,0,0,0.25)" }}><MDBox p={2}>
        <MDTypography variant="h6" sx={{ fontSize: 15 }}>
          If the same band power occurred under closed-loop control, how would the time divide?
        </MDTypography>
        <MDTypography variant="caption" sx={{ display: "block", fontSize: 11.5,
          color: PAL.neutral }}>
          {duty === null && data
            ? `No duty cycle is computed for ${MODE_LABEL[activeMode] || activeMode}`
              + `${activeMode === "single_inverse"
                ? ", because that mode cannot drive therapy and so has no controller to model."
                : "."}`
            : `The duty cycle has not been computed for this configuration${err ? ` (${err})` : ""}.`}
        </MDTypography>
      </MDBox></Card>
    );
  }

  const observedSamples = duty.fractions_are_of_observed_samples === true;
  // The single most important string in this panel. When the flag is true the denominator is the
  // samples on record; the words "of the day" must not appear anywhere, and the phrase is built
  // once here and threaded into every label so no individual label can drift off it.
  const denominatorPhrase = observedSamples
    ? "the samples on record"
    : "the elapsed time on record";

  const onsetInoperative = duty.onset_inoperative === true;
  const rampResolvable = replay && replay.params ? replay.params.ramp_resolvable : null;
  const amplitudeAnswerable = isNum(duty.stim_frac_at_upper) || isNum(duty.mean_amplitude_mA);

  return (
    // Dashed frame: every number in this card is modelled rather than observed.
    <Card sx={{ width: "100%", border: "2px dashed rgba(0,0,0,0.28)" }}>
      <MDBox p={2}>
        <MDTypography variant="h6" sx={{ fontSize: 15, lineHeight: 1.3 }}>
          If the same band power occurred under closed-loop control, how would the time divide?
        </MDTypography>
        <MDTypography variant="caption" sx={{ display: "block", fontSize: 11.5, color: "#4A4A4A" }}>
          {`Modelled for ${MODE_LABEL[activeMode] || activeMode}. The dashed frame around this card `
            + "marks every number inside it as modelled rather than measured; every other card on "
            + "this page has a solid frame."}
        </MDTypography>

        {/* COVERAGE FIRST, before any fraction, because it is what tells a reader how much the
            fractions are a fraction of. */}
        <MDBox mt={1} p={1} sx={{ backgroundColor: observedSamples ? PAL.warnFill : PAL.neutralFill,
          borderRadius: "4px",
          border: `1px solid ${observedSamples ? PAL.warnBorder : PAL.neutralBorder}` }}>
          <MDTypography variant="caption" sx={{ display: "block", fontSize: 10,
            fontWeight: "bold", letterSpacing: 0.4,
            color: observedSamples ? PAL.warnText : PAL.neutral }}>
            WHAT THE FRACTIONS BELOW ARE FRACTIONS OF
          </MDTypography>
          <MDTypography variant="caption" sx={{ display: "block", fontSize: 11.5,
            color: "#2A2A2A" }}>
            {observedSamples
              ? `They are fractions of ${denominatorPhrase}, not of the day. The record holds `
                + `${fmtNum(duty.hours_of_signal, 1)} hours of signal across `
                + `${fmtNum(duty.hours_observed, 0)} hours of elapsed time, which is a coverage of `
                + `${fmtPct(duty.coverage_frac, 4)}. A chronic Percept record is sampled in short `
                + "bursts minutes apart, and those bursts are not a random sample of the day "
                + "either, because streaming happens when the participant or the clinic starts it."
              : `They are fractions of ${denominatorPhrase}. Coverage is `
                + `${fmtPct(duty.coverage_frac, 4)}: `
                + `${fmtNum(duty.hours_of_signal, 1)} hours of signal across `
                + `${fmtNum(duty.hours_observed, 0)} hours elapsed.`}
          </MDTypography>
        </MDBox>

        <MDBox mt={1.2}>
          <StateBar below={duty.lfp_frac_below} between={duty.lfp_frac_between}
            above={duty.lfp_frac_above} denominatorPhrase={denominatorPhrase} />
        </MDBox>

        {/* The counts. The transition rate changes register when the persistence requirement is not
            operating, because a high rate of state changes on a controller with no working onset
            requirement is the signature of a loop chasing noise rather than tracking a biomarker. */}
        <MDBox mt={1.2}>
          <Stat label="Qualified state changes per hour"
            value={fmtNum(duty.transitions_per_hour, 3)}
            ink={onsetInoperative ? PAL.warnText : undefined}
            qualifier={onsetInoperative
              ? "Read this together with the onset finding below. The persistence requirement is "
                + "not operating, so a state change needs no confirmation beyond a single averaged "
                + "sample, and this rate therefore counts changes the controller would act on "
                + "immediately."
              : null} />
          <Stat label="Qualified state changes in the record"
            value={duty.qualified_transitions == null ? "not reported"
              : String(duty.qualified_transitions)}
            qualifier={`counted across ${denominatorPhrase}`} />
          <Stat label="Unqualified excursions"
            value={duty.unqualified_excursions == null ? "not reported"
              : String(duty.unqualified_excursions)}
            ink={onsetInoperative && duty.unqualified_excursions === 0 ? PAL.warnText : undefined}
            qualifier={onsetInoperative && duty.unqualified_excursions === 0
              ? "This count is zero BECAUSE the onset is inoperative, not because the signal is "
                + "clean: with a one-step requirement nothing can fail to persist, so there is no "
                + "excursion left for the onset to reject."
              : "threshold crossings that did not satisfy the onset duration"} />
        </MDBox>

        {/* THE ONSET FINDING, with the arithmetic. This is the same finding the coupling banner on
            the prescription panel carries; it is repeated here because a reader who came to this
            panel for the transition rate needs it in order to read that rate correctly. */}
        {onsetInoperative ? (
          <MDBox mt={1.2} p={1} sx={{ backgroundColor: PAL.warnFill, borderRadius: "4px",
            border: `1px solid ${PAL.warnBorder}` }}>
            <MDTypography variant="caption" sx={{ display: "block", fontSize: 10,
              fontWeight: "bold", letterSpacing: 0.4, color: PAL.warnText }}>
              THE ONSET DURATION IS INOPERATIVE AT THIS AVERAGING DURATION
            </MDTypography>
            <MDTypography variant="caption" sx={{ display: "block", fontSize: 11.5,
              fontFamily: PAL.mono, color: "#111111", mt: 0.2 }}>
              {`upper onset spans ${duty.onset_windows_upper} controller `
                + `step${duty.onset_windows_upper === 1 ? "" : "s"} \u00B7 `
                + `lower onset spans ${duty.onset_windows_lower} `
                + `step${duty.onset_windows_lower === 1 ? "" : "s"}`}
            </MDTypography>
            <MDTypography variant="caption" sx={{ display: "block", fontSize: 11.5,
              color: "#2A2A2A" }}>
              At one controller step the first averaged sample past a threshold already satisfies
              the onset, so there is no persistence requirement at all and the only protection
              against acting on one noisy window is the separation between the two thresholds. The
              parameter table above carries the two field values this follows from.
            </MDTypography>
            {/* PROVENANCE OF THE SEPARATION FLOOR, added 2026-09-05 on the PI's instruction to make
                it explicit on the page. The sentence is deliberately one line: the number is ours,
                not Medtronic's, and a reader deciding whether to argue with a refusal needs to know
                that without reading the module. Until today the same criterion was declared twice
                at different values (0.5 in StimOptimizer's response test, 1.0 in this module's
                threshold placement), so a band could clear the screen and be refused here; both now
                import the looser definition from one place. */}
            <MDTypography variant="caption" sx={{ display: "block", fontSize: 10.5,
              color: "#6A6A6A", fontStyle: "italic", mt: 0.4 }}>
              Capture separation floor 0.5 is our judgement, not a Medtronic figure.
            </MDTypography>
          </MDBox>
        ) : null}

        {/* THE PREDICTED FAILURE MODE, when the module names one. Each of the failure states has a
            different remedy and two of the remedies move parameters in opposite directions, so a
            generic warning here would be worse than none. */}
        <MDBox mt={1.2} p={1} sx={{ borderRadius: "4px",
          backgroundColor: duty.predicted_failure_mode ? PAL.failFill : PAL.neutralFill,
          border: `1px solid ${duty.predicted_failure_mode ? PAL.failBorder
            : PAL.neutralBorder}` }}>
          <MDTypography variant="caption" sx={{ display: "block", fontSize: 10,
            fontWeight: "bold", letterSpacing: 0.4,
            color: duty.predicted_failure_mode ? PAL.fail : PAL.neutral }}>
            PREDICTED CONTROLLER FAILURE MODE
          </MDTypography>
          <MDTypography variant="caption" sx={{ display: "block", fontSize: 11.5,
            color: "#2A2A2A" }}>
            {duty.predicted_failure_mode
              || "The module does not predict one of its named failure modes for this "
                + "configuration. That is not a statement that the controller would behave well; "
                + "it is a statement that none of the specific patterns the module checks for was "
                + "matched."}
          </MDTypography>
        </MDBox>

        {/* THE AMPLITUDE SIDE. These are the fractions a clinician actually asks about, and they
            are null here because the replay refused to run rather than because nobody computed
            them. Rendering that as a blank or a zero would be a false answer to a real question. */}
        <MDBox mt={1.2}>
          <MDTypography variant="caption" sx={{ display: "block", fontSize: 10,
            fontWeight: "bold", letterSpacing: 0.4, color: "#8A8A8A" }}>
            WHAT FRACTION OF THE TIME WOULD THE STIMULATION SIT AT EACH AMPLITUDE LIMIT?
          </MDTypography>
          {amplitudeAnswerable ? (
            <MDBox>
              <Stat label="At the upper amplitude limit" value={fmtPct(duty.stim_frac_at_upper, 1)}
                qualifier={`of ${denominatorPhrase} \u2014 an amplitude-range fraction, which is `
                  + "not the same quantity as a time-in-state fraction above"} />
              <Stat label="At the lower amplitude limit" value={fmtPct(duty.stim_frac_at_lower, 1)}
                qualifier={`of ${denominatorPhrase}`} />
              <Stat label="Mean delivered amplitude"
                value={`${fmtNum(duty.mean_amplitude_mA, 2)} mA`} qualifier={null} />
              <Stat label="Amplitude duty" value={fmtPct(duty.amplitude_duty, 1)}
                qualifier="fraction of the adaptive amplitude range that would be used" />
            </MDBox>
          ) : (
            <MDBox p={1} mt={0.3} sx={{ backgroundColor: PAL.neutralFill, borderRadius: "4px",
              border: `1px solid ${PAL.neutralBorder}` }}>
              <MDTypography variant="caption" sx={{ display: "block", fontSize: 11.5,
                fontWeight: 600, color: PAL.warnText }}>
                Not answerable at this sampling cadence &mdash; it needs a streaming session.
              </MDTypography>
              {replay && replay.params ? (
                <MDTypography variant="caption" sx={{ display: "block", fontSize: 11.5,
                  fontFamily: PAL.mono, color: "#111111", mt: 0.3 }}>
                  {`samples arrive every ${fmtNum(replay.params.median_interval_s, 0)} s \u00B7 `
                    + `transition up takes ${fmtNum(replay.params.transition_up_s, 0)} s \u00B7 `
                    + `ramp resolvable: ${rampResolvable === null ? "not reported"
                      : String(rampResolvable)}`}
                </MDTypography>
              ) : null}
              <MDTypography variant="caption" sx={{ display: "block", fontSize: 11.5,
                color: "#2A2A2A", mt: 0.3 }}>
                {(replay && replay.note)
                  || "No replay was run, so no time-at-limit fraction is reported. These four "
                    + "fields are absent because the question was refused, not because the "
                    + "computation was skipped."}
              </MDTypography>
            </MDBox>
          )}
        </MDBox>

        {/* THE MEASURED COMPARISON, left explicitly empty. The device's own Timeline reports the
            same three percentages, so one checks the other, and an empty labelled slot is both the
            honest state of it and a far stronger prompt to go and read the Timeline than a sentence
            would be. */}
        <MDBox mt={1.2}>
          <MDTypography variant="caption" sx={{ display: "block", fontSize: 10,
            fontWeight: "bold", letterSpacing: 0.4, color: "#8A8A8A" }}>
            WHAT THE DEVICE ACTUALLY DID &mdash; TO BE FILLED IN FROM THE TIMELINE
          </MDTypography>
          <MDBox display="flex" flexDirection="row" gap={0.8} mt={0.4}>
            {["below the lower threshold", "between the thresholds", "above the upper threshold"]
              .map((lbl) => (
                <MDBox key={`slot-${lbl}`} flex="1 1 0" p={1} sx={{ borderRadius: "3px",
                  border: "1.5px dashed rgba(0,0,0,0.28)", textAlign: "center" }}>
                  <MDTypography variant="caption" sx={{ display: "block", fontSize: 15,
                    fontFamily: PAL.mono, color: "#BBBBBB" }}>
                    &nbsp;
                  </MDTypography>
                  <MDTypography variant="caption" sx={{ display: "block", fontSize: 10,
                    color: "#8A8A8A" }}>
                    {lbl}
                  </MDTypography>
                </MDBox>
            ))}
          </MDBox>
          <MDTypography variant="caption" sx={{ display: "block", fontSize: 10.5, color: "#6A6A6A",
            mt: 0.3 }}>
            These three cells hold the same three quantities the modelled bar above shows, as the
            device measured them. Reading them off the programmer&rsquo;s Timeline and entering them
            here is what turns this panel from a screening estimate into a measurement.
          </MDTypography>
        </MDBox>

        {/* EVERY CAVEAT THE MODULE EMITTED, kept with the numbers rather than moved to a footnote.
            They are not interchangeable: one says the prediction rests on an assumption that may be
            false, another says the denominator is not what a reader would assume, and a third says
            a parameter visible in the table above is doing nothing. */}
        {(duty.caveats || []).length > 0 ? (
          <MDBox mt={1.2} pt={0.8} sx={{ borderTop: "1px solid rgba(0,0,0,0.12)" }}>
            <MDTypography variant="caption" sx={{ display: "block", fontSize: 10,
              fontWeight: "bold", letterSpacing: 0.4, color: "#8A8A8A" }}>
              {`ALL ${duty.caveats.length} CAVEATS THE MODULE ATTACHED TO THESE NUMBERS`}
            </MDTypography>
            {duty.caveats.map((c, i) => (
              <MDTypography key={`cv${i}`} variant="caption" sx={{ display: "block", fontSize: 11,
                color: "#3A3A3A", mt: 0.35 }}>
                {`${i + 1}. ${c}`}
              </MDTypography>
            ))}
          </MDBox>
        ) : null}
      </MDBox>
    </Card>
  );
}
