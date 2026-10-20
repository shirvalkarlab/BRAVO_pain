/** Synthetic ROC response tests; no participant observations. */

import "@testing-library/jest-dom";
import { render, screen } from "@testing-library/react";
import RocCurrentRemovedLine from "./RocCurrentRemovedLine";
import { wrap } from "testUtils/render";
import fs from "fs";
import path from "path";

const SYNTHETIC = {
  available: true, label: "with the stimulation current taken out", hemisphere: "Left",
  shape_words: "a straight line", auc: 0.675, auc_low: 0.55, auc_high: 0.825,
  n_spectral_samples: 24, n_pain_reports: 8, n_distinct_currents: 3, n_samples_without_current: 0,
  plain_on_same_samples: { auc: 0.725, auc_low: 0.6, auc_high: 0.85 },
};

test("prints the adjusted area beside the plain one, with its interval, and says it is descriptive", () => {
  render(wrap(<RocCurrentRemovedLine plainAuc={0.725} adjusted={SYNTHETIC} />));
  const line = screen.getByTestId("roc-current-removed");
  // "AUC" reads "How well it tells high pain from low" since the redesign of 2026-09-26.
  expect(line).toHaveTextContent("How well it tells high pain from low: 0.72 plainly; 0.68 (0.55–0.82) with the stimulation current taken out");
  expect(line).toHaveTextContent("8 pain reports");
  expect(line).toHaveTextContent("3 distinct Left currents");
  expect(line).toHaveTextContent("Descriptive only");
});

test("a refusal prints its reason, never a number", () => {
  render(wrap(<RocCurrentRemovedLine plainAuc={0.725}
    adjusted={{ available: false, why: "no dated stimulation settings have been filed" }} />));
  const line = screen.getByTestId("roc-current-removed");
  expect(line).toHaveTextContent("With the stimulation current taken out: not computed (no dated stimulation settings have been filed)");
  expect(line).not.toHaveTextContent("0.");
});

test("a response without the field prints nothing", () => {
  render(wrap(<RocCurrentRemovedLine plainAuc={0.725} adjusted={null} />));
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
