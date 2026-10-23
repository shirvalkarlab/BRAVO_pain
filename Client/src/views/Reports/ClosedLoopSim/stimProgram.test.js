/**
 * The stimulation program card (decision 467): the rules, the same sentences as the server's
 * `stim_program.py`, and the card's clicks.
 */
import "@testing-library/jest-dom";
import fs from "fs";
import path from "path";
import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import { wrap } from "testUtils/render";
import {
  blockingProblems, contactsText, sensingPair, nextSign, requestProgram, isEdited, fromServer, shownContact,
} from "./stimProgram";
import StimProgramCard from "./StimProgramCard";
import { deploymentReportBody } from "./useDeploymentReport";

const RCS08 = {
  available: true, rate_hz: 55, session_date: "2026-09-30T18:21:10Z",
  Left: { contacts: { "2a": -1, "2b": -1, "2c": -1, case: 1 }, amp_mA: 3, pw_us: 100,
    lower_limit_mA: 1.4, upper_limit_mA: 4, target: "Left GPe" },
  Right: { contacts: { "1a": -1, "1b": -1, "1c": -1, "2a": -1, "2b": -1, "2c": -1, case: 1 }, amp_mA: 2.5,
    pw_us: 150, lower_limit_mA: 1.2, upper_limit_mA: 3, target: "Right MD Thal" },
};

test("the flanking rule (D52) on RCS08's program today", () => {
  const p = fromServer(RCS08);
  expect(blockingProblems(p.Left, [0, 3])).toEqual(["Sensing on 0-3 needs stimulation on 1 and 2: the device cannot sense"]);
  expect(blockingProblems(p.Left, [1, 3])).toEqual([]);
  expect(blockingProblems(p.Right, [0, 3], "Right")).toEqual([]);
  expect(blockingProblems(p.Right, [1, 3], "Right")).toEqual(["Sensing on 9-11 needs stimulation on 10: the device cannot sense"]);
});

test("each blocking problem is said, and nothing when it passes", () => {
  expect(blockingProblems({ contacts: { case: 1 } })).toEqual(["No negative contact: no stimulation on this side"]);
  expect(blockingProblems({ contacts: { "2a": -1 } })).toEqual(["No positive contact: make the case or a contact positive"]);
  expect(blockingProblems({ contacts: { 3: -1, case: 1 } }, [0, 3]))
    .toEqual(["Sensing on 0-3 needs stimulation on 1 and 2: the device cannot sense"]);
  expect(blockingProblems({ contacts: { "2a": -1, case: 1 }, amp_mA: 5, lower_limit_mA: 1, upper_limit_mA: 4 }))
    .toEqual(["Amp is outside the lowest and highest current"]);
});

test("the page's sentences are the server's, word for word", () => {
  const py = fs.readFileSync(path.join(__dirname, "..", "..", "..", "..", "..", "BRAVO", "modules",
    "ClosedLoopDeployment", "stim_program.py"), "utf8");
  ["No negative contact: no stimulation on this side",
    "No positive contact: make the case or a contact positive",
    "Lowest current is above the highest", "Amp is outside the lowest and highest current",
    "needs stimulation on", ": the device cannot sense", "No stimulating contact lets the device sense on"].forEach((t) => expect(py).toContain(t));
});

test("helpers: sensing pair, programmer text, right-lead labels, the click cycle", () => {
  expect(sensingPair("ZERO_THREE_LEFT")).toEqual({ side: "Left", pair: [0, 3] });
  expect(sensingPair("ONE_THREE_RIGHT")).toEqual({ side: "Right", pair: [1, 3] });
  expect(contactsText("Right", { "2a": -1, "1b": -1, case: 1 })).toBe("C+ 9b− 10a−");
  expect(shownContact("Right", "0")).toBe("8");
  expect([nextSign(0), nextSign(-1), nextSign(1)]).toEqual([-1, 1, 0]);
});

test("only an edited program is sent, and it leaves the request untouched otherwise", () => {
  const inh = fromServer(RCS08);
  const same = { ...inh, Left: { ...inh.Left, contacts: { case: 1, "2c": -1, "2b": -1, "2a": -1 } } };
  expect(isEdited(same, inh)).toBe(false);
  expect(isEdited({ ...inh, rate_hz: 60 }, inh)).toBe(true);
  const band = { channel: "ZERO_THREE_LEFT", centerHz: 25.5 };
  expect(deploymentReportBody({ participantUid: "u", bandCandidate: band })).not.toHaveProperty("StimProgram");
  const body = deploymentReportBody({ participantUid: "u", bandCandidate: band, stimProgram: requestProgram({ ...inh, rate_hz: 60 }) });
  expect(body.StimProgram.rate_hz).toBe(60);
  expect(body.StimProgram.Left).not.toHaveProperty("target");
});

function Harness({ start }) {
  const [p, setP] = React.useState(start);
  return <StimProgramCard program={p} onChange={setP} onInherit={() => setP(fromServer(RCS08))}
    inheritedFrom="2026-09-30" edited={false} sensing={{ side: "Left", pair: [1, 3] }} />;
}

test("the card: targets, a click cycles a contact and shows its sign, a block is said in red", () => {
  render(wrap(<Harness start={fromServer(RCS08)} />));
  expect(screen.getByTestId("stim-target-Left")).toHaveTextContent("Left GPe");
  expect(screen.getByTestId("stim-target-Right")).toHaveTextContent("Right MD Thal");
  expect(screen.getByTestId("stim-text-Left")).toHaveTextContent("C+ 2a− 2b− 2c−");
  expect(screen.queryAllByTestId("stim-problem")).toHaveLength(0);
  const c3 = screen.getByTestId("contact-Left-3");
  fireEvent.click(c3);
  expect(c3).toHaveAttribute("data-sign", "-1");
  expect(screen.getByText(/Sensing on 1-3 needs stimulation on 2: the device cannot sense/)).toBeInTheDocument();
  fireEvent.click(c3); fireEvent.click(c3);
  expect(c3).toHaveAttribute("data-sign", "0");
  expect(screen.queryAllByTestId("stim-problem")).toHaveLength(0);
});

test("the card: Inherit fills an empty program from the device", () => {
  render(wrap(<Harness start={{ rate_hz: null }} />));
  expect(screen.getAllByTestId("stim-problem").length).toBeGreaterThan(0);
  fireEvent.click(screen.getByTestId("inherit-current"));
  expect(screen.getByTestId("rate-box")).toHaveValue(55);
  expect(screen.getByTestId("amp-Right")).toHaveValue(2.5);
  expect(screen.queryAllByTestId("stim-problem")).toHaveLength(0);
});
