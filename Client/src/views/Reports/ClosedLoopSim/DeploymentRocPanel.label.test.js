/**
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
import fs from "fs";
import path from "path";

const src = fs.readFileSync(path.join(__dirname, "DeploymentRocPanel.js"), "utf8");

describe("the deployment ROC panel's cut-point label", () => {
  it("never says 'log-power' anywhere in the rendered label", () => {
    // The visible label lives in one <span>; assert on that element's text directly so a future
    // rewording of surrounding comments cannot make this pass by accident.
    const labelMatch = src.match(
      /<span style=\{\{ color: "#5E5E5E" \}\}>\(([^)]*device LSB[^)]*)\)<\/span>/,
    );
    expect(labelMatch).not.toBeNull();
    const label = labelMatch[1];
    expect(label).not.toMatch(/log-power/i);
    expect(label).toMatch(/oriented,? standardi[sz]ed band power units/i);
  });
});
