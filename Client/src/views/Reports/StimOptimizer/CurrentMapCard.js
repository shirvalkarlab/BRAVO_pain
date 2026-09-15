/**
 * "Where the two currents have been tried, and what the record says" -- the Stim Optimizer page's
 * new card drawing the (left current, right current) surface behind decision 158's honest-current
 * rule (`two_stage.stage1.rate_strata[].surface`, added 2026-09-14 alongside that rule so the page
 * can show WHY a rate reads flat instead of only stating the verdict).
 *
 * One section per (pulse-width-Left, pulse-width-Right) pair Stage 1 actually fitted a joint
 * surface for, one row per stimulation rate inside it, rates ordered by how many stretches of
 * unchanged settings they rest on (most first). A FITTED rate draws a square heatmap -- x = left
 * current, y = right current, colour = the pain-plus-side-effect objective the search minimises
 * (green low, red high, zero at the setting in force) -- with the three checks decision 158's rule
 * reads printed beside it, each with its own numbers and a tick or a cross. A rate that never
 * cleared the 8-epoch floor prints one plain line and draws nothing: there is no surface to show.
 *
 * The POOLED, across-every-rate 3-input surface -- the number that used to be read as a current
 * recommendation and, on RCS08, turned out to be flat (varying by 0.004 against a scatter of 1.1)
 * -- is folded, closed by default, and labelled reference only: the caveat is that it borrows its
 * apparent precision from every OTHER rate through the fit's shared, pinned rate axis.
 */
import { useEffect, useMemo, useRef, useState } from "react";

import { Card, Grid } from "@mui/material";

import MDBox from "components/MDBox";
import MDTypography from "components/MDTypography";

import Plotly from "plotly.js-dist";
import { PlotlyRenderManager } from "graphing-utility/Plotly";
import Fold from "views/Reports/ClosedLoopSim/Fold";
import PAL from "views/Reports/ClosedLoopSim/palette";

import { num, fmtHz, fmtUs } from "./stimFormat";
import { TYPE, SMALL } from "./typeScale";

const CHECK_MARK = "✓";
const CROSS_MARK = "✗";

function CheckRow({ label, passes, detail }) {
  const color = passes === true ? "#1B7A3D" : (passes === false ? PAL.warnText : "#8A8A8A");
  const mark = passes === true ? CHECK_MARK : (passes === false ? CROSS_MARK : "—");
  return (
    <MDBox display="flex" alignItems="baseline" gap={0.8} sx={{ mt: 0.3 }}>
      <span style={{ color, fontWeight: 700, fontSize: TYPE.body, minWidth: 14 }}>{mark}</span>
      <MDTypography variant="caption" component="div" sx={{ fontSize: TYPE.body }}>
        <span style={{ fontWeight: 600 }}>{label}</span>{detail ? ` — ${detail}` : ""}
      </MDTypography>
    </MDBox>
  );
}

/** One (left-current, right-current) surface: the heatmap, the setting-in-force ×, the observed
 * points, and a ★ on the best cell when (and only when) that rate's own current is resolved. */
