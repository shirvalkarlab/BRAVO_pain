/**
 * The 4 arms of the flat optimiser as small multiples: one cell per pain site and side, each with
 * the candidate cell against the setting in force, the gain drawn against its own uncertainty,
 * and the three-state verdict. Click a cell to bring its model surfaces up below.
 *
 * Added 2026-09-12 (page redesign, phase 4). Replaces the 7-column "Arms" table and its two
 * explanatory paragraphs (folded here). Sites are rows and sides are columns, so a reader compares
 * the two sides of one site along a row and the two sites of one side down a column, and never
 * reads the four as panels of one result (figure conventions, rule 2: the unit is the arm). The
 * shared gain axis across the 4 cells is what makes the comparison honest.
 *
 * Everything is read: `optimum`, `incumbent_xy`, `comparison` and `optimum_resolved` per arm,
 * exactly as the table read them. The verdict is the SERVED one; `resolutionOf` in index.js still
 * owns the legacy fallback and passes the state in.
 */
import { Tooltip } from "@mui/material";

import MDBox from "components/MDBox";
import MDTypography from "components/MDTypography";

import Fold from "views/Reports/ClosedLoopSim/Fold";
import PAL from "views/Reports/ClosedLoopSim/palette";
import { AmberGlyph } from "views/Reports/ClosedLoopSim/glyphs";

import { GainBar, VerdictGlyph } from "./GainBar";
import { num, fmtHz, fmtMa, fmtPts, siteName } from "./stimFormat";

const MONO = { fontFamily: PAL.mono, fontSize: 12, color: "#1A1A1A" };
const SMALL = { fontSize: 10.5, color: "#6A6A6A" };

export default function ArmGainStrip({ arms, resolutions, activeArm, onSelect }) {
  const entries = Object.entries(arms || {});
  if (!entries.length) return null;
  const sites = [...new Set(entries.map(([, a]) => a.site))];
  const sides = ["Left", "Right"].filter((h) => entries.some(([, a]) => a.hemisphere === h));
  const halfRange = Math.max(2, ...entries.map(([k]) => {
    const r = (resolutions || {})[k] || {};
    return num(r.gain) === null ? 0 : Math.ceil(Math.abs(num(r.gain)) + (num(r.sdDiff) || 0));
  }));
  return (
    <MDBox>
      <MDBox sx={{ display: "grid", gridTemplateColumns: `90px repeat(${sides.length}, minmax(0, 1fr))`,
        columnGap: "14px", rowGap: "10px", alignItems: "start" }}>
        <span />
        {sides.map((h) => (
          <MDTypography key={h} variant="caption" sx={{ fontSize: 10, fontWeight: 700, letterSpacing: 0.4, color: "#8A8A8A", textTransform: "uppercase" }}>
            {`${h} side current`}
          </MDTypography>
        ))}
        {sites.map((site) => [
          <MDTypography key={`${site}-l`} variant="button" fontWeight="medium" sx={{ fontSize: 12.5, pt: 0.5 }}>
            {siteName(site)}
          </MDTypography>,
          ...sides.map((h) => {
            const found = entries.find(([, a]) => a.site === site && a.hemisphere === h);
            if (!found) return <span key={`${site}-${h}`} style={SMALL}>not fitted</span>;
            const [key, a] = found;
            const r = (resolutions || {})[key] || {};
            const resolved = r.state === "resolved" ? true : (r.state === "unresolved" ? false : null);
            const inc = a.incumbent_xy || [null, null];
            const opt = a.optimum || {};
            const ceil = num(a.safe_contiguous_ceiling);
            const aboveCeil = num(opt.amp_mA) !== null && ceil !== null && num(opt.amp_mA) > ceil + 1e-9;
            const active = key === activeArm;
            return (
              <MDBox key={key} onClick={() => onSelect && onSelect(key)} role="button" tabIndex={0}
                onKeyDown={(e) => { if (onSelect && (e.key === "Enter" || e.key === " ")) onSelect(key); }}
                sx={{ p: 1, borderRadius: "6px", cursor: "pointer",
                  border: `1px solid ${active ? PAL.accentBorder : PAL.neutralBorder}`,
                  backgroundColor: active ? PAL.accentFill : "transparent" }}>
                <MDBox display="flex" alignItems="baseline" gap={1} flexWrap="wrap">
                  <span style={SMALL}>in force</span>
                  <span style={MONO}>{`${fmtHz(inc[0])} · ${fmtMa(inc[1])}`}</span>
                  <span style={{ color: "#9A9A9A" }}>→</span>
                  <span style={SMALL}>candidate</span>
                  <span style={{ ...MONO, fontWeight: 600 }}>{`${fmtHz(opt.freq_hz)} · ${fmtMa(opt.amp_mA)}`}</span>
                  {aboveCeil && (
                    <Tooltip title={`the candidate's ${fmtMa(opt.amp_mA)} is above the ${fmtMa(ceil)} a current ramp can reach without crossing currents the safety model rejects`}>
                      <span><AmberGlyph label="above the reachable safe ceiling" size={12} /></span>
                    </Tooltip>
                  )}
                </MDBox>
                <MDBox display="flex" alignItems="center" gap={1} mt={0.4}>
                  <GainBar gain={r.gain} sd={r.sdDiff} halfRange={halfRange} />
                  <span style={{ ...MONO, fontSize: 11.5 }}>
                    {num(r.gain) === null ? "—" : `${fmtPts(r.gain)}${num(r.sdDiff) === null ? "" : ` ± ${num(r.sdDiff).toFixed(2)}`}`}
                  </span>
                </MDBox>
                <MDBox display="flex" alignItems="center" justifyContent="space-between" mt={0.3}>
                  <VerdictGlyph resolved={resolved} />
                  <span style={SMALL}>
                    {`${a.n_epochs_fitted ?? "—"} stretches`}
                    {ceil !== null ? ` · safe ceiling ${fmtMa(ceil)}` : ""}
                    {a.safe_contiguous === false ? " · safe set not contiguous" : ""}
                  </span>
                </MDBox>
              </MDBox>
            );
          }),
        ])}
      </MDBox>
      <Fold show="How the gain and its uncertainty are computed, and what the 3 verdicts mean" hide="Hide">
        <MDTypography variant="caption" color="text" component="div" sx={{ fontSize: 10.5 }}>
          The objective is a pain score, so lower is better and a positive gain means the candidate
          cell is predicted better than the setting in force. An arm is marked resolved only when
          that gain exceeds 1 standard deviation of the difference itself, propagated from both
          cells&apos; posteriors as sqrt(sd_candidate² + sd_in-force²). The joint covariance between
          the two cells is not carried in this payload, so the propagated standard deviation omits
          the −2 cov term; nearby cells on a smooth kernel are positively correlated, so the omission
          overstates the uncertainty and the test is conservative: it can withhold a recommendation
          it might have supported, but it cannot manufacture one.
        </MDTypography>
        <MDTypography variant="caption" color="text" component="div" sx={{ fontSize: 10.5, mt: 0.5 }}>
          <strong>not resolved</strong> means the comparison was made and the two cells were not
          separated. <strong>not determinable</strong> means the comparison could not be made at
          all, because a posterior mean or standard deviation this arm needs is missing or
          degenerate; it calls for fixing the fit rather than collecting more exposure. Neither is
          drawn in the failure ink, because in neither case has a setting been shown to be worse.
        </MDTypography>
      </Fold>
    </MDBox>
  );
}
