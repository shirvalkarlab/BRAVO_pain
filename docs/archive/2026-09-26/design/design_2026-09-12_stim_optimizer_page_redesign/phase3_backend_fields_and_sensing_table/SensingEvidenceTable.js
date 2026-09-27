/**
 * The sensing evidence behind closed-loop readiness: every sensing contact and stimulation rate
 * whose band power responded to stimulation current at all, with how many bands responded, how
 * many still fall once the time confound is removed, the currents tested, the separation, and
 * whether the combination is usable -- as numbers and symbols, the reasons one click away.
 *
 * Added 2026-09-12 (page redesign, phase 3). Replaces the "Closed-loop readiness (Adaptive
 * Therapy)" table, which printed the contact pair by its raw key ("ONE_THREE_LEFT" -- the contact
 * numbers spelled out as words), a yes/no word for usable, and a 55-word sentence in the last
 * column of 8 of its 20 rows. Reads `closed_loop` from the page's response; the contact label is
 * the server's `display_short` ("L 1⁻3⁺"), added to each row in the same phase, and the rows are
 * ordered by the project's one contact order (left before right, then by contact number).
 */
import { Tooltip } from "@mui/material";

import MDBox from "components/MDBox";
import MDTypography from "components/MDTypography";

import Fold from "views/Reports/ClosedLoopSim/Fold";
import PAL from "views/Reports/ClosedLoopSim/palette";
import { TickGlyph, CrossGlyph } from "views/Reports/ClosedLoopSim/glyphs";
import { contactSortKey } from "views/Reports/Biomarkers/contactOrder";

import { num, fmtHz, fmtMa, contactLabel } from "./stimFormat";

const HEAD = { fontSize: 10, fontWeight: 700, letterSpacing: 0.4, color: "#8A8A8A", textTransform: "uppercase" };
const MONO = { fontFamily: PAL.mono, fontSize: 11.5, color: "#1A1A1A" };
const SMALL = { fontSize: 10.5, color: "#6A6A6A" };

/** "n of N" as a small filled bar with the count beside it; the 50% line marks the requirement. */
function CountBar({ n, of, width = 72 }) {
  const a = num(n), b = num(of);
  if (a === null || b === null || b <= 0) return <span style={SMALL}>—</span>;
  const frac = Math.max(0, Math.min(1, a / b));
  return (
    <MDBox display="inline-flex" alignItems="center" gap={0.6}>
      <svg width={width} height={10} role="img" aria-label={`${a} of ${b}`}>
        <rect x="0" y="1" width={width} height="8" fill="#EEEEEE" />
        <rect x="0" y="1" width={Math.round(frac * width)} height="8" fill={frac >= 0.5 ? PAL.pass : PAL.neutral} />
        <line x1={width / 2} x2={width / 2} y1="0" y2="10" stroke="#4A4A4A" strokeWidth="1" />
      </svg>
      <span style={{ ...MONO, fontSize: 11 }}>{`${Math.round(a)} of ${Math.round(b)}`}</span>
    </MDBox>
  );
}

