/**
 * The electrode identifier check (the PI, 2026-10-06), in the Biomarkers page's bottom fold
 * ("Chance and current checks (offline)"), below the calibration panel. Feeds nothing on any page.
 *
 * The device's electrode identifier records each electrode of one lead against contact 3 of the
 * OTHER lead, stimulation off, about 20 s per run (DEVICE_percept_rc.md §3). No channel is a
 * within-lead sensing pair and each mixes both brain sides, so these runs are never matched to pain.
 *
 * Served by /api/queryElectrodeIdentifierCheck (`Biomarkers/routines/electrode_identifier.py`).
 * Every number printed is read from the payload: the device's own PSD (µVp, linear axes; log power
 * enters no plot, decision 202), its ranking at the frequency the clinician selected, its peak
 * frequency and artefact flag. The headlines are built from those numbers when the panel draws.
 *
 * The figure is drawn only once the fold is open (a Plotly graph drawn hidden measures zero wide),
 * redrawn in place with a constant `uirevision`, and purged on unmount only.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import Plotly from "plotly.js-dist";
import { Select, MenuItem, FormControl } from "@mui/material";

import MDBox from "components/MDBox";
import MDTypography from "components/MDTypography";

import { SessionController } from "database/session-control";
import { useCachedResult } from "database/useCachedResult";

import { BM, recomputeSlots } from "views/Reports/moduleCacheKeys";
import PanelStaleNote from "views/Reports/ClosedLoopSim/PanelStaleNote";
import { promptSelectSx } from "views/Reports/paper/selectStyle";
import { T, TYPE } from "assets/theme/base/tokens";
import { CATEGORICAL } from "assets/theme/base/dataColors";
import { plotlyLayout, PLOTLY_CONFIG_WITH_TOOLBAR } from "views/Reports/figureStyle";

const day = (t) => new Date(Number(t) * 1000).toISOString().slice(0, 10);
const hz = (v) => (v == null || !Number(v) ? null : `${Number(v).toFixed(2)} Hz`);
const RANKED = ["highest", "middle", "lowest"];

/** "Left rings, 2025-07-16" (+ "run unknown" when the export could not tell which run). */
export function runLabel(r) {
  return `${day(r.t)} · ${r.side} ${r.group}${r.run_unknown ? " · run unknown" : ""}`;
}

/** One line per side and group, from the device's rankings (never pooled across sides). */
export function headline(s) {
  const what = `${s.side} ${s.group}`;
  const sep = s.n_insufficient_separation
    ? `insufficient signal separation in ${s.n_insufficient_separation}` : "";
  if (!s.n_ranked) {
    return `${what}: never ranked in ${s.n_runs} runs${sep ? `; ${sep}` : ""}`;
  }
  const top = s.most_often_highest || [];
  const n = top.length ? s.highest_counts[top[0]] : 0;
  const sel = s.selected_hz && s.selected_hz.n
    ? (s.selected_hz.n > 1
      ? `, selected ${Number(s.selected_hz.min).toFixed(1)}–${Number(s.selected_hz.max).toFixed(1)} Hz`
      : `, selected ${Number(s.selected_hz.median).toFixed(1)} Hz`)
    : "";
  return `${what}: ${top.join(" and ")} ranked highest in ${n} of ${s.n_ranked} ranked run${s.n_ranked === 1 ? "" : "s"}${sel}${sep ? `; ${sep}` : ""}`;
}

/** The line above the figure: what the device ranked in the chosen run. */
export function runLine(r) {
  if (!r) return "";
  const top = r.electrodes.filter((e) => e.ranking === "highest").map((e) => e.electrode);
  const sel = hz(r.electrodes.length ? r.electrodes[0].selected_hz : null);
  if (top.length) return `${runLabel(r)}: ${top.join(", ")} highest at ${sel}`;
  if (r.electrodes.some((e) => e.ranking === "insufficient separation")) {
    return `${runLabel(r)}: insufficient signal separation${sel ? ` at ${sel}` : ""}`;
  }
  return `${runLabel(r)}: no ranking (no frequency selected)`;
}

