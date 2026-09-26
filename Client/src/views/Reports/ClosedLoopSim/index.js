/**
 * Closed-Loop Deployment — the clinician route, rebuilt 2026-09-04.
 *
 * The reader this page is designed for is a clinician-scientist standing at a Medtronic A610 during
 * a programming visit, deciding whether to enable Adaptive Therapy for this participant and what to
 * type into the programmer. Their question has two parts in a strict order: may I enable this at
 * all, and if so what do I enter.
 *
 * WHAT CHANGED, AND WHY. The page this replaces rendered eleven sections in the order the module was
 * built in, which is a record of the work rather than a decision surface. It also stated its verdict
 * three times, from two endpoints that answer different questions, and the statement pinned to the
 * viewport was the one that did not know about the device rules — so the page could show a
 * permissive headline stuck to the top of the screen while the body of the page said the device
 * forbids the configuration. That is fixed structurally rather than by care: there is now one
 * headline, it is computed from both endpoints, and no arrangement of the viewport can produce the
 * old contradiction because there is no second verdict to disagree with.
 *
 * THE PAGE, in reading order since the minimalist redesign (SPEC 2026-09-26 section 5.2, which
 * builds on decision 302's one decision card):
 *   Head. The page's question as its title, the pain score, where the chosen band is held, the safe
 *      current ceiling read from the server, then one row of controls (the pain score, the
 *      clinic-sheet switch, and the ⋯ menu holding "Load a saved band file", "Clear" and the stored
 *      results), then the contents row of jump links.
 *   1. THE DECISION CARD: the verdict at 22 px; red ✕ bullets when the device refuses and ▲ ones for
 *      evidence that was not checked, worded as before; the values to enter, only when the device
 *      allows them; "Sign and print"; one Details fold.
 *   2. "Which band?" (the grid).   3. "Does the device allow it?" (the rule table).
 *   4. "Does the evidence hang together?"   5. "Does the band mean the same at every stimulation
 *      state?"   6. Background, folded: current and band power three ways, the simulated closed
 *      loop, and the switching-point panels.
 *
 * WHAT IS NO LONGER RENDERED HERE, and where it went. `DeploymentVerdictStrip` was superseded by
 * `DeploymentDecisionHeader` (2026-09-04), and that header by `DecisionCard` (decision 302), which
 * carries the verdict, the jump links and the print path. `DeploymentEvidencePanel` is
 * superseded by `DeviceRuleLedger` and `EvidenceTrianglePanel` between them. `CalibrationInEffectPanel`
 * (and, until its deletion on 2026-09-21, `PsdLsbPanel`) is not rendered on this route at all: the microvolt-to-least-significant-
 * bit conversion model and the power spectrum are methods artefacts whose reader is the analyst
 * before the visit, and the band has already been chosen and committed by the time anyone opens this
 * page. The raw BandCandidate JSON inspector is also gone, because a dump of an internal schema has
 * no clinical reader. All four component FILES are left in place and still export working
 * components, so whoever places them on the Biomarkers route can import them unchanged.
 *
 * `DeploymentRocPanel`, `LsbPowerPanel` and `EraRefitPanel` are demoted rather than cut. All three
 * are real evidence about whether the band generalises and where the cut-point sits, and none of
 * them is the first question at a programming visit, so they sit below the evidence behind one
 * fold.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";

import { Card, Grid } from "@mui/material";

import MDBox from "components/MDBox";
import MDTypography from "components/MDTypography";
import MDButton from "components/MDButton";

import DatabaseLayout from "layouts/DatabaseLayout";

import RecomputeBar from "views/Reports/RecomputeBar";
import CacheStatusLine from "views/Reports/CacheStatusLine";
import Fold from "./Fold";
import { recomputeClosedLoop } from "views/Reports/moduleCacheKeys";

import {
  loadBandCandidate, parseUploadedCandidate, syncChosenBand, recordChosenBand, recordClearedBand,
  chosenBandRecordText,
} from "./bandCandidateStore";
import DeploymentRocPanel from "./DeploymentRocPanel";
import LsbPowerPanel from "./LsbPowerPanel";
import EraRefitPanel from "./EraRefitPanel";
import DecisionCard, { ContentsRow } from "./DecisionCard";
import DeveloperMenu from "./DeveloperMenu";
import DeviceRuleLedger from "./DeviceRuleLedger";
import EvidenceTrianglePanel from "./EvidenceTrianglePanel";
import ClosedLoopSimulationPanel from "./ClosedLoopSimulationPanel";
import BandStabilityPanel from "./BandStabilityPanel";
import BandSweepGridPanel from "./BandSweepGridPanel";
import ThreeSourceResponsePanel from "./ThreeSourceResponsePanel";
import useDeploymentSummary from "./useDeploymentSummary";
import useDeploymentReport from "./useDeploymentReport";
import useBandSweepGrid from "./useBandSweepGrid";
import useThreeSourcePooled from "./useThreeSourcePooled";
import useClosedLoopSimulation from "./useClosedLoopSimulation";
import PAL from "./palette";
import { TYPE, CARD, LAYOUT } from "assets/theme/base/tokens";
import { contextLine } from "views/Reports/paper/PageHead";
import CeilingLine from "views/Reports/paper/CeilingLine";
import { useStudyCode } from "views/Reports/paper/studyCode";
import "./deployPrint.css";
import { bandPainScore, summaryRequestParams, withheldIfOtherBand } from "./candidateRequestParams";
import PainScoreSelect from "./PainScoreSelect";
import { PAIN_SCORE_OPTIONS } from "views/Reports/painScores";
import ClinicSheetsSummaryButton, { loadSummarySheets, saveSummarySheets } from "./ClinicSheetsSummaryButton";

/**
 * THE PAGE'S OWN DISPLAY STATE, HELD AT MODULE SCOPE FOR THE SAME REASON THE RESULT CACHE IS.
 *
 * Caching the fetches is only half of what a reader means by "the page is still where I left it".
 * This is a route-level component, so React Router destroys its `useState` on navigation, and four
 * pieces of that state decide what the restored page looks like: whether the analyst fold was open,
 * which threshold mode was selected, and which operating point and device threshold the panels had
 * settled on. Losing them means coming back to a page that has the right numbers arranged in the
 * wrong way — the fold shut on the panel someone was reading, the mode reset from the one they
 * chose to the one the payload recommends.
 *
 * THE OPERATING POINT MATTERS FOR A SECOND AND LESS OBVIOUS REASON. It is an input to the
 * statistical summary's request, so it is part of that request's cache key. If it came back as
 * null on every return, the key would not match the entry stored under the cut-point that was in
 * force, and the page would declare itself stale the moment it reappeared — on a change nobody
 * made. Keeping it here means the key that is asked for on return is the key that was stored.
 *
 * A hard reload clears this, which is correct and matches the result cache: a reload is a request
 * for a clean slate.
 */
