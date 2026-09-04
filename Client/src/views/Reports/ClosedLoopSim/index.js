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
 * THE SIX BANDS, in reading order:
 *   0. The reconciled verdict, sticky, with the three sub-answers side by side.
 *   1. What would change this answer, ranked, with the actor named per row.
 *   2. The device rule ledger.
 *   3. The evidence triangle.
 *   4. The device parameters to transcribe, with the threshold-mode toggle at its top.
 *   5. The predicted duty cycle.
 * Then the configuration identity, then the analyst panels folded away, then the printable sign-off.
 *
 * WHAT IS NO LONGER RENDERED HERE, and where it went. `DeploymentVerdictStrip` is superseded by
 * `DeploymentDecisionHeader`, which keeps its sticky behaviour, its jump links and its print class
 * and drops its independently-computed verdict and its threshold cell. `DeploymentEvidencePanel` is
 * superseded by `DeviceRuleLedger` and `EvidenceTrianglePanel` between them. `PsdLsbPanel` and
 * `ConversionModelPanel` are not rendered on this route at all: the microvolt-to-least-significant-
 * bit conversion model and the power spectrum are methods artefacts whose reader is the analyst
 * before the visit, and the band has already been chosen and committed by the time anyone opens this
 * page. The raw BandCandidate JSON inspector is also gone, because a dump of an internal schema has
 * no clinical reader. All four component FILES are left in place and still export working
 * components, so whoever places them on the Biomarkers route can import them unchanged.
 *
 * `DeploymentRocPanel`, `LsbPowerPanel` and `EraRefitPanel` are demoted rather than cut. All three
 * are real evidence about whether the band generalises and where the cut-point sits, and none of
 * them is the first question at a programming visit, so they sit below the prescription behind one
 * fold.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { Card, Chip, Grid } from "@mui/material";

import MDBox from "components/MDBox";
import MDTypography from "components/MDTypography";
import MDButton from "components/MDButton";

import DatabaseLayout from "layouts/DatabaseLayout";

import {
  loadBandCandidate, clearBandCandidate, parseUploadedCandidate, commitBandCandidate,
} from "./bandCandidateStore";
import DeploymentRocPanel from "./DeploymentRocPanel";
import LsbPowerPanel from "./LsbPowerPanel";
import EraRefitPanel from "./EraRefitPanel";
import DeploySignoffCard from "./DeploySignoffCard";
import DeploymentDecisionHeader from "./DeploymentDecisionHeader";
import WhatWouldChangeThis from "./WhatWouldChangeThis";
import DeviceRuleLedger from "./DeviceRuleLedger";
import EvidenceTrianglePanel from "./EvidenceTrianglePanel";
import PrescriptionPanel from "./PrescriptionPanel";
import DutyCyclePanel from "./DutyCyclePanel";
import useDeploymentSummary from "./useDeploymentSummary";
import useDeploymentReport from "./useDeploymentReport";
import PAL from "./palette";
import { fmtHz } from "./deployFormat";
import "./deployPrint.css";

// Reconstruct the discovery request knobs (metric + binarization + match tolerance) from a
// committed candidate's label provenance, so the deployment ROC defines the band feature with the
// SAME binarization the candidate was validated under.
function requestParamsFromCandidate(bc) {
  const lbl = (bc && bc.label) || {};
  const bin = lbl.binarization || {};
  const rp = {};
  if (lbl.pro_metric) rp.LabelMetric = lbl.pro_metric;
  if (bin.strategy) rp.LabelStrategy = bin.strategy;
  if (bin.low_pct != null) rp.PercentileLow = bin.low_pct;
  if (bin.high_pct != null) rp.PercentileHigh = bin.high_pct;
  if (lbl.match_tolerance_min != null) rp.MatchToleranceMin = lbl.match_tolerance_min;
  return rp;
}

const fmt = (v, d = 2) => (v == null || !Number.isFinite(Number(v)) ? "not reported"
  : Number(v).toFixed(d));
const fmtP = (p) => (p == null || !Number.isFinite(Number(p)) ? "not reported"
  : Number(p) < 0.001 ? Number(p).toExponential(1) : Number(p).toFixed(3));

// Verdict badge color for the committed candidate's own discovery-stage verdict, which is a
// different quantity from anything on the reconciled header and is labelled as such below.
function verdictColor(verdict) {
  const v = verdict || "";
  if (/VALIDATED \(stim-stable\)/.test(v)) return PAL.pass;
  if (/VALIDATED \(stim-dependent\)/.test(v)) return PAL.warn;
  if (/failed/.test(v)) return PAL.fail;
  return PAL.neutral;
}

