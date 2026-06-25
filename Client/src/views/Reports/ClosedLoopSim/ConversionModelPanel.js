/**
 * PSD -> device-LSB CONVERSION MODEL panel (deployment lookup, frozen).
 *
 * Distinct from PsdLsbPanel (which refits ONE committed band live): this panel serves the reviewed,
 * frozen per-participant conversion model from /api/queryPsdLsbConversionModel and renders the two
 * clinically-useful views of it:
 *
 *   (1) GAIN ANCHOR vs FREQUENCY, one trace per channel — the device's on-board power gain (LSB at
 *       1 uV^2) falls as sensing frequency rises; this is the trend the threshold estimator uses
 *       when the device never sensed a band. Bootstrap CIs as error bars; a per-channel common slope
 *       b is annotated (the per-frequency difference is a gain/intercept shift, not a slope change).
 *   (2) LSB vs PSD, one subplot per fittable channel, points colored by sensing frequency, with the
 *       per-band common-slope fit lines overlaid and excluded (outlier) clusters as grey ×.
 *
 * This is the model the deploy sign-off falls back on (flagged ESTIMATED) when a band has no device
 * LSB recordings of its own. Imperative Plotly.react-once discipline (module standard; commit 255e0ef).
 */
import { useEffect, useRef, useState } from "react";
import Plotly from "plotly.js-dist";

import { Card } from "@mui/material";
import MDBox from "components/MDBox";
import MDTypography from "components/MDTypography";

import { SessionController } from "database/session-control";
import PAL from "./palette";

const fmt = (v, d = 2) => (v == null || !Number.isFinite(Number(v)) ? "—" : Number(v).toFixed(d));

// Channel ink: the two fittable channels get the two most-separable Okabe–Ito inks; others neutral.
const CH_INK = { ZERO_THREE_RIGHT: PAL.accent, ZERO_THREE_LEFT: PAL.fail };
const chInk = (ch) => CH_INK[ch] || PAL.neutral;

// Viridis-ish ramp for sensing frequency (low freq = purple, high = yellow), CVD-robust sequential.
function hzColor(hz, lo, hi) {
  const t = hi > lo ? Math.min(1, Math.max(0, (hz - lo) / (hi - lo))) : 0.5;
  // 5-stop viridis approximation
  const stops = [[68, 1, 84], [59, 82, 139], [33, 145, 140], [94, 201, 98], [253, 231, 37]];
  const x = t * (stops.length - 1);
  const i = Math.min(stops.length - 2, Math.floor(x));
  const f = x - i;
  const c = stops[i].map((a, k) => Math.round(a + f * (stops[i + 1][k] - a)));
  return `rgb(${c[0]},${c[1]},${c[2]})`;
}

const shortChannel = (ch) => (ch || "")
  .replace("ZERO_THREE", "0–3").replace("ONE_THREE", "1–3").replace("ZERO_TWO", "0–2")
  .replace("_RIGHT", " R").replace("_LEFT", " L");

