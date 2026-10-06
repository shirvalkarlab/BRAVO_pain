/**
 * Indefinite streaming's modelled points on the recording timeline (item P-11, 2026-10-06).
 *
 * Pinned: the server marks them with ";indefinite" after the route and constant in `method`; the
 * page draws them as open squares (montage TD stays circles, the PSD bridge diamonds), names them
 * "indefinite TD, stimulation off" in the hover, still reads the constant from the server's text,
 * and the legend names the square only when such a point is on the page.
 */
import fs from "fs";
import path from "path";
import { modeledLegendName, routeLabel } from "./calibrationLabels";

const IND = "td_transform_x_k=349.10;indefinite;band=in_force";

test("the hover names the source and the server's constant", () => {
  expect(routeLabel(IND)).toBe("indefinite TD, stimulation off, transform constant ×349.10");
  expect(routeLabel("td_transform_x_k=349.10")).toBe("TD, transform constant ×349.10");
});

test("the legend names the square only when such a point is drawn", () => {
  expect(modeledLegendName([{ method: IND }])).toContain("□ indefinite TD, stimulation off");
  expect(modeledLegendName([{ method: "td_transform_x_k=349.10" }])).not.toContain("indefinite");
});

test("indefinite points are drawn as open squares, apart from the montage circles", () => {
  const code = fs.readFileSync(path.join(__dirname, "BiomarkerDataTimeline.js"), "utf8");
  expect(code).toMatch(/\[ms_ind, "square-open"\]/);
  expect(code).toMatch(/startsWith\("td_transform"\) && !isInd\(m\)/);
});