function CurrentSurfaceHeatmap({ divId, surface, inForceLeft, inForceRight, starLeft, starRight,
  showStar, size = 340 }) {
  const figRef = useRef(null);
  const rows = surface ? surface.mu.length : 0;
  const cols = rows ? surface.mu[0].length : 0;

  const { zmin, zmax, gridZ } = useMemo(() => {
    if (!surface) return { zmin: -1, zmax: 1, gridZ: [] };
    const finite = [];
    surface.mu.forEach((row, i) => row.forEach((v, j) => {
      if (v != null && surface.safe[i][j]) finite.push(Math.abs(v));
    }));
    const half = Math.max(0.5, ...finite, 0);
    const gz = surface.mu.map((row, i) => row.map((v, j) => (surface.safe[i][j] ? v : null)));
    return { zmin: -half, zmax: half, gridZ: gz };
  }, [surface]);

  useEffect(() => {
    if (!surface || !rows || !cols) return undefined;
    if (!figRef.current) figRef.current = new PlotlyRenderManager(divId, "en");
    const fig = figRef.current;
    fig.clearData();
    fig.subplots(1, 1, { sharex: false, sharey: false });
    fig.traces.push({
      type: "heatmap", z: gridZ, x: surface.amps_mA, y: surface.amps_mA,
      colorscale: "RdYlGn", reversescale: true, zmin, zmax, zmid: 0,
      colorbar: { title: { text: "pain + side-effect score<br>(lower is better; 0 = setting in force)",
        font: { size: 10 } }, thickness: 12, len: 0.9, tickfont: { size: 10 } },
      xgap: 1, ygap: 1,
      hovertemplate: "left %{x:.2f} mA, right %{y:.2f} mA<br>score %{z:.3f}<extra></extra>",
    });
    // Observed reports, sized by how many ratings they carry.
    const pts = surface.points || [];
    fig.traces.push({
      type: "scatter", mode: "markers", showlegend: false,
      x: pts.map((p) => p.amp_left_mA), y: pts.map((p) => p.amp_right_mA),
      marker: { size: pts.map((p) => 6 + 2.2 * Math.sqrt(Math.max(1, p.n_reports || 1))),
        color: "rgba(20,20,20,0.75)", line: { width: 1, color: "#FFFFFF" } },
      hovertemplate: pts.map((p) => `epoch ${p.epoch}: ${p.n_reports} report(s)<br>`
        + `${p.amp_left_mA.toFixed(2)} / ${p.amp_right_mA.toFixed(2)} mA<extra></extra>`),
    });
    // The setting in force, ×.
    if (inForceLeft != null && inForceRight != null) {
      fig.traces.push({
        type: "scatter", mode: "markers", showlegend: false,
        x: [inForceLeft], y: [inForceRight],
        marker: { symbol: "x-thin", size: 18, color: "#1A1A1A", line: { width: 3, color: "#1A1A1A" } },
        hovertemplate: `setting in force: ${inForceLeft.toFixed(2)} / ${inForceRight.toFixed(2)} mA<extra></extra>`,
      });
    }
    // The best cell, only when the rate's own current is resolved (decision 158's rule).
    if (showStar && starLeft != null && starRight != null) {
      fig.traces.push({
        type: "scatter", mode: "markers", showlegend: false,
        x: [starLeft], y: [starRight],
        marker: { symbol: "star", size: 20, color: "#0B63C6", line: { width: 1.5, color: "#FFFFFF" } },
        hovertemplate: `best cell: ${starLeft.toFixed(2)} / ${starRight.toFixed(2)} mA<extra></extra>`,
      });
    }
    fig.setLayoutProps({
      height: size, width: size, margin: { l: 46, r: 70, t: 8, b: 40 },
      xaxis: { showgrid: false, zeroline: false, range: [-0.15, 5.15] },
      yaxis: { showgrid: false, zeroline: false, range: [-0.15, 5.15] },
      hovermode: "closest",
    });
    fig.setXlabel("Left current (mA)", { fontSize: 11 });
    fig.setYlabel("Right current (mA)", { fontSize: 11 });
    fig.render();
    Plotly.react(divId, fig.traces, fig.layout,
      { displayModeBar: false, responsive: true, doubleClick: false });
    return undefined;
  }, [divId, surface, gridZ, zmin, zmax, rows, cols, inForceLeft, inForceRight, starLeft, starRight,
    showStar, size]);

  useEffect(() => () => {
    if (figRef.current && document.getElementById(divId)) figRef.current.purge();
  }, [divId]);

  if (!surface) return null;
  return <div id={divId} style={{ width: size, height: size }} />;
}

/** Group `rate_strata` rows by (pw_us_left, pw_us_right), rates ordered by n_epochs descending. */
function groupByPulseWidthPair(rateStrata) {
  const groups = new Map();
  (rateStrata || []).forEach((r) => {
    if (r == null) return;
    const key = `${r.pw_us_left}_${r.pw_us_right}`;
    if (!groups.has(key)) {
      groups.set(key, { key, pw_us_left: r.pw_us_left, pw_us_right: r.pw_us_right, rows: [] });
    }
    groups.get(key).rows.push(r);
  });
  const out = Array.from(groups.values());
  out.forEach((g) => g.rows.sort((a, b) => (num(b.n_epochs) || 0) - (num(a.n_epochs) || 0)));
  return out;
}

