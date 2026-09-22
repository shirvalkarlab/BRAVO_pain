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
 * notation); the 22 band centres as a strip, clear ones in ink and the ones within 2.5 Hz of a
 * harmonic of the rate struck; the reasons folded under "Why this design". One line at the
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
 */
import React, { useState } from "react";
import { Button, Card, Table, TableBody, TableCell, TableHead, TableRow, TextField, Tooltip } from "@mui/material";

import MDBox from "components/MDBox";
import MDTypography from "components/MDTypography";

import { SessionController } from "database/session-control";

import PAL from "views/Reports/ClosedLoopSim/palette";

import { num, fmtHz, fmtMa, fmtUs, contactLabel } from "./stimFormat";
import { TYPE, HEAD, SMALL, MONO, NOWRAP, SizedFold as Fold } from "./typeScale";

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

export const TITRATION_CARD_TITLE = "Titration session to run next";
/** The exploratory ladder's own heading (the PI, 2026-09-21): a second ladder for the stimulation
 *  configuration the readiness screen's best sensing pair needs, when it is not the one in force. */
export const EXPLORATORY_TITLE = "Exploratory ladder for the pair the screen prefers";

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
 * every visit-filled column) prints as an em dash. */
const SHEET_MONO_COLS = new Set(["Amp (mA)", "Rate (Hz)", "PW (µs)", "Duration (s)"]);
function fmtSheetCell(col, v) {
  if (v === null || v === undefined || v === "") return "—";
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
      <MDTypography variant="caption" component="div" fontWeight="medium"
        sx={{ fontSize: TYPE.num, mb: 0.3 }}>
        {title}
      </MDTypography>
      {caption && (
        <MDTypography variant="caption" component="div" color="text" sx={{ ...SMALL, mb: 0.6 }}>
          {caption}
        </MDTypography>
      )}
      <MDBox sx={{ overflowX: "auto" }}>
        <Table size="small">
          <TableHead sx={{ display: "table-header-group", p: 0 }}>
            <TableRow>
              <TableCell sx={{ py: 0.4, px: 0.6 }}>
                <MDTypography variant="caption" sx={HEAD}>step</MDTypography>
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
                sx={{ backgroundColor: r.row_kind === "ramp" ? "rgba(0,0,0,0.025)" : "transparent" }}>
                <TableCell sx={{ py: 0.3, px: 0.6 }}>
                  <MDTypography variant="caption"
                    sx={{ fontSize: TYPE.small, fontFamily: PAL.mono, whiteSpace: "nowrap" }}>
                    {`${r.step ?? "—"}${r.row_kind ? ` · ${r.row_kind}` : ""}`}
                  </MDTypography>
                </TableCell>
                {columns.map((c) => (
                  <TableCell key={c} sx={{ py: 0.3, px: 0.6 }}>
                    <MDTypography variant="caption"
                      sx={{ fontSize: TYPE.small, whiteSpace: "nowrap",
                        fontFamily: SHEET_MONO_COLS.has(c) ? PAL.mono : "inherit" }}>
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
    : "—";
  const items = [
    ["rate", fmtHz((left || right || {}).rate_hz)],
    ["left pulse width", fmtUs(left && left.pulse_width_us)],
    ["right pulse width", fmtUs(right && right.pulse_width_us)],
    ["left ceiling", fmtMa(left && left.ceiling_mA)],
    ["right ceiling", fmtMa(right && right.ceiling_mA)],
    ["left's ladder holds right at", fmtMa(left && left.held_other_side && left.held_other_side.current_mA)],
    ["right's ladder holds left at", fmtMa(right && right.held_other_side && right.held_other_side.current_mA)],
    ["step timing", stepLine],
    ["total session time", num(sess.total_minutes) != null ? `~${Math.round(num(sess.total_minutes))} min` : "—"],
  ];
  return (
    <MDBox mt={1} display="flex" columnGap={3} rowGap={1} flexWrap="wrap">
      {items.map(([k, v]) => (
        <MDBox key={k}>
          <MDTypography variant="caption" component="div" sx={HEAD}>{k}</MDTypography>
          <MDTypography variant="caption" component="div"
            sx={{ fontSize: TYPE.num, fontFamily: PAL.mono, whiteSpace: "nowrap" }}>{v}</MDTypography>
        </MDBox>
      ))}
      {sess.why && (
        <MDTypography variant="caption" component="div" color="text" sx={{ ...SMALL, width: "100%", mt: 0.3 }}>
          {sess.why}
        </MDTypography>
      )}
    </MDBox>
  );
}

const LABEL = { ...HEAD, alignSelf: "baseline" };
const VALUE = { ...MONO, fontSize: TYPE.numLarge };
const VALUE_SMALL = { ...MONO, fontSize: TYPE.num };

/** One label + value row of a side's column. */
function Row({ label, children, sub }) {
  return (
    <MDBox sx={{ display: "grid", gridTemplateColumns: "minmax(88px, 0.45fr) 1fr", columnGap: "12px",
      alignItems: "baseline", py: 0.4 }}>
      <MDTypography variant="caption" sx={LABEL}>{label}</MDTypography>
      <MDBox>
        <div>{children}</div>
        {sub ? <MDTypography variant="caption" component="div" sx={SMALL}>{sub}</MDTypography> : null}
      </MDBox>
    </MDBox>
  );
}

/** The 22 centres as a strip: a clear centre in ink, an avoided one struck through and greyed. */
function BandStrip({ bands }) {
  if (!bands || !Array.isArray(bands.centres_hz)) return <span style={SMALL}>—</span>;
  const avoid = new Set((bands.avoid_hz || []).map((v) => Number(v)));
  return (
    <MDBox sx={{ display: "flex", flexWrap: "wrap", gap: "4px 6px", alignItems: "baseline" }}>
      {bands.centres_hz.map((c) => {
        const x = Number(c);
        const out = avoid.has(x);
        const reason = out ? (bands.avoid_reasons || {})[String(x)] || "" : "clear";
        return (
          <span key={x} title={`${x} Hz: ${reason}`}
            style={{ fontFamily: PAL.mono, fontSize: TYPE.num, whiteSpace: "nowrap",
              color: out ? "#9A9A9A" : "#1A1A1A", textDecoration: out ? "line-through" : "none" }}>
            {x}
          </span>
        );
      })}
      <span style={{ ...SMALL, marginLeft: 6 }}>
        {`Hz · ${bands.n_clear ?? "—"} clear, ${bands.n_avoid ?? "—"} struck`}
      </span>
    </MDBox>
  );
}

function SideColumn({ side, plan }) {
  if (!plan) {
    return (
      <MDBox>
        <MDTypography variant="h6" sx={{ fontSize: TYPE.section }}>{side}</MDTypography>
        <MDTypography variant="caption" sx={SMALL}>no plan for this side</MDTypography>
      </MDBox>
    );
  }
  const c = plan.sensing_contact;
  const lad = plan.ladder || {};
  const hold = plan.hold || {};
  const src = plan.sources || {};
  const rec = (plan.yield || {}).record_today || {};
  const harm = (plan.bands || {}).harmonics_hz || {};
  const harmonicsText = ["folded_about_250_hz", "half_rate", "quarter_rate", "three_quarters_rate"]
    .map((k) => (num(harm[k]) === null ? null : `${num(harm[k])} Hz`)).filter(Boolean).join(", ");
  return (
    <MDBox>
      <MDTypography variant="h6" sx={{ fontSize: TYPE.section }}>{side}</MDTypography>
      <Row label="rate" sub={plan.rate_lifted ? plan.rate_why : null}>
        <span style={VALUE}>{fmtHz(plan.rate_hz)}</span>
        {plan.rate_lifted && num(plan.rate_in_force_hz) !== null && (
          <span style={{ ...SMALL, marginLeft: 8, color: PAL.warnText }}>
            {`(in force: ${fmtHz(plan.rate_in_force_hz)})`}
          </span>
        )}
      </Row>
      <Row label="pulse width" sub={plan.pulse_width_note || null}>
        <span style={VALUE}>{fmtUs(plan.pulse_width_us)}</span>
      </Row>
      <Row label="ceiling">
        <span style={VALUE}>{fmtMa(plan.ceiling_mA)}</span>
      </Row>
      <Row label="ladder" sub={lad.why || null}>
        <span style={{ ...VALUE_SMALL, whiteSpace: "normal" }}>{lad.compact || "—"}</span>
        {num(lad.n_steps) !== null && (
          <span style={{ ...SMALL, marginLeft: 8 }}>
            {`${lad.n_steps} steps, ${lad.n_distinct_currents} distinct currents`}
          </span>
        )}
      </Row>
      <Row label="hold per step" sub={hold.why || null}>
        <span style={VALUE}>{num(hold.seconds) === null ? "—" : `${num(hold.seconds)} s`}</span>
        {num(hold.usable_pieces_after_margin) !== null && (
          <span style={{ ...SMALL, marginLeft: 8 }}>
            {`${hold.usable_pieces_after_margin} usable ${num(hold.piece_s)} s pieces after the ${num(hold.post_ramp_margin_s)} s margin (${hold.min_pieces_required} needed)`}
          </span>
        )}
      </Row>
      <Row label="record from" sub={c ? (c.ipsilateral_alternative
        ? `${c.note}. The best contact on this side itself: ${contactLabel(c.ipsilateral_alternative)}, ${c.ipsilateral_alternative.n_qualifying ?? "—"} of ${c.ipsilateral_alternative.n_bands ?? "—"} bands both fall with current and rise with pain${c.ipsilateral_alternative.deployable ? "" : " (did not pass the screen)"}`
        : c.note) : plan.sensing_contact_note}>
        {c ? (
          <span>
            <span style={{ ...VALUE, color: c.on_other_side ? PAL.warnText : VALUE.color }}>{contactLabel(c)}</span>
            {num(c.n_qualifying) !== null && (
              <span style={{ ...SMALL, marginLeft: 8 }}>
                {`${c.n_qualifying} of ${num(c.n_bands) === null ? "—" : c.n_bands} bands both fall with current and rise with pain at ${fmtHz(c.rate_hz)}${Array.isArray(c.qualifying_centers_hz) && c.qualifying_centers_hz.length ? ` (${c.qualifying_centers_hz.map((v) => Number(v)).join(", ")} Hz)` : ""}${c.deployable ? "" : " · did not pass the screen"}`}
              </span>
            )}
          </span>
        ) : <span style={{ ...VALUE, color: PAL.neutral }}>—</span>}
      </Row>
      <Row label="analyse at" sub={harmonicsText ? `the stimulator shows up at ${harmonicsText}; a centre within ±${num((plan.bands || {}).half_width_hz) ?? "—"} Hz of one is struck` : null}>
        <BandStrip bands={plan.bands} />
      </Row>
      <MDBox mt={0.6}>
        <MDTypography variant="caption" sx={LABEL}>during the session</MDTypography>
        <MDBox component="ul" sx={{ m: 0, mt: 0.3, pl: 2.2 }}>
          {(plan.conditions || []).map((t, i) => (
            <li key={i} style={{ fontSize: TYPE.body, lineHeight: 1.35 }}>{t}</li>
          ))}
        </MDBox>
      </MDBox>
      <MDTypography variant="caption" component="div" sx={{ ...SMALL, mt: 0.8 }}>
        {`today: ${rec.note || "—"}`}
      </MDTypography>
      <Fold show="Why this design" hide="Hide" mt={0.6}>
        <MDBox component="dl" sx={{ m: 0, "& dt": { ...HEAD, mt: 0.6 }, "& dd": { m: 0, fontSize: TYPE.small, lineHeight: 1.35, color: "#3E3E3E" } }}>
          <dt>rate</dt><dd>{plan.rate_why} — {src.rate_hz}</dd>
          <dt>pulse width</dt><dd>{src.pulse_width_us}</dd>
          <dt>ceiling</dt><dd>{src.ceiling_mA}</dd>
          <dt>ladder</dt><dd>{src.ladder}</dd>
          <dt>hold per step</dt><dd>{src.hold}</dd>
          <dt>sensing contact</dt><dd>{src.sensing_contact}</dd>
          <dt>band centres</dt><dd>{(plan.bands || {}).why} — {src.bands}</dd>
          <dt>what the record holds today</dt><dd>{src["yield.record_today"]}</dd>
          <dt>the margin</dt><dd>{src["yield.margin"]}</dd>
          <dt>the conditions</dt><dd>{src.conditions}</dd>
        </MDBox>
      </Fold>
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
    <MDBox>
      <MDTypography variant="h6" sx={{ fontSize: TYPE.section }}>{`${p.side}: stimulate ${st.contacts_short || "—"}`}</MDTypography>
      <MDTypography variant="caption" component="div" sx={{ fontSize: TYPE.body, lineHeight: 1.4, mt: 0.4 }}>
        {p.purpose}
      </MDTypography>
      <Row label="stimulate on" sub={sp.why ? `${sp.display_short || sp.channel}: ${sp.why}` : null}>
        <span style={VALUE}>{st.contacts_short || "—"}</span>
        {st.differs_from_in_force && (
          <span style={{ ...SMALL, marginLeft: 8, color: PAL.warnText }}>
            {`(in force today: rings ${(st.in_force_rings || []).join(", ") || "none"})`}
          </span>
        )}
      </Row>
      <Row label="record from" sub={num(c.n_qualifying) !== null
        ? `${c.n_qualifying} of ${num(c.n_bands) ?? "—"} bands rise with pain on this pair at ${fmtHz(c.rate_hz)}; ${num(c.n_responding) ?? 0} fall with current (none can, until this configuration has carried current)`
        : null}>
        <span style={VALUE}>{sp.display_short || sp.channel || "—"}</span>
      </Row>
      <Row label="rate" sub={src.rate_hz || null}>
        <span style={VALUE}>{fmtHz(p.rate_hz)}</span>
        {num(p.rate_in_force_hz) !== null && num(p.rate_in_force_hz) !== num(p.rate_hz) && (
          <span style={{ ...SMALL, marginLeft: 8, color: PAL.warnText }}>{`(in force today: ${fmtHz(p.rate_in_force_hz)})`}</span>
        )}
      </Row>
      <Row label="pulse width"><span style={VALUE}>{fmtUs(p.pulse_width_us)}</span></Row>
      <Row label="ceiling"><span style={VALUE}>{fmtMa(p.ceiling_mA)}</span></Row>
      <Row label="watch" sub={bands.watch_why || null}>
        <span style={VALUE_SMALL}>{watch ? `${watch} Hz` : "—"}</span>
      </Row>
      <Row label="the record today" sub={fe.why || null}>
        <span style={{ ...SMALL, color: fe.ever_powered === false ? PAL.warnText : "#1A1A1A" }}>{fe.sentence || "—"}</span>
      </Row>
      <Row label="stop rule"><span style={{ fontSize: TYPE.body }}>{fe.stop_rule || "—"}</span></Row>
      <Row label="ladder (part A)" sub={lad.why || null}>
        <span style={{ ...VALUE_SMALL, whiteSpace: "normal" }}>{lad.compact || "—"}</span>
        {num(lad.n_steps) !== null && (
          <span style={{ ...SMALL, marginLeft: 8 }}>{`${lad.n_steps} steps, ${lad.n_distinct_currents} distinct currents`}</span>
        )}
      </Row>
      <Row label="holds (part B)" sub={holds.why || null}>
        <span style={{ ...VALUE_SMALL, whiteSpace: "normal" }}>
          {(holds.holds || []).length
            ? `${holds.holds.map((h) => h.state).join(" / ")}: ${holds.holds.map((h) => fmtMa(h.current_mA)).join(", ")}, ${num(holds.minutes_each)} min each, a rating every ${num(holds.rating_every_minutes)} min, the patient blind to the current`
            : "—"}
        </span>
      </Row>
      <Row label="the other side">
        <span style={{ fontSize: TYPE.body }}>{`${other} side held at ${fmtMa(p.held_other_side && p.held_other_side.current_mA)}`}</span>
      </Row>
      <Row label="time">
        <span style={{ fontSize: TYPE.body }}>{num((p.session_time || {}).total_minutes) != null ? `~${Math.round(num(p.session_time.total_minutes))} min on its own (${(p.session_time || {}).why || ""})` : "—"}</span>
      </Row>
      <MDBox mt={0.6}>
        <MDTypography variant="caption" sx={LABEL}>during the session</MDTypography>
        <MDBox component="ul" sx={{ m: 0, mt: 0.3, pl: 2.2 }}>
          {(p.conditions || []).map((t, i) => (
            <li key={i} style={{ fontSize: TYPE.body, lineHeight: 1.35 }}>{t}</li>
          ))}
        </MDBox>
      </MDBox>
      <Fold show="Why this design" hide="Hide" mt={0.6}>
        <MDBox component="dl" sx={{ m: 0, "& dt": { ...HEAD, mt: 0.6 }, "& dd": { m: 0, fontSize: TYPE.small, lineHeight: 1.35, color: "#3E3E3E" } }}>
          {Object.entries(src).map(([k, v]) => (<React.Fragment key={k}><dt>{k.replace(/_/g, " ")}</dt><dd>{v}</dd></React.Fragment>))}
        </MDBox>
      </Fold>
    </MDBox>
  );
}

export default function TitrationSessionCard({ plan, participantUid }) {
  const [sessionDate, setSessionDate] = useState(nextWednesdayISO);
  // status: "idle" | "working" | "error" | "xlsx" | "drive"
  const [exportState, setExportState] = useState({ status: "idle" });

  const handleExport = async () => {
    if (!participantUid || exportState.status === "working") return;
    setExportState({ status: "working" });
    try {
      const response = await SessionController.query(
        "/api/exportTitrationSheet",
        { ParticipantId: participantUid, VisitDate: sessionDate },
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
  const marginLine = (() => {
    if (!plan.available) return plan.reason || "the plan could not be built";
    const need = num(margin.min_settled_settings);
    if (need === null) return "whether the 20 s post-ramp margin can be switched on could not be judged (no per-run table is stored)";
    if (margin.available) {
      return `A run with at least ${need} settled settings exists (${margin.run} on ${margin.sensing_contact}: ${margin.max_settled_settings_in_one_run}), so the 20 s post-ramp margin ${margin.switch_on ? "is switched on" : "can be switched on; it is off today"}.`;
    }
    const most = num(margin.max_settled_settings_in_one_run);
    return `No run in the record holds the ${need} settled settings the 20 s post-ramp margin needs${most === null ? "" : ` (the most in any one run is ${most}, ${margin.run} on ${margin.sensing_contact})`}; the margin stays off until this session is recorded, and its rising leg alone gives ${num((left || right || {}).yield ? (left || right).yield.distinct_currents_up_leg : null) ?? "—"}.`;
  })();

  const sheetRows = Array.isArray(plan.sheet_rows) ? plan.sheet_rows : [];
  const sheetColumns = Array.isArray(plan.sheet_columns) ? plan.sheet_columns : [];
  const leftRows = sheetRows.filter((r) => r.block === "left_ladder");
  const rightRows = sheetRows.filter((r) => r.block === "right_ladder");
  const jointRows = sheetRows.filter((r) => r.block === "joint_corners");
  const jc = plan.joint_corners || {};
  const proposed = plan.proposed || {};
  const proposedSides = Object.keys(proposed).filter((k) => proposed[k]);

  return (
    <Card>
      <MDBox p={2}>
        <MDBox display="flex" justifyContent="space-between" alignItems="flex-start" flexWrap="wrap" gap={1.5}>
          <MDBox display="flex" alignItems="baseline" gap={1} flexWrap="wrap">
            <MDTypography variant="h6" sx={{ fontSize: TYPE.section }}>{TITRATION_CARD_TITLE}</MDTypography>
            <MDTypography variant="caption" sx={SMALL}>
              {`one rate, 0 mA to the ceiling in ${num(plan.step_mA) ?? 0.5} mA steps, up and then down, ${num(plan.hold_s) ?? 60} s a step, streaming on`}
            </MDTypography>
          </MDBox>
          <MDBox display="flex" alignItems="center" gap={1}>
            <TextField type="date" size="small" value={sessionDate}
              onChange={(e) => { setSessionDate(e.target.value); setExportState({ status: "idle" }); }}
              inputProps={{ style: { fontSize: TYPE.small, fontFamily: PAL.mono, padding: "6px 8px" } }} />
            {exportState.status === "drive" ? (
              <MDBox display="flex" alignItems="center" gap={1}>
                <MDTypography component="a" href={exportState.url} target="_blank" rel="noreferrer"
                  variant="caption" sx={{ fontSize: TYPE.small, color: PAL.pass, whiteSpace: "nowrap" }}>
                  Open in Google Sheets
                </MDTypography>
                <Button variant="text" size="small" onClick={handleExport}
                  disabled={!participantUid}
                  sx={{ fontSize: TYPE.small, textTransform: "none", whiteSpace: "nowrap" }}>
                  re-export
                </Button>
              </MDBox>
            ) : (
              <Tooltip title={participantUid ? "copies the clinic-sheet template and writes this "
                + "session's rows into it" : "no participant is selected"}>
                <span>
                  <Button variant="outlined" size="small" onClick={handleExport}
                    disabled={!participantUid || exportState.status === "working"}
                    sx={{ fontSize: TYPE.small, textTransform: "none", whiteSpace: "nowrap" }}>
                    {exportState.status === "working" ? "Making sheet…" : "Make Google sheet"}
                  </Button>
                </span>
              </Tooltip>
            )}
          </MDBox>
        </MDBox>

        {exportState.status === "error" && (
          <MDTypography variant="caption" component="div"
            sx={{ ...SMALL, mt: 0.5, color: PAL.warnText }}>
            {`could not make the sheet: ${exportState.message}`}
          </MDTypography>
        )}
        {exportState.status === "drive" && (
          <MDTypography variant="caption" component="div" sx={{ ...SMALL, mt: 0.5 }}>
            {`${exportState.overwrote ? "Overwrote" : "Wrote"} "${exportState.name}" with `
              + `${exportState.nRows} rows. Re-export overwrites this same file rather than `
              + "making a new copy."}
          </MDTypography>
        )}
        {exportState.status === "xlsx" && (
          <MDTypography variant="caption" component="div" sx={{ ...SMALL, mt: 0.5 }}>
            {`Downloaded ${exportState.name}. ${SHEET_EXPORT_SETUP_NOTE}`}
          </MDTypography>
        )}

        {!plan.available ? (
          <MDTypography variant="caption" component="div" sx={{ ...SMALL, mt: 1, color: PAL.warnText }}>
            {plan.reason || "the plan could not be built"}
          </MDTypography>
        ) : (
          <>
            <SessionHeaderStrip plan={plan} />

            <MDBox mt={1.5} sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", md: "1fr 1fr" }, columnGap: "28px", rowGap: "16px" }}>
              <SideColumn side="Left" plan={left} />
              <SideColumn side="Right" plan={right} />
            </MDBox>

            {proposedSides.length > 0 && (
              <MDBox mt={1.5} sx={{ border: `2px solid ${PAL.accentBorder}`, borderRadius: 2, p: 1.5 }}>
                <MDTypography variant="h6" sx={{ fontSize: TYPE.section }}>{EXPLORATORY_TITLE}</MDTypography>
                <MDTypography variant="caption" component="div" sx={{ ...SMALL, mb: 0.5 }}>
                  {"The readiness screen's best sensing pair on this side needs stimulating contacts other than the ones in force (the device allows a pair only while the contacts it flanks stimulate, decision 217). This ladder runs that configuration: part A for how the band power moves with current, part B for what the current does to pain over minutes. A separate visit, or the end of the ordinary session; its rows are at the end of the sheet."}
                </MDTypography>
                <MDBox sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", md: proposedSides.length > 1 ? "1fr 1fr" : "1fr" }, columnGap: "28px", rowGap: "16px" }}>
                  {proposedSides.map((side) => <ProposedColumn key={side} p={proposed[side]} />)}
                </MDBox>
              </MDBox>
            )}

            <MDBox mt={1.5} sx={{ borderTop: `1px solid ${PAL.neutralBorder}`, pt: 1 }}>
              <MDTypography variant="caption" component="div" fontWeight="medium" sx={{ fontSize: TYPE.num }}>
                The clinic sheet
              </MDTypography>
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
              {plan.sheet_source && (
                <MDTypography variant="caption" component="div" color="text" sx={{ ...SMALL, mt: 1 }}>
                  {`sheet template: ${plan.sheet_source}`}
                </MDTypography>
              )}
            </MDBox>
          </>
        )}
        {plan.available && (
          <MDBox mt={1.2} sx={{ borderTop: `1px solid ${PAL.neutralBorder}`, pt: 0.8 }}>
            <MDTypography variant="caption" component="div" sx={{ fontSize: TYPE.body, lineHeight: 1.4 }}>
              {[left, right].filter(Boolean).map((p) => (
                <span key={p.side} style={{ display: "block" }}>
                  <b style={NOWRAP}>{p.side}:</b> {(p.yield || {}).sentence || "—"}
                </span>
              ))}
              <span style={{ display: "block", marginTop: 4, color: margin.available ? PAL.pass : PAL.warnText }}>{marginLine}</span>
            </MDTypography>
            <MDTypography variant="caption" component="div" sx={{ ...SMALL, mt: 0.5 }}>
              {`protocol: ${plan.protocol_source || "—"}`}
            </MDTypography>
          </MDBox>
        )}
      </MDBox>
    </Card>
  );
}
