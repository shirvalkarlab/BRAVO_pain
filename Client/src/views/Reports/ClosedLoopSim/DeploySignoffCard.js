/**
 * The printable sign-off record: what the decision card folds under "Details" and prints in full.
 *
 * Until decision 302 this was its own card, "Deploy-to-Percept review", at the foot of the page,
 * with its own verdict box, a box saying where the values to transcribe were, and the Print and
 * Export buttons. The PI (2026-09-26): "Combine the full parameter recommendation with the
 * deployment card to create one simple, streamlined card." The verdict is now the decision card's
 * status line, the values are the decision card's table, and "Sign and print" is the decision
 * card's button; this file keeps the record itself (`SignoffRecord`, the default export), the
 * print-and-export logic (`useSignoffActions`), the stale-inputs notice and the figure pictures.
 * Every number here is one the page already shows elsewhere, gathered for the signed sheet.
 */
import { useEffect, useState } from "react";
import { Grid, Icon } from "@mui/material";
import MDBox from "components/MDBox";
import MDTypography from "components/MDTypography";

import { captureFigureSnapshots } from "./figureSnapshots";
import PAL from "./palette";
import ProvisionalNote from "./ProvisionalNote";
import { gridSettingsLine } from "./BandSweepGridPanel";
import { painScoreLabel } from "views/Reports/painScores";

const fmt = (v, d = 2) => (v == null || !Number.isFinite(Number(v)) ? "—" : Number(v).toFixed(d));

function GateRow({ gate }) {
  // Tri-state gate (audit C8): pass / fail / indeterminate. Each state carries BOTH a CVD-safe color
  // (bluish-green / vermillion / gray — never green-vs-red alone) AND a distinct icon, so the verdict
  // is never color-only. "indeterminate" (the stim-stability LRT did not run) is a NEUTRAL help icon,
  // not a check — absence of evidence must never look like a pass. A NECESSARY gate (a hard
  // prerequisite to program at all) is tagged so a clinician sees which failures are blocking.
  const state = gate.state || (gate.pass ? "pass" : "fail");
  const STYLE = {
    pass: { color: PAL.passText, icon: "check_circle" },
    fail: { color: PAL.failText, icon: "cancel" },
    indeterminate: { color: PAL.indeterminate, icon: "help" },
  };
  const s = STYLE[state] || STYLE.fail;
  return (
    <MDBox display="flex" alignItems="flex-start" py={0.4}
      sx={{ borderBottom: "1px solid #f0f0f0" }}>
      <Icon sx={{ fontSize: "18px !important", color: s.color, mr: 1, mt: 0.1 }}>
        {s.icon}
      </Icon>
      <MDBox flex={1}>
        <MDTypography variant="caption" sx={{ fontSize: 11.5, fontWeight: "bold", color: s.color }}>
          {gate.label}
          {gate.necessary ? (
            <span style={{ fontSize: 11, fontWeight: "bold", color: PAL.neutral,
              marginLeft: 6, verticalAlign: "middle", letterSpacing: "0.04em" }}>
              REQUIRED
            </span>
          ) : null}
          {state === "indeterminate" ? (
            <span style={{ fontSize: 11, fontWeight: "bold", color: PAL.indeterminate,
              marginLeft: 6, verticalAlign: "middle", letterSpacing: "0.04em" }}>
              NOT TESTED
            </span>
          ) : null}
        </MDTypography>
        <MDTypography variant="caption" display="block" sx={{ fontSize: 11, color: "#5E5E5E" }}>
          {gate.detail}
        </MDTypography>
      </MDBox>
    </MDBox>
  );
}

/** The module's own verdict string, so the signed sheet carries the same words as the page. */
function EvidenceVerdictLine({ rep }) {
  const verdict = rep && rep.available ? rep.verdict : null;
  if (!verdict) return null;
  return (
    <MDTypography variant="caption" display="block" sx={{ fontSize: 11, color: "#2A2A2A", mt: 0.5 }}>
      {`Evidence verdict from the deployment report: ${verdict}.`}
    </MDTypography>
  );
}

