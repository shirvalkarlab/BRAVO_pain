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
 *
 * THE MINIMALIST REDESIGN OF 2026-09-26 (SPEC.md section 5.3, §3): the rows on the pairs the device
 * allows are sentence blocks, each opening with ✓ usable or ✕ not usable and closing with its
 * "Why not usable" fold; the other combinations stay in a folded table with sentence-case headers
 * whose two technical columns are defined once above it. Colours and sizes from the shared tokens.
 */
import { Tooltip } from "@mui/material";

import MDBox from "components/MDBox";
import MDTypography from "components/MDTypography";

import { contactSortKey } from "views/Reports/Biomarkers/contactOrder";

import { num, fmtHz, fmtMa, contactLabel, EMPTY } from "./stimFormat";
import { T, TYPE, HEAD, SMALL, MONO as MONO_BASE, SUBHEAD, WEIGHT, WRAP, HAIRLINE, Mark, SizedFold } from "./typeScale";

const MONO = { ...MONO_BASE, fontSize: TYPE.body };

// An empty cell reads as a word, never "—" (TASTE_AUDIT.md C9): an empty list is "none", a value
// the response does not carry is "not given".
const hzList = (xs) => (Array.isArray(xs) ? (xs.length ? `${xs.map((v) => Number(v)).join(", ")} Hz` : "none") : EMPTY);
const countText = (n, of) => {
  const a = num(n), b = num(of);
  return a === null || b === null || b <= 0 ? "" : `${Math.round(a)} of ${Math.round(b)}`;
};
const sideWord = (h) => (h === "Left" ? "left" : (h === "Right" ? "right" : String(h || EMPTY)));

/** A band near a folded multiple of the rate, in the PI's advisory words (never a refusal). */
function harmonicNoteFor(c) {
  const onHarmonic = Array.isArray(c.qualifying_near_stim_harmonic_hz) ? c.qualifying_near_stim_harmonic_hz : [];
  return onHarmonic.length
    ? `${hzList(onHarmonic)} carry a folded multiple of the stimulation rate at ${fmtHz(c.rate_hz)}: ${Object.values(c.stim_harmonic_notes || {}).join("; ")}. Flagged, never refused: the band is analysed either way.`
    : "";
}

/** The warning, the note and the "why not" under a row, in both layouts. */
function UnderRow({ c }) {
  const reason = c.blocking_reasons ? String(c.blocking_reasons) : "";
  if (!(c.harmonic_warning || c.harmonic_note || reason)) return null;
  return (
    <MDBox mt={0.5}>
      {c.harmonic_warning ? (
        <MDTypography variant="caption" component="div" sx={{ fontSize: TYPE.body, maxWidth: "80ch", color: T.caution }}>
          {`▲ ${c.harmonic_warning}`}
        </MDTypography>
      ) : null}
      {c.harmonic_note ? (
        <MDTypography variant="caption" component="div" sx={{ fontSize: TYPE.body, maxWidth: "80ch", color: T.ink2 }}>{c.harmonic_note}</MDTypography>
      ) : null}
      {reason ? (
        <SizedFold show="Why not usable" hide="Hide" dense mt={0.25}>
          <MDTypography variant="caption" component="div" sx={{ fontSize: TYPE.body, maxWidth: "80ch", color: T.ink2 }}>{reason}</MDTypography>
        </SizedFold>
      ) : null}
    </MDBox>
  );
}

/**
 * The usable mark: ✓ usable, ✕ not usable, with the word a screen reader hears. RED MEANS ONE
 * THING (the PI's ruling of 2026-09-26, TASTE_AUDIT.md D14): a row on a pair the device does not
 * allow with today's contacts (`refusedByDevice`) is the device refusing, red ✕; a row the device
 * allows that is not usable on the evidence (no band both falls with current and rises with pain)
 * is a statistical result, ink ✕, never red.
 */
function UsableMark({ usable, refusedByDevice = false }) {
  return (
    <Tooltip title={usable ? "usable for closed loop" : "not usable for closed loop"}>
      <span style={{ display: "inline-flex" }}>
        {usable ? <Mark state="pass" label="usable" />
          : <Mark state={refusedByDevice ? "refused" : "blocked"} label="not usable" />}
      </span>
    </Tooltip>
  );
}

