/**
 * THE PAIN SCORES A BAND CAN BE READ AGAINST, one list for the Biomarkers heat maps and the
 * Closed-Loop page (the PI, 2026-09-25 night: nothing on the Closed-Loop page is computed on NRS
 * alone, and its dropdown offers the heat maps' own choices).
 *
 * The server's list is the authority: `Biomarkers/routines/sweep_settings.BIOMARKER_METRICS`, sent
 * as `available_metrics` on the heat-map responses. This is the page's copy for before a response
 * has arrived, and a jest test pins it to the server's list, key for key and label for label.
 */
export const PAIN_SCORE_OPTIONS = [
  { key: "nrs", label: "NRS (0–10)" },
  { key: "vas", label: "Overall VAS" },
  { key: "left_leg_vas", label: "Left Leg VAS" },
  { key: "back_vas", label: "Back VAS" },
  { key: "mpq_sum", label: "MPQ Sum" },
  { key: "composite_mpq_leftleg", label: "Composite (MPQ + Left Leg VAS)" },
];

export const DEFAULT_PAIN_SCORE = "nrs";

/** The label a reader sees for a pain-score key; the key itself when it is not on the list. */
export function painScoreLabel(key, options = PAIN_SCORE_OPTIONS) {
  const hit = (options || PAIN_SCORE_OPTIONS).find((m) => m.key === key);
  return hit ? hit.label : String(key || "");
}
