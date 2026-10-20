/** Synthetic UI contract regression. No live participant response or empirical validation. */
import fs from "fs";
import path from "path";
import "@testing-library/jest-dom";
import { fireEvent, render as rtlRender, screen } from "@testing-library/react";
import DecisionCard, { decisionStatus, deviceBullets, unevaluatedBullets, stimulatorLine, UncheckedStimulatorCard } from "./DecisionCard";
import LEFT from "./__fixtures__/synthetic_allowed_left.json";
import RIGHT from "./__fixtures__/synthetic_refused_right.json";
import SUM_L from "./__fixtures__/synthetic_summary_left.json";
import SUM_R from "./__fixtures__/synthetic_summary_right.json";
import { limitsSourceWords } from "./ClosedLoopSimulationPanel";
import { withheldIfOtherBand } from "./candidateRequestParams";
import { clone, wrap } from "testUtils/render";

jest.mock("plotly.js-dist", () => ({
  react: jest.fn(), purge: jest.fn(), restyle: jest.fn(), relayout: jest.fn(), newPlot: jest.fn(),
  toImage: jest.fn(),
}));
jest.mock("database/session-control", () => ({ SessionController: { query: jest.fn() } }));

const BC_L = { contact: "ONE_THREE_LEFT", contact_label: "L 1-3+", center_freq_hz: 24.5, bandwidth_hz: 5,
  hemisphere: "Left" };
const BC_R = { contact: "ZERO_THREE_RIGHT", contact_label: "R 0-3+", center_freq_hz: 24.5, bandwidth_hz: 5,
  hemisphere: "Right" };
const card = (rep, sum, bc) => rtlRender(wrap(
  <DecisionCard participantUid="uid" bandCandidate={bc} deploymentReport={{ data: rep, loading: false, err: null }}
    summary={{ data: sum, loading: false, err: null }}
    chosenBand={{ band_candidate: bc, committed_at: "2026-09-23T08:00:00.000Z" }}
    bandRecord={{ where: "server", saved: true, chosenBy: "clinician@example.org" }}
    mode={null} onMode={() => {}} />));

const words = (s) => String(s).trim().split(/\s+/).length;

function visibleText(container) {
  const c = container.cloneNode(true);
  c.querySelectorAll(".MuiCollapse-hidden").forEach((n) => n.remove());
  return c.textContent;
}
const bulletsOf = (container, cls) => Array.from(container.querySelectorAll(`.${cls} li [data-bullet]`))
  .map((el) => el.textContent.trim());
const detailsOpen = (container) => {
  const d = container.querySelector(".cl-details .MuiCollapse-root");
  return !!d && !d.classList.contains("MuiCollapse-hidden");
};

describe("the status line is the one verdict", () => {
  it("left: the device allows it and the evidence supports it, provisionally", () => {
    const s = decisionStatus(LEFT);
    expect(s.key).toBe("supported_provisional");
    const { container } = card(LEFT, SUM_L, BC_L);
    expect(visibleText(container)).toMatch(/Device allows it; evidence supports it \(provisional\)/);
  });
  it("right: the device refuses it", () => {
    expect(decisionStatus(RIGHT).key).toBe("refused");
    const { container } = card(RIGHT, SUM_R, BC_R);
    expect(visibleText(container)).toMatch(/Device refuses this configuration/);
  });
});

describe("red bullets: only when the device refuses, five words or less", () => {
  it("none on the left, where every rule passes", () => {
    expect(deviceBullets(LEFT)).toEqual([]);
    expect(bulletsOf(card(LEFT, SUM_L, BC_L).container, "cl-bullets-red")).toEqual([]);
  });
  it("one per blocking rule on the right, in the rule table's own words", () => {
    const { container } = card(RIGHT, SUM_R, BC_R);
    const red = bulletsOf(container, "cl-bullets-red");
    expect(red).toEqual(["Unmet: signs suit control law", "Unmet: stimulation below artefact limits"]);
    red.forEach((b) => expect(words(b)).toBeLessThanOrEqual(5));
  });
  it("a rule that could not be evaluated reads Unchecked, and still blocks", () => {
    const rep = clone(RIGHT);
    rep.eligibility.unknowns = [{ rule_id: "D04", kind: "value_not_read_off_programmer",
      short_label: "Single neurostimulator implanted", title: "A single neurostimulator is required" }];
    expect(deviceBullets(rep).map((b) => b.text)).toContain("Unchecked: single neurostimulator implanted");
    deviceBullets(rep).forEach((b) => expect(words(b.text)).toBeLessThanOrEqual(5));
  });
  it("a row from an older response with no label still says which rule", () => {
    const rep = clone(RIGHT);
    delete rep.eligibility.failures[0].short_label;
    expect(deviceBullets(rep)[0].text).toBe("Unmet: rule D19");
  });
});

