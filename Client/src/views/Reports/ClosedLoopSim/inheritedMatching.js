/**
 * THE MATCHING SETTINGS THE CLOSED-LOOP PAGE INHERITS FROM THE BIOMARKERS PAGE (decision 331; the
 * PI, 2026-09-26: "the Closed-loop page should inherit what was most recently run on the Biomarkers
 * page regarding matching settings").
 *
 * ONE SOURCE: the Biomarkers page's saved controls in this browser
 * (`Biomarkers/biomarkerStateStore.loadMatchingRun`), which record the settings of its last run --
 * a Recompute, or a heat-map grid it built and showed as current. Before this, the Closed-Loop
 * page read the "Choose a band" grid's settings from the Biomarkers page's last COMPUTED request
 * (decision 131), which since 2026-09-26 carries no clinic-sheet switch, so the card asked for the
 * sheets-off grid whatever the Biomarkers page showed; and the deployment summary and the stability
 * card used the server's defaults (60 minutes) whatever the Biomarkers page ran.
 *
 * WHERE EACH SETTING GOES, and what takes none:
 *  - the "Choose a band" grid: the pain score, the window, the direction, reuse, the clinic-sheet
 *    switch and the split (every setting the heat maps read);
 *  - the report (`/api/queryClosedLoopDeployment`): the window, direction, cap, gap, reuse, switch
 *    and split, for the stability card, the one reading in it that matches reports to recordings.
 *    E1 to E3 join the ratings per settings period and take no window; the pain score is the page's
 *    own dropdown (decision 292), not inherited;
 *  - the deployment summary and the panels sharing its request (the ROC, the device-units panel,
 *    the per-block refit): the window, cap, gap, reuse, switch and split. NOT the direction: those
 *    panels read the band power BEFORE a report by default ("prior", the ROC's own toggle), because
 *    the question they answer is whether the device could act on it in time;
 *  - the CL-DBS simulation reads no pain report, so it takes none.
 */
import { loadMatchingRun } from "views/Reports/Biomarkers/biomarkerStateStore";
import { painScoreLabel } from "views/Reports/painScores";

/** Every matching and split request key, as the Biomarkers routines read them. */
export const MATCHING_KEYS = ["MatchToleranceMin", "MatchDirection", "AllowWindowReuse",
  "MaxPerRating", "RefractoryMin", "IncludeClinicSheetRatings", "LabelStrategy", "PercentileLow",
  "PercentileHigh"];
/** The keys the deployment summary takes: all but the direction (see above). */
export const SUMMARY_MATCHING_KEYS = MATCHING_KEYS.filter((k) => k !== "MatchDirection");

/** `{settings, ranAt, source}` for this participant (see `loadMatchingRun`). */
export function inheritedMatching(participantUid) {
  return loadMatchingRun(participantUid);
}

/** The inherited settings under `keys`, as request keys; booleans as "1" / "" like the pages. */
export function matchingRequestKeys(inherited, keys = MATCHING_KEYS) {
  const s = (inherited && inherited.settings) || {};
  const out = {};
  keys.forEach((k) => {
    if (s[k] === undefined || s[k] === null) return;
    out[k] = typeof s[k] === "boolean" ? (s[k] ? "1" : "") : s[k];
  });
  return out;
}

const DIRECTION_WORDS = { nearest: "nearest", pro_first: "report picks nearest", prior: "next report" };
const SPLIT_WORDS = { tertile: "tertile split", median: "median split", kmeans: "2-cluster split" };
const truthy = (v) => v === true || ["1", "true", "yes", "on"].includes(String(v).toLowerCase());

/** The one line the page prints: which settings it inherited (terse, 2026-10-02: the PI wants
 *  minimal words; the run's time is in the head). */
export function inheritedMatchingLine(inherited) {
  const s = (inherited && inherited.settings) || {};
  const tol = Number(s.MatchToleranceMin);
  const parts = [
    Number.isFinite(tol) && tol > 0 ? `±${tol} min` : "no window",
    DIRECTION_WORDS[s.MatchDirection] || String(s.MatchDirection || ""),
    `≤${s.MaxPerRating} per report, ${s.RefractoryMin} min apart`,
    truthy(s.AllowWindowReuse) ? "reuse" : "no reuse",
    truthy(s.IncludeClinicSheetRatings) ? "clinic sheets in" : "clinic sheets out",
    s.LabelStrategy === "percentile"
      ? `split ${Number(Number(s.PercentileLow).toFixed(1))}/${Number(Number(s.PercentileHigh).toFixed(1))} percentiles`
      : (SPLIT_WORDS[s.LabelStrategy] || String(s.LabelStrategy || "")),
    painScoreLabel(s.LabelMetric),
  ];
  const src = inherited && inherited.source;
  const when = inherited && inherited.ranAt
    ? new Date(inherited.ranAt).toISOString().slice(0, 16).replace("T", " ") + " UTC" : null;
  const head = src === "defaults" ? "Matching, defaults"
    : `Matching from Biomarkers${when ? `, ${when}` : ""}`;
  return `${head}: ${parts.join(", ")}.`;
}

/** The settings a result says it was computed under, in request keys, from its echo: the report's
 *  `matching`, the summary's `identity.matching`. Null when it carries none (an older answer). */
export function echoedMatching(data, kind = "report") {
  const m = kind === "summary" ? data && data.identity && data.identity.matching
    : data && data.matching;
  if (!m) return null;
  return {
    MatchToleranceMin: m.match_tolerance_min, MatchDirection: m.match_direction,
    AllowWindowReuse: m.allow_window_reuse, MaxPerRating: m.max_per_rating,
    RefractoryMin: m.refractory_min, IncludeClinicSheetRatings: m.include_clinic_sheet_ratings,
    LabelStrategy: m.label_strategy, PercentileLow: m.percentile_low,
    PercentileHigh: m.percentile_high,
  };
}

const KEY_WORDS = {
  MatchToleranceMin: "match window", MatchDirection: "match direction",
  AllowWindowReuse: "reuse setting", MaxPerRating: "cap per report",
  RefractoryMin: "minimum gap", IncludeClinicSheetRatings: "clinic-sheet setting",
  LabelStrategy: "high / low split", PercentileLow: "low cut", PercentileHigh: "high cut",
};

const sameValue = (key, a, b) => {
  if (key === "AllowWindowReuse" || key === "IncludeClinicSheetRatings") return truthy(a) === truthy(b);
  if (typeof a === "number" || typeof b === "number" || !Number.isNaN(Number(a))) {
    return Math.abs(Number(a) - Number(b)) < 1e-9;
  }
  return String(a) === String(b);
};

/** `{what, chosen, computedFor}` for the first inherited setting a result was computed under
 *  another value of, or null (also when the result echoes nothing). */
export function matchingMismatch(data, wanted, kind = "report", keys = MATCHING_KEYS) {
  const got = echoedMatching(data, kind);
  if (!got || !wanted) return null;
  for (let i = 0; i < keys.length; i += 1) {
    const k = keys[i];
    if (wanted[k] === undefined || got[k] === undefined || got[k] === null) continue;
    if (!sameValue(k, wanted[k], got[k])) {
      return { what: KEY_WORDS[k] || k, chosen: String(wanted[k]), computedFor: String(got[k]) };
    }
  }
  return null;
}
