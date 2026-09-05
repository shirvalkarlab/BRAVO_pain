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
  Card, Grid, Chip, Divider, Table, TableBody, TableCell, TableHead, TableRow,
  FormControl, InputLabel, Select, MenuItem, CircularProgress, Tooltip,
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
import { recomputeSlots } from "views/Reports/moduleCacheKeys";
// Semantic colour roles live in one place for the whole closed-loop family of pages, so a verdict
// that means the same thing on the deployment page and here is drawn in the same ink. The roles
// used below are `neutral` for a question that has not been answered and `warnText` for a caveat
// that has; the failure ink is deliberately not used for either, because neither is a failure.
import PAL from "views/Reports/ClosedLoopSim/palette";

const MODEBAR = { responsive: true, displaylogo: false,
  modeBarButtonsToRemove: ["select2d", "lasso2d", "autoScale2d"] };

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

// Chip appearance for the three states. "Not determinable" takes the neutral ink and an outline,
// never the failure ink and never the same treatment as "not resolved": the first means the
// question could not be put, the second means it was put and answered no, and a reader deciding
// what to do next needs to tell them apart.
const RESOLUTION_CHIP = {
  resolved: { label: "resolved", color: "success", variant: "filled" },
  unresolved: { label: "not resolved", color: "default", variant: "outlined" },
  undeterminable: { label: "not determinable", color: "default", variant: "outlined" },
};

const FIGURES = [
  ["posterior_surface", "Posterior objective surface with the safe set",
   "Predicted pain objective across the frequency x amplitude grid. Lower is better. Tested cells are overlaid; the dashed contour is the safe-set boundary."],
  ["acquisition", "Where the search explores versus exploits",
   "The acquisition surface and its argmax, with the exploration share of each selection. A high exploration share means the surrogate cannot yet separate cells by predicted benefit."],
  ["trajectory", "Search trajectory across simulated batches",
   "Parameters sampled, the safety value at each sample, and the running best estimate, over forward-simulated batches."],
  ["dual_model", "Composite objective against the preference model",
   "The scalar objective and the illustrative preference model on shared axes, with both optima marked. Disagreement between them is informative, not an error."],
  ["coverage", "Coverage: what the grid has never tested",
   "Posterior standard deviation across the grid, with the optimistic bound in never-tested cells. This is the visual form of the unexplored-region audit."],
];

