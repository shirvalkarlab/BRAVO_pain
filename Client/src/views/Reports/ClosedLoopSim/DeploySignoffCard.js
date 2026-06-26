/**
 * Phase E: the read-only Deploy-to-Percept sign-off card.
 *
 * One authoritative fetch (/api/queryDeploymentSummary) → a clinician-facing review: device identity,
 * the deployable LSB threshold (big), the gate checklist they sign against, evidence with CI,
 * per-era portability, and the deployment caveats. Printable (window.print) and exportable to JSON
 * for the device-programming record. This is a SUMMARY, not a new analysis — every number here is
 * the same one the Phase B–D panels show, gathered in one place.
 */
import { Card, Grid, Icon } from "@mui/material";
import MDBox from "components/MDBox";
import MDTypography from "components/MDTypography";
import MDButton from "components/MDButton";

import useDeploymentSummary from "./useDeploymentSummary";
import PAL from "./palette";

const fmt = (v, d = 2) => (v == null || !Number.isFinite(Number(v)) ? "—" : Number(v).toFixed(d));

function GateRow({ gate }) {
  // Tri-state gate (audit C8): pass / fail / indeterminate. Each state carries BOTH a CVD-safe color
  // (bluish-green / vermillion / gray — never green-vs-red alone) AND a distinct icon, so the verdict
  // is never color-only. "indeterminate" (the stim-stability LRT did not run) is a NEUTRAL help icon,
  // not a check — absence of evidence must never look like a pass. A NECESSARY gate (a hard
  // prerequisite to program at all) is tagged so a clinician sees which failures are blocking.
  const state = gate.state || (gate.pass ? "pass" : "fail");
  const STYLE = {
    pass: { color: PAL.pass, icon: "check_circle" },
    fail: { color: PAL.fail, icon: "cancel" },
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
            <span style={{ fontSize: 8.5, fontWeight: "bold", color: PAL.neutral,
              marginLeft: 6, verticalAlign: "middle", letterSpacing: "0.04em" }}>
              REQUIRED
            </span>
          ) : null}
          {state === "indeterminate" ? (
            <span style={{ fontSize: 8.5, fontWeight: "bold", color: PAL.indeterminate,
              marginLeft: 6, verticalAlign: "middle", letterSpacing: "0.04em" }}>
              NOT TESTED
            </span>
          ) : null}
        </MDTypography>
        <MDTypography variant="caption" display="block" sx={{ fontSize: 10, color: "#777" }}>
          {gate.detail}
        </MDTypography>
      </MDBox>
    </MDBox>
  );
}

function KV({ k, v }) {
  return (
    <MDBox display="flex" justifyContent="space-between" py={0.25}>
      <MDTypography variant="caption" sx={{ fontSize: 10.5, color: "#999" }}>{k}</MDTypography>
      <MDTypography variant="caption" sx={{ fontSize: 10.5, fontWeight: "bold", textAlign: "right" }}>{v}</MDTypography>
    </MDBox>
  );
}

