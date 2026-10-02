/**
 * Phase D panel: per-era refit of the deployment ROC (OFF / LOW / HIGH stim).
 *
 * Fetches /api/queryDeploymentRocByEra and renders the per-era AUC (with clustered bootstrap CI)
 * as a FOREST / dot-and-whisker plot against the pooled value, plus the per-state check as supporting
 * detail for the page's one stability answer (2026-10-02; `eraDetail`): a band
 * whose AUC or cut-point swings across stim eras is a fragile closed-loop anchor even with a strong
 * pooled AUC. Eras with too few high/low samples are drawn as "insufficient" rows rather than hidden.
 *
 * The forest plot replaces the four text EraCards a reviewer flagged: a clinician judging
 * portability needs to SEE whether the per-era CIs overlap the pooled band, which reading four
 * separate AUC numbers does not afford. The Plotly graph is drawn once per dataset with the
 * imperative Plotly.react pattern the module standardized on (no figure rebuilds on interaction).
 */
import { useEffect, useRef } from "react";
import Plotly from "plotly.js-dist";

import { Card } from "@mui/material";
import MDBox from "components/MDBox";
import MDTypography from "components/MDTypography";

import { SessionController } from "database/session-control";
import { useCachedResult } from "database/useCachedResult";

import { CL, recomputeSlots } from "views/Reports/moduleCacheKeys";
import PanelStaleNote from "./PanelStaleNote";
import PAL from "./palette";
import { TYPE, WRAP, CARD, STATE } from "assets/theme/base/tokens";
import { plotlyLayout, REF_LINE, wrapLabel } from "views/Reports/figureStyle";

const fmt = (v, d = 2) => (v == null || !Number.isFinite(Number(v)) ? "not reported" : Number(v).toFixed(d));

/** The per-state check, as SUPPORTING DETAIL for the page's one stability answer (the PI,
 *  2026-10-02): "Stability across stimulation states" above gives the answer; this card printed a
 *  second one ("Holds", with a tick) beside it. Facts only; `caution` marks a fact that is a warning
 *  (a confident reversal, or the interaction test finding a difference), drawn with its triangle.
 *  The checks are the same as before (audit C3: decided on inference, not on raw spreads). */
export function eraDetail(data) {
  if (!data) return null;
  const lrt = data.stim_lrt || {};
  const spreadNote = (data.auc_spread != null)
    ? ` The readings span ${fmt(data.auc_spread)}${data.cutpoint_spread != null ? ` and the switching points ${fmt(data.cutpoint_spread, 2)}` : ""} across states (described, not tested).`
    : "";
  const lrtNote = (lrt.available && lrt.lrt_p != null)
    ? ` Test of whether the link differs between states: p ${fmt(lrt.lrt_p, 3)}.`
    : " The test of whether the link differs between states did not converge.";
  // A state whose POINT AUC dipped below 0.5 but whose CI still straddles chance is not a reversal.
  const dipNote = (!data.any_reversed && data.any_below_half)
    ? " One state fell below 0.5, but its 95% range includes 0.5." : "";
  const where = " Supporting detail; the stability answer is the one in \"Stability across stimulation states\" above.";
  let caution = false;
  let text;
  if (data.n_eras_estimable < 2) {
    text = "Only one stimulation state has enough data for a reading within each state.";
  } else if (data.any_reversed) {
    caution = true;
    text = `In at least one state the whole 95% range sits below 0.5, the opposite way to all states together: a device set on the all-states switching point would adjust the wrong way there.${lrtNote}`;
  } else if (lrt.available && lrt.stim_stable === false) {
    caution = true;
    text = `The test finds the link differs between stimulation states (p ${fmt(lrt.lrt_p, 3)}).${spreadNote}`;
  } else if (data.portable_by_ci === false) {
    text = `Not every state's 95% range overlaps the reading for all states together.${lrtNote}${spreadNote}`;
  } else if (data.portable_by_ci === true) {
    text = `Every state's 95% range overlaps the reading for all states together, and no state clearly reverses.${lrtNote}${dipNote}${spreadNote}`;
  } else {
    text = `The states available do not allow this check.${lrtNote}${dipNote}${spreadNote}`;
  }
  return { caution, text: text + where };
}