/**
 * The deployment report's caveats, ranked, each naming the card it is about.
 *
 * WHY AN EMPTY LIST STILL PRINTS A SENTENCE. A heading with nothing under it reads as a card that
 * failed to load. "No caveats were assembled for this report" is a different statement from "this
 * report has nothing to qualify", and saying which is which on a signed sheet is the point.
 */
const CAVEAT_INK = { high: PAL.failText, medium: PAL.warnText, low: "#5E5E5E" };

function ReportCaveats({ caveats }) {
  const rows = Array.isArray(caveats) ? caveats : null;
  if (!rows || rows.length === 0) {
    return (
      <MDTypography variant="caption" display="block" sx={{ fontSize: 11, color: "#5E5E5E", mt: 0.4 }}>
        {rows
          ? "This report lists no caveats of its own. Every number it prints carries an "
            + "uncertainty interval, and no warning is outstanding."
          : "No caveats reached this sheet from the deployment report. That is a missing list, "
            + "not a report with nothing to qualify."}
      </MDTypography>
    );
  }
  return (
    <MDBox mt={0.5}>
      {rows.map((c, i) => (
        <MDBox key={`cav${i}`} display="flex" alignItems="flex-start" mb={0.45}>
          <MDTypography variant="caption" sx={{ fontSize: 11, fontWeight: "bold",
            letterSpacing: 0.3, color: CAVEAT_INK[c.severity] || PAL.neutral, mt: 0.15,
            minWidth: "44px" }}>
            {String(c.severity || "").toUpperCase()}
          </MDTypography>
          <MDTypography variant="caption" sx={{ fontSize: 11, color: "#3A3A3A", flex: "1 1 auto" }}>
            {c.text}
            {c.card ? (
              <i style={{ color: "#5E5E5E" }}>{`  (${c.card})`}</i>
            ) : null}
          </MDTypography>
        </MDBox>
      ))}
    </MDBox>
  );
}

function KV({ k, v }) {
  return (
    <MDBox display="flex" justifyContent="space-between" py={0.25}>
      <MDTypography variant="caption" sx={{ fontSize: 11.5, color: "#5E5E5E" }}>{k}</MDTypography>
      <MDTypography variant="caption" sx={{ fontSize: 11.5, fontWeight: "bold", textAlign: "right" }}>{v}</MDTypography>
    </MDBox>
  );
}

/**
 * THE BAND SIGNED FOR, read from the chosen band itself (panel D item 8, with the PI's ruling 8;
 * 2026-09-23). The "DEVICE TARGET" block beside it comes from the deployment summary, whose pain
 * score and split are rebuilt from the band's label, and a band chosen on the grid carries an empty
 * label; so this block is the one that says which band was chosen, when, by whom, whether the
 * server holds that record, and which grid it was picked from.
 */
/** Which ratings the summary used (the PI, 2026-09-24), in words: REDCap alone, or with the clinic
 *  sheets and how many, or the sheets asked for and why none could be added. */
export function ratingsUsedText(block) {
  const b = block || {};
  if (!b.included) return "REDCap reports only (clinic-sheet ratings off)";
  if (b.reason) return `REDCap reports only: the clinic sheets were asked for, but ${b.reason}`;
  return `REDCap reports plus ${b.n_added} clinic-sheet rating${b.n_added === 1 ? "" : "s"}`;
}

/** Which pain score every band-to-pain reading on the page used (the PI, 2026-09-25 night): the
 *  deployment report's own record of it, beside the summary's; if the two ever differ the sheet
 *  says so in capitals rather than printing one of them. */
export function painScoreUsedText(reportPain, summaryMetric) {
  if (!reportPain || !reportPain.key) return "not recorded on the deployment report";
  if (summaryMetric && summaryMetric !== reportPain.key) {
    return `NOT THE SAME: the evidence and stability readings used ${painScoreLabel(reportPain.key)}, `
      + `the deployment summary ${painScoreLabel(summaryMetric)}`;
  }
  const label = reportPain.label || painScoreLabel(reportPain.key);
  const why = reportPain.fell_back_to_nrs && reportPain.reason ? ` (${reportPain.reason})` : "";
  return `${label}, for every band-to-pain reading on this page${why}`;
}

