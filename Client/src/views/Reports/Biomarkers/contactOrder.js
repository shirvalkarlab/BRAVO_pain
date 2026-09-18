/**
 * The order sensing contact pairs are listed in, everywhere a page lists them: LEFT before RIGHT,
 * and within each side ascending by contact number (0-2 before 0-3 before 1-3).
 *
 * Moved out of BiomarkerHeatmapGrids.js on 2026-09-11 so the Closed-Loop Deployment page's band
 * heat map orders its contact tabs by the same rule as the Biomarkers thumbnails (the PI's
 * instruction: "ordered left to right as in biomarkers thumbnails"), from one definition.
 */
const _WORD2DIGIT_STRIP = { ZERO: "0", ONE: "1", TWO: "2", THREE: "3", FOUR: "4",
  FIVE: "5", SIX: "6", SEVEN: "7", EIGHT: "8", NINE: "9" };

/** Reads the server's own display fields first and only falls back to the raw channel key
 * (e.g. "ZERO_TWO_LEFT") for an older, unlabeled cached response. Returns [sideRank, contactRank]. */
export function contactSortKey(ch, sw) {
  const hemi = (sw && sw.display_hemisphere)
    || (/LEFT/i.test(ch) ? "Left" : (/RIGHT/i.test(ch) ? "Right" : ""));
  const hemiRank = hemi === "Left" ? 0 : (hemi === "Right" ? 1 : 2);
  const contactsStr = (sw && sw.display_contacts) || "";
  let digits = (contactsStr.match(/\d/g) || []).map(Number);
  if (!digits.length) {
    const toks = String(ch || "").toUpperCase().replace(/-/g, "_").split("_")
      .filter((t) => _WORD2DIGIT_STRIP[t] !== undefined || /^\d+$/.test(t));
    digits = toks.map((t) => Number(_WORD2DIGIT_STRIP[t] !== undefined ? _WORD2DIGIT_STRIP[t] : t));
  }
  const contactsRank = digits.length ? digits[0] * 10 + (digits[1] || 0) : 0;
  return [hemiRank, contactsRank];
}

/** Sort channel keys with contactSortKey, given the map of channel -> sweep. */
export function orderContacts(sweeps) {
  return Object.keys(sweeps || {}).sort((a, b) => {
    const ka = contactSortKey(a, sweeps[a]);
    const kb = contactSortKey(b, sweeps[b]);
    return (ka[0] - kb[0]) || (ka[1] - kb[1]);
  });
}
