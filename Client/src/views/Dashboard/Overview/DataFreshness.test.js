import React from "react";
import {createRoot} from "react-dom/client";
import {act} from "react-dom/test-utils";
import DataFreshness, {freshnessDate} from "./DataFreshness";

jest.mock("components/MDBox", () => ({children, component: Tag = "div", sx, ...props}) => <Tag {...props}>{children}</Tag>);
jest.mock("components/MDTypography", () => ({children, component: Tag = "span", variant, fontWeight, display, color, sx, ...props}) => <Tag {...props}>{children}</Tag>);
let root, element;
const valid = {available: true, value: "2026-09-04T21:45:59.846000+00:00", precision: "second", partial: false};
beforeEach(() => {
  global.IS_REACT_ACT_ENVIRONMENT = true;
  jest.spyOn(Date, "now").mockReturnValue(Date.parse("2026-09-05T22:00:00Z"));
  element = document.createElement("div"); root = createRoot(element);
});
afterEach(() => {act(() => root.unmount()); jest.restoreAllMocks();});
const mount = props => act(() => root.render(<DataFreshness {...props}/>));

test("formats true source timestamps in Pacific time, including minute precision and winter offset", () => {
  expect(freshnessDate(valid)).toBe("Fri, Sep 4, 2026, 14:45 PDT");
  expect(freshnessDate({...valid, precision: "minute", value: "2026-09-04T16:56:00-07:00"})).toBe("Fri, Sep 4, 2026, 16:56 PDT");
  expect(freshnessDate({...valid, value: "2026-01-05T08:00:00Z"})).toBe("Mon, Jan 5, 2026, 00:00 PST");
});
test.each([undefined, {}, {...valid, available: false}, {...valid, precision: "day"},
  {...valid, value: null}, {...valid, value: 0}, {...valid, value: "2026-09-04T16:56:00"},
  {...valid, value: "not-a-timeZ"}, {...valid, value: "1970-01-01T00:00:00Z"},
  {...valid, value: "2027-01-01T00:00:00Z"}])("does not turn missing, ambiguous or invalid dates into evidence: %p", entry => {
  expect(freshnessDate(entry)).toBeNull();
});
test("renders four labeled rows with real source times, missing evidence and partial provenance", () => {
  mount({data: {redcap: valid, neural_json: {...valid, partial: true, reason: "Two files not indexed.", source: "Native session", semantics: "Observed session date."},
    neural_pdf: {...valid, precision: "minute"}, oura: {available: false, reason: "No timed measurements are saved."}}, checking: false});
  expect(element.querySelectorAll("dt")).toHaveLength(4);
  expect(element.querySelector('[data-freshness="redcap"] dd').textContent).toBe("Fri, Sep 4, 2026, 14:45 PDT");
  expect(element.querySelector('[data-freshness="neural_json"] dd').textContent).toContain("Partial coverage");
  expect(element.querySelector("details").textContent).toContain("Two files not indexed. Observed session date. Native session");
  expect(element.querySelector('[data-freshness="oura"]').textContent).toContain("Latest Oura measurementUnavailableNo timed measurements are saved.");
  expect(element.textContent).not.toContain("Last App Sync");
});
test("distinguishes initial loading, absent evidence and retained evidence during a failed status refresh", () => {
  mount({checking: true}); expect(element.querySelectorAll("dd")[0].textContent).toBe("Checking…");
  mount({checking: false}); expect(element.querySelectorAll("dd")[0].textContent).toBe("Unavailable");
  mount({data: {redcap: valid}, checking: true});
  expect(element.querySelectorAll("dd")[0].textContent).toContain("14:45 PDT");
  expect(element.textContent).toContain("showing the last successful check");
  expect(element.querySelectorAll("dd")[1].textContent).toBe("Unavailable");
});
