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
 *
 * Resized 2026-09-12 after the PI's review: cells at 13 px body, the gain at 15 px, the bar's
 * axis labels at 11 px, the footnotes at 12 px, and more room around each cell.
 */
import { Tooltip } from "@mui/material";

import MDBox from "components/MDBox";
import MDTypography from "components/MDTypography";

import PAL from "views/Reports/ClosedLoopSim/palette";
import { AmberGlyph } from "views/Reports/ClosedLoopSim/glyphs";

import { GainBar, VerdictGlyph } from "./GainBar";
import { num, fmtHz, fmtMa, fmtPts, siteName } from "./stimFormat";
import { TYPE, HEAD, SMALL, SizedFold } from "./typeScale";

const MONO = { fontFamily: PAL.mono, fontSize: TYPE.num, color: "#1A1A1A", whiteSpace: "nowrap" };
const LABEL = { fontSize: TYPE.body, color: "#5E5E5E", whiteSpace: "nowrap" };
const NOTE = { ...SMALL, whiteSpace: "nowrap" };

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
      <MDBox sx={{ display: "grid", gridTemplateColumns: `110px repeat(${sides.length}, minmax(0, 1fr))`,
        columnGap: "20px", rowGap: "16px", alignItems: "start" }}>
        <span />
        {sides.map((h) => (
          <MDTypography key={h} variant="caption" sx={HEAD}>{`${h} side current`}</MDTypography>
        ))}
        {sites.map((site) => [
          <MDTypography key={`${site}-l`} variant="button" fontWeight="medium" sx={{ fontSize: TYPE.num, pt: 1.5 }}>
            {siteName(site)}
          </MDTypography>,
          ...sides.map((h) => {
            const found = entries.find(([, a]) => a.site === site && a.hemisphere === h);
            if (!found) return <span key={`${site}-${h}`} style={{ ...SMALL, paddingTop: 12 }}>not fitted</span>;
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
                sx={{ p: 1.75, borderRadius: "8px", cursor: "pointer",
                  border: `1px solid ${active ? PAL.accentBorder : PAL.neutralBorder}`,
                  backgroundColor: active ? PAL.accentFill : "transparent" }}>
                <MDBox display="flex" alignItems="baseline" columnGap={1.2} rowGap={0.4} flexWrap="wrap">
                  <span style={LABEL}>in force</span>
                  <span style={MONO}>{`${fmtHz(inc[0])} · ${fmtMa(inc[1])}`}</span>
                  <span style={{ color: "#9A9A9A", fontSize: TYPE.num }}>→</span>
                  <span style={LABEL}>candidate</span>
                  <span style={{ ...MONO, fontWeight: 600 }}>{`${fmtHz(opt.freq_hz)} · ${fmtMa(opt.amp_mA)}`}</span>
                  {aboveCeil && (
                    <Tooltip title={`the candidate's ${fmtMa(opt.amp_mA)} is above the ${fmtMa(ceil)} a current ramp can reach without crossing currents the safety model rejects`}>
                      <span><AmberGlyph label="above the reachable safe ceiling" size={14} /></span>
                    </Tooltip>
                  )}
                </MDBox>
                <MDBox display="flex" alignItems="center" columnGap={1.5} mt={1} flexWrap="wrap">
                  <GainBar gain={r.gain} sd={r.sdDiff} halfRange={halfRange} />
                  <span style={{ ...MONO, fontSize: TYPE.gain }}>
                    {num(r.gain) === null ? "—" : `${fmtPts(r.gain)}${num(r.sdDiff) === null ? "" : ` ± ${num(r.sdDiff).toFixed(2)}`}`}
                  </span>
                </MDBox>
                <MDBox display="flex" alignItems="center" justifyContent="space-between" columnGap={1.5} mt={0.8} flexWrap="wrap">
                  <VerdictGlyph resolved={resolved} />
                  <span style={NOTE}>
                    {`${a.n_epochs_fitted ?? "—"} stretches`}
                    {ceil !== null && (
                      // "safe ceiling" is the highest current a ramp from zero reaches without
                      // crossing a cell the safety model rejects. The model's own ceiling -- the
                      // current the PI stated as not acceptable on this side, 2026-09-12 -- is
                      // in `safety_anchors` and is named here so the two are never confused.
                      <Tooltip title={(a.safety_anchors && a.safety_anchors.ceiling_mA != null)
                        ? `the safety model was told: not above ${fmtMa(a.safety_anchors.ceiling_mA)} on this side (${a.safety_anchors.provenance || "no provenance recorded"}); ${fmtMa(ceil)} is the highest current a ramp from zero reaches without crossing a cell the model rejects`
                        : `${fmtMa(ceil)} is the highest current a ramp from zero reaches without crossing a cell the safety model rejects`}>
                        <span>{` · safe ceiling ${fmtMa(ceil)}`}</span>
                      </Tooltip>
                    )}
                    {a.safe_contiguous === false ? " · safe set not contiguous" : ""}
                  </span>
                </MDBox>
              </MDBox>
            );
          }),
        ])}
      </MDBox>
      <SizedFold show="How the gain and its uncertainty are computed, and what the 3 verdicts mean" hide="Hide" mt={1.2}>
        <MDTypography variant="caption" color="text" component="div" sx={{ fontSize: TYPE.body }}>
          The objective is a pain score, so lower is better and a positive gain means the candidate
          cell is predicted better than the setting in force. An arm is marked resolved only when
          that gain exceeds 1 standard deviation of the difference itself, propagated from both
          cells&apos; posteriors as sqrt(sd_candidate² + sd_in-force²). The joint covariance between
          the two cells is not carried in this payload, so the propagated standard deviation omits
          the −2 cov term; nearby cells on a smooth kernel are positively correlated, so the omission
          overstates the uncertainty and the test is conservative: it can withhold a recommendation
          it might have supported, but it cannot manufacture one.
        </MDTypography>
        <MDTypography variant="caption" color="text" component="div" sx={{ fontSize: TYPE.body, mt: 0.8 }}>
          <strong>not resolved</strong> means the comparison was made and the two cells were not
          separated. <strong>not determinable</strong> means the comparison could not be made at
          all, because a posterior mean or standard deviation this arm needs is missing or
          degenerate; it calls for fixing the fit rather than collecting more exposure. Neither is
          drawn in the failure ink, because in neither case has a setting been shown to be worse.
        </MDTypography>
      </SizedFold>
    </MDBox>
  );
}
