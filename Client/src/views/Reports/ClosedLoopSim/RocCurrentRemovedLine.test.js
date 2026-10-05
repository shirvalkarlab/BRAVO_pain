/**
 * The deployment ROC panel prints its area under the curve read again with the stimulation current
 * taken out, beside the plain one (2026-09-26). The panel has its own endpoint
 * (`band_deployment_roc`), which now carries `auc_current_removed` from the routine the deployment
 * summary already prints it with (decision 293). Descriptive only; a refusal prints its reason,
 * never a number; a response without the field prints nothing. Values below are RCS08's live
 * reading of 2026-09-26 (L 1-3+ 24.5 Hz, Left Leg VAS, tertile, 60 min, forecasting).
 *
 * Merged here 2026-10-05: DeploymentRocPanel.label.test.js. Each merged file's tests sit in a
 * describe block named after it, with its reason above it.
 */

import "@testing-library/jest-dom";
import { render, screen } from "@testing-library/react";
import RocCurrentRemovedLine from "./RocCurrentRemovedLine";
import { wrap } from "testUtils/render";
import fs from "fs";
import path from "path";

const LIVE = {
  available: true, label: "with the stimulation current taken out", hemisphere: "Left",
  shape_words: "a straight line", auc: 0.5799, auc_low: 0.4269, auc_high: 0.7111,
  n_spectral_samples: 469, n_pain_reports: 39, n_distinct_currents: 5, n_samples_without_current: 0,
  plain_on_same_samples: { auc: 0.6173, auc_low: 0.44, auc_high: 0.71 },
};

test("prints the adjusted area beside the plain one, with its interval, and says it is descriptive", () => {
  render(wrap(<RocCurrentRemovedLine plainAuc={0.6173} adjusted={LIVE} />));
  const line = screen.getByTestId("roc-current-removed");
  // "AUC" reads "How well it tells high pain from low" since the redesign of 2026-09-26.
  expect(line).toHaveTextContent("How well it tells high pain from low: 0.62 plainly; 0.58 (0.43–0.71) with the stimulation current taken out");
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
  // the summary's match-window reading (2026-10-02), never this panel's own second computation
  expect(src).toMatch(/<RocCurrentRemovedLine plainAuc=\{roc \? roc\.auc : null\} adjusted=\{currentRemoved \|\| null\} \/>/);
  expect(src.indexOf("<RocCurrentRemovedLine")).toBeGreaterThan(src.indexOf("<div ref={ref}"));
  expect(src.indexOf("<RocCurrentRemovedLine")).toBeLessThan(src.indexOf("<div ref={histRef}"));
});

/* From DeploymentRocPanel.label.test.js.
 * P-02 (triage 06-25 and 06-27, audit [28]; `artifacts/pending_items_from_handoffs_2026-09-25.md`).
 * The cut-point label on the deployment ROC panel read "oriented log-power units", left over from
 * before decisions 202 and 204 took log power out of every calculation on this path. The feature
 * the panel actually draws is standardised RAW power, oriented so AUC >= 0.5 (`analytics.
 * deployment_roc`: "The band feature is standardised raw power oriented so AUC >= 0.5"), the same
 * wording the panel's own feature-distribution histogram already uses ("Oriented band power
 * (standardized, cut-point scale)"). This test reads the component source directly, the same way
 * `DeploymentJumpLinks.order.test.js` pins page structure without rendering the panel (which needs
 * a live ROC payload from `useCachedResult`/Plotly to mount).
 */
describe("from DeploymentRocPanel.label", () => {
  const src = fs.readFileSync(path.join(__dirname, "DeploymentRocPanel.js"), "utf8");

  describe("the deployment ROC panel's cut-point label", () => {
    it("never says 'log-power' anywhere in the rendered label", () => {
      // The visible label lives in one <span>; assert on that element's text directly so a future
      // rewording of surrounding comments cannot make this pass by accident.
      const labelMatch = src.match(
        /<span style=\{\{ color: PAL.ink3 \}\}>\(([^)]*device LSB[^)]*)\)<\/span>/,
      );
      expect(labelMatch).not.toBeNull();
      const label = labelMatch[1];
      expect(label).not.toMatch(/log-power/i);
      expect(label).toMatch(/oriented,? standardi[sz]ed band power units/i);
    });
  });
});
