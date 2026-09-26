/**
 * The deployment ROC panel prints its area under the curve read again with the stimulation current
 * taken out, beside the plain one (2026-09-26). The panel has its own endpoint
 * (`band_deployment_roc`), which now carries `auc_current_removed` from the routine the deployment
 * summary already prints it with (decision 293). Descriptive only; a refusal prints its reason,
 * never a number; a response without the field prints nothing. Values below are RCS08's live
 * reading of 2026-09-26 (L 1-3+ 24.5 Hz, Left Leg VAS, tertile, 60 min, forecasting).
 */
import "@testing-library/jest-dom";
import { render, screen } from "@testing-library/react";
import { ThemeProvider } from "@mui/material/styles";
import theme from "assets/theme";
import { PlatformContextProvider } from "context";
import RocCurrentRemovedLine from "./RocCurrentRemovedLine";

const wrap = (ui) => (
  <ThemeProvider theme={theme}>
    <PlatformContextProvider initialStates={{ darkMode: false }}>{ui}</PlatformContextProvider>
  </ThemeProvider>
);
const LIVE = {
  available: true, label: "with the stimulation current taken out", hemisphere: "Left",
  shape_words: "a straight line", auc: 0.5799, auc_low: 0.4269, auc_high: 0.7111,
  n_spectral_samples: 469, n_pain_reports: 39, n_distinct_currents: 5, n_samples_without_current: 0,
  plain_on_same_samples: { auc: 0.6173, auc_low: 0.44, auc_high: 0.71 },
};

test("prints the adjusted area beside the plain one, with its interval, and says it is descriptive", () => {
  render(wrap(<RocCurrentRemovedLine plainAuc={0.6173} adjusted={LIVE} />));
  const line = screen.getByTestId("roc-current-removed");
  expect(line).toHaveTextContent("AUC 0.62 plainly; 0.58 (0.43–0.71) with the stimulation current taken out");
  expect(line).toHaveTextContent("39 pain reports");
  expect(line).toHaveTextContent("5 distinct Left currents");
  expect(line).toHaveTextContent("Descriptive only");
});

test("a refusal prints its reason, never a number", () => {
  render(wrap(<RocCurrentRemovedLine plainAuc={0.6173}
    adjusted={{ available: false, why: "no dated stimulation settings have been filed" }} />));
  const line = screen.getByTestId("roc-current-removed");
  expect(line).toHaveTextContent("With the stimulation current taken out: not computed (no dated stimulation settings have been filed)");
  expect(line).not.toHaveTextContent("0.");
});

test("a response without the field prints nothing", () => {
  render(wrap(<RocCurrentRemovedLine plainAuc={0.6173} adjusted={null} />));
  expect(screen.queryByTestId("roc-current-removed")).toBeNull();
});

test("the panel places the line under its ROC figure", () => {
  const fs = require("fs");
  const path = require("path");
  const src = fs.readFileSync(path.join(__dirname, "DeploymentRocPanel.js"), "utf8");
  expect(src).toMatch(/<RocCurrentRemovedLine plainAuc=\{roc \? roc\.auc : null\} adjusted=\{envOk \? env\.auc_current_removed : null\} \/>/);
  expect(src.indexOf("<RocCurrentRemovedLine")).toBeGreaterThan(src.indexOf("<div ref={ref}"));
  expect(src.indexOf("<RocCurrentRemovedLine")).toBeLessThan(src.indexOf("<div ref={histRef}"));
});
