/**
 * Phase C panel: anchor the Phase-B cut-point to deployable device LSB units + power / sample-size.
 *
 * Fetches /api/queryLsbPower with the cut-point lifted from the Phase-B ROC panel and renders three
 * blocks, in descending order of how much weight the clinician should give them:
 *   1) WHERE THE CUT-POINT SITS IN THE DEVICE'S OWN READINGS -- the percentile of the device
 *      Timeline's band power the ROC's cut-point falls at, in device units. NOT a value to program
 *      (decision 302): the values to enter are the decision card's, and the comparison with what
 *      the device runs today is the "Programmed today" column of its table.
 *   2) Power / sample-size — current power vs AUC=0.5 on the count of independent ratings, and the
 *      ratings needed for 80% power (a clear "enough data yet?" verdict).
 *   3) Empirical µV²/LSB ratio — a confidence-rated FYI cross-check, explicitly NOT the deployable
 *      number.
 */
import { useEffect, useRef } from "react";
import Plotly from "plotly.js-dist";

import { Card } from "@mui/material";
import MDBox from "components/MDBox";
import MDTypography from "components/MDTypography";

import { lsbSettings } from "./candidateRequestParams";
import { SessionController } from "database/session-control";
import { useCachedResult } from "database/useCachedResult";

import { CL, recomputeSlots } from "views/Reports/moduleCacheKeys";
import PanelStaleNote from "./PanelStaleNote";
import PAL from "./palette";
import { TYPE, WRAP, CARD, STATE } from "assets/theme/base/tokens";
import { plotlyLayout, REF_LINE, wrapLabel } from "views/Reports/figureStyle";

const fmt = (v, d = 2) => (v == null || !Number.isFinite(Number(v)) ? "not reported" : Number(v).toFixed(d));

// Human labels for the modeled-LSB fallback tiers (backend _modeled_lsb_threshold_estimate). Ordered
// best→coarsest: a real per-contact modeled timeline, then the per-participant frozen conversion. The
// population-constant (k=269) tier was retired 2026-06-28 — when no fitted per-participant model exists
// the backend returns no modeled threshold (indeterminate) rather than a population-average guess.
// Shown on the ESTIMATED threshold card so the clinician sees which modeled source produced the number.
// The frozen conversion model's tier labels were removed (decision 218 deleted the model; SPEC
// section 5.2 item 7). Only the modelled timeline, which still exists, is named.
const TIER_LABEL = {
  modeled_timeline: "from the modelled device-unit timeline",
};

