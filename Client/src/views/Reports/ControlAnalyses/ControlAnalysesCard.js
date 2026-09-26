/**
 * Control analyses: saved, dated results of checks run offline on this participant's record (the
 * PI, 2026-09-24), one dropdown per page. The card draws what the server saved and nothing more; a
 * new run adds a result and keeps the old ones, and nothing here is recomputed on a page load.
 */
import React, { useEffect, useState } from "react";
import PropTypes from "prop-types";

import Card from "@mui/material/Card";
import MDBox from "components/MDBox";
import MDTypography from "components/MDTypography";
import { SessionController } from "database/session-control";

import { FIGURES } from "./figures";

const ENDPOINT = "/api/queryControlAnalyses";
const SUB = "#5E5E5E";

function stamp(snap, nRuns) {
  const when = snap.run_at ? new Date(snap.run_at) : null;
  const day = when && !Number.isNaN(when.getTime())
    ? when.toLocaleString([], { year: "numeric", month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })
    : String(snap.run_at || "");
  const span = `${snap.data_from || "—"} to ${snap.data_through || "—"}`;
  return `Run ${day} on data ${span} · ${nRuns} run${nRuns === 1 ? "" : "s"} kept`;
}

/** A run saved for both positions of the page's clinic-sheet switch (the band detector, the PI's
 * ruling 5a of 2026-09-25) carries `reading_by_sheets_switch`; the card then shows ONLY the position
 * the page's switch is in, and says which. Every other run reads as before. */
function linesFor(snap, clinicSheets) {
  const bySwitch = snap && snap.result && snap.result.reading_by_sheets_switch;
  if (!bySwitch) return { lines: (snap && snap.reading) || [], note: null };
  const pos = clinicSheets ? "on" : "off";
  return {
    lines: bySwitch[pos] || [],
    note: clinicSheets
      ? "Showing the run with the clinic-sheet ratings merged in, because the page's clinic-sheet switch is on."
      : "Showing the run on REDCap ratings only; the clinic-sheet ratings enter only when the page's clinic-sheet switch is on.",
  };
}

export default function ControlAnalysesCard({ payload, clinicSheets }) {
  const analyses = (payload && payload.analyses) || [];
  const [key, setKey] = useState(analyses.length ? analyses[0].key : null);
  if (!analyses.length) return null;
  const a = analyses.find((x) => x.key === key) || analyses[0];
  const snap = a.snapshot;
  const Figure = FIGURES[a.key];
  const { lines, note } = linesFor(snap, clinicSheets);
  return (
    <Card>
      <MDBox p={2} data-testid="control-analyses-card">
        <MDTypography variant="h6" sx={{ fontSize: 17, mb: 0.25 }}>{"Control analyses"}</MDTypography>
        <MDTypography variant="caption" component="div" sx={{ fontSize: 12.5, color: SUB, mb: 1 }}>
          {"Saved, dated results of checks run offline on this participant's record. This card feeds no recommendation, and nothing here is recomputed when the page loads."}
        </MDTypography>
        <label htmlFor="control-analysis-select" style={{ fontSize: 13, color: SUB, marginRight: 8 }}>{"Control analysis"}</label>
        <select id="control-analysis-select" value={a.key} onChange={(e) => setKey(e.target.value)}
          style={{ fontSize: 14, padding: "4px 8px", maxWidth: "100%" }}>
          {analyses.map((x) => <option key={x.key} value={x.key}>{x.title}{x.snapshot ? "" : " (not run yet)"}</option>)}
        </select>
        <MDTypography variant="caption" component="div" sx={{ fontSize: 13, color: "#1A1A1A", mt: 1 }}>{a.what}</MDTypography>
        {!snap ? (
          <MDTypography variant="caption" component="div" sx={{ fontSize: 13, color: SUB, mt: 1 }}>
            {"Not run yet for this participant. A run is started offline and saved; it then appears here with its date."}
          </MDTypography>
        ) : (
          <>
            <MDTypography variant="caption" component="div" sx={{ fontSize: 12.5, color: SUB, mt: 0.75 }}>{stamp(snap, a.n_runs)}</MDTypography>
            {note && (
              <MDTypography variant="caption" component="div" sx={{ fontSize: 12.5, color: SUB, mt: 0.5 }}>{note}</MDTypography>
            )}
            {Figure && <MDBox mt={1}><Figure result={snap.result} clinicSheets={Boolean(clinicSheets)} /></MDBox>}
            <MDBox component="ul" sx={{ pl: 2.5, mt: 1, mb: 0 }}>
              {lines.map((line) => (
                <MDTypography key={line} component="li" variant="caption" display="list-item" sx={{ fontSize: 13, color: "#1A1A1A" }}>{line}</MDTypography>
              ))}
            </MDBox>
          </>
        )}
        <MDBox mt={1}>
          {(a.literature || []).map((l) => (
            <MDTypography key={l.url} variant="caption" component="div" sx={{ fontSize: 12.5 }}>
              <a href={l.url} target="_blank" rel="noopener noreferrer">{l.label}</a>
            </MDTypography>
          ))}
        </MDBox>
      </MDBox>
    </Card>
  );
}

ControlAnalysesCard.propTypes = { payload: PropTypes.shape({ analyses: PropTypes.array }), clinicSheets: PropTypes.bool };
ControlAnalysesCard.defaultProps = { payload: null, clinicSheets: false };

/** Fetches the page's saved control analyses once per participant and draws the card; a failed
 * request says so in one line rather than hiding the section. */
export function ControlAnalysesSection({ participantUid, page, clinicSheets }) {
  const [state, setState] = useState({ payload: null, err: null });
  useEffect(() => {
    let live = true;
    if (!participantUid) return undefined;
    Promise.resolve(SessionController.query(ENDPOINT, { ParticipantId: participantUid, Page: page }))
      .then((res) => { if (live) setState({ payload: res && res.data, err: null }); })
      .catch((e) => { if (live) setState({ payload: null, err: String((e && e.message) || e) }); });
    return () => { live = false; };
  }, [participantUid, page]);
  if (state.err) {
    return (
      <MDTypography variant="caption" component="div" sx={{ fontSize: 12.5, color: SUB, px: 1 }}>
        {`Control analyses could not be read: ${state.err}`}
      </MDTypography>
    );
  }
  return <ControlAnalysesCard payload={state.payload} clinicSheets={clinicSheets} />;
}

ControlAnalysesSection.propTypes = { participantUid: PropTypes.string, page: PropTypes.string.isRequired, clinicSheets: PropTypes.bool };
ControlAnalysesSection.defaultProps = { participantUid: null, clinicSheets: false };
