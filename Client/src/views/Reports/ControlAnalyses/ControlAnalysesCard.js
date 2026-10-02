/**
 * Checks against chance and against the current, run offline (the "control analyses"): saved,
 * dated results of checks run offline on this participant's record (the PI, 2026-09-24), one
 * dropdown per page. Restyled 2026-09-26 for the minimalist redesign (SPEC.md, WP4): shared tokens,
 * one outlined select, the reading in body text, no literal colour or size of its own. The card draws what the server saved and nothing more; a
 * new run adds a result and keeps the old ones, and nothing here is recomputed on a page load.
 */
import React, { useContext, useEffect, useState } from "react";
import PropTypes from "prop-types";

import Card from "@mui/material/Card";
import Select from "@mui/material/Select";
import MDBox from "components/MDBox";
import { SessionController } from "database/session-control";
import { T, TYPE, SPACE, CARD, LAYOUT } from "assets/theme/base/tokens";
import { SectionRevealedContext } from "views/Reports/paper/Section";

import { FIGURES } from "./figures";

const ENDPOINT = "/api/queryControlAnalyses";
const SELECT_ID = "control-analysis-select";

/** The card's title, in the spec's words for "Control analyses" (SPEC.md section 6). */
export const CARD_TITLE = "Chance and current checks (offline)";

function stamp(snap, nRuns) {
  const when = snap.run_at ? new Date(snap.run_at) : null;
  const day = when && !Number.isNaN(when.getTime())
    ? when.toLocaleString([], { year: "numeric", month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })
    : String(snap.run_at || "");
  const span = `${snap.data_from || "a start not given"} to ${snap.data_through || "an end not given"}`;
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
      ? "Showing the run with the clinic-sheet ratings merged in, because this page's clinic-sheet switch is on."
      : "Showing the run on the home pain surveys alone; the clinic-sheet ratings enter only when this page's clinic-sheet switch is on.",
  };
}

const CAPTION = { ...TYPE.body, color: T.ink3, margin: 0 };
const PROSE = { maxWidth: LAYOUT.proseMax };

/** `plain`: drawn as a plain row of a page's Background group, with no card around it (taste audit
 * C12, 2026-09-26; the Biomarkers page). Without it the card is drawn as before. */
export default function ControlAnalysesCard({ payload, clinicSheets, plain }) {
  const analyses = (payload && payload.analyses) || [];
  const [key, setKey] = useState(analyses.length ? analyses[0].key : null);
  if (!analyses.length) return null;
  const a = analyses.find((x) => x.key === key) || analyses[0];
  const snap = a.snapshot;
  const Figure = FIGURES[a.key];
  const { lines, note } = linesFor(snap, clinicSheets);
  const Frame = plain ? PlainFrame : CardFrame;
  return (
    <Frame>
      <MDBox p={plain ? 0 : 3} data-testid="control-analyses-card" data-plain={plain ? "true" : "false"}
        sx={{ fontFamily: "inherit" }}>
        <h3 style={{ ...TYPE.title, color: T.ink, margin: 0 }}>{CARD_TITLE}</h3>
        <p style={{ ...TYPE.body, ...PROSE, color: T.ink2, margin: `${SPACE.xs}px 0 ${SPACE.sm}px` }}>
          {"Saved, dated results of checks run offline on this participant's data. This card feeds no recommendation, and nothing here is worked out again when the page loads."}
        </p>
        <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: SPACE.xs }}>
          <label htmlFor={SELECT_ID} style={{ ...TYPE.body, color: T.ink2 }}>{"Which check"}</label>
          <Select native size="small" value={a.key} onChange={(e) => setKey(e.target.value)}
            inputProps={{ id: SELECT_ID }}
            sx={{ ...TYPE.body, color: T.ink, background: T.surface, maxWidth: "100%", minWidth: 280,
              "& select": { ...TYPE.body, color: T.ink, py: 0.75 } }}>
            {analyses.map((x) => <option key={x.key} value={x.key}>{x.title}{x.snapshot ? "" : " (not run yet)"}</option>)}
          </Select>
        </div>
        <p style={{ ...TYPE.lead, ...PROSE, color: T.ink, margin: `${SPACE.sm}px 0 0` }}>{a.what}</p>
        {!snap ? (
          <p style={{ ...TYPE.body, ...PROSE, color: T.ink2, margin: `${SPACE.xs}px 0 0` }}>
            {"Not run yet for this participant. A run is started offline and saved; it then appears here with its date."}
          </p>
        ) : (
          <>
            <p style={{ ...CAPTION, marginTop: SPACE.xs }}>{stamp(snap, a.n_runs)}</p>
            {note && <p style={{ ...CAPTION, ...PROSE, marginTop: SPACE.xxs }}>{note}</p>}
            {Figure && (
              <div style={{ marginTop: SPACE.sm }}>
                <Figure result={snap.result} clinicSheets={Boolean(clinicSheets)} />
              </div>
            )}
            {lines.length > 0 && (
              <ul style={{ ...TYPE.body, ...PROSE, color: T.ink2, margin: `${SPACE.sm}px 0 0`, paddingLeft: SPACE.md }}>
                {lines.map((line) => <li key={line}>{line}</li>)}
              </ul>
            )}
          </>
        )}
        {(a.literature || []).length > 0 && (
          <div style={{ marginTop: SPACE.sm }}>
            <p style={CAPTION}>{"Background reading"}</p>
            {(a.literature || []).map((l) => (
              <div key={l.url} style={{ ...TYPE.body }}>
                <a href={l.url} target="_blank" rel="noopener noreferrer" style={{ color: T.accent }}>{l.label}</a>
              </div>
            ))}
          </div>
        )}
      </MDBox>
    </Frame>
  );
}

