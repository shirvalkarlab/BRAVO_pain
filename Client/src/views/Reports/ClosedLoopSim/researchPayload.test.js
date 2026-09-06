import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import { TRACKS, coherenceReading } from "./stateTracks";
import { ciBound, fmtFieldValue, fmtHz, fmtMilliamps, fmtMilliseconds, fmtNum, fmtP,
  fmtPct, fmtPower, parseSignPattern, signPhrase, signWord, unevaluableFor } from "./deployFormat";
import ResearchDeploymentPanels from "./ResearchDeploymentPanels";
import DutyCyclePanel from "./DutyCyclePanel";
import StateTrack from "./StateTrack";

jest.mock("@mui/material", () => ({ Card: ({ children }) => <div>{children}</div>,
  Grid: ({ children }) => <div>{children}</div>, Divider: () => <hr />, Icon: ({ children }) => <span>{children}</span> }));
jest.mock("components/MDBox", () => ({ children }) => <div>{children}</div>);
jest.mock("components/MDTypography", () => ({ children }) => <div>{children}</div>);
jest.mock("components/MDButton", () => ({ children, onClick, disabled }) => <button onClick={onClick} disabled={disabled}>{children}</button>);

const research = {
  available: true, readiness: { ready: false, status: "research_only" }, licensed: false,
  verdict_detail: { device_eligible: true, all_edges_resolved: false },
  eligibility: { eligible: true, checked: 1, failures: [], unknowns: [] },
  edges: { E1: { estimate: null, ci: null, resolved: false, note: "Insufficient epochs" } },
  coherence: { coherent: null }, manifest: { outcome: "left_leg_vas" },
  planning: { available: false, reason: "Current programmer settings and capture limits have not been verified." },
};

