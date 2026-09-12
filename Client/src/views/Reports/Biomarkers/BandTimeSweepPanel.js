/**
 * HOW WELL EACH BAND TRACKS PAIN, AT EVERY LENGTH OF SIGNAL AVERAGED INTO ONE MEASUREMENT.
 *
 * The last section of the biomarker exploration page, above the device-scale calibration panels.
 * It answers one question over a grid: if the band power a decision were made on was the average
 * over the last N seconds of recording, how well would that number track the pain score the reader
 * chooses here? Band centre on one axis, length of signal on the other, two numbers per cell.
 *
 * WHY IT HAS ITS OWN BUTTON. The whole page follows the rule that nothing is computed until the
 * reader asks for it, and this section is the most expensive thing on it: ten matchings of every
 * pain report against the recording history, per sensing contact pair. It therefore fetches on its
 * own rather than riding the page's main result, and it does so through the same endpoint with
 * `BandTimeSweep` set, which makes the server return the sweep alone.
 *
 * WHAT IT TAKES FROM THE TOP OF THE PAGE, AND THE ONE THING IT DOES NOT. Every control that
 * changes which recording is matched to which pain report is passed straight through in
 * `requestParams` -- the match tolerance, whether a window may serve more than one report, how high
 * pain is separated from low, the outlier rule. The reader's choice of pain score is the ONE
 * override, sent as `SweepMetric`, because the PI asked for that choice to live in this section;
 * its options are the page's own list so the two selectors can never offer different scores. The
 * top-of-page slider for how much recording goes into one measurement is deliberately NOT passed,
 * because that quantity is the axis this section sweeps.
 *
 * TWO THINGS THIS PANEL MUST KEEP SAYING, both of them requirements rather than decoration.
 *   1. The value in each row of each table is the LARGEST of ten lengths of signal, chosen after
 *      seeing all ten, so it is optimistic and its ordinary p-value is not the probability of what
 *      was done. The note saying so is rendered in the panel, not only in a caption, and the
 *      server's own verdict for a row requires the value to beat what the same best-of-ten choice
 *      reaches on shuffled pain scores.
 *   2. For telling high-pain reports from low-pain ones, the value that means no discrimination is
 *      0.5 and not 0. The heat map's colour scale is centred on 0.5 by the server, an interval that
 *      spans 0.5 is rendered as UNSETTLED in the neutral ink, and it is never given the same
 *      treatment as a value that was measured and came out weak.
 *
 * The figures arrive as Plotly figure descriptions computed on the server, with every piece of
 * their text derived from the numbers in the same pass. Nothing is rendered to an image anywhere;
 * the browser draws them. They follow the module's drawing discipline: drawn once per result with
 * Plotly.react, mounted on first reveal so a graph is never measured inside a collapsed container,
 * and purged on unmount only.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import Plotly from "plotly.js-dist";

import { Card, Grid, Select, MenuItem, FormControl, CircularProgress } from "@mui/material";

import MDBox from "components/MDBox";
import MDTypography from "components/MDTypography";
import MDButton from "components/MDButton";

import { SessionController } from "database/session-control";
import PAL from "views/Reports/ClosedLoopSim/palette";

const num = (v, d = 3) => (v == null || !Number.isFinite(Number(v)) ? "—" : Number(v).toFixed(d));
const sec = (v) => (v == null || !Number.isFinite(Number(v)) ? "—" : `${Number(v)} s`);

// The three answers the server returns, and the ink each one is drawn in. They are three states and
// not two: "not settled" is a question that was asked and not answered, "not assessed" is a question
// that could not be asked at all, and neither of them is a negative result. Both are drawn in the
// neutral ink so that no reader takes an unsettled row for a band that was shown to carry nothing.
const ANSWER_INK = {
  established: PAL.ok || "#009E73",
  not_resolved: PAL.neutralInk || "#6C757D",
  not_assessed: PAL.neutralInk || "#6C757D",
};
const ANSWER_WORD = {
  established: "established",
  not_resolved: "not settled",
  not_assessed: "not assessed",
};

/** One server-supplied Plotly figure, drawn once per result and kept across re-renders. */
function ServerFigure({ figure, height }) {
  const ref = useRef(null);
  useEffect(() => {
    const gd = ref.current;
    if (!gd) return;
    if (!figure || !figure.data) { Plotly.purge(gd); return; }
    const layout = { ...(figure.layout || {}) };
    if (height) layout.height = height;
    Plotly.react(gd, figure.data, layout, PAL.MODEBAR);
  }, [figure, height]);
  // Purge on unmount ONLY. Doing it in the cleanup of the effect above would destroy the graph
  // before every redraw, because a cleanup runs before each re-run of its own effect and not only
  // when the component goes away.
  useEffect(() => () => { if (ref.current) Plotly.purge(ref.current); }, []);
  return <div ref={ref} style={{ width: "100%" }} />;
}

