/**
 * The fixture test that makes a collapsed N-valued answer detectable.
 *
 * WHAT THIS TEST IS FOR. Every state track on the Closed-Loop Deployment page has three cells
 * because the answer it renders has three values, and the defect this test exists to catch is one
 * of those three values being cast to a boolean somewhere between the module and the screen. The
 * symptom of that defect is silent and specific: one cell of the track can never be lit by any
 * input, so the interface looks correct on every case a reviewer happens to try. The assertion
 * below is therefore a coverage assertion over the fixture set rather than a check of any single
 * case — if a track cell cannot be reached, it fails.
 *
 * It deliberately imports only the pure track definitions and not the React component, so it needs
 * no renderer, no DOM and no test-library dependency. The arity of a track is a property of the
 * data model, and testing it at the model is both cheaper and stricter than testing it through
 * markup.
 */
import { TRACKS, coherenceReading } from "./stateTracks";
import { parseSignPattern } from "./deployFormat";

// Four payload shapes, chosen to span the states rather than to be realistic in every field. Only
// the keys the `lit` functions read are populated; anything else would suggest to a later reader
// that some other field participates in the decision, and none does.
const FIXTURES = {
  // Nothing has loaded. "We have not looked yet" is one of the three states, not an error case.
  no_report: null,

  // The RCS08 state as of 2026-09-04: the device refuses the configuration, all three edges are
  // resolved, and their signs do not match the pattern Dual Threshold requires.
  rcs08_blocked_and_misaligned: {
    available: true,
    verdict_detail: { device_eligible: false, all_edges_resolved: true, coherent: false },
    coherence: { coherent: false },
  },

  // A configuration that clears both questions, which is the only state in which the parameter
  // table is shown with its read-back checklist enabled.
  cleared_and_coherent: {
    available: true,
    verdict_detail: { device_eligible: true, all_edges_resolved: true, coherent: true },
    coherence: { coherent: true },
  },

  // The device permits the configuration but the evidence has not spoken: at least one edge is
  // unresolved, so the coherence test returns null rather than false. This is the fixture that
  // lights the "not established" cell, and it is the one a boolean collapse makes unreachable.
  permitted_but_evidence_unestablished: {
    available: true,
    verdict_detail: { device_eligible: true, all_edges_resolved: false, coherent: null },
    coherence: { coherent: null },
  },
};

describe("state tracks", () => {
  it("lights exactly one cell per track for every fixture, including the empty one", () => {
    Object.entries(TRACKS).forEach(([name, track]) => {
      Object.entries(FIXTURES).forEach(([fname, data]) => {
        const i = track.lit(data);
        expect(Number.isInteger(i)).toBe(true);
        expect(i).toBeGreaterThanOrEqual(0);
        expect(i).toBeLessThan(track.cells.length);
        expect(`${name}/${fname}/${track.cells[i].key}`).toBeTruthy();
      });
    });
  });

  it("reaches every cell of every track across the fixture set", () => {
    Object.entries(TRACKS).forEach(([name, track]) => {
      const reached = new Set(Object.values(FIXTURES).map((d) => track.lit(d)));
      const dark = track.cells
        .map((c, i) => (reached.has(i) ? null : `${name}.${c.key}`))
        .filter(Boolean);
      // A dark cell means one state of this answer cannot be produced by any input. That is the
      // signature of a three-valued field being carried as a boolean, so the message names the
      // unreachable cell rather than only reporting a count.
      expect(dark).toEqual([]);
    });
  });

  it("keeps 'not established' on the neutral role and never on the failure role", () => {
    // Collected and asserted once rather than asserted inside the loop, so a failure names every
    // offending cell instead of stopping at the first. Grey says the question is still open; the
    // failure ink says an answer came back and it was bad, and painting an unanswered question red
    // would tell a reader to abandon a configuration nobody has assessed.
    const misroled = [];
    Object.entries(TRACKS).forEach(([name, track]) => {
      track.cells.forEach((c) => {
        const isOpenState = /not_established|unestablished|unevaluated/.test(c.key);
        if (isOpenState && c.role !== "neutral") misroled.push(`${name}.${c.key}=${c.role}`);
      });
    });
    expect(misroled).toEqual([]);
  });
});

describe("coherence reading", () => {
  // RCS08's live pattern. The three edges compose consistently — raising amplitude raises band
  // power, higher band power goes with less pain, and raising amplitude reduces pain — and that
  // self-consistent story is still not the one Dual Threshold's control law assumes. Both halves
  // are asserted here because the interface has to be able to say them separately.
  const observed = { E1: 1, E2: -1, E3: -1 };
  const expected = { E1: -1, E2: 1, E3: -1 };

  it("reports the three edges as agreeing with each other", () => {
    expect(coherenceReading(observed, expected).edgesAgreeInternally).toBe(true);
  });

  it("reports the same three edges as not matching the control law, naming which edges differ", () => {
    const r = coherenceReading(observed, expected);
    expect(r.matchesControlLaw).toBe(false);
    expect(r.mismatchedEdges).toEqual(["E1", "E2"]);
  });

  it("does not claim internal agreement when a sign is missing", () => {
    const r = coherenceReading({ E1: 1, E2: null, E3: -1 }, expected);
    expect(r.haveAllSigns).toBe(false);
    expect(r.edgesAgreeInternally).toBe(false);
    expect(r.matchesControlLaw).toBe(false);
  });
});

describe("sign-pattern parsing", () => {
  // The backend serialises these two fields as the repr of a Python dictionary, not as JSON: the
  // keys are single-quoted and the expected pattern carries a prose `why` entry containing
  // apostrophes. Both real strings are used verbatim here so a change of serialisation shape shows
  // up as a test failure rather than as three silently absent signs on the page.
  const EXPECTED_REPR = "{'E1': -1, 'E2': 1, 'E3': -1, 'why': 'Dual Threshold ramps amplitude UP "
    + "when band power rises above the upper threshold (white paper p. 13), because the control "
    + "law assumes power FALLS as amplitude rises.'}";
  const OBSERVED_REPR = "{'E1': 1, 'E2': -1, 'E3': -1}";

  it("reads the three signs out of the Python repr the backend sends", () => {
    expect(parseSignPattern(EXPECTED_REPR)).toEqual({ E1: -1, E2: 1, E3: -1 });
    expect(parseSignPattern(OBSERVED_REPR)).toEqual({ E1: 1, E2: -1, E3: -1 });
  });

  it("returns null signs rather than throwing when the field is absent or reshaped", () => {
    expect(parseSignPattern(null)).toEqual({ E1: null, E2: null, E3: null });
    expect(parseSignPattern("something else entirely")).toEqual({ E1: null, E2: null, E3: null });
  });

  it("also reads a real object, in case the backend starts sending JSON", () => {
    expect(parseSignPattern({ E1: -1, E2: 1, E3: -1 })).toEqual({ E1: -1, E2: 1, E3: -1 });
  });
});