// White text on the warn fill measures 2.25:1, which is below every WCAG threshold, so the badge
// text colour adapts to its fill: near-black on the amber, white on the others.
function verdictTextColor(verdict) {
  return verdictColor(verdict) === PAL.warn ? PAL.onWarn : "white";
}

// A labeled key/value row used across the identity block.
function KV({ label, children }) {
  return (
    <MDBox display="flex" flexDirection="row" alignItems="baseline" gap={1} mb={0.4}>
      <MDTypography variant="caption" sx={{ fontSize: 11, fontWeight: "bold", minWidth: 150,
        color: "#555" }}>{label}</MDTypography>
      <MDTypography variant="caption" sx={{ fontSize: 11.5 }}>{children}</MDTypography>
    </MDBox>
  );
}

/**
 * The committed configuration's identity.
 *
 * The DEVICE IDENTITY column stays visible, because it is genuinely useful as a check that the right
 * contact and the right band are loaded, and getting that wrong invalidates everything above.
 *
 * The MIXED-EFFECTS EVIDENCE column is folded away behind a click. Those statistics — the odds ratio
 * per standard deviation, the mixed-effects p-value, the credible-interval flag, stim stability and
 * the per-era odds ratios — are discovery-stage evidence about whether the band was worth committing
 * at all. That question was settled when the band was committed, and this page's question is a
 * different one; they also duplicate what the receiver-operating-characteristic and per-era panels
 * show further down. Folded rather than deleted, because the audit trail is worth keeping one click
 * away.
 */
