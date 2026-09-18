import React from "react";
import { render, screen } from "@testing-library/react";
import CacheStatusLine, { cacheStatusText } from "./CacheStatusLine";

jest.mock("components/MDBox", () => ({ children }) => <div>{children}</div>);
jest.mock("components/MDTypography", () => ({ children }) => <span>{children}</span>);

test.each([null, undefined, false, "not a status"])("missing status renders nothing: %s", (status) => {
  expect(cacheStatusText(status)).toBeNull();
  const { container } = render(<CacheStatusLine status={status} />);
  expect(container.textContent).toBe("");
});

test("stored input build time carries an explicit timezone and input meaning", () => {
  render(<CacheStatusLine status={{ exists: true, kind: "inputs", last_built_utc: "2026-09-18T12:00:00Z",
    what_it_means: "the decoded recordings and matched pain reports were stored" }} />);
  expect(screen.getByText(/Stored inputs last assembled Fri, 18 Sep 2026 12:00:00 GMT/)).toBeTruthy();
  expect(screen.getByText(/decoded recordings and matched pain reports/)).toBeTruthy();
});

test.each([null, "invalid date", 123])("stored answer without trustworthy timestamp stays explicit: %s", (stamp) => {
  expect(cacheStatusText({ exists: true, last_built_utc: stamp })).toMatch(/build time is unavailable/);
});

test("cache miss does not claim the analysis just ran or launch a request", () => {
  const { rerender } = render(<CacheStatusLine status={{ exists: false }} />);
  expect(screen.getByText(/No stored entry or build time is available/)).toBeTruthy();
  rerender(<CacheStatusLine status={{ exists: false, note: "private /path/error", what_it_means: {} }} />);
  expect(screen.getByText(/No stored entry or build time is available/)).toBeTruthy();
  expect(screen.queryByText(/private/)).toBeNull();
});

test("result cache uses result wording and unknown input build times remain explicit", () => {
  expect(cacheStatusText({ exists: true, last_built_utc: "2026-09-18T12:00:00Z" }))
    .toMatch(/Stored results last built/);
  expect(cacheStatusText({ exists: true, kind: "inputs" }))
    .toBe("Stored inputs are available; their build time is unavailable.");
});
