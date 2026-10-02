/**
 * One date style on every page (page review 2026-10-02, item 4.8): the Stim Optimizer page printed
 * "Oct 2, 2026, 6:47 AM", "10/2/2026, 5:46:48 AM" and "2026-09-02" for the same kind of fact.
 * Times read like the stored-results line (medium date, short time); dates alone, medium date.
 */
import { fmtDateTime, fmtDate } from "./dates";

const ref = (opts) => new Date("2026-10-02T13:47:00Z").toLocaleString(undefined, opts);

test("a time is the medium date and short time, the stored-results line's style", () => {
  expect(fmtDateTime("2026-10-02T13:47:00Z")).toBe(ref({ dateStyle: "medium", timeStyle: "short" }));
  expect(fmtDateTime(Date.parse("2026-10-02T13:47:00Z"))).toBe(ref({ dateStyle: "medium", timeStyle: "short" }));
});
test("a date alone is the medium date, never a raw ISO string", () => {
  expect(fmtDate("2026-09-02")).toBe(new Date("2026-09-02T00:00:00Z").toLocaleDateString(undefined, { dateStyle: "medium", timeZone: "UTC" }));
  expect(fmtDate("2026-09-02T19:15:00+00:00")).not.toMatch(/T19/);
});
test("nothing, or something unreadable, is said as such", () => {
  expect(fmtDateTime(null)).toBe(null);
  expect(fmtDate("not a date")).toBe("not a date");
});