function BandCandidateIdentity({ bc, envelope }) {
  const [showStats, setShowStats] = useState(false);
  const ev = bc.evidence || {};
  const lbl = bc.label || {};
  const prov = bc.provenance || {};
  return (
    <Card sx={{ width: "100%" }}>
      <MDBox p={2}>
        <MDBox display="flex" alignItems="center" gap={1.2} mb={1} flexWrap="wrap">
          <MDBox px={1.4} py={0.4} sx={{ backgroundColor: verdictColor(bc.verdict),
            color: verdictTextColor(bc.verdict),
            borderRadius: "10px", fontSize: 11, fontWeight: "bold" }}>
            {bc.verdict || "no discovery verdict"}
          </MDBox>
          <MDTypography variant="h6" sx={{ fontSize: 16 }}>
            {`${bc.contact_label || bc.contact || "band"} at ${fmt(bc.center_freq_hz, 1)} Hz`}
          </MDTypography>
          <Chip size="small" label={lbl.pro_metric_label || lbl.pro_metric || "metric"}
            sx={{ height: 20, fontSize: 11 }} />
          {bc.adaptive_valid
            ? <Chip size="small" label="inside the adaptive band (8–30 Hz)"
                sx={{ height: 20, fontSize: 10.5, backgroundColor: PAL.pass, color: "white" }} />
            : <Chip size="small" label="outside the adaptive band"
                sx={{ height: 20, fontSize: 10.5, backgroundColor: PAL.warn,
                  color: PAL.onWarn }} />}
        </MDBox>
        <MDTypography variant="caption" sx={{ display: "block", fontSize: 10.5, color: "#8A8A8A",
          mb: 1 }}>
          The badge above is the discovery-stage verdict this band was committed with. It is a
          different quantity from the reconciled verdict at the top of the page, which is about
          whether the device will accept the configuration and whether the evidence supports it.
        </MDTypography>

        <Grid container spacing={3}>
          <Grid item xs={12} md={6}>
            <MDTypography variant="caption" sx={{ fontSize: 10.5, fontWeight: "bold",
              letterSpacing: 0.4, color: "#999" }}>DEVICE IDENTITY</MDTypography>
            <MDBox mt={0.6}>
              <KV label="Hemisphere">{bc.hemisphere || "not reported"}</KV>
              <KV label="Contact (sensing)">{bc.contact || "not reported"}</KV>
              <KV label="Band">{`${fmt(bc.band_lo_hz, 1)} to ${fmt(bc.band_hi_hz, 1)} Hz `
                + `(${fmt(bc.bandwidth_hz, 1)} Hz wide)`}</KV>
              <KV label="Centre, and FFT-snapped">
                {`${fmt(bc.center_freq_hz, 2)} to ${fmt(bc.snapped_center_freq_hz, 2)} Hz`}
              </KV>
              <KV label="Polarity">{bc.polarity || "not reported"}</KV>
              <KV label="Suggested mode">
                {bc.suggested_mode
                  || <span style={{ color: PAL.warnText }}>none suggested — see the note</span>}
              </KV>
            </MDBox>
          </Grid>
          <Grid item xs={12} md={6}>
            <MDTypography variant="caption" onClick={() => setShowStats((s) => !s)}
              sx={{ fontSize: 10.5, fontWeight: "bold", letterSpacing: 0.4, color: PAL.accent,
                cursor: "pointer", "&:hover": { textDecoration: "underline" } }}>
              {showStats
                ? "HIDE THE DISCOVERY-STAGE STATISTICS"
                : "SHOW THE DISCOVERY-STAGE STATISTICS (AUDIT TRAIL)"}
            </MDTypography>
            {showStats ? (
              <MDBox mt={0.6}>
                <KV label="Odds ratio (per 1 SD)">
                  {`${fmt(ev.odds_ratio)} `}
                  {ev.or_lo != null && ev.or_hi != null
                    ? `(95% CI ${fmt(ev.or_lo)} to ${fmt(ev.or_hi)})` : ""}
                  {ev.credible_ci === false
                    ? <span style={{ color: PAL.fail }}> · interval narrower than the
                        credibility rule allows</span>
                    : ev.credible_ci === true
                      ? <span style={{ color: PAL.pass }}> · credible</span> : null}
                </KV>
                <KV label="Mixed-effects p">{fmtP(ev.p_glmer)}</KV>
                <KV label="Samples and eras">
                  {`${ev.n_matched_samples ?? "not reported"} samples across `
                    + `${ev.n_clusters ?? "not reported"} weekly eras`}
                </KV>
                <KV label="Stim stability">
                  {ev.stim_stable == null ? "not reported"
                    : ev.stim_stable ? "stim-stable" : "stim-dependent"}
                  {ev.stim_lrt_p != null
                    ? ` (likelihood-ratio test p = ${fmtP(ev.stim_lrt_p)})` : ""}
                </KV>
                <KV label="Odds ratio per era">
                  {ev.or_by_era
                    ? ["OFF", "LOW", "HIGH"].map((t) => `${t}: ${fmt(ev.or_by_era[t])}`)
                      .join("  \u00B7  ")
                    : "not reported"}
                </KV>
                <KV label="Label and join">
                  {`${lbl.pro_metric || "not reported"} \u00B7 `
                    + `${(lbl.binarization && lbl.binarization.strategy) || "not reported"} \u00B7 `
                    + `${lbl.join || "not reported"} \u00B7 `
                    + `${lbl.n_pos_days ?? "not reported"} positive days, `
                    + `${lbl.n_neg_days ?? "not reported"} negative`}
                </KV>
              </MDBox>
            ) : null}
          </Grid>
        </Grid>

        {(!bc.adaptive_valid || bc.suggested_mode == null) && bc.suggested_mode_reason ? (
          <MDBox mt={1} p={1} sx={{ backgroundColor: PAL.warnFill, borderRadius: "6px" }}>
            <MDTypography variant="caption" sx={{ fontSize: 10.8, color: PAL.warnText }}>
              {`Deployment note: ${bc.suggested_mode_reason}.`}
              {bc.adaptive_valid_reason ? ` ${bc.adaptive_valid_reason}.` : ""}
            </MDTypography>
          </MDBox>
        ) : null}

        <MDBox mt={1}>
          <MDTypography variant="caption" color="text" sx={{ fontSize: 10.3, fontStyle: "italic" }}>
            {prov.selection_biased ? "Selection-biased pool \u2014 " : ""}
            {prov.selection_note || ""}
            {envelope && envelope.committed_at
              ? ` \u00B7 committed ${new Date(envelope.committed_at).toLocaleString()}` : ""}
          </MDTypography>
        </MDBox>
      </MDBox>
    </Card>
  );
}

