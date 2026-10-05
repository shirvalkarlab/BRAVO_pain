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
 *
 * Merged here 2026-10-05: DeviceRuleLedger.countsSum.test.js. Each merged file's tests sit in a
 * describe block named after it, with its reason above it.
 */

import "@testing-library/jest-dom";
import { fireEvent, render, screen } from "@testing-library/react";
import DeviceRuleLedger from "./DeviceRuleLedger";
import WhatWouldChangeThis from "./WhatWouldChangeThis";
import { refusalFor } from "./deployFormat";
import React from "react";
import { wrap } from "testUtils/render";

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

/* From DeviceRuleLedger.countsSum.test.js.
 * The device-rule ledger's open counts must sum to the total rules checked. Until now "Allowed"
 * silently included rules pinned for their recorded value (`recorded_value`), and every deferred
 * or advisory row lived only inside a closed fold, so Refuses + Could not check + Allowed read
 * less than the server's own `checked` total whenever any such row existed -- the counts a
 * clinician sees in the open did not add up (the PI, 2026-09-26).
 */
describe("from DeviceRuleLedger.countsSum", () => {
  const rule = (id, extra = {}) => ({ rule_id: id, title: "a rule", page: "p.1", ...extra });

  // 10 rules checked: 1 refused, 1 could-not-check, 1 deferred, 1 failed advisory, 1 pinned
  // (recorded_value), 1 no-predicate advisory, 1 not-determinable advisory -- 7 reported, so 3 pass
  // with nothing to report (satisfied). 1(refuse) + 1(could not check) + 3(allowed) + 1(pinned) +
  // 4(notes: deferred + failed + no-predicate + not-determinable) = 10 = checked.
  const eligibility = {
    checked: 10,
    summary: "a fixture",
    failures: [rule("F1", { kind: "device_range" })],
    unknowns: [rule("U1", { kind: "advisory_not_determinable" })],
    deferred: [rule("D1", { deferred_to: "F1" })],
    advisories: [
      rule("A1", { kind: "advisory_failed" }),
      rule("A2", { kind: "recorded_value" }),
      rule("A3", { kind: "advisory_no_predicate" }),
      rule("A4", { kind: "advisory_not_determinable" }),
    ],
  };

  test("the open counts (Refuses, Could not check, Allowed, Passed with value shown, Notes) sum to the total checked", () => {
    render(wrap(<DeviceRuleLedger report={{ data: { eligibility }, loading: false, err: null }} />));
    const line = screen.getByTestId("rule-counts").textContent;
    const nums = [...line.matchAll(/\((\d+)\)/g)].map((m) => Number(m[1]));
    // five categories, each a number in parentheses, before "of 10 rules"
    expect(nums.length).toBe(5);
    expect(nums.reduce((s, n) => s + n, 0)).toBe(10);
    expect(line).toMatch(/of 10 rules checked/);
  });

  test("Allowed means only rules that were satisfied; rules passed with their value shown get their own count", () => {
    render(wrap(<DeviceRuleLedger report={{ data: { eligibility }, loading: false, err: null }} />));
    const line = screen.getByTestId("rule-counts").textContent;
    expect(line).toMatch(/Allowed \(3\)/);
    expect(line).toMatch(/Passed, value shown \(1\)/);
    expect(line).toMatch(/Notes, not blocking \(4\)/);
    expect(line).toMatch(/Refuses \(1\)/);
    expect(line).toMatch(/Could not check \(1\)/);
  });
});
