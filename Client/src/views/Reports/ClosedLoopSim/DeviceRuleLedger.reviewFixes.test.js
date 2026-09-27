/**
 * Three things the device-rule ledger said wrongly or not at all (review findings, 2026-09-26):
 *
 * 1. Every refusal was labelled "Measurement, a property of the recording", including D52 (the
 *    sensing pair must flank the stimulating contacts), which is cleared at the programmer by a
 *    change of contacts. The server now says per rule what clears a refusal (`resolved_by`).
 * 2. A kept rule's `deferral_note` (why its finding was not handed to the rule that owns it) was
 *    never printed.
 * 3. An advisory whose own check raised an error was filed under "unrecognised kind" instead of
 *    being named as a check that raised an error.
 */
import "@testing-library/jest-dom";
import { render, fireEvent } from "@testing-library/react";
import { ThemeProvider } from "@mui/material/styles";

import theme from "assets/theme";
import { PlatformContextProvider } from "context";
import DeviceRuleLedger from "./DeviceRuleLedger";
import WhatWouldChangeThis from "./WhatWouldChangeThis";
import { refusalFor } from "./deployFormat";

const wrap = (ui) => (
  <ThemeProvider theme={theme}>
    <PlatformContextProvider initialStates={{ darkMode: false }}>{ui}</PlatformContextProvider>
  </ThemeProvider>
);
const rule = (id, extra = {}) => ({ rule_id: id, title: `rule ${id}`, page: "p.1", ...extra });
const report = (el) => ({ data: { available: true, eligibility: { checked: 52, summary: "s", ...el } },
  loading: false, err: null });

const D52 = rule("D52", { kind: "failed", resolved_by: "configuration",
  title: "The sensing pair must flank the contacts that stimulate" });
const D16 = rule("D16", { kind: "failed", resolved_by: "recording" });
const D19 = rule("D19", { kind: "failed", resolved_by: "band" });
const D11 = rule("D11", { kind: "failed", resolved_by: "analysis" });

describe("who clears a refusal is the rule's own, not one word for every refusal", () => {
  it("a configuration rule is cleared at the programmer, never by measurement", () => {
    const r = refusalFor(D52);
    expect(r.actor).toMatch(/programmer/);
    expect(r.actor).not.toMatch(/measurement/i);
  });
  it("each of the four answers names a different actor", () => {
    const actors = [D52, D16, D19, D11].map((x) => refusalFor(x).actor);
    expect(new Set(actors).size).toBe(4);
    expect(refusalFor(D16).actor).toMatch(/measurement/);
    expect(refusalFor(D11).actor).toMatch(/analysis/);
  });
  it("a row from a response that predates the field names no actor it cannot know", () => {
    const r = refusalFor(rule("D27", { kind: "failed" }));
    expect(r.actor).not.toMatch(/measurement/i);
    expect(r.actor).toMatch(/not stated/);
  });
  it("the ledger's D52 row reads the configuration actor", () => {
    const { container } = render(wrap(<DeviceRuleLedger report={report({ failures: [D52] })} />));
    expect(container.textContent).toMatch(/Clinician, a change of settings at the programmer/);
    expect(container.textContent).not.toMatch(/Measurement, a property of the recording/);
  });
  it("what-would-change-this says a band refusal is cleared by another band, not by reprogramming", () => {
    const { container } = render(wrap(<WhatWouldChangeThis report={report({ failures: [D19] })} bare />));
    expect(container.textContent).toMatch(/another band or sensing pair/);
    expect(container.textContent).not.toMatch(/Only a change to the configuration clears this/);
  });
  it("a configuration refusal counts as resolvable at the programmer", () => {
    const { container } = render(wrap(<WhatWouldChangeThis report={report({ failures: [D52] })} />));
    expect(container.textContent).toMatch(/1 resolvable at the programmer/);
  });
});

describe("the deferral note on a kept row is printed", () => {
  it("is in the open on the refused row", () => {
    const row = { ...D52, deferral_note: "Its owner D02 could not be evaluated, so this rule keeps its own charge." };
    const { container } = render(wrap(<DeviceRuleLedger report={report({ failures: [row] })} />));
    expect(container.textContent).toMatch(/Its owner D02 could not be evaluated/);
  });
});

describe("an advisory whose check raised an error", () => {
  it("is named as a check that raised an error, not as an unrecognised kind", () => {
    const adv = rule("D09", { kind: "predicate_error", severity: "advisory" });
    const { container, getByText } = render(wrap(<DeviceRuleLedger report={report({ advisories: [adv] })} />));
    fireEvent.click(getByText(/Notes and pinned values/));
    expect(container.textContent).not.toMatch(/unrecognised kind/);
    expect(container.textContent).toMatch(/the check raised an error/);
  });
});
