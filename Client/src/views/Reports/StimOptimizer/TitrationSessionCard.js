/**
 * "Titration session to run next": the card on the Stim Optimizer page, directly under "What to
 * test at the next visit", that turns open item 30 (the titration session that would let a
 * response peak be estimated) and decision 144 (the 20 s post-ramp margin, shipped OFF because on
 * 11-13 points it flips a verdict) into one sheet a clinician reads at the visit. The PI's decision
 * of 2026-09-12 evening: "make #4 a feature of next stim opt recommendation combined with 30".
 *
 * Everything here is READ from the `titration_plan` block the server returns
 * (`StimOptimizer/titration_plan.py` through `bravo_service.titration_plan_block`); nothing is
 * derived on the page. Two columns, Left | Right; numbers where numbers exist (rate, pulse width,
 * ceiling, the ladder as "0 → 0.5 → … → 5.0 → … → 0 mA", the hold, the contact in Medtronic
 * notation); the 22 band centres as a strip, all of them analysed, clear ones in ink and the ones
 * within 2.5 Hz of a harmonic of the rate flagged and greyed -- flagged, never dropped: the PI's
 * advisory ruling of 2026-09-06 and decision 220 (a warning, not a refusal); the reasons folded
 * under "Design rationale". One line at the
 * bottom says what the record holds on that contact today against what the session yields, and
 * whether the margin can be switched on. The page's type scale (typeScale.js) and formatters
 * (stimFormat.js) are used throughout; nothing under 11 px.
 *
 * REBUILT AS THE CLINIC SHEET, 2026-09-14 (decisions 160-161): a header strip (rate, both pulse
 * widths, both ceilings, the current the OTHER side is held at while each ladder runs, the
 * ramp+test step timing, the total session length) and three printable tables -- the left ladder,
 * the right ladder, and the optional joint-corner points -- built directly from `sheet_rows`, in
 * the clinic template's own 19-column order (`sheet_columns`), never re-derived on the page.
 *
 * THE "MAKE GOOGLE SHEET" BUTTON IS WIRED (decision 163). It posts the chosen date to
 * `/api/exportTitrationSheet` (`Server/APIs/DataAnalysis.ExportTitrationSheet`, which rebuilds the
 * plan the same way this page's own request does and hands it to
 * `StimOptimizer/sheet_export.py`). The server answers one of two ways and the button follows
 * either: with Google credentials configured, JSON naming the real, shared Google Sheet it wrote
 * (the button becomes "Open in Google Sheets", plus "Re-export" to overwrite it); without them, a
 * filled `.xlsx` file, downloaded directly -- this page's own copy of the setup note
 * (`SHEET_EXPORT_SETUP_NOTE`, kept identical to `google_sheets_client.SETUP_NOTE`) is shown
 * underneath, since the download itself carries no JSON body to read a note from.
 *
 * THE DESIGN REVIEW OF 2026-09-26 (the PI: "yes to all six, build them"):
 *   - the clinic-sheet tables (34 rows on the 2026-09-15 response, 101 on 2026-09-25) fold under
 *     the export button that already makes the sheet: "Make Google sheet" exports them, and the
 *     page shows them one click away;
 *   - each side's explanatory prose (the rate, the ladder, the hold, the sensing contact, the
 *     harmonic paragraph) moves into that side's own "Design rationale" fold; the values stay open;
 *   - the session conditions both ladders share print once, under both columns;
 *   - the ceiling is stated once, in the header strip ("ceiling L 4.5 mA · R 4.5 mA");
 *   - THE HOME SCHEDULE IS INSIDE THIS CARD as its second fold (it was a card of its own, kept
 *     apart by the PI's ruling of 2026-09-12, which he amended on 2026-09-26): the next visit and
 *     the weeks after it are one plan;
 *   - where the protocol and the template come from folds too; no decision number is printed.
 *
 * THE MINIMALIST REDESIGN OF 2026-09-26 (SPEC.md section 5.3, §4): the section asks "What must the
 * next visit deliver?"; the session's facts in one row with "Make Google sheet" beside them; the two
 * ladders drawn as step plots of current against step number, the safe ceiling dashed and the side
 * held still named; the band centres on an 8–30 Hz axis, a flagged centre a hollow ring and each
 * folded multiple of the rate labelled ("rate ×4 → 30 Hz"); the exploratory ladder below a
 * hairline, not in a box; one "Design rationale" fold for both sides. Colours and sizes from the
 * shared tokens; the PI's harmonic wording is kept word for word.
 */
import React, { memo, useState } from "react";
import { Button, Table, TableBody, TableCell, TableHead, TableRow, TextField, Tooltip } from "@mui/material";

import MDBox from "components/MDBox";
import MDTypography from "components/MDTypography";

import { SessionController } from "database/session-control";

import Section from "views/Reports/paper/Section";

import { num, fmtHz, fmtMa, fmtUs, contactLabel, EMPTY } from "./stimFormat";
import { HomeScheduleSection, InForceAboveCeilingLine, inForceAboveCeiling } from "./CurrentMapScheduleCard";
import { OPTIMIZER_REQUEST } from "./optimizerRequest";
import { T, TYPE, HEAD, SMALL, MONO, NOWRAP, SUBHEAD, HEADING, WEIGHT, HAIRLINE, SizedFold as Fold } from "./typeScale";
import { LadderPlot, BandAxis } from "./LadderFigures";

/** Kept word-for-word identical to `StimOptimizer/google_sheets_client.py`'s `SETUP_NOTE` -- the
 * download itself is a raw file with no JSON body to carry the server's own copy in, so this page
 * shows its own. If one changes, change the other. */