/** One combination on a pair the device allows today, as a block of sentences. */
function ReadinessBlock({ c, allowed }) {
  const usable = c.deployable === true;
  const painKnown = c.n_pain_positive !== null && c.n_pain_positive !== undefined;
  const harmonicNote = harmonicNoteFor(c);
  return (
    <MDBox data-testid="readiness-row" data-allowed={allowed === null ? "unknown" : (allowed ? "true" : "false")}
      sx={{ borderTop: HAIRLINE, py: 1.5 }}>
      <MDBox display="flex" alignItems="baseline" gap={1} flexWrap="wrap">
        <UsableMark usable={usable} />
        <span style={{ ...SUBHEAD, color: T.ink }}>
          <span style={{ whiteSpace: "nowrap" }}>{contactLabel(c)}</span>
          {`, ${sideWord(c.hemisphere)} stimulation at ${fmtHz(c.rate_hz)} — ${usable ? "usable" : "not usable"}`}
        </span>
        {c.harmonic_only === true && (
          <span style={{ ...SMALL, color: T.caution, fontWeight: WEIGHT.strong, whiteSpace: "nowrap" }}>▲ warning</span>
        )}
      </MDBox>
      <MDTypography variant="caption" component="div" sx={{ fontSize: TYPE.body, color: T.ink2, mt: 0.5, maxWidth: "80ch" }}>
        {"Power falls with current (after allowing for differences between clinic visits): "}
        <span style={MONO}>{countText(c.n_era_negative_significant, c.n_bands) || EMPTY}</span>
        {" bands · rises with pain: "}
        <span style={MONO}>{painKnown ? (countText(c.n_pain_positive, c.n_bands) || EMPTY) : "not known"}</span>
        {" · both: "}
        <span style={{ ...MONO, fontWeight: num(c.n_qualifying) ? WEIGHT.strong : WEIGHT.regular, whiteSpace: "normal" }}>{hzList(c.qualifying_centers_hz)}</span>
        {harmonicNote && (
          <Tooltip title={harmonicNote}>
            <span style={{ ...SMALL, color: T.caution }}> <span aria-hidden="true">▲ </span>(carries a folded multiple of the rate)</span>
          </Tooltip>
        )}
        {"."}
      </MDTypography>
      <MDTypography variant="caption" component="div" sx={{ fontSize: TYPE.body, color: T.ink2, maxWidth: "80ch" }}>
        {"Currents tested "}
        <span style={MONO}>{`${fmtMa(c.amp_low_mA).replace(/\s*mA$/, "")}–${fmtMa(c.amp_high_mA)}`}</span>
        {"; the gap between the two measured power levels, in units of their own scatter: "}
        <span style={MONO}>{num(c.median_separation_d) === null ? EMPTY : num(c.median_separation_d).toFixed(2)}</span>
        {"."}
      </MDTypography>
      <UnderRow c={c} />
    </MDBox>
  );
}

// pair | side | rate | falls | rises | both | currents | gap | usable; "why not" under its row.
const COLUMNS = "minmax(64px, 0.8fr) 40px 56px minmax(80px, 1fr) minmax(80px, 1fr) minmax(110px, 1.4fr) minmax(90px, 1fr) minmax(64px, 0.8fr) 52px";
const HEADERS = ["Sensing pair", "Side", "Rate", "Power falls with current", "Rises with pain",
  "Bands doing both", "Currents tested", "Power gap", "Usable"];

/** The rows the device does not allow today, as a table (folded by the caller). */
function ReadinessGrid({ rows, allowed }) {
  return (
    <MDBox>
      <MDTypography variant="caption" component="div" sx={{ ...SMALL, mb: 1, maxWidth: "80ch" }}>
        Power falls with current: power goes down as current goes up, after allowing for differences
        between clinic visits. Power gap: the gap between the two measured power levels, in units of
        their own scatter.
      </MDTypography>
      <MDBox sx={{ display: "grid", gridTemplateColumns: COLUMNS, columnGap: "14px", rowGap: "8px",
        alignItems: "center" }}>
        {HEADERS.map((h) => (
          <MDTypography key={h} variant="caption" sx={{ ...HEAD, alignSelf: "end" }}>{h}</MDTypography>
        ))}
        {rows.map((c, i) => {
          const usable = c.deployable === true;
          const painKnown = c.n_pain_positive !== null && c.n_pain_positive !== undefined;
          const harmonicNote = harmonicNoteFor(c);
          const under = c.harmonic_warning || c.harmonic_note || c.blocking_reasons;
          return (
            <div key={i} data-testid="readiness-row" data-allowed={allowed === null ? "unknown" : (allowed ? "true" : "false")}
              style={{ display: "contents" }}>
              <span style={{ ...MONO, fontWeight: WEIGHT.strong }}>{contactLabel(c)}</span>
              <span style={MONO}>{c.hemisphere ? String(c.hemisphere)[0] : EMPTY}</span>
              <span style={MONO}>{fmtHz(c.rate_hz)}</span>
              <span style={MONO}>{countText(c.n_era_negative_significant, c.n_bands) || EMPTY}</span>
              <span style={MONO}>{painKnown ? (countText(c.n_pain_positive, c.n_bands) || EMPTY) : "not known"}</span>
              <MDBox sx={{ display: "flex", alignItems: "center", gap: 0.6, flexWrap: "wrap" }}>
                <span style={{ ...MONO, fontWeight: num(c.n_qualifying) ? WEIGHT.strong : WEIGHT.regular, whiteSpace: "normal" }}>{hzList(c.qualifying_centers_hz)}</span>
                {harmonicNote && (
                  <Tooltip title={harmonicNote}>
                    <span style={{ ...SMALL, color: T.caution }}><span aria-hidden="true">▲ </span>carries a folded multiple of the rate</span>
                  </Tooltip>
                )}
              </MDBox>
              <span style={MONO}>{`${fmtMa(c.amp_low_mA).replace(/\s*mA$/, "")}–${fmtMa(c.amp_high_mA)}`}</span>
              <span style={MONO}>{num(c.median_separation_d) === null ? EMPTY : num(c.median_separation_d).toFixed(2)}</span>
              <MDBox sx={{ display: "inline-flex", alignItems: "center", gap: 0.5 }}>
                <UsableMark usable={usable} refusedByDevice={allowed === false} />
                {c.harmonic_only === true && (
                  <span style={{ ...SMALL, color: T.caution, fontWeight: WEIGHT.strong, whiteSpace: "nowrap" }}><span aria-hidden="true">▲ </span>warning</span>
                )}
              </MDBox>
              {under ? <MDBox sx={{ gridColumn: "1 / -1", mt: -0.4, pl: 1 }}><UnderRow c={c} /></MDBox> : null}
            </div>
          );
        })}
      </MDBox>
    </MDBox>
  );
}

