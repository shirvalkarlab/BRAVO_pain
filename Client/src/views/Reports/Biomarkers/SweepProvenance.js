import MDBox from "components/MDBox";
import MDTypography from "components/MDTypography";
import { TYPE, T } from "assets/theme/base/tokens";
import Fold from "./Fold";

const fmt = (value, digits = 2) => value == null || !Number.isFinite(Number(value))
  ? "not reported" : Number(value).toFixed(digits);

/** Explain the backend's selection policy without changing the displayed grid's source. */
export function bandSelectionWords(sweep) {
  const chronic = sweep && sweep.chronic_band_choice;
  if (chronic && chronic.status === "read_failed") {
    return "The chronic recordings could not be read completely. Band selection is unavailable; descriptive heat maps do not establish a usable band.";
  }
  if (chronic || ((sweep && sweep.best_correlation_rows) || []).some((r) => r.choice_source)) {
    return "Band selection uses home chronic-log correlation where it covers the band; otherwise TD-only correlation. AUC remains TD-only. PSD-only and mixed results are descriptive.";
  }
  return "This saved result does not report the chronic-log selection policy. Recompute to check the current policy. PSD-only and mixed results are descriptive.";
}

export function gridSourceWords(sweep) {
  const source = sweep && (sweep.choosing_grid || sweep.grid_source);
  if (source === "none") return sweep.choosing_grid_reason || "No grid is available for band selection.";
  if (source === "td") return `TD-only grid (time-domain recordings). ${bandSelectionWords(sweep)}`;
  if (source === "psd") return `PSD-only grid (device PSD snapshots). Descriptive only; cannot select a band. ${bandSelectionWords(sweep)}`;
  if (source === "td_psd_where_no_td") return `Mixed grid: TD recordings, with PSD snapshots where no TD is available. ${bandSelectionWords(sweep)}`;
  return "Grid source not reported in this saved result; recompute to verify its recording source.";
}

/** These are per-band checks, not a claim that current was measured on each retained tile. */
export function CurrentScopeNotes({ sweep }) {
  const checks = ((sweep && sweep.best_correlation_rows) || []).filter((row) => row.current_removed_check);
  if (!checks.length) return null;
  return <MDBox data-testid="current-scope-notes" mt={1}>
    <MDTypography sx={{ ...TYPE.body, color: T.ink2 }}>
      Current-adjusted checks are descriptive. Current is an approximation from candidate recording pieces, not necessarily the pieces retained for each band and window.
    </MDTypography>
    <Fold show="Current-adjustment details by band">
      {checks.map((row, i) => {
        const check = row.current_removed_check;
        return <MDTypography component="p" key={`${row.band_center_hz}-${i}`} sx={{ ...TYPE.body, color: T.ink2 }}>
          {`${fmt(row.band_center_hz, 1)} Hz: ${check.what || "Adjustment details not reported."} `}
          {`Current scope: ${check.current_scope || "not reported in this result"}. `}
          {check.n_reports_without_current != null
            ? `${check.n_reports_without_current} otherwise eligible reports lack current; adjustment uses the known-current subset.` : "Missing-current count not reported."}
        </MDTypography>;
      })}
    </Fold>
  </MDBox>;
}

/** Display the returned source-specific best rows without querying the mixed-grid cell endpoint. */
export function SourceGridDetails({ sweep }) {
  const sources = sweep && sweep.by_source_grid;
  if (!sources) return null;
  return <Fold show="TD-only and PSD-only results">
    <MDTypography sx={{ ...TYPE.body, color: T.ink2 }}>
      Each source has its own reports and analysis. These tables show the best window for each band and statistic, so correlation and AUC can use different windows and report counts. Best-window values are optimistic by selection. PSD-only results cannot select a band.
    </MDTypography>
    {["td", "psd"].map((source) => {
      const grid = sources[source];
      return <MDBox key={source} mt={2} data-testid={`source-grid-${source}`}>
        <MDTypography component="h3" sx={{ ...TYPE.body, fontWeight: 600 }}>{source.toUpperCase()}-only results</MDTypography>
        {!grid ? <MDTypography sx={TYPE.body}>This source grid was not returned.</MDTypography> : <>
          {["correlation", "auc"].map((kind) => {
            const rows = grid[kind === "auc" ? "best_auc_rows" : "best_correlation_rows"] || [];
            return <MDBox key={kind} sx={{ overflowX: "auto", mt: 1 }}>
              {!rows.length ? <MDTypography sx={TYPE.body}>{`${kind === "auc" ? "AUC" : "Correlation"}: ${grid.reason || "no source-specific result available"}.`}</MDTypography>
                : <table style={{ ...TYPE.body, borderCollapse: "collapse", width: "100%" }}>
                  <caption style={{ textAlign: "left" }}>{kind === "auc" ? "AUC (0.5 = chance)" : "Correlation with pain"}</caption>
                  <thead><tr>{["Band center (Hz)", kind === "auc" ? "AUC" : "r", "Window (s)", "Pain reports"].map((label) => <th key={label} scope="col" style={{ textAlign: "left", padding: 4 }}>{label}</th>)}</tr></thead>
                  <tbody>{rows.map((row, i) => <tr key={`${row.band_center_hz}-${i}`}>
                    <td>{fmt(row.band_center_hz, 1)}</td><td>{fmt(row[kind === "auc" ? "auc" : "pearson_r"])}</td>
                    <td>{fmt(row.integration_seconds_delivered, 0)}</td><td>{fmt(row.n_pain_reports, 0)}</td>
                  </tr>)}</tbody>
                </table>}
            </MDBox>;
          })}
          <CurrentScopeNotes sweep={grid}/>
        </>}
      </MDBox>;
    })}
  </Fold>;
}