/** The ranking table: every run the device ranked or could not separate, oldest first. */
export function rankingRows(runs) {
  return (runs || [])
    .filter((r) => r.electrodes.some((e) => RANKED.includes(e.ranking) || e.ranking === "insufficient separation"))
    .map((r) => {
      const by = (k) => r.electrodes.filter((e) => e.ranking === k).map((e) => e.electrode).join(", ");
      const insufficient = !r.electrodes.some((e) => RANKED.includes(e.ranking));
      return { key: `${r.t}-${r.side}-${r.group}`, date: day(r.t), side: r.side, group: r.group,
        unknown: r.run_unknown, selected: hz(r.electrodes[0].selected_hz) || "none",
        highest: insufficient ? "insufficient separation" : by("highest"),
        middle: insufficient ? "" : by("middle"), lowest: insufficient ? "" : by("lowest") };
    });
}

function ElectrodeIdentifierPanel({ participantUid, revealed }) {
  const plotRef = useRef(null);
  const cached = useCachedResult({
    moduleKey: BM.electrodeIdentifier,
    uid: participantUid,
    settings: {},
    enabled: !!participantUid && !!revealed,
    fetcher: () => SessionController.query("/api/queryElectrodeIdentifierCheck",
      { ParticipantId: participantUid })
      .then((response) => (response && response.data) || null),
  });
  const raw = cached.data;
  const data = raw && raw.available ? raw : null;
  const err = cached.err || (raw && !raw.available ? (raw.reason || "not available") : null);

  const withSpectra = useMemo(() => (data ? data.runs.filter((r) => r.psd === "with values") : []), [data]);
  const [pick, setPick] = useState(null);
  const chosen = withSpectra.find((r) => runLabel(r) === pick) || withSpectra[withSpectra.length - 1] || null;

  useEffect(() => {
    const gd = plotRef.current;
    if (!gd || !revealed || !chosen) return;
    const traces = chosen.electrodes.filter((e) => e.uvp && e.uvp.length).map((e, i) => ({
      x: e.freq, y: e.uvp, type: "scatter", mode: "lines",
      name: `${e.electrode} · ${e.ranking}${e.artifact ? " · artefact" : ""}`,
      line: { color: CATEGORICAL[i % CATEGORICAL.length], width: 1.6, dash: e.artifact ? "dot" : "solid" },
      hovertemplate: `${e.electrode}: %{y:.3f} µVp at %{x:.2f} Hz<extra></extra>`,
    }));
    const sel = chosen.electrodes.length ? Number(chosen.electrodes[0].selected_hz) : 0;
    const layout = plotlyLayout({
      height: 320, uirevision: "electrode-identifier", showlegend: true,
      margin: { l: 56, r: 16, t: 8, b: 44 },
      xaxis: { title: { text: "Frequency (Hz)" }, range: [0, 60] },
      yaxis: { title: { text: "Device PSD (µVp)" }, rangemode: "tozero" },
      shapes: sel > 0 ? [{ type: "line", xref: "x", yref: "paper", x0: sel, x1: sel, y0: 0, y1: 1,
        line: { color: T.ink3, width: 1, dash: "dash" } }] : [],
    });
    Plotly.react(gd, traces, layout, PLOTLY_CONFIG_WITH_TOOLBAR);
  }, [chosen, revealed]);
  useEffect(() => () => { if (plotRef.current) Plotly.purge(plotRef.current); }, []);

  const LINE = { ...TYPE.body, color: T.ink2, display: "block" };
  const HEAD = { ...TYPE.body, fontWeight: 600, color: T.ink, display: "block" };
  const TH = { ...TYPE.caption, color: T.ink3, textAlign: "left", padding: "2px 10px 2px 0", fontWeight: 600 };
  const TD = { ...TYPE.body, color: T.ink2, padding: "2px 10px 2px 0", verticalAlign: "top" };
  const table = data ? rankingRows(data.runs) : [];
  const nSpectra = withSpectra.length;
  const nRuns = data ? data.runs.filter((r) => !r.run_unknown).length : 0;

  return (
    <MDBox component="section" mt={3} pt={3} data-testid="electrode-identifier-section"
      sx={{ borderTop: `1px solid ${T.rule}` }}>
      <MDTypography component="h3" sx={{ ...TYPE.title, color: T.ink, m: 0 }}>
        Electrode identifier, stimulation off
      </MDTypography>
      <PanelStaleNote stale={cached.stale} staleReasons={cached.staleReasons}
        loading={cached.loading} notKept={cached.notKept}
        onRecompute={() => recomputeSlots(participantUid, [BM.electrodeIdentifier])} />
      {cached.loading && !data ? (
        <MDTypography variant="caption" sx={{ ...LINE, mt: 1, color: T.ink3 }}>
          Loading the electrode identifier runs…
        </MDTypography>
      ) : err ? (
        <MDTypography variant="caption" sx={{ ...LINE, mt: 1, color: T.caution }}>
          {`▲ No electrode identifier check: ${err}.`}
        </MDTypography>
      ) : data ? (
        <>
          <MDBox mt={1} data-testid="electrode-identifier-status">
            <MDTypography variant="caption" sx={LINE}>
              {`${nRuns} runs on ${data.n_days} visit days; ${nSpectra} carry the device's PSD (the export keeps `
                + "each session's latest only). Each electrode is recorded against contact 3 of the other "
                + "lead, so a channel mixes both brain sides and is never matched to pain."}
            </MDTypography>
            {Object.values(data.summary).map((s) => (
              <MDTypography key={`${s.side}-${s.group}`} variant="caption" sx={LINE}
                data-testid="electrode-identifier-headline">
                {headline(s)}
              </MDTypography>
            ))}
          </MDBox>

          {chosen ? (
            <MDBox mt={2}>
              <MDBox display="flex" alignItems="center" flexWrap="wrap" sx={{ gap: 1.5 }}>
                <MDTypography variant="caption" sx={HEAD}>Run</MDTypography>
                <FormControl size="small" sx={{ minWidth: 300 }}>
                  <Select value={runLabel(chosen)} onChange={(e) => setPick(e.target.value)}
                    sx={{ fontSize: 14, ...promptSelectSx }}>
                    {withSpectra.map((r) => (
                      <MenuItem key={runLabel(r)} value={runLabel(r)} sx={{ fontSize: 14 }}>{runLabel(r)}</MenuItem>
                    ))}
                  </Select>
                </FormControl>
              </MDBox>
              <MDTypography variant="caption" data-testid="electrode-identifier-run-line"
                sx={{ ...LINE, textAlign: "center", mt: 1 }}>
                {runLine(chosen)}
              </MDTypography>
              <MDTypography variant="caption" sx={{ ...TYPE.caption, color: T.ink3, display: "block", textAlign: "center" }}>
                {`reference ${chosen.reference} · dashed line: the frequency selected · dotted trace: artefact flagged by the device`}
              </MDTypography>
              <div ref={plotRef} style={{ width: "100%" }} />
            </MDBox>
          ) : null}

          {table.length ? (
            <MDBox mt={2} sx={{ overflowX: "auto" }}>
              <MDTypography variant="caption" sx={HEAD}>The device's ranking, every run it ranked</MDTypography>
              <table style={{ borderCollapse: "collapse", marginTop: 4 }} data-testid="electrode-identifier-table">
                <thead>
                  <tr>{["Date", "Lead", "Electrodes", "Selected", "Highest", "Middle", "Lowest"].map((h) => (
                    <th key={h} style={TH}>{h}</th>))}</tr>
                </thead>
                <tbody>
                  {table.map((r) => (
                    <tr key={r.key}>
                      <td style={TD}>{r.date}{r.unknown ? " *" : ""}</td>
                      <td style={TD}>{r.side}</td>
                      <td style={TD}>{r.group}</td>
                      <td style={TD}>{r.selected}</td>
                      <td style={{ ...TD, color: T.ink, fontWeight: 600 }}>{r.highest}</td>
                      <td style={TD}>{r.middle}</td>
                      <td style={TD}>{r.lowest}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <MDTypography variant="caption" sx={{ ...TYPE.caption, color: T.ink3, display: "block", mt: 0.5 }}>
                {"* the export could not tell which of the session's runs this was; stamped with the session start. "
                  + "The device ranks each electrode against the strongest at the selected frequency: highest at 80% or more, middle 40–80%, lowest under 40%."}
              </MDTypography>
            </MDBox>
          ) : null}
        </>
      ) : null}
    </MDBox>
  );
}

export default ElectrodeIdentifierPanel;