function ClosedLoopSim() {
  const navigate = useNavigate();
  const { participant_uid } = useParams();
  const fileRef = useRef(null);

  const [envelope, setEnvelope] = useState(null);   // {band_candidate, participant_uid, committed_at}
  const [cutpoint, setCutpoint] = useState(null);   // chosen operating point, lifted from the ROC
  // The resolved device-LSB threshold, lifted from the LSB panel so the ROC's feature histogram can
  // annotate its cut line with the same value.
  const [lsbThreshold, setLsbThreshold] = useState(null);   // {upperLsb, estimated} | null
  const [showAnalyst, setShowAnalyst] = useState(false);

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
  const [thresholdMode, setThresholdMode] = useState(null);

  useEffect(() => {
    if (!participant_uid) { navigate("/database", { replace: false }); return; }
    setEnvelope(loadBandCandidate(participant_uid));
  }, [participant_uid, navigate]);

  // Tag <body> while this view is mounted so the print stylesheet can scope its "hide everything
  // except the record" rules to this page only, and clean the class up on unmount so printing any
  // other view is unaffected.
  useEffect(() => {
    document.body.classList.add("cl-deploy-root");
    return () => document.body.classList.remove("cl-deploy-root");
  }, []);

  const bc = envelope && envelope.band_candidate;

  // Derive the discovery request knobs ONCE per committed candidate. Building this inline in JSX
  // produced a fresh object identity on every parent re-render, which is listed in every panel's
  // fetch-effect dependencies — so any child state change re-created it and re-fired every panel's
  // fetch, collapsing all figures into their loading state at once.
  const requestParams = useMemo(() => requestParamsFromCandidate(bc), [bc]);

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
  const deploymentReport = useDeploymentReport({
    participantUid: participant_uid,
    bandCandidate: bc && {
      channel: bc.contact,
      centerHz: bc.center_freq_hz,
      bandWidthHz: bc.bandwidth_hz || 5.0,
      sensingHemisphere: bc.hemisphere,
      rateHz: bc.rate_hz,
      pulseWidthUs: bc.pulse_width_us,
      thresholdMode: bc.threshold_mode || "dual",
    },
  });

  const onUpload = (e) => {
    const file = e.target.files && e.target.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      const parsed = parseUploadedCandidate(String(reader.result));
      if (parsed && parsed.band_candidate) {
        commitBandCandidate(participant_uid, parsed.band_candidate);
        setEnvelope(loadBandCandidate(participant_uid));
      }
    };
    reader.readAsText(file);
    e.target.value = "";   // allow re-upload of the same file
  };

  return (
    <DatabaseLayout>
      <MDBox pt={3}>
        <Grid container spacing={2}>
          <Grid item xs={12}>
            <Card sx={{ width: "100%" }}>
              <MDBox p={2} display="flex" flexDirection="row" justifyContent="space-between"
                alignItems="center" flexWrap="wrap" gap={1}>
                <MDBox>
                  <MDTypography variant="h6" fontSize={22}>Closed-Loop Deployment</MDTypography>
                  <MDTypography variant="caption" color="text" sx={{ fontSize: 11.5 }}>
                    {"May this configuration be programmed onto the Percept, and if so what should "
                      + "be entered?"}
                  </MDTypography>
                </MDBox>
                <MDBox display="flex" gap={1} alignItems="center">
                  <input ref={fileRef} type="file" accept="application/json,.json"
                    style={{ display: "none" }} onChange={onUpload} />
                  <MDButton size="small" variant="outlined" color="info"
                    onClick={() => fileRef.current && fileRef.current.click()}>
                    Load BandCandidate JSON
                  </MDButton>
                  {bc ? (
                    <MDButton size="small" variant="text" color="secondary"
                      onClick={() => { clearBandCandidate(participant_uid); setEnvelope(null); }}>
                      Clear
                    </MDButton>
                  ) : null}
                </MDBox>
              </MDBox>
            </Card>
          </Grid>

          {!bc ? (
            <Grid item xs={12}>
              <Card sx={{ width: "100%" }}>
                <MDBox p={3} textAlign="center">
                  <MDTypography variant="h6" sx={{ fontSize: 15, color: "#777" }}>
                    No band has been committed for this participant yet
                  </MDTypography>
                  <MDTypography variant="caption" color="text" display="block" mt={1}
                    sx={{ fontSize: 12 }}>
                    {"Deployability is evaluated for one channel at one centre frequency rather "
                      + "than for a participant, so a candidate configuration has to be chosen "
                      + "before any of this page means anything. Open the Biomarker Exploration "
                      + "view, choose a validated band and commit it, or load a previously "
                      + "downloaded BandCandidate file."}
                  </MDTypography>
                  <MDBox mt={2}>
                    <MDButton size="small" color="info" variant="gradient"
                      onClick={() => navigate(`/reports/biomarkers/${participant_uid}`)}>
                      Go to Biomarker Exploration
                    </MDButton>
                  </MDBox>
                </MDBox>
              </Card>
            </Grid>
          ) : (
            <>
              {/* BAND 0 — one reconciled verdict, computed from both endpoints, sticky. */}
              <Grid item xs={12}>
                <DeploymentDecisionHeader bandCandidate={bc} summary={summary}
                  deploymentReport={deploymentReport} />
              </Grid>

              {/* BAND 1 — what would change the answer, ranked, actor per row. */}
              <Grid item xs={12} id="cl-what-changes">
                <WhatWouldChangeThis report={deploymentReport} />
              </Grid>

              {/* BAND 2 — the device rule ledger. Placed before the evidence because on a device
                  that actuates, whether a configuration is PERMITTED is prior to how well it
                  scores. */}
              <Grid item xs={12} id="cl-rules">
                <DeviceRuleLedger report={deploymentReport} />
              </Grid>

              {/* BAND 3 — the evidence triangle and the three-valued coherence answer. */}
              <Grid item xs={12} id="cl-evidence">
                <EvidenceTrianglePanel report={deploymentReport} />
              </Grid>

              {/* BAND 4 — the transcription surface. Withholds its values while the device verdict
                  is negative. */}
              <Grid item xs={12} id="cl-prescription">
                <PrescriptionPanel report={deploymentReport} mode={thresholdMode}
                  onMode={setThresholdMode} />
              </Grid>

              {/* BAND 5 — the predicted duty cycle, for the mode selected above. */}
              <Grid item xs={12} id="cl-duty">
                <DutyCyclePanel report={deploymentReport} mode={thresholdMode} />
              </Grid>

              <Grid item xs={12}>
                <BandCandidateIdentity bc={bc} envelope={envelope} />
              </Grid>

              {/* The analyst panels, demoted behind one fold. Real evidence, and not the first
                  question at a programming visit. */}
              <Grid item xs={12}>
                <Card sx={{ width: "100%" }}>
                  <MDBox p={1.5} display="flex" justifyContent="space-between"
                    alignItems="center" gap={1} flexWrap="wrap">
                    <MDBox>
                      <MDTypography variant="h6" sx={{ fontSize: 14 }}>
                        Evidence for the analyst, before the visit
                      </MDTypography>
                      <MDTypography variant="caption" sx={{ display: "block", fontSize: 11,
                        color: "#7A7A7A" }}>
                        {"Where the cut-point sits, how the band converts to device units, and "
                          + "whether the discrimination holds up era by era. Folded away because "
                          + `none of it is the first question at the programmer for `
                          + `${bc.contact || "this band"} at ${fmtHz(bc.center_freq_hz)
                            || "its centre"} Hz.`}
                      </MDTypography>
                    </MDBox>
                    <MDButton size="small" variant="outlined" color="info"
                      onClick={() => setShowAnalyst((s) => !s)}
                      sx={{ textTransform: "none", fontSize: 11.5 }}>
                      {showAnalyst ? "Fold these away" : "Show the three analyst panels"}
                    </MDButton>
                  </MDBox>
                </Card>
              </Grid>

              {showAnalyst ? (
                <>
                  <Grid item xs={12} md={6} id="cl-roc">
                    <DeploymentRocPanel participantUid={participant_uid} bandCandidate={bc}
                      requestParams={requestParams} onCutpoint={setCutpoint}
                      lsbThreshold={lsbThreshold} />
                  </Grid>
                  <Grid item xs={12} md={6} id="cl-lsb">
                    <LsbPowerPanel participantUid={participant_uid} bandCandidate={bc}
                      requestParams={requestParams} cutpoint={cutpoint}
                      onLsbThreshold={setLsbThreshold} deploymentReport={deploymentReport} />
                  </Grid>
                  <Grid item xs={12} id="cl-era">
                    <EraRefitPanel participantUid={participant_uid} bandCandidate={bc}
                      requestParams={requestParams} />
                  </Grid>
                </>
              ) : null}

              {/* The printable record. It keeps the gate checklist and loses its own headline
                  verdict and its own threshold cell, so the page cannot contain two answers. */}
              <Grid item xs={12} id="cl-signoff">
                <DeploySignoffCard participantUid={participant_uid} bandCandidate={bc}
                  requestParams={requestParams} cutpoint={cutpoint} summary={summary}
                  deploymentReport={deploymentReport} />
              </Grid>
            </>
          )}
        </Grid>
      </MDBox>
    </DatabaseLayout>
  );
}

export default ClosedLoopSim;
