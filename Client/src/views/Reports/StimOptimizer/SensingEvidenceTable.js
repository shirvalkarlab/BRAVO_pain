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
 *
 * CUT TO THE ALLOWED PAIRS, 2026-09-26 (the design review, S3; the PI: "yes to all six"). While
 * today's contacts stimulate, the device senses on one pair per lead (decision 217), so only the
 * rows on those pairs (`sensing_rule.by_side[side].allowed_channel`) can ever be usable; they stay
 * open and every other row folds under "Show the N other combinations". A response without the rule
 * shows every row, as before. The two count bars went (each repeated the number printed beside it),
 * "why not" sits under its row instead of in a twelfth column, and the grid has no fixed minimum
 * width (it was 1,180 px, which scrolled sideways on a laptop). The pointer to the checks card is
 * gone; the explanatory paragraphs sit in one fold. A band near a harmonic is said in the PI's
 * advisory words, "carries a folded multiple of the stimulation rate", and the rule is decision
 * 277's: every whole multiple of the rate, folded by the device's 250 Hz sampling.
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

const hzList = (xs) => (Array.isArray(xs) && xs.length ? `${xs.map((v) => Number(v)).join(", ")} Hz` : "—");
const countText = (n, of) => {
  const a = num(n), b = num(of);
  return a === null || b === null || b <= 0 ? "" : `${Math.round(a)} of ${Math.round(b)}`;
};

// pair | side | rate | falls (count) | rises (count) | both (which bands) | currents | gap | usable;
// "why not" is a full-width line UNDER its row. About 750 px at the columns' minimums.
const COLUMNS = "minmax(64px, 0.8fr) 40px 56px minmax(80px, 1fr) minmax(80px, 1fr) minmax(110px, 1.4fr) minmax(90px, 1fr) minmax(64px, 0.8fr) 52px";
const HEADERS = ["sensing pair", "stim side", "rate", "falls with current (clinic-visit differences removed)",
  "rises with pain (Biomarkers grid)", "both: the bands that qualify", "currents tested",
  "power gap (scatter units)", "usable"];

