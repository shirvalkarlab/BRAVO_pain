/**
 * Include the clinic-sheet ratings in the deployment summary, or not (the PI, 2026-09-24: "a simple
 * button with a red outline"). Off by default. When on, the summary's request -- shared by the ROC
 * and the other sign-off panels -- carries `IncludeClinicSheetRatings`, so the server merges the
 * clinic and at-home sheets' scores for the chosen pain score into the ratings, exactly as the
 * heat-map grid does (decision 186). Remembered per participant in this browser only.
 */
import MDButton from "components/MDButton";
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

export default function ClinicSheetsSummaryButton({ on, onToggle }) {
  return (
    <MDButton size="small" variant="outlined" onClick={() => onToggle(!on)} aria-pressed={!!on}
      sx={{ textTransform: "none", fontSize: 13, fontWeight: 600, color: "#1A1A1A",
        border: `2px solid ${PAL.fail}`, borderRadius: "6px", py: 0.5, px: 1.5, minHeight: 0,
        backgroundColor: on ? PAL.failFill : "transparent",
        "&:hover": { border: `2px solid ${PAL.fail}`, backgroundColor: PAL.failFill } }}>
      {`Clinic-sheet ratings in the summary: ${on ? "on" : "off"}`}
    </MDButton>
  );
}
