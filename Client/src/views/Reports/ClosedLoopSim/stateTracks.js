/**
 * The N-valued state tracks rendered by StateTrack, defined as data rather than as markup.
 *
 * WHY THIS FILE EXISTS AT ALL. Several of the answers on this page have three states and not two,
 * and each of them had previously been collapsed to a boolean somewhere between the module and the
 * screen. Sign coherence is the clearest case: `coherence.coherent` is true, false, or null meaning
 * that the test could not be run, and "the evidence contradicts this configuration" is a completely
 * different finding from "the evidence has not spoken". A boolean cannot carry the difference, and
 * once the difference is lost at any layer no amount of care in the component recovers it.
 *
 * Holding the tracks here as plain objects buys two things. The component becomes a renderer with
 * no knowledge of any particular question, so a new N-valued answer is a new entry in this file
 * rather than a new component. And the arity of each track becomes testable without rendering
 * anything: StateTrack.fixture.test.js walks this registry against a set of fixtures and asserts
 * that every cell of every track is lit by at least one of them. That assertion is what makes the
 * collapse detectable rather than something code review has to catch every time — a track fed a
 * two-valued input cannot light a three-cell track, so one cell stays dark and the test fails.
 *
 * Colour ROLES are named here, not colour values, so palette.js stays the single place a colour is
 * chosen. The rule that matters: a "not established" cell is always the neutral role and never the
 * failure role, because grey says the question is open and red says the answer came back bad.
 */

/**
 * Each track is `{ label, question, cells: [{ key, label, role, blurb }], lit(data) }`.
 *
 * `lit` takes the whole /api/queryClosedLoopDeployment payload (or null when nothing has loaded)
 * and returns the index of the single cell that is filled. It must return a valid index for every
 * possible input, including null, because there is no such thing as a track with nothing lit: "we
 * have not looked yet" is itself one of the states and has its own cell.
 */
