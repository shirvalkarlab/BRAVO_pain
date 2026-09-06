/** Carry only analysis controls; candidate evidence or alternate patient data never enter a request. */
const ALLOWED = ["LabelMetric", "LabelStrategy", "PercentileLow", "PercentileHigh",
  "MatchToleranceMin", "MatchExtentSec", "MaxPerRating", "RefractoryMin", "MatchDirection",
  "AllowWindowReuse", "SlidingWindow", "TrainMonths", "TestMonths", "GapMonths"];

export function candidateRequestParams(bc, saved = {}) {
  const lbl = (bc && bc.label) || {};
  const bin = lbl.binarization || {};
  const params = {};
  if (lbl.pro_metric) params.LabelMetric = lbl.pro_metric;
  if (bin.strategy) params.LabelStrategy = bin.strategy;
  if (bin.low_pct != null) params.PercentileLow = bin.low_pct;
  if (bin.high_pct != null) params.PercentileHigh = bin.high_pct;
  if (lbl.match_tolerance_min != null) params.MatchToleranceMin = lbl.match_tolerance_min;
  if (lbl.join) params.MatchDirection = lbl.join;
  for (const key of ALLOWED) {
    if (saved && saved[key] != null && ["string", "number", "boolean"].includes(typeof saved[key])) {
      params[key] = saved[key];
    }
  }
  return params;
}