const signed = (v) => {
  const x = num(v);
  return x === null ? EMPTY : `${x >= 0 ? "+" : "−"}${Math.abs(x).toFixed(3)}`;
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
        sx={{ fontSize: TYPE.body, color: T.ink2, mt: 1 }}>
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
    <MDBox mt={1} data-testid="still-positive">
      <MDTypography variant="caption" component="div" sx={{ fontSize: TYPE.body, color: T.ink2 }}>
        {`Still positive with the current taken out, per band that rises with pain (plain correlation → with the current in force taken out; the adjusted point value only, no interval, and it moves no verdict): ${lines.length ? lines.join(" · ") : "no band rises with pain on any contact"}.`}
      </MDTypography>
    </MDBox>
  );
}

export default function SensingEvidenceTable({ closedLoop }) {
  const cl = closedLoop || {};
  if (!cl.available) {
    return (
      <MDTypography variant="caption" component="div" sx={{ fontSize: TYPE.body, color: T.ink2 }}>
        {`○ ${cl.reason || "the sensing evidence was not evaluated"}`}
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
    ? `${nDeploy === null ? "Not given how many" : Math.round(nDeploy)} of ${Math.round(nScreened)} contact-and-rate combinations usable for closed loop`
    : "no combinations screened — usability not yet assessed";
  const rule = cl.sensing_rule || null;
  // The pairs the device allows while today's contacts stimulate, one per lead (decision 217).
  // With them named, their rows stay open and the rest fold; without them, every row is open.
  const allowedSides = rule && rule.by_side ? Object.values(rule.by_side).filter((b) => b && b.allowed_channel) : [];
  const allowed = new Set(allowedSides.map((b) => String(b.allowed_channel)));
  const allowedNames = allowedSides.map((b) => b.allowed_display || b.allowed_channel);
  const split = allowed.size > 0;
  // Red only when the DEVICE allows no sensing pair at all with today's contacts (D14); "0 of 50
  // usable" on pairs it does allow is a statistical result, drawn in ink with ✕.
  const deviceAllowsNone = !!(rule && rule.by_side
    && Object.values(rule.by_side).some((b) => b && b.rule_applied) && allowed.size === 0);
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
          sx={{ fontSize: TYPE.lead, lineHeight: "24px", color: T.ink, mb: 1, maxWidth: "68ch" }}>
          {rule.sentence}
        </MDTypography>
      ) : null}
      <MDBox display="flex" alignItems="center" gap={1} flexWrap="wrap">
        {nScreened ? (cl.ready ? <Mark state="pass" label="a usable combination exists" size={TYPE.lead} />
          : <Mark state={deviceAllowsNone ? "refused" : "blocked"} label="no usable combination" size={TYPE.lead} />) : null}
        <MDTypography variant="h6" component="p" sx={{ fontSize: TYPE.lead, fontWeight: WEIGHT.strong,
          color: nScreened && !cl.ready && deviceAllowsNone ? T.refused : T.ink, m: 0, ...WRAP.balance }}>{headline}</MDTypography>
        {sel && (
          <MDTypography variant="caption" sx={{ ...MONO, fontSize: TYPE.num }}>
            {`· best ${contactLabel(sel)} at ${fmtHz(sel.rate_hz)} (${sel.hemisphere} stimulation)`}
          </MDTypography>
        )}
      </MDBox>

      {cl.harmonic_warning && cl.harmonic_warning.sentence && (
        <MDTypography variant="caption" component="div" data-testid="harmonic-screen-warning"
          sx={{ fontSize: TYPE.body, mt: 1, color: T.caution, fontWeight: WEIGHT.strong }}>
          {`▲ ${cl.harmonic_warning.sentence}`}
        </MDTypography>
      )}

      {rows.length > 0 && (
        <MDBox mt={2} data-scroll-x="" sx={{ overflowX: "auto", maxWidth: "100%" }}>
          {openRows.length > 0 ? openRows.map((c, i) => <ReadinessBlock key={i} c={c} allowed={split ? true : null} />) : (
            <MDTypography variant="caption" component="div" sx={{ fontSize: TYPE.body, color: T.ink2 }}>
              {/* The list holds only combinations with something on them, at most 30; a pair with
                  no row was still screened and is counted above (2026-09-26). */}
              {`No combination on ${allowedNames.join(" or ")} is in this list: it holds only combinations with a band that qualifies, falls with current or responds to a change in current, at most 30 of them.`}
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
        <MDTypography variant="caption" component="div" sx={{ fontSize: TYPE.body, color: T.ink2, mt: 1 }}>
          {`Rises with pain: read off the Biomarkers grid for the ${pr.score_label || pr.score || "pain"} score${pr.stored_utc ? `, built ${new Date(pr.stored_utc).toLocaleString()}` : ""}.`}
        </MDTypography>
      )}
      {pr && pr.available && (
        <StillPositiveLines still={pr.still_positive_without_current} labelFor={labelFor} />
      )}
      {pr && pr.available === false && (
        <MDTypography variant="caption" component="div" sx={{ fontSize: TYPE.body, mt: 1, color: T.caution }}>
          {`▲ Which bands rise with pain is not known: ${pr.reason || "no stored Biomarkers grid"}. Without it no combination can be called usable.`}
        </MDTypography>
      )}

      {/* The explanatory paragraphs, in one fold (the design review of 2026-09-26, S3). */}
      <SizedFold show="What “usable” requires, and why the current limit is flat" hide="Hide">
        <MDTypography variant="caption" component="div" sx={{ fontSize: TYPE.body, color: T.ink2 }}>
          {`A combination is usable when at least one band both falls with current after removing the differences between clinic visits (a significant negative slope of band power on current) and rises with pain on the Biomarkers grid (a positive correlation with the pain score whose interval lies wholly above zero), on the one sensing pair the device allows while today's contacts stimulate (the two contacts flanking them). That is the device's fixed control polarity: more current, less power, less pain. Evidence counts only from currents at or below the module's ${fmtMa(cl.amp_hard_limit_mA)} hard limit, which is not the safe ceiling for programming. One band is enough (the PI's ruling of 2026-09-17; until then half the bands had to respond).`}
        </MDTypography>
        {pr && pr.available && (
          <MDTypography variant="caption" component="div" sx={{ fontSize: TYPE.body, color: T.ink2, mt: 1 }}>
            {`The pain half: a band counts when its correlation with pain is positive and its interval lies wholly above zero (supported); the stricter selection-aware bar the grid calls "established" is reported beside it, not required. ${painSummary}`}
          </MDTypography>
        )}
        <MDTypography variant="caption" component="div" sx={{ fontSize: TYPE.body, color: T.ink2, mt: 1 }}>
          {`Closed loop can use a band inside ${(cl.adaptive_window_hz || []).map((v) => Number(v)).join("–")} Hz at a rate of at least ${fmtHz(cl.min_adaptive_rate_hz)}. Its only lever is current, so a band must move with current, which is a different question from whether it tracks pain. ${
            cl.safe_ceiling_mA_by_side
              ? `Safe ceiling, stated by the PI: L ${fmtMa(cl.safe_ceiling_mA_by_side.Left)} / R ${fmtMa(cl.safe_ceiling_mA_by_side.Right)}; evidence above the ${fmtMa(cl.amp_hard_limit_mA)} module cap is excluded.`
              : `Current limit ${fmtMa(cl.amp_hard_limit_mA)}.`} The safe ceiling is stated by the PI for each side; it does not vary with rate or pulse width.`}
        </MDTypography>
        <MDTypography variant="caption" component="div" sx={{ fontSize: TYPE.body, color: T.ink2, mt: 1 }}>
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
