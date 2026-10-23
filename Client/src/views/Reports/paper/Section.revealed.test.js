/**
 * A collapsible section tells its contents whether it has EVER been opened (speed-up item C5,
 * 2026-10-01). Figures inside a closed section are not drawn until the first opening, then stay
 * drawn when it is closed again. Outside any collapsible section the answer is "yes", so a figure
 * that reads it behaves exactly as before.
 *
 * Merged here 2026-10-05: Section.reclick.test.js. Each merged file's tests sit in a describe
 * block named after it, with its reason above it.
 */

import "@testing-library/jest-dom";
import { useContext } from "react";
import { act, fireEvent, render, screen } from "@testing-library/react";
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

/* From Section.reclick.test.js.
 * A jump link to a collapsible section opens it. The hash change opens it the first time; a second
 * click on the same link, after the reader closed the section again, changes no hash and fires no
 * hash change, so the section also opens on a click of any link to it (2026-09-26).
 */
describe("from Section.reclick", () => {
  function Page() {
    return (
      <>
        <a href="#sec-a">Go to A</a>
        <Section id="sec-a" question="Is A open?" answer="A's answer." collapsible>
          <p>A's body</p>
        </Section>
      </>
    );
  }

  const body = () => document.getElementById("sec-a-body");

  describe("a jump link to a closed section opens it every time", () => {
    afterEach(() => { window.history.replaceState(null, "", "/"); });

    it("opens on the first click, and again on a second click after it was closed", () => {
      render(<Page />);
      expect(body()).not.toBeVisible();
      act(() => {
        window.history.replaceState(null, "", "#sec-a");
        window.dispatchEvent(new HashChangeEvent("hashchange"));
      });
      fireEvent.click(screen.getByText("Go to A"));
      expect(body()).toBeVisible();
      fireEvent.click(screen.getByRole("button", { name: /Is A open\?/ }));
      expect(body()).not.toBeVisible();
      // the hash is already #sec-a: no hash change fires
      fireEvent.click(screen.getByText("Go to A"));
      expect(body()).toBeVisible();
    });

    it("a click on a link to another section leaves this one closed", () => {
      render(<><a href="#elsewhere">Elsewhere</a><Page /></>);
      fireEvent.click(screen.getByText("Elsewhere"));
      expect(body()).not.toBeVisible();
    });
  });
});