const VIEW_STATE = new Map();

function readViewState(uid) { return VIEW_STATE.get(String(uid || "unknown")) || {}; }

function writeViewState(uid, patch) {
  const k = String(uid || "unknown");
  VIEW_STATE.set(k, { ...(VIEW_STATE.get(k) || {}), ...patch });
}

/**
 * True once `show` has been true at least once, and true forever after.
 *
 * This is how the analyst fold keeps its figures. A collapsed panel is HIDDEN rather than
 * unmounted, so Plotly keeps its own zoom, pan and legend state and reopening the fold shows the
 * figure exactly as it was left rather than redrawing it from the top. But the panels are not
 * mounted until the fold has been opened once, because a Plotly graph first drawn inside a
 * container with `display: none` measures its width as zero and stays that size when the container
 * becomes visible. Mounting on first reveal means every first draw happens at the width it will be
 * read at.
 *
 * The remaining limit is worth naming: a window resized while the fold is shut leaves those figures
 * at their previous width until something else prompts Plotly to resize them.
 */
function useRevealedOnce(show) {
  const [revealed, setRevealed] = useState(!!show);
  useEffect(() => { if (show && !revealed) setRevealed(true); }, [show, revealed]);
  return revealed;
}

/**
 * Where the chosen band is held, in one line under the page title (the PI's ruling 8). A band held
 * in this browser only is said so in the warning colour, with the reason, because nobody opening
 * this page elsewhere would see it. The wording lives in `bandCandidateStore.chosenBandRecordText`.
 */