export default function SensingEvidenceTable({ closedLoop }) {
  const cl = closedLoop || {};
  if (!cl.available) {
    return (
      <MDTypography variant="caption" color="text" component="div">
        {cl.reason || "the sensing evidence was not evaluated"}
      </MDTypography>
    );
  }
  const rows = (Array.isArray(cl.responding_cells) ? cl.responding_cells : []).slice().sort((a, b) => {
    const ka = contactSortKey(a.channel, a), kb = contactSortKey(b.channel, b);
    return (ka[0] - kb[0]) || (ka[1] - kb[1]) || String(a.hemisphere).localeCompare(String(b.hemisphere))
      || (num(a.rate_hz) || 0) - (num(b.rate_hz) || 0);
  });
  const sel = cl.selected || null;
  const nScreened = num(cl.n_cells_screened), nDeploy = num(cl.n_cells_deployable);
  const headline = nScreened
    ? `${nDeploy === null ? "—" : Math.round(nDeploy)} of ${Math.round(nScreened)} contact-and-rate combinations usable for closed loop`
    : "no combinations screened — usability not yet assessed";
  return (
    <MDBox>
      <MDBox display="flex" alignItems="center" gap={1} flexWrap="wrap">
        {nScreened ? (cl.ready ? <TickGlyph label="a usable combination exists" size={18} /> : <CrossGlyph label="no usable combination" size={18} />) : null}
        <MDTypography variant="h6" sx={{ fontSize: 15 }}>{headline}</MDTypography>
        {sel && (
          <MDTypography variant="caption" sx={{ ...MONO, fontSize: 12 }}>
            {`· best ${contactLabel(sel)} at ${fmtHz(sel.rate_hz)} (${sel.hemisphere} stimulation)`}
          </MDTypography>
        )}
      </MDBox>
      <MDTypography variant="caption" component="div" sx={SMALL}>
        {`Adaptive mode can use a band inside ${(cl.adaptive_window_hz || []).map((v) => Number(v)).join("–")} Hz at a rate of at least ${fmtHz(cl.min_adaptive_rate_hz)}; its only lever is current, so a band must move with current, which is a different question from whether it tracks pain. Current limit ${fmtMa(cl.amp_hard_limit_mA)}.`}
      </MDTypography>

      {rows.length > 0 && (
        <MDBox mt={1} sx={{ overflowX: "auto" }}>
          <MDBox sx={{ display: "grid", gridTemplateColumns: "84px 56px 60px 150px 150px 92px 54px 22px 1fr",
            columnGap: "10px", rowGap: "3px", alignItems: "center", minWidth: 820 }}>
            {["sensing contact", "stim side", "rate", "bands responding (of 18)", "still falling after the time confound is removed", "currents tested", "separation", "", "why not"].map((h) => (
              <MDTypography key={h} variant="caption" sx={HEAD}>{h}</MDTypography>
            ))}
            {rows.map((c, i) => {
              const usable = c.deployable === true;
              const reason = c.blocking_reasons ? String(c.blocking_reasons) : "";
              return [
                <span key={`${i}-a`} style={{ ...MONO, fontWeight: 600 }}>{contactLabel(c)}</span>,
                <span key={`${i}-b`} style={MONO}>{c.hemisphere ? String(c.hemisphere)[0] : "—"}</span>,
                <span key={`${i}-c`} style={MONO}>{fmtHz(c.rate_hz)}</span>,
                <CountBar key={`${i}-d`} n={c.n_responding} of={c.n_bands} />,
                <CountBar key={`${i}-e`} n={c.n_era_negative_significant} of={c.n_bands} />,
                <span key={`${i}-f`} style={MONO}>{`${fmtMa(c.amp_low_mA).replace(" mA", "")}–${fmtMa(c.amp_high_mA)}`}</span>,
                <span key={`${i}-g`} style={MONO}>{num(c.median_separation_d) === null ? "—" : `d ${num(c.median_separation_d).toFixed(2)}`}</span>,
                <Tooltip key={`${i}-h`} title={usable ? "usable for closed loop" : "not usable for closed loop"}>
                  <span>{usable ? <TickGlyph label="usable" /> : <CrossGlyph label="not usable" />}</span>
                </Tooltip>,
                <MDBox key={`${i}-i`}>
                  {reason ? (
                    <Fold show="Reason" hide="Hide" dense mt={0}>
                      <MDTypography variant="caption" color="text" component="div" sx={{ fontSize: 10.5, maxWidth: "70ch" }}>{reason}</MDTypography>
                    </Fold>
                  ) : <span style={SMALL}>—</span>}
                </MDBox>,
              ];
            })}
          </MDBox>
        </MDBox>
      )}

      <Fold show="What 'usable' requires, and why the current limit is flat" hide="Hide">
        <MDTypography variant="caption" color="text" component="div" sx={{ fontSize: 10.5 }}>
          {`A combination is usable only if at least 50% of the scanned bands respond, the slope survives the time-confound adjustment, and the currents tested sit at or below the flat ${fmtMa(cl.amp_hard_limit_mA)} limit. That limit is PI-declared and was established by testing at 165 Hz; it does not vary with rate or pulse width. An earlier version of this panel applied an energy-matched ceiling that scaled as the square root of 55/f; that model has been withdrawn, because tolerable current at a given frequency is not governed by total delivered energy. A response measured only above the current we are willing to program was never usable evidence.`}
        </MDTypography>
      </Fold>
    </MDBox>
  );
}