function ConversionModelPanel({ participantUid }) {
  const trendRef = useRef(null);
  const scatterRef = useRef(null);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState(null);

  useEffect(() => {
    if (!participantUid) { setData(null); return; }
    setLoading(true); setErr(null);
    SessionController.query("/api/queryPsdLsbConversionModel", { ParticipantId: participantUid })
      .then((response) => {
        const d = response && response.data;
        if (d && d.available) setData(d);
        else { setData(null); setErr((d && d.reason) || "no conversion model"); }
        setLoading(false);
      }).catch(() => { setData(null); setErr("request failed"); setLoading(false); });
  }, [participantUid]);

  // ---- (1) gain-anchor vs frequency, one trace per channel ----
  useEffect(() => {
    const gd = trendRef.current;
    if (!gd || !data || !data.channels) { if (gd) Plotly.purge(gd); return; }
    const fit = data.channels.filter((c) => c.fittable && c.bands && c.bands.length);
    if (!fit.length) { Plotly.purge(gd); return; }
    const traces = [];
    fit.forEach((c) => {
      const xs = c.bands.map((b) => b.center_hz);
      const ys = c.bands.map((b) => b.lsb_at_1uv2);
      const hi = c.bands.map((b) => (b.intercept_ci ? 10 ** b.intercept_ci[1] - b.lsb_at_1uv2 : 0));
      const lo = c.bands.map((b) => (b.intercept_ci ? b.lsb_at_1uv2 - 10 ** b.intercept_ci[0] : 0));
      traces.push({
        x: xs, y: ys, type: "scatter", mode: "markers+lines",
        name: `${shortChannel(c.channel)} (b=${fmt(c.common_slope_b, 2)}, R²=${fmt(c.r2, 2)})`,
        line: { color: chInk(c.channel), width: 1.5 },
        marker: { color: chInk(c.channel), size: 8 },
        error_y: { type: "data", symmetric: false, array: hi, arrayminus: lo, thickness: 1, width: 3,
          color: chInk(c.channel) },
        customdata: c.bands.map((b) => b.n),
        hovertemplate: `${shortChannel(c.channel)}<br>%{x:.1f} Hz<br>LSB@1µV² %{y:.0f}<br>n=%{customdata}<extra></extra>`,
      });
    });
    const layout = {
      margin: { l: 56, r: 12, t: 8, b: 40 }, height: 250,
      xaxis: { title: { text: "sensing center frequency (Hz)", font: { size: 10.5 } }, tickfont: { size: 9.5 } },
      yaxis: { title: { text: "gain anchor — LSB at 1 µV²", font: { size: 10.5 } }, type: "log",
        zeroline: false, tickfont: { size: 9.5 } },
      legend: { font: { size: 9 }, orientation: "h", y: 1.12, x: 0 },
    };
    Plotly.react(gd, traces, layout, PAL.MODEBAR);
  }, [data]);

  // ---- (2) LSB vs PSD, one column per fittable channel, colored by frequency ----
  useEffect(() => {
    const gd = scatterRef.current;
    if (!gd || !data || !data.channels) { if (gd) Plotly.purge(gd); return; }
    const fit = data.channels.filter((c) => c.fittable && c.scatter && c.scatter.length);
    // The model JSON ships per-band fit params; the cluster scatter is attached as c.scatter when
    // the backend includes it. If absent, draw the fit LINES alone (still informative).
    const haveScatter = fit.length > 0;
    const cols = data.channels.filter((c) => c.fittable);
    if (!cols.length) { Plotly.purge(gd); return; }
    // global frequency range for the color ramp
    let flo = Infinity; let fhi = -Infinity;
    cols.forEach((c) => (c.bands || []).forEach((b) => { flo = Math.min(flo, b.center_hz); fhi = Math.max(fhi, b.center_hz); }));
    const traces = [];
    const ncol = cols.length;
    const domainFor = (j) => {
      const gap = 0.08; const w = (1 - gap * (ncol - 1)) / ncol;
      return [j * (w + gap), j * (w + gap) + w];
    };
    cols.forEach((c, j) => {
      const xax = j === 0 ? "x" : `x${j + 1}`;
      const yax = j === 0 ? "y" : `y${j + 1}`;
      // fit lines per band (always available from the frozen model)
      (c.bands || []).forEach((b) => {
        // draw across a decade around the band's own anchor; the panel x is log so endpoints suffice
        const gx = [0.05, 0.5, 5, 50];
        const gy = gx.map((p) => 10 ** (b.intercept_a + c.common_slope_b * Math.log10(p)));
        traces.push({ x: gx, y: gy, xaxis: xax, yaxis: yax, type: "scatter", mode: "lines",
          line: { color: hzColor(b.center_hz, flo, fhi), width: 1.4 }, showlegend: false,
          hovertemplate: `${b.center_hz.toFixed(1)} Hz · LSB@1µV²=${b.lsb_at_1uv2.toFixed(0)}<extra></extra>` });
      });
      // cluster scatter colored by frequency, if the backend attached it
      if (haveScatter && c.scatter) {
        const xs = c.scatter.map((p) => p.psd_uv2);
        const ys = c.scatter.map((p) => p.lsb);
        const cs = c.scatter.map((p) => hzColor(p.center_hz, flo, fhi));
        const ex = c.scatter.map((p) => !!p.excluded);
        traces.push({ x: xs.filter((_, k) => !ex[k]), y: ys.filter((_, k) => !ex[k]), xaxis: xax, yaxis: yax,
          type: "scattergl", mode: "markers",
          marker: { color: cs.filter((_, k) => !ex[k]), size: 5, opacity: 0.55 }, showlegend: false,
          hovertemplate: "PSD %{x:.3g} µV²<br>LSB %{y:.0f}<extra></extra>" });
        if (ex.some(Boolean)) {
          traces.push({ x: xs.filter((_, k) => ex[k]), y: ys.filter((_, k) => ex[k]), xaxis: xax, yaxis: yax,
            type: "scattergl", mode: "markers",
            marker: { color: PAL.neutral, size: 7, symbol: "x" }, showlegend: false,
            hovertemplate: "excluded<extra></extra>" });
        }
      }
    });
    const layout = { margin: { l: 50, r: 10, t: 22, b: 40 }, height: 300, annotations: [] };
    cols.forEach((c, j) => {
      const xax = j === 0 ? "xaxis" : `xaxis${j + 1}`;
      const yax = j === 0 ? "yaxis" : `yaxis${j + 1}`;
      layout[xax] = { domain: domainFor(j), type: "log", zeroline: false, tickfont: { size: 8.5 },
        title: { text: "PSD band power (µV²)", font: { size: 9.5 } }, anchor: j === 0 ? "y" : `y${j + 1}` };
      layout[yax] = { type: "log", zeroline: false, tickfont: { size: 8.5 },
        title: { text: j === 0 ? "device LSB" : "", font: { size: 9.5 } }, anchor: j === 0 ? "x" : `x${j + 1}` };
      layout.annotations.push({ xref: "paper", yref: "paper",
        x: (domainFor(j)[0] + domainFor(j)[1]) / 2, y: 1.04, xanchor: "center", yanchor: "bottom",
        text: `<b>${shortChannel(c.channel)}</b> · b=${fmt(c.common_slope_b, 2)}`, showarrow: false,
        font: { size: 10, color: chInk(c.channel) } });
    });
    Plotly.react(gd, traces, layout, PAL.MODEBAR);
  }, [data]);

  useEffect(() => () => {
    if (trendRef.current) Plotly.purge(trendRef.current);
    if (scatterRef.current) Plotly.purge(scatterRef.current);
  }, []);

  return (
    <Card sx={{ height: "100%" }}>
      <MDBox p={2}>
        <MDTypography variant="h6" sx={{ fontSize: 13 }}>
          PSD → device-LSB conversion model (deployment lookup)
        </MDTypography>
        <MDTypography variant="caption" color="text" sx={{ fontSize: 10.5 }}>
          Frozen per-participant model · per-channel common slope, frequency-specific gain. The
          fallback the threshold estimator uses when the device never sensed a band.
        </MDTypography>

        {loading ? (
          <MDTypography variant="caption" color="text" sx={{ display: "block", mt: 1, fontStyle: "italic", fontSize: 11 }}>
            Loading conversion model…
          </MDTypography>
        ) : err ? (
          <MDTypography variant="caption" sx={{ display: "block", mt: 1, fontSize: 11, color: PAL.warnText }}>
            {`No conversion model: ${err}.`}
          </MDTypography>
        ) : data ? (
          <>
            <MDBox mt={1.2}>
              <MDTypography variant="caption" sx={{ fontSize: 10.5, fontWeight: "bold", color: "#555" }}>
                Gain anchor vs frequency (device gain falls as sensing frequency rises)
              </MDTypography>
              <div ref={trendRef} style={{ width: "100%" }} />
            </MDBox>
            <MDBox mt={1.2}>
              <MDTypography variant="caption" sx={{ fontSize: 10.5, fontWeight: "bold", color: "#555" }}>
                LSB vs PSD per channel — color = sensing frequency, lines = per-band common-slope fit
              </MDTypography>
              <div ref={scatterRef} style={{ width: "100%" }} />
            </MDBox>
            <MDTypography variant="caption" display="block" sx={{ fontSize: 9, color: "#888", mt: 0.5, fontStyle: "italic" }}>
              {`Outliers omitted per band (Iglewicz–Hoaglin robust z); n≥6 per fitted band. ${
                (data.special && data.special["ZERO_THREE_RIGHT_8.8Hz"]) ? "8.8 Hz 0–3 Right restricted to the recent gain regime." : ""}`}
            </MDTypography>
          </>
        ) : null}
      </MDBox>
    </Card>
  );
}

export default ConversionModelPanel;
