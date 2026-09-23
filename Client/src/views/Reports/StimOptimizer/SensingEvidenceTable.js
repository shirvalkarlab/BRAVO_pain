/**
 * The sensing evidence behind closed-loop readiness: every sensing contact and stimulation rate
 * with anything on it, with how many bands fall with current once the time confound is removed,
 * how many rise with pain on the Biomarkers grid, WHICH bands do both (the one-band rule of
 * decision 199, 2026-09-17: one such band makes the combination usable), the currents tested,
 * the capture separation, and whether the combination is usable -- as numbers and symbols, the
 * reasons one click away. A qualifying band that sits on the stimulator's own harmonic at that
 * rate is marked, because a fall in it with current may be the stimulator and not the brain;
 * since 2026-09-21 (the PI's ruling) a usable row that rests on such bands ALONE carries a
 * warning printed in full under the row, the screen prints one sentence counting those rows,
 * and nothing about it blocks: the tick stays.
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
// The checks card this table's evidence feeds, named by its own title constant so the link
// cannot drift from the card it points to.
import { TWO_STAGE_CARD_TITLE } from "./TwoStagePlanCard";

const MONO = { fontFamily: PAL.mono, fontSize: TYPE.body, color: "#1A1A1A", whiteSpace: "nowrap" };

/**
 * "n of N" as a filled bar that takes its cell's width; the count is printed by the caller in
 * the next cell, so no text ever sits on the bar. Green from ONE band up: one is what the rule
 * needs (decision 199), so there is no half-way mark any more.
 */
function CountBar({ n, of }) {
  const a = num(n), b = num(of);
  if (a === null || b === null || b <= 0) return <span style={SMALL}>—</span>;
  const frac = Math.max(0, Math.min(1, a / b));
  return (
    <svg width="100%" height={14} viewBox="0 0 100 14" preserveAspectRatio="none" role="img" aria-label={`${a} of ${b}`}>
      <rect x="0" y="1" width="100" height="12" fill="#EEEEEE" />
      <rect x="0" y="1" width={frac * 100} height="12" fill={a >= 1 ? PAL.pass : PAL.neutral} />
    </svg>
  );
}
const hzList = (xs) => (Array.isArray(xs) && xs.length ? `${xs.map((v) => Number(v)).join(", ")} Hz` : "—");
const countText = (n, of) => {
  const a = num(n), b = num(of);
  return a === null || b === null || b <= 0 ? "" : `${Math.round(a)} of ${Math.round(b)}`;
};

// contact | side | rate | bar | count | bar | count | both (which bands) | currents | separation | usable | reason
const COLUMNS = "108px 64px 76px minmax(90px, 1fr) 76px minmax(90px, 1fr) 76px minmax(150px, 1.2fr) 150px 120px 36px minmax(120px, 1.1fr)";
const HEADERS = ["sensing contact", "stim side", "rate", "falls with current (time removed)", "", "rises with pain (Biomarkers grid)", "",
  "both: the bands that qualify", "currents tested", "Separation (SD)", "", "why not"];

const signed = (v) => {
  const x = num(v);
  return x === null ? "—" : `${x >= 0 ? "+" : "−"}${Math.abs(x).toFixed(3)}`;
};

/**
 * For every band that rises with pain on a contact: is it still positive once the stimulation
 * current in force is taken out? (Panel C item 6; the PI, 2026-09-22, decision 233 answer 2: shown
 * beside the plain answer, never re-selecting a band.) The adjusted POINT value only -- the grid
 * carries no interval on it -- read from a stored current-adjusted grid, which this page never
 * builds; when none is stored, the reason is printed instead.
 */
