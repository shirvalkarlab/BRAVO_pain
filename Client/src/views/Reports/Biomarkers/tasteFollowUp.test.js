/**
 * The taste audit's follow-up on the Biomarkers page (the PI, 2026-09-26: build C1-C12; the spec
 * wins on D3-D13; D14: red only for a device refusal or a value above the safe ceiling).
 * artifacts/design_2026-09-26_minimalist_redesign/TASTE_AUDIT.md sections C and D.
 *
 *   C2  an empty figure collapses to one sentence saying what would fill it; a grid on its way is
 *       still grey blocks shaped like it, never a spinner, with the waiting words kept;
 *   C6  the page's fold is the shared one (paper/Fold), its sections the shared paper/Section;
 *   C9  no dash stands for an empty value; the page says "not given" or "none";
 *   C12 the Background group's items are plain rows, not cards;
 *   D14 red appears on this page only beside the device's refusal of a sensing pair.
 */
import "@testing-library/jest-dom";
import fs from "fs";
import path from "path";
import { render as rtlRender, screen, fireEvent } from "@testing-library/react";
import { ThemeProvider } from "@mui/material/styles";
import theme from "assets/theme";
import { PlatformContextProvider } from "context";

import TimingHistogram from "./TimingHistogram";
import BinarizationPreview from "./BinarizationPreview";
import GridSkeleton from "./GridSkeleton";
import Fold from "./Fold";

jest.mock("plotly.js-dist", () => {
  const noop = () => {};
  return { react: () => Promise.resolve(), purge: noop, restyle: noop, relayout: noop, newPlot: noop };
});

const wrap = (ui) => (
  <ThemeProvider theme={theme}>
    <PlatformContextProvider initialStates={{ darkMode: false }}>{ui}</PlatformContextProvider>
  </ThemeProvider>
);
const read = (f) => fs.readFileSync(path.join(__dirname, f), "utf8");
const stripComments = (src) => src.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:"'\\])\/\/[^\n]*/g, "$1");

describe("C2: empty figures collapse to one sentence", () => {
  test("the timing histogram with nothing to place takes no height and says what would fill it", () => {
    const { container } = rtlRender(wrap(
      <TimingHistogram scanIndex={[]} painSeries={null} windowMin={60} matchDirection="nearest"
        metricLabel="NRS" />));
    const fig = container.querySelector("[data-testid='timing-histogram']");
    expect(fig).not.toBeNull();                       // still mounted, for Plotly
    expect(fig.getAttribute("data-empty")).toBe("true");
    expect(fig.style.height).toBe("0px");
    expect(container.textContent).toContain("No band-power readings to place against the pain reports yet");
    expect(container.textContent).toMatch(/appears once the recordings and the pain reports have both loaded/);
    expect(container.textContent).not.toContain("outside the window");   // no key for an empty figure
  });

  test("the high / low split with no reports keeps no 440 px of blank space", () => {
    const { container } = rtlRender(wrap(
      <BinarizationPreview points={[]} strategy="tertile" percentileLow={33} percentileHigh={67}
        metricLabel="Left Leg VAS" metricKey="left_leg_vas" totalReports={0} loading={false}
        matchTolerance={60} scanModel={null} matchedLoading={false} matchDirty={false}
        setPercentileLow={() => {}} setPercentileHigh={() => {}} setStrategy={() => {}} />));
    const fig = container.querySelector("[data-testid='split-figure']");
    expect(fig.getAttribute("data-empty")).toBe("true");
    expect(fig.style.height).toBe("0px");
    expect(screen.getByTestId("split-empty").textContent)
      .toBe("The histogram of the high and low pain split appears here once there are Left Leg VAS reports to split.");
    expect(container.querySelector("[role='slider']")).toBeNull();   // no handles over nothing
  });
});

describe("C2: still grey blocks instead of a spinner", () => {
  test("the placeholder keeps the waiting words and draws blocks shaped like the grid, with no motion", () => {
    const { container } = rtlRender(<GridSkeleton words="Computing the calibrated grid…" />);
    expect(screen.getByRole("status").textContent).toContain("Computing the calibrated grid…");
    const blocks = container.querySelector("[data-skeleton='blocks']");
    expect(blocks.getAttribute("aria-hidden")).toBe("true");
    // six pair thumbnails at 120 x 60 and two maps
    const thumbs = Array.from(blocks.querySelectorAll("div")).filter((d) => d.style.width === "120px");
    expect(thumbs).toHaveLength(6);
    container.querySelectorAll("*").forEach((el) => {
      expect(el.style.animation || "").toBe("");
      expect(el.style.transition || "").toBe("");
    });
  });

  test("the heat maps and the older sweep panel draw no spinner", () => {
    ["BiomarkerHeatmapGrids.js", "BandTimeSweepPanel.js"].forEach((f) => {
      const src = stripComments(read(f));
      expect(src).not.toMatch(/CircularProgress/);
      expect(src).toMatch(/<GridSkeleton /);
    });
    // the waiting words are kept word for word
    expect(read("BiomarkerHeatmapGrids.js")).toContain("\"Computing the calibrated grid…\"");
    expect(read("BandTimeSweepPanel.js")).toContain("\"Sweeping…\"");
  });
});

