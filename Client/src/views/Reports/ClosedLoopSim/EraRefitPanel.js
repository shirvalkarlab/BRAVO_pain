/**
 * Phase D panel: per-era refit of the deployment ROC (OFF / LOW / HIGH stim).
 *
 * Fetches /api/queryDeploymentRocByEra and renders the per-era AUC (with clustered bootstrap CI)
 * as a FOREST / dot-and-whisker plot against the pooled value, plus a portability verdict: a band
 * whose AUC or cut-point swings across stim eras is a fragile closed-loop anchor even with a strong
 * pooled AUC. Eras with too few high/low samples are drawn as "insufficient" rows rather than hidden.
 *
 * The forest plot replaces the four text EraCards a reviewer flagged: a clinician judging
 * portability needs to SEE whether the per-era CIs overlap the pooled band, which reading four
 * separate AUC numbers does not afford. The Plotly graph is drawn once per dataset with the
 * imperative Plotly.react pattern the module standardized on (no figure rebuilds on interaction).
 */
import { useEffect, useRef, useState } from "react";
import Plotly from "plotly.js-dist";

import { Card } from "@mui/material";
import MDBox from "components/MDBox";
import MDTypography from "components/MDTypography";

import { SessionController } from "database/session-control";
import PAL from "./palette";

const fmt = (v, d = 2) => (v == null || !Number.isFinite(Number(v)) ? "—" : Number(v).toFixed(d));

// Forest-plot row order, top-to-bottom: stim eras low→high, then a separator, then Pooled at the
// bottom as the reference series the per-era points are judged against.
const ROW_ORDER = ["OFF", "LOW", "HIGH", "Pooled"];

