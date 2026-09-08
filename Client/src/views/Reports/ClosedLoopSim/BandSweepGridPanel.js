/**
 * Track D — browse the calibrated grid Biomarkers already built, and pick any point from it.
 *
 * WHAT THIS READS. `grid` is `report.band_sweep_grid`, computed server-side by
 * `ClosedLoopDeployment.adapter.band_sweep_grid_for_closed_loop`: the SAME stored entry the
 * Biomarkers exploration page reads (`biomarker_band_sweep`), read here as `consumer="closed_loop"`
 * rather than recomputed. Every frequency point crossed with every length of signal, for every
 * sensing contact pair, was already in that entry before Track D touched anything — this panel adds
 * no new backend field for the grid itself, only a way to browse it.
 *
 * WHY THE EXPENSIVE CHECKS ARE NOT HERE. The full three-source comparison, the receiver-operating
 * curve and the exact switching value stay exactly as expensive as they already are and run live
 * only for whichever point a user opens — clicking a cell here does not compute any of that. It
 * commits a BandCandidate through the SAME mechanism the file-upload path on this page already uses
 * (`bandCandidateStore.commitBandCandidate`), which is what makes every other panel on this page
 * (the ROC, the prescription, the evidence triangle) recompute for the newly chosen point, exactly
 * as if the user had uploaded a BandCandidate file naming it.
 *
 * TWO COLUMNS TRACK D COULD NOT BUILD, STATED HONESTLY RATHER THAN FAKED.
 *
 * (1) "Blocked by device rules." Checked directly against the 51-rule table
 * (`ClosedLoopDeployment/constraints.py`) before writing any code: of the 51 rules, only four read
 * solely a band's own centre frequency and width; every other rule needs a specific stimulation
 * current, pulse width, rate or impedance reading, none of which a (contact, band centre) grid point
 * carries. Running the full 51-rule screen on a grid point would mark it "blocked" only because
 * those fields are absent, not because anything about the band is actually forbidden -- and running
 * only the four band-only rules would never flag anything, because this grid's 22 centres already
 * sit inside the device's own permitted range by construction (decision 32). Both versions of the
 * check are meaningless at this grain, so this panel shows every cell as an equally clickable point
 * and names this limitation once, rather than drawing a badge that would look like a device-rule
 * verdict and is not one.
 *
 * (2) "Does this band mean the same thing at every stimulation setting." Real, and shown, but ONLY
 * WHEN the server has actually computed it for a given point (`cross_setting_stability` present).
 * It is a real, per-point mixed-effects model fit -- the same one `BandStabilityPanel` already runs
 * for the single committed candidate -- and running it for every point in the grid by default would
 * add real per-point cost to a page that otherwise reads a pre-computed grid instantly. Biomarkers
 * only computes it when asked (`IncludeCrossSettingStability`); until that has happened for this
 * participant, cells show a plain "not yet computed" tag instead of a fabricated answer.
 */
import { useMemo, useState } from "react";
import { Card, Chip, Tooltip } from "@mui/material";
import MDBox from "components/MDBox";
import MDTypography from "components/MDTypography";
import MDButton from "components/MDButton";

import PAL from "./palette";
import { fmtHz, fmtNum } from "./deployFormat";
import { commitBandCandidate } from "./bandCandidateStore";

const STABILITY_INK = {
  "behaves the same": PAL.pass,
  "behaves differently": PAL.fail,
  "cannot tell": PAL.warn,
  "not tested": PAL.indeterminate,
};

function channelLabel(ch) {
  return String(ch || "").replace(/_/g, " ");
}