describe("yellow bullets: only for evidence that should have been evaluated and was not", () => {
  it("none on either side today: every check ran, whatever it found", () => {
    expect(unevaluatedBullets(LEFT, SUM_L)).toEqual([]);
    expect(unevaluatedBullets(RIGHT, SUM_R)).toEqual([]);
    expect(bulletsOf(card(LEFT, SUM_L, BC_L).container, "cl-bullets-yellow")).toEqual([]);
  });
  it("an edge with no estimate and a gate that did not run each get one", () => {
    const rep = clone(LEFT);
    rep.evidence_not_evaluated = [{ key: "E2", label: "Band power tracks pain", card: "x", why: "y" }];
    const sum = clone(SUM_L);
    const fwd = sum.gates.find((g) => g.key === "forward_validated");
    fwd.state = "indeterminate"; fwd.evaluated = false;
    const got = unevaluatedBullets(rep, sum).map((b) => b.text);
    expect(got).toEqual(["Untested: band power tracks pain", "Untested: holds on later weeks"]);
    got.forEach((b) => expect(words(b)).toBeLessThanOrEqual(5));
  });
  it("an unsettled answer is not an absence: indeterminate but evaluated gives no bullet", () => {
    const sum = clone(SUM_L);
    expect(sum.gates.find((g) => g.key === "stim_stable").state).toBe("indeterminate");
    expect(unevaluatedBullets(LEFT, sum)).toEqual([]);
  });
  it("yellow bullets are drawn in their own list, with a word as well as a colour", () => {
    const rep = clone(LEFT);
    rep.evidence_not_evaluated = [{ key: "coherence", label: "Sign agreement", card: "x", why: "y" }];
    const { container } = card(rep, SUM_L, BC_L);
    expect(bulletsOf(container, "cl-bullets-yellow")).toEqual(["Untested: sign agreement"]);
  });
});

describe("the Details fold: closed by default whatever the verdict (the PI, 2026-10-08)", () => {
  it("closed on the left, where the device allows it", () => {
    expect(detailsOpen(card(LEFT, SUM_L, BC_L).container)).toBe(false);
  });
  it("closed on the right, where the device refuses", () => {
    expect(detailsOpen(card(RIGHT, SUM_R, BC_R).container)).toBe(false);
  });
  it("closed when the device allows it but the evidence is not established", () => {
    const rep = clone(LEFT);
    rep.coherence.coherent = null;
    expect(decisionStatus(rep).key).toBe("unestablished");
    expect(detailsOpen(card(rep, SUM_L, BC_L).container)).toBe(false);
  });
});

describe("the values to enter", () => {
  it("are on the left's card with what the device is programmed at today beside them", () => {
    const { container } = card(LEFT, SUM_L, BC_L);
    const t = visibleText(container);
    expect(t).toMatch(/Upper LFP threshold/);
    expect(t).toMatch(/120\.1250/);
    expect(t).toMatch(/programmed today/i);
    expect(t).toMatch(/121/);
    expect(container.querySelector(".cl-prescription-authorised")).toBeTruthy();
  });
  it("are withheld on the right: no value is printed", () => {
    const { container } = card(RIGHT, SUM_R, BC_R);
    expect(container.textContent).not.toMatch(/130\.2500/);
    expect(container.textContent).not.toMatch(/70\.2500/);
    expect(visibleText(container)).toMatch(/16 values withheld/);
    expect(container.querySelector(".cl-prescription-authorised")).toBeNull();
  });
  it("the planning view still opens on the right, marked as planning only", () => {
    const { container } = card(RIGHT, SUM_R, BC_R);
    fireEvent.click(screen.getByText(/Show the values for planning/));
    expect(container.textContent).toMatch(/130\.2500/);
    expect(container.querySelector(".cl-prescription-planning")).toBeTruthy();
    expect(container.textContent).toMatch(/PLANNING ONLY/);
  });
});

