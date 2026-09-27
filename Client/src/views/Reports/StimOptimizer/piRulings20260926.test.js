/**
 * The PI's requests of 2026-09-26 for the Stim Optimizer page, pinned: the three very long sections
 * (the current map, "Can closed loop start?", the next visit) open and close from their title and
 * start closed, their content still mounted; the clinic sheet leaves an empty cell blank.
 */
import fs from "fs";
import path from "path";
import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";

import Section from "views/Reports/paper/Section";

const read = (f) => fs.readFileSync(path.join(__dirname, f), "utf8");

test("a collapsible section starts closed, keeps its body mounted and opens from its title", () => {
  const { container } = render(
    <Section id="closed-loop" question="Can closed loop start?" answer="No." collapsible>
      <p>the long table</p>
    </Section>);
  const body = container.querySelector("#closed-loop-body");
  expect(body.hidden).toBe(true);
  expect(body.textContent).toContain("the long table");
  expect(container.textContent).toContain("No.");
  const btn = screen.getByRole("button", { name: /Can closed loop start\?/ });
  expect(btn.getAttribute("aria-expanded")).toBe("false");
  fireEvent.click(btn);
  expect(body.hidden).toBe(false);
});

test("a plain section is unchanged: no button, always open", () => {
  const { container } = render(<Section id="decision" question="Q?"><p>x</p></Section>);
  expect(container.querySelector("button")).toBeNull();
  expect(container.querySelector("#decision-body").hidden).toBe(false);
});

test("the three long sections on this page are collapsible", () => {
  expect(read("index.js")).toMatch(/<Section id="closed-loop" question="Can closed loop start\?" collapsible>/);
  expect(read("CurrentMapCard.js")).toMatch(/<Section id="current-map"[^>]*collapsible/);
  expect(read("TitrationSessionCard.js")).toMatch(/<Section id="next-visit"[^>]*collapsible/);
});

test("the clinic sheet leaves an empty cell blank, not 'not given'", () => {
  expect(read("TitrationSessionCard.js")).toMatch(/if \(v === null \|\| v === undefined \|\| v === ""\) return "";/);
});