export function ChosenBandBlock({ bandCandidate, chosenBand, bandRecord }) {
  const bc = bandCandidate || {};
  if (!bc.contact) return null;
  const name = `${bc.contact_label || bc.contact} at ${fmt(bc.center_freq_hz, 1)} Hz`;
  const when = chosenBand && chosenBand.committed_at
    ? new Date(chosenBand.committed_at).toLocaleString() : null;
  const who = bandRecord && bandRecord.chosenBy;
  const held = !bandRecord ? "where it is held has not been checked yet"
    : bandRecord.where === "server" ? "recorded on the server"
      : `held in this browser only (${bandRecord.reason || "the server did not record it"})`;
  const grid = gridSettingsLine(bc.grid_settings);
  return (
    <MDBox mt={1.2}>
      <MDTypography variant="caption" sx={{ fontSize: 11, fontWeight: "bold", color: "#5E5E5E" }}>
        THE BAND SIGNED FOR
      </MDTypography>
      <KV k="Band" v={name} />
      <KV k="Chosen" v={bandRecord && bandRecord.source === "browser_storage"
        ? `${when || "time not recorded"}, chosen in a browser before the server kept a record; `
          + `carried over to the server${who ? ` by ${who}` : ""}`
        : `${when || "time not recorded"}${who ? `, by ${who}` : ""}; ${held}`} />
      <KV k="Picked from the grid" v={grid || "not recorded with this band (chosen before "
        + "2026-09-23, or loaded from a file)"} />
    </MDBox>
  );
}

/** P-04, 2026-09-25: the mixed-effects check leaves out the first weeks of the whole record, counted
 * from the first recorded sample (near implant), NOT from each setting change and not from the first
 * usable rating (`Biomarkers.routines.analytics.VALIDATION_EXCLUDE_FIRST_WEEKS`'s own comment).
 * Printed only once the backend sends the count, so an older cached response prints nothing rather
 * than a zero. Its own component because the card is large enough that one more branch inside it
 * trips the installed hooks lint rule's path counting. */
function BurnInNote({ ev }) {
  if (!ev || !ev.excluded_first_weeks) return null;
  const weeks = ev.excluded_first_weeks;
  const n = ev.n_excluded_burn_in != null ? ev.n_excluded_burn_in : 0;
  return (
    <MDTypography variant="caption" display="block" sx={{ fontSize: 11, color: "#5E5E5E", mt: 0.3 }}>
      {`The check above leaves out the first ${weeks} week${weeks === 1 ? "" : "s"} of the whole record, `
        + "counted from the first recorded sample (not from each setting change), because the signal is "
        + `still settling after implant (impedance and recovery from surgery) (${n} `
        + `rating${n === 1 ? "" : "s"} excluded).`}
    </MDTypography>
  );
}

/** The PI, 2026-09-25 (answer 6): the area under the curve above, read again with the stimulation
 * current in force at each sample taken out of the band power (Biomarkers
 * `routines/deployment_current.py`), printed on the line under the plain number. Descriptive only:
 * the plain number sets every gate. A refusal prints its reason, never a number; an older response
 * that does not carry the reading prints nothing. Its own component for the same lint reason as
 * BurnInNote. */
function CurrentRemovedAuc({ ev }) {
  const a = ev && ev.auc_current_removed;
  if (!a) return null;
  const k = "Deployment AUC — with the stimulation current taken out";
  const note = { fontSize: 11, color: "#5E5E5E", mt: 0.3 };
  if (!a.available || a.auc == null) {
    return (
      <>
        <KV k={k} v="not computed" />
        <MDTypography variant="caption" display="block" sx={note}>
          {`Not computed: ${a.why || "no reason was recorded"}. That is an absent measurement, not a finding.`}
        </MDTypography>
      </>
    );
  }
  const same = a.plain_on_same_samples;
  const n0 = a.n_samples_without_current || 0;
  return (
    <>
      <KV k={k} v={`${fmt(a.auc)} (${fmt(a.auc_low)}–${fmt(a.auc_high)})`} />
      <MDTypography variant="caption" display="block" sx={note}>
        {`The same samples and the same high-or-low split, with the ${a.hemisphere || ""} current in `
          + `force at each sample taken out of the band power as ${a.shape_words || "a straight line"}, `
          + "in the same direction as the plain number (below 0.5 would mean the direction reversed). "
          + (same && same.auc != null
            ? `On the ${a.n_spectral_samples} samples from ${a.n_pain_reports} pain reports it rests on, `
              + `the plain reading on those same samples is ${fmt(same.auc)} (${fmt(same.auc_low)}–`
              + `${fmt(same.auc_high)}). `
            : "")
          + (n0 > 0 ? `${n0} sample${n0 === 1 ? "" : "s"} recorded before the first dated setting have no current. ` : "")
          + "Descriptive only: the plain reading above sets every gate and the verdict."}
      </MDTypography>
    </>
  );
}