function LsbPowerPanel({ participantUid, bandCandidate, requestParams, cutpoint, onLsbThreshold }) {
  // NOT A VALUE TO PROGRAM, ON ANY ANSWER (decision 302). Until 2026-09-26 this panel headed its
  // number "THRESHOLD TO PROGRAM" at 26-point type when the device permitted the configuration, and
  // printed a "recommended vs programmed" box beside it. On RCS08 that number is not the one the
  // parameter table recommends: the percentile the ROC's cut-point falls at read 141.7 (L 1-3+,
  // modelled) and 143.0 (R 0-3+, measured) device units, where the table's upper threshold reads
  // 241.14 and 213.48. Two "recommended" thresholds on one page is one too many; this panel now says
  // only where the cut-point sits in the device's own readings.
  const pwRef = useRef(null);
  const thrRef = useRef(null);

  const bc = bandCandidate || {};
  const channelRaw = bc.contact;
  const centerHz = bc.center_freq_hz;
  const cutThr = cutpoint ? cutpoint.threshold : null;
  const cutDegenerate = !!(cutpoint && cutpoint.degenerate);

  // The request, minus the participant, is the cache key. The operating point is IN it, because
  // this panel exists to anchor that particular cut-point to device units — a different cut-point
  // is a different question, not a different view of the same answer.
  const settings = lsbSettings(bc, cutpoint, requestParams);

  const cached = useCachedResult({
    moduleKey: CL.lsbPower,
    uid: participantUid,
    settings,
    // Nothing is asked for until the ROC panel has settled on an operating point, because the
    // request has no meaning without one.
    enabled: !!participantUid && channelRaw != null && centerHz != null && cutThr != null,
    fetcher: () => SessionController.query("/api/queryLsbPower",
      { ParticipantId: participantUid, ...settings })
      .then((response) => (response && response.data) || null),
  });

  const raw = cached.data;
  const data = raw && raw.available ? raw : null;
  const loading = cached.loading;
  const err = cached.err || (raw && !raw.available ? (raw.reason || "unavailable") : null);

  const tl = data && data.threshold_lsb;
  const pw = data && data.power;
  const lr = data && data.lsb_ratio;

  // Audit [42]: lift the resolved device-LSB threshold + whether it is estimated up to the parent, so
  // the ROC panel's feature-histogram cut line can be annotated with the same device-unit value
  // (where the cut-point sits, not a value to program; decision 302) — closing the "oriented log-power ↔ LSB connected only by prose" gap. Fires only when the
  // value actually changes (keyed on the primitives, not the rebuilt tl object).
  const tlUpperLsb = tl && tl.available ? tl.upper_lsb : null;
  const tlEstimated = !!(tl && tl.available && tl.estimated);
  useEffect(() => {
    if (!onLsbThreshold) return;
    onLsbThreshold(tlUpperLsb != null && Number.isFinite(Number(tlUpperLsb))
      ? { upperLsb: Number(tlUpperLsb), estimated: tlEstimated } : null);
  }, [tlUpperLsb, tlEstimated]);  // eslint-disable-line react-hooks/exhaustive-deps

  // Draw the POWER-vs-N sufficiency curve once per payload: power to reject AUC=0.5 as the count of
  // independent ratings grows, with the 80% target line, and markers at the current N and the N
  // needed for 80% power. This replaces a 3-number readout a reviewer flagged — a clinician asking
  // "do I have enough pain ratings yet?" reads the answer off the curve's shape and the gap between
  // the two markers, not three separate figures. Plotly.react updates in place (no rebuild).
  useEffect(() => {
    const gd = pwRef.current;
    const curve = pw && pw.available && pw.curve;
    if (!gd || !curve || !Array.isArray(curve.n) || curve.n.length < 2) return;
    const tgt = pw.target_power != null ? pw.target_power : 0.80;
    const sufficient = !pw.more_data_needed;
    const curColor = sufficient ? PAL.series : PAL.warn;          // marker fill: filled when enough
    const curTextColor = sufficient ? PAL.ink : PAL.warnText;     // annotation text
    const nMax = Math.max(...curve.n);
    const traces = [
      // power curve
      { x: curve.n, y: curve.power.map((p) => p * 100), type: "scatter", mode: "lines",
        line: { color: PAL.series, width: 2 }, hoverinfo: "skip", showlegend: false },
      // current N marker (power at the POINT AUC — the optimistic end of the band)
      { x: [pw.n_ratings_current], y: [pw.power_current * 100], type: "scatter", mode: "markers",
        marker: { color: curColor, size: 12, line: { color: PAL.surface, width: 2 } },
        hovertemplate: `now: ${pw.n_ratings_current} ratings<br>chance of detecting a real link %{y:.0f}% (at the point reading)<extra></extra>`,
        showlegend: false },
    ];
    // audit C4: power BAND — the conservative end at the de-folded CI lower bound. Power is monotone
    // in AUC, so the point-AUC marker is optimistic; this open marker (and the connecting bar) shows
    // how far the honest power could fall if the true AUC sits at the CI lower bound. The "powered"
    // gate reads THIS end, not the filled marker above.
    const hasBand = pw.power_current_lo != null && pw.auc_lo != null;
    if (hasBand) {
      const yLo = pw.power_current_lo * 100;
      const yHi = pw.power_current * 100;
      traces.push(
        { x: [pw.n_ratings_current, pw.n_ratings_current], y: [yLo, yHi], type: "scatter",
          mode: "lines", line: { color: PAL.warnText, width: 1.4 }, hoverinfo: "skip",
          showlegend: false },
        { x: [pw.n_ratings_current], y: [yLo], type: "scatter", mode: "markers",
          marker: { color: PAL.surface, size: 11, symbol: "circle-open",
                    line: { color: PAL.warnText, width: 2 } },
          hovertemplate: `cautious: %{y:.0f}% at the lower end of the 95% range, ${pw.auc_lo.toFixed(2)}<extra></extra>`,
          showlegend: false });
    }
    const annotations = [
      { x: nMax * 1.02, y: tgt * 100, xanchor: "right", yanchor: "bottom",
        text: `${(tgt * 100).toFixed(0)}% target`, showarrow: false,
        font: { size: PAL.fs.body, color: PAL.ink3 } },
      // Static "now" annotation so the current marker is self-identifying in a printout / grayscale
      // (audit C7), not only on hover.
      // above its point, so it never meets the "lower end of range" label below (review 2026-10-02)
      { x: pw.n_ratings_current, y: pw.power_current * 100, xanchor: "center", yanchor: "bottom",
        yshift: 6, text: `${sufficient ? "" : "▲ "}now: ${pw.n_ratings_current}`, showarrow: false,
        font: { size: PAL.fs.body, color: curTextColor } },
    ];
    // audit C4: label the conservative (CI-lower-bound) end of the power band.
    if (hasBand) {
      annotations.push({ x: pw.n_ratings_current, y: pw.power_current_lo * 100,
        xanchor: "left", yanchor: "top", xshift: 8,
        text: `▲ lower end of range: ${Math.round(pw.power_current_lo * 100)}%`, showarrow: false,
        font: { size: PAL.fs.body, color: PAL.warnText } });
    }
    // needed-N marker (only when more data is needed and the number is known). Audit C5: place it at
    // the CURVE's own power at n_need (linear-interpolate the existing curve array) — NOT on the 80%
    // target line. The scalar n_ratings_needed comes from a closed-form SE²·N solve while the curve
    // is exact Hanley–McNeil, so pinning the marker to tgt made it sit visibly OFF the curve and read
    // as a glitch. Interpolating keeps marker and curve coincident.
    if (pw.more_data_needed && pw.n_ratings_needed != null) {
      const nNeed = pw.n_ratings_needed;
      const ns = curve.n; const ps = curve.power;
      let yNeed;
      if (nNeed <= ns[0]) {
        yNeed = ps[0];
      } else if (nNeed >= ns[ns.length - 1]) {
        yNeed = ps[ps.length - 1];
      } else {
        let j = 1;
        while (j < ns.length && ns[j] < nNeed) j += 1;
        const x0 = ns[j - 1]; const x1 = ns[j]; const y0 = ps[j - 1]; const y1 = ps[j];
        yNeed = x1 === x0 ? y1 : y0 + (y1 - y0) * ((nNeed - x0) / (x1 - x0));
      }
      traces.push({
        x: [nNeed], y: [yNeed * 100], type: "scatter", mode: "markers",
        marker: { color: PAL.neutral, size: 11, symbol: "circle-open", line: { width: 2 } },
        hovertemplate: `need ${nNeed} for a ${(tgt * 100).toFixed(0)}% chance<extra></extra>`,
        showlegend: false });
      annotations.push({ x: nNeed, y: yNeed * 100, xanchor: "center", yanchor: "bottom",
        yshift: 6, text: `need: ${nNeed}`, showarrow: false,
        font: { size: PAL.fs.body, color: PAL.ink3 } });
    }
    // Audit [19]: when the effective n is discounted for serial autocorrelation (design_effect > 1),
    // say so on the figure and clarify the x-axis is REAL ratings collected (power is evaluated at the
    // discounted effective count). At design_effect == 1 the panel is unchanged.
    const deff = pw.design_effect != null ? pw.design_effect : 1.0;
    const xTitle = deff > 1.0 ? "pain ratings collected" : "independent pain ratings";
    if (deff > 1.0) {
      // above the plot area, wrapped, not across the curve (review 2026-10-02: clipped both sides)
      annotations.push({ xref: "paper", yref: "paper", x: 0, y: 1, xanchor: "left", yanchor: "bottom",
        yshift: 4, align: "left",
        text: wrapLabel(`▲ counted as about ${(100 / deff).toFixed(0)}% as many independent ratings, because neighbouring ratings resemble each other`, 70),
        showarrow: false, font: { size: PAL.fs.body, color: PAL.warnText } });
    }
    const layout = plotlyLayout({
      margin: { l: 72, r: 16, t: deff > 1.0 ? 52 : 24, b: 48 }, height: deff > 1.0 ? 268 : 240,
      xaxis: { title: { text: xTitle }, range: [0, nMax * 1.02] },
      yaxis: { title: { text: wrapLabel("chance of detecting a real link with pain (%)", 24) }, range: [0, 106], dtick: 25 },
      shapes: [
        // the target line
        { type: "line", x0: 0, x1: nMax * 1.02, y0: tgt * 100, y1: tgt * 100, line: REF_LINE },
      ],
      annotations,
    });
    Plotly.react(gd, traces, layout, PAL.MODEBAR);
  }, [data]);  // eslint-disable-line react-hooks/exhaustive-deps

  // --- THRESHOLD GAUGE on the device Timeline distribution (Plotly): shows the recommended threshold
  // as a vertical marker against the device's own LSB distribution (p10/median/p90 from the backend),
  // with ±1σ error bars when the threshold is ESTIMATED from k (showing the calibration uncertainty).
  // Percentile-anchored thresholds are exact (no error bar). When threshold_mode is present, the mode
  // verdict annotation shows below.
  useEffect(() => {
    const gd = thrRef.current;
    if (!gd || !tl) { if (gd) Plotly.purge(gd); return; }
    const hasLsb = tl.available && tl.upper_lsb != null;
    const tm = data && data.threshold_mode;
    // Distribution whisker from device Timeline
    const p10 = tl.device_lsb_p10; const med = tl.device_lsb_median; const p90 = tl.device_lsb_p90;
    const hasDist = p10 != null && med != null && p90 != null;
    if (!hasLsb && !hasDist) { Plotly.purge(gd); return; }

    const traces = [];
    // Timeline distribution as a horizontal box (p10–p90 with median)
    if (hasDist) {
      traces.push({
        type: "box", x: [p10, med, p90], orientation: "h", name: "the device's own readings",
        marker: { color: PAL.neutral }, line: { color: PAL.neutral },
        boxpoints: false, showlegend: false, hoverinfo: "x",
        q1: [p10], median: [med], q3: [p90], lowerfence: [p10], upperfence: [p90],
      });
      // Actually draw as a shape+scatter since box from summary stats is tricky in plotly.js
    }
    // Threshold marker with optional error bars
    if (hasLsb) {
      const isEstimated = tl.method && tl.method.includes("modeled");
      // For a MODELLED threshold the bar either side is the calibration blocks' own raw scatter,
      // served as upper_lsb_lo / upper_lsb_hi (ruling A2, 2026-09-21); a measured one has no bar.
      const hasBand = isEstimated && Number.isFinite(tl.upper_lsb_lo) && Number.isFinite(tl.upper_lsb_hi);
      const errLo = hasBand ? tl.upper_lsb - tl.upper_lsb_lo : 0;
      const errHi = hasBand ? tl.upper_lsb_hi - tl.upper_lsb : 0;
      traces.push({
        type: "scatter", mode: "markers", x: [tl.upper_lsb], y: ["switching point"],
        marker: { color: PAL.series, size: 14, symbol: "diamond",
          line: { color: PAL.surface, width: 2 } },
        error_x: hasBand ? {
          type: "data", symmetric: false,
          array: [errHi], arrayminus: [errLo],
          color: PAL.series, thickness: 2, width: 6,
        } : undefined,
        hovertemplate: isEstimated
          ? `Modelled: ${fmt(tl.upper_lsb, 0)} LSB${hasBand ? ` (typical spread ${fmt(tl.upper_lsb_lo, 0)} to ${fmt(tl.upper_lsb_hi, 0)})` : ""}<extra></extra>`
          : `Read off the device's own readings: ${fmt(tl.upper_lsb, 0)} LSB (percentile ${fmt(tl.percentile, 0)})<extra></extra>`,
        showlegend: false,
      });
    }

    // Distribution range as horizontal markers
    if (hasDist) {
      traces.push({
        type: "scatter", mode: "markers+text", x: [p10, med, p90],
        y: ["device readings", "device readings", "device readings"],
        marker: { color: [PAL.neutral, PAL.neutral, PAL.neutral], size: [8, 12, 8],
          symbol: ["line-ns", "line-ns", "line-ns"],
          line: { width: 2, color: PAL.neutral } },
        text: ["10th", "median", "90th"], textposition: "top center",
        textfont: { size: PAL.fs.body, color: PAL.ink3 },
        hovertemplate: "%{x:.0f} LSB<extra></extra>", showlegend: false,
      });
      // Range bar
      traces.push({
        type: "scatter", mode: "lines", x: [p10, p90], y: ["device readings", "device readings"],
        line: { color: PAL.neutral, width: 4 },
        hoverinfo: "skip", showlegend: false,
      });
    }

    // Mode verdict annotation
    const modeNote = (tm && tm.chosen)
      ? `${tm.requested_mode}: ${tm.threshold_usable ? "✓ usable" : "▲ not usable"} · ${tm.chosen.fft_size}-point transform · ${Math.round(tm.chosen.averaging_ms_adaptive)} ms averaging`
      : "";
    const noteColor = (tm && tm.threshold_usable) ? PAL.ink : PAL.warnText;

    const layout = plotlyLayout({
      // the mode note sits above the plot, wrapped, and the 10th/median/90th labels have room
      // under it (review 2026-10-02: the note overlapped the x title and was cut at the right)
      margin: { l: 112, r: 16, t: modeNote ? 52 : 28, b: 48 }, height: modeNote ? 172 : 140,
      xaxis: { title: { text: "band power (device units, LSB)" } },
      yaxis: { fixedrange: true, showline: false, ticks: "" },
      annotations: modeNote ? [{
        xref: "paper", yref: "paper", x: 0, y: 1, xanchor: "left", yanchor: "bottom", yshift: 22,
        text: wrapLabel(modeNote, 70), showarrow: false, font: { size: PAL.fs.body, color: noteColor }, align: "left",
      }] : [],
    });
    // This gauge has never carried a toolbar (unlike the power curve above it): it is read-only,
    // not a value to program (decision 302), so there is nothing on it a reviewer needs to export.
    Plotly.react(gd, traces, layout, { displayModeBar: false, responsive: true });
  }, [data, tl]);  // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => () => {
    if (pwRef.current) Plotly.purge(pwRef.current);
    if (thrRef.current) Plotly.purge(thrRef.current);
  }, []);

  const head = (text) => (
    <MDTypography component="h4" sx={{ ...TYPE.body, fontWeight: 600, color: PAL.ink }}>{text}</MDTypography>
  );
  return (
    <Card sx={{ ...CARD, width: "100%" }}>
      <MDBox p={3}>
        <MDTypography component="h3" sx={{ ...TYPE.title, ...WRAP.balance, color: PAL.ink, mb: 1 }}>
          Switching point in device units
        </MDTypography>
        <MDTypography sx={{ ...TYPE.body, color: PAL.ink3, mb: 1 }}>
          LSB is the device&apos;s own unit of band power: the number its sensing readout prints.
        </MDTypography>
        <PanelStaleNote stale={cached.stale} staleReasons={cached.staleReasons}
          loading={cached.loading} notKept={cached.notKept}
          onRecompute={() => recomputeSlots(participantUid, [CL.lsbPower])} />

        {/* The switching point chosen on the curve to the left, the rule that chose it and how it
            performs, then (when found below) the same point in device units: one connected
            statement rather than two numbers a reader has to bridge between panels. */}
        {cutpoint && cutThr != null ? (
          <MDTypography sx={{ ...TYPE.body, color: PAL.ink, mb: 1 }}>
            {`Switching point (${cutpoint.rule || "youden"}): high-pain moments caught ${fmt(cutpoint.sensitivity)}, `
              + `low-pain moments left alone ${fmt(cutpoint.specificity)}; band power ≥ ${fmt(cutThr, 3)} on the standardised scale`}
            {tl && tl.available && tl.upper_lsb != null ? (
              <b style={{ fontWeight: 600, color: tl.estimated ? PAL.warnText : PAL.ink }}>
                {` → ${tl.estimated ? "≈" : "="} ${fmt(tl.upper_lsb, 1)} LSB${tl.estimated ? " (estimated)" : ""}`}
                {tl.estimated ? <span aria-hidden="true" style={{ marginLeft: 6 }}>▲</span> : null}
              </b>
            ) : null}
          </MDTypography>
        ) : null}

        {cutThr == null ? (
          <MDTypography sx={{ ...TYPE.body, color: PAL.ink2 }}>
            Choose a switching point on the curve beside this: the device-unit value and the chance of
            detecting a real link are read from it.
          </MDTypography>
        ) : loading ? (
          <MDTypography sx={{ ...TYPE.body, color: PAL.ink2 }}>
            Reading the device&apos;s own band power and working out the chance of detecting a real link…
          </MDTypography>
        ) : err ? (
          <MDTypography sx={{ ...TYPE.body, color: PAL.ink2 }}>
            <span aria-hidden="true" style={{ marginRight: 6 }}>{STATE.notChecked.glyph}</span>
            {`Not available: ${err}.`}
          </MDTypography>
        ) : data ? (
          <>
            {/* A switching point that switches almost always or almost never must not be presented
                as a usable device setting. Said before the number. */}
            {cutDegenerate ? (
              <MDTypography sx={{ ...TYPE.body, fontWeight: 600, color: PAL.warnText, mb: 1.5 }}>
                <span aria-hidden="true" style={{ marginRight: 6 }}>{STATE.caution.glyph}</span>
                The chosen switching point would switch almost never or almost always, so the value
                below could not drive closed-loop stimulation. Choose a balanced switching point on
                the curve before programming.
              </MDTypography>
            ) : null}

            {/* 1) WHERE THE SWITCHING POINT SITS -- MEASURED on the device's own readings. */}
            {tl && tl.available && !tl.estimated ? (
              <MDBox mb={2}>
                {head("Where the switching point sits in the device's own readings (not a value to program)")}
                <MDTypography sx={{ ...TYPE.answer, ...WRAP.balance, color: PAL.ink, mt: 0.5 }}>
                  {`percentile ${fmt(tl.percentile, 0)} = ${fmt(tl.upper_lsb, 1)} LSB`}
                </MDTypography>
                <MDTypography display="block" sx={{ ...TYPE.body, color: PAL.ink2, mt: 0.5 }}>
                  {`of the device's own band-power readings, ${tl.n_timeline_samples} readings in this band; `
                    + `10th percentile / median / 90th percentile ${fmt(tl.device_lsb_p10, 0)} / ${fmt(tl.device_lsb_median, 0)} / `
                    + `${fmt(tl.device_lsb_p90, 0)}. The values to enter are on the decision card.`}
                </MDTypography>
              </MDBox>
            ) : tl && tl.available && tl.estimated ? (
              /* WHERE IT WOULD SIT -- ESTIMATED (the device never sensed this band). Caution ink and
                 the typical spread, so a modelled estimate is never mistaken for a measured one. */
              <MDBox mb={2}>
                <MDTypography sx={{ ...TYPE.body, fontWeight: 600, color: PAL.warnText }}>
                  <span aria-hidden="true" style={{ marginRight: 6 }}>{STATE.caution.glyph}</span>
                  {`Estimated: where the switching point would sit (not a value to program), ${TIER_LABEL[tl.tier] || "modelled"}${tl.freq_extrapolated ? ", beyond the bands measured" : ""}`}
                </MDTypography>
                <MDTypography sx={{ ...TYPE.answer, ...WRAP.balance, color: PAL.warnText, mt: 0.5 }}>
                  {`power ≈ ${fmt(tl.upper_lsb, 1)} LSB`}
                </MDTypography>
                <MDTypography display="block" sx={{ ...TYPE.body, color: PAL.ink2, mt: 0.5 }}>
                  {(Number.isFinite(tl.upper_lsb_lo) && Number.isFinite(tl.upper_lsb_hi)
                      ? `typical spread ${fmt(tl.upper_lsb_lo, 1)} to ${fmt(tl.upper_lsb_hi, 1)} LSB (±${fmt(100 * (tl.scatter_frac || 0), 0)}%, the typical spread of the conversion ratio over ${tl.scatter_n_blocks || 0} blocks)`
                      : "no spread: how much the conversion varies is unknown for this participant")
                    + (tl.percentile != null ? ` · read at percentile ${fmt(tl.percentile, 0)}` : "")
                    + (tl.n_modeled_points ? ` · ${tl.n_modeled_points} modelled readings in this band` : "")}
                </MDTypography>
                <MDTypography display="block" sx={{ ...TYPE.body, color: PAL.ink2, mt: 0.5 }}>
                  {tl.note || "Modelled estimate; the device never sensed this band. Confirm on device readings."}
                </MDTypography>
              </MDBox>
            ) : (
              <MDBox mb={2}>
                <MDTypography sx={{ ...TYPE.body, fontWeight: 600, color: PAL.ink2 }}>
                  <span aria-hidden="true" style={{ marginRight: 6 }}>{STATE.notChecked.glyph}</span>
                  No device-unit value for this switching point
                </MDTypography>
                <MDTypography display="block" sx={{ ...TYPE.body, color: PAL.ink2, mt: 0.5 }}>
                  {(tl && tl.reason) || "unavailable"}
                  {tl && tl.hint ? `: ${tl.hint}` : ""}
                </MDTypography>
              </MDBox>
            )}

            {/* 1a) The switching point against the device's own readings, with the typical spread
                either side when it is modelled. */}
            {tl ? (
              <MDBox mb={2}>
                <div ref={thrRef} style={{ width: "100%" }} />
              </MDBox>
            ) : null}

            {/* 1b) The recommended-versus-programmed comparison that stood here moved to the
                decision card's table, as its "Programmed today" column (decision 302). */}

            {/* 2) HOW MANY RATINGS ARE ENOUGH: a curve rather than three numbers. */}
            {pw && pw.available ? (
              <MDBox mb={2}>
                {head(`Rating count: ${fmt(pw.power_current * 100, 0)}% power at ${pw.n_ratings_current} ratings`)}
                <div ref={pwRef}
                  style={{ width: "100%", display: pw.curve ? "block" : "none" }} />
                <MDTypography display="block"
                  sx={{ ...TYPE.body, mt: 0.5, color: pw.more_data_needed ? PAL.warnText : PAL.ink }}>
                  <span aria-hidden="true" style={{ marginRight: 6 }}>
                    {pw.more_data_needed ? STATE.caution.glyph : STATE.pass.glyph}
                  </span>
                  {pw.more_data_needed
                    ? `Not enough: about ${(pw.n_ratings_needed - pw.n_ratings_current)} more independent ratings needed for 80% power.`
                    : "Enough ratings for 80% power."}
                </MDTypography>
              </MDBox>
            ) : (
              <MDTypography sx={{ ...TYPE.body, color: PAL.ink2, mb: 2 }}>
                {`Chance of detecting a real link: ${(pw && pw.reason) || "unavailable"}.`}
              </MDTypography>
            )}

            {/* 3) µV²/LSB RATIO, for information */}
            <MDBox pt={2} sx={{ borderTop: `1px solid ${PAL.rule}` }}>
              {head("µV²/LSB from streaming: independent check, not a programmed value")}
              {lr && lr.available ? (
                <MDTypography display="block" sx={{ ...TYPE.body, color: PAL.ink2, mt: 0.5 }}>
                  {`median ${lr.median.toExponential(2)} µV²/LSB `}
                  <span style={{ color: lr.confidence === "high" ? PAL.ink : PAL.warnText, fontWeight: 600 }}>
                    {lr.confidence === "high" ? null : <span aria-hidden="true" style={{ marginRight: 4 }}>▲</span>}
                    {`(confidence: ${lr.confidence})`}
                  </span>
                  {` · spread ${fmt(lr.cv)} of the median · ${fmt(lr.fold_of_constant_in_effect, 2)}× the constant in effect (1 µV² = ${fmt(1 / lr.constant_in_effect_uv2_per_lsb, 2)} LSB) · ${lr.n} paired sessions`}
                </MDTypography>
              ) : (
                <MDTypography display="block" sx={{ ...TYPE.body, color: PAL.ink2, mt: 0.5 }}>
                  {(lr && lr.reason) || "unavailable"}
                </MDTypography>
              )}
            </MDBox>
          </>
        ) : null}
      </MDBox>
    </Card>
  );
}

export default LsbPowerPanel;