/** The two summary matrices: one row per band centre, best value and the length of signal behind it. */
function BestTable({ rows, kind, nullValue }) {
  const isAuc = kind === "auc";
  if (!rows || !rows.length) {
    return (
      <MDTypography variant="caption" color="dark" sx={{ fontSize: 11.5, fontStyle: "italic" }}>
        {"No band centre produced a value, so there is no table to show."}
      </MDTypography>
    );
  }
  const head = ["Band (Hz)", isAuc ? "High vs low pain" : "Correlation", "Seconds averaged",
    "95% interval", "Shuffled best of ten", "Pain reports", "Answer"];
  return (
    <MDBox sx={{ overflowX: "auto" }}>
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 11.5 }}>
        <thead>
          <tr>
            {head.map((h) => (
              <th key={h} style={{ textAlign: "left", padding: "3px 6px", borderBottom: "1px solid #ccc",
                fontWeight: 700, whiteSpace: "nowrap" }}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => {
            const v = isAuc ? r.auc : r.pearson_r;
            const lo = isAuc ? r.auc_low : r.pearson_r_low;
            const hi = isAuc ? r.auc_high : r.pearson_r_high;
            const spans = lo != null && hi != null
              && Number(lo) <= nullValue && nullValue <= Number(hi);
            const ans = r.answer || "not_assessed";
            return (
              <tr key={`${r.band_center_hz}`} title={r.why || ""}>
                <td style={{ padding: "3px 6px", whiteSpace: "nowrap" }}>
                  {`${num(r.band_center_hz, 1)} (${num(r.band_low_hz, 1)}–${num(r.band_high_hz, 1)})`}
                  {r.band_fully_inside_8_to_30_hz === false ? (
                    <span title={"This band reaches outside the 8–30 Hz range the firmware can place "
                      + "an adaptive sensing band in, so it could not be acted on from this page."}
                    style={{ color: PAL.neutralInk || "#6C757D", marginLeft: 4 }}>{"*"}</span>
                  ) : null}
                </td>
                <td style={{ padding: "3px 6px", fontWeight: 600 }}>
                  {num(v, 3)}
                  {isAuc && r.auc_direction_folded != null ? (
                    <span style={{ fontWeight: 400, color: "#666" }}>
                      {` (fitted ${num(r.auc_direction_folded, 3)})`}
                    </span>
                  ) : null}
                </td>
                <td style={{ padding: "3px 6px", whiteSpace: "nowrap" }}>
                  {sec(r.integration_seconds_delivered)}
                  {r.integration_seconds_requested != null
                    && Number(r.integration_seconds_requested) !== Number(r.integration_seconds_delivered)
                    ? <span style={{ color: "#666" }}>{` (asked ${sec(r.integration_seconds_requested)})`}</span>
                    : null}
                </td>
                <td style={{ padding: "3px 6px", whiteSpace: "nowrap" }}>
                  {lo == null || hi == null ? "—" : `${num(lo, 3)} to ${num(hi, 3)}`}
                  {spans ? (
                    <span style={{ color: PAL.neutralInk || "#6C757D" }}>
                      {isAuc ? " — includes 0.5" : " — includes 0"}
                    </span>
                  ) : null}
                </td>
                <td style={{ padding: "3px 6px" }}>{num(r.shuffled_best_of_windows_p95, 3)}</td>
                <td style={{ padding: "3px 6px" }}>{r.n_pain_reports == null ? "—" : r.n_pain_reports}</td>
                <td style={{ padding: "3px 6px", color: ANSWER_INK[ans], fontWeight: 600,
                  whiteSpace: "nowrap" }}>
                  {ANSWER_WORD[ans] || ans}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </MDBox>
  );
}

function BandTimeSweepPanel({ participantUid, requestParams, availableMetrics, pageMetric,
  metricLabel }) {
  // The section's own choice of pain score. It starts on whatever the page above is showing, so the
  // first thing a reader sees is the same score the panels above them used, and its options are the
  // page's own list rather than a second list that could drift out of step with it.
  const options = useMemo(() => (
    (availableMetrics && availableMetrics.length ? availableMetrics : [])
  ), [availableMetrics]);
  const [metric, setMetric] = useState(pageMetric || "nrs");
  useEffect(() => { if (pageMetric) setMetric(pageMetric); }, [pageMetric]);

  const [result, setResult] = useState(null);
  const [running, setRunning] = useState(false);
  const [err, setErr] = useState(null);
  const [channel, setChannel] = useState(null);
  // What was actually computed, so the panel can say when the controls have moved since.
  const [ranWith, setRanWith] = useState(null);

  const run = () => {
    if (!participantUid) return;
    const body = {
      ParticipantId: participantUid,
      ...(requestParams || {}),
      BandTimeSweep: "1",
      SweepMetric: metric,
    };
    setRunning(true); setErr(null);
    SessionController.query("/api/queryBiomarkerAnalysis", body)
      .then((response) => {
        const d = (response && response.data) || null;
        setResult(d);
        setRanWith({ metric, requestParams: JSON.stringify(requestParams || {}) });
        const keys = Object.keys((d && d.band_time_sweep) || {});
        setChannel(keys.length ? keys[0] : null);
      })
      .catch((e) => setErr((e && e.message) || String(e)))
      .finally(() => setRunning(false));
  };

  const drifted = !!(ranWith && (ranWith.metric !== metric
    || ranWith.requestParams !== JSON.stringify(requestParams || {})));
  const sweeps = (result && result.band_time_sweep) || {};
  const channels = Object.keys(sweeps);
  const sw = (channel && sweeps[channel]) || null;
  const figures = (sw && sw.figures) || {};
  const notes = (sw && sw.notes) || [];
  const applied = (result && result.settings_applied) || null;

  return (
    <Card sx={{ width: "100%" }}>
      <MDBox p={2}>
        <MDTypography variant="h5" fontWeight="bold" sx={{ fontSize: 22, lineHeight: 1.3 }}>
          {"How well each band tracks pain, at every length of signal averaged into one measurement"}
        </MDTypography>
        <MDTypography variant="body2" color="dark" sx={{ fontSize: 13.5, mt: 0.5 }}>
          {"Band centre across the bottom, seconds of recording averaged into one band-power "
           + "measurement up the side. Two numbers for every cell: how the band power moves with "
           + "the pain score chosen below, and how well it tells that patient's high-pain reports "
           + "from the low-pain ones. The point of the grid is the shape of the surface, so the "
           + "whole grid is drawn and not only the best cell in each row."}
        </MDTypography>

        {/* THE CONTROLS. The pain score is chosen here; everything else comes from the top of the
            page and is shown rather than described, so a reader can check it. */}
        <MDBox mt={2} display="flex" alignItems="center" flexWrap="wrap" sx={{ gap: 1.5 }}>
          <MDBox>
            <MDTypography variant="caption" fontWeight="bold" color="dark"
              sx={{ fontSize: 11.5, display: "block" }}>
              {"Patient-reported pain score"}
            </MDTypography>
            <FormControl size="small" sx={{ minWidth: 260 }}>
              <Select value={metric} onChange={(e) => setMetric(e.target.value)}
                sx={{ fontSize: 13 }}>
                {options.map((m) => (
                  <MenuItem key={m.key} value={m.key} sx={{ fontSize: 13 }}>{m.label}</MenuItem>
                ))}
              </Select>
            </FormControl>
          </MDBox>
          {channels.length > 1 ? (
            <MDBox>
              <MDTypography variant="caption" fontWeight="bold" color="dark"
                sx={{ fontSize: 11.5, display: "block" }}>
                {"Sensing contact pair"}
              </MDTypography>
              <FormControl size="small" sx={{ minWidth: 220 }}>
                <Select value={channel || ""} onChange={(e) => setChannel(e.target.value)}
                  sx={{ fontSize: 13 }}>
                  {channels.map((c) => (
                    <MenuItem key={c} value={c} sx={{ fontSize: 13 }}>{c}</MenuItem>
                  ))}
                </Select>
              </FormControl>
            </MDBox>
          ) : null}
          <MDBox sx={{ alignSelf: "flex-end" }}>
            <MDButton variant="gradient" color="info" size="small" onClick={run}
              disabled={running || !participantUid || !requestParams}>
              {running ? "Sweeping…" : (result ? "Sweep again" : "Run the sweep")}
            </MDButton>
          </MDBox>
          {running ? <CircularProgress size={18} /> : null}
        </MDBox>

        {!requestParams ? (
          <MDTypography variant="caption" color="dark"
            sx={{ fontSize: 11.5, display: "block", mt: 1, fontStyle: "italic" }}>
            {"This section reads the settings at the top of the page, so run the analysis up there "
             + "first and then come back."}
          </MDTypography>
        ) : null}
        {drifted ? (
          <MDTypography variant="caption"
            sx={{ fontSize: 11.5, display: "block", mt: 1, color: PAL.warn || "#E69F00" }}>
            {"The controls have changed since this grid was computed, so what is shown below is the "
             + "previous answer. Press “Sweep again” for the current settings."}
          </MDTypography>
        ) : null}
        {err ? (
          <MDTypography variant="caption" sx={{ fontSize: 11.5, display: "block", mt: 1,
            color: PAL.fail || "#D55E00" }}>
            {`The sweep could not be computed: ${err}`}
          </MDTypography>
        ) : null}
        {result && result.message ? (
          <MDTypography variant="caption" color="dark"
            sx={{ fontSize: 11.5, display: "block", mt: 1, fontStyle: "italic" }}>
            {result.message}
          </MDTypography>
        ) : null}

        {/* THE OPTIMISM NOTE AND THE 0.5 NOTE, IN THE PANEL AND NOT ONLY IN A CAPTION. Both come
            from the server, computed in the same pass as the numbers, so the panel cannot show a
            grid without the sentences that say how to read it. */}
        {sw && notes.length ? (
          <MDBox mt={2} sx={{ border: `2px solid ${PAL.accentBorder || "#0072B255"}`,
            borderRadius: 2, p: 1.25, background: "#0072B208" }}>
            <MDTypography variant="caption" fontWeight="bold" color="dark"
              sx={{ fontSize: 12, display: "block", mb: 0.5 }}>
              {"How to read the two tables below"}
            </MDTypography>
            {notes.map((n, i) => (
              <MDTypography key={i} variant="caption" color="dark"
                sx={{ fontSize: 11.5, display: "block", mb: 0.4, lineHeight: 1.45 }}>
                {`• ${n}`}
              </MDTypography>
            ))}
          </MDBox>
        ) : null}

        {sw && sw.center_freqs_hz && sw.center_freqs_hz.length ? (
          <>
            <Grid container spacing={2} mt={1}>
              <Grid item xs={12}>
                <MDTypography variant="button" fontWeight="bold" color="dark"
                  sx={{ fontSize: 13, display: "block", mb: 0.5 }}>
                  {"How the band power moves with the pain score"}
                </MDTypography>
                <ServerFigure figure={figures.correlation} />
                <MDTypography variant="caption" color="dark"
                  sx={{ fontSize: 11, display: "block", fontStyle: "italic" }}>
                  {"The colour scale is centred on 0, which is the value that means no relationship "
                   + "for this quantity. Grey columns mark band centres whose 5 Hz window reaches "
                   + "outside the 8–30 Hz range the firmware can place an adaptive sensing band in."}
                </MDTypography>
              </Grid>
              <Grid item xs={12}>
                <MDTypography variant="button" fontWeight="bold" color="dark"
                  sx={{ fontSize: 13, display: "block", mb: 0.5 }}>
                  {"How well the band power tells high-pain reports from low-pain ones"}
                </MDTypography>
                <ServerFigure figure={figures.auc} />
                <MDTypography variant="caption" color="dark"
                  sx={{ fontSize: 11, display: "block", fontStyle: "italic" }}>
                  {"The colour scale is centred on 0.5, which is the value that means no "
                   + "discrimination for this quantity — NOT 0. Above 0.5 the band power is higher "
                   + "on the high-pain reports and below 0.5 it is lower; both are relationships, "
                   + "and 0.5 itself is neither."}
                </MDTypography>
              </Grid>
            </Grid>

            <Grid container spacing={2} mt={1}>
              <Grid item xs={12} lg={6}>
                <MDTypography variant="button" fontWeight="bold" color="dark"
                  sx={{ fontSize: 13, display: "block", mb: 0.5 }}>
                  {"Best correlation per band centre, and the length of signal that produced it"}
                </MDTypography>
                <BestTable rows={sw.best_correlation_rows} kind="correlation" nullValue={0} />
              </Grid>
              <Grid item xs={12} lg={6}>
                <MDTypography variant="button" fontWeight="bold" color="dark"
                  sx={{ fontSize: 13, display: "block", mb: 0.5 }}>
                  {"Best high-versus-low-pain value per band centre, and the length of signal that "
                   + "produced it"}
                </MDTypography>
                <BestTable rows={sw.best_auc_rows} kind="auc" nullValue={0.5} />
                <MDTypography variant="caption" color="dark"
                  sx={{ fontSize: 11, display: "block", mt: 0.4, fontStyle: "italic" }}>
                  {"The number in brackets is the same value with its direction folded away, which "
                   + "is what a fitted one-predictor logistic regression returns in sample. That "
                   + "number cannot fall below 0.5, so for it 0.5 is a floor rather than a neutral "
                   + "middle, and the level it has to beat is the shuffled column beside it."}
                </MDTypography>
              </Grid>
            </Grid>

            {/* WHAT ACTUALLY RAN. Printed rather than assumed, so a reader can check that the
                settings at the top of the page reached this section. */}
            <MDBox mt={2}>
              <MDTypography variant="caption" color="dark" sx={{ fontSize: 11, display: "block" }}>
                {`Contact pair ${channel}. Pain score: ${(result && result.metric_label)
                  || metricLabel || metric}. `}
                {applied ? (
                  `Settings taken from the top of the page: pain reports matched within `
                  + `\u00b1${applied.match_tolerance_min} min; window reuse `
                  + `${applied.allow_window_reuse ? "on" : "off"}; high and low pain split by `
                  + `${applied.label_strategy} (${applied.percentile_low}/${applied.percentile_high}); `
                  + `outliers at ${applied.outlier_n_mad} median absolute deviations on the `
                  + `${applied.outlier_scale} scale. `
                ) : ""}
                {sw.logistic_fit_crosscheck ? (
                  `A real one-predictor logistic regression was fitted at each of the `
                  + `${sw.logistic_fit_crosscheck.n_cells} cells in the table and matched the folded `
                  + `value in ${sw.logistic_fit_crosscheck.n_agree} of them. `
                ) : ""}
                {sw.total_seconds != null
                  ? `This grid took ${num(sw.total_seconds, 2)} s to compute.` : ""}
              </MDTypography>
            </MDBox>
          </>
        ) : (sw ? (
          <MDTypography variant="caption" color="dark"
            sx={{ fontSize: 11.5, display: "block", mt: 1, fontStyle: "italic" }}>
            {sw.why || "Nothing could be computed for this contact pair."}
          </MDTypography>
        ) : null)}
      </MDBox>
    </Card>
  );
}

export default BandTimeSweepPanel;
