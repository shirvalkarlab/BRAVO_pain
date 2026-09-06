// These percentages describe amplitude position, not measured time at a state.
export function adaptiveParameters(note) {
  const adaptive = note?.Adaptive;
  const thresholds = adaptive?.RecordingConfiguration?.Config?.Thresholds;
  if (!thresholds) return {};
  let lfp = thresholds.LFPThresholds;
  if (Array.isArray(lfp) && typeof lfp[0] === "object") lfp = lfp[0]?.Value;
  const result = {};
  if (Array.isArray(lfp) && lfp.every(Number.isFinite)) {
    // Preserve BRAVO's existing suppression of the nominal default thresholds.
    if (lfp[0] !== 20 && lfp[1] !== 30) result.LFPThresholds = [...new Set(lfp)];
  }
  const limits = thresholds.AmplitudeThreshold;
  if (adaptive?.StimulationConfiguration?.Type === "Medtronic Adaptive" &&
      Array.isArray(limits) && limits.length === 2 && limits.every(Number.isFinite) &&
      limits[0] >= 0 && limits[1] > limits[0]) result.StimulationLimits = [...limits];
  return result;
}

export function amplitudeRangePercent(value, limits) {
  if (!Number.isFinite(value) || !limits || limits[1] <= limits[0]) return null;
  // Out-of-range samples cannot represent this programmed range; leave a gap.
  if (value < limits[0] || value > limits[1]) return null;
  return 100 * (value - limits[0]) / (limits[1] - limits[0]);
}
