/**
 * The taste follow-up in the shared page components (TASTE_AUDIT.md C1, C3, C4, C5, C7, C11 and
 * D13, D14; the PI's rulings of 2026-09-26).
 */
import fs from "fs";
import path from "path";
import { render, screen, fireEvent } from "@testing-library/react";

import { T, LAYOUT, STATE } from "assets/theme/base/tokens";
import PageHead from "views/Reports/paper/PageHead";
import Section from "views/Reports/paper/Section";
import Fold from "views/Reports/paper/Fold";
import StatusList, { STATUS_KEY } from "views/Reports/paper/StatusList";
import JumpRow, { JUMP_ROW_CLASS, JUMP_LINK_CLASS, JUMP_ROW_LINK } from "views/Reports/paper/links";
import useDocumentTitle, { documentTitleFor } from "views/Reports/paper/useDocumentTitle";

const src = (name) => fs.readFileSync(path.join(__dirname, name), "utf8");

describe("C7: the browser tab's title is the page's question", () => {
  function Probe({ title }) {
    useDocumentTitle(title);
    return null;
  }

  test("the hook sets the title and puts the previous one back", () => {
    document.title = "before";
    const { unmount } = render(<Probe title="Which brain signal tracks pain?" />);
    expect(document.title).toBe("Which brain signal tracks pain? - UF BRAVO Platform");
    unmount();
    expect(document.title).toBe("before");
  });

  test("an empty or non-text title leaves the tab alone", () => {
    expect(documentTitleFor("")).toBeNull();
    expect(documentTitleFor(<span>x</span>)).toBeNull();
    document.title = "kept";
    render(<Probe title="" />);
    expect(document.title).toBe("kept");
  });

  test("PageHead sets the tab to its title", () => {
    document.title = "before";
    render(<PageHead title="Which current to try next?" />);
    expect(document.title).toBe("Which current to try next? - UF BRAVO Platform");
  });
});

describe("C5: headings balance, prose is pretty", () => {
  // jsdom drops the text-wrap property it does not know, so the source is read.
  test("PageHead balances its title and status sentence", () => {
    const s = src("PageHead.js");
    expect(s).toContain("<h1 style={{ margin: 0, ...TYPE.title, color: T.ink, ...WRAP.balance }}>");
    expect(s).toContain("...TYPE.answer, color: T.ink, ...WRAP.balance }}>");
  });

  test("Section balances its title and makes its answer and reading pretty", () => {
    const s = src("Section.js");
    expect(s).toContain("...TYPE.title, color: T.ink, ...WRAP.balance }}>");
    expect(s.match(/maxWidth: LAYOUT\.proseMax, \.\.\.WRAP\.pretty/g)).toHaveLength(2);
  });
});

describe("D13: 64 px between sections", () => {
  test("a section leaves 64 px below it", () => {
    const { container } = render(<Section question="A question?" />);
    const section = container.querySelector("[data-paper='section']");
    expect(section.style.marginBottom).toBe(`${LAYOUT.betweenSections}px`);
    expect(LAYOUT.betweenSections).toBe(64);
  });
});

describe("C1 and C4: the fold", () => {
  test("its button leaves the outline alone, so the keyboard focus ring shows", () => {
    render(<Fold label="How this was worked out">words</Fold>);
    const button = screen.getByRole("button");
    expect(button.style.outline).toBe("");
    button.focus();
    expect(document.activeElement).toBe(button);
  });

  test("the arrow turns by a CSS transition, which reduced motion makes instant", () => {
    const { container } = render(<Fold label="Method">words</Fold>);
    const arrow = container.querySelector("[data-paper='fold-arrow']");
    expect(arrow.style.transition).toBe("transform .15s");
    fireEvent.click(screen.getByRole("button"));
    expect(arrow.style.transform).toBe("rotate(90deg)");
    expect(screen.getByText("words").hidden).toBe(false);
  });
});

describe("C3 and C11: jump-link rows", () => {
  test("a jump row is navigation, carries the no-underline class and has no middle dots", () => {
    const { container } = render(<JumpRow items={[
      { href: "#heat-maps", label: "Heat maps" }, { href: "#timeline", label: "Timeline" },
    ]} />);
    const nav = screen.getByRole("navigation", { name: "On this page" });
    expect(nav.className).toBe(JUMP_ROW_CLASS);
    const links = Array.from(container.querySelectorAll("a"));
    expect(links.map((a) => a.textContent)).toEqual(["Heat maps", "Timeline"]);
    links.forEach((a) => {
      expect(a.className).toBe(JUMP_LINK_CLASS);
      expect(a.style.textDecoration).toBe("none");
    });
    expect(container.textContent).not.toContain("·");
    expect(JUMP_ROW_LINK.color).toBe(T.accent);
  });

  test("an empty row draws nothing", () => {
    const { container } = render(<JumpRow items={[]} />);
    expect(container.innerHTML).toBe("");
  });
});

describe("D14: a statistical block is ink with ✕, a device refusal red with ✕", () => {
  const rgb = (hex) => {
    const h = hex.replace("#", "");
    return `rgb(${[0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16)).join(", ")})`;
  };

  test("the two states keep their glyph and differ only in ink", () => {
    const { container } = render(<StatusList items={[
      { state: "blocked", text: "Setting not proven better" },
      { state: "refused", text: "Unmet: sensing pair" },
    ]} />);
    const [blocked, refused] = Array.from(container.querySelectorAll("li"));
    expect(blocked.textContent).toBe("✕Setting not proven better");
    expect(refused.textContent).toBe("✕Unmet: sensing pair");
    expect(blocked.style.color).toBe(rgb(T.ink));
    expect(refused.style.color).toBe(rgb(T.refused));
    expect(STATE.blocked.ink).toBe(T.ink);
  });

  test("the glyph key draws its ✕ in ink, with its words unchanged", () => {
    expect(STATUS_KEY[0]).toEqual({ state: "blocked", text: "blocks" });
    const { container } = render(<StatusList showKey />);
    expect(container.textContent).toContain("✕blocks · ▲needs more data or caution · ○not checked");
    const cross = Array.from(container.querySelectorAll("span[aria-hidden='true']"))
      .find((s) => s.textContent === "✕");
    expect(cross.style.color).toBe(rgb(T.ink));
  });
});