describe("what the card no longer repeats", () => {
  it("prints no E1/E2/E3 lines and no sign-agreement track: those live on the evidence card", () => {
    const t = visibleText(card(LEFT, SUM_L, BC_L).container);
    expect(t).not.toMatch(/\bE[123] sign/);
    expect(t).not.toMatch(/SIGN AGREEMENT/i);
    expect(t).not.toMatch(/INTERVALS SPAN ZERO/);
  });
  it("no sentence of the status line is repeated in the open part of the card", () => {
    const t = visibleText(card(RIGHT, SUM_R, BC_R).container);
    expect((t.match(/Device refuses this configuration/g) || []).length).toBe(1);
  });
  it("the left card's first screen is short", () => {
    const t = visibleText(card(LEFT, SUM_L, BC_L).container);
    // the whole open card, table included; the old header, table and sheet together were 3,077
    expect(words(t)).toBeLessThan(700);
  });
});

describe("Sign and print still carries the whole record", () => {
  it("offers Sign and print and Export", () => {
    card(LEFT, SUM_L, BC_L);
    expect(screen.getByText("Sign and print")).toBeInTheDocument();
    expect(screen.getByText("Export JSON")).toBeInTheDocument();
  });
  it("the record is in the card, folded on screen: the band, the pain score, the ratings", () => {
    const { container } = card(LEFT, SUM_L, BC_L);
    const t = container.textContent;
    // Sentence case since the redesign of 2026-09-26; "gates" reads "checks ... (each one can refuse)".
    expect(t).toMatch(/The band signed for/);
    expect(t).toMatch(/Pain score used/);
    expect(t).toMatch(/Pain ratings used/);
    expect(t).toMatch(/Checks before deployment \(each one can refuse\)/);
    expect(t).toMatch(/Caveats/);
  });
  it("the print stylesheet opts the card in, opens its folds and still drops the planning view", () => {
    const css = fs.readFileSync(path.join(__dirname, "deployPrint.css"), "utf8");
    expect(css).toMatch(/\.cl-decision-card \*/);
    expect(css).toMatch(/\.cl-decision-card \.MuiCollapse-root[\s\S]*height: auto !important/);
    expect(css).toMatch(/\.cl-prescription-planning \{\s*display: none !important/);
    expect(css).not.toMatch(/\.cl-signoff-card \*/);
  });
  it("on the right the record says it authorises nothing", () => {
    expect(visibleText(card(RIGHT, SUM_R, BC_R).container)).toMatch(/This record authorises nothing/);
  });
});

describe("one band on the whole page (the live bug of 2026-09-26)", () => {
  // Seen on the served page: the header named L 1-3+ at 24.5 Hz while the report under it -- a
  // result kept in the page's cache from an earlier band and returned, marked stale, when the band
  // changed -- was L 0-2+ at 23.5 Hz: "D52 is violated ... sensing on 0-2". The chosen band (the
  // server's record, decision 249) is the one the page is about; a report computed for another band
  // is withheld and named, never shown under the chosen band's name.
  // eslint-disable-next-line global-require
  const { reportIsForBand, withheldIfOtherBand } = require("./candidateRequestParams");
  const OTHER = (() => { const r = clone(LEFT); r.candidates = [{ ...r.candidates[0], channel: "ZERO_TWO_LEFT", center_hz: 23.5 }]; return r; })();

  it("knows which band a report was computed for", () => {
    expect(reportIsForBand(LEFT, BC_L)).toBe(true);
    expect(reportIsForBand(OTHER, BC_L)).toBe(false);
    expect(reportIsForBand(RIGHT, BC_L)).toBe(false);
    expect(reportIsForBand(null, BC_L)).toBe(true);        // nothing to contradict yet
  });

  it("withholds a report computed for another band, naming both bands", () => {
    const shown = withheldIfOtherBand({ data: OTHER, loading: false, err: null, stale: true }, BC_L);
    expect(shown.data).toBeNull();
    expect(shown.bandMismatch.chosen).toMatch(/L 1-3\+ at 24\.5 Hz/);
    expect(shown.bandMismatch.computedFor).toMatch(/ZERO_TWO_LEFT at 23\.5 Hz/);
    const same = { data: LEFT, loading: false, err: null };
    expect(withheldIfOtherBand(same, BC_L)).toBe(same);
  });

  it("the decision card says so and shows no verdict, no bullets and no values", () => {
    const shown = withheldIfOtherBand({ data: OTHER, loading: false, err: null, stale: true }, BC_L);
    const { container } = rtlRender(wrap(
      <DecisionCard participantUid="uid" bandCandidate={BC_L} deploymentReport={shown}
        summary={{ data: SUM_L, loading: false, err: null }} mode={null} onMode={() => {}}
        onRecompute={() => {}} />));
    const t = visibleText(container);
    expect(t).toMatch(/Recompute/);
    expect(t).toMatch(/ZERO_TWO_LEFT at 23\.5 Hz/);
    expect(t).toMatch(/L 1-3\+ at 24\.5 Hz/);
    expect(t).not.toMatch(/Device allows it|Device refuses/);
    expect(container.textContent).not.toMatch(/120\.1250/);
    expect(bulletsOf(container, "cl-bullets-red")).toEqual([]);
  });

  it("a summary computed for another band is withheld the same way", () => {
    const sum = clone(SUM_L); sum.identity.contact = "ZERO_TWO_LEFT";
    expect(withheldIfOtherBand({ data: sum }, BC_L, "summary").data).toBeNull();
    expect(withheldIfOtherBand({ data: SUM_L }, BC_L, "summary").data).toBe(SUM_L);
  });
});

describe("the headline never reads better than the server's own verdict (decision 242: one verdict)", () => {
  // The server's verdict is `licensed` / `verdict`; it is false / "unsupported" whenever the analysis
  // appended a reason of its own (`verdict_detail.blockers`: a step that raised, a capture current
  // above the module limit, a control authority that could not be estimated), even when every device
  // rule passes and the three signs agree. The card read only the device rules and the signs, so such
  // a report printed "Device allows it; evidence supports it" with the Details fold closed.
  // eslint-disable-next-line global-require
  const PAL = require("./palette").default;
  const blockedForAnotherReason = () => {
    const rep = clone(LEFT);
    rep.licensed = false;
    rep.verdict = "unsupported";
    rep.verdict_detail.provisional = false;
    rep.verdict_detail.blockers = ["replay failed: ValueError: no samples in the replay window"];
    return rep;
  };

  it("a non-device blocker makes the headline 'not supported', never 'evidence supports it'", () => {
    const rep = blockedForAnotherReason();
    const s = decisionStatus(rep);
    expect(s.key).toBe("unsupported");
    expect(s.headline).not.toMatch(/supports it/);
    const { container } = card(rep, SUM_L, BC_L);
    const t = visibleText(container);
    expect(t).not.toMatch(/Device allows it; evidence supports it/);
    expect(t).toMatch(/Device allows it; the analysis does not support it/);
  });

  it("the blocker's own sentence is in the open while the Details fold stays closed", () => {
    const { container } = card(blockedForAnotherReason(), SUM_L, BC_L);
    expect(detailsOpen(container)).toBe(false);
    expect(visibleText(container)).toMatch(/replay failed: ValueError: no samples in the replay window/);
  });

  it("the server saying not licensed is enough, even with no blocker sentence", () => {
    const rep = clone(LEFT);
    rep.licensed = false;
    rep.verdict = "unsupported";
    expect(decisionStatus(rep).key).toBe("unsupported");
  });

  it("a blocker sentence alone is enough, for a response that predates the licensed field", () => {
    const rep = blockedForAnotherReason();
    delete rep.licensed;
    delete rep.verdict;
    expect(decisionStatus(rep).key).toBe("unsupported");
  });

  it("the non-device blocker is not drawn as a device refusal: no red, no red bar", () => {
    const s = decisionStatus(blockedForAnotherReason());
    expect(s.ink).not.toBe(PAL.failText);
    expect(bulletsOf(card(blockedForAnotherReason(), SUM_L, BC_L).container, "cl-bullets-red")).toEqual([]);
  });

  it("a device refusal keeps its red ✕ wording whatever else blocks", () => {
    const rep = clone(RIGHT);
    rep.verdict_detail.blockers = ["replay failed: ValueError"];
    const s = decisionStatus(rep);
    expect(s.key).toBe("refused");
    expect(s.ink).toBe(PAL.failText);
    expect(s.glyph).toBe("✕");
  });

  it("the synthetic allowed-left response, still reads supported (provisional)", () => {
    expect(LEFT.licensed).toBe(true);
    expect(decisionStatus(LEFT).key).toBe("supported_provisional");
  });
});


describe("from DecisionCard.ceiling", () => {
  const NOTE = "Capped at the 3.0 mA safe ceiling; the highest current measured was 3.5 mA.";
  const UPPER = "Adaptive amplitude limit, upper";

  const BC_L = { contact: "ONE_THREE_LEFT", contact_label: "L 1-3+", center_freq_hz: 24.5, bandwidth_hz: 5,
    hemisphere: "Left" };

  
  function capped() {
    const rep = JSON.parse(JSON.stringify(LEFT));
    const fix = (rows) => (rows || []).forEach((r) => {
      if (r.parameter === UPPER) { r.value = 3.0; r.ceiling_note = NOTE; }
    });
    Object.values(rep.prescriptions.modes).forEach((m) => fix(m.fields));
    if (rep.prescription) fix(rep.prescription.fields);
    return rep;
  }

  const card = (rep) => rtlRender(wrap(
    <DecisionCard participantUid="uid" bandCandidate={BC_L} deploymentReport={{ data: rep, loading: false, err: null }}
      summary={{ data: SUM_L, loading: false, err: null }}
      chosenBand={{ band_candidate: BC_L, committed_at: "2026-09-23T08:00:00.000Z" }}
      bandRecord={{ where: "server", saved: true, chosenBy: "clinician@example.org" }}
      mode={null} onMode={() => {}} />));

  
  function visibleText(container) {
    const c = container.cloneNode(true);
    c.querySelectorAll(".MuiCollapse-hidden").forEach((n) => n.remove());
    return c.textContent;
  }

  describe("the capped upper limit on the decision card", () => {
    it("shows 3.00 mA and the one-sentence reason in the open, on that row", () => {
      const { container } = card(capped());
      const text = visibleText(container);
      expect(text).toContain(NOTE);
      expect(text).not.toMatch(/3\.50/);
      const row = screen.getByText(UPPER).closest("[data-param-row]");
      expect(row).not.toBeNull();
      expect(row.textContent).toContain("3.00");
      expect(row.textContent).toContain(NOTE);
    });

    it("keeps the read-back box working on the capped value", () => {
      card(capped());
      const box = screen.getByLabelText(`The programmer now displays ${UPPER} as 3.00 mA`);
      expect(box).not.toBeDisabled();
      fireEvent.click(box);
      expect(box).toBeChecked();
    });

    it("says nothing about a ceiling on a row the ceiling did not touch", () => {
      const { container } = card(capped());
      const lower = screen.getByText("Adaptive amplitude limit, lower").closest("[data-param-row]");
      expect(lower.textContent).not.toMatch(/ceiling/i);
      // and the uncapped synthetic response carries no such sentence anywhere in the open
      const { container: c2 } = card(LEFT);
      expect(visibleText(c2)).not.toMatch(/Capped at the/);
      expect(container).toBeTruthy();
    });
  });

  describe("the CL-DBS simulation names the limits it ran between", () => {
    it("says the range was capped when the server capped it", () => {
      expect(limitsSourceWords({ amp_limit_note: NOTE }))
        .toBe("the capture range, capped at the safe ceiling");
    });
    it("keeps the old words for a range the ceiling did not touch", () => {
      expect(limitsSourceWords({})).toBe("the capture range, held");
      expect(limitsSourceWords({ amp_limit_note: null })).toBe("the capture range, held");
    });
  });
});


describe("from DecisionCard.painScoreGuard", () => {
  const BC_L = { contact: "ONE_THREE_LEFT", contact_label: "L 1-3+", center_freq_hz: 24.5, bandwidth_hz: 5,
    hemisphere: "Left" };
  function visibleText(container) {
    const c = container.cloneNode(true);
    c.querySelectorAll(".MuiCollapse-hidden").forEach((n) => n.remove());
    return c.textContent;
  }

  
  const LLVAS = (() => {
    const r = clone(LEFT);
    r.pain_score = { key: "left_leg_vas", label: "Left Leg VAS", requested: "left_leg_vas",
      fell_back_to_nrs: false, reason: null };
    return r;
  })();

  describe("a report computed on another pain score is withheld", () => {
    it("withholds it and names both scores", () => {
      const shown = withheldIfOtherBand({ data: LLVAS, loading: false, err: null, stale: true }, BC_L,
        "report", { painScore: "nrs" });
      expect(shown.data).toBeNull();
      expect(shown.bandMismatch).toEqual({ what: "pain score", chosen: "NRS (0–10)",
        computedFor: "Left Leg VAS" });
      expect(shown.err).toMatch(/Left Leg VAS/);
    });

    it("passes a report on the chosen score through untouched", () => {
      const same = { data: LLVAS, loading: false, err: null };
      expect(withheldIfOtherBand(same, BC_L, "report", { painScore: "left_leg_vas" })).toBe(same);
      // and a caller that names no pain score gets the band check alone, as before
      expect(withheldIfOtherBand(same, BC_L)).toBe(same);
    });

    it("names the band first when both the band and the score differ", () => {
      const other = clone(LLVAS);
      other.candidates = [{ ...other.candidates[0], channel: "ZERO_TWO_LEFT", center_hz: 23.5 }];
      const shown = withheldIfOtherBand({ data: other }, BC_L, "report", { painScore: "nrs" });
      expect(shown.bandMismatch.what).toBe("band");
      expect(shown.bandMismatch.computedFor).toMatch(/ZERO_TWO_LEFT at 23\.5 Hz/);
    });
  });

  describe("a summary computed on another pain score or clinic-sheet setting is withheld", () => {
    it("withholds a summary on another score", () => {
      expect(withheldIfOtherBand({ data: SUM_L }, BC_L, "summary",
        { painScore: "left_leg_vas", includeSheets: false }).data).toBeNull();
      expect(withheldIfOtherBand({ data: SUM_L }, BC_L, "summary",
        { painScore: "nrs", includeSheets: false }).data).toBe(SUM_L);
    });

    it("withholds a summary built with the clinic-sheet switch the other way", () => {
      const shown = withheldIfOtherBand({ data: SUM_L }, BC_L, "summary",
        { painScore: "nrs", includeSheets: true });
      expect(shown.data).toBeNull();
      expect(shown.bandMismatch).toEqual({ what: "clinic-sheet setting",
        chosen: "clinic-sheet ratings included", computedFor: "REDCap ratings only" });
    });
  });

  describe("the decision card says so and shows nothing computed on the old score", () => {
    it("names the score it was computed on, the chosen one, and offers Recompute", () => {
      const shown = withheldIfOtherBand({ data: LLVAS, loading: false, err: null, stale: true }, BC_L,
        "report", { painScore: "nrs" });
      const { container } = rtlRender(wrap(
        <DecisionCard participantUid="uid" bandCandidate={BC_L} deploymentReport={shown}
          summary={{ data: SUM_L, loading: false, err: null }} mode={null} onMode={() => {}}
          onRecompute={() => {}} />));
      const t = visibleText(container);
      expect(t).toMatch(/Recompute: the analysis shown is for Left Leg VAS/);
      expect(t).toMatch(/The chosen pain score is NRS \(0–10\)/);
      expect(t).toMatch(/Recompute for NRS \(0–10\)/);
      expect(t).not.toMatch(/Device allows it|Device refuses/);
      expect(t).not.toMatch(/Values withheld|Adaptive amplitude limit/);
    });
  });

  describe("the page hands the guard its current pain score and clinic-sheet switch", () => {
    it("both calls in the page file pass them", () => {
      const src = fs.readFileSync(path.join(__dirname, "index.js"), "utf8");
      // since decision 331 each also hands the matching settings inherited from the Biomarkers page
      expect(src).toMatch(/withheldIfOtherBand\(deploymentReport, bc, "report",\s*\{ painScore, matching: reportMatching \}\)/);
      expect(src).toMatch(/withheldIfOtherBand\(summary, bc, "summary", \{ painScore, includeSheets,\s*matching: requestParams/);
    });
  });
});

describe("one decision per stimulator, from the sense-to-control wiring (the PI, 2026-10-08)", () => {
  it("names the stimulator and how it is driven", () => {
    expect(stimulatorLine({ stim: "Left", source: "Left", kind: "own" })).toBe("Left stimulator · ipsilateral sensing");
    expect(stimulatorLine({ stim: "Right", source: "Left", kind: "contralateral" }))
      .toBe("Right stimulator · contralateral sensing, from the left band");
    expect(stimulatorLine(null)).toBeNull();
  });
  it("a stimulator with no band on its driving side is said not checked, never allowed", () => {
    const { container } = rtlRender(wrap(<UncheckedStimulatorCard stimulator={{ stim: "Right", source: "Right", kind: "no_band" }} />));
    expect(container.textContent).toMatch(/Not checked: no band chosen on the right/);
    expect(container.textContent).not.toMatch(/allows/);
  });
  it("the device rule check is inside the closed Details, not a panel of its own", () => {
    const { container } = card(RIGHT, SUM_R, BC_R);
    expect(container.textContent).toMatch(/Device rule check, every rule/);
    expect(visibleText(container)).not.toMatch(/Device rule check, every rule/);
    expect(detailsOpen(container)).toBe(false);
    // its refusals are still in the open, as the red bullets
    expect(visibleText(container)).toMatch(/Device refuses this configuration/);
    const page = fs.readFileSync(path.join(__dirname, "index.js"), "utf8");
    expect(page).not.toMatch(/<DeviceRuleLedger/);
  });
});
