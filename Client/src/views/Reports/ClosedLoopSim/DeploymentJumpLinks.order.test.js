/**
 * The jump links at the top right of the Closed-Loop page are a table of contents: the comment
 * above them in DeploymentDecisionHeader.js says their order IS the page's reading order. That
 * makes the list a second copy of an order the page already carries, and a second copy drifts.
 *
 * It had drifted. The list put "CL-DBS simulations" above "Sign-off", while on the page the
 * sign-off card renders first and the simulations card below it, so a clinician following the list
 * downward was sent back up. The down-arrow on the sign-off label said the same untrue thing.
 *
 * This test reads the page file itself and compares the order the jump ids appear there with the
 * order of the list. It fails whether someone reorders the cards or reorders the links, which is
 * the only way a copy of an order stays honest.
 */
import fs from "fs";
import path from "path";

import { JUMPS } from "./DeploymentDecisionHeader";

const pageSource = fs.readFileSync(path.join(__dirname, "index.js"), "utf8");

/** Every `id="cl-..."` in index.js, in the order the file sets them. */
const idsInPageOrder = () => {
  const found = [];
  const re = /id="(cl-[a-z0-9-]+)"/g;
  let m = re.exec(pageSource);
  while (m) {
    found.push(m[1]);
    m = re.exec(pageSource);
  }
  return found;
};

describe("the Closed-Loop page's jump links are a table of contents", () => {
  it("every link points at a section the page actually sets an id on", () => {
    const onPage = idsInPageOrder();
    const missing = JUMPS.map((j) => j.id).filter((id) => !onPage.includes(id));
    expect(missing).toEqual([]);
  });

  it("the links are listed in the order the sections render down the page", () => {
    const onPage = idsInPageOrder();
    const linked = JUMPS.map((j) => j.id);
    const sameIdsInPageOrder = onPage.filter((id) => linked.includes(id));
    expect(linked).toEqual(sameIdsInPageOrder);
  });

  it("no label claims a position the page does not give it", () => {
    // A down-arrow on a label reads as "this is the bottom of the page". Only the last link can
    // say that, and the sign-off card is no longer last.
    const labelsWithArrow = JUMPS.filter((j) => /↓/.test(j.label));
    const last = JUMPS[JUMPS.length - 1];
    labelsWithArrow.forEach((j) => expect(j.id).toBe(last.id));
  });
});
