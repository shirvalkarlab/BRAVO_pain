/**
 * The Biomarkers timeline names the calibration constant it was served, never a literal (decision 209).
 *
 * Until 2026-09-20 the timeline's three route labels ("transform DSP ×352.62", "PSD→LSB bridge
 * ×73.63") were typed into the component, so the day the constant moved (352.62 → 349.10, decision
 * 209) the page would have kept printing the old one beside points computed with the new one. The
 * server already writes the constant into every modeled point (`method: "td_transform_x_k=349.10"`)
 * and every per-rating record (`reason: "direct TD->LSB transform (k=349.10)"`); the labels are now
 * read from those strings, and the component source carries no calibration number at all.
 *
 * Since 2026-09-25 the labels name the two sources in the PI's one vocabulary for the page -- TD
 * (the time-domain recording) and PSD (the device's 30 s snapshot) -- beside each constant's own
 * name; the legend entry is the timeline's first mention of TD, so it defines it.
 */
import fs from "fs";
import path from "path";

import { kFromServed, routeLabel, modeledLegendName } from "./calibrationLabels";

describe("the route label is read from the served method or reason string", () => {
  test("a transform point names the k it was served", () => {
    expect(routeLabel("td_transform_x_k=349.10")).toBe("TD, transform constant ×349.10");
    expect(routeLabel("td_transform_x_k=352.62")).toBe("TD, transform constant ×352.62");
  });
  test("a bridge point names the bridge k it was served", () => {
    expect(routeLabel("event_psd_bridge_x_k=72.90")).toBe("PSD, bridge constant ×72.90");
  });
  test("a per-rating reason sentence yields the same number", () => {
    expect(kFromServed("direct TD->LSB transform (k=349.10)")).toBe("349.10");
    expect(kFromServed("PSD-only event bridge (k=72.90)")).toBe("72.90");
    expect(kFromServed("device-sensed in band")).toBe(null);
  });
  test("a point with no route string is labelled without a number, never with a stale one", () => {
    expect(routeLabel(undefined)).toBe("modeled");
    expect(routeLabel("td_transform")).toBe("TD, transform constant");
  });
  test("the legend entry is built from the constants seen in the data", () => {
    const pts = [{ method: "td_transform_x_k=349.10" }, { method: "event_psd_bridge_x_k=72.90" },
                 { method: "td_transform_x_k=349.10" }];
    expect(modeledLegendName(pts)).toBe(
      "modeled LSB  (○ time domain (TD), transform constant ×349.10 · ◇ PSD, bridge constant ×72.90; red ring = TD saturated)");
    expect(modeledLegendName([])).toBe("modeled LSB  (○ time domain (TD), transform constant · ◇ PSD, bridge constant; red ring = TD saturated)");
  });
});

describe("the timeline source carries no calibration constant", () => {
  const src = fs.readFileSync(path.join(__dirname, "BiomarkerDataTimeline.js"), "utf8");
  const code = src.split("\n").filter((l) => !/^\s*\/\//.test(l)).join("\n");
  test.each(["352.62", "349.10", "73.63", "72.90"])("no literal %s outside comments", (tok) => {
    expect(code).not.toContain(tok);
  });
});