const fmt = (v, d = 2) =>
  (v === null || v === undefined || Number.isNaN(Number(v))) ? "\u2014" : Number(v).toFixed(d);

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
function FigurePanel({ title, blurb, figure }) {
  const ref = useRef(null);
  useEffect(() => {
    const gd = ref.current;
    if (!gd || !figure) return;
    Plotly.react(gd, figure.data || [], figure.layout || {}, MODEBAR);
  }, [figure]);
  // The node is read at cleanup time rather than captured at mount, because the container is not in
  // the page until a figure exists.
  useEffect(() => () => { if (ref.current) Plotly.purge(ref.current); }, []);
  if (!figure) return null;
  return (
    <MDBox mb={3}>
      <MDTypography variant="button" fontWeight="medium">{title}</MDTypography>
      <MDTypography variant="caption" color="text" component="div" sx={{ mb: 1 }}>{blurb}</MDTypography>
      <MDBox ref={ref} sx={{ width: "100%", minHeight: 380 }} />
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
  useEffect(() => {
    if (arm) LAST_ARM.set(String(participant_uid), arm);
  }, [participant_uid, arm]);

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
            Fitting one Gaussian-process surrogate per arm. Every stored session report is read to
            rebuild the exposure history, so the first load after an ingest is the slow one.
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
  const nUnresolved = armStates.filter((s) => s === "unresolved").length;
  const nUndeterminable = armStates.filter((s) => s === "undeterminable").length;
  const armWord = (n) => `${n} arm${n === 1 ? "" : "s"}`;

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
              onRecompute={() => recomputeSlots(participant_uid, [MODULES.stimOptimizer])}
            />
          </Grid>

          {/* ---------- verdict first, before any figure ---------- */}
          <Grid item xs={12}>
            <MDAlert color={supported ? "success" : "info"} dismissible={false}>
              <MDBox>
                <MDTypography variant="button" fontWeight="medium" color="white" component="div">
                  {supported
                    ? "At least one arm resolves its optimum against the setting currently in force"
                    : "The data do not yet support a stimulation parameter recommendation"}
                </MDTypography>
                <MDTypography variant="caption" color="white" component="div" sx={{ mt: 0.5 }}>
                  {supported
                    ? "Only arms marked resolved below have a predicted gain larger than the uncertainty of the difference against the setting in force."
                    : (nUndeterminable === 0
                      ? `For all ${armWord(nUnresolved)}, the predicted gain over the setting `
                        + "currently in force is smaller than the uncertainty of that difference. "
                        + "The surfaces show where to look next, not what to program."
                      : (nUnresolved === 0
                        ? `For ${armWord(nUndeterminable)}, the difference against the setting `
                          + "currently in force could not be formed at all, so no arm has been "
                          + "compared to its incumbent. The surfaces show where to look next, not "
                          + "what to program."
                        : `For ${armWord(nUnresolved)}, the predicted gain over the setting `
                          + "currently in force is smaller than the uncertainty of that "
                          + `difference. A further ${armWord(nUndeterminable)} could not be `
                          + "compared to the setting in force at all. The surfaces show where to "
                          + "look next, not what to program."))}
                </MDTypography>
                {(data.blockers || []).map((b, i) => (
                  <MDTypography key={i} variant="caption" color="white" component="div" sx={{ mt: 0.75 }}>
                    &bull; {b}
                  </MDTypography>
                ))}
              </MDBox>
            </MDAlert>
          </Grid>

          {/* ---------- closed-loop readiness ----------
              A DIFFERENT question from everything above it, and the panel says so. The optimizer
              asks which setting relieves pain best; this asks whether any sensed band moves with
              stimulation amplitude, which is the only lever Adaptive Therapy has. A band can
              predict pain beautifully and be useless as a control signal.

              Do NOT collapse this to a single ready/not-ready chip. The per-cell blocking reasons
              are the content: a refusal because the data cannot support the test and a refusal
              because the response is genuinely absent are different clinical conclusions. */}
          {data.closed_loop && (
            <Grid item xs={12}>
              <Card>
                <MDBox p={2}>
                  <MDBox display="flex" alignItems="center" justifyContent="space-between">
                    <MDTypography variant="h6">Closed-loop readiness (Adaptive Therapy)</MDTypography>
                    {data.closed_loop.available && (
                      <MDBox
                        px={1.5}
                        py={0.4}
                        borderRadius="lg"
                        sx={{
                          // A screen that ran and qualified nothing, and a screen that never ran,
                          // are different states and the badge used to word them identically as
                          // "no deployable control signal" — which reads as a measured finding in
                          // both cases. The served payload carries `n_cells_screened`, so the
                          // second case can be named for what it is. Neither takes the failure
                          // colour: an unscreened participant has not failed anything.
                          backgroundColor: data.closed_loop.ready
                            ? "success.main"
                            : (data.closed_loop.n_cells_screened ? "warning.main" : "text.disabled"),
                        }}
                      >
                        <MDTypography variant="caption" color="white" fontWeight="medium">
                          {data.closed_loop.ready
                            ? `${data.closed_loop.n_cells_deployable} of ${data.closed_loop.n_cells_screened} cells deployable`
                            : (data.closed_loop.n_cells_screened
                              ? `no deployable control signal \u2014 0 of ${data.closed_loop.n_cells_screened} screened cells qualified`
                              : "no cells screened \u2014 deployability not yet assessed")}
                        </MDTypography>
                      </MDBox>
                    )}
                  </MDBox>

                  {!data.closed_loop.available ? (
                    <MDTypography variant="caption" color="text" component="div" sx={{ mt: 1 }}>
                      {data.closed_loop.reason}
                    </MDTypography>
                  ) : (
                    <>
                      <MDTypography variant="caption" color="text" component="div" sx={{ mt: 0.5 }}>
                        Adaptive Therapy can only be driven by a band inside{" "}
                        {(data.closed_loop.adaptive_window_hz || []).join("\u2013")}&nbsp;Hz, and only
                        at a rate of at least {data.closed_loop.min_adaptive_rate_hz}&nbsp;Hz. Its
                        only lever is amplitude, so a candidate band must be shown to MOVE with
                        amplitude &mdash; a separate question from whether it tracks pain.
                      </MDTypography>
                      <MDTypography variant="button" fontWeight="medium" component="div" sx={{ mt: 1 }}>
                        {data.closed_loop.verdict}
                      </MDTypography>

                      {(data.closed_loop.responding_cells || []).length > 0 && (
                        <MDBox sx={{ overflowX: "auto", mt: 1.5 }}>
                          <Table size="small">
                            <TableBody>
                              <TableRow>
                                {["Channel", "Side", "Rate (Hz)", "Bands responding",
                                  "Era-significant", "Amp range (mA)", "Amp limit (mA)",
                                  "Deployable", "Why not"].map((h) => (
                                  <TableCell key={h}>
                                    <MDTypography variant="caption" fontWeight="medium">
                                      {h}
                                    </MDTypography>
                                  </TableCell>
                                ))}
                              </TableRow>
                              {data.closed_loop.responding_cells.map((c, i) => (
                                <TableRow key={i}>
                                  <TableCell>
                                    <MDTypography variant="caption">{c.channel}</MDTypography>
                                  </TableCell>
                                  <TableCell>
                                    <MDTypography variant="caption">{c.hemisphere}</MDTypography>
                                  </TableCell>
                                  <TableCell>
                                    <MDTypography variant="caption">{fmt(c.rate_hz, 0)}</MDTypography>
                                  </TableCell>
                                  <TableCell>
                                    <MDTypography variant="caption">
                                      {c.n_responding} / {c.n_bands}
                                    </MDTypography>
                                  </TableCell>
                                  <TableCell>
                                    <MDTypography variant="caption">
                                      {c.n_era_significant} / {c.n_bands}
                                    </MDTypography>
                                  </TableCell>
                                  <TableCell>
                                    <MDTypography variant="caption">
                                      {fmt(c.amp_low_mA, 1)}&ndash;{fmt(c.amp_high_mA, 1)}
                                    </MDTypography>
                                  </TableCell>
                                  <TableCell>
                                    <MDTypography variant="caption">
                                      {c.amp_limit_mA == null ? "\u2014" : fmt(c.amp_limit_mA, 1)}
                                    </MDTypography>
                                  </TableCell>
                                  <TableCell>
                                    <MDTypography
                                      variant="caption"
                                      fontWeight="medium"
                                      // A cell that does not clear the device constraints has
                                      // not failed in the sense the error ink means; it is simply
                                      // outside what this device can actuate on, and the reason is
                                      // spelled out in the next column. The error ink is reserved
                                      // for a finding that blocks, so this reads in the neutral
                                      // register and the word carries the meaning.
                                      sx={{ color: c.deployable ? undefined : PAL.neutral }}
                                      color={c.deployable ? "success" : "text"}
                                    >
                                      {c.deployable ? "yes" : "no"}
                                    </MDTypography>
                                  </TableCell>
                                  <TableCell sx={{ maxWidth: 420 }}>
                                    <MDTypography variant="caption" color="text">
                                      {c.blocking_reasons || "\u2014"}
                                    </MDTypography>
                                  </TableCell>
                                </TableRow>
                              ))}
                            </TableBody>
                          </Table>
                        </MDBox>
                      )}

                      <MDTypography variant="caption" color="text" component="div" sx={{ mt: 1.5 }}>
                        A cell is deployable only if a majority of scanned bands respond, the slope
                        survives era blocking, and the amplitude contrast sits at or below the flat{" "}
                        {fmt(data.closed_loop.amp_hard_limit_mA, 1)}&nbsp;mA hard limit. That limit is
                        PI-declared and was established by testing at 165&nbsp;Hz; it does not vary
                        with rate or pulse width. An earlier version of this panel applied an
                        energy-matched ceiling that scaled as the square root of 55/f &mdash; that
                        model has been withdrawn, because tolerable amplitude at a given frequency is
                        not governed by total delivered energy. The amplitude condition still matters
                        for the same reason it always did: a response measured only above the
                        amplitude we are willing to program was never deployable evidence.
                      </MDTypography>
                    </>
                  )}
                </MDBox>
              </Card>
            </Grid>
          )}

          {/* ---------- evidence base ---------- */}
          <Grid item xs={12}>
            <Card>
              <MDBox p={2}>
                <MDTypography variant="h6">Evidence base</MDTypography>
                <MDTypography variant="caption" color="text" component="div">
                  An epoch is one continuous exposure to one parameter setting; a new epoch opens
                  whenever any parameter changes. Pain reports inside the wash-in window are excluded.
                </MDTypography>
                <Grid container spacing={2} sx={{ mt: 1 }}>
                  {[
                    ["Exposure epochs", dm.n_epochs],
                    ["Pain reports used", dm.n_reports],
                    ["Left amplitude levels", dm.amp_mA_Left_levels],
                    ["First epoch", dm.t_first ? String(dm.t_first).slice(0, 10) : "\u2014"],
                    ["Last epoch", dm.t_last ? String(dm.t_last).slice(0, 10) : "\u2014"],
                    ["Wash-in (min)", data.washin_min],
                  ].map(([k, v]) => (
                    <Grid item xs={6} md={2} key={k}>
                      <MDTypography variant="caption" color="text" component="div">{k}</MDTypography>
                      <MDTypography variant="h6">{v === null || v === undefined ? "\u2014" : v}</MDTypography>
                    </Grid>
                  ))}
                </Grid>
                {dm.states && (
                  <MDBox mt={2} display="flex" gap={1} flexWrap="wrap">
                    {Object.entries(dm.states).map(([k, v]) => (
                      <Tooltip key={k} title="A hemisphere at 0 mA is a distinct therapeutic state, not the low end of a dose axis, and is modelled separately.">
                        <Chip size="small" variant="outlined" label={`${k.replace(/_/g, " ")}: ${v}`} />
                      </Tooltip>
                    ))}
                  </MDBox>
                )}
              </MDBox>
            </Card>
          </Grid>

          {/* ---------- per-arm table ---------- */}
          <Grid item xs={12}>
            <Card>
              <MDBox p={2}>
                <MDTypography variant="h6">Arms</MDTypography>
                <MDTypography variant="caption" color="text" component="div">
                  One arm is one pain site crossed with one hemisphere, fitted independently. Sites
                  are never blended: the left leg and the back are separate optimization problems.
                  Click a row to show its surfaces.
                </MDTypography>
                <Table size="small" sx={{ mt: 1 }}>
                  <TableHead>
                    <TableRow>
                      {/* The column that decides the verdict is the DIFFERENCE against the setting
                          in force, together with the uncertainty of that difference — so it is a
                          column of the table rather than something the reader assembles from the
                          two posterior columns beside it. "Candidate cell" replaces the old header
                          "Best cell": the cell is where the surrogate's mean is lowest, which is
                          not the same as a setting the evidence recommends, and a header should not
                          say "best" about a cell whose advantage may be indistinguishable from
                          zero. */}
                      {["Arm", "Epochs", "Candidate cell", "Predicted \u00b1 SD",
                        "In force \u00b1 SD", "Gain over in force (\u00b11 SD of the difference)",
                        "Optimum"]
                        .map((h) => (
                          <TableCell key={h}>
                            <MDTypography variant="caption" fontWeight="medium">{h}</MDTypography>
                          </TableCell>
                        ))}
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {Object.entries(arms).map(([label, a]) => {
                      const res = resolutionOf(a);
                      const chip = RESOLUTION_CHIP[res.state];
                      return (
                        <TableRow key={label} hover selected={label === activeArm}
                                  onClick={() => setArm(label)} sx={{ cursor: "pointer" }}>
                          <TableCell><MDTypography variant="caption">{label.replace("__", " \u00b7 ")}</MDTypography></TableCell>
                          <TableCell><MDTypography variant="caption">{a.n_epochs_fitted ?? "\u2014"}</MDTypography></TableCell>
                          <TableCell>
                            <MDTypography variant="caption">
                              {fmt(a.optimum?.freq_hz, 0)} Hz / {fmt(a.optimum?.amp_mA, 1)} mA
                            </MDTypography>
                          </TableCell>
                          <TableCell>
                            <MDTypography variant="caption">
                              {`${fmt(a.optimum?.posterior_mean)} \u00b1 ${fmt(a.optimum?.posterior_sd)}`}
                            </MDTypography>
                          </TableCell>
                          <TableCell>
                            <MDTypography variant="caption">
                              {fmt(a.incumbent_mu)}
                              {a.incumbent_sd === null || a.incumbent_sd === undefined
                                ? "" : ` \u00b1 ${fmt(a.incumbent_sd)}`}
                            </MDTypography>
                          </TableCell>
                          {/* The gain and its interval, in the objective's own units. The interval
                              is one standard deviation of the difference wide on each side, which
                              is the width the resolution rule uses — it is NOT a 95% interval and
                              is not labelled as one. An interval that straddles zero is the visual
                              form of "this arm has not earned a recommendation". */}
                          <TableCell>
                            {res.sdDiff === null ? (
                              <MDTypography variant="caption" sx={{ color: PAL.neutral }}>
                                {"not formable"}
                              </MDTypography>
                            ) : (
                              <MDTypography variant="caption"
                                sx={{ color: res.state === "resolved" ? "inherit" : PAL.warnText }}>
                                {`${res.gain >= 0 ? "+" : ""}${fmt(res.gain)}`}
                                {`  (${res.gain - res.sdDiff >= 0 ? "+" : ""}${fmt(res.gain - res.sdDiff)}`}
                                {` to ${res.gain + res.sdDiff >= 0 ? "+" : ""}${fmt(res.gain + res.sdDiff)})`}
                              </MDTypography>
                            )}
                          </TableCell>
                          <TableCell>
                            <Tooltip title={res.why}>
                              <Chip size="small" color={chip.color} variant={chip.variant}
                                    label={chip.label} />
                            </Tooltip>
                          </TableCell>
                        </TableRow>
                      );
                    })}
                  </TableBody>
                </Table>
                <MDTypography variant="caption" color="text" component="div" sx={{ mt: 1 }}>
                  The objective is a pain score, so lower is better and a POSITIVE gain means the
                  candidate cell is predicted to be better than the setting in force. An arm is
                  marked resolved only when that gain exceeds one standard deviation of the
                  difference itself, propagated from both cells&apos; posteriors as{" "}
                  <em>sqrt(sd_candidate&sup2; + sd_in-force&sup2;)</em>. The joint covariance
                  between the two cells is not carried in this payload, so the propagated standard
                  deviation omits the <em>&minus;2&thinsp;cov</em> term; nearby cells on a smooth
                  kernel are positively correlated, so the omission overstates the uncertainty and
                  the test is strictly conservative &mdash; it can withhold a recommendation it
                  might have supported, but it cannot manufacture one.
                </MDTypography>
                <MDTypography variant="caption" color="text" component="div" sx={{ mt: 0.75 }}>
                  <strong>not resolved</strong> means the comparison was made and the two cells were
                  not separated. <strong>not determinable</strong> means the comparison could not be
                  made at all, because a posterior mean or standard deviation this arm needs is
                  missing or degenerate; it is not a weaker form of the same answer and it calls for
                  a different response, namely fixing the fit rather than collecting more exposure.
                  Neither is a recommendation, and neither is drawn in the failure ink, because in
                  neither case has a setting been shown to be worse.
                </MDTypography>
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
                    <MDTypography variant="h6">{activeArm.replace("__", " \u00b7 ")}</MDTypography>
                    <FormControl size="small" sx={{ minWidth: 240 }}>
                      <InputLabel>Arm</InputLabel>
                      <Select value={activeArm} label="Arm" onChange={(e) => setArm(e.target.value)}>
                        {Object.keys(arms).map((k) => (
                          <MenuItem key={k} value={k}>{k.replace("__", " \u00b7 ")}</MenuItem>
                        ))}
                      </Select>
                    </FormControl>
                  </MDBox>
                  <MDTypography variant="caption" color="text" component="div" sx={{ mt: 0.5 }}>
                    Provenance: {current.provenance?.data_horizon || "undeclared"} &middot; wash-in{" "}
                    {current.provenance?.washin_min ?? "\u2014"} min &middot; amplitude column{" "}
                    {current.provenance?.amp_col || "\u2014"}
                  </MDTypography>
                  <MDTypography variant="caption" color="text" component="div">
                    Kernel: {current.kernel || "\u2014"}
                  </MDTypography>
                  <Divider sx={{ my: 2 }} />

                  {FIGURES.map(([key, title, blurb]) => (
                    <FigurePanel key={key} title={title} blurb={blurb}
                                 figure={(current.figures || {})[key]} />
                  ))}

                  {current.figures_error && (
                    <MDAlert color="warning" dismissible={false}>
                      <MDTypography variant="caption" color="white">
                        Figures could not be built: {current.figures_error}
                      </MDTypography>
                    </MDAlert>
                  )}

                  {(current.queue || []).length > 0 && (
                    <MDBox mt={2}>
                      <MDTypography variant="h6">
                        Where the model is most uncertain (not the clinic schedule)
                      </MDTypography>
                      <MDTypography variant="caption" color="text" component="div">
                        These are cells that have <strong>never been tested</strong>, ordered by
                        expected improvement. That is exactly what makes them informative &mdash; a
                        setting with no reports is where the model knows least &mdash; and it is also
                        why most of them are <strong>not</strong> on the in-clinic testing schedule.
                        The schedule is built by the opposite rule: it uses only combinations of rate,
                        amplitude and pulse width this patient has <strong>already received</strong>,
                        so that tolerability is established before a setting is programmed for a
                        60-second step.
                      </MDTypography>
                      <MDTypography variant="caption" color="text" component="div" sx={{ mt: 0.75 }}>
                        So read this table as the research question, and the clinic schedule as what
                        can be run tomorrow. The two disagree by design. The{" "}
                        <strong>eligible</strong> column marks the rows that satisfy the schedule&apos;s
                        safety rule as they stand; a row marked no is not forbidden, but moving to a
                        combination never delivered before is a clinical decision and needs explicit
                        sign-off rather than being run because the model ranked it highly. Amplitudes
                        are additionally capped at the flat{" "}
                        {fmt((data.closed_loop || {}).amp_hard_limit_mA ?? 5, 1)}&nbsp;mA hard limit.
                      </MDTypography>
                      {/* Explicit column list rather than the first six keys of the payload: the
                          eligibility flag is the whole point of this panel and a positional slice
                          would silently drop it as soon as the backend adds a column. */}
                      <Table size="small" sx={{ mt: 1 }}>
                        <TableHead>
                          <TableRow>
                            {[["rank", "rank"], ["freq_hz", "freq (Hz)"], ["amp_mA", "amp (mA)"],
                              ["posterior_mean", "posterior mean"], ["posterior_sd", "posterior SD"],
                              ["expected_improvement", "exp. improvement"],
                              ["prior_records_at_this_rate_and_amp", "prior records"],
                              ["schedulable_without_new_clinical_signoff", "eligible"]].map(([k, label]) => (
                              <TableCell key={k}>
                                <MDTypography variant="caption" fontWeight="medium">
                                  {label}
                                </MDTypography>
                              </TableCell>
                            ))}
                          </TableRow>
                        </TableHead>
                        <TableBody>
                          {current.queue.slice(0, 10).map((r, i) => (
                            <TableRow key={i}>
                              {["rank", "freq_hz", "amp_mA", "posterior_mean", "posterior_sd",
                                "expected_improvement", "prior_records_at_this_rate_and_amp",
                                "schedulable_without_new_clinical_signoff"].map((h) => (
                                <TableCell key={h}>
                                  {h === "schedulable_without_new_clinical_signoff" ? (
                                    <MDTypography
                                      variant="caption"
                                      fontWeight="medium"
                                      color={r[h] ? "success" : "text"}
                                    >
                                      {r[h] == null ? "\u2014" : r[h] ? "yes" : "no"}
                                    </MDTypography>
                                  ) : (
                                    <MDTypography variant="caption">
                                      {typeof r[h] === "number" ? fmt(r[h], 3) : String(r[h] ?? "\u2014")}
                                    </MDTypography>
                                  )}
                                </TableCell>
                              ))}
                            </TableRow>
                          ))}
                        </TableBody>
                      </Table>
                    </MDBox>
                  )}
                </MDBox>
              </Card>
            </Grid>
          )}
        </Grid>
      </MDBox>
    </DatabaseLayout>
  );
}
