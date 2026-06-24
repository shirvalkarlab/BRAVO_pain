/**
 * Shared colorblind-safe palette for the Closed-Loop Deployment module (Phase-2 viz pass).
 *
 * Hoisted out of the four panel files (DeploymentRocPanel / EraRefitPanel / LsbPowerPanel /
 * DeploySignoffCard), which each duplicated a handful of hardcoded hexes (#1A73E8, #0a7f3f,
 * #B17500, #9A3324, #6c757d) and — on the deploy-decision axis — paired green "pass" against red
 * "fail", which deuteranopic/protanopic viewers (~8% of men) cannot separate by hue.
 *
 * Built on the Okabe–Ito qualitative palette (Okabe & Ito 2008), whose eight inks are mutually
 * distinguishable under the common color-vision deficiencies. Semantic roles below pick from it so
 * that every pairing that carries meaning is CVD-safe:
 *   - DECISION axis: pass = bluish-green, warn = orange, fail = vermillion. Green is never paired
 *     with red; the green↔orange↔vermillion triad is separable for all CVD types. (Gate rows also
 *     carry a check/cancel ICON, so the encoding is redundant, not color-only.)
 *   - FEATURE classes (pain-high vs pain-low) and the per-class histogram use blue↔vermillion, the
 *     single most robust two-color contrast in the set.
 *   - STIM eras OFF/LOW/HIGH no longer reuse the primary accent for HIGH: OFF = neutral gray,
 *     LOW = orange, HIGH = vermillion (an intuitive low→high ramp), Pooled = the accent blue
 *     (it is the reference series).
 *
 * Import the SEMANTIC roles (PAL.pass, PAL.eraColor(tag), …) rather than raw hexes so the meaning,
 * not the color, is what the panels reference.
 */

// ---- Okabe–Ito qualitative palette (raw tokens) ----
export const OKABE_ITO = {
  black: "#000000",
  orange: "#E69F00",
  skyBlue: "#56B4E9",
  bluishGreen: "#009E73",
  yellow: "#F0E442",
  blue: "#0072B2",
  vermillion: "#D55E00",
  reddishPurple: "#CC79A7",
  gray: "#6C757D", // not an Okabe–Ito ink, but CVD-neutral; reserved for "off / baseline / chance"
};

// ---- Semantic roles (what panels should reference) ----
export const PAL = {
  // Primary "ink" for the main data series (ROC curve, power curve, threshold headline).
  accent: OKABE_ITO.blue,

  // Deploy-decision axis — NO red/green pairing.
  pass: OKABE_ITO.bluishGreen,   // gate passed / sufficient / non-degenerate cut-point
  warn: OKABE_ITO.orange,        // soft caveat / degenerate operating point / underpowered
  fail: OKABE_ITO.vermillion,    // gate failed / hard stop
  neutral: OKABE_ITO.gray,       // chance line, "not estimable", baseline

  // Cut-point marker on the ROC.
  cutpoint: OKABE_ITO.bluishGreen,
  cutpointDegenerate: OKABE_ITO.orange,

  // Feature-distribution histogram (pain-high vs pain-low) — blue↔vermillion, max CVD contrast.
  painHigh: OKABE_ITO.vermillion,
  painLow: OKABE_ITO.blue,
  thresholdLine: OKABE_ITO.black,

  // Light fills / borders for MUI boxes, derived from the roles above (hex + alpha suffix).
  accentFill: "#0072B215",
  accentBorder: "#0072B255",
  passFill: "#009E7315",
  warnFill: "#E69F0015",
  warnBorder: "#E69F0066",
};

// Per-era color for the stim-state forest plot + cards. Pooled = accent (it is the reference).
const ERA_COLORS = {
  OFF: OKABE_ITO.gray,
  LOW: OKABE_ITO.orange,
  HIGH: OKABE_ITO.vermillion,
  Pooled: OKABE_ITO.blue,
};
PAL.eraColor = (tag) => ERA_COLORS[tag] || OKABE_ITO.black;
PAL.ERA_COLORS = ERA_COLORS;

export default PAL;
