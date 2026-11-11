/**
 * Sense-to-control algorithm wiring (the PI, 2026-10-08): which side's sensed band power drives the
 * Adaptive Therapy of which stimulated side. On screen: Closed-Loop page, the card under
 * "Stimulation program".
 *
 * The device's own terms (programming guide A610 p. 37 and p. 39; rules D38-D40): Adaptive Therapy
 * is set per hemisphere, and a hemisphere either uses its own sensing (ipsilateral) or, on a dual
 * lead implant, the other hemisphere's sensing (contralateral sensing, a documented fallback, D39).
 *
 * The choice is remembered in this browser per participant. It decides which stimulators the
 * decision card answers for (`controllers`): one card per stimulator, each checked with the band
 * chosen on the side that drives it (Band selection takes one band per side).
 */

export const WIRINGS = [
  { key: "independent", label: "2 independent controllers: Ipsilateral wiring",
    medtronic: "Left: ipsilateral sensing. Right: ipsilateral sensing.",
    drives: { Left: "Left", Right: "Right" } },
  { key: "left_both", label: "Left sensing drives both",
    medtronic: "Left: ipsilateral sensing. Right: contralateral sensing (from Left).",
    drives: { Left: "Left", Right: "Left" } },
  { key: "right_both", label: "Right sensing drives both",
    medtronic: "Left: contralateral sensing (from Right). Right: ipsilateral sensing.",
    drives: { Left: "Right", Right: "Right" } },
];

export const wiringOf = (key) => WIRINGS.find((w) => w.key === key) || null;

/** The sides whose sensed band power this wiring reads: ["Left"], ["Right"] or both. */
export function sensedSides(key) {
  const w = wiringOf(key);
  return w ? [...new Set(Object.values(w.drives))].sort() : [];
}

/**
 * What stops this wiring being set up with the band(s) chosen; [] when nothing does.
 * `bandSides` is the list of sides a band has been chosen on.
 */
export function wiringProblems(key, bandSides) {
  const have = new Set(bandSides || []);
  return sensedSides(key).filter((s) => !have.has(s))
    .map((s) => `No band chosen on the ${s.toLowerCase()}: choose one in Band selection`);
}

/**
 * One entry per stimulator the decision answers for, in the order Left, Right:
 * `{ stim, source, kind }`, kind "own" (ipsilateral), "contralateral" (driven by the other side's
 * band) or "no_band" (its driving side has no band chosen). `bandSides` lists the sides with a band
 * chosen (Band selection takes one per side). With no wiring chosen, `pageSide` only (the side of
 * the band ticked last), as the page checked before the choice existed.
 */
export function controllers(key, bandSides, pageSide = null) {
  const have = new Set(typeof bandSides === "string" ? [bandSides] : (bandSides || []));
  const w = wiringOf(key);
  if (!w) {
    const own = pageSide || (have.size === 1 ? [...have][0] : null);
    return own && have.has(own) ? [{ stim: own, source: own, kind: "own" }] : [];
  }
  return ["Left", "Right"].map((stim) => {
    const source = w.drives[stim];
    if (!have.has(source)) return { stim, source, kind: "no_band" };
    return { stim, source, kind: source === stim ? "own" : "contralateral" };
  });
}