function DeploySignoffCard({ participantUid, bandCandidate, requestParams, cutpoint, summary }) {
  const bc = bandCandidate || {};
  const channelRaw = bc.contact;
  const centerHz = bc.center_freq_hz;
  const bandWidthHz = bc.bandwidth_hz || 5.0;
  const cutThr = cutpoint ? cutpoint.threshold : null;
  const matchDir = cutpoint ? cutpoint.matchDir : "prior";

  // Prefer the SHARED summary fetch lifted to the parent (one /queryDeploymentSummary call feeds both
  // this card and the top verdict strip — glmer runs through single-threaded embedded R per worker, so
  // a duplicate concurrent call starved the pool and dropped sibling requests). Fall back to a local
  // fetch only if the prop isn't supplied (standalone use), so the two can never disagree.
  const ownSummary = useDeploymentSummary({
    participantUid, channel: channelRaw, centerHz, bandWidthHz, matchDir, cutThr, requestParams,
    enabled: !summary,
  });
  const { data, loading, err } = summary || ownSummary;
  // Operating-point provenance for the auditable device-programming record: WHICH rule chose the
  // cut-point and at what sensitivity/specificity. Without this two clinicians could program the same
  // patient at different operating points with identical-looking sign-off sheets.
  const RULE_LABEL = { youden: "Balanced (Youden J)", f1: "Favor detection (F1)", cost: "Cost-weighted" };
  const opProvenance = cutpoint ? {
    rule: cutpoint.rule || null,
    rule_label: RULE_LABEL[cutpoint.rule] || cutpoint.rule || null,
    sensitivity: cutpoint.sensitivity ?? null,
    specificity: cutpoint.specificity ?? null,
    degenerate: !!cutpoint.degenerate,
  } : null;

  const exportJson = () => {
    if (!data) return;
    const blob = new Blob([JSON.stringify({ schema_version: "deploy_signoff_v1",
      generated_at: new Date().toISOString(), operating_point: opProvenance, summary: data }, null, 2)],
      { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `DeploySignoff_${participantUid}_${channelRaw}_${centerHz}Hz.json`;
    a.click(); URL.revokeObjectURL(a.href);
  };

  const id = data && data.identity;
  const dc = data && data.device_control;
  const ev = data && data.evidence;
  const th = data && data.threshold;
  const pw = data && data.power;
  const fwd = data && data.forward;
  // Audit C8: "ready to program" keys on the NECESSARY gates alone (a hard prerequisite failing
  // blocks deployment even at a high passed-count), NOT on n_gates_passed === n_gates. Fall back to
  // the count only for older payloads that predate ready_to_program.
  const ready = data
    ? (data.ready_to_program != null ? !!data.ready_to_program : data.n_gates_passed === data.n_gates)
    : false;
  const nIndet = (data && data.n_gates_indeterminate) || 0;

  return (
    <Card className="cl-signoff-card"
      sx={{ width: "100%", border: data ? `2px solid ${ready ? PAL.pass : PAL.warn}` : undefined }}>
      <MDBox p={2.5}>
        <MDBox display="flex" justifyContent="space-between" alignItems="center" mb={1}>
          <MDTypography variant="h5" sx={{ fontSize: 18 }}>Deploy-to-Percept review</MDTypography>
          {data ? (
            <MDBox className="cl-signoff-actions">
              <MDButton size="small" variant="outlined" color="dark" onClick={() => window.print()} sx={{ mr: 1 }}>
                Print
              </MDButton>
              <MDButton size="small" variant="gradient" color="info" onClick={exportJson}>
                Export JSON
              </MDButton>
            </MDBox>
          ) : null}
        </MDBox>

        {loading ? (
          <MDTypography variant="caption" sx={{ fontStyle: "italic", fontSize: 11 }}>
            Assembling the deployment review…
          </MDTypography>
        ) : err ? (
          <MDTypography variant="caption" sx={{ fontSize: 11, color: PAL.fail }}>{`Unavailable: ${err}.`}</MDTypography>
        ) : data ? (
          <>
            {/* headline verdict — driven by the NECESSARY gates (audit C8), not the passed-count */}
            <MDBox p={1} mb={1.5} sx={{ borderRadius: "6px",
              backgroundColor: ready ? PAL.passFill : PAL.warnFill }}>
              <MDTypography variant="h6" sx={{ fontSize: 14, color: ready ? PAL.pass : PAL.warnText }}>
                {ready
                  ? "Ready to program — all required gates passed"
                  : (data.n_necessary != null
                    ? `Not ready — ${data.n_necessary_passed} of ${data.n_necessary} required gates passed`
                    : "Not ready — review caveats before programming")}
              </MDTypography>
              <MDTypography variant="caption" display="block" sx={{ fontSize: 10.5, color: "#666" }}>
                {`${data.n_gates_passed} of ${data.n_gates} total gates passed`}
                {nIndet ? ` · ${nIndet} not tested` : ""}
                {` · verdict: ${data.verdict} · match direction: ${data.match_direction}`}
              </MDTypography>
            </MDBox>

            <Grid container spacing={2}>
              {/* LEFT: identity + threshold + evidence */}
              <Grid item xs={12} md={6}>
                <MDTypography variant="caption" sx={{ fontSize: 10, fontWeight: "bold", color: "#999" }}>
                  DEVICE TARGET
                </MDTypography>
                {id ? (
                  <>
                    <KV k="Contact" v={`${id.contact} (${id.hemisphere || "—"})`} />
                    <KV k="Region" v={id.region || "—"} />
                    <KV k="Band" v={`${fmt(id.band_lo_hz, 1)}–${fmt(id.band_hi_hz, 1)} Hz`} />
                    <KV k="Center (FFT-snapped)" v={`${fmt(id.center_freq_hz, 1)} → ${fmt(id.snapped_center_freq_hz, 2)} Hz`} />
                    <KV k="PRO metric / binarization" v={`${id.pro_metric} / ${id.binarization}`} />
                    <KV k="Polarity / suggested mode" v={`${dc.polarity} / ${dc.suggested_mode || "—"}`} />
                  </>
                ) : null}

                <MDBox mt={1.2} p={1.2} sx={{ borderRadius: "6px",
                  backgroundColor: th && th.available ? PAL.accentFill : PAL.warnFill,
                  border: `1px solid ${th && th.available ? PAL.accentBorder : PAL.warnBorder}` }}>
                  <MDTypography variant="caption" sx={{ fontSize: 10, fontWeight: "bold",
                    color: th && th.available ? PAL.accent : PAL.warnText }}>
                    THRESHOLD TO PROGRAM
                  </MDTypography>
                  {th && th.available ? (
                    <>
                      <MDTypography variant="h4" sx={{ fontSize: 24, color: PAL.accent, lineHeight: 1.1 }}>
                        {`power ≥ ${fmt(th.upper_lsb, 1)} LSB`}
                      </MDTypography>
                      <MDTypography variant="caption" sx={{ fontSize: 9.5, color: "#777" }}>
                        {`p${fmt(th.percentile, 0)} of device Timeline LSB · ${th.n_timeline_samples} in-band samples`}
                      </MDTypography>
                      {opProvenance && opProvenance.rule_label ? (
                        <MDTypography variant="caption" display="block" sx={{ fontSize: 9.5, color: "#777", mt: 0.3 }}>
                          {`Operating point: ${opProvenance.rule_label}`}
                          {opProvenance.sensitivity != null
                            ? ` · sens ${fmt(opProvenance.sensitivity)} / spec ${fmt(opProvenance.specificity)}` : ""}
                          {opProvenance.degenerate ? " · ⚠ degenerate — not deployable" : ""}
                        </MDTypography>
                      ) : null}
                    </>
                  ) : (
                    <MDTypography variant="caption" display="block" sx={{ fontSize: 11, mt: 0.3 }}>
                      No deployable LSB threshold — this band is off the device's adaptive sensing range.
                    </MDTypography>
                  )}
                </MDBox>

                {/* Advisory ramp guidance (audit C10): the closed-loop tuning surface is band +
                    threshold + RAMP. Renders only when the biomarker is deployable as stock adaptive. */}
                {dc && dc.ramp && dc.ramp.available ? (
                  <MDBox mt={1.2} p={1.0} sx={{ borderRadius: "6px",
                    backgroundColor: dc.ramp.posture === "conservative" ? PAL.warnFill : PAL.passFill,
                    border: `1px solid ${dc.ramp.posture === "conservative" ? PAL.warnBorder : (PAL.passBorder || "#009E7344")}` }}>
                    <MDTypography variant="caption" sx={{ fontSize: 10, fontWeight: "bold",
                      color: dc.ramp.posture === "conservative" ? PAL.warnText : PAL.pass }}>
                      {`RAMP GUIDANCE — ${String(dc.ramp.posture).toUpperCase()} (advisory)`}
                    </MDTypography>
                    <MDTypography variant="caption" display="block" color="text" sx={{ fontSize: 10.5, mt: 0.3 }}>
                      {dc.ramp.transition_note}
                    </MDTypography>
                    <MDTypography variant="caption" display="block" color="text" sx={{ fontSize: 10, mt: 0.3 }}>
                      {`Ramp up: ${dc.ramp.ramp_up_hint}. Ramp down: ${dc.ramp.ramp_down_hint}.`}
                    </MDTypography>
                    <MDTypography variant="caption" display="block" sx={{ fontSize: 9, color: "#777", mt: 0.3, fontStyle: "italic" }}>
                      {dc.ramp.reason}
                    </MDTypography>
                  </MDBox>
                ) : null}

                <MDBox mt={1.2}>
                  <MDTypography variant="caption" sx={{ fontSize: 10, fontWeight: "bold", color: "#999" }}>
                    EVIDENCE
                  </MDTypography>
                  {ev ? (
                    <>
                      <KV k="Deployment AUC — in-sample (95% clustered-bootstrap CI)" v={`${fmt(ev.auc)} (${fmt(ev.auc_lo)}–${fmt(ev.auc_hi)})`} />
                      {/* Audit C2: the held-out (train-past → test-future) AUC shown BESIDE the
                          in-sample number, so the forward optimism is visible at sign-off. Color the
                          held-out value by whether its CI clears chance (green) or not (warn). */}
                      {fwd && fwd.available && fwd.held_out_auc != null ? (
                        <KV
                          k={`Deployment AUC — forward held-out (${fwd.n_folds ?? "—"} weekly folds)`}
                          v={
                            <span style={{ color: fwd.beats_chance_forward ? PAL.pass : PAL.warnText, fontWeight: 600 }}>
                              {`${fmt(fwd.held_out_auc)} (${fmt(fwd.held_out_auc_lo)}–${fmt(fwd.held_out_auc_hi)})`}
                              {fwd.beats_chance_forward ? " ✓ clears chance" : " ✗ not validated forward"}
                            </span>
                          }
                        />
                      ) : (
                        <KV k="Deployment AUC — forward held-out" v={
                          <span style={{ color: PAL.warnText }}>
                            {fwd && fwd.reason ? `not assessable (${fwd.reason})` : "in-sample only — forward UNCONFIRMED"}
                          </span>
                        } />
                      )}
                      <KV k="Odds ratio (95% CI)" v={`${fmt(ev.odds_ratio)} (${fmt(ev.or_ci_low)}–${fmt(ev.or_ci_high)})${ev.credible_ci ? " ✓" : ""}`} />
                      <KV k="Mixed-effects p" v={ev.p_glmer != null ? ev.p_glmer.toExponential(2) : "—"} />
                      <KV k="Matched samples / ratings" v={`${ev.n_matched_samples ?? "—"} / ${ev.n_clusters ?? "—"}`} />
                      {pw && pw.available ? (
                        <KV k="Power (vs AUC 0.5)" v={pw.more_data_needed
                          ? `${fmt(pw.power_current * 100, 0)}% · need ${pw.n_ratings_needed} ratings`
                          : `${fmt(pw.power_current * 100, 0)}% · adequately powered`} />
                      ) : null}
                    </>
                  ) : null}
                </MDBox>
              </Grid>

              {/* RIGHT: gates + caveats */}
              <Grid item xs={12} md={6}>
                <MDTypography variant="caption" sx={{ fontSize: 10, fontWeight: "bold", color: "#999" }}>
                  DEPLOYMENT GATES
                </MDTypography>
                <MDBox mb={1.2}>
                  {(data.gates || []).map((g) => <GateRow key={g.key} gate={g} />)}
                </MDBox>

                <MDTypography variant="caption" sx={{ fontSize: 10, fontWeight: "bold", color: PAL.warnText }}>
                  CAVEATS
                </MDTypography>
                <MDBox component="ul" sx={{ pl: 2, mt: 0.5, mb: 0 }}>
                  {(data.caveats || []).map((c, i) => (
                    <MDTypography key={i} component="li" variant="caption"
                      sx={{ fontSize: 10, color: "#555", display: "list-item", mb: 0.3 }}>
                      {c}
                    </MDTypography>
                  ))}
                </MDBox>
              </Grid>
            </Grid>
          </>
        ) : null}
      </MDBox>
    </Card>
  );
}

export default DeploySignoffCard;