// eslint-disable-next-line react/prop-types
function CardFrame({ children }) { return <Card sx={{ ...CARD }}>{children}</Card>; }
// eslint-disable-next-line react/prop-types
function PlainFrame({ children }) { return <div data-paper="background-row">{children}</div>; }

ControlAnalysesCard.propTypes = { payload: PropTypes.shape({ analyses: PropTypes.array }), clinicSheets: PropTypes.bool, plain: PropTypes.bool };
ControlAnalysesCard.defaultProps = { payload: null, clinicSheets: false, plain: false };

/** Fetches the page's saved control analyses once per participant and draws the card; a failed
 * request says so in one line rather than hiding the section.
 *
 * ASKED FOR WHEN ITS FOLD IS FIRST OPENED (speed-up item C8, 2026-10-02). Both pages hold this
 * section in a closed fold, and its request was sent on page load, beside the page's own heavy
 * requests, for a card nobody had opened. It now reads whether the enclosing fold has ever been
 * opened (`SectionRevealedContext`, which the page sets around it) and asks only from then on.
 * Outside any fold the answer is "yes", so it loads at once as before. While the request is out
 * it says so in one line, so an opened fold is never blank. */
export function ControlAnalysesSection({ participantUid, page, clinicSheets, plain }) {
  const revealed = useContext(SectionRevealedContext);
  const [state, setState] = useState({ payload: null, err: null, answered: false });
  useEffect(() => {
    let live = true;
    if (!participantUid || !revealed) return undefined;
    Promise.resolve(SessionController.query(ENDPOINT, { ParticipantId: participantUid, Page: page }))
      .then((res) => { if (live) setState({ payload: res && res.data, err: null, answered: true }); })
      .catch((e) => { if (live) setState({ payload: null, err: String((e && e.message) || e), answered: true }); });
    return () => { live = false; };
  }, [participantUid, page, revealed]);
  if (state.err) {
    return (
      <p style={{ ...TYPE.body, color: T.ink2, margin: 0, padding: `0 ${SPACE.xs}px` }}>
        {`The saved checks could not be read: ${state.err}`}
      </p>
    );
  }
  if (!state.answered) {
    return revealed && participantUid ? (
      <p style={{ ...TYPE.body, color: T.ink2, margin: 0, padding: `0 ${SPACE.xs}px` }}>
        {"Reading the saved checks…"}
      </p>
    ) : null;
  }
  return <ControlAnalysesCard payload={state.payload} clinicSheets={clinicSheets} plain={plain} />;
}

ControlAnalysesSection.propTypes = { participantUid: PropTypes.string, page: PropTypes.string.isRequired, clinicSheets: PropTypes.bool, plain: PropTypes.bool };
ControlAnalysesSection.defaultProps = { participantUid: null, clinicSheets: false, plain: false };
