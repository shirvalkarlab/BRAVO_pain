/**
 * One date style on every page (page review 2026-10-02, item 4.8): a time reads like the
 * stored-results line, medium date and short time in the reader's own locale ("Oct 2, 2026,
 * 6:47 AM"); a date alone, the medium date ("Sep 2, 2026"), never a raw ISO string.
 */
const toDate = (v) => {
  if (v === null || v === undefined || v === "") return null;
  const d = typeof v === "number" ? new Date(v) : new Date(String(v));
  return Number.isNaN(d.getTime()) ? null : d;
};

export function fmtDateTime(v) {
  if (v === null || v === undefined || v === "") return null;
  const d = toDate(v);
  return d ? d.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" }) : String(v);
}

/** A calendar date. A bare "YYYY-MM-DD" is that day wherever the reader is (read as UTC). */
export function fmtDate(v) {
  if (v === null || v === undefined || v === "") return null;
  const s = String(v);
  const bare = /^\d{4}-\d{2}-\d{2}$/.test(s);
  const d = toDate(bare ? `${s}T00:00:00Z` : s);
  if (!d) return s;
  return d.toLocaleDateString(undefined, { dateStyle: "medium", ...(bare ? { timeZone: "UTC" } : {}) });
}