function ChosenBandRecordLine({ status, hasBand }) {
  const text = chosenBandRecordText(status, hasBand);
  if (!text) return null;
  return (
    <MDTypography variant="caption" display="block" sx={{ fontSize: PAL.fs.caption,
      color: status.where === "browser" ? PAL.warnText : PAL.ink3 }}>
      {/* A caution ink always carries its glyph (SPEC 2.3). */}
      {status.where === "browser" ? <span aria-hidden="true">{"\u25B2 "}</span> : null}
      {text}
    </MDTypography>
  );
}

/** The page's question, its title (SPEC 2026-09-26 section 5.2). */
export const PAGE_QUESTION = "Can this setting be programmed, and what do I enter?";

/**
 * The safe current ceiling line, READ FROM THE SERVER (decision 306 sends the ceiling for the
 * stimulated side with the report's threshold block) and never typed here. It is drawn by the
 * shared `paper/CeilingLine` in the specification's sentence (SPEC section 4 rule 1). The report
 * carries the one side it plans for, so that side is printed and the other is said not to have
 * been sent. Returns null when the report carries no ceiling at all; the page then says so
 * (`CEILING_NOT_SENT`) instead of printing a number.
 */
export const CEILING_NOT_SENT = "Safe current ceiling: not sent with this report.";

export function ceilingLineProps(threshold, side) {
  const v = threshold && threshold.safety_ceiling_mA;
  if (v == null || !Number.isFinite(Number(v))) return null;
  const n = Number(v);
  const prov = (threshold.safety_ceiling_provenance
    && String(threshold.safety_ceiling_provenance).trim()) || "";
  // The PI-stated provenance reads "stated by PI, <date> ..."; any other (the module's hard limit
  // where no ceiling was stated) is printed as the server wrote it, never as "set by the PI".
  const source = !prov || /^stated by (the )?PI\b/i.test(prov) ? "set by the PI" : prov;
  const s = String(side || "").toLowerCase();
  if (s === "left") return { leftMa: n, rightMa: null, source };
  if (s === "right") return { leftMa: null, rightMa: n, source };
  return null;
}

