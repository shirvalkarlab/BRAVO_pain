/**
 * The device-rule ledger's open counts must sum to the total rules checked. Until now "Allowed"
 * silently included rules pinned for their recorded value (`recorded_value`), and every deferred
 * or advisory row lived only inside a closed fold, so Refuses + Could not check + Allowed read
 * less than the server's own `checked` total whenever any such row existed -- the counts a
 * clinician sees in the open did not add up (the PI, 2026-09-26).
 */
import "@testing-library/jest-dom";
import React from "react";
import { render, screen } from "@testing-library/react";
import { ThemeProvider } from "@mui/material/styles";

import theme from "assets/theme";
import { PlatformContextProvider } from "context";
import DeviceRuleLedger from "./DeviceRuleLedger";

const wrap = (ui) => (
  <ThemeProvider theme={theme}>
    <PlatformContextProvider initialStates={{ darkMode: false }}>{ui}</PlatformContextProvider>
  </ThemeProvider>
);

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
