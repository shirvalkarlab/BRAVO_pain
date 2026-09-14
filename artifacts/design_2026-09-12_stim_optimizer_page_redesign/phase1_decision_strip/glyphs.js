/**
 * The four verdict symbols the Closed-Loop family of pages draws, in one place.
 *
 * Lifted out of BandSweepGridPanel.js on 2026-09-12 so the Stim Optimizer page can draw the SAME
 * symbols for the same meanings (decision 122 approved these shapes and inks on the Closed-Loop
 * page): a filled disc with a tick, a filled square with a cross, a plain amber disc, and an open
 * dashed circle for "not tested". Distinct SHAPES as well as distinct inks, because about eight
 * per cent of men cannot separate these hues and this page prints.
 *
 * Meanings, so the two pages cannot drift: Tick = passes / the same; Cross = fails / different;
 * Amber = measured and cannot tell; NotTested = the question was not put. "Not determinable" on the
 * Stim Optimizer page (a difference that could not be FORMED) takes NotTested, never Amber, because
 * it is the absence of a comparison rather than an inconclusive one.
 */
import PAL from "./palette";

export const GLYPH = 15;

export function TickGlyph({ label, size = GLYPH }) {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" role="img" aria-label={label}>
      <circle cx="8" cy="8" r="7" fill={PAL.pass} />
      <path d="M4.5 8.3 L7 10.8 L11.5 5.5" stroke="#fff" strokeWidth="1.9" fill="none"
        strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
export function CrossGlyph({ label, size = GLYPH }) {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" role="img" aria-label={label}>
      <rect width="16" height="16" rx="2" fill={PAL.fail} />
      <path d="M4.5 4.5 L11.5 11.5 M11.5 4.5 L4.5 11.5" stroke="#fff" strokeWidth="1.9"
        strokeLinecap="round" />
    </svg>
  );
}
export function AmberGlyph({ label, size = GLYPH }) {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" role="img" aria-label={label}>
      <circle cx="8" cy="8" r="7" fill={PAL.warn} />
    </svg>
  );
}
export function NotTestedGlyph({ label, size = GLYPH }) {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" role="img" aria-label={label}>
      <circle cx="8" cy="8" r="6.5" fill="none" stroke={PAL.neutral} strokeWidth="1.4"
        strokeDasharray="2 2" />
    </svg>
  );
}

/** One symbol from a three-valued answer: true = tick, false = cross, null = not tested. */
export function TriGlyph({ value, labels, size = GLYPH }) {
  const l = labels || {};
  if (value === true) return <TickGlyph label={l.yes || "yes"} size={size} />;
  if (value === false) return <CrossGlyph label={l.no || "no"} size={size} />;
  return <NotTestedGlyph label={l.none || "not assessed"} size={size} />;
}
