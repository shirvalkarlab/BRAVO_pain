/**
=========================================================
* UF BRAVO Platform -- OPEN-LOOP Stimulation Parameter Optimizer (Shirvalkar Lab)
=========================================================
* Renders the per-arm Bayesian-optimization surfaces returned by /api/queryStimOptimizer.
*
* DESIGN INTENT -- please preserve. This card is built so that it CAN say the data do not support a
* parameter recommendation, which is currently the truthful answer for RCS08. The blockers panel and
* the per-arm "resolved" chip are the result, not decoration: an unresolved arm has a predicted gain
* smaller than the uncertainty of the difference against the setting in force, so its surface says
* where to look next, not what to program. Do NOT add a "recommended settings" banner that reads the
* optimum without gating on `recommendation_supported`.
*
* Added 2026-09-04, and please preserve for the same reason. The arms table now carries the GAIN
* against the setting in force together with one standard deviation of that difference, because
* that difference is the quantity the verdict is about and printing the two posteriors separately
* left the reader to combine four numbers by hand. The per-arm chip has THREE states, not two: an
* arm whose difference was formed and found too small to call reads "not resolved", while an arm
* whose difference could not be formed at all reads "not determinable" — the backend's boolean
* reports both as False, and they call for different responses (collect more exposure versus fix
* the fit). Do NOT collapse those two back together, and do not draw either of them in the failure
* ink: neither says that a setting is worse, only that the comparison has not been earned.
*/

import { useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";

import {
  Card, Grid, Divider, FormControl, InputLabel, Select, MenuItem, CircularProgress, Tooltip,
} from "@mui/material";

import Plotly from "plotly.js-dist";

import MDBox from "components/MDBox";
import MDTypography from "components/MDTypography";
import MDAlert from "components/MDAlert";

import DatabaseLayout from "layouts/DatabaseLayout";
import { SessionController } from "database/session-control";
import { MODULES } from "database/resultCache";
import { useCachedResult } from "database/useCachedResult";

import RecomputeBar from "views/Reports/RecomputeBar";
import CacheStatusLine from "views/Reports/CacheStatusLine";
import { recomputeSlots, STIM_OPTIMIZER_SLOTS } from "views/Reports/moduleCacheKeys";
// The two-stage plan (open loop, then the check that decides whether closed loop may start, then
// closed loop) is a second request to the same endpoint, fetched after this page's own response
// has arrived and cached in its own slot; see useTwoStagePlan.js for why.
import useTwoStagePlan from "./useTwoStagePlan";
import TwoStagePlanCard from "./TwoStagePlanCard";
// The decision strip: the setting programmed now beside the setting the search prefers, per
// side, with the gain drawn against its own uncertainty (2026-09-12, the page redesign, phase 1).
import DecisionStrip from "./DecisionStrip";
// The sensing evidence behind closed-loop readiness, contacts in Medtronic form, reasons folded
// (redesign phase 3).
import SensingEvidenceTable from "./SensingEvidenceTable";
// The 4 arms as small multiples with a shared gain axis (redesign phase 4).
import ArmGainStrip from "./ArmGainStrip";
import { fmtHz as fmtHzU, fmtMa as fmtMaU, siteName } from "./stimFormat";
// The page's one type scale (2026-09-12, after the PI's review of the redesign: nothing under
// 11 px, body 13-14 px, section titles 17 px, the headline 19 px), and the shared reveal control
// with its toggle resized to that scale.
import { TYPE, HEAD, SMALL, SizedFold as Fold } from "./typeScale";
import { TickGlyph, NotTestedGlyph } from "views/Reports/ClosedLoopSim/glyphs";
// Semantic colour roles live in one place for the whole closed-loop family of pages, so a verdict
// that means the same thing on the deployment page and here is drawn in the same ink. The roles
// used below are `neutral` for a question that has not been answered and `warnText` for a caveat
// that has; the failure ink is deliberately not used for either, because neither is a failure.
import PAL from "views/Reports/ClosedLoopSim/palette";

const MODEBAR = { responsive: true, displaylogo: false,
  modeBarButtonsToRemove: ["select2d", "lasso2d", "autoScale2d"] };

/** One cell of the "what to test next" table: a number in the tabular font, never wrapped. */
const QUEUE_CELL = { fontFamily: PAL.mono, fontSize: TYPE.body, whiteSpace: "nowrap" };

/**
 * THE REQUEST THIS VIEW SENDS, WRITTEN OUT IN FULL RATHER THAN LEFT TO THE SERVER'S DEFAULTS.
 *
 * The endpoint takes six optional parameters besides the participant — the pain sites, the
 * hemispheres, the wash-in exclusion window, the figure backend, and the depth and width of the
 * forward simulation behind the trajectory panel. They are documented on `QueryStimOptimizer` in
 * `BRAVO/Server/APIs/DataAnalysis.py` and applied in `modules/StimOptimizer/bravo_service`
 * `run_for_participant`, and the values below are exactly those documented defaults. The request is
 * therefore unchanged in what it asks the server for.
 *
 * What changes is that it is now written down here, which is what allows the result cache to key on
 * it. A cache key has to name everything that changes the answer; a request that relies on the
 * server's defaults names none of it, so a key derived from such a request would be blind to the
 * very parameters this page is about. Writing them out also means that the first control added to
 * this page — a wash-in slider, say — becomes part of the key by being part of this object, rather
 * than by someone remembering to add it in two places.
 */
const OPTIMIZER_REQUEST = {
  Sites: ["left_leg", "back"],
  Hemispheres: ["Left", "Right"],
  WashinMin: 1.0,
  Backend: "plotly",
  NBatches: 3,
  Q: 4,
};

/**
 * THE ARM THE READER LAST LOOKED AT, KEPT AT MODULE SCOPE ALONGSIDE THE CACHED RESULT.
 *
 * This is a route-level component, so navigating away destroys its state. Now that the surfaces
 * themselves survive that trip, resetting the selection to the first arm on return would put the
 * reader back on a different pain site from the one they were reading, with no indication that the
 * page had moved underneath them. Which arm is selected changes nothing about what was computed —
 * every arm is in the one payload — so it belongs here rather than in the cache key.
 */
const LAST_ARM = new Map();

// THE COMPARISON THIS PAGE EXISTS TO SHOW, COMPUTED WHERE IT CAN BE DISPLAYED.
//
// The module's position, which the figures and the withheld recommendation both rest on, is that a
// predicted optimum means nothing until it is resolved against the uncertainty of ITS OWN
// DIFFERENCE from the setting currently in force. The backend applies exactly that test in
// `pipeline.StimArm.surface_can_resolve_its_optimum`: the gain is `incumbent_mu - mu_star` (the
// objective is a pain score, so lower is better and a positive gain means the candidate is
// predicted to be better), the standard deviation of the difference is
// `sqrt(sd_star^2 + incumbent_sd^2)`, and the optimum counts as resolved only when the gain exceeds
// one such standard deviation.
//
// The page used to print the two posterior means and their two separate standard deviations and
// then a bare resolved / not-resolved chip, which left the reader to combine four numbers in their
// head to see the quantity the verdict was actually about. Worse, the chip could not distinguish
// two different situations that the backend's boolean also conflates: an arm whose difference was
// measured and found too small to call, and an arm for which the difference could not be formed at
// all — which happens when either posterior standard deviation is missing or non-finite, and which
// `surface_can_resolve_its_optimum` reports as False along with the genuine negatives. Both sides
// of the difference are in the payload, so the difference and its uncertainty are recomputed here
// and the third state is recovered rather than lost.
//
// UPDATED 2026-09-04: THE COMPARISON AND THE VERDICT NOW BOTH COME FROM THE BACKEND.
//
// This function used to recompute the difference itself and carried its own `RESOLUTION_K = 1.0`
// mirroring `stage1_openloop.RESOLUTION_K`, with a comment asking a future reader to keep the two in
// step. That was a real hazard rather than untidiness: if the constant had changed on the Python
// side, this page would have gone on drawing intervals and resolved/unresolved chips computed
// against the old multiple, sitting beside a verdict computed against the new one, and nothing would
// have failed. Two numbers disagreeing silently is worse than one number being wrong.
//
// Two backend changes removed the need. `optimum_resolved` is no longer passed through `bool()`, so
// the three-valued answer survives serialisation: `true` (the gain exceeds the margin), `false` (it
// was measured and does not), and `null` (the difference could not be formed at all, because a
// posterior is degenerate — typically a stratum that never delivered the incumbent's rate). And each
// arm now carries a `comparison` block with `gain`, `sd_of_difference`, `k` and `margin`, computed
// by the same code that decides the verdict.
//
// So the verdict is READ, and the arithmetic is read alongside it rather than repeated. The
// fallbacks below exist only for a payload predating those changes; when they fire, the page says so
// rather than presenting a locally-derived answer as the served one.
function resolutionOf(a) {
  const num = (x) => (x == null || !Number.isFinite(Number(x)) ? null : Number(x));
  const cmp = (a && a.comparison) || {};
  const served = a ? a.optimum_resolved : undefined;

  let gain = num(cmp.gain);
  let sdDiff = num(cmp.sd_of_difference);
  let k = num(cmp.k);
  let derivedLocally = false;

  // Legacy payload: reconstruct only what is missing, and flag that it was reconstructed.
  if (gain === null || sdDiff === null) {
    const opt = (a && a.optimum) || {};
    const muStar = num(opt.posterior_mean);
    const sdStar = num(opt.posterior_sd);
    const muInc = num(a && a.incumbent_mu);
    const sdInc = num(a && a.incumbent_sd);
    if (muStar !== null && muInc !== null && sdStar !== null && sdInc !== null) {
      const g = muInc - muStar;
      const s = Math.sqrt(sdStar * sdStar + sdInc * sdInc);
      if (Number.isFinite(s) && s > 0) {
        gain = g;
        sdDiff = s;
        derivedLocally = true;
      } else {
        gain = g;
        sdDiff = null;
      }
    }
  }
  if (k === null) k = 1.0;

  // An interval cannot be drawn around a centre that is not known. The renderer decides whether to
  // draw the gain and its band by testing `sdDiff` alone, so a response carrying a standard
  // deviation without a gain would have printed a band around a null centre. Tying them together
  // here keeps that decision in one place rather than adding a second guard at the call site, where
  // it would be easy to add a third display later and forget it.
  if (gain === null) sdDiff = null;

  // The SERVED verdict decides the state. The three cases are distinguished by identity, not by
  // truthiness, because `null` here means the question could not be put and must not read as "no".
  let state;
  let why;
  if (served === true) {
    state = "resolved";
    why = "the predicted gain exceeds one standard deviation of its own difference from the setting "
          + "in force";
  } else if (served === false) {
    state = "unresolved";
    why = "the predicted gain is smaller than one standard deviation of its own difference from the "
          + "setting in force, so the two cells are not separated";
  } else {
    state = "undeterminable";
    why = "the difference against the setting in force could not be formed at all, because one of "
          + "the two posteriors is degenerate — so this arm was not compared, rather than compared "
          + "and found wanting. That needs the fit repaired rather than more exposure at the cell";
  }

  return {
    state,
    gain,
    sdDiff,
    k,
    derivedLocally,
    why: derivedLocally
      ? `${why}. Note that the gain and its standard deviation shown here were reconstructed on `
        + "this page because the response did not carry them, so they are not guaranteed to match "
        + "the quantities the verdict was computed from"
      : why,
  };
}

/**
 * The five figures, with the one that answers the page's question marked as primary.
 *
 * WHY ONE IS LARGER THAN THE OTHERS. Five figures at identical size read as five equally important
 * results, and they are not. The page exists to ask a single question — is the predicted optimum
 * separated from the setting currently in force? — and only the posterior surface answers it. The
 * other four say where to look NEXT, which is a different and secondary question: useful for
 * planning the next visit, not for deciding what to program. Rendering them all the same size left
 * a reader to work out that ranking for themselves, and the ordering alone did not convey it.
 *
 * The safe set is not a sixth figure. It is drawn as a contour ON the posterior surface, and the
 * numeric safety ceilings live in the tables above, so there is no separate safety panel to
 * separate out.
 */
const FIGURES = [
  ["posterior_surface", "Posterior objective surface with the safe set",
   "Predicted pain objective across the frequency x amplitude grid. Lower is better. Tested cells are overlaid; the dashed contour is the safe-set boundary.",
   "primary"],
  ["acquisition", "Where the search explores versus exploits",
   "The acquisition surface and its argmax, with the exploration share of each selection. A high exploration share means the surrogate cannot yet separate cells by predicted benefit.",
   "secondary"],
  ["trajectory", "Search trajectory across simulated batches",
   "Parameters sampled, the safety value at each sample, and the running best estimate, over forward-simulated batches.",
   "secondary"],
  ["dual_model", "Composite objective against the preference model",
   "The scalar objective and the illustrative preference model on shared axes, with both optima marked. Disagreement between them is informative, not an error.",
   "secondary"],
  ["coverage", "Coverage: what the grid has never tested",
   "Posterior standard deviation across the grid, with the optimistic bound in never-tested cells. This is the visual form of the unexplored-region audit.",
   "secondary"],
];

/**
 * One Plotly figure from server-supplied figure JSON.
 *
 * PLOT PERSISTENCE. `Plotly.react` updates the graph that is already in the page, diffing against
 * what is drawn, so a figure whose colours or labels changed does not rebuild the node and does not
 * discard the zoom, pan and legend selections the reader has set. The version this replaces purged
 * the node in the effect's cleanup, which ran before every redraw as well as on unmount — so
 * switching arms, or any change to the figure at all, tore the graph down and built it again from
 * nothing. The purge now happens only when the panel really goes away, which is where it is needed:
 * to release the graph's event handlers and any WebGL context it holds.
 */
function FigurePanel({ title, blurb, figure, prominence, error }) {
  const ref = useRef(null);
  const primary = prominence === "primary";
  useEffect(() => {
    const gd = ref.current;
    if (!gd || !figure) return;
    Plotly.react(gd, figure.data || [], figure.layout || {}, MODEBAR);
  }, [figure]);
  // The node is read at cleanup time rather than captured at mount, because the container is not in
  // the page until a figure exists.
  useEffect(() => () => { if (ref.current) Plotly.purge(ref.current); }, []);

  // A FIGURE THAT FAILED SAYS SO, rather than leaving a gap. This used to `return null` whenever
  // the figure was absent, which made a per-figure failure indistinguishable from a figure that was
  // never requested — and the backend was equally quiet about it, catching each builder's exception
  // and logging at debug level so the payload simply lacked the key. Between the two, a broken
  // figure produced an empty space on the page and no explanation anywhere. The server now returns
  // `figure_errors` keyed by the same name, and this renders it.
  if (!figure) {
    if (!error) return null;
    return (
      <MDBox mb={3} p={1.5} sx={{
        borderRadius: "6px", border: "1px solid #e0c187", backgroundColor: "#fdf6e7",
      }}>
        <MDTypography variant="button" fontWeight="medium">{title}</MDTypography>
        <MDTypography variant="caption" display="block" sx={{ fontSize: TYPE.body, color: "#8a6a1f" }}>
          {`This figure could not be built, so it is absent rather than empty. `
            + `${error.error_type || "Error"}: ${error.message || "no message supplied"}`}
        </MDTypography>
        <MDTypography variant="caption" display="block" sx={{ fontSize: TYPE.small, color: "#8a6a1f" }}>
          {`Builder: ${error.builder || "unknown"}. The other figures on this page are unaffected.`}
        </MDTypography>
      </MDBox>
    );
  }

  return (
    <MDBox mb={primary ? 4 : 3}>
      <MDTypography variant={primary ? "h6" : "button"} fontWeight="medium"
        sx={{ fontSize: primary ? TYPE.section : TYPE.num }}>
        {title}
      </MDTypography>
      <MDTypography variant="caption" color="text" component="div" sx={{ mb: 1, fontSize: TYPE.body }}>{blurb}</MDTypography>
      {/* The primary figure is given roughly two thirds more height. The question it answers is
          read off the surface itself — whether the optimum and the incumbent are separated — and
          that is exactly the judgement a cramped colour map makes hard. */}
      <MDBox ref={ref} sx={{ width: "100%", minHeight: primary ? 620 : 380 }} />
    </MDBox>
  );
}

export default function StimOptimizer() {
  const { participant_uid } = useParams();

  const cached = useCachedResult({
    moduleKey: MODULES.stimOptimizer,
    uid: participant_uid,
    // The request, minus the participant, is the cache key: the participant is already the other
    // half of the cache slot, so including it would put the same value in the key twice.
    settings: OPTIMIZER_REQUEST,
    enabled: !!participant_uid,
    fetcher: () => SessionController.query("/api/queryStimOptimizer",
      { ParticipantId: participant_uid, ...OPTIMIZER_REQUEST })
      .then((response) => (response && response.data) || {}),
  });

  const data = cached.data;
  const loading = cached.loading;
  const errorText = cached.err;

  const [arm, setArm] = useState(() => LAST_ARM.get(String(participant_uid)) || null);
  // Whether the surfaces fold has been opened once; the Plotly panels mount only then.
  const [figuresMounted, setFiguresMounted] = useState(false);
  useEffect(() => {
    if (arm) LAST_ARM.set(String(participant_uid), arm);
  }, [participant_uid, arm]);

  // THE TWO-STAGE PLAN IS FETCHED ONLY ONCE THE PAGE'S OWN RESPONSE HAS ARRIVED. `afterMain` is
  // this page's `data`; while it is null the hook issues nothing, so the first paint is unchanged.
  // Called here, before any early return, because a hook must run on every render.
  const twoStage = useTwoStagePlan({
    participantUid: participant_uid,
    baseRequest: OPTIMIZER_REQUEST,
    afterMain: cached.data,
  });

  // THE SELECTED ARM IS DERIVED, NOT ASSIGNED IN THE FETCH CALLBACK.
  //
  // It used to be set from inside the response handler, which worked only because a response always
  // arrived. Now that a result can come back from the cache without any request being made, that
  // assignment would never run on a return visit and the page would restore its table and its
  // verdict with no arm selected and no surfaces below them. Deriving the selection from whatever
  // arms the payload actually contains covers both paths with one rule, and it also repairs the
  // case where a recompute returns a payload that no longer carries the arm that was selected.
  const armKeys = Object.keys((data && data.arms) || {});
  const activeArm = arm && armKeys.includes(arm) ? arm : (armKeys[0] || null);

  // A spinner is shown while a request is in flight AND on the very first paint before the hook's
  // effect has started one. Without that second condition the page would show its "no parameter
  // surface could be built" notice for one frame on every first load, which is a false statement
  // about the data rather than a cosmetic flash.
  if (loading || (!cached.hasCached && !errorText)) {
    return (
      <DatabaseLayout>
        <MDBox pt={3} display="flex" alignItems="center" justifyContent="center" gap={2}>
          <CircularProgress size={22} />
          <MDTypography variant="body2">
            Loading this participant&apos;s recordings and the stored settings history, and running the
            closed-loop readiness screen over every sensing contact and rate; the four surface fits
            themselves take about a second. About ten seconds in all; the first load after an ingest
            also rebuilds the settings history from the stored session reports and is slower.
          </MDTypography>
        </MDBox>
      </DatabaseLayout>
    );
  }

  if (errorText || !data || data.available === false) {
    return (
      <DatabaseLayout>
        <MDBox pt={3}>
          <MDAlert color="warning" dismissible={false}>
            <MDTypography variant="body2" color="white">
              No parameter surface could be built.{" "}
              {errorText || data?.reason || "This participant has no exposure epochs carrying pain reports."}
            </MDTypography>
          </MDAlert>
        </MDBox>
      </DatabaseLayout>
    );
  }

  const dm = data.design_matrix || {};
  const arms = data.arms || {};
  const current = (activeArm && arms[activeArm]) || null;
  const supported = data.recommendation_supported === true;
  // The banner used to state, whenever a recommendation was withheld, that "for every arm the
  // predicted gain over the setting currently in force is smaller than the uncertainty of that
  // difference". That is a positive claim about a measurement, and it is only true of the arms
  // whose difference could actually be formed. An arm whose posterior at the incumbent cell is
  // missing or degenerate contributes no such measurement, and asserting one on its behalf is the
  // same class of error as the resolved/not-resolved chip made: it turns "we could not tell" into
  // "we checked and it is not enough". The two populations are counted here so the banner can
  // report each of them.
  const armStates = Object.values(arms).map((a) => resolutionOf(a).state);
  const nUndeterminable = armStates.filter((s) => s === "undeterminable").length;
  const nResolved = armStates.filter((s) => s === "resolved").length;
  const resolutions = Object.fromEntries(Object.entries(arms).map(([k, a]) => [k, resolutionOf(a)]));

  return (
    <DatabaseLayout>
      <MDBox pt={3}>
        <Grid container spacing={2}>

          {/* The Recompute control comes before the verdict, because whether the verdict was
              computed under the settings now on the page has to be readable before the verdict is
              read. Every surface below it is served from memory until it is pressed. */}
          <Grid item xs={12}>
            <RecomputeBar
              title="stim parameter optimizer"
              stale={cached.stale}
              staleReasons={cached.staleReasons}
              computedAt={cached.computedAt}
              loading={cached.loading}
              notKept={cached.notKept}
              // Both slots: the page's own response and the two-stage plan fetched after it.
              onRecompute={() => recomputeSlots(participant_uid, STIM_OPTIMIZER_SLOTS)}
            />
            <CacheStatusLine status={data ? data.cache_status : null} />
          </Grid>

          {/* ---------- the decision, before any figure (redesign phase 1, 2026-09-12) ----------
              One headline computed from the counts, then the per-side strip. The six model
              blockers are still here, one click away; what changed is that the values now lead
              and the sentences follow. */}
          <Grid item xs={12}>
            <Card>
              <MDBox p={2}>
                <MDBox display="flex" alignItems="center" gap={1} flexWrap="wrap">
                  <MDTypography variant="h6" sx={{ fontSize: TYPE.headline }}>
                    {supported
                      ? `Program: ${nResolved} of ${armStates.length} arms resolve a gain larger than its own uncertainty`
                      : `No setting is recommended today: ${nResolved} of ${armStates.length} arms resolve a gain larger than its own uncertainty`}
                  </MDTypography>
                  {nUndeterminable > 0 && (
                    <MDTypography variant="caption" sx={{ fontSize: TYPE.body, color: PAL.neutral }}>
                      {`· ${nUndeterminable} of ${armStates.length} could not be compared at all`}
                    </MDTypography>
                  )}
                </MDBox>
                <MDBox mt={2}>
                  <DecisionStrip arms={arms} plan={twoStage.data} planLoading={twoStage.loading}
                    planErr={twoStage.err} inForce={data.in_force_by_side || null} />
                </MDBox>
                {(data.blockers || []).length > 0 && (
                  <Fold show={`Why no setting is recommended (${(data.blockers || []).length} reasons from the model)`}
                    hide="Hide the reasons">
                    {(data.blockers || []).map((b, i) => (
                      <MDTypography key={i} variant="caption" color="text" component="div"
                        sx={{ mt: 0.6, fontSize: TYPE.body }}>
                        &bull; {b}
                      </MDTypography>
                    ))}
                  </Fold>
                )}
              </MDBox>
            </Card>
          </Grid>

          {/* ---------- the sensing evidence behind closed-loop readiness (redesign phase 3) ----------
              A DIFFERENT question from the strip above it: the optimizer asks which setting
              relieves pain best; this asks whether any sensed band moves with stimulation current,
              which is the only lever adaptive mode has. The per-row reasons stay, folded, because a
              refusal for want of data and a refusal on a measured negative are different clinical
              conclusions. */}
          {data.closed_loop && (
            <Grid item xs={12}>
              <Card>
                <MDBox p={2}>
                  <SensingEvidenceTable closedLoop={data.closed_loop} />
                </MDBox>
              </Card>
            </Grid>
          )}

          {/* ---------- evidence base, one row of counts (redesign phase 4) ---------- */}
          <Grid item xs={12}>
            <Card>
              <MDBox p={2}>
                <MDBox display="flex" alignItems="baseline" gap={1} flexWrap="wrap">
                  <MDTypography variant="h6" sx={{ fontSize: TYPE.section }}>Evidence base</MDTypography>
                  <MDTypography variant="caption" sx={SMALL}>
                    a stretch is one continuous exposure to one setting; reports inside the wash-in are excluded
                  </MDTypography>
                </MDBox>
                <MDBox mt={1.2} display="flex" columnGap={4} rowGap={1.5} flexWrap="wrap">
                  {[
                    ["stretches of unchanged settings", dm.n_epochs],
                    ["pain reports used", dm.n_reports],
                    ["first to last", `${dm.t_first ? String(dm.t_first).slice(0, 10) : "—"} → ${dm.t_last ? String(dm.t_last).slice(0, 10) : "—"}`],
                    ["wash-in", data.washin_min != null ? `${data.washin_min} min` : "—"],
                    ["left currents delivered", dm.amp_mA_Left_range ? `${Number(dm.amp_mA_Left_range[0]).toFixed(1)}–${Number(dm.amp_mA_Left_range[1]).toFixed(1)} mA` : "—"],
                    ["right currents delivered", dm.amp_mA_Right_range ? `${Number(dm.amp_mA_Right_range[0]).toFixed(1)}–${Number(dm.amp_mA_Right_range[1]).toFixed(1)} mA` : "—"],
                  ].map(([k, v]) => (
                    <MDBox key={k}>
                      <MDTypography variant="caption" component="div" sx={HEAD}>{k}</MDTypography>
                      <MDTypography variant="h6" sx={{ fontSize: TYPE.numLarge, fontFamily: PAL.mono, whiteSpace: "nowrap" }}>{v === null || v === undefined ? "—" : v}</MDTypography>
                    </MDBox>
                  ))}
                  {dm.states && (
                    <MDBox>
                      <MDTypography variant="caption" component="div" sx={HEAD}>stretches by state</MDTypography>
                      <Tooltip title="A side at 0 mA is a distinct therapeutic state, not the low end of a dose axis, and is modelled separately.">
                        <MDTypography variant="h6" sx={{ fontSize: TYPE.num, fontFamily: PAL.mono }}>
                          {Object.entries(dm.states).map(([k, v]) => `${k.replace(/_/g, " ")} ${v}`).join(" · ")}
                        </MDTypography>
                      </Tooltip>
                    </MDBox>
                  )}
                </MDBox>
              </MDBox>
            </Card>
          </Grid>

          {/* ---------- the 4 arms as small multiples (redesign phase 4) ---------- */}
          <Grid item xs={12}>
            <Card>
              <MDBox p={2}>
                <MDBox display="flex" alignItems="baseline" gap={1} flexWrap="wrap">
                  <MDTypography variant="h6" sx={{ fontSize: TYPE.section }}>Arms: each pain site on each side, fitted on its own</MDTypography>
                  <MDTypography variant="caption" sx={SMALL}>
                    click a cell to show its model surfaces below
                  </MDTypography>
                </MDBox>
                <MDBox mt={1.5}>
                  <ArmGainStrip arms={arms} resolutions={resolutions} activeArm={activeArm} onSelect={setArm} />
                </MDBox>
              </MDBox>
            </Card>
          </Grid>

          {/* ---------- selected arm ---------- */}
          {current && (
            <Grid item xs={12}>
              <Card>
                <MDBox p={2}>
                  <MDBox display="flex" alignItems="center" justifyContent="space-between"
                         flexWrap="wrap" gap={2}>
                    <MDTypography variant="h6" sx={{ fontSize: TYPE.section }}>
                      {`${siteName(current.site)} · ${current.hemisphere} side: model surfaces and what to test next`}
                    </MDTypography>
                    {/* The arm selector, sized as an ordinary control beside the title rather
                        than a small field in the corner. */}
                    <FormControl size="medium" sx={{ minWidth: 300 }}>
                      <InputLabel sx={{ fontSize: TYPE.num }}>Arm</InputLabel>
                      <Select value={activeArm} label="Arm" onChange={(e) => setArm(e.target.value)}
                        sx={{ fontSize: TYPE.num, minHeight: 44, "& .MuiSelect-select": { fontSize: TYPE.num, py: 1.4 } }}>
                        {Object.keys(arms).map((k) => (
                          <MenuItem key={k} value={k} sx={{ fontSize: TYPE.num }}>{`${siteName(arms[k].site)} · ${arms[k].hemisphere}`}</MenuItem>
                        ))}
                      </Select>
                    </FormControl>
                  </MDBox>
                  <Divider sx={{ my: 1.5 }} />

                  {/* THE 5 SURFACES, FOLDED, MOUNTED ON FIRST REVEAL (redesign phase 4). They are
                      the same server-drawn figures in the same order (the posterior surface first
                      and largest, per the figure conventions); nothing about them changed. A Plotly
                      graph first drawn in a hidden container measures itself at 0 px wide, so the
                      panels are rendered only once the fold has been opened. */}
                  <Fold show="Show the 5 model surfaces (the first answers whether the candidate is separated from the setting in force; the other 4 say where to look next)"
                    hide="Hide the model surfaces" onChange={(o) => { if (o) setFiguresMounted(true); }}>
                    {/* Where the fitted surfaces came from and the kernel that was fitted: the two
                        lines a reader of the figures needs and nobody else does, so they sit inside
                        the fold with the figures (PI's review, 2026-09-12). */}
                    <MDTypography variant="caption" color="text" component="div" sx={{ fontSize: TYPE.small, mb: 0.4 }}>
                      Provenance: {current.provenance?.data_horizon || "undeclared"} &middot; wash-in{" "}
                      <span style={{ whiteSpace: "nowrap" }}>{current.provenance?.washin_min ?? "\u2014"} min</span>
                      {" "}&middot; amplitude column {current.provenance?.amp_col || "\u2014"}
                    </MDTypography>
                    <MDTypography variant="caption" color="text" component="div"
                      sx={{ fontSize: TYPE.small, mb: 1.2, fontFamily: PAL.mono, wordBreak: "normal" }}>
                      Kernel: {current.kernel || "\u2014"}
                    </MDTypography>
                    {figuresMounted && FIGURES.filter(([, , , p]) => p === "primary").map(([key, title, blurb, prom]) => (
                      <FigurePanel key={key} title={title} blurb={blurb} prominence={prom}
                                   figure={(current.figures || {})[key]}
                                   error={(current.figure_errors || {})[key]} />
                    ))}
                    {figuresMounted && (
                      <MDTypography variant="caption" display="block" sx={{ ...HEAD, mb: 1 }}>
                        where to look next
                      </MDTypography>
                    )}
                    {figuresMounted && FIGURES.filter(([, , , p]) => p !== "primary").map(([key, title, blurb, prom]) => (
                      <FigurePanel key={key} title={title} blurb={blurb} prominence={prom}
                                   figure={(current.figures || {})[key]}
                                   error={(current.figure_errors || {})[key]} />
                    ))}
                    {current.figures_error && (
                      <MDAlert color="warning" dismissible={false}>
                        <MDTypography variant="caption" color="white" sx={{ fontSize: TYPE.body }}>
                          Figures could not be built: {current.figures_error}
                        </MDTypography>
                      </MDAlert>
                    )}
                  </Fold>

                  {(current.queue || []).length > 0 && (
                    <MDBox mt={2}>
                      <MDBox display="flex" alignItems="baseline" gap={1} flexWrap="wrap">
                        <MDTypography variant="h6" sx={{ fontSize: TYPE.section }}>What to test at the next visit</MDTypography>
                        <MDTypography variant="caption" sx={SMALL}>
                          {`cells never tested, ranked by expected improvement · ${current.queue.slice(0, 10).filter((r) => r.schedulable_without_new_clinical_signoff === true).length} of ${Math.min(10, current.queue.length)} eligible without new sign-off · currents capped at ${fmtMaU((data.closed_loop || {}).amp_hard_limit_mA ?? 5)}`}
                        </MDTypography>
                      </MDBox>
                      {/* The table takes the card's width: fixed-minimum columns that share the
                          remaining space, rows at 13 px under 11 px headers. */}
                      <MDBox mt={1} sx={{ display: "grid",
                        gridTemplateColumns: "minmax(56px, 0.5fr) minmax(90px, 1fr) minmax(100px, 1fr) minmax(130px, 1.2fr) minmax(110px, 1fr) minmax(170px, 1.4fr) minmax(120px, 1fr) minmax(90px, 0.8fr) minmax(120px, 1fr)",
                        columnGap: "14px", rowGap: "8px", alignItems: "center" }}>
                        {["rank", "rate", "current", "predicted (pts)", "±1 SD (pts)", "expected improvement", "prior records", "eligible", "closed loop"].map((h) => (
                          <MDTypography key={h} variant="caption" sx={{ ...HEAD, alignSelf: "end" }}>{h}</MDTypography>
                        ))}
                        {current.queue.slice(0, 10).map((r, i) => [
                          <span key={`${i}-a`} style={QUEUE_CELL}>{r.rank ?? i + 1}</span>,
                          <span key={`${i}-b`} style={QUEUE_CELL}>{fmtHzU(r.freq_hz)}</span>,
                          <span key={`${i}-c`} style={QUEUE_CELL}>{fmtMaU(r.amp_mA)}</span>,
                          <span key={`${i}-d`} style={QUEUE_CELL}>{typeof r.posterior_mean === "number" ? `${r.posterior_mean >= 0 ? "+" : "−"}${Math.abs(r.posterior_mean).toFixed(2)}` : "—"}</span>,
                          <span key={`${i}-e`} style={QUEUE_CELL}>{typeof r.posterior_sd === "number" ? r.posterior_sd.toFixed(2) : "—"}</span>,
                          <span key={`${i}-f`} style={QUEUE_CELL}>{typeof r.expected_improvement === "number" ? r.expected_improvement.toFixed(3) : "—"}</span>,
                          <span key={`${i}-g`} style={QUEUE_CELL}>{r.prior_records_at_this_rate_and_amp ?? "—"}</span>,
                          <span key={`${i}-h`} style={{ display: "inline-flex" }}>
                            {r.schedulable_without_new_clinical_signoff == null ? <span style={{ color: "#9A9A9A", fontSize: TYPE.body }}>—</span>
                              : (r.schedulable_without_new_clinical_signoff ? <TickGlyph label="eligible without new sign-off" size={17} /> : <NotTestedGlyph label="needs sign-off: never delivered before" size={17} />)}
                          </span>,
                          /* Whether the device's closed-loop mode could use this cell at all (its rate
                             at or above the adaptive minimum), read from the row's own
                             `adaptive_capable` (review S6, 2026-09-12). The list is not held to the
                             envelope -- that is the PI's call -- but a cell it cannot use says so. */
                          <span key={`${i}-i`} style={{ ...QUEUE_CELL, color: r.adaptive_capable === false ? "#B03A2E" : QUEUE_CELL.color }}>
                            {r.adaptive_capable == null ? "—" : (r.adaptive_capable ? "usable" : "adaptive cannot use")}
                          </span>,
                        ])}
                      </MDBox>
                      <Fold show="Why this list and the clinic schedule disagree by design" hide="Hide" mt={1}>
                        <MDTypography variant="caption" color="text" component="div" sx={{ fontSize: TYPE.body }}>
                          These are cells that have never been tested, ordered by expected
                          improvement. That is exactly what makes them informative, a setting with no
                          reports is where the model knows least, and it is also why most of them are
                          not on the in-clinic testing schedule. The schedule is built by the opposite
                          rule: it uses only combinations of rate, current and pulse width this
                          patient has already received, so that tolerability is established before a
                          setting is programmed for a 60-second step. A row not marked eligible is not
                          forbidden, but moving to a combination never delivered before is a clinical
                          decision and needs explicit sign-off rather than being run because the
                          model ranked it highly.
                        </MDTypography>
                      </Fold>
                    </MDBox>
                  )}
                </MDBox>
              </Card>
            </Grid>
          )}

          {/* ---------- the two-stage plan, after every figure (PI, 2026-09-12) ---------- */}
          <Grid item xs={12}>
            <TwoStagePlanCard plan={twoStage.data} loading={twoStage.loading} err={twoStage.err} />
          </Grid>
        </Grid>
      </MDBox>
    </DatabaseLayout>
  );
}