test("research-only report keeps all modes visible and planning unavailable even if rule checks pass", () => {
  render(<ResearchDeploymentPanels data={research} />);
  expect(screen.getByText("Closed-loop research review")).toBeTruthy();
  expect(screen.queryByText("AUTHORIZATION REPORTED")).toBeTruthy(); // Unlit state is visible; selection tested below.
  expect(TRACKS.transcription.lit(research)).toBe(1);
  expect(screen.queryAllByRole("checkbox")).toHaveLength(0);
  expect(screen.queryByText(/0.0000  \[/)).toBeNull();
  expect(screen.queryByText(/limit unbounded/)).toBeNull();
  expect(screen.getByText("left_leg_vas")).toBeTruthy();
  for (const name of ["Single Threshold", "Single Threshold Inverse", "Dual Threshold"]) {
    fireEvent.click(screen.getByRole("button", { name }));
    expect(screen.getByText(new RegExp(`Selected mode: ${name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}`))).toBeTruthy();
    expect(screen.getAllByText(/capture limits have not been verified/).length).toBeGreaterThanOrEqual(2);
    expect(screen.queryAllByRole("checkbox")).toHaveLength(0);
  }
  expect(screen.getByText("Titration planning")).toBeTruthy();
});
test("mode-specific missing duty cannot borrow another mode's values", () => {
  render(<DutyCyclePanel mode="single_inverse" report={{ data: { available: true,
    prescriptions: { modes: { single_inverse: { fields: [], duty: null } } },
    prescription: { duty: { below: .2, between: .5, above: .3 } } } }} />);
  expect(screen.getByText(/No duty cycle is computed for Single Threshold Inverse/)).toBeTruthy();
  expect(screen.queryByText("20.0%")).toBeNull();
});
test("missing observed or expected signs cannot establish control-law agreement", () => {
  const expected = { E1: -1, E2: 1, E3: -1 };
  expect(coherenceReading(expected, expected)).toMatchObject({ haveAllSigns: true, haveExpectedSigns: true,
    edgesAgreeInternally: true, matchesControlLaw: true });
  expect(coherenceReading({ E1: 1, E2: -1, E3: -1 }, expected)).toMatchObject({
    edgesAgreeInternally: true, matchesControlLaw: false, mismatchedEdges: ["E1", "E2"] });
  expect(coherenceReading(expected, null).matchesControlLaw).toBe(false);
  expect(coherenceReading(null, expected).haveAllSigns).toBe(false);
  for (const value of [0, null, NaN, Infinity, "1"]) {
    expect(coherenceReading({ ...expected, E1: value }, expected).haveAllSigns).toBe(false);
  }
});
test("every state remains distinct; missing fields are never a pass", () => {
  const fixtures = [null, {}, { available: false }, { available: true }, research,
    { available: true, coherence: {}, verdict_detail: { all_edges_resolved: true } }];
  for (const device of [true, false, null]) for (const resolved of [true, false, null]) for (const coherent of [true, false, null]) {
    fixtures.push({ available: true, licensed: true, readiness: { ready: true },
      verdict_detail: { device_eligible: device, all_edges_resolved: resolved }, coherence: { coherent } });
  }
  for (const track of Object.values(TRACKS)) {
    expect(new Set(fixtures.map(track.lit))).toEqual(new Set(track.cells.map((_, i) => i)));
  }
  const view = render(<StateTrack />); expect(view.container.textContent).toBe("");
  view.rerender(<StateTrack track={{ label: "Evidence", cells: [{ key: "a", label: "Unknown", role: "other" }] }} />);
  expect(screen.getByText("Unknown")).toBeTruthy();
  view.rerender(<StateTrack track={TRACKS.coherence} data={research} dense showBlurb={false} />);
  expect(screen.getByText("NOT ESTABLISHED")).toBeTruthy();
});
test("numeric formatting distinguishes unknowns, zeros, units and unbounded intervals", () => {
  for (const value of [null, undefined, NaN, Infinity, false, ""]) {
    expect(fmtMilliamps(value)).toBeNull(); expect(fmtMilliseconds(value)).toBeNull();
    expect(fmtHz(value)).toBeNull(); expect(fmtPower(value)).toBeNull();
    expect(fmtP(value)).toBe("not reported"); expect(fmtPct(value)).toBe("not reported");
    expect(fmtNum(value)).toBe("not reported");
  }
  expect(fmtMilliamps(1.4)).toBe("1.40"); expect(fmtMilliseconds(150000)).toBe("150\u2009000");
  expect(fmtHz(20)).toBe("20.0"); expect(fmtPower(0)).toBe("0.0000");
  expect(fmtP(.0001)).toBe("1.0e-4"); expect(fmtP(.04)).toBe("0.0400");
  expect(fmtNum(2)).toBe("2.000"); expect(fmtPct(.2)).toBe("20.0%");
  expect(fmtFieldValue(null)).toBeNull(); expect(fmtFieldValue({ value: null })).toBeNull();
  expect(fmtFieldValue({ value: "unchanged" })).toBe("unchanged");
  for (const units of ["mA", "ms", "Hz", "LFP power", "LSB", "other", null]) expect(fmtFieldValue({ value: 1, units })).toBeTruthy();
  expect(fmtFieldValue({ value: true })).toBe("true");
  expect(ciBound(null, 0)).toEqual({ value: null, unbounded: false, unavailable: true });
  expect(ciBound([1], 1).unavailable).toBe(true); expect(ciBound([-1, 1], 0).value).toBe(-1);
  expect(ciBound([-Infinity, Infinity], 1).unbounded).toBe(true);
  expect(ciBound([-Infinity, Infinity], 0).unbounded).toBe(true);
  expect(parseSignPattern(null)).toEqual({ E1: null, E2: null, E3: null });
  expect(parseSignPattern({ E1: -1, E2: 1, E3: -1 })).toEqual({ E1: -1, E2: 1, E3: -1 });
  expect(parseSignPattern("{'E1': -1, 'E2': 1, 'why': 'quoted text'}")).toEqual({ E1: -1, E2: 1, E3: null });
  for (const value of [null, 0, 1, -1]) { expect(signPhrase(value)).toBeTruthy(); expect(signWord(value)).toBeTruthy(); }
  expect(unevaluableFor("failed").actor).toContain("measurement");
  expect(unevaluableFor("unrecognized").actor).toContain("unrecognized"); expect(unevaluableFor(null).actor).toContain("absent");
});