describe("C6: the shared fold and section", () => {
  test("the page's fold is paper/Fold: content mounted while closed, the same label open (only the arrow turns)", () => {
    const { container } = rtlRender(<Fold show="Stored results, memory" hide="Hide stored results">inside words</Fold>);
    expect(container.querySelector("[data-paper='fold']")).not.toBeNull();
    const button = screen.getByRole("button");
    expect(button.textContent).toBe("▸Stored results, memory");
    expect(screen.getByText("inside words").hidden).toBe(true);
    fireEvent.click(button);
    expect(button.getAttribute("aria-expanded")).toBe("true");
    expect(button.textContent).toBe("▸Stored results, memory");
    expect(screen.getByText("inside words").hidden).toBe(false);
  });

  test("the page's own fold file keeps no copy of the row: it draws the shared one", () => {
    const src = stripComments(read("Fold.js"));
    expect(src).toMatch(/from "views\/Reports\/paper\/Fold"/);
    expect(src).not.toMatch(/Collapse|<button/);
  });

  test("the sections are paper/Section", () => {
    const idx = stripComments(read("index.js"));
    expect(idx).toMatch(/<Section id="biomarker-pairing" question="Report–recording pairing">/);
    expect(idx).toMatch(/<Section id="biomarker-timeline" question="Recording timeline">/);
    expect(idx).not.toMatch(/<Card\b/);
    expect(stripComments(read("BiomarkerHeatmapGrids.js")))
      .toMatch(/<Section id="biomarker-heat-maps" question="Power–pain heat maps"/);
  });
});

describe("C9: no dash for an empty value", () => {
  const FILES = ["BinarizationPreview.js", "gridReadouts.js", "CalibrationInEffectPanel.js",
    "BiomarkerHeatmapGrids.js", "BiomarkerDataTimeline.js", "BandTimeSweepPanel.js",
    "../ControlAnalyses/ControlAnalysesCard.js", "../ControlAnalyses/figures.js"];
  FILES.forEach((f) => {
    test(`${f}: no dash given as the value when one is missing`, () => {
      const src = stripComments(read(f));
      // a fallback (after ?, :, || or return) or a table cell that is only a dash
      expect(src).not.toMatch(/(\?|:|\|\||return)\s*"(\u2014|\u2013|\\u2014|\\u2013|-)"/);
      expect(src).not.toMatch(/\{"(\u2014|\u2013|-)"\}/);
    });
  });
});

describe("C12: the Background items are rows, not cards", () => {
  test("the calibration panel is a plain row with a hairline above it", () => {
    const src = stripComments(read("CalibrationInEffectPanel.js"));
    expect(src).not.toMatch(/<Card\b/);
    expect(src).toMatch(/data-paper="background-row"/);
  });

  test("the research checks on this page are drawn plain", () => {
    expect(stripComments(read("index.js")))
      .toMatch(/<ControlAnalysesSection participantUid=\{participant_uid\} page="biomarkers" clinicSheets=\{includeClinicSheetRatings\} plain \/>/);
  });
});

describe("D14: red only for the device's refusal", () => {
  test("every red ink on the page sits beside a refusal of a sensing pair", () => {
    ["index.js", "BiomarkerHeatmapGrids.js", "MatchWindowBand.js", "BinarizationPreview.js",
      "CalibrationInEffectPanel.js", "TimingHistogram.js", "BiomarkerDataTimeline.js",
      "../ControlAnalyses/ControlAnalysesCard.js", "../ControlAnalyses/figures.js"].forEach((f) => {
      const lines = stripComments(read(f)).split("\n");
      lines.forEach((l, i) => {
        if (!/T\.refused\b|refusedTint/.test(l)) return;
        const near = lines.slice(Math.max(0, i - 4), i + 4).join("\n");
        expect(`${f}:${i + 1} ${near}`).toMatch(/[Rr]efus/);
        expect(near).toMatch(/RefusedCross|\u2715|Refused today|M3\.5 3\.5/);
      });
    });
  });
});
