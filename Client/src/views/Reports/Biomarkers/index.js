/**
=========================================================
* UF BRAVO Platform -- Pain Biomarkers report (Shirvalkar Lab)
=========================================================
* Renders the selectable-source biomarker timeline (time-domain PSD<->pain and/or the
* power-domain ~10-min LFP threshold detector) returned by /api/queryBiomarkerAnalysis.
*/

import { useEffect, useMemo, useState, useRef } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { Card, Grid, Select, MenuItem, FormControl,
  Slider, LinearProgress, CircularProgress,
  ToggleButton, ToggleButtonGroup } from "@mui/material";

import MDBox from "components/MDBox";
import MDTypography from "components/MDTypography";
import MDButton from "components/MDButton";

import BiomarkerTimeline from "./BiomarkerTimeline";
import BiomarkerDataTimeline from "./BiomarkerDataTimeline";
import BiomarkerAnalytics from "./BiomarkerAnalytics";
import BinarizationPreview from "./BinarizationPreview";
import { computeMatchedScanModel } from "./binarizationModel";
import {
  saveControls, loadControls, putHeavy, getHeavy, underMemoryPressure, memoryInfo,
} from "./biomarkerStateStore";

import DatabaseLayout from "layouts/DatabaseLayout";

import { SessionController } from "database/session-control";
import { usePlatformContext, setContextState } from "context.js";

// Pain metric the LFP biomarker is computed against (sent as LabelMetric). Used until the server
// echoes its own `available_metrics` list. The composite blends MPQ sum + left-leg VAS.
const DEFAULT_METRIC_OPTIONS = [
  { key: "nrs", label: "NRS (0–10)" },
  { key: "vas", label: "Overall VAS" },
  { key: "left_leg_vas", label: "Left Leg VAS" },
  { key: "back_vas", label: "Back VAS" },
  { key: "mpq_sum", label: "MPQ Sum" },
  { key: "composite_mpq_leftleg", label: "Composite (MPQ + Left Leg VAS)" },
];

// How the continuous pain score is turned into the binary high/low pain_level the detector trains
// on (sent as LabelStrategy). "tertile" (default) splits low/high and drops the ambiguous middle —
// the cleanest detector target on RCS08; "median" keeps every day at a 50/50 split; "kmeans" is the
// legacy 2-cluster notebook labeler. The cut is computed on the DAILY PRO distribution and
// broadcast to samples, so recording density no longer biases the split.
// See docs/binarization_recommendation_RCS08.md.
const DEFAULT_STRATEGY_OPTIONS = [
  { key: "tertile", label: "Tertile (low/high, drop middle)" },
  { key: "percentile", label: "Percentile (adjustable cuts)" },
  { key: "median", label: "Median split" },
  { key: "kmeans", label: "KMeans (legacy)" },
];

// Debounce a fast-changing value for the EXPENSIVE live recompute. Dragging any of the matching
// sliders fires onChange on every pixel; the matched-scan rematch and the timeline's Plotly redraw
// are both costly, so re-running them on every intermediate value makes the sliders and plot lag.
// The raw slider state still updates instantly (responsive thumbs, value labels, captions, and the
// binarization cut-lines), but a debounced copy is what drives the heavy scanModel / timeline
// overlay, so that work runs once the drag settles (~delay ms) instead of dozens of times mid-drag.
function useDebounced(value, delay = 250) {
  const [debounced, setDebounced] = useState(value);
  const timer = useRef(null);
  useEffect(() => {
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => setDebounced(value), delay);
    return () => { if (timer.current) clearTimeout(timer.current); };
  }, [value, delay]);
  return debounced;
}