export const TRACKS = {
  /* Does the device permit this configuration to be programmed at all? Read off the encoded
     Percept rule table, which is a question about the device and not about the biomarker. */
  device: {
    label: "Does the device permit this configuration?",
    cells: [
      { key: "permitted", label: "PERMITTED", role: "pass",
        blurb: "Every rule that could be evaluated is satisfied." },
      { key: "refused", label: "NOT PERMITTED", role: "fail",
        blurb: "At least one rule is violated, or has a value that could not be evaluated." },
      { key: "unevaluated", label: "NOT EVALUATED", role: "neutral",
        blurb: "The rule table has not been run for this configuration." },
    ],
    lit: (d) => {
      if (!d || !d.available) return 2;
      const e = (d.verdict_detail || {}).device_eligible;
      if (e === true) return 0;
      if (e === false) return 1;
      return 2;
    },
  },

  /* Does the measured evidence support this configuration? This is a separate question from the
     one above and it has a separate remedy: a device refusal is fixed at the programmer, whereas
     unestablished evidence is fixed only by measuring more. */
  evidence: {
    label: "Does the evidence support this configuration?",
    cells: [
      { key: "supported", label: "SUPPORTED", role: "pass",
        blurb: "All three edges are resolved and their signs match the pattern the selected "
             + "control law requires." },
      { key: "misaligned", label: "NOT ALIGNED WITH THE CONTROL LAW", role: "fail",
        blurb: "All three edges are resolved, and their signs do not match the pattern the "
             + "selected control law requires." },
      { key: "unestablished", label: "NOT ESTABLISHED", role: "neutral",
        blurb: "At least one edge is unresolved, or the coherence test could not be run, so the "
             + "evidence has not answered the question either way." },
    ],
    lit: (d) => {
      if (!d || !d.available) return 2;
      const vd = d.verdict_detail || {};
      if (vd.all_edges_resolved !== true) return 2;
      const co = d.coherence || {};
      if (co.coherent === true) return 0;
      if (co.coherent === false) return 1;
      return 2;
    },
  },

  /* Is there anything for a clinician to transcribe today? Deliberately a separate answer from
     both of the above, because it is the one a reader acts on at a programming visit, and because
     it must be able to say WITHHELD rather than showing a number. */
  transcription: {
    label: "Is there anything to transcribe today?",
    cells: [
      { key: "ready", label: "READY TO TRANSCRIBE", role: "pass",
        blurb: "The device permits the configuration, so the parameter table is shown with its "
             + "read-back checklist enabled." },
      { key: "withheld", label: "WITHHELD", role: "fail",
        blurb: "The device does not permit this configuration, so no value to program is shown. A "
             + "read-only planning view is available and is watermarked as such." },
      { key: "unevaluated", label: "NOT EVALUATED", role: "neutral",
        blurb: "No device answer has been computed, and an absent verdict is not permission." },
    ],
    lit: (d) => {
      if (!d || !d.available) return 2;
      const e = (d.verdict_detail || {}).device_eligible;
      if (e === true) return 0;
      if (e === false) return 1;
      return 2;
    },
  },

  /* The three-valued sign-coherence answer itself, rendered inside the evidence panel next to the
     three edges it is computed from. */
  coherence: {
    label: "Sign coherence",
    cells: [
      { key: "coherent", label: "COHERENT", role: "pass",
        blurb: "The three edge signs match the pattern the selected control law requires." },
      { key: "incoherent", label: "NOT COHERENT", role: "fail",
        blurb: "The three edge signs do not match the pattern the selected control law requires. "
             + "Read the two statements below: the edges can disagree with each other, or agree "
             + "with each other and disagree with the control law, and those are different "
             + "findings." },
      { key: "not_established", label: "NOT ESTABLISHED", role: "neutral",
        blurb: "The coherence test did not return an answer, which is not the same as returning a "
             + "negative one." },
    ],
    lit: (d) => {
      const co = d && d.coherence;
      if (!co) return 2;
      if (co.coherent === true) return 0;
      if (co.coherent === false) return 1;
      return 2;
    },
  },
};

/**
 * The signs the three edges are OBSERVED to have, and the signs the selected control law REQUIRES,
 * reduced to the two questions a reader has to keep apart.
 *
 * `edgesAgreeInternally` asks whether the three edges tell one self-consistent story. The identity
 * it tests is the only arithmetic relation the three edges can have: E1 is the slope of power on
 * amplitude, E2 the slope of pain on power, and E3 the slope of pain on amplitude, so composing the
 * first two has to reproduce the third if all three are describing the same physiology. When
 * sign(E1) x sign(E2) equals sign(E3), the edges agree with each other whatever the device thinks.
 *
 * `matchesControlLaw` asks the separate question of whether the observed signs are the ones the
 * device's control law assumes. A configuration can fail this while passing the first, and that
 * combination is neither a data problem nor a contradiction — it means the physiology is coherent
 * and the device would drive it the wrong way. Collapsing the two into one red verdict would tell a
 * reader to go and re-measure when the actual remedy is to choose a different band or a different
 * mode, so the two are computed separately and reported separately.
 */
export function coherenceReading(observed, expected) {
  const o = observed || {};
  const e = expected || {};
  const haveAll = ["E1", "E2", "E3"].every((k) => o[k] != null && Number(o[k]) !== 0);
  const composed = haveAll ? Math.sign(Number(o.E1)) * Math.sign(Number(o.E2)) : null;
  const mismatched = ["E1", "E2", "E3"].filter(
    (k) => o[k] != null && e[k] != null && Math.sign(Number(o[k])) !== Math.sign(Number(e[k])),
  );
  return {
    haveAllSigns: haveAll,
    composedSign: composed,
    edgesAgreeInternally: haveAll && composed === Math.sign(Number(o.E3)),
    matchesControlLaw: mismatched.length === 0 && haveAll,
    mismatchedEdges: mismatched,
  };
}

export default TRACKS;
