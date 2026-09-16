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
 *
 * Laid out again 2026-09-12 after the PI's review: the table takes the card's full width; a
 * header never breaks inside a word; the "n of N" count sits in a cell of its own to the right of
 * its bar, never on it; the currents are one line; the separation is printed as a number under a
 * header that names its unit; rows are 13 px and tall enough that the bars do not touch.
 */
import { Tooltip } from "@mui/material";

import MDBox from "components/MDBox";
import MDTypography from "components/MDTypography";

import PAL from "views/Reports/ClosedLoopSim/palette";
import { TickGlyph, CrossGlyph } from "views/Reports/ClosedLoopSim/glyphs";
import { contactSortKey } from "views/Reports/Biomarkers/contactOrder";

import { num, fmtHz, fmtMa, contactLabel } from "./stimFormat";
import { TYPE, HEAD, SMALL, SizedFold } from "./typeScale";

const MONO = { fontFamily: PAL.mono, fontSize: TYPE.body, color: "#1A1A1A", whiteSpace: "nowrap" };

/**
 * "n of N" as a filled bar that takes its cell's width, with the 50% requirement marked; the
 * count is printed by the caller in the next cell, so no text ever sits on the bar.
 */
function CountBar({ n, of }) {
  const a = num(n), b = num(of);
  if (a === null || b === null || b <= 0) return <span style={SMALL}>—</span>;
  const frac = Math.max(0, Math.min(1, a / b));
  return (
    <svg width="100%" height={14} viewBox="0 0 100 14" preserveAspectRatio="none" role="img" aria-label={`${a} of ${b}`}>
      <rect x="0" y="1" width="100" height="12" fill="#EEEEEE" />
      <rect x="0" y="1" width={frac * 100} height="12" fill={frac >= 0.5 ? PAL.pass : PAL.neutral} />
      <line x1="50" x2="50" y1="0" y2="14" stroke="#4A4A4A" strokeWidth="1" vectorEffect="non-scaling-stroke" />
    </svg>
  );
}
const countText = (n, of) => {
  const a = num(n), b = num(of);
  return a === null || b === null || b <= 0 ? "" : `${Math.round(a)} of ${Math.round(b)}`;
};

// contact | side | rate | bar | count | bar | count | currents | separation | usable | reason
const COLUMNS = "108px 64px 76px minmax(110px, 1fr) 76px minmax(110px, 1fr) 76px 150px 120px 36px minmax(120px, 1.1fr)";
const HEADERS = ["sensing contact", "stim side", "rate", "bands responding", "", "still falling, time confound removed", "",
  "currents tested", "Separation (SD)", "", "why not"];

