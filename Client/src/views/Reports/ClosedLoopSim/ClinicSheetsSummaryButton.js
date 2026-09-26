/**
 * Include the clinic-sheet ratings in the deployment summary, or not (the PI, 2026-09-24; drawn as a
 * plain switch since the redesign of 2026-09-26). Off by default. When on, the summary's request -- shared by the ROC
 * and the other sign-off panels -- carries `IncludeClinicSheetRatings`, so the server merges the
 * clinic and at-home sheets' scores for the chosen pain score into the ratings, exactly as the
 * heat-map grid does (decision 186). Remembered per participant in this browser only.
 */
import PAL from "./palette";

const KEY = "bravo.clSummaryClinicSheets.";

export function loadSummarySheets(participantUid) {
  try {
    return window.localStorage.getItem(KEY + String(participantUid || "unknown")) === "1";
  } catch (e) {
    return false;
  }
}

export function saveSummarySheets(participantUid, on) {
  try {
    window.localStorage.setItem(KEY + String(participantUid || "unknown"), on ? "1" : "0");
  } catch (e) {
    /* storage unavailable: the button still works for this visit */
  }
}

/**
 * A plain on/off switch in the accent colour (SPEC 2026-09-26 section 5.2: "the red outline goes";
 * red now means only that the device refuses or a value is above the safe ceiling). It stays a
 * button with `aria-pressed`, so a screen reader announces it as a toggle, and its words still say
 * which ratings the summary uses.
 */
export default function ClinicSheetsSummaryButton({ on, onToggle }) {
  const track = { width: 28, height: 16, borderRadius: 8, position: "relative", flex: "0 0 auto",
    backgroundColor: on ? PAL.accent : PAL.surface, border: `1px solid ${on ? PAL.accent : PAL.ink3}` };
  const knob = { position: "absolute", top: 2, left: on ? 14 : 2, width: 10, height: 10,
    borderRadius: "50%", backgroundColor: on ? PAL.onFill : PAL.ink3, transition: "left .15s" };
  return (
    <button type="button" onClick={() => onToggle(!on)} aria-pressed={!!on}
      style={{ display: "inline-flex", alignItems: "center", gap: 8, background: "none", border: 0,
        padding: "4px 0", cursor: "pointer", fontFamily: "inherit", fontSize: PAL.fs.body,
        color: PAL.ink, textAlign: "left" }}>
      <span aria-hidden="true" style={track}><span style={knob} /></span>
      {`Clinic-sheet ratings in the summary: ${on ? "on" : "off"}`}
    </button>
  );
}