export default function CurrentMapCard({ plan }) {
  const stage1 = (plan && plan.stage1) || {};
  const rawRateStrata = stage1.rate_strata;
  const rateStrata = useMemo(() => (Array.isArray(rawRateStrata) ? rawRateStrata : []), [rawRateStrata]);
  const pooledSurfaces = stage1.pooled_surfaces || {};
  const inForceBySide = (stage1.frozen_configuration || {}).in_force_by_side || {};
  const inForceLeft = num(inForceBySide.Left && inForceBySide.Left.amplitude_mA);
  const inForceRight = num(inForceBySide.Right && inForceBySide.Right.amplitude_mA);

  const groups = useMemo(() => groupByPulseWidthPair(rateStrata), [rateStrata]);
  const [poolOpen, setPoolOpen] = useState({});

  if (!rateStrata.length) return null;

  return (
    <Card>
      <MDBox p={2}>
        <MDTypography variant="h6" sx={{ fontSize: TYPE.section }}>
          Where the two currents have been tried, and what the record says
        </MDTypography>
        <MDTypography variant="caption" component="div" color="text" sx={{ fontSize: TYPE.body, mt: 0.5, mb: 1.5 }}>
          Each square below is one stimulation speed: the left current runs along the bottom, the
          right current up the side, and the colour is the combined pain-and-side-effect score the
          search is trying to make as small (as green) as possible -- zero, on the colour scale, is
          the score AT the setting programmed today. A black × marks that setting; the dots are
          combinations this participant has actually been rated on, sized by how many ratings back
          them; a blue star appears only when the record can tell currents apart well enough to
          trust it, per the three checks printed beside each square.
        </MDTypography>

        {groups.map((g) => (
          <MDBox key={g.key} sx={{ mt: 2.5, "&:first-of-type": { mt: 0 } }}>
            <MDTypography variant="caption" fontWeight="medium" component="div"
              sx={{ fontSize: TYPE.num, mb: 0.5 }}>
              {`left pulse width ${fmtUs(g.pw_us_left)} · right pulse width ${fmtUs(g.pw_us_right)}`}
            </MDTypography>

            {g.rows.map((r) => {
              const divId = `cms-surface-${g.key}-${r.rate_hz}`;
              if (!r.fitted) {
                return (
                  <MDTypography key={divId} variant="caption" component="div" color="text"
                    sx={{ fontSize: TYPE.body, mt: 1, mb: 1 }}>
                    {`${fmtHz(r.rate_hz)} · ${num(r.n_epochs) ?? 0} epoch${num(r.n_epochs) === 1 ? "" : "s"} — `
                      + `not enough data (${r.reason || "below the 8-epoch floor"}); no surface is drawn.`}
                  </MDTypography>
                );
              }
              return (
                <MDBox key={divId} sx={{ mt: 1, mb: 2 }}>
                  <MDTypography variant="caption" component="div" sx={{ fontSize: TYPE.body, mb: 0.6 }}>
                    {`${fmtHz(r.rate_hz)} · left ${fmtUs(g.pw_us_left)} / right ${fmtUs(g.pw_us_right)} · `
                      + `${num(r.n_epochs) ?? 0} epochs · ${Math.round(num(r.n_reports) || 0)} reports`}
                  </MDTypography>
                  <Grid container spacing={2}>
                    <Grid item xs={12} sm="auto">
                      <CurrentSurfaceHeatmap divId={divId} surface={r.surface}
                        inForceLeft={inForceLeft} inForceRight={inForceRight}
                        starLeft={num(r.amp_mA_left)} starRight={num(r.amp_mA_right)}
                        showStar={r.resolved === true} />
                    </Grid>
                    <Grid item xs={12} sm>
                      <MDTypography variant="caption" component="div" sx={{ fontSize: TYPE.body, mb: 0.6 }}>
                        {r.resolved ? "a current CAN be recommended at this speed." : "no current can be recommended at this speed yet."}
                      </MDTypography>
                      {/* `flat_passes` is the BACKEND's own check that the surface VARIES enough
                          to mean something (it is NOT flat), so a tick here means "not flat,
                          this check passed" -- read in the same "good = passed" direction as the
                          other two rows below, and not negated here. */}
                      <CheckRow label="Surface flat?"
                        passes={r.flat_passes}
                        detail={num(r.flat_range) != null && num(r.flat_median_sd) != null
                          ? `varies by ${num(r.flat_range).toFixed(3)} against a typical uncertainty of ${num(r.flat_median_sd).toFixed(3)}`
                          : "not assessable"} />
                      <CheckRow label="Beats the setting in force?"
                        passes={r.gain_passes}
                        detail={num(r.gain) != null && num(r.gain_sd_of_difference) != null
                          ? `${num(r.gain) >= 0 ? "+" : "−"}${Math.abs(num(r.gain)).toFixed(3)} against ${num(r.gain_sd_of_difference).toFixed(3)}`
                          : "no comparison available"} />
                      <CheckRow label="Enough combinations tried?"
                        passes={r.coverage_passes}
                        detail={`${num(r.coverage_n_pairs) ?? 0} pairs, `
                          + `${num(r.coverage_span_left_mA) != null ? num(r.coverage_span_left_mA).toFixed(1) : "0.0"} mA left / `
                          + `${num(r.coverage_span_right_mA) != null ? num(r.coverage_span_right_mA).toFixed(1) : "0.0"} mA right span`} />
                      {r.sentence && (
                        <MDTypography variant="caption" component="div" color="text"
                          sx={{ ...SMALL, mt: 0.8 }}>
                          {String(r.sentence)}
                        </MDTypography>
                      )}
                    </Grid>
                  </Grid>
                </MDBox>
              );
            })}

            {/* Note the flat-surface check reads a `flat` PASS as "the surface is NOT flat" --
                CheckRow above negates `flat_passes` so its tick/cross reads the same direction as
                the other two ("passing" = good), matching the label "Surface flat?" answered "no". */}

            <Fold show="Pooled across rates — reference only" hide="Hide the pooled surface"
              onChange={(open) => setPoolOpen((s) => ({ ...s, [g.key]: open || s[g.key] }))}>
              <MDTypography variant="caption" component="div" color="text" sx={{ fontSize: TYPE.small, mb: 1 }}>
                The surface below pools every rate together through one shared, pinned rate axis.
                It is shown for reference only: reading a current off it draws confidence from
                OTHER rates, not the one being asked about, which is exactly why the honest
                surfaces above are fitted one rate at a time.
              </MDTypography>
              {g.rows.map((r) => {
                const stratumKey = `${Number(g.pw_us_left).toString()}_${Number(g.pw_us_right).toString()}`;
                const rateKey = Number(r.rate_hz).toString();
                const pooled = (pooledSurfaces[stratumKey] || {}).surface_at_rate || {};
                const pooledSurface = pooled[rateKey];
                const divId = `cms-pooled-${g.key}-${r.rate_hz}`;
                if (!pooledSurface) return null;
                return (
                  <MDBox key={divId} sx={{ mt: 1, mb: 1.5 }}>
                    <MDTypography variant="caption" component="div" sx={{ fontSize: TYPE.body, mb: 0.4 }}>
                      {fmtHz(r.rate_hz)}
                    </MDTypography>
                    {poolOpen[g.key] && (
                      <CurrentSurfaceHeatmap divId={divId} surface={pooledSurface}
                        inForceLeft={inForceLeft} inForceRight={inForceRight}
                        starLeft={null} starRight={null} showStar={false} size={220} />
                    )}
                    <MDTypography variant="caption" component="div" color="text" sx={{ ...SMALL, mt: 0.4 }}>
                      {String(r.pooled_across_rates_note || "")}
                    </MDTypography>
                  </MDBox>
                );
              })}
            </Fold>
          </MDBox>
        ))}
      </MDBox>
    </Card>
  );
}