export default function SensingEvidenceTable({ closedLoop }) {
  const cl = closedLoop || {};
  if (!cl.available) {
    return (
      <MDTypography variant="caption" color="text" component="div" sx={{ fontSize: TYPE.body }}>
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
        {nScreened ? (cl.ready ? <TickGlyph label="a usable combination exists" size={20} /> : <CrossGlyph label="no usable combination" size={20} />) : null}
        <MDTypography variant="h6" sx={{ fontSize: TYPE.section }}>{headline}</MDTypography>
        {sel && (
          <MDTypography variant="caption" sx={{ ...MONO, fontSize: TYPE.num }}>
            {`· best ${contactLabel(sel)} at ${fmtHz(sel.rate_hz)} (${sel.hemisphere} stimulation)`}
          </MDTypography>
        )}
      </MDBox>
      <MDTypography variant="caption" component="div" sx={{ ...SMALL, fontSize: TYPE.body, mt: 0.4 }}>
        {`Adaptive mode can use a band inside ${(cl.adaptive_window_hz || []).map((v) => Number(v)).join("–")} Hz at a rate of at least ${fmtHz(cl.min_adaptive_rate_hz)}; its only lever is current, so a band must move with current, which is a different question from whether it tracks pain. ${
          cl.safe_ceiling_mA_by_side
            ? `Safe ceiling, stated by the PI: L ${fmtMa(cl.safe_ceiling_mA_by_side.Left)} / R ${fmtMa(cl.safe_ceiling_mA_by_side.Right)}; evidence above the ${fmtMa(cl.amp_hard_limit_mA)} module cap is excluded.`
            : `Current limit ${fmtMa(cl.amp_hard_limit_mA)}.`}`}
      </MDTypography>

      {rows.length > 0 && (
        <MDBox mt={1.5} sx={{ overflowX: "auto" }}>
          <MDBox sx={{ display: "grid", gridTemplateColumns: COLUMNS, columnGap: "12px", rowGap: "10px",
            alignItems: "center", minWidth: 1180 }}>
            {HEADERS.map((h, i) => (
              <MDTypography key={`h${i}`} variant="caption" sx={{ ...HEAD, alignSelf: "end",
                textTransform: h === "Separation (SD)" ? "none" : "uppercase" }}>{h}</MDTypography>
            ))}
            {rows.map((c, i) => {
              const usable = c.deployable === true;
              const reason = c.blocking_reasons ? String(c.blocking_reasons) : "";
              return [
                <span key={`${i}-a`} style={{ ...MONO, fontWeight: 600 }}>{contactLabel(c)}</span>,
                <span key={`${i}-b`} style={MONO}>{c.hemisphere ? String(c.hemisphere)[0] : "—"}</span>,
                <span key={`${i}-c`} style={MONO}>{fmtHz(c.rate_hz)}</span>,
                <MDBox key={`${i}-d`} sx={{ minHeight: 26, display: "flex", alignItems: "center" }}>
                  <CountBar n={c.n_responding} of={c.n_bands} />
                </MDBox>,
                <span key={`${i}-d2`} style={MONO}>{countText(c.n_responding, c.n_bands)}</span>,
                <MDBox key={`${i}-e`} sx={{ minHeight: 26, display: "flex", alignItems: "center" }}>
                  <CountBar n={c.n_era_negative_significant} of={c.n_bands} />
                </MDBox>,
                <span key={`${i}-e2`} style={MONO}>{countText(c.n_era_negative_significant, c.n_bands)}</span>,
                <span key={`${i}-f`} style={MONO}>{`${fmtMa(c.amp_low_mA).replace(" mA", "")}–${fmtMa(c.amp_high_mA)}`}</span>,
                <span key={`${i}-g`} style={MONO}>{num(c.median_separation_d) === null ? "—" : num(c.median_separation_d).toFixed(2)}</span>,
                <Tooltip key={`${i}-h`} title={usable ? "usable for closed loop" : "not usable for closed loop"}>
                  <span style={{ display: "inline-flex" }}>{usable ? <TickGlyph label="usable" size={18} /> : <CrossGlyph label="not usable" size={18} />}</span>
                </Tooltip>,
                <MDBox key={`${i}-i`}>
                  {reason ? (
                    <SizedFold show="Reason" hide="Hide" dense mt={0}>
                      <MDTypography variant="caption" color="text" component="div" sx={{ fontSize: TYPE.body, maxWidth: "70ch" }}>{reason}</MDTypography>
                    </SizedFold>
                  ) : <span style={SMALL}>—</span>}
                </MDBox>,
              ];
            })}
          </MDBox>
        </MDBox>
      )}

      <SizedFold show="What 'usable' requires, and why the current limit is flat" hide="Hide">
        <MDTypography variant="caption" color="text" component="div" sx={{ fontSize: TYPE.body }}>
          {`A combination is usable only if at least 50% of the scanned bands respond, the slope survives the time-confound adjustment, and the currents tested sit at or below the flat ${fmtMa(cl.amp_hard_limit_mA)} limit. That limit is PI-declared and was established by testing at 165 Hz; it does not vary with rate or pulse width. An earlier version of this panel applied an energy-matched ceiling that scaled as the square root of 55/f; that model has been withdrawn, because tolerable current at a given frequency is not governed by total delivered energy. A response measured only above the current we are willing to program was never usable evidence. Separation is the gap between the two measured power levels, in units of their own scatter (standard deviations).`}
        </MDTypography>
      </SizedFold>
    </MDBox>
  );
}