const RULE_LABEL = { youden: "Balanced (Youden J)", f1: "Favor detection (F1)", cost: "Cost-weighted" };

/**
 * Print and export for the signed record. Pictures of the page's figures are taken in the browser
 * when Print or Export is pressed (audit item [49]), so the sheet shows the operating point the
 * reader chose; `printPending` makes capture and print two steps, because window.print() blocks
 * and the pictures must be in the document before it is called.
 *
 * STALENESS REACHES THE RECORD. The summary's key includes the cut-point, so a new operating point
 * marks the page stale rather than refetching. A printed or exported record outlives the screen and
 * its amber Recompute bar, so the record says so at its own head and in the exported file.
 */
export function useSignoffActions({ participantUid, bandCandidate, summary, cutpoint, chosenBand,
                                    bandRecord }) {
  const data = summary && summary.data;
  const inputsStale = !!(summary && summary.stale);
  const staleWhy = (summary && summary.staleReasons) || [];
  const computedAt = (summary && summary.computedAt) || null;
  const bc = bandCandidate || {};
  const opProvenance = cutpoint ? {
    rule: cutpoint.rule || null,
    rule_label: RULE_LABEL[cutpoint.rule] || cutpoint.rule || null,
    sensitivity: cutpoint.sensitivity ?? null,
    specificity: cutpoint.specificity ?? null,
    degenerate: !!cutpoint.degenerate,
  } : null;

  const [snapshots, setSnapshots] = useState(null);
  const [capturing, setCapturing] = useState(false);
  const [printPending, setPrintPending] = useState(false);

  const takeSnapshots = async () => {
    setCapturing(true);
    try {
      const snap = await captureFigureSnapshots();
      setSnapshots(snap);
      return snap;
    } catch (e) {
      const snap = { figures: [], missing: [], captured_at: new Date().toISOString(),
        error: `figures could not be captured (${e && e.message ? e.message : e})` };
      setSnapshots(snap);
      return snap;
    } finally {
      setCapturing(false);
    }
  };

  useEffect(() => {
    if (!printPending || capturing || !snapshots) return;
    setPrintPending(false);
    window.requestAnimationFrame(() => window.print());
  }, [printPending, capturing, snapshots]);

  const printWithFigures = async () => {
    setPrintPending(true);
    await takeSnapshots();
  };

  const exportJson = async () => {
    if (!data) return;
    const snap = await takeSnapshots();
    const blob = new Blob([JSON.stringify({ schema_version: "deploy_signoff_v1",
      generated_at: new Date().toISOString(), operating_point: opProvenance, summary: data,
      chosen_band: { band_candidate: bandCandidate || null,
        committed_at: (chosenBand && chosenBand.committed_at) || null,
        record: bandRecord || null },
      inputs_stale: inputsStale,
      inputs_stale_reasons: inputsStale ? staleWhy : [],
      summary_computed_at: computedAt ? new Date(computedAt).toISOString() : null,
      figures: snap.figures.map((f) => ({ section_id: f.section_id, title: f.title, index: f.index,
        n_in_section: f.n_in_section, width_px: f.width_px, height_px: f.height_px,
        image_data_url: f.image_data_url })),
      figures_missing: snap.missing,
      figures_captured_at: snap.captured_at }, null, 2)],
      { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `DeploySignoff_${participantUid}_${bc.contact}_${bc.center_freq_hz}Hz.json`;
    a.click(); URL.revokeObjectURL(a.href);
  };

  return { hasData: !!data, snapshots, capturing, printWithFigures, exportJson, inputsStale,
    staleWhy, computedAt };
}

/** At the head of the record, on screen and on paper, when the settings changed since. */
export function StaleNotice({ inputsStale, computedAt, staleWhy }) {
  if (!inputsStale) return null;
  return (
    <MDBox className="cl-signoff-stale" mb={1} p={1}
      sx={{ borderRadius: "4px", backgroundColor: PAL.warnFill, border: `1px solid ${PAL.warnText}` }}>
      <MDTypography variant="caption" display="block" sx={{ fontSize: 12, fontWeight: 700, color: PAL.warnText }}>
        {computedAt
          ? `This record describes the analysis of ${new Date(computedAt).toLocaleString()}; the `
            + "settings have changed since. Press Recompute before signing."
          : "The settings have changed since this analysis. Press Recompute before signing."}
      </MDTypography>
      {staleWhy.map((r) => (
        <MDTypography key={r} variant="caption" display="block" sx={{ fontSize: 11.5, color: PAL.warnText }}>
          {r}
        </MDTypography>
      ))}
    </MDBox>
  );
}

/** The pictures taken when Print or Export was pressed, drawn inside the printed card. */
export function SnapshotFigures({ snapshots }) {
  if (!snapshots) return null;
  return (
    <MDBox className="cl-signoff-figures" mt={2} pt={1.5} sx={{ borderTop: "1px solid #e0e0e0" }}>
      <MDTypography variant="caption" sx={{ fontSize: 11.5, fontWeight: "bold", color: "#4A4A4A" }}>
        FIGURES AS DRAWN WHEN THIS RECORD WAS MADE
        {snapshots.captured_at ? `, ${new Date(snapshots.captured_at).toLocaleString()}` : ""}
      </MDTypography>
      {snapshots.error ? (
        <MDTypography variant="caption" display="block" sx={{ fontSize: 11.5, color: PAL.failText }}>
          {snapshots.error}
        </MDTypography>
      ) : null}
      {snapshots.figures.map((f) => (
        <MDBox key={`${f.section_id}-${f.index}`} mt={1} sx={{ pageBreakInside: "avoid" }}>
          <MDTypography variant="caption" display="block" sx={{ fontSize: 11.5, fontWeight: "bold" }}>
            {f.n_in_section > 1 ? `${f.title} (${f.index} of ${f.n_in_section})` : f.title}
          </MDTypography>
          <img src={f.image_data_url} alt={f.title}
            style={{ display: "block", width: f.width_px, maxWidth: "100%", height: "auto",
              border: "1px solid #eee" }} />
        </MDBox>
      ))}
      {snapshots.missing.length ? (
        <MDBox mt={1}>
          <MDTypography variant="caption" display="block" sx={{ fontSize: 11.5, fontWeight: "bold", color: PAL.warnText }}>
            NOT ON THIS RECORD
          </MDTypography>
          {snapshots.missing.map((m) => (
            <MDTypography key={m.section_id + m.reason} variant="caption" display="block"
              sx={{ fontSize: 11.5, color: PAL.warnText }}>
              {`${m.title}: ${m.reason}`}
            </MDTypography>
          ))}
        </MDBox>
      ) : null}
    </MDBox>
  );
}

/**
 * The record itself. No verdict box and no pointer to the values (both are the decision card's
 * own, directly above this fold); the statistical gates stay as the checklist they are, labelled
 * as evidence and not permission (decision 242: one verdict).
 */
function SignoffRecord({ bandCandidate, summary, deploymentReport, chosenBand, bandRecord }) {
  const _rep = deploymentReport && deploymentReport.data ? deploymentReport.data : deploymentReport;
  const { data, loading, err } = summary || { data: null, loading: false, err: null };
  const id = data && data.identity;
  const dc = data && data.device_control;
  const ev = data && data.evidence;
  const pw = data && data.power;
  const fwd = data && data.forward;
  const summaryReady = data
    ? (data.ready_to_program != null ? !!data.ready_to_program : data.n_gates_passed === data.n_gates)
    : false;
  const nIndet = (data && data.n_gates_indeterminate) || 0;

  if (loading) {
    return (
      <MDTypography variant="caption" sx={{ fontStyle: "italic", fontSize: 11.5 }}>
        Assembling the deployment review…
      </MDTypography>
    );
  }
  if (err) {
    return (
      <MDTypography variant="caption" sx={{ fontSize: 11.5, color: PAL.failText }}>
        {`The statistical summary is unavailable: ${err}.`}
      </MDTypography>
    );
  }
  if (!data) return null;
  return (
    <MDBox className="cl-signoff-record">
      <MDTypography variant="caption" display="block" sx={{ fontSize: 11.5, color: "#3A3A3A", mb: 1 }}>
        {`Statistical gates, as evidence and not as permission: ${data.n_gates_passed} of ${data.n_gates} passed`}
        {data.n_necessary != null ? `, of which ${data.n_necessary_passed} of ${data.n_necessary} required` : ""}
        {nIndet ? `, ${nIndet} not settled` : ""}
        {`. Match direction: ${data.match_direction}.`}
        {summaryReady
          ? " The required gates all passed; that is about discrimination, not about the device."
          : " The required gates did not all pass."}
      </MDTypography>

      <Grid container spacing={2}>
        <Grid item xs={12} md={6}>
          <MDTypography variant="caption" sx={{ fontSize: 11.5, fontWeight: "bold", color: "#4A4A4A" }}>
            DEVICE TARGET
          </MDTypography>
          {id ? (
            <>
              <KV k="Contact" v={`${id.contact} (${id.hemisphere || "—"})`} />
              <KV k="Region" v={id.region || "—"} />
              <KV k="Band" v={`${fmt(id.band_lo_hz, 1)}–${fmt(id.band_hi_hz, 1)} Hz`} />
              <KV k="Center (FFT-snapped)" v={`${fmt(id.center_freq_hz, 1)} → ${fmt(id.snapped_center_freq_hz, 2)} Hz`} />
              <KV k="PRO metric / binarization" v={`${id.pro_metric} / ${id.binarization}`} />
              <KV k="Pain ratings used" v={ratingsUsedText(id.clinic_sheet_ratings)} />
              <KV k="Pain score used" v={painScoreUsedText(_rep && _rep.pain_score, id.pro_metric)} />
              <KV k="Polarity / suggested mode" v={`${dc.polarity} / ${dc.suggested_mode || "—"}`} />
            </>
          ) : null}
          <ChosenBandBlock bandCandidate={bandCandidate} chosenBand={chosenBand} bandRecord={bandRecord} />

          {/* The evidence verdict this sheet is signed against, verbatim from the module, with each
              edge's interval and p when it rests on point signs alone (PI rule 2026-09-13). */}
          <MDBox mt={1.2}>
            <EvidenceVerdictLine rep={_rep} />
            <ProvisionalNote deploymentReport={_rep} dense mt={0.5} headline={false} />
          </MDBox>

          {dc && dc.ramp && dc.ramp.available ? (
            <MDBox mt={1.2}>
              <MDTypography variant="caption" sx={{ fontSize: 11.5, fontWeight: "bold",
                color: dc.ramp.posture === "conservative" ? PAL.warnText : PAL.passText }}>
                {`RAMP GUIDANCE, ${String(dc.ramp.posture).toUpperCase()} (advisory)`}
              </MDTypography>
              <MDTypography variant="caption" display="block" color="text" sx={{ fontSize: 11.5, mt: 0.3 }}>
                {dc.ramp.transition_note}
              </MDTypography>
              <MDTypography variant="caption" display="block" color="text" sx={{ fontSize: 11.5, mt: 0.3 }}>
                {`Ramp up: ${dc.ramp.ramp_up_hint}. Ramp down: ${dc.ramp.ramp_down_hint}.`}
              </MDTypography>
              <MDTypography variant="caption" display="block" sx={{ fontSize: 11.5, color: "#5E5E5E", mt: 0.3 }}>
                {dc.ramp.reason}
              </MDTypography>
            </MDBox>
          ) : null}

          <MDBox mt={1.2}>
            <MDTypography variant="caption" sx={{ fontSize: 11.5, fontWeight: "bold", color: "#4A4A4A" }}>
              EVIDENCE
            </MDTypography>
            {ev ? (
              <>
                <KV k="Deployment AUC — in-sample (95% clustered-bootstrap CI)" v={`${fmt(ev.auc)} (${fmt(ev.auc_lo)}–${fmt(ev.auc_hi)})`} />
                <CurrentRemovedAuc ev={ev} />
                {fwd && fwd.available && fwd.held_out_auc != null ? (
                  <KV
                    k={`Deployment AUC — forward held-out (${fwd.n_folds ?? "—"} weekly folds)`}
                    v={
                      <span style={{ color: fwd.beats_chance_forward ? PAL.passText : PAL.warnText, fontWeight: 600 }}>
                        {`${fmt(fwd.held_out_auc)} (${fmt(fwd.held_out_auc_lo)}–${fmt(fwd.held_out_auc_hi)})`}
                        {fwd.beats_chance_forward ? " ✓ clears chance" : " ✗ not validated forward"}
                      </span>
                    }
                  />
                ) : (
                  <KV k="Deployment AUC — forward held-out" v={
                    <span style={{ color: PAL.warnText }}>
                      {fwd && fwd.reason ? `not assessable (${fwd.reason})` : "in-sample only, forward UNCONFIRMED"}
                    </span>
                  } />
                )}
                <KV k="Odds ratio (95% CI)" v={`${fmt(ev.odds_ratio)} (${fmt(ev.or_ci_low)}–${fmt(ev.or_ci_high)})${ev.credible_ci ? " ✓" : ""}`} />
                <KV k="Mixed-effects p" v={ev.p_glmer != null ? ev.p_glmer.toExponential(2) : "—"} />
                <KV k="Matched samples / ratings" v={`${ev.n_matched_samples ?? "—"} / ${ev.n_clusters ?? "—"}`} />
                <BurnInNote ev={ev} />
                {pw && pw.available ? (
                  <KV k="Power (vs AUC 0.5)" v={pw.more_data_needed
                    ? `${fmt(pw.power_current * 100, 0)}% · need ${pw.n_ratings_needed} ratings`
                    : `${fmt(pw.power_current * 100, 0)}% · adequately powered`} />
                ) : null}
              </>
            ) : null}
          </MDBox>
        </Grid>

        <Grid item xs={12} md={6}>
          <MDTypography variant="caption" sx={{ fontSize: 11.5, fontWeight: "bold", color: "#4A4A4A" }}>
            DEPLOYMENT GATES
          </MDTypography>
          <MDBox mb={1.2}>
            {(data.gates || []).map((g) => <GateRow key={g.key} gate={g} />)}
          </MDBox>

          <MDTypography variant="caption" sx={{ fontSize: 11.5, fontWeight: "bold", color: PAL.warnText }}>
            CAVEATS
          </MDTypography>
          {/* The deployment report's own caveats (panel D item 3), ranked, each naming its card;
              then the older statistical endpoint's own, labelled as coming from elsewhere. */}
          <ReportCaveats caveats={_rep && _rep.available ? _rep.caveats : null} />
          {(data.caveats || []).length > 0 ? (
            <MDTypography variant="caption" display="block"
              sx={{ fontSize: 11.5, fontWeight: "bold", color: "#4A4A4A", mt: 0.8 }}>
              FROM THE SEPARATE STATISTICAL SUMMARY
            </MDTypography>
          ) : null}
          <MDBox component="ul" sx={{ pl: 2, mt: 0.5, mb: 0 }}>
            {(data.caveats || []).map((c) => (
              <MDTypography key={c} component="li" variant="caption"
                sx={{ fontSize: 11.5, color: "#4A4A4A", display: "list-item", mb: 0.3 }}>
                {c}
              </MDTypography>
            ))}
          </MDBox>
        </Grid>
      </Grid>
    </MDBox>
  );
}

export { SignoffRecord };
export default SignoffRecord;
