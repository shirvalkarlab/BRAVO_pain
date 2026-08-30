/**
=========================================================
* UF BRAVO Platform -- Stimulation Parameter Optimizer (Shirvalkar Lab)
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
                      <MDTypography variant="h6">What to test next</MDTypography>
                      <MDTypography variant="caption" color="text" component="div">
                        Never-tested cells ordered by expected improvement. While no optimum is
                        resolved, this queue is the actionable output of the module.
                      </MDTypography>
                      <Table size="small" sx={{ mt: 1 }}>
                        <TableHead>
                          <TableRow>
                            {Object.keys(current.queue[0]).slice(0, 6).map((h) => (
                              <TableCell key={h}>
                                <MDTypography variant="caption" fontWeight="medium">
                                  {h.replace(/_/g, " ")}
                                </MDTypography>
                              </TableCell>
                            ))}
                          </TableRow>
                        </TableHead>
                        <TableBody>
                          {current.queue.slice(0, 10).map((r, i) => (
                            <TableRow key={i}>
                              {Object.keys(current.queue[0]).slice(0, 6).map((h) => (
                                <TableCell key={h}>
                                  <MDTypography variant="caption">
                                    {typeof r[h] === "number" ? fmt(r[h], 3) : String(r[h] ?? "\u2014")}
                                  </MDTypography>
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