function Biomarkers() {
  const navigate = useNavigate();
  const [controller, dispatch] = usePlatformContext();
  const { language } = controller;
  const { participant_uid } = useParams();

  // Persisted controls for THIS participant (localStorage), read once so the state defaults below
  // restore the exact panel config the user left when they navigated to the deployment view. null
  // on first-ever visit -> the documented defaults apply. The heavy ~19 MB result is restored
  // separately from the in-memory cache (see the hydration effect), never from localStorage.
  const persisted = useMemo(() => loadControls(participant_uid), [participant_uid]);
  const P = persisted || {};

  // The heavy result is restored from the module-level LRU cache (survives route unmount/mount).
  // If a fresh cached bundle exists for this participant, seed `data` with it on the very first
  // render so the page paints the full analysis immediately instead of the loading view.
  const cachedHeavy = useMemo(() => getHeavy(participant_uid), [participant_uid]);
  const [data, setData] = useState((cachedHeavy && cachedHeavy.bundle) || false);
  // Source tabs (time-domain / power-domain / both) removed — the analysis is always unified
  // (time-domain streaming PSD + power-domain band power together). One code path, no tab.
  const source = "both";
  const [metric, setMetric] = useState(P.metric || "nrs");
  const [strategy, setStrategy] = useState(P.strategy || "tertile");   // binarization labeler (default tertile)
  const [percentileLow, setPercentileLow] = useState(P.percentileLow != null ? P.percentileLow : 33.3);   // tertile/percentile low cut
  const [percentileHigh, setPercentileHigh] = useState(P.percentileHigh != null ? P.percentileHigh : 66.7);  // tertile/percentile high cut
  // PRO<->PSD match window (minutes): a streaming/PSD session is matched to the nearest pain
  // report whose timestamp falls within ± this many minutes. Drives the matched-neural-sample
  // counts (computed on the PSDs by the backend) and is a compute param, so changing it makes the
  // view dirty (a recompute re-matches). Exploratory — default 15 min.
  // Match window for PSD<->PRO pairing. Bumped from 15 to 60 min after the matching audit on RCS08:
  // pain reports anchor neural data on a minutes-to-hours timescale, and the 15-min window dropped
  // ~80% of the otherwise-usable PSDs. Combined with the new direction='pro_first' default, this
  // lifts PRO coverage to 290/682 (42.5%) of the matched discovery pool (measured on RCS08, vas,
  // pro_first, ±60 min — matching the offline validation pool; see FIXHANDOUT_pro_timezone_mismatch).
  const [matchTolerance, setMatchTolerance] = useState(P.matchTolerance != null ? P.matchTolerance : 60);
  // Per-rating CAP for the exploratory scan (replaces the old all-vs-one-per-rating toggle, which
  // it subsumes): how many PSDs a single pain rating may absorb PER CHANNEL, and the refractory gap
  // (minutes) enforced among the kept set so a streaming burst around one survey can't double-count.
  //   maxPerRating = 1  -> one PSD per rating (the old "one per rating": maximally independent)
  //   maxPerRating > 1  -> up to N nearest-prior PSDs per rating; AUC stays rating-grouped on top.
  // Matching is PRIOR-only (forecasting): each rating is paired with PSDs recorded BEFORE it.
  const [maxPerRating, setMaxPerRating] = useState(P.maxPerRating != null ? P.maxPerRating : 3);
  const [refractoryMin, setRefractoryMin] = useState(P.refractoryMin != null ? P.refractoryMin : 2);
  // Match direction: "prior" (forecasting — PSD must precede the rating) vs "nearest" (symmetric ±
  // tolerance; pairs the closest PSD in either time direction). Default "prior".
  // Match direction: pro_first (default for discovery) walks PROs and claims up to max_per_rating
  // PSDs per channel each within tolerance, maximizing PRO coverage (each PRO is an independent
  // observation, so this is the right framing for discovery). 'nearest' is PSD-first symmetric.
  // 'prior' is PSD-first forecasting (PSD must precede the PRO), kept for the threshold-deployment
  // view where causal direction is the right semantics.
  const [matchDirection, setMatchDirection] = useState(P.matchDirection || "pro_first");
  // Timeline color mode: "multimodal" colors the neural lanes by sensing center frequency (the data
  // view); "binarization" recolors every modality LIVE by its high/low/excluded pain label at the
  // current match window (matched-and-included = vermillion/blue, everything else dimmed light grey),
  // so the user sees exactly which samples feed the binarized biomarker. Toggle sits on the timeline.
  const [timelineColorMode, setTimelineColorMode] = useState(P.timelineColorMode || "multimodal");
  const slidingWindow = false;   // sliding-window analysis removed — always all-data, one threshold
  // The biomarker is EXPENSIVE (full-resolution detector over ~300k rows), so it is computed only
  // when the user clicks "Compute biomarker now" — never automatically on a settings change. This
  // holds the snapshot of options actually computed; the fetch effect runs only when it changes.
  // Restore the last-computed requestParams so a return visit isn't "dirty" and the results show
  // without re-clicking Compute. If the in-memory heavy cache is fresh we already seeded `data`, so
  // the fetch effect short-circuits (cache hit); otherwise this drives the auto-recompute.
  const [requestParams, setRequestParams] = useState(
    (persisted && persisted.requestParams) || null);
  const [computing, setComputing] = useState(false);
  const [alert, setAlert] = useState(null);

  // Raw pain-score distribution for the LIVE binarization preview card. Fetched once per
  // participant (lightweight — daily PRO survey rows only, no LFP); the card recomputes the
  // high/low cuts client-side as the user changes strategy or drags the percentile sliders,
  // so no /queryBiomarkerAnalysis roundtrip is needed for the preview.
  const [painScores, setPainScores] = useState(null);
  const [painLoading, setPainLoading] = useState(false);

  // ALWAYS-ON data-availability timeline. This is for visualization/exploration and must show on
  // page load WITHOUT requiring "Compute biomarker now" — so it has its own lightweight endpoint
  // (/queryDataAvailability assembles records/pain/stim/freq_bands with NO biomarker computation),
  // fetched once per participant. The heavy compute still returns its own availability payload;
  // we prefer the live one here so the timeline is populated before (and independent of) compute.
  const [availData, setAvailData] = useState(null);
  const [availLoading, setAvailLoading] = useState(false);

  const snapshot = () => ({
    source, LabelMetric: metric, LabelStrategy: strategy,
    PercentileLow: percentileLow, PercentileHigh: percentileHigh,
    MatchToleranceMin: matchTolerance,
    MaxPerRating: maxPerRating,
    RefractoryMin: refractoryMin,
    MatchDirection: matchDirection,
    SlidingWindow: slidingWindow,
  });
  const compute = () => setRequestParams(snapshot());
  // "Dirty" = the live options differ from what's currently displayed (or nothing computed yet),
  // so the shown results are stale and a (re)compute is needed.
  const dirty = !requestParams || JSON.stringify(requestParams) !== JSON.stringify(snapshot());

  useEffect(() => {
    if (!participant_uid) {
      navigate("/database", { replace: false });
      return;
    }
    setContextState(dispatch, "report", "CustomizedAnalysis");
  }, [participant_uid]);

  // Fetch ONLY when a compute was requested (requestParams set by the Compute button). Progress is
  // shown INLINE (a labeled bar in the card) instead of the generic "loading data" overlay.
  useEffect(() => {
    if (!participant_uid || !requestParams) return undefined;
    const requestKey = JSON.stringify(requestParams);

    // CACHE HIT: the in-memory LRU holds the heavy result for THIS exact requestParams (e.g. we just
    // came back from the deployment view). Restore it with zero recompute — instant, identical view.
    const cached = getHeavy(participant_uid);
    if (cached && cached.request_key === requestKey) {
      setData((prev) => (prev === cached.bundle ? prev : cached.bundle));
      setComputing(false);
      return undefined;
    }

    // CACHE MISS: compute (or recompute after a controls change / hard reload). The backend caches
    // the PSD inputs, so even the ~19 MB analysis returns quickly on a return visit.
    let cancelled = false;
    setComputing(true);
    SessionController.query("/api/queryBiomarkerAnalysis", {
      ParticipantId: participant_uid, ...requestParams,
    }).then((response) => {
      if (cancelled) return;
      setData(response.data);
      setComputing(false);
      // Stash in the heap cache (memory-guarded — declines under pressure) so the next return is
      // instant. Persist the controls+requestParams so a hard reload restores the view too.
      putHeavy(participant_uid, response.data, requestKey);
    }).catch((error) => {
      if (cancelled) return;
      setComputing(false);
      SessionController.displayError(error, setAlert);
    });
    return () => { cancelled = true; };
  }, [participant_uid, requestParams]);

  // Persist the lightweight control panel + the last-computed requestParams to localStorage whenever
  // they change, so navigating to the deployment view and back (or a hard reload) restores the exact
  // view config. This is the small, always-safe layer; the heavy result rides the in-memory cache.
  useEffect(() => {
    if (!participant_uid) return;
    saveControls(participant_uid, {
      metric, strategy, percentileLow, percentileHigh, matchTolerance,
      maxPerRating, refractoryMin, matchDirection, timelineColorMode, requestParams,
    });
  }, [participant_uid, metric, strategy, percentileLow, percentileHigh, matchTolerance,
    maxPerRating, refractoryMin, matchDirection, timelineColorMode, requestParams]);

  // Fetch raw pain-score reports ONCE per participant (no LFP, just the PRO surveys) so the
  // binarization preview card can show a live histogram with cuts before any heavy compute.
  useEffect(() => {
    if (!participant_uid) return;
    setPainLoading(true);
    SessionController.query("/api/queryPainScores", { ParticipantId: participant_uid })
      .then((response) => {
        setPainScores(response.data);
        setPainLoading(false);
      })
      .catch(() => { setPainLoading(false); /* preview is optional — degrade silently */ });
  }, [participant_uid]);

  // Fetch the data-availability payload ONCE per participant (lightweight, no biomarker compute),
  // so the timeline renders immediately on page load.
  useEffect(() => {
    if (!participant_uid) return;
    setAvailLoading(true);
    SessionController.query("/api/queryDataAvailability", { ParticipantId: participant_uid })
      .then((response) => {
        setAvailData(response.data);
        setAvailLoading(false);
      })
      .catch(() => { setAvailLoading(false); /* timeline is optional — degrade silently */ });
  }, [participant_uid]);

  // The object handed to the timeline: prefer the live availability payload; fall back to the
  // availability embedded in a heavy compute result if the live fetch is unavailable.
  const timelineData = (availData && availData.availability && availData.availability.records
    && availData.availability.records.length > 0)
    ? availData
    : data;

  // The points array for the currently-selected pain metric, fed straight into the preview card.
  // The composite metric ("composite_mpq_leftleg") is NOT a raw PRO column returned by
  // /queryPainScores; it is synthesized here exactly as the backend does — the per-day average of
  // z(MPQ-sum) and z(left-leg-VAS) across all surveys, keeping a day when either part exists.
  const previewPoints = (() => {
    if (!painScores || !Array.isArray(painScores.metrics)) return [];
    if (metric === "composite_mpq_leftleg") {
      const get = (k) => {
        const m = painScores.metrics.find((x) => x.key === k);
        return m ? m.points : [];
      };
      const zStats = (pts) => {
        const vs = pts.map((p) => p.v).filter((v) => v != null && Number.isFinite(v));
        if (vs.length < 2) return null;
        const mu = vs.reduce((s, v) => s + v, 0) / vs.length;
        const sd = Math.sqrt(vs.reduce((s, v) => s + (v - mu) ** 2, 0) / vs.length) || 1;
        return { mu, sd };
      };
      const mpq = get("mpq_sum"), leg = get("left_leg_vas");
      const sM = zStats(mpq), sL = zStats(leg);
      if (!sM && !sL) return [];
      // Index each part's z-score by timestamp, then average the available parts per day.
      const zByT = {};
      const add = (pts, st, slot) => {
        if (!st) return;
        pts.forEach((p) => {
          if (p.v == null || !Number.isFinite(p.v)) return;
          const key = String(p.t);
          const e = (zByT[key] = zByT[key] || {});
          e[slot] = (p.v - st.mu) / st.sd;
          // Preserve the numeric epoch so the composite series matches in UTC like the raw metrics.
          if (Number.isFinite(p.t_epoch)) e.t_epoch = p.t_epoch;
        });
      };
      add(mpq, sM, "m"); add(leg, sL, "l");
      return Object.keys(zByT).sort().map((t) => {
        const z = zByT[t];
        const parts = [z.m, z.l].filter((v) => v != null && Number.isFinite(v));
        return parts.length
          ? { t, t_epoch: z.t_epoch, v: parts.reduce((s, v) => s + v, 0) / parts.length }
          : null;
      }).filter(Boolean);
    }
    const m = painScores.metrics.find((x) => x.key === metric);
    return m ? m.points : [];
  })();
  const previewMetricLabel = (((data && data.available_metrics) || DEFAULT_METRIC_OPTIONS)
    .find((m) => m.key === metric) || {}).label || metric;

  // Live pain series for the timeline's pain row, in the {metric, t:[epoch_s], y:[]} shape the
  // BiomarkerDataTimeline expects. Built from the lightweight previewPoints (fetched once per
  // participant) so changing the metric updates the pain plot INSTANTLY — no recompute. previewPoints
  // carry `t` as a timestamp string and `v` as the value; convert to epoch seconds.
  // Memoized so its object identity is STABLE across re-renders that don't touch its inputs (e.g.
  // dragging the tertile sliders, which changes binarization but not the pain row). A new identity
  // would re-run the timeline's Plotly effect and reset the page scroll, so only recompute when the
  // metric or the underlying preview points actually change.
  const painSeriesLive = useMemo(() => {
    if (!previewPoints || !previewPoints.length) return null;
    // Use the backend's numeric `t_epoch` (UTC seconds) when present — NOT Date.parse(p.t). The
    // backend pain timestamps are tz-naive UTC strings; Date.parse re-reads them in the BROWSER's
    // local zone, shifting every rating 7-8 h and dropping ~3/4 of the otherwise-matchable PROs off
    // the PSDs (the "61/682 instead of 290/682" symptom). t_epoch is zone-independent. Fall back to
    // Date.parse only for older payloads that predate t_epoch.
    const epochOf = (p) => (Number.isFinite(p.t_epoch) ? p.t_epoch : Date.parse(p.t) / 1000);
    const pairs = previewPoints
      .map((p) => [epochOf(p), p.v])
      .filter(([t, v]) => Number.isFinite(t) && v != null && Number.isFinite(v))
      .sort((a, b) => a[0] - b[0]);
    return { metric, t: pairs.map((p) => p[0]), y: pairs.map((p) => p[1]) };
  }, [previewPoints, metric]);

  // LIVE matched-scan model: replicate the backend's nearest-PRO match + binarization over the
  // PSDs the exploratory scan pools (availability.psd_scan_index), at the CURRENT match window /
  // metric / strategy — no recompute. This single object feeds BOTH the binarization-preview
  // histogram (which neural data is available to binarize, updating as the slider moves) AND the
  // timeline's binarization color overlay. Counts are verified identical to the backend
  // `matched_sample_counts`. Memoized so dragging an unrelated control doesn't rebuild it.
  const scanIndex = (timelineData && timelineData.availability && timelineData.availability.psd_scan_index)
    || (data && data.availability && data.availability.psd_scan_index) || null;
  // Debounced copies of every slider-driven input to the heavy matched-scan recompute. The raw
  // states stay live everywhere else (slider thumbs, value labels, the binarization preview's
  // cut-lines and counts); only the expensive scanModel + timeline overlay wait for the drag to
  // settle, so all of these sliders now feel as snappy as the survey-match one.
  const matchToleranceD = useDebounced(matchTolerance);
  const percentileLowD = useDebounced(percentileLow);
  const percentileHighD = useDebounced(percentileHigh);
  const maxPerRatingD = useDebounced(maxPerRating);
  const refractoryMinD = useDebounced(refractoryMin);
  const scanModel = useMemo(() => {
    if (!scanIndex || !painSeriesLive) return null;
    return computeMatchedScanModel({
      scanIndex, painSeries: painSeriesLive, toleranceMin: matchToleranceD,
      strategy, percentileLow: percentileLowD, percentileHigh: percentileHighD,
      maxPerRating: maxPerRatingD, refractoryMin: refractoryMinD, matchDirection,
    });
  }, [scanIndex, painSeriesLive, matchToleranceD, strategy, percentileLowD, percentileHighD,
      maxPerRatingD, refractoryMinD, matchDirection]);

  // Render an honest, multi-line summary for a branch: the headline estimate plus the rigor
  // statistics (FDR q, permutation p, autocorrelation-adjusted effective n, Fisher-z CI for the
  // time domain; balanced accuracy vs chance + AUC for the power domain) and any caveats.
  // [removed] summaryLine() — the legacy Time-/Power-domain dual-pipeline prose summary it
  // generated was replaced by the concise per-channel matched-sample + TD/PSD-LSB summary
  // rendered inline below the Recompute button (see the spectral_feature_importance block).

  return (
    <>
      {alert}
      <DatabaseLayout>
        <MDBox pt={3}>
          <Grid container spacing={2}>
            <Grid item xs={12}>
              <Card sx={{ width: "100%" }}>
                <Grid container>
                  {/* Title row (source tabs removed — analysis is always unified time + power) */}
                  <Grid item xs={12}>
                    <MDBox px={2} pt={2} pb={1} display="flex" flexDirection="row" justifyContent="space-between" alignItems="center" flexWrap="wrap" gap={2}>
                      <MDTypography variant="h5" fontSize={28} fontWeight="bold">
                        {"Pain Biomarker Exploration"}
                      </MDTypography>
                    </MDBox>
                  </Grid>

                  {/* ── DATA-AVAILABILITY TIMELINE up front (ALWAYS shown) ────────────────────
                      For visualization/exploration: rendered on page load from the lightweight
                      /queryDataAvailability payload (timelineData), with NO "Compute biomarker
                      now" required. The pain row is driven LIVE by the selected metric
                      (painSeriesLive) so it updates instantly when the metric picker below
                      changes. Falls back to the legacy timeline only if no availability payload
                      is available at all. The Compute button lives BELOW this. */}
                  {timelineData && timelineData.availability && timelineData.availability.records
                        && timelineData.availability.records.length > 0 ? (
                    <Grid item xs={12}>
                      <BiomarkerDataTimeline data={timelineData} painOverride={painSeriesLive}
                        scanModel={scanModel} colorMode={timelineColorMode}
                        setColorMode={setTimelineColorMode} />
                    </Grid>
                  ) : (timelineData && timelineData.timeline && timelineData.timeline.length > 0 ? (
                    <Grid item xs={12}>
                      <BiomarkerTimeline data={timelineData} figureTitle={"BiomarkerTimeline"} />
                    </Grid>
                  ) : (
                    <Grid item xs={12}>
                      <MDBox px={2} pb={1.5}>
                        <MDTypography variant="button" color="text" fontStyle="italic">
                          {availLoading ? "Loading data-availability timeline…"
                                        : "No decoded Percept recordings available for this participant yet."}
                        </MDTypography>
                      </MDBox>
                    </Grid>
                  ))}

                  {/* Pain-metric picker DIRECTLY BELOW the timeline — drives the pain row live. */}
                  {timelineData && timelineData.availability && timelineData.availability.records
                        && timelineData.availability.records.length > 0 ? (
                    <Grid item xs={12}>
                      <MDBox px={2} pb={1.5} display="flex" flexDirection="row" alignItems="center"
                             gap={2} flexWrap="wrap" justifyContent="center">
                        <MDTypography variant="button" fontWeight="bold"
                                      sx={{ fontSize: 18, color: "#1a1a1a !important" }}>
                          {"Pain metric (drives live timeline + exploratory analysis):"}
                        </MDTypography>
                        <FormControl size="small" sx={{ minWidth: 420 }}>
                          <Select value={metric} onChange={(e) => setMetric(e.target.value)}
                                  sx={{
                                    // Enlarge ONLY the closed / displayed selected value. A plain
                                    // fontSize on <Select> lands on .MuiInputBase-root and does NOT
                                    // resize the rendered value — that text is the inner
                                    // .MuiSelect-select slot, so target it directly. !important beats
                                    // MUI's own .MuiInputBase-input rule (equal specificity otherwise).
                                    "& .MuiSelect-select": {
                                      fontSize: "18px !important",  // matches the open-menu items
                                      fontWeight: 700,
                                      lineHeight: 1.2,
                                      color: "#1a1a1a !important",  // ink (red is reserved for errors/warnings)
                                    },
                                  }}>
                            {((timelineData && timelineData.available_metrics)
                               || (data && data.available_metrics) || DEFAULT_METRIC_OPTIONS).map((m) => (
                              <MenuItem key={m.key} value={m.key} sx={{ fontSize: 18 }}>{m.label}</MenuItem>
                            ))}
                          </Select>
                        </FormControl>
                      </MDBox>
                    </Grid>
                  ) : null}

                  {computing ? (
                    <Grid item xs={12}>
                      <MDBox px={2} pb={1}>
                        <MDTypography variant="button" fontWeight="medium" color="dark" display="block" mb={0.5}>
                          {"Computing time-domain + power-domain biomarker on full-resolution data — this can take ~10–40 s…"}
                        </MDTypography>
                        <LinearProgress color="error" />
                      </MDBox>
                    </Grid>
                  ) : null}

                  {/* Controls row: LEFT box = pain metric + binarization selector + sliders
                                   RIGHT box = live binarization preview histogram
                      Thick black border wraps both panels. Renders on every tab.               */}
                  <Grid item xs={12}>
                    <MDBox px={2} pb={1.5}>
                      <Card sx={{ border: "2.5px solid #1A1A1A", boxShadow: "none", borderRadius: 2 }}>
                        <Grid container sx={{ minHeight: 480 }}>

                          {/* LEFT: pain metric dropdown + binarization dropdown + sliders */}
                          <Grid item xs={12} md={5}
                            sx={{ borderRight: { md: "1.5px solid #1A1A1A" }, borderBottom: { xs: "1.5px solid #1A1A1A", md: "none" } }}>
                            <MDBox p={2} display="flex" flexDirection="column" gap={1.5}>
                              <MDBox>
                                <MDTypography variant="button" fontWeight="bold" color="dark" sx={{ fontSize: 17 }}>
                                  {"Binarization — defines the high vs low pain classifier boundary"}
                                </MDTypography>
                                <FormControl fullWidth size="medium" sx={{ mt: 0.5 }}>
                                  <Select
                                    value={strategy}
                                    onChange={(e) => setStrategy(e.target.value)}
                                    sx={{ fontSize: 16, fontWeight: 500 }}
                                  >
                                    {((data && data.available_strategies) || DEFAULT_STRATEGY_OPTIONS).map((s) => (
                                      <MenuItem key={s.key} value={s.key} sx={{ fontSize: 16 }}>{s.label}</MenuItem>
                                    ))}
                                  </Select>
                                </FormControl>
                              </MDBox>
                              {strategy === "tertile" || strategy === "percentile" ? (
                                <MDBox display="flex" flexDirection="column" gap={1}>
                                  <MDBox display="flex" flexDirection="row" alignItems="center" gap={1.5}>
                                    <MDTypography variant="caption" fontWeight="medium" color="dark" sx={{ minWidth: 80, fontSize: 14 }}>
                                      {"Low pain ≤ percentile"}
                                    </MDTypography>
                                    <Slider
                                      value={percentileLow} min={5} max={50} step={1}
                                      valueLabelDisplay="auto" size="small" sx={{ flex: 1 }}
                                      onChange={(e, v) => {
                                        // Tertile is the FIXED 33.3/66.7 preset (ignores these cuts, by
                                        // design — matches the backend). Dragging a slider means the user
                                        // wants an adjustable cut, so promote to "percentile" (which both
                                        // the live preview AND the backend honor) so the cut actually moves.
                                        if (strategy === "tertile") setStrategy("percentile");
                                        const lo = Math.min(v, percentileHigh - 1); setPercentileLow(lo);
                                      }}
                                    />
                                  </MDBox>
                                  <MDBox display="flex" flexDirection="row" alignItems="center" gap={1.5}>
                                    <MDTypography variant="caption" fontWeight="medium" color="dark" sx={{ minWidth: 80, fontSize: 14 }}>
                                      {"High pain ≥ percentile"}
                                    </MDTypography>
                                    <Slider
                                      value={percentileHigh} min={50} max={95} step={1}
                                      valueLabelDisplay="auto" size="small" sx={{ flex: 1 }}
                                      onChange={(e, v) => {
                                        if (strategy === "tertile") setStrategy("percentile");
                                        const hi = Math.max(v, percentileLow + 1); setPercentileHigh(hi);
                                      }}
                                    />
                                  </MDBox>
                                </MDBox>
                              ) : null}
                              <MDTypography variant="caption" color="dark" fontStyle="italic" sx={{ fontSize: 13 }}>
                                {strategy === "tertile"
                                  ? "Tertile uses fixed 33⅓ / 66⅔ cuts; samples between them are excluded. Drag a slider to switch to adjustable percentile cuts."
                                  : strategy === "percentile"
                                    ? "Samples between the cuts are excluded from training."
                                    : strategy === "median"
                                      ? "Every sample is labeled at the median split (~50/50)."
                                      : "Legacy 2-cluster KMeans labeler."}
                              </MDTypography>

                              {/* Match direction: pro_first (PRO-anchored, default) vs nearest (PSD-first
                                  symmetric) vs prior (PSD-first forecasting). */}
                              <MDBox mt={1.5}>
                                <MDTypography variant="caption" fontWeight="bold" color="dark"
                                  sx={{ fontSize: 13, display: "block", mb: 0.5 }}>
                                  Match direction
                                </MDTypography>
                                <ToggleButtonGroup
                                  value={matchDirection} exclusive size="small"
                                  aria-label="Match direction"
                                  onChange={(e, v) => { if (v) setMatchDirection(v); }}
                                  sx={{ "& .MuiToggleButton-root": { textTransform: "none", fontSize: 12, py: 0.4, px: 1 } }}
                                >
                                  <ToggleButton value="pro_first" title="Walk pain ratings; claim up to N closest PSDs per channel each (maximizes discovery coverage)">PRO-first (discovery)</ToggleButton>
                                  <ToggleButton value="nearest" title="Pair each PSD with the nearest pain rating in either time direction (symmetric ± window)">Nearest (±window)</ToggleButton>
                                  <ToggleButton value="prior" title="Pair each PSD only with pain ratings recorded AFTER it (causal / closed-loop forecasting direction)">Prior (forecast)</ToggleButton>
                                </ToggleButtonGroup>
                                <MDTypography variant="caption" color="dark" fontStyle="italic"
                                  sx={{ fontSize: 13, display: "block", mt: 0.5 }}>
                                  {matchDirection === "pro_first"
                                    ? "Walks pain ratings (the unit of independence) and claims up to N closest PSDs PER CHANNEL each, within the window. Maximizes the number of ratings that contribute to discovery — the right framing when 'does this band track pain?' is the question."
                                    : matchDirection === "nearest"
                                    ? "Each PSD is paired with the closest pain rating in EITHER time direction (symmetric ± window). Cross-sectional association, not forecasting."
                                    : "Each PSD is paired only with pain ratings recorded AFTER it within the window (causal/forecasting direction). Use for closed-loop deployment."}
                                </MDTypography>
                              </MDBox>

                              {/* Per-rating CAP (replaces the old all / one-per-rating toggle). */}
                              <MDBox mt={1.5}>
                                <MDTypography variant="caption" fontWeight="bold" color="dark"
                                  sx={{ fontSize: 13, display: "block", mb: 0.5 }}>
                                  {`Max PSD snapshots per pain rating (currently ${maxPerRating})`}
                                </MDTypography>
                                <MDBox px={0.5}>
                                  <Slider
                                    value={maxPerRating} min={1} max={10} step={1}
                                    marks valueLabelDisplay="auto" size="small"
                                    onChange={(e, v) => setMaxPerRating(v)} />
                                </MDBox>
                                <MDTypography variant="caption" fontWeight="bold" color="dark"
                                  sx={{ fontSize: 13, display: "block", mb: 0.5, mt: 0.5 }}>
                                  {`Minimum gap between selected PSDs (${refractoryMin} min)`}
                                </MDTypography>
                                <MDBox px={0.5}>
                                  <Slider
                                    value={refractoryMin} min={0} max={30} step={1}
                                    valueLabelDisplay="auto" size="small"
                                    disabled={maxPerRating <= 1 || matchDirection === "pro_first"}
                                    onChange={(e, v) => setRefractoryMin(v)} />
                                </MDBox>
                                <MDTypography variant="caption" color="dark" fontStyle="italic"
                                  sx={{ fontSize: 13, display: "block", mt: 0.5 }}>
                                  {matchDirection === "pro_first"
                                    ? "Refractory gap does not apply in PRO-first matching: each PSD is claimed by at most one rating, so a streaming burst can't double-count regardless of the gap. Switch to Nearest or Prior to enforce a minimum spacing between kept PSDs."
                                    : (`Each pain rating keeps at most ${maxPerRating} PSD${maxPerRating > 1 ? "s" : ""} per channel — `
                                   + (matchDirection === "prior"
                                      ? "the ones recorded closest in time BEFORE the rating (forecasting direction)"
                                      : "the ones closest in time to the rating (either direction)")
                                   + (maxPerRating > 1
                                      ? `, and no two kept PSDs within ${refractoryMin} min of each other, so a streaming burst around one survey can't dominate. `
                                      : " — i.e. one independent sample per rating. ")
                                   + (maxPerRating > 1
                                      ? "The binary-classification AUC is still cross-validated with folds grouped by rating, so reused ratings can't inflate it; the AUC n is the count of independent ratings."
                                      : "Every sample is an independent (channel, rating) pair — no double-dipping."))}
                                </MDTypography>
                              </MDBox>
                            </MDBox>
                          </Grid>

                          {/* RIGHT: live binarization preview histogram */}
                          <Grid item xs={12} md={7}>
                            <MDBox p={1.5} sx={{ height: "100%" }}>
                              <BinarizationPreview
                                points={previewPoints}
                                strategy={strategy}
                                percentileLow={percentileLow}
                                percentileHigh={percentileHigh}
                                metricLabel={previewMetricLabel}
                                metricKey={metric}
                                loading={painLoading}
                                matchTolerance={matchTolerance}
                                setMatchTolerance={setMatchTolerance}
                                scanModel={scanModel}
                                matchedLoading={availLoading}
                                matchDirty={dirty}
                              />
                            </MDBox>
                          </Grid>

                        </Grid>
                      </Card>
                    </MDBox>
                  </Grid>

                  {/* ── Exploratory analysis trigger, DIRECTLY BENEATH the Pain Biomarkers box ──
                      The timeline + preview above are live (no compute). The full-spectrum
                      exploration (5 Hz sliding-band r + AUC over the matched PSDs) is EXPENSIVE
                      and runs ONLY on click, using the metric / binarization / match-window chosen
                      in the box above. */}
                  <Grid item xs={12}>
                    <MDBox px={2} pt={0.5} pb={1.5} display="flex" flexDirection="row" alignItems="center" gap={2} flexWrap="wrap">
                      <MDButton
                        variant="contained" color="error" size="large"
                        onClick={compute} disabled={computing}
                        sx={{ fontWeight: "bold", fontSize: 16, px: 3, py: 1.25,
                              backgroundColor: "#d32f2f", color: "#ffffff",
                              "&:hover": { backgroundColor: "#b71c1c" },
                              "&.Mui-disabled": { backgroundColor: "#e57373", color: "#ffffff" } }}
                      >
                        {computing ? (
                          <><CircularProgress size={18} sx={{ color: "#fff", mr: 1 }} />{"Computing…"}</>
                        ) : (data ? "↻ Recompute full-spectrum exploration" : "▶ Start exploratory analysis")}
                      </MDButton>
                      {!computing && dirty && data ? (
                        <MDTypography variant="button" color="error" fontWeight="medium">
                          {"Settings changed — click to recompute."}
                        </MDTypography>
                      ) : null}
                      {data && data.timeline_points_full ? (
                        <MDTypography variant="caption" color="dark">
                          {`(computed on ${Number(data.timeline_points_full).toLocaleString()} full-resolution samples)`}
                        </MDTypography>
                      ) : null}
                      {/* Persistence status: tells the user this view will survive a trip to the
                          deployment view. Green when the heavy result is cached in memory (instant
                          restore); amber when memory is tight so it'll recompute on return instead. */}
                      {data && !computing ? (
                        underMemoryPressure() ? (
                          <MDTypography variant="caption" sx={{ color: "#8A6100", fontStyle: "italic" }}>
                            {`⚠ memory tight${memoryInfo() ? ` (${memoryInfo().usedMB.toFixed(0)}/${memoryInfo().limitMB.toFixed(0)} MB)` : ""} — view will recompute on return`}
                          </MDTypography>
                        ) : (
                          <MDTypography variant="caption" sx={{ color: "#0a7f3f", fontStyle: "italic" }}>
                            {"✓ view retained — returns instantly from the deployment page"}
                          </MDTypography>
                        )
                      ) : null}
                    </MDBox>
                  </Grid>

                  {!data && !alert ? (
                    <Grid item xs={12}>
                      <MDBox p={2}>
                        <MDTypography variant="button" color="dark">
                          {"Pick a pain metric and binarization above — the timeline and binarization preview are already live. Click "}
                          <strong>▶ Start exploratory analysis</strong>{" to run the full-spectrum scan."}
                        </MDTypography>
                      </MDBox>
                    </Grid>
                  ) : null}

                  {data && data.message ? (
                    <Grid item xs={12}>
                      <MDBox p={2}>
                        <MDTypography variant="h6" color="error" fontSize={18}>
                          {data.message}
                        </MDTypography>
                        <MDTypography variant="button" color="dark">
                          {"Upload a Percept session for this participant and configure REDCap (REDCAP_API_URL / REDCAP_API_TOKEN), then reload."}
                        </MDTypography>
                      </MDBox>
                    </Grid>
                  ) : null}

                  {data && data.summary ? (
                    <Grid item xs={12}>
                      <MDBox px={2} pb={1}>
                        {data.label_metric ? (
                          <MDTypography variant="button" fontWeight="medium" color="dark" display="block">
                            {"Biomarker computed against: "}
                            {(((data && data.available_metrics) || DEFAULT_METRIC_OPTIONS)
                              .find((m) => m.key === data.label_metric) || {}).label || data.label_metric}
                          </MDTypography>
                        ) : null}
                        {data.label_strategy ? (
                          <MDTypography variant="caption" color="dark" display="block">
                            {"Binarized by: "}
                            {(((data && data.available_strategies) || DEFAULT_STRATEGY_OPTIONS)
                              .find((s) => s.key === data.label_strategy) || {}).label || data.label_strategy}
                            {(data.label_strategy === "tertile" || data.label_strategy === "percentile")
                              && data.percentile_low != null
                              ? ` (≤${Number(data.percentile_low).toFixed(0)}th / ≥${Number(data.percentile_high).toFixed(0)}th pct, daily)`
                              : ""}
                          </MDTypography>
                        ) : null}
                        {/* Concise per-channel matched-sample summary (replaces the legacy dual-
                            pipeline Time-/Power-domain prose). For each bipolar channel: how many
                            matched samples fell HIGH / LOW / excluded-middle by the active cut, and
                            how many of the channel's LSB vectors are time-domain-derived vs PSD-
                            derived. Only modeled/real LSB values feed the spectral feature-importance
                            scan, so these two source counts ARE the analyzable-sample budget. */}
                        {(() => {
                          const sfi = data.analytics && data.analytics.timedomain
                            && data.analytics.timedomain.spectral_feature_importance;
                          const chans = (sfi && sfi.channels) || [];
                          if (!chans.length) return null;
                          const bin = (sfi && sfi.binarization) || {};
                          return (
                            <MDBox mt={0.5} mb={0.5}>
                              <MDTypography variant="button" fontWeight="medium" color="dark" display="block">
                                {"Matched samples per channel "}
                                <span style={{ fontWeight: 400, color: "#6c757d" }}>
                                  {"(high / low / excluded · LSB source TD / PSD)"}
                                </span>
                              </MDTypography>
                              {chans.map((c, i) => (
                                <MDTypography key={i} variant="caption" color="text" display="block"
                                  sx={{ fontSize: 12.5, lineHeight: 1.5 }}>
                                  <strong>{c.short}</strong>
                                  {`: ${c.n_high != null ? c.n_high : "—"} high · `
                                   + `${c.n_low != null ? c.n_low : "—"} low · `
                                   + `${c.n_excluded != null ? c.n_excluded : "—"} excluded`}
                                  {(c.n_td != null || c.n_psd_bridge != null)
                                    ? <span style={{ color: "#6c757d" }}>{`  ·  ${c.n_td || 0} TD / ${c.n_psd_bridge || 0} PSD LSBs`}</span>
                                    : null}
                                </MDTypography>
                              ))}
                              {bin.n_high != null && (
                                <MDTypography variant="caption" fontStyle="italic" color="dark" display="block"
                                  sx={{ fontSize: 11.5, lineHeight: 1.5, mt: 0.25 }}>
                                  {`Pooled binarization: ${bin.n_high} high · ${bin.n_low} low · `
                                   + `${bin.n_excluded_middle} excluded-middle. `
                                   + "Only modeled/real LSB values (TD-transform or PSD-bridge) feed the "
                                   + "spectral feature-importance scan."}
                                </MDTypography>
                              )}
                            </MDBox>
                          );
                        })()}
                        {data.powerdomain_pooled_warning ? (
                          <MDTypography variant="button" fontWeight="medium" color="warning" display="block">
                            {`⚠ ${data.powerdomain_pooled_warning}`}
                          </MDTypography>
                        ) : null}
                        {data.recorded_powers && data.recorded_powers.length ? (() => {
                          const left  = data.recorded_powers.filter((p) => /\bL\b|Left/i.test(p.label));
                          const right = data.recorded_powers.filter((p) => /\bR\b|Right/i.test(p.label));
                          const other = data.recorded_powers.filter((p) =>
                            !(/\bL\b|Left/i.test(p.label)) && !(/\bR\b|Right/i.test(p.label)));
                          const noFreq = data.recorded_powers.every((p) => p.center_hz == null);
                          const anyAboveCap = data.recorded_powers.some((p) => p.above_cap);
                          const fmt = (p) => {
                            const base = p.region ? `${p.label} (${p.region})` : p.label;
                            const withHz = p.center_hz != null ? `${base} @ ${Number(p.center_hz).toFixed(1)} Hz` : base;
                            return p.above_cap ? `${withHz} ⚠` : withHz;
                          };
                          // Above-cap (≥50 Hz) sensing bands are rendered in the warning color.
                          const rowLine = (p, i) => (
                            <MDTypography key={i} variant="caption"
                              color={p.above_cap ? "warning" : "text"} sx={{ fontSize: 12 }}>
                              {fmt(p)}
                            </MDTypography>
                          );
                          return (
                            <MDBox display="flex" flexDirection="column" alignItems="center" mt={0.5}>
                              <MDTypography variant="button" fontWeight="medium" color="dark" mb={0.25}>
                                {"Recorded power channels"}
                              </MDTypography>
                              <MDBox display="flex" flexDirection="row" gap={4} justifyContent="center" flexWrap="wrap">
                                {left.length > 0 && (
                                  <MDBox display="flex" flexDirection="column" alignItems="center">
                                    <MDTypography variant="caption" fontWeight="medium" color="dark" sx={{ fontSize: 11, textDecoration: "underline" }}>
                                      {"Left"}
                                    </MDTypography>
                                    {left.map(rowLine)}
                                  </MDBox>
                                )}
                                {right.length > 0 && (
                                  <MDBox display="flex" flexDirection="column" alignItems="center">
                                    <MDTypography variant="caption" fontWeight="medium" color="dark" sx={{ fontSize: 11, textDecoration: "underline" }}>
                                      {"Right"}
                                    </MDTypography>
                                    {right.map(rowLine)}
                                  </MDBox>
                                )}
                                {other.map(rowLine)}
                              </MDBox>
                              {anyAboveCap && (
                                <MDTypography variant="caption" color="warning" fontStyle="italic" sx={{ fontSize: 11.5, mt: 0.25 }}>
                                  {"⚠ Sensing band ≥ 50 Hz — outside the validated theta/alpha/beta/low-gamma biomarker range."}
                                </MDTypography>
                              )}
                              {noFreq && (
                                <MDTypography variant="caption" color="dark" fontStyle="italic" sx={{ fontSize: 11.5, mt: 0.25 }}>
                                  {"Sensing-band center frequency not available in this device export."}
                                </MDTypography>
                              )}
                            </MDBox>
                          );
                        })() : null}
                      </MDBox>
                    </Grid>
                  ) : null}

                </Grid>
              </Card>
            </Grid>

            {data && data.analytics ? (
              <BiomarkerAnalytics analytics={data.analytics} summary={data.summary}
                recordedPowers={data.recorded_powers}
                programmedThresholds={data.programmed_thresholds}
                binStrategy={strategy} binMetricKey={metric}
                binPercentileLow={percentileLow} binPercentileHigh={percentileHigh}
                participantUid={participant_uid}
                requestParams={requestParams}
                matchDirty={dirty}
                metricLabel={(((data && data.available_metrics) || DEFAULT_METRIC_OPTIONS)
                  .find((m) => m.key === data.label_metric) || {}).label || data.label_metric} />
            ) : null}
          </Grid>
        </MDBox>
      </DatabaseLayout>
    </>
  );
}

// [removed] module-level fmt()/fmtP() — their only consumer was summaryLine(), removed above.
// The recorded-power list uses its own local fmt(); other panels format inline.

export default Biomarkers;