function ClosedLoopSim() {
  const navigate = useNavigate();
  const { participant_uid } = useParams();
  // The de-identified study code for the line under the title (SPEC section 4 rule 1); null when
  // the participant record carries none.
  const participantCode = useStudyCode(participant_uid);
  const fileRef = useRef(null);

  // Everything below that describes how the page is ARRANGED is seeded from the retained view
  // state, so a return to this route restores the arrangement as well as the results.
  const retained = readViewState(participant_uid);

  const [envelope, setEnvelope] = useState(null);   // {band_candidate, participant_uid, committed_at}
  // Where the chosen band is held: on the server's record, or in this browser only (with why).
  const [bandRecord, setBandRecord] = useState(null);
  // The clinic-sheet ratings in the deployment summary, or not (the PI, 2026-09-24): off by default,
  // remembered per participant in this browser.
  const [includeSheets, setIncludeSheets] = useState(() => loadSummarySheets(participant_uid));
  const onToggleSheets = (on) => { setIncludeSheets(on); saveSummarySheets(participant_uid, on); };
  useEffect(() => { setIncludeSheets(loadSummarySheets(participant_uid)); }, [participant_uid]);
  const [cutpoint, setCutpoint] = useState(retained.cutpoint || null);   // chosen operating point, lifted from the ROC
  // The resolved device-LSB threshold, lifted from the LSB panel so the ROC's feature histogram can
  // annotate its cut line with the same value.
  const [lsbThreshold, setLsbThreshold] = useState(retained.lsbThreshold || null);   // {upperLsb, estimated} | null
  const [showAnalyst, setShowAnalyst] = useState(!!retained.showAnalyst);

  /**
   * THE SELECTED THRESHOLD MODE, held here because two panels depend on it.
   *
   * It starts as null and STAYS null until the clinician picks a mode, and each panel falls back to
   * the payload's own `prescriptions.selected` or `prescriptions.recommended` while it is null. That
   * arrangement is what satisfies the requirement that a selection must never snap back to the
   * recommendation: there is no effect that writes the recommendation into this state, so nothing
   * can overwrite a choice once it has been made, not on a re-render and not when the report
   * refetches.
   *
   * Changing it does NOT refetch anything. The payload already carries all three modes with their
   * own field lists, couplings and duty cycles, so switching modes is a pure display change. That
   * matters because the deployment endpoint fits regression models, and a toggle that refetched
   * would put a model fit behind a button press.
   */
  const [thresholdMode, setThresholdMode] = useState(retained.thresholdMode || null);

  // Retain the four pieces of arrangement across a route unmount. This writes only when one of them
  // changes, and it writes plain values, so nothing here can hold a stale render's closure.
  useEffect(() => {
    if (!participant_uid) return;
    writeViewState(participant_uid, { cutpoint, thresholdMode, showAnalyst, lsbThreshold });
  }, [participant_uid, cutpoint, thresholdMode, showAnalyst, lsbThreshold]);

  useEffect(() => {
    if (!participant_uid) { navigate("/database", { replace: false }); return undefined; }
    // This browser's copy first, so the page draws at once; then the server's record, which wins
    // (the PI's ruling 8). The envelope is replaced only when the server's band differs, so a
    // matching answer does not hand every panel a new object and refire its fetch.
    const local = loadBandCandidate(participant_uid);
    setEnvelope(local);
    let alive = true;
    syncChosenBand(participant_uid).then(({ envelope: server, status }) => {
      if (!alive) return;
      setBandRecord(status);
      const same = (a, b) => JSON.stringify(a && a.band_candidate) === JSON.stringify(b && b.band_candidate);
      if (!same(server, local)) setEnvelope(server);
    });
    return () => { alive = false; };
  }, [participant_uid, navigate]);

  // Tag <body> while this view is mounted so the print stylesheet can scope its "hide everything
  // except the record" rules to this page only, and clean the class up on unmount so printing any
  // other view is unaffected.
  useEffect(() => {
    document.body.classList.add("cl-deploy-root");
    return () => document.body.classList.remove("cl-deploy-root");
  }, []);

  const bc = envelope && envelope.band_candidate;

  // THE PAIN SCORE EVERY BAND-TO-PAIN READING ON THIS PAGE IS COMPUTED ON (the PI, 2026-09-25
  // night). Starts on the band's own (its grid's, decision 254), NRS when it carries none; a choice
  // made here holds until another band is chosen.
  const bandDefaultPain = useMemo(() => bandPainScore(bc), [bc]);
  const [painScoreChoice, setPainScoreChoice] = useState(null);
  const bandIdentity = bc ? `${bc.contact}|${bc.center_freq_hz}|${bandDefaultPain.key}` : "";
  useEffect(() => { setPainScoreChoice(null); }, [bandIdentity]);
  const painScore = painScoreChoice || bandDefaultPain.key;

  // Derive the discovery request knobs ONCE per committed candidate. Building this inline in JSX
  // produced a fresh object identity on every parent re-render, which is listed in every panel's
  // fetch-effect dependencies — so any child state change re-created it and re-fired every panel's
  // fetch, collapsing all figures into their loading state at once.
  const requestParams = useMemo(() => summaryRequestParams(bc, includeSheets, painScore),
    [bc, includeSheets, painScore]);

  // ONE deployment-summary fetch for the whole page. Each call runs a mixed-effects fit through
  // rpy2's embedded R, which is single-threaded per worker, so duplicate concurrent calls starve
  // the worker pool and drop sibling requests.
  const cutThr = cutpoint ? cutpoint.threshold : null;
  const matchDir = cutpoint ? cutpoint.matchDir : "prior";
  const summary = useDeploymentSummary({
    participantUid: participant_uid,
    channel: bc && bc.contact,
    centerHz: bc && bc.center_freq_hz,
    bandWidthHz: (bc && bc.bandwidth_hz) || 5.0,
    matchDir, cutThr, requestParams,
  });

  // A SEPARATE question from the summary above, and a separate endpoint. The summary asks where the
  // threshold goes and whether the statistical gates pass; this asks whether the device would permit
  // the configuration at all, estimates the three edges of the amplitude, power and pain triangle at
  // their correct clustering units, and tests whether the three signs are coherent with the control
  // law. Both must clear, and they can disagree.
  // One candidate object for the report AND the simulation fetch, so the two cannot name
  // different bands (the simulation is read back BY candidate since 2026-09-11).
  const reportCandidate = bc && {
    channel: bc.contact,
    centerHz: bc.center_freq_hz,
    bandWidthHz: bc.bandwidth_hz || 5.0,
    sensingHemisphere: bc.hemisphere,
    rateHz: bc.rate_hz,
    pulseWidthUs: bc.pulse_width_us,
    thresholdMode: bc.threshold_mode || "dual",
  };
  const deploymentReport = useDeploymentReport({
    participantUid: participant_uid,
    bandCandidate: reportCandidate,
    painScore,
  });

  // ONE BAND ON THE WHOLE PAGE (decision 302). The cache hands back the last result, marked stale,
  // when the request changes, so right after a new band is chosen the report and the summary in
  // hand can still be the previous band's. Every card below reads these two, never the raw hooks,
  // and a result computed for another band reaches them as "not computed for this band" with both
  // bands named, instead of the old band's verdict under the new band's name.
  // The same for the page's pain score and clinic-sheet switch (decision 307): a result computed on
  // another score, or with the switch the other way, is withheld and named until Recompute.
  const report = withheldIfOtherBand(deploymentReport, bc, "report", { painScore });
  const summaryForBand = withheldIfOtherBand(summary, bc, "summary", { painScore, includeSheets });

  // TRACK D: fetched independently of any committed candidate -- see useBandSweepGrid.js for why
  // gating this on useDeploymentReport's own enabled condition would make it unreachable from the
  // one screen that needs it (choosing a first candidate).
  const bandSweepGrid = useBandSweepGrid({ participantUid: participant_uid });

  // THE POOLED THREE-SOURCE VIEW, fetched AFTER the report has answered (the PI, 2026-09-11:
  // "prefetch the data after the first figures load"). It reads two stored tables and groups
  // them, so it never holds the verdict up; its own slot, so a Recompute rebuilds it too.
  const threeSourcePooled = useThreeSourcePooled({
    participantUid: participant_uid, afterReport: deploymentReport.data,
  });
  const closedLoopSim = useClosedLoopSimulation({ participantUid: participant_uid,
    bandCandidate: reportCandidate, afterReport: deploymentReport.data,
    reportStamp: deploymentReport.computedAt });
  // Medtronic labels for sensing contacts, from the grid's own sweeps (server-built, decision 86).
  const contactLabel = (ch) => {
    const sw = bandSweepGrid.grid && bandSweepGrid.grid.band_time_sweep
      && bandSweepGrid.grid.band_time_sweep[ch];
    return (sw && sw.display_short) || String(ch || "").replace(/_/g, " ");
  };

  // ARRIVING FROM THE BIOMARKERS PAGE'S "Open this grid in Closed-Loop" BUTTON. That button
  // navigates here with the fragment `#cl-grid`, naming the anchor already on the grid panel's own
  // Grid item below. React Router does not scroll to a fragment on its own, and this page is long
  // enough that landing at the top would leave a reader hunting for the panel they asked for.
  //
  // WAITS FOR THE GRID'S OWN FETCH TO SETTLE rather than scrolling on mount: the panel renders
  // immediately but is only a few lines tall while it is still loading, so a scroll fired on mount
  // lands at a position that stops being the panel's position a moment later. `scrolledToHash`
  // makes it fire once per arrival, so a later recompute (which flips `loading` again) does not
  // yank a reader's scroll position back.
  const location = useLocation();
  const scrolledToHash = useRef(null);
  useEffect(() => {
    const hash = (location.hash || "").replace(/^#/, "");
    if (!hash || bandSweepGrid.loading || scrolledToHash.current === hash) return;
    const el = document.getElementById(hash);
    if (!el) return;
    scrolledToHash.current = hash;
    el.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [location.hash, bandSweepGrid.loading]);

  /**
   * THE ONE RECOMPUTE CONTROL FOR THIS PAGE, REPORTING ON BOTH PAGE-LEVEL REQUESTS AT ONCE.
   *
   * A reader is asking one question — does what I am looking at reflect the settings on this page —
   * and the page answers it from two endpoints. Giving each its own control would put two of them
   * at the top disagreeing about whether the page is current, which is the same class of problem
   * the rebuilt page removed when it reduced three verdicts to one.
   *
   * The reasons are pooled and de-duplicated, because both requests see the same server restart and
   * the same committed-band change and would each report it.
   */
  const staleReasons = Array.from(new Set([
    ...(deploymentReport.staleReasons || []),
    ...(summary.staleReasons || []),
  ]));
  // The OLDER of the two timestamps. Reporting the newer one would let a summary computed a moment
  // ago speak for a deployment report computed an hour before it.
  const computedAtCandidates = [deploymentReport.computedAt, summary.computedAt]
    .filter((t) => t != null);
  const pageComputedAt = computedAtCandidates.length ? Math.min(...computedAtCandidates) : null;

  const onRecomputePage = () => recomputeClosedLoop(participant_uid);

  const analystRevealed = useRevealedOnce(showAnalyst);

  const onUpload = (e) => {
    const file = e.target.files && e.target.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      const parsed = parseUploadedCandidate(String(reader.result));
      if (parsed && parsed.band_candidate) {
        recordChosenBand(participant_uid, parsed.band_candidate, "upload")
          .then(({ status }) => setBandRecord(status));
        setEnvelope(loadBandCandidate(participant_uid));
      }
    };
    reader.readAsText(file);
    e.target.value = "";   // allow re-upload of the same file
  };

  const painLabel = (report && report.data && report.data.pain_score && report.data.pain_score.label)
    || bandDefaultPain.label || null;
  const threshold = report && report.data && report.data.threshold;
  const sideOf = report && report.data && report.data.manifest && report.data.manifest.hemisphere;
  const ceilingProps = ceilingLineProps(threshold, sideOf);

  return (
    <DatabaseLayout>
      <MDBox pt={3} pb={8} sx={{ maxWidth: LAYOUT.contentMax, mx: "auto", px: { xs: 2, md: 0 } }}>
        {/* THE HEAD (SPEC 2026-09-26 section 4 rule 1): the title as a question, one grey line,
            the ceiling line read from the server, then the controls in one row. The verdict is
            the decision card's status line, directly below. */}
        <MDBox component="header" mb={3}>
          <MDTypography component="h1" sx={{ ...TYPE.title, m: 0, color: PAL.ink }}>
            {PAGE_QUESTION}
          </MDTypography>
          {participantCode || painLabel ? (
            <MDTypography data-testid="context-line" sx={{ ...TYPE.caption, color: PAL.ink3, mt: 0.5 }}>
              {contextLine(participantCode, painLabel)}
            </MDTypography>
          ) : null}
          <ChosenBandRecordLine status={bandRecord} hasBand={!!bc} />
          {bc ? (
            <MDBox mt={1}>
              {ceilingProps ? (
                <CeilingLine leftMa={ceilingProps.leftMa} rightMa={ceilingProps.rightMa}
                  source={ceilingProps.source} />
              ) : (
                <MDTypography data-paper="ceiling-line" sx={{ ...TYPE.body, color: PAL.ink }}>
                  {CEILING_NOT_SENT}
                </MDTypography>
              )}
            </MDBox>
          ) : null}

          <MDBox display="flex" gap={3} alignItems="flex-start" flexWrap="wrap" mt={2}>
            {bc ? (
              <PainScoreSelect value={painScore} bandDefault={bandDefaultPain}
                options={(bandSweepGrid.grid && bandSweepGrid.grid.available_metrics)
                  || PAIN_SCORE_OPTIONS}
                onChange={setPainScoreChoice} />
            ) : null}
            <ClinicSheetsSummaryButton on={includeSheets} onToggle={onToggleSheets} />
            <MDBox ml="auto">
              <DeveloperMenu
                onLoad={() => fileRef.current && fileRef.current.click()}
                onClear={bc ? () => {
                  recordClearedBand(participant_uid).then(({ status }) => setBandRecord(status));
                  setEnvelope(null);
                } : null}>
                {/* The stored-results line is for a developer, so it lives in the closed ⋯ menu
                    (SPEC 2026-09-26 section 4 rule 2). The menu hides it without unmounting it, and
                    it is not wrapped in a fold of its own: no fold inside a fold (rule 4). */}
                {bc && deploymentReport.data && deploymentReport.data.cache_status ? (
                  <MDBox data-testid="stored-results-menu-item">
                    <MDTypography sx={{ ...TYPE.caption, fontWeight: 600, color: PAL.ink3 }}>
                      Stored results
                    </MDTypography>
                    <CacheStatusLine status={deploymentReport.data.cache_status} />
                  </MDBox>
                ) : null}
              </DeveloperMenu>
              <input ref={fileRef} type="file" accept="application/json,.json"
                style={{ display: "none" }} onChange={onUpload} />
            </MDBox>
          </MDBox>
          {bc ? <ContentsRow /> : null}
        </MDBox>

        {bc ? (
          <>
            {/* The Recompute control sits immediately above the decision card, because whether the
                verdict is current has to be readable before the verdict itself is read. */}
            <MDBox mb={2}>
              <RecomputeBar
                title="closed-loop deployment"
                stale={!!(deploymentReport.stale || summary.stale)}
                staleReasons={staleReasons}
                computedAt={pageComputedAt}
                loading={!!(deploymentReport.loading || summary.loading)}
                notKept={deploymentReport.notKept || summary.notKept}
                onRecompute={onRecomputePage}
              />
            </MDBox>
            {/* THE DECISION CARD (decision 302; SPEC 2026-09-26 section 5.2): the verdict, red and
                caution bullets worded as the rule table words them, the values to enter only when
                the device allows them, "Sign and print", and one Details fold. */}
            <MDBox id="cl-decision" mb={4}>
              <DecisionCard participantUid={participant_uid} bandCandidate={bc} summary={summaryForBand}
                deploymentReport={report} chosenBand={envelope} bandRecord={bandRecord}
                cutpoint={cutpoint} mode={thresholdMode} onMode={setThresholdMode}
                onRecompute={onRecomputePage} />
            </MDBox>
          </>
        ) : null}

        {/* SECTION 1, "Which band?" Rendered whether or not a band is chosen: the grid is how a
            first band gets chosen, so it must be reachable exactly when none exists yet. Picking
            a row commits a band through the same store the file path uses (bandCandidateStore). */}
        <MDBox id="cl-grid" mb={4}>
          <BandSweepGridPanel
            grid={bandSweepGrid.grid}
            participantUid={participant_uid}
            committed={bc ? { contact: bc.contact, centerHz: bc.center_freq_hz } : null}
            onCandidateChosen={() => setEnvelope(loadBandCandidate(participant_uid))}
            onChoiceRecorded={({ status }) => setBandRecord(status)}
          />
        </MDBox>

        {!bc ? (
          <Card sx={{ ...CARD, p: 3 }}>
            <MDTypography component="h2" sx={{ ...TYPE.title, color: PAL.ink }}>
              No band has been chosen for this participant yet
            </MDTypography>
            <MDTypography sx={{ ...TYPE.body, color: PAL.ink2, mt: 1, maxWidth: "68ch" }}>
              {"Whether the device allows closed loop is checked for one sensing contact pair at one "
                + "band, not for a participant, so a band has to be chosen before anything on this "
                + "page applies. Choose one in the grid above, choose one on the Biomarkers page, or "
                + "load a saved band file from the ⋯ menu."}
            </MDTypography>
            <MDBox mt={2}>
              <MDButton size="small" variant="outlined" color="dark"
                onClick={() => navigate(`/reports/biomarkers/${participant_uid}`)}
                sx={{ textTransform: "none", fontSize: PAL.fs.body }}>
                Go to the Biomarkers page
              </MDButton>
            </MDBox>
          </Card>
        ) : (
          <>
            {/* SECTION 2, "Does the device allow it?" Before the evidence, because on a device
                that acts on its own, whether a configuration is PERMITTED comes before how well it
                scores. */}
            <MDBox id="cl-rules" mb={4}>
              <DeviceRuleLedger report={report} />
            </MDBox>

            {/* SECTION 3, "Does the evidence hang together?" */}
            <MDBox id="cl-evidence" mb={4}>
              <EvidenceTrianglePanel report={report} />
            </MDBox>

            {/* SECTION 4, "Does the band mean the same at every stimulation state?" It qualifies the
                relationship section 3 draws: a band whose meaning shifts with the current is a
                different problem from one whose relationship is simply weak. */}
            <MDBox id="cl-stability" mb={4}>
              <BandStabilityPanel stability={report?.data?.band_stability}
                cacheStatus={report?.data?.cache_status}
                painScore={report?.data?.pain_score} />
            </MDBox>

            {/* BACKGROUND, folded (SPEC section 5.2 item 7): how band power moves with current,
                measured three ways; what the automatic adjustment would have done (simulated);
                and the switching point, device units and month-by-month check. None of it gates
                anything. The three-source and simulation panels stay MOUNTED inside the fold (it
                collapses to zero height without hiding the width, so their Plotly figures measure
                the right width). The three switching-point panels are mounted on the fold's first
                opening, as before, because they send their own requests. */}
            <Card id="cl-background" sx={{ ...CARD, p: 3 }}>
              <MDTypography component="h2" sx={{ ...TYPE.title, color: PAL.ink }}>Background</MDTypography>
              <MDTypography sx={{ ...TYPE.body, color: PAL.ink2, mt: 1, maxWidth: "68ch" }}>
                {"Checks for the analyst before the visit. Nothing here changes the answer above."}
              </MDTypography>
              <Fold show="Show the background (current and band power; simulated closed loop; switching point and month-by-month check)"
                hide="Hide the background" mt={2}
                onChange={(open) => { if (open) setShowAnalyst(true); }}>
                <MDBox id="cl-three-source" mt={2}>
                  <ThreeSourceResponsePanel report={report} pooled={threeSourcePooled}
                    committed={{ contact: bc.contact, centerHz: bc.center_freq_hz }}
                    contactLabel={contactLabel} />
                </MDBox>
                <MDBox id="cl-simulation" mt={4}>
                  <ClosedLoopSimulationPanel sim={closedLoopSim}
                    hemisphere={report?.data?.manifest?.hemisphere}
                    contactLabel={contactLabel} bandCandidate={bc} />
                </MDBox>
                {analystRevealed ? (
                  <Grid container spacing={3} mt={1}>
                    <Grid item xs={12} md={6} id="cl-roc">
                      <DeploymentRocPanel participantUid={participant_uid} bandCandidate={bc}
                        requestParams={requestParams} onCutpoint={setCutpoint}
                        lsbThreshold={lsbThreshold} />
                    </Grid>
                    <Grid item xs={12} md={6} id="cl-lsb">
                      <LsbPowerPanel participantUid={participant_uid} bandCandidate={bc}
                        requestParams={requestParams} cutpoint={cutpoint}
                        onLsbThreshold={setLsbThreshold} deploymentReport={report} />
                    </Grid>
                    <Grid item xs={12} id="cl-era">
                      <EraRefitPanel participantUid={participant_uid} bandCandidate={bc}
                        requestParams={requestParams} />
                    </Grid>
                  </Grid>
                ) : null}
              </Fold>
            </Card>
          </>
        )}
      </MDBox>
    </DatabaseLayout>
  );
}

export default ClosedLoopSim;
