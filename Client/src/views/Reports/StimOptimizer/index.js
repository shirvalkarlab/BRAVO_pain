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
*/

import { useCallback, useEffect, useRef, useState } from "react";
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

const MODEBAR = { responsive: true, displaylogo: false,
  modeBarButtonsToRemove: ["select2d", "lasso2d", "autoScale2d"] };

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

/** One Plotly figure from server-supplied figure JSON. Plotly.react-once discipline, purge on unmount. */
function FigurePanel({ title, blurb, figure }) {
  const ref = useRef(null);
  useEffect(() => {
    const gd = ref.current;
    if (!gd || !figure) return undefined;
    Plotly.react(gd, figure.data || [], figure.layout || {}, MODEBAR);
    return () => { if (gd) Plotly.purge(gd); };
  }, [figure]);
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
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [errorText, setErrorText] = useState(null);
  const [arm, setArm] = useState(null);

  const load = useCallback(() => {
    setLoading(true); setErrorText(null);
    SessionController.query("/api/queryStimOptimizer", {
      ParticipantId: participant_uid, Backend: "plotly",
    }).then((response) => {
      const d = (response && response.data) || {};
      setData(d); setLoading(false);
      const keys = Object.keys(d.arms || {});
      setArm((prev) => (prev && keys.includes(prev) ? prev : (keys[0] || null)));
    }).catch((error) => {
      setLoading(false);
      setErrorText(String((error && error.message) || error));
    });
  }, [participant_uid]);

  useEffect(() => { load(); }, [load]);

  if (loading) {
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
  const current = (arm && arms[arm]) || null;
  const supported = data.recommendation_supported === true;

  return (
    <DatabaseLayout>
      <MDBox pt={3}>
        <Grid container spacing={2}>

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
                    : "For every arm, the predicted gain over the setting currently in force is smaller than the uncertainty of that difference. The surfaces show where to look next, not what to program."}
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
                          backgroundColor: data.closed_loop.ready ? "success.main" : "warning.main",
                        }}
                      >
                        <MDTypography variant="caption" color="white" fontWeight="medium">
                          {data.closed_loop.ready
                            ? `${data.closed_loop.n_cells_deployable} of ${data.closed_loop.n_cells_screened} cells deployable`
                            : "no deployable control signal"}
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
                                      color={c.deployable ? "success" : "error"}
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
                      {["Arm", "Epochs", "Best cell", "Predicted", "\u00b1 SD", "In force", "Optimum"]
                        .map((h) => (
                          <TableCell key={h}>
                            <MDTypography variant="caption" fontWeight="medium">{h}</MDTypography>
                          </TableCell>
                        ))}
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {Object.entries(arms).map(([label, a]) => (
                      <TableRow key={label} hover selected={label === arm}
                                onClick={() => setArm(label)} sx={{ cursor: "pointer" }}>
                        <TableCell><MDTypography variant="caption">{label.replace("__", " \u00b7 ")}</MDTypography></TableCell>
                        <TableCell><MDTypography variant="caption">{a.n_epochs_fitted ?? "\u2014"}</MDTypography></TableCell>
                        <TableCell>
                          <MDTypography variant="caption">
                            {fmt(a.optimum?.freq_hz, 0)} Hz / {fmt(a.optimum?.amp_mA, 1)} mA
                          </MDTypography>
                        </TableCell>
                        <TableCell><MDTypography variant="caption">{fmt(a.optimum?.posterior_mean)}</MDTypography></TableCell>
                        <TableCell><MDTypography variant="caption">{fmt(a.optimum?.posterior_sd)}</MDTypography></TableCell>
                        <TableCell>
                          <MDTypography variant="caption">
                            {fmt(a.incumbent_mu)}
                            {a.incumbent_sd === null || a.incumbent_sd === undefined
                              ? "" : ` \u00b1 ${fmt(a.incumbent_sd)}`}
                          </MDTypography>
                        </TableCell>
                        <TableCell>
                          <Chip size="small"
                                color={a.optimum_resolved ? "success" : "default"}
                                variant={a.optimum_resolved ? "filled" : "outlined"}
                                label={a.optimum_resolved ? "resolved" : "not resolved"} />
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
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
                    <MDTypography variant="h6">{arm.replace("__", " \u00b7 ")}</MDTypography>
                    <FormControl size="small" sx={{ minWidth: 240 }}>
                      <InputLabel>Arm</InputLabel>
                      <Select value={arm} label="Arm" onChange={(e) => setArm(e.target.value)}>
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