function StillPositiveLines({ still, labelFor }) {
  if (!still) return null;
  if (!still.available) {
    return (
      <MDTypography variant="caption" component="div" data-testid="still-positive"
        sx={{ ...SMALL, fontSize: TYPE.body, mt: 0.6 }}>
        {`Whether each band that rises with pain is still positive with the current taken out: not assessed: ${still.reason || "no current-adjusted grid is stored"}.`}
      </MDTypography>
    );
  }
  const lines = Object.entries(still.by_channel || {})
    .filter(([, rows]) => Array.isArray(rows) && rows.length)
    .map(([ch, rows]) => `${labelFor(ch)}: ${rows.map((r) => (r.answer === "not assessed"
      ? `${Number(r.center_hz)} Hz not assessed`
      : `${Number(r.center_hz)} Hz ${r.answer} (${signed(r.pearson_r)} → ${signed(r.pearson_r_adjusted)})`)).join(", ")}`);
  return (
    <MDBox mt={0.6} data-testid="still-positive">
      <MDTypography variant="caption" component="div" sx={{ ...SMALL, fontSize: TYPE.body }}>
        {`Still positive with the current taken out, per band that rises with pain (plain correlation → with the current in force taken out; the adjusted point value only, no interval, and it moves no verdict): ${lines.length ? lines.join(" · ") : "no band rises with pain on any contact"}.`}
      </MDTypography>
    </MDBox>
  );
}

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
  const pr = cl.pain_relationship || null;
  const painSummary = pr && pr.by_channel
    ? Object.entries(pr.by_channel).map(([ch, v]) => {
      // Decision 210: the count that feeds the rule is the SUPPORTED one (interval wholly above
      // zero); the stricter "established" count is shown beside it when it differs.
      const rise = v.n_supported_positive != null ? v.n_supported_positive : (v.n_established_positive || 0);
      const est = v.n_established_positive || 0;
      const estNote = rise && est !== rise ? ` (${est} of them established)` : "";
      return `${contactLabel(v, ch)}: ${rise} rise${estNote}${v.n_established_negative ? `, ${v.n_established_negative} fall` : ""}`;
    }).join(" · ")
    : "";
  const nScreened = num(cl.n_cells_screened), nDeploy = num(cl.n_cells_deployable);
  const headline = nScreened
    ? `${nDeploy === null ? "—" : Math.round(nDeploy)} of ${Math.round(nScreened)} contact-and-rate combinations usable for closed loop`
    : "no combinations screened — usability not yet assessed";
  const rule = cl.sensing_rule || null;
  const labelFor = (ch) => {
    const v = (pr && pr.by_channel && pr.by_channel[ch]) || null;
    return v ? contactLabel(v, ch) : ch;
  };
  return (
    <MDBox>
      {/* The device's sensing rule FIRST, with the count it explains (decision 217; panel C item
          5, report C §5.3). It applies to every row at once, and it used to be printed only row
          by row under "why not", so a count that read differently on an earlier visit read zero
          with no reason in sight. */}
      {rule && rule.sentence ? (
        <MDTypography variant="caption" component="div" data-testid="sensing-rule-first"
          sx={{ fontSize: TYPE.body, fontWeight: 600, color: "#1A1A1A", mb: 0.6 }}>
          {rule.sentence}
        </MDTypography>
      ) : null}
      <MDBox display="flex" alignItems="center" gap={1} flexWrap="wrap">
        {nScreened ? (cl.ready ? <TickGlyph label="a usable combination exists" size={20} /> : <CrossGlyph label="no usable combination" size={20} />) : null}
        <MDTypography variant="h6" sx={{ fontSize: TYPE.section }}>{headline}</MDTypography>
        {sel && (
          <MDTypography variant="caption" sx={{ ...MONO, fontSize: TYPE.num }}>
            {`· best ${contactLabel(sel)} at ${fmtHz(sel.rate_hz)} (${sel.hemisphere} stimulation)`}
          </MDTypography>
        )}
      </MDBox>
      {/* The two readiness cards stay two cards (panel C item 5), each pointing at the other. */}
      <MDTypography variant="caption" component="div" sx={{ ...SMALL, fontSize: TYPE.body, mt: 0.4 }}>
        {`This table is the evidence. Whether closed loop may start is decided by the four checks in the card "${TWO_STAGE_CARD_TITLE}" at the foot of this page; one of them reads the best row here.`}
      </MDTypography>
      <MDTypography variant="caption" component="div" sx={{ ...SMALL, fontSize: TYPE.body, mt: 0.4 }}>
        {`Adaptive mode can use a band inside ${(cl.adaptive_window_hz || []).map((v) => Number(v)).join("–")} Hz at a rate of at least ${fmtHz(cl.min_adaptive_rate_hz)}; its only lever is current, so a band must move with current, which is a different question from whether it tracks pain. ${
          cl.safe_ceiling_mA_by_side
            ? `Safe ceiling, stated by the PI: L ${fmtMa(cl.safe_ceiling_mA_by_side.Left)} / R ${fmtMa(cl.safe_ceiling_mA_by_side.Right)}; evidence above the ${fmtMa(cl.amp_hard_limit_mA)} module cap is excluded.`
            : `Current limit ${fmtMa(cl.amp_hard_limit_mA)}.`}`}
      </MDTypography>

      {cl.harmonic_warning && cl.harmonic_warning.sentence && (
        <MDTypography variant="caption" component="div" data-testid="harmonic-screen-warning"
          sx={{ ...SMALL, fontSize: TYPE.body, mt: 0.6, color: PAL.warnText, fontWeight: 600 }}>
          {cl.harmonic_warning.sentence}
        </MDTypography>
      )}

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
              const painKnown = c.n_pain_positive !== null && c.n_pain_positive !== undefined;
              const onHarmonic = Array.isArray(c.qualifying_near_stim_harmonic_hz) ? c.qualifying_near_stim_harmonic_hz : [];
              const harmonicNote = onHarmonic.length
                ? `${hzList(onHarmonic)} on a stimulator harmonic at ${fmtHz(c.rate_hz)}: ${Object.values(c.stim_harmonic_notes || {}).join("; ")} — a fall there with current may be the stimulator, not the brain`
                : "";
              return [
                <span key={`${i}-a`} style={{ ...MONO, fontWeight: 600 }}>{contactLabel(c)}</span>,
                <span key={`${i}-b`} style={MONO}>{c.hemisphere ? String(c.hemisphere)[0] : "—"}</span>,
                <span key={`${i}-c`} style={MONO}>{fmtHz(c.rate_hz)}</span>,
                <MDBox key={`${i}-d`} sx={{ minHeight: 26, display: "flex", alignItems: "center" }}>
                  <CountBar n={c.n_era_negative_significant} of={c.n_bands} />
                </MDBox>,
                <span key={`${i}-d2`} style={MONO}>{countText(c.n_era_negative_significant, c.n_bands)}</span>,
                <MDBox key={`${i}-e`} sx={{ minHeight: 26, display: "flex", alignItems: "center" }}>
                  {painKnown ? <CountBar n={c.n_pain_positive} of={c.n_bands} /> : <span style={SMALL}>not known</span>}
                </MDBox>,
                <span key={`${i}-e2`} style={MONO}>{painKnown ? countText(c.n_pain_positive, c.n_bands) : ""}</span>,
                <MDBox key={`${i}-q`} sx={{ minHeight: 26, display: "flex", alignItems: "center", gap: 0.6, flexWrap: "wrap" }}>
                  <span style={{ ...MONO, fontWeight: num(c.n_qualifying) ? 600 : 400, whiteSpace: "normal" }}>{hzList(c.qualifying_centers_hz)}</span>
                  {harmonicNote && (
                    <Tooltip title={harmonicNote}>
                      <span style={{ ...SMALL, color: PAL.warnText, whiteSpace: "nowrap" }}>on a stimulator harmonic</span>
                    </Tooltip>
                  )}
                </MDBox>,
                <span key={`${i}-f`} style={MONO}>{`${fmtMa(c.amp_low_mA).replace(" mA", "")}–${fmtMa(c.amp_high_mA)}`}</span>,
                <span key={`${i}-g`} style={MONO}>{num(c.median_separation_d) === null ? "—" : num(c.median_separation_d).toFixed(2)}</span>,
                <MDBox key={`${i}-h`} sx={{ display: "inline-flex", alignItems: "center", gap: 0.5 }}>
                  <Tooltip title={usable ? "usable for closed loop" : "not usable for closed loop"}>
                    <span style={{ display: "inline-flex" }}>{usable ? <TickGlyph label="usable" size={18} /> : <CrossGlyph label="not usable" size={18} />}</span>
                  </Tooltip>
                  {c.harmonic_only === true && (
                    <span style={{ ...SMALL, color: PAL.warnText, fontWeight: 600, whiteSpace: "nowrap" }}>warning</span>
                  )}
                </MDBox>,
                <MDBox key={`${i}-i`}>
                  {c.harmonic_warning ? (
                    <MDTypography variant="caption" component="div" sx={{ fontSize: TYPE.body, maxWidth: "70ch", color: PAL.warnText }}>{c.harmonic_warning}</MDTypography>
                  ) : null}
                  {c.harmonic_note ? (
                    <MDTypography variant="caption" component="div" sx={{ ...SMALL, fontSize: TYPE.body, maxWidth: "70ch" }}>{c.harmonic_note}</MDTypography>
                  ) : null}
                  {reason ? (
                    <SizedFold show="Reason" hide="Hide" dense mt={0}>
                      <MDTypography variant="caption" color="text" component="div" sx={{ fontSize: TYPE.body, maxWidth: "70ch" }}>{reason}</MDTypography>
                    </SizedFold>
                  ) : (!c.harmonic_warning && !c.harmonic_note ? <span style={SMALL}>—</span> : null)}
                </MDBox>,
              ];
            })}
          </MDBox>
        </MDBox>
      )}

      {pr && pr.available && (
        <MDTypography variant="caption" component="div" sx={{ ...SMALL, fontSize: TYPE.body, mt: 0.8 }}>
          {`Which bands rise with pain is read off the Biomarkers grid for the ${pr.score_label || pr.score || "pain"} score${pr.stored_utc ? `, built ${new Date(pr.stored_utc).toLocaleString()}` : ""}: a band counts when its correlation with pain is positive and its interval lies wholly above zero (supported); the stricter selection-aware bar the grid calls "established" is reported beside it, not required. ${painSummary}`}
        </MDTypography>
      )}
      {pr && pr.available && (
        <StillPositiveLines still={pr.still_positive_without_current} labelFor={labelFor} />
      )}
      {pr && pr.available === false && (
        <MDTypography variant="caption" component="div" sx={{ ...SMALL, fontSize: TYPE.body, mt: 0.8, color: PAL.warnText }}>
          {`Which bands rise with pain is not known: ${pr.reason || "no stored Biomarkers grid"}. Without it no combination can be called usable.`}
        </MDTypography>
      )}

      <SizedFold show="What 'usable' requires, and why the current limit is flat" hide="Hide">
        <MDTypography variant="caption" color="text" component="div" sx={{ fontSize: TYPE.body }}>
          {`A combination is usable when at least ONE band both falls with current once the time confound is removed (a significant negative slope of band power on current, with the clinic-visit blocks removed) and rises with pain on the Biomarkers grid (a positive correlation with the pain score whose interval lies wholly above zero, decision 210), on the one sensing pair the device allows while today's contacts stimulate (the two contacts flanking them, decision 217) — the device's fixed control polarity: more current, less power, less pain — and the currents tested sit at or below the flat ${fmtMa(cl.amp_hard_limit_mA)} limit. One band is enough (the PI's ruling of 2026-09-17, decision 199; until then half the bands had to respond). A qualifying band that sits within 2.5 Hz of the stimulator's own harmonics at that rate (|250 − rate|, half, a quarter and three quarters of the rate) is marked, not refused. The current limit is PI-declared and was established by testing at 165 Hz; it does not vary with rate or pulse width. Separation is the gap between the two measured power levels, in units of their own scatter (standard deviations), reported for information.`}
        </MDTypography>
      </SizedFold>
    </MDBox>
  );
}
