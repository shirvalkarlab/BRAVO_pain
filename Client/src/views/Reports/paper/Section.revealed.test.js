/**
 * A collapsible section tells its contents whether it has EVER been opened (speed-up item C5,
 * 2026-10-01). Figures inside a closed section are not drawn until the first opening, then stay
 * drawn when it is closed again. Outside any collapsible section the answer is "yes", so a figure
 * that reads it behaves exactly as before.
 */
import "@testing-library/jest-dom";
import { useContext } from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import Section, { SectionRevealedContext } from "./Section";

function Probe() {
  const revealed = useContext(SectionRevealedContext);
  return <span data-testid="probe">{revealed ? "revealed" : "not yet"}</span>;
}

it("a closed collapsible section reports not yet revealed, then revealed for good once opened", () => {
  render(
    <Section id="sec-r" question="Is R open?" answer="R's answer." collapsible>
      <Probe />
    </Section>
  );
  expect(screen.getByTestId("probe")).toHaveTextContent("not yet");
  const toggle = screen.getByRole("button", { name: /Is R open\?/ });
  fireEvent.click(toggle);
  expect(screen.getByTestId("probe")).toHaveTextContent("revealed");
  fireEvent.click(toggle);
  expect(screen.getByTestId("probe")).toHaveTextContent("revealed");
});

it("a section that starts open, and anything outside a section, reports revealed", () => {
  render(
    <>
      <Section id="sec-o" question="Open?" answer="yes" collapsible defaultOpen><Probe /></Section>
      <Probe />
    </>
  );
  screen.getAllByTestId("probe").forEach((el) => expect(el).toHaveTextContent("revealed"));
});

it("the current-map squares skip drawing until their section has been revealed", () => {
  const src = require("fs").readFileSync(
    require("path").join(__dirname, "..", "StimOptimizer", "CurrentMapCard.js"), "utf8");
  expect(src).toMatch(/const revealed = useContext\(SectionRevealedContext\);/);
  expect(src).toMatch(/if \(!revealed \|\| !surface/);
});