const SHEET_EXPORT_SETUP_NOTE =
  "To let this server write directly to Google Sheets, sign it in as yourself: (1) in Google " +
  "Cloud, create an OAuth client (Desktop app) and put its JSON at " +
  "secrets/google_oauth_client.json; (2) on a machine with a browser, run " +
  "google_oauth_consent.py once and click Allow -- it writes secrets/google_oauth_token.json " +
  "(or point GOOGLE_OAUTH_TOKEN_FILE at it); (3) restart the server's worker processes. A " +
  "service-account key at secrets/google_service_account.json is used only when no user token " +
  "exists, and cannot CREATE sheets in a My Drive folder: a service account owns what it " +
  "creates and has no Drive storage, so the copy is refused for quota. Until one of these is " +
  "in place, this button downloads a filled .xlsx file instead.";

/** Pulls a `filename="..."` out of a `Content-Disposition` response header; falls back to a
 * generic name rather than failing the download outright. */
function filenameFromDisposition(disposition, fallback) {
  if (!disposition) return fallback;
  const m = /filename\*?=(?:UTF-8'')?"?([^";]+)"?/i.exec(disposition);
  return m ? decodeURIComponent(m[1]) : fallback;
}

/** The section's question (SPEC.md section 5.3, §4). */
export const TITRATION_CARD_TITLE = "Next-visit requirements";
/** The exploratory ladder's own heading (the PI, 2026-09-21): a second ladder for the stimulation
 *  configuration the readiness screen's best sensing pair needs, when it is not the one in force. */
export const EXPLORATORY_TITLE = "Exploratory ladder for the pair the readiness check prefers";

/** The soonest Wednesday on or after today, as "YYYY-MM-DD" for a `<input type="date">`. */
function nextWednesdayISO() {
  const d = new Date();
  const add = (3 - d.getDay() + 7) % 7; // Wed = 3; 0 if today already is Wednesday
  d.setDate(d.getDate() + add);
  const yyyy = d.getFullYear();
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  return `${yyyy}-${mm}-${dd}`;
}

/** A cell of the clinic sheet, formatted by its column name; a blank cell (most "test" rows,
 * every visit-filled column) is left blank, to be filled at the visit (the PI, 2026-09-26: "remove
 * 'not given' and just leave blank"; supersedes TASTE_AUDIT.md C9 for this table). */
const SHEET_MONO_COLS = new Set(["Amp (mA)", "Rate (Hz)", "PW (µs)", "Duration (s)"]);
function fmtSheetCell(col, v) {
  if (v === null || v === undefined || v === "") return "";
  if (col === "Rate (Hz)") return fmtHz(v);
  if (col === "Duration (s)") return `${v} s`;
  return String(v);
}

/** One printable clinic-sheet table: a leading Step column, then the template's own columns in
 * order, two rows per step (a "ramp" row and a "test" row) exactly as `sheet_rows` gives them. */
