/**
 * The shared page components (SPEC.md sections 3.2 and 4): folded content stays mounted,
 * every status item carries its glyph, the ceiling line prints only the values passed in,
 * and no text is set under 12 px.
 */
import { render, screen, fireEvent } from "@testing-library/react";

import PageHead, { contextLine } from "views/Reports/paper/PageHead";
import Section from "views/Reports/paper/Section";
import StatusList, { MAX_STATUS_ITEMS } from "views/Reports/paper/StatusList";
import CeilingLine, { ceilingSentence } from "views/Reports/paper/CeilingLine";
import Fold from "views/Reports/paper/Fold";
import ColorKey from "views/Reports/paper/ColorKey";

const allFontSizes = (container) => Array.from(container.querySelectorAll("*"))
  .map((el) => el.style.fontSize).filter(Boolean).map((s) => parseFloat(s));

describe("Fold", () => {
  test("its content is mounted while closed and shown when opened", () => {
    render(<Fold label="How this was worked out" inside="three steps">hidden words</Fold>);
    const button = screen.getByRole("button");
    expect(button.textContent).toBe("▸How this was worked out (three steps)");
    expect(button.getAttribute("aria-expanded")).toBe("false");
    const body = screen.getByText("hidden words");
    expect(body.hidden).toBe(true);
    fireEvent.click(button);
    expect(button.getAttribute("aria-expanded")).toBe("true");
    expect(screen.getByText("hidden words").hidden).toBe(false);
  });
});

describe("StatusList", () => {
  test("each item carries the glyph of its state", () => {
    const { container } = render(<StatusList items={[
      { state: "refused", text: "No usable sensing pair" },
      { state: "caution", text: "Next visit: 4 pairs short" },
      { state: "notChecked", text: "Rule not checked" },
      { state: "pass", text: "Rate allowed" },
    ]} />);
    const items = Array.from(container.querySelectorAll("li")).map((li) => li.textContent);
    expect(items).toEqual(["✕No usable sensing pair", "▲Next visit: 4 pairs short",
      "○Rule not checked", "✓Rate allowed"]);
  });

  test("it shows at most five items and prints the glyph key when asked", () => {
    const many = Array.from({ length: 7 }, (_, i) => ({ state: "caution", text: `item ${i}` }));
    const { container } = render(<StatusList items={many} showKey />);
    expect(container.querySelectorAll("li").length).toBe(MAX_STATUS_ITEMS);
    expect(container.textContent).toContain("✕blocks · ▲needs more data or caution · ○not checked");
  });
});

describe("CeilingLine", () => {
  test("it prints the ceiling read from the server, word for word", () => {
    const { container } = render(<CeilingLine leftMa={4.5} rightMa={4.5} />);
    expect(container.textContent).toBe("Safe current ceiling: 4.5 mA left, 4.5 mA right "
      + "(set by the PI). Nothing above it is offered on this page.");
  });

  test("it never types a current the server did not send", () => {
    expect(ceilingSentence(null, null)).not.toMatch(/\d/);
    expect(ceilingSentence(4.5, null)).toContain("right not received");
  });
});

describe("PageHead and Section", () => {
  test("the head names the participant and pain score and carries the ceiling", () => {
    const { container } = render(
      <PageHead title="Should today's setting change, and can closed loop start?"
        participant="RCS08" painScore="Left Leg VAS"
        status="Keep today's setting on both sides; closed loop cannot start."
        items={[{ state: "refused", text: "No usable sensing pair" }]}
        ceiling={{ leftMa: 4.5, rightMa: 4.5 }} />,
    );
    expect(contextLine("RCS08", "Left Leg VAS")).toBe("RCS08 · pain score Left Leg VAS");
    expect(container.textContent).toContain("RCS08 · pain score Left Leg VAS");
    expect(container.textContent).toContain("Safe current ceiling: 4.5 mA left");
    expect(screen.getByRole("status").textContent)
      .toBe("Keep today's setting on both sides; closed loop cannot start.");
    allFontSizes(container).forEach((px) => expect(px).toBeGreaterThanOrEqual(12));
  });

  test("a section is a question, an answer, a figure and one mounted method fold", () => {
    const { container } = render(
      <Section id="s1" question="Does band power rise or fall with pain?"
        answer="One band rises with pain." method="the method words">
        <div>figure</div>
      </Section>,
    );
    expect(screen.getByRole("heading").textContent).toBe("Does band power rise or fall with pain?");
    expect(container.textContent).toContain("the method words");
    expect(container.querySelectorAll("[data-paper='fold']").length).toBe(1);
    allFontSizes(container).forEach((px) => expect(px).toBeGreaterThanOrEqual(12));
  });
});

describe("ColorKey", () => {
  test("its ends and middle are labelled in words", () => {
    const { container } = render(<ColorKey range={[-0.5, 0.5]} lowLabel="falls with pain"
      midLabel="0" highLabel="rises with pain" />);
    expect(container.textContent).toBe("−0.5 falls with pain0rises with pain 0.5");
    allFontSizes(container).forEach((px) => expect(px).toBeGreaterThanOrEqual(12));
  });
});
