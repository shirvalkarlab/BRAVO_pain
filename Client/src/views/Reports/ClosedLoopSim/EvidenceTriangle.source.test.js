/**
 * Review 2026-09-15, finding C1. On the committed band E1 is the screening statistic (its note
 * begins "SCREENING STATISTIC ONLY") and was drawn exactly like a measured edge. The payload now
 * carries `edges.E1.source`; the triangle must draw a screening E1 differently and say the word.
 */
import "@testing-library/jest-dom";
import { render as rtlRender } from "@testing-library/react";
import { ThemeProvider } from "@mui/material/styles";

import theme from "assets/theme";
import { PlatformContextProvider } from "context";

import EvidenceTrianglePanel from "./EvidenceTrianglePanel";
import payload from "./__fixtures__/rcs08_deployment_payload.json";

const wrap = (ui) => (
  <ThemeProvider theme={theme}>
    <PlatformContextProvider initialStates={{ darkMode: false }}>{ui}</PlatformContextProvider>
  </ThemeProvider>
);
const withSource = (source) => {
  const d = JSON.parse(JSON.stringify(payload));
  d.edges.E1.source = source;
  return { data: d, loading: false, err: null };
};

test("a screening E1 is drawn dotted and labelled 'screening'", () => {
  const { container } = rtlRender(wrap(<EvidenceTrianglePanel report={withSource("screening_historical")} />));
  const line = container.querySelector('line[data-edge="E1"]');
  expect(line).not.toBeNull();
  expect(line.getAttribute("stroke-dasharray")).toBe("1.5 3.5");
  expect(container.textContent).toMatch(/screening/i);
});

test("a pooled-titration E1 keeps the solid measured-edge stroke and carries no screening label", () => {
  const { container } = rtlRender(wrap(<EvidenceTrianglePanel report={withSource("pooled_titration")} />));
  const line = container.querySelector('line[data-edge="E1"]');
  expect(line.getAttribute("stroke-dasharray")).toBeNull();
  // the legend may explain the convention; the LABEL must not be on this edge
  expect(container.textContent).not.toMatch(/screening statistic, not a measurement/i);
});