function SheetTable({ title, caption, rows, columns }) {
  if (!rows || !rows.length) return null;
  return (
    <MDBox sx={{ mt: 2 }}>
      <MDTypography variant="caption" component="div" sx={{ ...SUBHEAD, mb: 0.3 }}>
        {title}
      </MDTypography>
      {caption && (
        <MDTypography variant="caption" component="div" sx={{ ...SMALL, mb: 0.6 }}>
          {caption}
        </MDTypography>
      )}
      <MDBox data-scroll-x="" sx={{ overflowX: "auto", maxWidth: "100%" }}>
        <Table size="small">
          <TableHead sx={{ display: "table-header-group", p: 0 }}>
            <TableRow>
              <TableCell sx={{ py: 0.4, px: 0.6 }}>
                <MDTypography variant="caption" sx={HEAD}>Step</MDTypography>
              </TableCell>
              {columns.map((c) => (
                <TableCell key={c} sx={{ py: 0.4, px: 0.6 }}>
                  <MDTypography variant="caption" sx={{ ...HEAD, whiteSpace: "nowrap" }}>{c}</MDTypography>
                </TableCell>
              ))}
            </TableRow>
          </TableHead>
          <TableBody>
            {rows.map((r, i) => (
              <TableRow key={i}
                sx={{ backgroundColor: r.row_kind === "ramp" ? T.fillMuted : "transparent" }}>
                <TableCell sx={{ py: 0.3, px: 0.6 }}>
                  <MDTypography variant="caption"
                    sx={{ ...MONO, fontSize: TYPE.small }}>
                    {`${r.step ?? EMPTY}${r.row_kind ? ` · ${r.row_kind}` : ""}`}
                  </MDTypography>
                </TableCell>
                {columns.map((c) => (
                  <TableCell key={c} sx={{ py: 0.3, px: 0.6 }}>
                    <MDTypography variant="caption"
                      sx={{ fontSize: TYPE.small, whiteSpace: "nowrap", color: T.ink,
                        fontVariantNumeric: SHEET_MONO_COLS.has(c) ? "tabular-nums" : "normal" }}>
                      {fmtSheetCell(c, r[c])}
                    </MDTypography>
                  </TableCell>
                ))}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </MDBox>
    </MDBox>
  );
}

/** The header strip: the session's fixed facts, read once, printed once, above both columns. */
function SessionHeaderStrip({ plan }) {
  const left = (plan.sides || {}).Left || null;
  const right = (plan.sides || {}).Right || null;
  const st = plan.step_timing || {};
  const sess = plan.session_time || {};
  const stepLine = num(st.ramp_s) != null && num(st.test_s) != null
    ? `${num(st.ramp_s)} s ramp + ${num(st.test_s)} s test = ${Math.round((num(st.total_s) ?? (num(st.ramp_s) + num(st.test_s))) / 60)} min`
    : EMPTY;
  const items = [
    ["Rate", fmtHz((left || right || {}).rate_hz)],
    ["Left pulse width", fmtUs(left && left.pulse_width_us)],
    ["Right pulse width", fmtUs(right && right.pulse_width_us)],
    ["Safe ceiling", `L ${fmtMa(left && left.ceiling_mA)} · R ${fmtMa(right && right.ceiling_mA)}`],
    ["Left's ladder holds right at", fmtMa(left && left.held_other_side && left.held_other_side.current_mA)],
    ["Right's ladder holds left at", fmtMa(right && right.held_other_side && right.held_other_side.current_mA)],
    ["Step timing", stepLine],
    ["Total session time", num(sess.total_minutes) != null ? `~${Math.round(num(sess.total_minutes))} min` : EMPTY],
  ];
  return (
    <>
      <MDBox mt={2} display="flex" columnGap={3} rowGap={1.5} flexWrap="wrap">
        {items.map(([k, v]) => (
          <MDBox key={k}>
            <MDTypography variant="caption" component="div" sx={HEAD}>{k}</MDTypography>
            <MDTypography variant="caption" component="div"
              sx={{ ...MONO }}>{v}</MDTypography>
          </MDBox>
        ))}
      </MDBox>
    </>
  );
}

/** A held side whose current in force is above its safe ceiling is held AT the ceiling (decision
 * 308); the server's sentence says so. Printed in the next-visit section's always-visible lead, in
 * the warning colour: the section starts closed, and this instruction is never folded
 * (paper/Fold.js; 2026-09-26). */
export function heldCeilingNotes(plan) {
  const sides = (plan && plan.sides) || {};
  return [sides.Left, sides.Right]
    .map((p) => p && p.held_other_side && p.held_other_side.above_ceiling && p.held_other_side.note)
    .filter(Boolean).map((t) => String(t).replace(/ -- /g, " — "));
}

const LABEL = { ...HEAD, alignSelf: "baseline" };
/** A definition list in a fold: the term a 12 px header, the text 14 px body. */
const DL = { m: 0, "& dt": { ...HEAD, mt: 1 }, "& dd": { m: 0, fontSize: TYPE.body, lineHeight: 1.57, color: T.ink2 } };
const VALUE = { ...MONO, fontSize: TYPE.numLarge };
const VALUE_SMALL = { ...MONO, fontSize: TYPE.num };

/** One label + value row of a side's column. */
function Row({ label, children, sub }) {
  return (
    <MDBox sx={{ display: "grid", gridTemplateColumns: "minmax(88px, 0.45fr) minmax(0, 1fr)", columnGap: "12px",
      alignItems: "baseline", py: 0.4 }}>
      <MDTypography variant="caption" sx={LABEL}>{label}</MDTypography>
      <MDBox sx={{ minWidth: 0 }}>
        <div>{children}</div>
        {sub ? <MDTypography variant="caption" component="div" sx={SMALL}>{sub}</MDTypography> : null}
      </MDBox>
    </MDBox>
  );
}

/** The 22 centres: drawn on an 8–30 Hz axis, then named, a clear centre in ink and a flagged one in
 *  grey. Flagged is advisory only (the PI, 2026-09-06; a warning, never a refusal): it is never
 *  dropped from the analysis, so nothing here is struck through. */
function BandStrip({ bands }) {
  if (!bands || !Array.isArray(bands.centres_hz)) return <span style={SMALL}>{EMPTY}</span>;
  const flagged = new Set((bands.avoid_hz || []).map((v) => Number(v)));
  return (
    <MDBox>
      <BandAxis bands={bands} />
      <MDBox sx={{ display: "flex", flexWrap: "wrap", gap: "2px 6px", alignItems: "baseline", mt: 0.5 }}>
        {bands.centres_hz.map((c) => {
          const x = Number(c);
          const isFlagged = flagged.has(x);
          const reason = isFlagged ? (bands.avoid_reasons || {})[String(x)] || "" : "clear of every stimulator harmonic";
          return (
            <span key={x} title={`${x} Hz: ${reason}`}
              style={{ ...MONO, fontSize: TYPE.small, color: isFlagged ? T.ink3 : T.ink }}>
              {x}
            </span>
          );
        })}
        <span style={{ ...SMALL, marginLeft: 6 }}>
          {`Hz · ${bands.n_clear ?? "—"} clear, ${bands.n_avoid ?? "—"} flagged (analysed either way); on the axis a clear centre is a filled dot and a flagged one a hollow ring`}
        </span>
      </MDBox>
    </MDBox>
  );
}

/** The ladder's held side, in words, for the step plot. */
function heldWords(side, plan) {
  const other = side === "Left" ? "right" : "left";
  const h = plan && plan.held_other_side;
  const v = num(h && h.current_mA);
  return v === null ? null : `${other} side held at ${fmtMa(v)}`;
}

function SideColumn({ side, plan, shared = [], todayShared = false }) {
  if (!plan) {
    return (
      <MDBox>
        <MDTypography variant="h6" component="h3" sx={HEADING}>{side}</MDTypography>
        <MDTypography variant="caption" sx={SMALL}>no plan for this side</MDTypography>
      </MDBox>
    );
  }
  const c = plan.sensing_contact;
  const lad = plan.ladder || {};
  const hold = plan.hold || {};
  const rec = (plan.yield || {}).record_today || {};
  return (
    <MDBox sx={{ minWidth: 0 }}>
      <MDTypography variant="h6" component="h3" sx={HEADING}>{side}</MDTypography>
      <Row label="Rate">
        <span style={VALUE}>{fmtHz(plan.rate_hz)}</span>
        {plan.rate_lifted && num(plan.rate_in_force_hz) !== null && (
          <span style={{ ...SMALL, marginLeft: 8, color: T.caution }}>
            <span aria-hidden="true">▲ </span>{`(in force: ${fmtHz(plan.rate_in_force_hz)})`}
          </span>
        )}
      </Row>
      <Row label="Pulse width">
        <span style={VALUE}>{fmtUs(plan.pulse_width_us)}</span>
      </Row>
      <Row label="Ladder">
        <span style={{ ...VALUE_SMALL, whiteSpace: "normal" }}>{lad.compact || EMPTY}</span>
        {num(lad.n_steps) !== null && (
          <span style={{ ...SMALL, marginLeft: 8 }}>
            {`${lad.n_steps} steps, ${lad.n_distinct_currents} distinct currents`}
          </span>
        )}
      </Row>
      <LadderPlot side={side} steps={lad.steps_mA} ceilingMa={plan.ceiling_mA} heldText={heldWords(side, plan)} />
      <Row label="Hold per step">
        <span style={VALUE}>{num(hold.seconds) === null ? EMPTY : `${num(hold.seconds)} s`}</span>
        {num(hold.usable_pieces_after_margin) !== null && (
          <span style={{ ...SMALL, marginLeft: 8 }}>
            {`${hold.usable_pieces_after_margin} usable ${num(hold.piece_s)} s pieces after the ${num(hold.post_ramp_margin_s)} s margin (${hold.min_pieces_required} needed)`}
          </span>
        )}
      </Row>
      <Row label="Record from">
        {c ? (
          <span>
            <span style={{ ...VALUE, color: c.on_other_side ? T.caution : VALUE.color }}>{c.on_other_side ? <span aria-hidden="true">▲ </span> : null}{contactLabel(c)}</span>
            {num(c.n_qualifying) !== null && (
              <span style={{ ...SMALL, marginLeft: 8 }}>
                {`${c.n_qualifying} of ${num(c.n_bands) === null ? "—" : c.n_bands} bands both fall with current and rise with pain at ${fmtHz(c.rate_hz)}${Array.isArray(c.qualifying_centers_hz) && c.qualifying_centers_hz.length ? ` (${c.qualifying_centers_hz.map((v) => Number(v)).join(", ")} Hz)` : ""}${c.deployable ? "" : " · did not pass the readiness check"}`}
              </span>
            )}
          </span>
        ) : <span style={{ ...VALUE, color: T.ink3 }}>{EMPTY}</span>}
      </Row>
      <Row label="Analyse at">
        <BandStrip bands={plan.bands} />
      </Row>
      {(plan.conditions || []).filter((t) => !shared.includes(t)).length > 0 && (
        <MDBox mt={1}>
          <MDTypography variant="caption" sx={LABEL}>During this ladder</MDTypography>
          <MDBox component="ul" sx={{ m: 0, mt: 0.3, pl: 2.2 }}>
            {(plan.conditions || []).filter((t) => !shared.includes(t)).map((t, i) => (
              <li key={i} style={{ fontSize: TYPE.body, lineHeight: 1.57, color: T.ink2 }}>{t}</li>
            ))}
          </MDBox>
        </MDBox>
      )}
      {!todayShared && (
        <MDTypography variant="caption" component="div" sx={{ ...SMALL, mt: 1 }}>
          {`today: ${rec.note || EMPTY}`}
        </MDTypography>
      )}
    </MDBox>
  );
}

/** One side's reasons, for the section's one "Design rationale" fold. */
function WhySide({ side, plan }) {
  if (!plan) return null;
  const c = plan.sensing_contact;
  const lad = plan.ladder || {};
  const hold = plan.hold || {};
  const src = plan.sources || {};
  // `harmonics_hz` carries the two sub-harmonics (half_rate, quarter_rate, three_quarters_rate)
  // plus however many whole-multiple landings fold into range at this rate (multiple_4,
  // multiple_5, ...); read every value present rather than a fixed key list, so a rate whose
  // folded landings differ from 55 Hz's still shows all of them (found 2026-09-25).
  const harm = (plan.bands || {}).harmonics_hz || {};
  const harmonicsText = Object.values(harm)
    .map((v) => num(v))
    .filter((v) => v !== null)
    .sort((a, b) => a - b)
    .map((v) => `${v} Hz`)
    .join(", ");
  return (
    <MDBox mt={1}>
      <MDTypography variant="caption" component="div" sx={SUBHEAD}>{side}</MDTypography>
      <MDBox component="dl" sx={DL}>
        {plan.pulse_width_note ? <><dt>Pulse width</dt><dd>{plan.pulse_width_note}</dd></> : null}
        {lad.why ? <><dt>Ladder, in words</dt><dd>{lad.why}</dd></> : null}
        {hold.why ? <><dt>Hold per step, why</dt><dd>{hold.why}</dd></> : null}
        <dt>Record from, why</dt>
        <dd>{c ? (c.ipsilateral_alternative
          ? `${c.note}. The best contact on this side itself: ${contactLabel(c.ipsilateral_alternative)}, ${c.ipsilateral_alternative.n_qualifying ?? "—"} of ${c.ipsilateral_alternative.n_bands ?? "—"} bands both fall with current and rise with pain${c.ipsilateral_alternative.deployable ? "" : " (did not pass the readiness check)"}`
          : c.note) : (plan.sensing_contact_note || EMPTY)}</dd>
        {harmonicsText ? (
          <><dt>Analyse at, the harmonics</dt>
            <dd>{`the stimulator shows up at ${harmonicsText}; a centre within ±${num((plan.bands || {}).half_width_hz) ?? "—"} Hz of one carries a folded multiple of the stimulation rate and is flagged, not dropped -- every centre above is still analysed (advisory, the PI, 2026-09-06)`}</dd></>
        ) : null}
        <dt>Rate</dt><dd>{plan.rate_why} — {src.rate_hz}</dd>
        <dt>Pulse width, source</dt><dd>{src.pulse_width_us}</dd>
        <dt>Ceiling</dt><dd>{src.ceiling_mA}</dd>
        <dt>Ladder, source</dt><dd>{src.ladder}</dd>
        <dt>Hold per step, source</dt><dd>{src.hold}</dd>
        <dt>Sensing contact</dt><dd>{src.sensing_contact}</dd>
        <dt>Band centres</dt><dd>{(plan.bands || {}).why} — {src.bands}</dd>
        <dt>What the record holds today</dt><dd>{src["yield.record_today"]}</dd>
        <dt>The margin</dt><dd>{src["yield.margin"]}</dd>
        <dt>The conditions</dt><dd>{src.conditions}</dd>
      </MDBox>
    </MDBox>
  );
}

/** One proposed configuration's plan (`titration_plan.proposed[side]`): the contacts to stimulate
 *  and why, the pair and rate they serve, what the record holds for that configuration, the two
 *  answers the session is built for, the ladder, the holds, and the conditions. */
function ProposedColumn({ p }) {
  if (!p) return null;
  const st = p.stimulation || {};
  const sp = p.sensing_pair || {};
  const c = p.contact || {};
  const fe = p.first_exposure || {};
  const lad = p.ladder || {};
  const holds = p.acute_pain_holds || {};
  const bands = p.bands || {};
  const src = p.sources || {};
  const other = p.side === "Left" ? "right" : "left";
  const watch = Array.isArray(bands.watch_hz) ? bands.watch_hz.map((v) => Number(v)).join(", ") : "";
  return (
    <MDBox sx={{ minWidth: 0 }}>
      <MDTypography variant="h6" component="h3" sx={HEADING}>{`${p.side}: stimulate ${st.contacts_short || EMPTY}`}</MDTypography>
      <MDTypography variant="caption" component="div" sx={{ fontSize: TYPE.body, lineHeight: 1.57, color: T.ink2, mt: 0.5, maxWidth: "68ch" }}>
        {p.purpose}
      </MDTypography>
      <Row label="Stimulate on">
        <span style={VALUE}>{st.contacts_short || EMPTY}</span>
        {st.differs_from_in_force && (
          <span style={{ ...SMALL, marginLeft: 8, color: T.caution }}>
            <span aria-hidden="true">▲ </span>{`(in force today: rings ${(st.in_force_rings || []).join(", ") || "none"})`}
          </span>
        )}
      </Row>
      <Row label="Record from">
        <span style={VALUE}>{sp.display_short || sp.channel || EMPTY}</span>
      </Row>
      <Row label="Rate">
        <span style={VALUE}>{fmtHz(p.rate_hz)}</span>
        {num(p.rate_in_force_hz) !== null && num(p.rate_in_force_hz) !== num(p.rate_hz) && (
          <span style={{ ...SMALL, marginLeft: 8, color: T.caution }}><span aria-hidden="true">▲ </span>{`(in force today: ${fmtHz(p.rate_in_force_hz)})`}</span>
        )}
      </Row>
      <Row label="Pulse width"><span style={VALUE}>{fmtUs(p.pulse_width_us)}</span></Row>
      <Row label="Watch">
        <span style={VALUE_SMALL}>{watch ? `${watch} Hz` : EMPTY}</span>
      </Row>
      <Row label="The record today">
        <span style={{ fontSize: TYPE.body, color: fe.ever_powered === false ? T.caution : T.ink }}>{fe.ever_powered === false ? <span aria-hidden="true">▲ </span> : null}{fe.sentence || EMPTY}</span>
      </Row>
      <Row label="Stop rule"><span style={{ fontSize: TYPE.body, color: T.ink }}>{fe.stop_rule || EMPTY}</span></Row>
      <Row label="Ladder (part A)">
        <span style={{ ...VALUE_SMALL, whiteSpace: "normal" }}>{lad.compact || EMPTY}</span>
        {num(lad.n_steps) !== null && (
          <span style={{ ...SMALL, marginLeft: 8 }}>{`${lad.n_steps} steps, ${lad.n_distinct_currents} distinct currents`}</span>
        )}
      </Row>
      <Row label="Holds (part B)">
        <span style={{ ...VALUE_SMALL, whiteSpace: "normal" }}>
          {(holds.holds || []).length
            ? `${holds.holds.map((h) => h.state).join(" / ")}: ${holds.holds.map((h) => fmtMa(h.current_mA)).join(", ")}, ${num(holds.minutes_each)} min each, a rating every ${num(holds.rating_every_minutes)} min, the patient blind to the current`
            : EMPTY}
        </span>
      </Row>
      <Row label="The other side"
        sub={p.held_other_side && p.held_other_side.above_ceiling && p.held_other_side.note
          ? <span style={{ color: T.caution }}><span aria-hidden="true">▲ </span>{String(p.held_other_side.note).replace(/ -- /g, " — ")}</span> : null}>
        <span style={{ fontSize: TYPE.body, color: T.ink }}>{`${other} side held at ${fmtMa(p.held_other_side && p.held_other_side.current_mA)}`}</span>
      </Row>
      <Row label="Time">
        <span style={{ fontSize: TYPE.body, color: T.ink }}>{num((p.session_time || {}).total_minutes) != null ? `~${Math.round(num(p.session_time.total_minutes))} min on its own` : EMPTY}</span>
      </Row>
      {/* Its session conditions and the time's breakdown fold: most of the list repeats the rows
          above and the ordinary session's conditions (the design review of 2026-09-26). */}
      <Fold show={`During this ladder: the full list (${(p.conditions || []).length}) and the time, in detail`} hide="Hide" mt={0.6}>
        <MDBox component="ul" sx={{ m: 0, mt: 0.3, pl: 2.2 }}>
          {(p.conditions || []).map((t, i) => (
            <li key={i} style={{ fontSize: TYPE.body, lineHeight: 1.57, color: T.ink2 }}>{t}</li>
          ))}
        </MDBox>
        {(p.session_time || {}).why ? (
          <MDTypography variant="caption" component="div" sx={{ ...SMALL, mt: 0.4 }}>{`time: ${p.session_time.why}`}</MDTypography>
        ) : null}
      </Fold>
      <Fold show="Design rationale" hide="Hide" mt={0.6}>
        <MDBox component="dl" sx={DL}>
          {sp.why ? <><dt>stimulate on, why</dt><dd>{`${sp.display_short || sp.channel}: ${sp.why}`}</dd></> : null}
          {num(c.n_qualifying) !== null ? (
            <><dt>record from, what the pair holds</dt>
              <dd>{`${c.n_qualifying} of ${num(c.n_bands) ?? "—"} bands rise with pain on this pair at ${fmtHz(c.rate_hz)}; ${num(c.n_responding) ?? 0} fall with current (none can, until this configuration has carried current)`}</dd></>
          ) : null}
          {bands.watch_why ? <><dt>watch, why</dt><dd>{bands.watch_why}</dd></> : null}
          {fe.why ? <><dt>the record today, why</dt><dd>{fe.why}</dd></> : null}
          {lad.why ? <><dt>ladder, in words</dt><dd>{lad.why}</dd></> : null}
          {holds.why ? <><dt>holds, why</dt><dd>{holds.why}</dd></> : null}
          {Object.entries(src).map(([k, v]) => (<React.Fragment key={k}><dt>{k.replace(/_/g, " ")}</dt><dd>{v}</dd></React.Fragment>))}
        </MDBox>
      </Fold>
    </MDBox>
  );
}

function TitrationSessionCard({ plan, participantUid, homeSchedule = null }) {
  const [sessionDate, setSessionDate] = useState(nextWednesdayISO);
  // status: "idle" | "working" | "error" | "xlsx" | "drive"
  const [exportState, setExportState] = useState({ status: "idle" });

  const handleExport = async () => {
    if (!participantUid || exportState.status === "working") return;
    setExportState({ status: "working" });
    try {
      const response = await SessionController.query(
        "/api/exportTitrationSheet",
        // The page's own request, so the server's rebuild is the stored response the page read
        // (2026-09-26: the participant and date alone were answered under another key).
        { ...OPTIMIZER_REQUEST, ParticipantId: participantUid, VisitDate: sessionDate },
        undefined, undefined, "blob");
      const contentType = String((response.headers || {})["content-type"] || "");
      if (contentType.indexOf("json") !== -1) {
        const text = await response.data.text();
        const data = JSON.parse(text);
        if (data.available === false) {
          setExportState({ status: "error", message: data.reason || "the export could not be built" });
          return;
        }
        if (data.mode === "drive") {
          setExportState({ status: "drive", url: data.url, name: data.name,
            overwrote: !!data.overwrote, nRows: data.n_rows });
          return;
        }
        setExportState({ status: "error",
          message: "the server returned an answer this page does not recognise" });
        return;
      }
      const disposition = (response.headers || {})["content-disposition"];
      const filename = filenameFromDisposition(disposition, "titration_session.xlsx");
      const blobUrl = window.URL.createObjectURL(response.data);
      const a = document.createElement("a");
      a.href = blobUrl;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(blobUrl);
      setExportState({ status: "xlsx", name: filename });
    } catch (err) {
      const message = (err && err.response && err.response.data && err.response.data.message)
        || (err && err.message) || "the export request failed";
      setExportState({ status: "error", message });
    }
  };

  if (!plan) return null;
  const sides = plan.sides || {};
  const margin = plan.margin || {};
  const left = sides.Left || null;
  const right = sides.Right || null;
  // Page-written wording (SPEC.md section 6): "the margin" is dropping the first 20 s after each
  // current change; a "settled setting" is a step held long enough to read.
  const MARGIN = "dropping the first 20 s after each current change";
  const marginLine = (() => {
    if (!plan.available) return plan.reason || "the plan could not be built";
    const need = num(margin.min_settled_settings);
    if (need === null) return `whether ${MARGIN} can be switched on could not be judged (no per-run table is stored)`;
    if (margin.available) {
      return `A run with at least ${need} steps held long enough to read exists (${margin.run} on ${margin.sensing_contact}: ${margin.max_settled_settings_in_one_run}), so ${MARGIN} ${margin.switch_on ? "is switched on" : "can be switched on; it is off today"}.`;
    }
    const most = num(margin.max_settled_settings_in_one_run);
    return `No run in the record holds the ${need} steps held long enough to read that ${MARGIN} needs${most === null ? "" : ` (the most in any one run is ${most}, ${margin.run} on ${margin.sensing_contact})`}; it stays off until this session is recorded, and the session's rising leg alone gives ${num((left || right || {}).yield ? (left || right).yield.distinct_currents_up_leg : null) ?? "—"}.`;
  })();

  const sheetRows = Array.isArray(plan.sheet_rows) ? plan.sheet_rows : [];
  const sheetColumns = Array.isArray(plan.sheet_columns) ? plan.sheet_columns : [];
  const leftRows = sheetRows.filter((r) => r.block === "left_ladder");
  const rightRows = sheetRows.filter((r) => r.block === "right_ladder");
  const jointRows = sheetRows.filter((r) => r.block === "joint_corners");
  const jc = plan.joint_corners || {};
  const proposed = plan.proposed || {};
  const proposedSides = Object.keys(proposed).filter((k) => proposed[k]);
  // The session conditions both ladders share, printed once under both columns.
  const lc = (left && Array.isArray(left.conditions)) ? left.conditions : [];
  const rc = (right && Array.isArray(right.conditions)) ? right.conditions : [];
  const shared = left && right ? lc.filter((t) => rc.includes(t)) : [];
  // The record today, and what the session yields: once when both sides read alike.
  const todayOf = (p) => (((p || {}).yield || {}).record_today || {}).note || null;
  const todayShared = !!(left && right && todayOf(left) && todayOf(left) === todayOf(right));
  const yieldOf = (p) => ((p || {}).yield || {}).sentence || null;
  const yieldShared = !!(left && right && yieldOf(left) && yieldOf(left) === yieldOf(right));

  const oneRate = num((left || right || {}).rate_hz);
  const minutes = num((plan.session_time || {}).total_minutes);
  const answer = plan.available
    ? `One clinic session${oneRate !== null ? ` at ${fmtHz(oneRate)}` : ""}: each side's current stepped up from 0 mA in ${num(plan.step_mA) ?? 0.5} mA steps and back down, ${num(plan.hold_s) ?? 60} s a step, with recording on${minutes !== null ? `, about ${Math.round(minutes)} minutes` : ""}.`
    : null;
  const exportControls = (
    <MDBox display="flex" alignItems="center" gap={1} flexWrap="wrap">
      <TextField type="date" size="small" value={sessionDate} label="Visit date"
        onChange={(e) => { setSessionDate(e.target.value); setExportState({ status: "idle" }); }}
        inputProps={{ style: { fontSize: TYPE.body, fontVariantNumeric: "tabular-nums", padding: "8px 10px" } }} />
      {exportState.status === "drive" ? (
        <MDBox display="flex" alignItems="center" gap={1}>
          <MDTypography component="a" href={exportState.url} target="_blank" rel="noreferrer"
            variant="caption" sx={{ fontSize: TYPE.body, color: T.accent, whiteSpace: "nowrap" }}>
            Open in Google Sheets
          </MDTypography>
          <Button variant="text" size="small" onClick={handleExport}
            disabled={!participantUid}
            sx={{ fontSize: TYPE.body, textTransform: "none", whiteSpace: "nowrap", color: T.ink2 }}>
            Re-export
          </Button>
        </MDBox>
      ) : (
        <Tooltip title={participantUid ? "copies the clinic-sheet template and writes this "
          + "session's rows into it" : "no participant is selected"}>
          <span>
            <Button variant="contained" size="small" onClick={handleExport} disableElevation
              disabled={!participantUid || exportState.status === "working"}
              sx={{ fontSize: TYPE.body, fontWeight: WEIGHT.strong, textTransform: "none", whiteSpace: "nowrap",
                minHeight: 36, px: 2, backgroundColor: T.accent, color: `${T.onFill} !important`,
                boxShadow: "none", "&:hover": { backgroundColor: T.accent, boxShadow: "none" } }}>
              {exportState.status === "working" ? "Making sheet…" : "Make Google sheet"}
            </Button>
          </span>
        </Tooltip>
      )}
    </MDBox>
  );

  // The two safety lines stay in view while the section is closed (2026-09-26).
  const heldNotes = plan.available ? heldCeilingNotes(plan) : [];
  const homeInForce = homeSchedule ? inForceAboveCeiling(homeSchedule) : null;
  const lead = (heldNotes.length || homeInForce) ? (
    <MDBox data-testid="next-visit-safety-lead">
      {heldNotes.map((t) => (
        <MDTypography key={t} variant="caption" component="div" data-testid="held-above-ceiling"
          sx={{ fontSize: TYPE.body, mt: 0.5, color: T.caution }}>{`▲ Held at the ceiling: ${t}.`}</MDTypography>
      ))}
      <InForceAboveCeilingLine inForce={homeInForce} />
    </MDBox>
  ) : null;

  return (
    <Section id="next-visit" question={TITRATION_CARD_TITLE} answer={answer} lead={lead} collapsible>
        {exportControls}

        {exportState.status === "error" && (
          <MDTypography variant="caption" component="div"
            sx={{ fontSize: TYPE.body, mt: 1, color: T.caution }}>
            {`▲ could not make the sheet: ${exportState.message}`}
          </MDTypography>
        )}
        {exportState.status === "drive" && (
          <MDTypography variant="caption" component="div" sx={{ ...SMALL, mt: 1 }}>
            {`${exportState.overwrote ? "Overwrote" : "Wrote"} "${exportState.name}" with `
              + `${exportState.nRows} rows. Re-export overwrites this same file rather than `
              + "making a new copy."}
          </MDTypography>
        )}
        {exportState.status === "xlsx" && (
          <MDTypography variant="caption" component="div" sx={{ ...SMALL, mt: 1 }}>
            {`Downloaded ${exportState.name}. ${SHEET_EXPORT_SETUP_NOTE}`}
          </MDTypography>
        )}

        {!plan.available ? (
          <MDTypography variant="caption" component="div" sx={{ fontSize: TYPE.body, mt: 1, color: T.notChecked }}>
            {`○ ${plan.reason || "the plan could not be built"}`}
          </MDTypography>
        ) : (
          <>
            <SessionHeaderStrip plan={plan} />

            <MDBox mt={3} sx={{ display: "grid", gridTemplateColumns: { xs: "minmax(0, 1fr)", md: "repeat(2, minmax(0, 1fr))" }, columnGap: "48px", rowGap: "24px" }}>
              <SideColumn side="Left" plan={left} shared={shared} todayShared={todayShared} />
              <SideColumn side="Right" plan={right} shared={shared} todayShared={todayShared} />
            </MDBox>
            {todayShared && (
              <MDTypography variant="caption" component="div" sx={{ ...SMALL, mt: 1 }}>
                {`both sides today: ${todayOf(left)}`}
              </MDTypography>
            )}
            {shared.length > 0 && (
              <MDBox mt={1.5}>
                <MDTypography variant="caption" sx={LABEL}>During the session, both ladders</MDTypography>
                <MDBox component="ul" sx={{ m: 0, mt: 0.3, pl: 2.2 }}>
                  {shared.map((t, i) => (
                    <li key={i} style={{ fontSize: TYPE.body, lineHeight: 1.57, color: T.ink2 }}>{t}</li>
                  ))}
                </MDBox>
              </MDBox>
            )}
            {/* ONE "Design rationale" fold for both sides (SPEC.md section 5.3, §4). */}
            {(left || right) && (
              <Fold show="Design rationale" hide="Hide why this design" mt={1.5}>
                <WhySide side="Left" plan={left} />
                <WhySide side="Right" plan={right} />
              </Fold>
            )}

            {/* The exploratory ladder: below a hairline, not in a box. */}
            {proposedSides.length > 0 && (
              <MDBox mt={3} pt={3} sx={{ borderTop: HAIRLINE }}>
                <MDTypography variant="h6" component="h3" sx={{ ...HEADING, fontSize: TYPE.lead }}>{EXPLORATORY_TITLE}</MDTypography>
                <MDTypography variant="caption" component="div" sx={{ fontSize: TYPE.body, color: T.ink2, mb: 1, mt: 0.5, maxWidth: "68ch" }}>
                  {"Best sensing pair on this side needs other stimulating contacts than today's; this ladder runs them. Separate visit, or end of the session; rows at the end of the sheet."}
                </MDTypography>
                <MDBox sx={{ display: "grid", gridTemplateColumns: { xs: "minmax(0, 1fr)", md: proposedSides.length > 1 ? "repeat(2, minmax(0, 1fr))" : "minmax(0, 1fr)" }, columnGap: "48px", rowGap: "24px" }}>
                  {proposedSides.map((side) => <ProposedColumn key={side} p={proposed[side]} />)}
                </MDBox>
              </MDBox>
            )}

            {/* The clinic sheet, folded under the button that exports it (the design review of
                2026-09-26, S1: about 1,200 of the card's words on the 2026-09-15 response). */}
            <MDBox mt={3} sx={{ borderTop: HAIRLINE, pt: 1.5 }}>
              <Fold show={`Show the clinic sheet (${sheetRows.length} rows; "Make Google sheet" above exports it)`}
                hide="Hide the clinic sheet" mt={0}>
              <MDBox data-testid="clinic-sheet-tables">
              <SheetTable
                title={`Left ladder${left && left.sensing_contact ? ` — record from ${contactLabel(left.sensing_contact)}` : ""}`}
                caption={left
                  ? `0 mA to ${fmtMa(left.ceiling_mA)} in ${num(plan.step_mA) ?? 0.5} mA steps, top held once, back down to 0 mA in `
                    + `${num(plan.down_step_mA) ?? 1.0} mA drops; the right side held at `
                    + `${fmtMa(left.held_other_side && left.held_other_side.current_mA)} for the whole ladder.`
                  : null}
                rows={leftRows} columns={sheetColumns} />
              <SheetTable
                title={`Right ladder${right && right.sensing_contact ? ` — record from ${contactLabel(right.sensing_contact)}` : ""}`}
                caption={right
                  ? `0 mA to ${fmtMa(right.ceiling_mA)} in ${num(plan.step_mA) ?? 0.5} mA steps, top held once, back down to 0 mA in `
                    + `${num(plan.down_step_mA) ?? 1.0} mA drops; the left side held at `
                    + `${fmtMa(right.held_other_side && right.held_other_side.current_mA)} for the whole ladder.`
                  : null}
                rows={rightRows} columns={sheetColumns} />
              <SheetTable
                title={`Joint corners (optional, ${jointRows.length ? Math.round(jointRows.length / 2) : 0} points)`}
                caption={jc.why ? `${jc.why}; not run if the visit is short on time.` : "not run if the visit is short on time."}
                rows={jointRows} columns={sheetColumns} />
              {proposedSides.map((side) => {
                const p = proposed[side];
                const rows = sheetRows.filter((r) => String(r.block).startsWith(`exploratory_${side.toLowerCase()}`));
                return (
                  <SheetTable key={`expl-${side}`}
                    title={`Exploratory ladder — ${(p.stimulation || {}).contacts_short || side} (${rows.filter((r) => r.row_kind === "ramp").length} steps, then ${rows.filter((r) => r.row_kind === "hold").length} holds)`}
                    caption={`Part A: 0 mA to ${fmtMa(p.ceiling_mA)} in ${num(plan.step_mA) ?? 0.5} mA steps at ${fmtHz(p.rate_hz)}, stopped at the first side-effect score of 2, back down in ${num(plan.down_step_mA) ?? 1.0} mA drops; part B: three ${num((p.acute_pain_holds || {}).minutes_each) ?? 5} min holds, off / on / off, a rating every minute; the ${side === "Left" ? "right" : "left"} side held at ${fmtMa(p.held_other_side && p.held_other_side.current_mA)}.`}
                    rows={rows} columns={sheetColumns} />
                );
              })}
              </MDBox>
              </Fold>
            </MDBox>
          </>
        )}
        {plan.available && (
          <MDBox mt={2}>
            <MDTypography variant="caption" component="div" sx={{ fontSize: TYPE.body, lineHeight: 1.57, color: T.ink2 }}>
              {yieldShared ? (
                <span style={{ display: "block" }}>
                  <b style={{ ...NOWRAP, color: T.ink }}>Both sides:</b> {yieldOf(left)}
                </span>
              ) : [left, right].filter(Boolean).map((p) => (
                <span key={p.side} style={{ display: "block" }}>
                  <b style={{ ...NOWRAP, color: T.ink }}>{p.side}:</b> {(p.yield || {}).sentence || EMPTY}
                </span>
              ))}
              <span style={{ display: "block", marginTop: 4, color: margin.available ? T.ink : T.caution }}>
                {`${margin.available ? "✓" : "▲"} ${marginLine}`}
              </span>
            </MDTypography>
            <Fold show="Protocol and template source" hide="Hide" mt={1}>
              <MDTypography variant="caption" component="div" sx={{ ...SMALL }}>
                {`protocol: ${plan.protocol_source || EMPTY}`}
              </MDTypography>
              {plan.sheet_source && (
                <MDTypography variant="caption" component="div" sx={{ ...SMALL, mt: 0.4 }}>
                  {`sheet template: ${plan.sheet_source}`}
                </MDTypography>
              )}
              {(plan.session_time || {}).why && (
                <MDTypography variant="caption" component="div" sx={{ ...SMALL, mt: 0.4 }}>
                  {`total session time: ${plan.session_time.why}`}
                </MDTypography>
              )}
            </Fold>
          </MDBox>
        )}
        {/* The home schedule, inside this section below a hairline (the PI amended his ruling of
            2026-09-12 on 2026-09-26: the visit and the weeks after it are one plan). */}
        {homeSchedule && <HomeScheduleSection schedule={homeSchedule} showInForce={false} />}
    </Section>
  );
}

// Rebuilt only when one of its inputs changes (speed-up item C6, 2026-10-02). The page re-renders
// several times while it loads and every card below it was rebuilt each time with the same inputs;
// the next-visit card (its clinic sheet is hundreds of table cells, folded but mounted) took about a quarter of a second per rebuild in the page test.
export default memo(TitrationSessionCard);
