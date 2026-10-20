/**
 * The timeline's left-gutter geometry (the bravo-timeline-layout rule), as pure functions so it
 * can be tested without drawing the figure. Three right-to-left columns -- tick numbers, contact
 * names, the rotated region tab -- are laid from ESTIMATED text widths (Arial about
 * 0.58 x font size x characters; bold 0.62) with one uniform gap; the contact and region fonts
 * shrink together, 1 px at a time, only while the margin would exceed LEFT_CAP. Every left
 * annotation of `BiomarkerDataTimeline.js` reads the x-shifts returned here, and the figure's left
 * margin is MARGIN_L exactly. The skill's `kernel.py` computes the same numbers in Python.
 *
 * `fitRowLabel` (2026-09-26): a row label's subtitle (the PAIN row's score name) sits in the
 * contact column, right-anchored, but was never in the column budget; "Composite (MPQ + Left Leg
 * VAS)" ran about 78 px off the figure. The rows below the lanes carry no region tab, so a subtitle
 * may use the whole width from the contact column's right edge to one gap inside the figure's left
 * edge. It is wrapped at word breaks to that width and, only if one word still does not fit, shrunk
 * 1 px at a time to 11 px (the house minimum for any text).
 */
export const LBL_GAP = 12;          // uniform px gap between columns and at both ends
export const LEFT_CAP = 230;        // max gutter before the fonts shrink
export const F_TICK = 14;
export const MIN_TEXT_PX = 11;

export const textW = (s, fs, bold) => (bold ? 0.62 : 0.58) * fs * String(s).length;

export function gutterGeometry(prettyChans, { fContact = 26, fRegion = 18 } = {}) {
  const W_tick = 4.2 * 0.58 * F_TICK;         // budget for a 4-char number
  let F_CONTACT = fContact;
  let F_REGION = fRegion;
  const layoutLeft = () => {
    const W_contact = Math.max(40, ...(prettyChans || []).map((s) => textW(s, F_CONTACT, true)));
    const W_region = 2 * 1.25 * F_REGION;     // rotated 2-line block (name / region) height
    const xTick = -LBL_GAP;
    const xContact = -(LBL_GAP + W_tick + LBL_GAP);
    const xRegionCenter = -(LBL_GAP + W_tick + LBL_GAP + W_contact + LBL_GAP + W_region / 2);
    const marginL = LBL_GAP + W_tick + LBL_GAP + W_contact + LBL_GAP + W_region + LBL_GAP;
    return { xTick, xContact, xRegionCenter, marginL, W_contact, W_region };
  };
  let L = layoutLeft();
  while (L.marginL > LEFT_CAP && F_CONTACT > 16) {
    F_CONTACT -= 1; F_REGION = Math.max(13, F_REGION - 0.6); L = layoutLeft();
  }
  return {
    X_TICK: Math.round(L.xTick), X_CONTACT: Math.round(L.xContact),
    X_REGION: Math.round(L.xRegionCenter), MARGIN_L: Math.ceil(L.marginL),
    F_CONTACT, F_REGION, W_tick, W_contact: L.W_contact, W_region: L.W_region,
    LBL_GAP, LEFT_CAP,
  };
}

function wrapWords(text, fontPx, maxPx) {
  const words = String(text).split(/\s+/).filter(Boolean);
  const lines = [];
  let cur = "";
  words.forEach((w) => {
    const next = cur ? `${cur} ${w}` : w;
    if (cur && textW(next, fontPx, false) > maxPx) { lines.push(cur); cur = w; } else { cur = next; }
  });
  if (cur) lines.push(cur);
  return lines;
}

/** A contact-column subtitle wrapped (and, only if a word will not fit, shrunk) to the space the
 *  row has: from the contact column's right edge to one gap inside the figure's left edge. */
export function fitRowLabel(text, geom, startPx = 14) {
  const maxPx = geom.MARGIN_L - LBL_GAP + geom.X_CONTACT;   // X_CONTACT is negative
  let fontPx = startPx;
  let lines = wrapWords(text, fontPx, maxPx);
  while (fontPx > MIN_TEXT_PX && lines.some((ln) => textW(ln, fontPx, false) > maxPx)) {
    fontPx -= 1;
    lines = wrapWords(text, fontPx, maxPx);
  }
  return { lines, fontPx };
}

/** Row subtitles that say only what their row shows, short enough for one line at 13 px in the
 *  contact column (2026-09-26: the longer forms ran off the figure; the PI ruled out the hover). */
export const eventsRowSubtitle = (nLabeled) => `${nLabeled} labeled`;
export const matchedRowSubtitle = (used, total) => `${used} of ${total} matched`;
