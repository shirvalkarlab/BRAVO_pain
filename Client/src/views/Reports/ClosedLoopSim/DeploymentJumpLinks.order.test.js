/**
 * The jump links at the top right of the Closed-Loop page's decision card are a table of contents:
 * their order IS the page's reading order (they lived on the sticky header until decision 302). That
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

// DecisionCard reaches Plotly (figure pictures for the printed record) and the session controller.
jest.mock("plotly.js-dist", () => ({ react: jest.fn(), purge: jest.fn(), toImage: jest.fn() }));
jest.mock("database/session-control", () => ({ SessionController: { query: jest.fn() } }));

// eslint-disable-next-line import/first
import { JUMPS } from "./DecisionCard";

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

  it("the decision card, which carries Sign and print, comes straight after the grid (decision 302)", () => {
    // The PI, 2026-09-26, merged the sign-off card into the one decision card at the top of the
    // decision area; decision 258(a)'s "sign-off card last" is superseded with it. The record a
    // clinician signs is printed from that card, and the print opens every fold in it.
    const onPage = idsInPageOrder();
    expect(onPage.slice(0, 2)).toEqual(["cl-grid", "cl-decision"]);
    expect(onPage).not.toContain("cl-signoff");
    expect(onPage).not.toContain("cl-prescription");
    expect(onPage).not.toContain("cl-what-changes");
    expect(JUMPS.map((j) => j.id)).not.toContain("cl-decision");
  });
});