function EraRefitPanel({ participantUid, bandCandidate, requestParams }) {
  const ref = useRef(null);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState(null);

  const bc = bandCandidate || {};
  const channelRaw = bc.contact;
  const centerHz = bc.center_freq_hz;
  const bandWidthHz = bc.bandwidth_hz || 5.0;

  useEffect(() => {
    if (!participantUid || channelRaw == null || centerHz == null) return;
    setLoading(true); setErr(null);
    SessionController.query("/api/queryDeploymentRocByEra", {
      ParticipantId: participantUid,
      Channel: channelRaw,
      CenterHz: Number(centerHz),
      BandWidthHz: Number(bandWidthHz),
      ...requestParams,
    }).then((response) => {
      const d = response && response.data;
      if (d && d.available && d.by_era && d.by_era.available) setData(d.by_era);
      else { setData(null); setErr((d && (d.reason || (d.by_era && d.by_era.reason))) || "unavailable"); }
      setLoading(false);
    }).catch(() => { setData(null); setErr("request failed"); setLoading(false); });
  }, [participantUid, channelRaw, centerHz, bandWidthHz, requestParams]);

  // Portability verdict by INFERENCE, not raw point-AUC spread (audit C3). The backend now orients
  // every era to the POOLED sign, so a reversed era reports a signed AUC < 0.5 (any_reversed), and
  // exposes whether each era's bootstrap CI overlaps the pooled CI (portable_by_ci) plus the formal
  // band×era LRT (stim_lrt). We decide on those, scope the wording to stim STATE (not time), and
  // keep the raw spreads only as a descriptive annotation.
  let verdict = null;
  if (data) {
    const aucSpread = data.auc_spread;
    const cutSpread = data.cutpoint_spread;
    const estimable = data.n_eras_estimable;
    const lrt = data.stim_lrt || {};
    const spreadNote = (aucSpread != null)
      ? ` (AUC spread ${fmt(aucSpread)}${cutSpread != null ? `, cut-point spread ${fmt(cutSpread, 2)}` : ""}, descriptive)`
      : "";
    const lrtNote = (lrt.available && lrt.lrt_p != null)
      ? ` band×era LRT p=${fmt(lrt.lrt_p, 3)}.` : " band×era LRT did not converge.";
    if (estimable < 2) {
      verdict = { color: PAL.neutral, text: "Only one stim era has enough data — per-era portability across stim states can't be assessed." };
    } else if (data.any_reversed) {
      // The worst closed-loop failure: the band's direction flips under stim. Hard fragile.
      verdict = { color: PAL.fail, text: `Direction REVERSES under stim: at least one era's band–pain relationship flips sign (AUC < 0.5 under the pooled orientation). A controller anchored on the pooled threshold would ramp the WRONG way in that era — do not deploy as a fixed-sign adaptive band.${lrtNote}` };
    } else if (lrt.available && lrt.stim_stable === false) {
      verdict = { color: PAL.fail, text: `Fragile across stim states: the band×era interaction is significant (p=${fmt(lrt.lrt_p, 3)}) — the band's pain-prediction depends on stim state, so the same threshold may not hold once stim changes.${spreadNote}` };
    } else if (data.portable_by_ci === false) {
      verdict = { color: PAL.warnText, text: `Per-era CIs do not all overlap the pooled estimate — portability is uncertain across stim states.${lrtNote}${spreadNote}` };
    } else if (data.portable_by_ci === true) {
      verdict = { color: PAL.pass, text: `Portable across stim states: no era reverses direction and every era's 95% CI overlaps the pooled estimate — the threshold holds across stim levels.${lrtNote}${spreadNote}` };
    } else {
      verdict = { color: PAL.neutral, text: `Per-era portability across stim states is indeterminate from the available eras.${lrtNote}${spreadNote}` };
    }
  }

  // Draw the AUC forest plot once per dataset: one row per era (+ Pooled), point = AUC, whiskers =
  // 95% clustered-bootstrap CI, a dotted chance line at 0.5, and a shaded pooled-CI reference band
  // so the eye reads directly whether each era's CI overlaps the pooled estimate. Estimable eras
  // only get a point/whisker; non-estimable eras still occupy a labeled row (drawn as a faint "n/a"
  // marker) so the OFF/LOW/HIGH structure is always visible. Plotly.react updates in place.
  useEffect(() => {
    if (!ref.current || !data) return;
    const rows = ROW_ORDER.map((tag) => ({
      tag, era: tag === "Pooled" ? data.pooled : data.eras[tag],
      count: tag === "Pooled" ? null : (data.era_counts && data.era_counts[tag]),
    }));
    // y positions top-to-bottom (Plotly y grows upward, so reverse the index).
    const yOf = (i) => rows.length - i;
    const traces = [];
    const pooled = data.pooled;
    const yLo = 0.4; const yHi = rows.length + 0.6;
    // X-range must show reversed eras (signed AUC can fall below 0.5 under the pooled orientation,
    // audit C3), so anchor the left edge at the smallest estimable lower-CI (floored at 0).
    let xMin = 0.5;
    rows.forEach((r) => {
      if (r.era && r.era.available) {
        if (r.era.auc != null) xMin = Math.min(xMin, r.era.auc);
        if (r.era.auc_lo != null) xMin = Math.min(xMin, r.era.auc_lo);
      }
    });
    const xLeft = Math.max(0, Math.min(0.42, xMin - 0.05));

    // (0) pooled-CI reference band as a filled rectangle behind everything, bracketed with dotted
    // edges so it reads in grayscale (audit C7) and labeled by a static annotation below.
    const annotations = [];
    if (pooled && pooled.available && pooled.auc_lo != null && pooled.auc_hi != null) {
      traces.push({
        x: [pooled.auc_lo, pooled.auc_hi, pooled.auc_hi, pooled.auc_lo],
        y: [yLo, yLo, yHi, yHi],
        fill: "toself", mode: "none", fillcolor: `${PAL.accent}18`,
        hoverinfo: "skip", showlegend: false,
      });
      [pooled.auc_lo, pooled.auc_hi].forEach((xb) => {
        traces.push({ x: [xb, xb], y: [yLo, yHi], type: "scatter", mode: "lines",
          line: { color: PAL.accent, dash: "dot", width: 1 }, hoverinfo: "skip", showlegend: false });
      });
      annotations.push({ x: pooled.auc_hi, y: yHi, xref: "x", yref: "y", yanchor: "bottom",
        xanchor: "left", text: "shaded = pooled 95% CI", showarrow: false,
        font: { size: 8.5, color: PAL.accent } });
    }
    // (1) chance line at AUC = 0.5.
    traces.push({
      x: [0.5, 0.5], y: [yLo, yHi], type: "scatter", mode: "lines",
      line: { color: PAL.neutral, dash: "dot", width: 1 }, hoverinfo: "skip", showlegend: false,
    });
    // (2) per-row CI whiskers + (3) AUC points, colored by era role.
    rows.forEach((r, i) => {
      const y = yOf(i);
      const color = PAL.eraColor(r.tag);
      const ok = r.era && r.era.available;
      if (ok && r.era.auc_lo != null && r.era.auc_hi != null) {
        traces.push({
          x: [r.era.auc_lo, r.era.auc_hi], y: [y, y], type: "scatter", mode: "lines",
          line: { color, width: 2 }, hoverinfo: "skip", showlegend: false,
        });
      }
      if (ok) {
        // A reversed era (signed AUC < 0.5) is the worst portability failure: mark it with an X and
        // a vermillion fail color regardless of its era role, so it never reads as a normal point.
        const reversed = !!r.era.reversed;
        traces.push({
          x: [r.era.auc], y: [y], type: "scatter", mode: "markers",
          marker: { color: reversed ? PAL.fail : color, size: r.tag === "Pooled" ? 13 : 11,
            symbol: reversed ? "x" : (r.tag === "Pooled" ? "diamond" : "circle"),
            line: { color: "#fff", width: 1.5 } },
          hovertemplate: `${r.tag}: AUC %{x:.2f}`
            + (reversed ? " (direction REVERSED vs pooled)" : "")
            + (r.era.auc_lo != null ? `<br>95% CI ${fmt(r.era.auc_lo)}–${fmt(r.era.auc_hi)}` : "")
            + `<br>${r.era.n_clusters ?? "—"} ratings · prev ${fmt(r.era.prevalence)}<extra></extra>`,
          showlegend: false,
        });
        if (reversed) {
          annotations.push({ x: r.era.auc, y, xref: "x", yref: "y", yanchor: "bottom",
            xanchor: "center", text: "reversed", showarrow: false,
            font: { size: 8.5, color: PAL.fail }, yshift: 8 });
        }
      } else {
        // Non-estimable era (audit C7): do NOT place a glyph on the chance line — that reads as
        // "performs at chance". Instead label the row "n/a" at the LEFT axis margin, off the AUC
        // scale, so the row stays visible without encoding absence as a meaningful AUC value.
        annotations.push({ x: xLeft, y, xref: "x", yref: "y", xanchor: "left", yanchor: "middle",
          text: "n/a (insufficient samples)", showarrow: false,
          font: { size: 9, color: PAL.neutral, style: "italic" } });
      }
    });

    const tickText = rows.map((r) => {
      if (r.tag === "Pooled") return "<b>Pooled</b>";
      const n = r.count != null ? ` (${r.count})` : "";
      return `${r.tag}${n}`;
    });
    const layout = {
      margin: { l: 64, r: 14, t: 10, b: 40 }, height: 220,
      xaxis: { title: { text: "AUC (95% clustered-bootstrap CI)", font: { size: 11 } },
        range: [xLeft, 1.02], zeroline: false, tickfont: { size: 10 }, dtick: 0.1 },
      yaxis: { tickmode: "array", tickvals: rows.map((_, i) => yOf(i)), ticktext: tickText,
        range: [yLo, yHi], tickfont: { size: 10.5 }, automargin: true },
      annotations, showlegend: false,
    };
    Plotly.react(ref.current, traces, layout, PAL.MODEBAR);
  }, [data]);  // eslint-disable-line react-hooks/exhaustive-deps

  // Purge on unmount only (keep the node across refits).
  useEffect(() => () => { if (ref.current) Plotly.purge(ref.current); }, []);

  return (
    <Card sx={{ width: "100%" }}>
      <MDBox p={2}>
        <MDTypography variant="h6" sx={{ fontSize: 14, mb: 1 }}>
          Per-era refit (OFF / LOW / HIGH stim)
        </MDTypography>
        {loading ? (
          <MDTypography variant="caption" color="text" sx={{ fontStyle: "italic", fontSize: 11 }}>
            Refitting the ROC within each stim era…
          </MDTypography>
        ) : err ? (
          <MDTypography variant="caption" sx={{ fontSize: 11, color: PAL.fail }}>
            {`Unavailable: ${err}.`}
          </MDTypography>
        ) : null}

        {/* Always-mounted forest plot; hidden until data arrives so the Plotly node survives refits. */}
        <div ref={ref} style={{ width: "100%", display: data && !loading && !err ? "block" : "none" }} />

        {data && !loading && !err ? (
          <>
            {verdict ? (
              <MDBox mt={1.2} p={1} sx={{ borderRadius: "6px", backgroundColor: `${verdict.color}12`,
                border: `1px solid ${verdict.color}40` }}>
                <MDTypography variant="caption" sx={{ fontSize: 11, color: verdict.color, fontWeight: "bold" }}>
                  {verdict.text}
                </MDTypography>
              </MDBox>
            ) : null}
            <MDTypography variant="caption" display="block" color="text" sx={{ fontSize: 9, mt: 0.6 }}>
              {`Eras: OFF < ${data.thresholds_mA.off_max} mA · LOW ≤ ${data.thresholds_mA.low_max} mA · HIGH above. `
                + "Same era boundaries as the stim-stability LRT."}
            </MDTypography>
          </>
        ) : null}
      </MDBox>
    </Card>
  );
}

export default EraRefitPanel;
