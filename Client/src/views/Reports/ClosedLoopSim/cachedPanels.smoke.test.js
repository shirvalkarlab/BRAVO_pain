/**
 * A render smoke test for the five analyst panels whose fetches were moved onto the shared result
 * cache.
 *
 * WHAT IT IS FOR, AND WHAT IT IS NOT. Moving a fetch out of a component removes its `useState`
 * declarations along with it, and a reference left behind to one of those removed names is a
 * blank clinician-facing panel at runtime rather than a build failure. The linter catches an
 * undefined name; it does not catch a panel that throws while rendering because a value it reads
 * out of the cached envelope is shaped differently from the value the old state held. So each panel
 * is rendered twice — once with nothing cached, and once with a cached payload — and the assertion
 * is simply that it renders and shows its own heading.
 *
 * It is deliberately NOT an assertion about what the panels display. `panels.payload.test.js` does
 * that against the real recorded response, and duplicating it here would mean two places to update
 * when a payload field moves.
 *
 * Plotly is replaced rather than run: these panels draw through the imperative `Plotly.react`
 * interface against a real graph node, which jsdom cannot provide, and the drawing is not what is
 * under test.
 */
import "@testing-library/jest-dom";
import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import { ThemeProvider } from "@mui/material/styles";

import theme from "assets/theme";
import { PlatformContextProvider } from "context";

import { invalidateAll, putResult, settingsKey } from "database/resultCache";
import { CL } from "views/Reports/moduleCacheKeys";

import ConversionModelPanel from "./ConversionModelPanel";
import DeploymentRocPanel from "./DeploymentRocPanel";
import EraRefitPanel from "./EraRefitPanel";
import LsbPowerPanel from "./LsbPowerPanel";
import PsdLsbPanel from "./PsdLsbPanel";

jest.mock("plotly.js-dist", () => ({
  react: jest.fn(), purge: jest.fn(), restyle: jest.fn(), relayout: jest.fn(), newPlot: jest.fn(),
}));
jest.mock("database/session-control", () => ({
  SessionController: { query: jest.fn() },
}));
// eslint-disable-next-line import/first
import { SessionController } from "database/session-control";

const UID = "TEST01";
const BC = { contact: "ZERO_THREE_LEFT", center_freq_hz: 9.77, bandwidth_hz: 5.0 };
const REQ = { LabelMetric: "vas" };

const wrap = (ui) => (
  <ThemeProvider theme={theme}>
    <PlatformContextProvider initialStates={{ darkMode: false }}>{ui}</PlatformContextProvider>
  </ThemeProvider>
);

beforeEach(() => {
  invalidateAll("smoke test setup");
  SessionController.query.mockReset();
  // Every request, including the hook's server-identity call, answers with something inert. The
  // panels each treat an unavailable answer as a sentence to display rather than an error, which is
  // exactly the path worth smoke-testing: it is the one a participant with no data takes.
  SessionController.query.mockImplementation(() => Promise.resolve({
    data: { boot_token: "boot-1", available: false, reason: "no data in this test" },
  }));
});

const PANELS = [
  ["DeploymentRocPanel", <DeploymentRocPanel participantUid={UID} bandCandidate={BC}
    requestParams={REQ} onCutpoint={() => {}} lsbThreshold={null} />, /Deployment ROC/],
  ["EraRefitPanel", <EraRefitPanel participantUid={UID} bandCandidate={BC}
    requestParams={REQ} />, /Per-era refit/],
  ["LsbPowerPanel", <LsbPowerPanel participantUid={UID} bandCandidate={BC} requestParams={REQ}
    cutpoint={{ threshold: 1.5, matchDir: "prior" }} onLsbThreshold={() => {}}
    deploymentReport={{ data: null }} />, /LSB threshold/],
  ["PsdLsbPanel", <PsdLsbPanel participantUid={UID} bandCandidate={BC}
    requestParams={REQ} />, /device-LSB conversion/],
  ["ConversionModelPanel", <ConversionModelPanel participantUid={UID} />,
    /conversion model/],
];

describe.each(PANELS)("%s", (name, element, heading) => {
  test("renders with nothing cached", async () => {
    render(wrap(element));
    await waitFor(() => expect(screen.getAllByText(heading).length).toBeGreaterThan(0));
  });
});

test("a cached entry whose settings have changed renders the panel and its stale notice", async () => {
  // Stored under a DIFFERENT band centre from the one the panel is about to ask for, which is the
  // situation the notice exists for: the figure on screen was computed for another band.
  putResult(CL.era, UID, settingsKey({ Channel: BC.contact, CenterHz: 8.0, BandWidthHz: 5.0, ...REQ }),
    {
      available: true,
      by_era: {
        available: true,
        thresholds_mA: { off_max: 0, low_max: 2 },
        // The minimum the forest plot reads. Every era is unestimable, which is a real state the
        // panel is built to draw and the cheapest one to write down here.
        eras: { OFF: null, LOW: null, HIGH: null },
        era_counts: {},
        pooled: null,
      },
    });

  render(wrap(<EraRefitPanel participantUid={UID} bandCandidate={BC} requestParams={REQ} />));

  expect(await screen.findByText(/Per-era refit/)).toBeInTheDocument();
  expect(screen.getByText(/last completed run for this panel/)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /Recompute this panel/ })).toBeInTheDocument();
});
