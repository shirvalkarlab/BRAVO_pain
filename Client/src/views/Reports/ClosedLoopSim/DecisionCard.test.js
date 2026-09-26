/**
 * The one decision card (decision 302; the PI, 2026-09-26): "Combine the full parameter
 * recommendation with the deployment card to create one simple, streamlined card." A status line,
 * red bullets when the device refuses, yellow bullets for evidence that should have been evaluated
 * and was not (five words or less each), the values to enter only when the device allows them,
 * "Sign and print", and one "Details" fold, closed when the configuration is allowed and supported
 * and open otherwise.
 *
 * Rendered against the live RCS08 responses of 2026-09-25 (L 1-3+ and R 0-3+ at 24.5 Hz, NRS):
 * the left is allowed and supported on point signs; the right is refused by D19 and D27.
 */
import fs from "fs";
import path from "path";
import "@testing-library/jest-dom";
import { render as rtlRender, fireEvent, screen } from "@testing-library/react";
import { ThemeProvider } from "@mui/material/styles";

import theme from "assets/theme";
import { PlatformContextProvider } from "context";

jest.mock("plotly.js-dist", () => ({
  react: jest.fn(), purge: jest.fn(), restyle: jest.fn(), relayout: jest.fn(), newPlot: jest.fn(),
  toImage: jest.fn(),
}));
jest.mock("database/session-control", () => ({ SessionController: { query: jest.fn() } }));

// eslint-disable-next-line import/first
import DecisionCard, { deviceBullets, unevaluatedBullets, decisionStatus } from "./DecisionCard";
import LEFT from "./__fixtures__/rcs08_cl_L13_24p5_2026-09-25.json";
import RIGHT from "./__fixtures__/rcs08_cl_R03_24p5_2026-09-25.json";
import SUM_L from "./__fixtures__/rcs08_summary_L13_24p5_2026-09-25.json";
import SUM_R from "./__fixtures__/rcs08_summary_R03_24p5_2026-09-25.json";

const wrap = (ui) => (
  <ThemeProvider theme={theme}>
    <PlatformContextProvider initialStates={{ darkMode: false }}>{ui}</PlatformContextProvider>
  </ThemeProvider>
);
const clone = (o) => JSON.parse(JSON.stringify(o));
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
/** Text a reader can see: everything outside a closed fold. */
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

describe("the Details fold: closed when allowed and supported, open otherwise", () => {
  it("closed on the left", () => {
    expect(detailsOpen(card(LEFT, SUM_L, BC_L).container)).toBe(false);
  });
  it("open on the right, where the device refuses", () => {
    expect(detailsOpen(card(RIGHT, SUM_R, BC_R).container)).toBe(true);
  });
  it("open when the device allows it but the evidence is not established", () => {
    const rep = clone(LEFT);
    rep.coherence.coherent = null;
    expect(decisionStatus(rep).key).toBe("unestablished");
    expect(detailsOpen(card(rep, SUM_L, BC_L).container)).toBe(true);
  });
});

describe("the values to enter", () => {
  it("are on the left's card with what the device is programmed at today beside them", () => {
    const { container } = card(LEFT, SUM_L, BC_L);
    const t = visibleText(container);
    expect(t).toMatch(/Upper LFP threshold/);
    expect(t).toMatch(/241\.1398/);
    expect(t).toMatch(/programmed today/i);
    expect(t).toMatch(/242/);
    expect(container.querySelector(".cl-prescription-authorised")).toBeTruthy();
  });
  it("are withheld on the right: no value is printed", () => {
    const { container } = card(RIGHT, SUM_R, BC_R);
    expect(container.textContent).not.toMatch(/213\.4834/);
    expect(container.textContent).not.toMatch(/75\.2447/);
    expect(visibleText(container)).toMatch(/16 values withheld/);
    expect(container.querySelector(".cl-prescription-authorised")).toBeNull();
  });
  it("the planning view still opens on the right, marked as planning only", () => {
    const { container } = card(RIGHT, SUM_R, BC_R);
    fireEvent.click(screen.getByText(/Show the values for planning/));
    expect(container.textContent).toMatch(/213\.4834/);
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
    expect(t).toMatch(/THE BAND SIGNED FOR/);
    expect(t).toMatch(/Pain score used/);
    expect(t).toMatch(/Pain ratings used/);
    expect(t).toMatch(/DEPLOYMENT GATES/);
    expect(t).toMatch(/CAVEATS/);
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
    expect(container.textContent).not.toMatch(/241\.1398/);
    expect(bulletsOf(container, "cl-bullets-red")).toEqual([]);
  });

  it("a summary computed for another band is withheld the same way", () => {
    const sum = clone(SUM_L); sum.identity.contact = "ZERO_TWO_LEFT";
    expect(withheldIfOtherBand({ data: sum }, BC_L, "summary").data).toBeNull();
    expect(withheldIfOtherBand({ data: SUM_L }, BC_L, "summary").data).toBe(SUM_L);
  });
});