/** One channel's rows, correlation and AUC merged by band centre so one row = one grid point. */
function mergedRows(sweepForChannel) {
  const corr = (sweepForChannel && sweepForChannel.best_correlation_rows) || [];
  const auc = (sweepForChannel && sweepForChannel.best_auc_rows) || [];
  const byCenter = new Map();
  corr.forEach((r) => {
    if (r && r.band_center_hz != null) byCenter.set(r.band_center_hz, { ...r });
  });
  auc.forEach((r) => {
    if (r == null || r.band_center_hz == null) return;
    const existing = byCenter.get(r.band_center_hz) || { band_center_hz: r.band_center_hz };
    existing.auc = r.auc;
    existing.auc_answer = r.answer;
    existing.family_wise_q_auc = r.family_wise_q_8_to_30hz;
    existing.family_wise_significant_auc = r.family_wise_significant_8_to_30hz;
    // The stability/device-rules fields are attached identically to both grids by
    // `Biomarkers.bravo_service._attach_grid_export_columns`, so either side's copy is the answer;
    // prefer whichever side actually carries it in case only one grid's row was ever built.
    if (existing.cross_setting_stability == null && r.cross_setting_stability != null) {
      existing.cross_setting_stability = r.cross_setting_stability;
    }
    if (existing.device_rules_status == null && r.device_rules_status != null) {
      existing.device_rules_status = r.device_rules_status;
    }
    byCenter.set(r.band_center_hz, existing);
  });
  return Array.from(byCenter.values()).sort((a, b) => a.band_center_hz - b.band_center_hz);
}

function FamilyWiseChip({ significant, q }) {
  if (significant == null) {
    return (
      <Tooltip title="the 22-centre family-wise correction has not been computed for this row">
        <Chip size="small" label="not assessed" sx={{ opacity: 0.6 }} />
      </Tooltip>
    );
  }
  const label = significant
    ? `clears the 22-centre correction${q != null ? ` (q=${fmtNum(q, 3)})` : ""}`
    : `does not clear the 22-centre correction${q != null ? ` (q=${fmtNum(q, 3)})` : ""}`;
  return (
    <Tooltip title="whether this band's correlation clears Benjamini-Hochberg correction across
      this contact pair's own 22 band centres, 8.5-29.5 Hz (decision 63) -- a label, never a gate:
      an uncorrected row stays fully selectable">
      <Chip
        size="small"
        label={significant ? "clears correction" : "does not clear"}
        title={label}
        sx={{
          backgroundColor: significant ? PAL.passFill : PAL.neutralFill,
          color: significant ? PAL.pass : PAL.neutral,
          border: `1px solid ${significant ? PAL.passBorder : PAL.neutralBorder}`,
          fontWeight: 600,
        }}
      />
    </Tooltip>
  );
}

function StabilityChip({ stability }) {
  if (!stability) {
    return (
      <Tooltip title="Biomarkers has not been asked to compute the cross-setting-stability answer
        for this grid yet (IncludeCrossSettingStability)">
        <Chip size="small" label="stability: not yet computed" sx={{ opacity: 0.55 }} />
      </Tooltip>
    );
  }
  const answer = stability.answer || "not tested";
  const ink = STABILITY_INK[answer] || PAL.indeterminate;
  return (
    <Tooltip title={stability.reason || answer}>
      <Chip
        size="small"
        label={`stability: ${answer}`}
        sx={{ backgroundColor: `${ink}22`, color: ink, border: `1px solid ${ink}66`, fontWeight: 600 }}
      />
    </Tooltip>
  );
}