/** The rows of one grid (the allowed pairs, or the folded rest), with its own header row. */
function ReadinessGrid({ rows, allowed }) {
  return (
    <MDBox sx={{ display: "grid", gridTemplateColumns: COLUMNS, columnGap: "14px", rowGap: "8px",
      alignItems: "center" }}>
      {HEADERS.map((h) => (
        <MDTypography key={h} variant="caption" sx={{ ...HEAD, alignSelf: "end" }}>{h}</MDTypography>
      ))}
      {rows.map((c, i) => {
        const usable = c.deployable === true;
        const reason = c.blocking_reasons ? String(c.blocking_reasons) : "";
        const painKnown = c.n_pain_positive !== null && c.n_pain_positive !== undefined;
        const onHarmonic = Array.isArray(c.qualifying_near_stim_harmonic_hz) ? c.qualifying_near_stim_harmonic_hz : [];
        const harmonicNote = onHarmonic.length
          ? `${hzList(onHarmonic)} carry a folded multiple of the stimulation rate at ${fmtHz(c.rate_hz)}: ${Object.values(c.stim_harmonic_notes || {}).join("; ")}. Flagged, never refused: the band is analysed either way.`
          : "";
        const under = c.harmonic_warning || c.harmonic_note || reason;
        return (
          <div key={i} data-testid="readiness-row" data-allowed={allowed === null ? "unknown" : (allowed ? "true" : "false")}
            style={{ display: "contents" }}>
            <span style={{ ...MONO, fontWeight: 600 }}>{contactLabel(c)}</span>
            <span style={MONO}>{c.hemisphere ? String(c.hemisphere)[0] : "—"}</span>
            <span style={MONO}>{fmtHz(c.rate_hz)}</span>
            <span style={MONO}>{countText(c.n_era_negative_significant, c.n_bands) || "—"}</span>
            <span style={MONO}>{painKnown ? (countText(c.n_pain_positive, c.n_bands) || "—") : "not known"}</span>
            <MDBox sx={{ display: "flex", alignItems: "center", gap: 0.6, flexWrap: "wrap" }}>
              <span style={{ ...MONO, fontWeight: num(c.n_qualifying) ? 600 : 400, whiteSpace: "normal" }}>{hzList(c.qualifying_centers_hz)}</span>
              {harmonicNote && (
                <Tooltip title={harmonicNote}>
                  <span style={{ ...SMALL, color: PAL.warnText }}>carries a folded multiple of the rate</span>
                </Tooltip>
              )}
            </MDBox>
            <span style={MONO}>{`${fmtMa(c.amp_low_mA).replace(/\s*mA$/, "")}–${fmtMa(c.amp_high_mA)}`}</span>
            <span style={MONO}>{num(c.median_separation_d) === null ? "—" : num(c.median_separation_d).toFixed(2)}</span>
            <MDBox sx={{ display: "inline-flex", alignItems: "center", gap: 0.5 }}>
              <Tooltip title={usable ? "usable for closed loop" : "not usable for closed loop"}>
                <span style={{ display: "inline-flex" }}>{usable ? <TickGlyph label="usable" size={18} /> : <CrossGlyph label="not usable" size={18} />}</span>
              </Tooltip>
              {c.harmonic_only === true && (
                <span style={{ ...SMALL, color: PAL.warnText, fontWeight: 600, whiteSpace: "nowrap" }}>warning</span>
              )}
            </MDBox>
            {/* why not, under its row */}
            {under ? (
              <MDBox sx={{ gridColumn: "1 / -1", mt: -0.4, pl: 1 }}>
                {c.harmonic_warning ? (
                  <MDTypography variant="caption" component="div" sx={{ fontSize: TYPE.body, maxWidth: "80ch", color: PAL.warnText }}>{c.harmonic_warning}</MDTypography>
                ) : null}
                {c.harmonic_note ? (
                  <MDTypography variant="caption" component="div" sx={{ ...SMALL, fontSize: TYPE.body, maxWidth: "80ch" }}>{c.harmonic_note}</MDTypography>
                ) : null}
                {reason ? (
                  <SizedFold show="Why not usable" hide="Hide" dense mt={0}>
                    <MDTypography variant="caption" color="text" component="div" sx={{ fontSize: TYPE.body, maxWidth: "80ch" }}>{reason}</MDTypography>
                  </SizedFold>
                ) : null}
              </MDBox>
            ) : null}
          </div>
        );
      })}
    </MDBox>
  );
}

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
  // The pairs the device allows while today's contacts stimulate, one per lead (decision 217).
  // With them named, their rows stay open and the rest fold; without them, every row is open.
  const allowedSides = rule && rule.by_side ? Object.values(rule.by_side).filter((b) => b && b.allowed_channel) : [];
  const allowed = new Set(allowedSides.map((b) => String(b.allowed_channel)));
  const allowedNames = allowedSides.map((b) => b.allowed_display || b.allowed_channel);
  const split = allowed.size > 0;
  const openRows = split ? rows.filter((c) => allowed.has(String(c.channel))) : rows;
  const foldedRows = split ? rows.filter((c) => !allowed.has(String(c.channel))) : [];
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

      {cl.harmonic_warning && cl.harmonic_warning.sentence && (
        <MDTypography variant="caption" component="div" data-testid="harmonic-screen-warning"
          sx={{ ...SMALL, fontSize: TYPE.body, mt: 0.6, color: PAL.warnText, fontWeight: 600 }}>
          {cl.harmonic_warning.sentence}
        </MDTypography>
      )}

      {rows.length > 0 && (
        <MDBox mt={1.5} sx={{ overflowX: "auto" }}>
          {openRows.length > 0 ? <ReadinessGrid rows={openRows} allowed={split ? true : null} /> : (
            <MDTypography variant="caption" component="div" sx={{ fontSize: TYPE.body }}>
              {`Nothing was screened on ${allowedNames.join(" or ")}.`}
            </MDTypography>
          )}
          {foldedRows.length > 0 && (
            <SizedFold show={`Show the ${foldedRows.length} other combination${foldedRows.length === 1 ? "" : "s"}, on pairs the device does not allow with today's contacts`}
              hide="Hide the other combinations">
              <ReadinessGrid rows={foldedRows} allowed={false} />
            </SizedFold>
          )}
        </MDBox>
      )}

      {pr && pr.available && (
        <MDTypography variant="caption" component="div" sx={{ ...SMALL, fontSize: TYPE.body, mt: 0.8 }}>
          {`Rises with pain: read off the Biomarkers grid for the ${pr.score_label || pr.score || "pain"} score${pr.stored_utc ? `, built ${new Date(pr.stored_utc).toLocaleString()}` : ""}.`}
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

      {/* The explanatory paragraphs, in one fold (the design review of 2026-09-26, S3). */}
      <SizedFold show="What “usable” requires, and why the current limit is flat" hide="Hide">
        <MDTypography variant="caption" color="text" component="div" sx={{ fontSize: TYPE.body }}>
          {`A combination is usable when at least one band both falls with current after removing the differences between clinic visits (a significant negative slope of band power on current) and rises with pain on the Biomarkers grid (a positive correlation with the pain score whose interval lies wholly above zero), on the one sensing pair the device allows while today's contacts stimulate (the two contacts flanking them). That is the device's fixed control polarity: more current, less power, less pain. Evidence counts only from currents at or below the module's ${fmtMa(cl.amp_hard_limit_mA)} hard limit, which is not the safe ceiling for programming. One band is enough (the PI's ruling of 2026-09-17; until then half the bands had to respond).`}
        </MDTypography>
        {pr && pr.available && (
          <MDTypography variant="caption" color="text" component="div" sx={{ fontSize: TYPE.body, mt: 0.6 }}>
            {`The pain half: a band counts when its correlation with pain is positive and its interval lies wholly above zero (supported); the stricter selection-aware bar the grid calls "established" is reported beside it, not required. ${painSummary}`}
          </MDTypography>
        )}
        <MDTypography variant="caption" color="text" component="div" sx={{ fontSize: TYPE.body, mt: 0.6 }}>
          {`Closed loop can use a band inside ${(cl.adaptive_window_hz || []).map((v) => Number(v)).join("–")} Hz at a rate of at least ${fmtHz(cl.min_adaptive_rate_hz)}. Its only lever is current, so a band must move with current, which is a different question from whether it tracks pain. ${
            cl.safe_ceiling_mA_by_side
              ? `Safe ceiling, stated by the PI: L ${fmtMa(cl.safe_ceiling_mA_by_side.Left)} / R ${fmtMa(cl.safe_ceiling_mA_by_side.Right)}; evidence above the ${fmtMa(cl.amp_hard_limit_mA)} module cap is excluded.`
              : `Current limit ${fmtMa(cl.amp_hard_limit_mA)}.`} The safe ceiling is stated by the PI for each side; it does not vary with rate or pulse width.`}
        </MDTypography>
        <MDTypography variant="caption" color="text" component="div" sx={{ fontSize: TYPE.body, mt: 0.6 }}>
          A qualifying band within 2.5 Hz of where the stimulator shows up
          carries a folded multiple of the stimulation rate: every whole multiple of the rate, folded back by the device&apos;s
          250 Hz sampling (half the rate included). Such a band is flagged, never refused, and it is
          analysed either way. The power gap is the gap between the two measured power levels, in
          units of their own scatter (standard deviations), reported for information.
        </MDTypography>
      </SizedFold>
    </MDBox>
  );
}
