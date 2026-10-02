/**
 * The band axis keeps its end tick and its edge labels inside the figure (page review 2026-10-02:
 * the "30" tick was missing and "rate ÷2 → 27" / "rate ‹" were cut at the right edge).
 */
import "@testing-library/jest-dom";
import { render } from "@testing-library/react";
import { BandAxis } from "./LadderFigures";

const bands = { centres_hz: [8.5, 12.5, 29.5], avoid_hz: [29.5], n_clear: 2, n_avoid: 1,
  harmonics_hz: { multiple_5: 30, half_rate: 8.2, quarter_rate: 15 } };

test("a label near the right edge is anchored to it, one near the left edge to the left", () => {
  const { container } = render(<BandAxis bands={bands} />);
  const texts = Array.from(container.querySelectorAll("text"));
  const right = texts.find((t) => /rate ×5/.test(t.textContent));
  const left = texts.find((t) => /rate ÷2/.test(t.textContent));
  const mid = texts.find((t) => /rate ÷4/.test(t.textContent));
  expect(right.getAttribute("text-anchor")).toBe("end");
  expect(left.getAttribute("text-anchor")).toBe("start");
  expect(mid.getAttribute("text-anchor")).toBe("middle");
});

test("the 30 Hz tick sits at least 14 px inside the right edge", () => {
  const { container } = render(<BandAxis bands={bands} />);
  const svg = container.querySelector("svg");
  const W = Number(svg.getAttribute("width"));
  const tick = Array.from(container.querySelectorAll("text")).find((t) => t.textContent === "30");
  expect(W - Number(tick.getAttribute("x"))).toBeGreaterThanOrEqual(14);
});