export default function BandSweepGridPanel({ grid, participantUid, hemisphere, onCandidateChosen }) {
  const channels = useMemo(
    () => Object.keys((grid && grid.band_time_sweep) || {}).sort(),
    [grid],
  );
  const [activeChannel, setActiveChannel] = useState(null);
  const channel = activeChannel && channels.includes(activeChannel) ? activeChannel : channels[0];

  if (!grid || grid.available === false) {
    return (
      <Card sx={{ p: 2, mb: 2 }}>
        <MDTypography variant="h6" fontWeight="bold">Browse the calibrated grid</MDTypography>
        <MDTypography variant="body2" color="text" mt={1}>
          {(grid && grid.reason) || "no calibrated grid is available for this participant yet."}
          {" "}Visit the Biomarkers exploration page first, then return here.
        </MDTypography>
      </Card>
    );
  }

  const sweepForChannel = (grid.band_time_sweep || {})[channel] || {};
  const rows = mergedRows(sweepForChannel);
  const bandWidthHz = Number(sweepForChannel.band_width_hz || 5.0);

  const choose = (row) => {
    const candidate = {
      channel,
      centerHz: row.band_center_hz,
      bandWidthHz,
      sensingHemisphere: hemisphere || null,
    };
    commitBandCandidate(participantUid, {
      contact: channel,
      center_freq_hz: row.band_center_hz,
      bandwidth_hz: bandWidthHz,
      hemisphere: hemisphere || null,
      threshold_mode: "dual",
      schema_version: "bandcandidate_v1",
      label: {},
    });
    if (onCandidateChosen) onCandidateChosen(candidate);
  };

  return (
    <Card sx={{ p: 2, mb: 2 }}>
      <MDBox display="flex" alignItems="center" justifyContent="space-between" flexWrap="wrap">
        <MDTypography variant="h6" fontWeight="bold">Browse the calibrated grid</MDTypography>
        {!grid.cross_setting_stability_included && (
          <Chip
            size="small"
            label="cross-setting stability not yet computed for this grid"
            sx={{ opacity: 0.6 }}
          />
        )}
      </MDBox>
      <MDTypography variant="caption" color="text" display="block" mt={0.5} mb={1.5}>
        Every point here is fully selectable, including a row that does not clear the 22-centre
        correction. The device&apos;s own 51-rule screen cannot be evaluated from a band alone (it
        needs a specific stimulation current, pulse width, rate and impedance reading), so no
        blocked/allowed mark is shown here -- that screen still runs, live, on whichever point you
        open below.
      </MDTypography>

      <MDBox display="flex" gap={0.5} flexWrap="wrap" mb={1.5}>
        {channels.map((ch) => (
          <Chip
            key={ch}
            label={channelLabel(ch)}
            size="small"
            onClick={() => setActiveChannel(ch)}
            sx={{
              fontWeight: ch === channel ? 700 : 400,
              backgroundColor: ch === channel ? PAL.accentFill : "transparent",
              border: `1px solid ${ch === channel ? PAL.accentBorder : PAL.neutralBorder}`,
            }}
          />
        ))}
      </MDBox>

      <MDBox sx={{ overflowX: "auto" }}>
        <table style={{ borderCollapse: "collapse", width: "100%", fontSize: "0.8rem" }}>
          <thead>
            <tr style={{ textAlign: "left" }}>
              <th style={{ padding: "4px 8px" }}>Band centre</th>
              <th style={{ padding: "4px 8px" }}>Correlation r</th>
              <th style={{ padding: "4px 8px" }}>High-vs-low</th>
              <th style={{ padding: "4px 8px" }}>Family-wise (correlation)</th>
              <th style={{ padding: "4px 8px" }}>Cross-setting stability</th>
              <th style={{ padding: "4px 8px" }} />
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.band_center_hz} style={{ borderTop: `1px solid ${PAL.neutralBorder}` }}>
                <td style={{ padding: "4px 8px", fontFamily: PAL.mono }}>
                  {fmtHz(row.band_center_hz)} Hz
                </td>
                <td style={{ padding: "4px 8px", fontFamily: PAL.mono }}>
                  {fmtNum(row.pearson_r, 3)}
                </td>
                <td style={{ padding: "4px 8px", fontFamily: PAL.mono }}>
                  {fmtNum(row.auc, 3)}
                </td>
                <td style={{ padding: "4px 8px" }}>
                  <FamilyWiseChip
                    significant={row.family_wise_significant_8_to_30hz}
                    q={row.family_wise_q_8_to_30hz}
                  />
                </td>
                <td style={{ padding: "4px 8px" }}>
                  <StabilityChip stability={row.cross_setting_stability} />
                </td>
                <td style={{ padding: "4px 8px" }}>
                  <MDButton size="small" variant="outlined" color="info" onClick={() => choose(row)}>
                    Use this band
                  </MDButton>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </MDBox>
    </Card>
  );
}