// Forest-plot row order, top-to-bottom: stim eras low→high, then a separator, then Pooled at the
// bottom as the reference series the per-era points are judged against.
const ROW_ORDER = ["OFF", "LOW", "HIGH", "Pooled"];
// The server's state names in plain words (SPEC section 6: "stim era" -> "stimulation state").
const STATE_WORDS = { OFF: "off", LOW: "low current", HIGH: "high current", Pooled: "all states" };

function EraRefitPanel({ participantUid, bandCandidate, requestParams }) {
  const ref = useRef(null);

  const bc = bandCandidate || {};
  const channelRaw = bc.contact;
  const centerHz = bc.center_freq_hz;
  const bandWidthHz = bc.bandwidth_hz || 5.0;

  // The request, minus the participant, is the cache key. See useDeploymentReport for why that
  // rule rather than a hand-kept list: the body is the complete statement of what changes the
  // answer, so a key derived from it cannot fall behind the request.
  const settings = {
    Channel: channelRaw,
    CenterHz: centerHz == null ? null : Number(centerHz),
    BandWidthHz: Number(bandWidthHz),
    ...requestParams,
  };

  const cached = useCachedResult({
    moduleKey: CL.era,
    uid: participantUid,
    settings,
    enabled: !!participantUid && channelRaw != null && centerHz != null,
    fetcher: () => SessionController.query("/api/queryDeploymentRocByEra",
      { ParticipantId: participantUid, ...settings })
      .then((response) => (response && response.data) || null),
  });

  // The panel has always worked on the `by_era` sub-object rather than the envelope, and it keeps
  // doing so. The ENVELOPE is what gets cached, because the reason an unavailable answer gives is
  // in the envelope and is worth keeping alongside the answer it explains.
  const env = cached.data;
  const byEra = env && env.available && env.by_era && env.by_era.available ? env.by_era : null;
  const data = byEra;
  const loading = cached.loading;
  const err = cached.err
    || (env && !byEra
      ? ((env.reason || (env.by_era && env.by_era.reason)) || "unavailable")
      : null);

  // Portability verdict by INFERENCE, not raw point-AUC spread (audit C3). The backend now orients
  // every era to the POOLED sign, so a reversed era reports a signed AUC < 0.5 (any_reversed), and
  // exposes whether each era's bootstrap CI overlaps the pooled CI (portable_by_ci) plus the formal
  // band×era LRT (stim_lrt). We decide on those, scope the wording to stim STATE (not time), and
  // keep the raw spreads only as a descriptive annotation.
  const verdict = eraDetail(data);

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
        fill: "toself", mode: "none", fillcolor: PAL.fillMuted,
        hoverinfo: "skip", showlegend: false,
      });
      [pooled.auc_lo, pooled.auc_hi].forEach((xb) => {
        traces.push({ x: [xb, xb], y: [yLo, yHi], type: "scatter", mode: "lines",
          line: { color: PAL.graphic, dash: "dot", width: 1 }, hoverinfo: "skip", showlegend: false });
      });
      // top left of the figure, clear of the toolbar at the top right (review 2026-10-02)
      annotations.push({ x: 0, y: 1, xref: "paper", yref: "paper", yanchor: "bottom",
        xanchor: "left", text: "shaded: 95% range, all states together", showarrow: false,
        font: { size: PAL.fs.body, color: PAL.ink3 } });
    }
    // (1) chance line at AUC = 0.5.
    traces.push({
      x: [0.5, 0.5], y: [yLo, yHi], type: "scatter", mode: "lines",
      line: REF_LINE, hoverinfo: "skip", showlegend: false,
    });
    annotations.push({ x: 0.5, y: yLo, xref: "x", yref: "y", yanchor: "top", xanchor: "center",
      text: "coin toss", showarrow: false, font: { size: PAL.fs.body, color: PAL.ink3 } });
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
          marker: { color, size: r.tag === "Pooled" ? 13 : 11,
            symbol: reversed ? "x" : (r.tag === "Pooled" ? "diamond" : "circle"),
            line: { color: PAL.surface, width: 1.5 } },
          hovertemplate: `${STATE_WORDS[r.tag] || r.tag}: tells high pain from low %{x:.2f}`
            + (reversed ? " (reversed against all states together)" : "")
            + (r.era.auc_lo != null ? `<br>95% range ${fmt(r.era.auc_lo)} to ${fmt(r.era.auc_hi)}` : "")
            + `<br>${r.era.n_clusters ?? "not reported"} ratings · share of high-pain reports ${fmt(r.era.prevalence)}<extra></extra>`,
          showlegend: false,
        });
        if (reversed) {
          annotations.push({ x: r.era.auc, y, xref: "x", yref: "y", yanchor: "bottom",
            xanchor: "center", text: "▲ reversed", showarrow: false,
            font: { size: PAL.fs.body, color: PAL.warnText }, yshift: 8 });
        }
      } else {
        // Non-estimable era (audit C7): do NOT place a glyph on the chance line — that reads as
        // "performs at chance". Instead label the row "n/a" at the LEFT axis margin, off the AUC
        // scale, so the row stays visible without encoding absence as a meaningful AUC value.
        annotations.push({ x: xLeft, y, xref: "x", yref: "y", xanchor: "left", yanchor: "middle",
          text: "not enough readings", showarrow: false,
          font: { size: PAL.fs.body, color: PAL.ink3 } });
      }
    });

    const tickText = rows.map((r) => {
      if (r.tag === "Pooled") return "all states";
      const n = r.count != null ? ` (${r.count})` : "";
      return `${STATE_WORDS[r.tag] || r.tag}${n}`;
    });
    const layout = plotlyLayout({
      margin: { l: 96, r: 16, t: 32, b: 64 }, height: 264,
      xaxis: { title: { text: wrapLabel("how well it tells high pain from low, with its 95% range (0.5 = coin toss)", 52) },
        range: [xLeft, 1.02], dtick: 0.1 },
      yaxis: { tickmode: "array", tickvals: rows.map((_, i) => yOf(i)), ticktext: tickText,
        range: [yLo, yHi], showline: false, ticks: "" },
      annotations, showlegend: false,
    });
    Plotly.react(ref.current, traces, layout, PAL.MODEBAR);
  }, [data]);  // eslint-disable-line react-hooks/exhaustive-deps

  // Purge on unmount only (keep the node across refits).
  useEffect(() => () => { if (ref.current) Plotly.purge(ref.current); }, []);

  return (
    <Card sx={{ ...CARD, width: "100%" }}>
      <MDBox p={3}>
        <MDTypography component="h3" sx={{ ...TYPE.title, ...WRAP.balance, color: PAL.ink, mb: 1 }}>
          Switching point across stimulation states
        </MDTypography>
        <PanelStaleNote stale={cached.stale} staleReasons={cached.staleReasons}
          loading={cached.loading} notKept={cached.notKept}
          onRecompute={() => recomputeSlots(participantUid, [CL.era])} />
        {loading ? (
          <MDTypography sx={{ ...TYPE.body, color: PAL.ink2 }}>
            Working out the reading within each stimulation state…
          </MDTypography>
        ) : err ? (
          <MDTypography sx={{ ...TYPE.body, color: PAL.ink2 }}>
            <span aria-hidden="true" style={{ marginRight: 6 }}>{STATE.notChecked.glyph}</span>
            {`Not available: ${err}.`}
          </MDTypography>
        ) : null}

        {data && !loading && !err && verdict ? (
          <MDTypography sx={{ ...TYPE.body, color: verdict.caution ? PAL.warnText : PAL.ink2, mb: 1, maxWidth: "68ch" }}>
            {verdict.caution ? <span aria-hidden="true" style={{ marginRight: 6 }}>{STATE.caution.glyph}</span> : null}
            {verdict.text}
          </MDTypography>
        ) : null}

        {/* Always-mounted forest plot; hidden until data arrives so the Plotly node survives refits. */}
        <div ref={ref} style={{ width: "100%", display: data && !loading && !err ? "block" : "none" }} />

        {data && !loading && !err ? (
          <MDTypography display="block" sx={{ ...TYPE.body, color: PAL.ink3, mt: 1 }}>
            {`Stimulation states: off below ${data.thresholds_mA.off_max} mA · low current up to ${data.thresholds_mA.low_max} mA · high current above. `
              + "The same boundaries as the stability section above."}
          </MDTypography>
        ) : null}
      </MDBox>
    </Card>
  );
}

export default EraRefitPanel;
