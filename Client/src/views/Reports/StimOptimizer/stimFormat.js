/**
 * Number and label formatting for the Stim Optimizer page, in one place.
 *
 * THE RULES (PI, 2026-09-12): digits only, never a spelled-out number ("zero", "two", "three of
 * four"); a unit on every number; the pain objective in "points" with its sign; contacts in the
 * project's Medtronic form ("L 0⁻2⁺"), which the SERVER produces (`analytics.format_channel`,
 * `display_short`) and this page only reads -- a raw channel key the response did not label is shown
 * as it arrived, marked, rather than re-derived here (decision 131: one definition, on the writer).
 */
/**
 * What an empty cell reads (TASTE_AUDIT.md C9, 2026-09-26): a word, never "—", which a screen
 * reader says as "em dash" and a reader can take for zero. A value the response does not carry is
 * "not given"; an empty list is "none"; a zero difference is "same" (the decision strip).
 */
export const EMPTY = "not given";

export const num = (v) => (v === null || v === undefined || !Number.isFinite(Number(v)) ? null : Number(v));

/** "3.0 mA" / "not given". */
export const fmtMa = (v, d = 1) => { const x = num(v); return x === null ? EMPTY : `${x.toFixed(d)} mA`; };
/** "55 Hz" / "not given". */
export const fmtHz = (v) => { const x = num(v); return x === null ? EMPTY : `${Number.isInteger(x) ? x : x.toFixed(1)} Hz`; };
/** "100 µs" / "not given". */
export const fmtUs = (v) => { const x = num(v); return x === null ? EMPTY : `${x.toFixed(0)} µs`; };
/** A pain-objective value, signed, in points: "+0.32 pts". Lower is better on this page. */
export const fmtPts = (v, d = 2) => { const x = num(v); return x === null ? EMPTY : `${x >= 0 ? "+" : "−"}${Math.abs(x).toFixed(d)} pts`; };
/** A signed difference in one unit: "+1.5 mA", "0 Hz". */
export const fmtDelta = (v, unit, d = 1) => {
  const x = num(v);
  if (x === null) return EMPTY;
  if (Math.abs(x) < 1e-9) return `0 ${unit}`;
  return `${x > 0 ? "+" : "−"}${Math.abs(x).toFixed(d)} ${unit}`;
};
/** An integer count: "12 of 18"; a missing part is said in words ("not given (of 18)"). */
export const fmtOf = (n, of) => {
  const a = num(n), b = num(of);
  if (a === null) return b === null ? EMPTY : `${EMPTY} (of ${Math.round(b)})`;
  return b === null ? `${Math.round(a)} of an unstated number` : `${Math.round(a)} of ${Math.round(b)}`;
};

/** "L" / "R" from "Left" / "Right"; anything else unchanged. */
export const sideLetter = (h) => (h === "Left" ? "L" : (h === "Right" ? "R" : String(h || "")));

/**
 * The contact label to print. Reads the server's own Medtronic-form label first (`display_short`,
 * e.g. "L 0⁻2⁺"). A record without one is an older cached response; its raw key is printed with
 * underscores as spaces and a trailing marker so a reader knows it was not formatted, and never
 * translated here.
 */
export function contactLabel(rec, rawKey) {
  const short = rec && (rec.display_short || rec.contacts_short);
  if (short) return String(short);
  const raw = rawKey || (rec && (rec.channel || rec.contacts_raw)) || "";
  return raw ? `${String(raw).replace(/_/g, " ")} (unformatted)` : EMPTY;
}

/** The pain site's plain name: "left leg" / "back" from the arm key's site part. */
export const siteName = (site) => String(site || "").replace(/_vas$/, "").replace(/_/g, " ");
