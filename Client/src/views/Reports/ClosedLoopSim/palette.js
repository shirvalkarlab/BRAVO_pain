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
  warn: OKABE_ITO.orange,        // soft caveat / degenerate operating point / underpowered (FILLS/AREA)
  fail: OKABE_ITO.vermillion,    // gate failed / hard stop
  neutral: OKABE_ITO.gray,       // chance line, "not estimable", baseline
  // Audit C6: #E69F00 as TEXT (or white-on-#E69F00) measures 2.25:1 — below WCAG AA (4.5) and
  // even large-text AA (3.0) — yet it carries the module's most safety-critical alerts (verdict
  // badge, degenerate-cutpoint callout, underpowered notice, "review caveats" sign-off line).
  // Reserve `warn` (#E69F00) for FILLS/AREA only; use `warnText` (a darkened amber, 5.5:1 on white)
  // for any warn-role TEXT, and dark `onWarn` text when sitting ON an orange fill (7.7:1).
  warnText: "#8A6100",           // WCAG-AA amber for small/critical warn text on white
  onWarn: "#1A1A1A",             // near-black text to place ON a #E69F00 fill
  indeterminate: OKABE_ITO.gray, // gate state: test did not run (absence of evidence, non-pass)

  // Cut-point marker on the ROC.
  cutpoint: OKABE_ITO.bluishGreen,
  cutpointDegenerate: OKABE_ITO.orange,

  // Feature-distribution histogram (pain-high vs pain-low) — blue↔vermillion, max CVD contrast.
  // Audit C7: overlaying two 0.62-opacity bars blends to a muddy purple-brown in the separation
  // zone (and is uninterpretable in grayscale). Render pain-low as a filled bar and pain-high as a
  // step OUTLINE so the two classes never blend into a phantom third category.
  painHigh: OKABE_ITO.vermillion,
  painLow: OKABE_ITO.blue,
  painHighOutline: OKABE_ITO.vermillion,
  thresholdLine: OKABE_ITO.black,

  // Light fills / borders for MUI boxes, derived from the roles above (hex + alpha suffix).
  accentFill: "#0072B215",
  accentBorder: "#0072B255",
  passFill: "#009E7315",
  passBorder: "#009E7344",
  warnFill: "#E69F0015",
  warnBorder: "#E69F0066",
  neutralFill: "#6C757D12",       // audit C10: recommended-vs-programmed Δ panel (neutral, non-alarm)
  neutralBorder: "#6C757D44",
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

// Audit C7/C10: a MINIMAL Plotly modebar so each figure is self-contained and exportable (the
// reviewer can save a PNG of the ROC / era forest / power curve to embed in the deployment record),
// without the clutter of the full bar. Keeps ONLY PNG export + zoom/pan/reset; strips the lasso,
// select, autoscale-duplicate, and the Plotly logo. `displayModeBar: "hover"` keeps it out of the way
// until the cursor is over the plot. Shared so every panel enables the identical bar.
//
// This config touches ONLY the toolbar chrome — it does NOT change how a figure is drawn or updated,
// so the imperative Plotly.react-once + restyle/relayout discipline (no rebuild on interaction) is
// fully preserved.
PAL.MODEBAR = {
  responsive: true,
  displaylogo: false,
  displayModeBar: "hover",
  modeBarButtonsToRemove: ["lasso2d", "select2d", "autoScale2d", "toggleSpikelines",
    "hoverClosestCartesian", "hoverCompareCartesian"],
  toImageButtonOptions: { format: "png", scale: 2 },
};

export default PAL;
