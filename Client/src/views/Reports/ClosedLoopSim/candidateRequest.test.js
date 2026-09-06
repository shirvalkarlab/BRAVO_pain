import { candidateRequestParams } from "./candidateRequest";
import { commitBandCandidate, loadBandCandidate, clearBandCandidate, parseUploadedCandidate } from "./bandCandidateStore";

test("candidate handoff keeps analysis settings but never uploaded data or patient selectors", () => {
  const controls = candidateRequestParams({ label: { join: "pro_first", pro_metric: "nrs" } },
    { MaxPerRating: 2, ParticipantId: "other", ProcessedPRO: [1], PtConfig: "other", RedcapFieldMap: {}, LabelMetric: "vas" });
  expect(controls).toEqual({ MatchDirection: "pro_first", LabelMetric: "vas", MaxPerRating: 2 });
});
test("other-participant and unidentified uploads cannot become candidates", () => {
  const band_candidate = { contact: "ZERO_TWO_LEFT", center_freq_hz: 20 };
  expect(parseUploadedCandidate(JSON.stringify({ band_candidate, participant_uid: "other" }), "current")).toBeNull();
  expect(parseUploadedCandidate(JSON.stringify(band_candidate), "current")).toBeNull();
  expect(parseUploadedCandidate(JSON.stringify({ band_candidate, participant_uid: "current" }), "current").band_candidate).toEqual(band_candidate);
});
test("old persisted evidence is ignored while the temporary choice preserves provenance", () => {
  localStorage.setItem("bravo.bandCandidate.pt", JSON.stringify({ band_candidate: { stale: true } }));
  expect(loadBandCandidate("pt")).toBeNull();
  const fresh = commitBandCandidate("pt", { contact: "LEFT" }, { InputManifest: { fingerprint: "new" } });
  expect(loadBandCandidate("pt")).toEqual(fresh);
  expect(localStorage.getItem("bravo.bandCandidate.pt")).toBeNull();
  clearBandCandidate("pt");
  expect(loadBandCandidate("pt")).toBeNull();
});

test("candidate label provenance restores zero-valued cuts and all matching settings", () => {
  expect(candidateRequestParams({ label: {
    pro_metric: "nrs", join: "prior", match_tolerance_min: 0,
    binarization: { strategy: "percentile", low_pct: 0, high_pct: 100 },
  } })).toEqual({ LabelMetric: "nrs", MatchDirection: "prior", MatchToleranceMin: 0,
    LabelStrategy: "percentile", PercentileLow: 0, PercentileHigh: 100 });
});
test("absent provenance and malformed saved controls cannot manufacture request inputs", () => {
  expect(candidateRequestParams(null)).toEqual({});
  expect(candidateRequestParams({}, null)).toEqual({});
  expect(candidateRequestParams({}, { LabelMetric: { forged: "nrs" }, MaxPerRating: [3],
    PercentileLow: null, AllowWindowReuse: false, RefractoryMin: 0 })).toEqual({
    AllowWindowReuse: false, RefractoryMin: 0,
  });
});
