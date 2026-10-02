/**
 * The committed band's identity and its discovery-stage statistics, read from the band file.
 *
 * Moved out of the page file into the decision card's "Details" fold by decision 302 (the PI,
 * 2026-09-26: the detail below a permitted, supported configuration is hidden or collapsible). It
 * no longer draws a card of its own, because a card inside the decision card's fold would be a card
 * inside a card. A band chosen on the grid carries no discovery statistics, and the rows say so.
 */
import { Grid } from "@mui/material";

import MDBox from "components/MDBox";
import MDTypography from "components/MDTypography";

import PAL from "./palette";
import { TYPE, STATE } from "assets/theme/base/tokens";
import { fmtOddsRatioWithInterval } from "./deployFormat";

const fmt = (v, d = 2) => (v == null || !Number.isFinite(Number(v)) ? "not reported"
  : Number(v).toFixed(d));
const fmtP = (p) => (p == null || !Number.isFinite(Number(p)) ? "not reported"
  : Number(p) < 0.001 ? Number(p).toExponential(1) : Number(p).toFixed(3));

/**
 * The committed candidate's own discovery-stage verdict, as plain text with its glyph, never as a
 * coloured tag (TASTE_AUDIT.md D5, 2026-09-26: no pastel or red tags). It is a different quantity
 * from anything on the reconciled header and is labelled as such below. A failed or stim-dependent
 * verdict is evidence, not a device refusal, so it is the caution ink with ▲, never red.
 */
export function verdictState(verdict) {
  const v = verdict || "";
  if (/VALIDATED \(stim-stable\)/.test(v)) return STATE.pass;
  if (/VALIDATED \(stim-dependent\)/.test(v) || /failed/.test(v)) return STATE.caution;
  return STATE.notChecked;
}

// A labeled key/value row used across the identity block.
function KV({ label, children }) {
  return (
    <MDBox display="flex" flexDirection="row" alignItems="baseline" gap={1} mb={0.4}>
      <MDTypography variant="caption" sx={{ fontSize: PAL.fs.body, fontWeight: 600, minWidth: 150,
        color: PAL.ink2 }}>{label}</MDTypography>
      <MDTypography variant="caption" sx={{ fontSize: PAL.fs.body, color: PAL.ink }}>{children}</MDTypography>
    </MDBox>
  );
}

/**
 * The committed configuration's identity.
 *
 * The DEVICE IDENTITY column stays visible, because it is genuinely useful as a check that the right
 * contact and the right band are loaded, and getting that wrong invalidates everything above.
 *
 * The MIXED-EFFECTS EVIDENCE column is folded away behind a click. Those statistics — the odds ratio
 * per standard deviation, the mixed-effects p-value, the credible-interval flag, stim stability and
 * the per-era odds ratios — are discovery-stage evidence about whether the band was worth committing
 * at all. That question was settled when the band was committed, and this page's question is a
 * different one; they also duplicate what the receiver-operating-characteristic and per-era panels
 * show further down. Folded rather than deleted, because the audit trail is worth keeping one click
 * away.
 */
export default function BandCandidateIdentity({ bc, envelope }) {
  const ev = bc.evidence || {};
  const lbl = bc.label || {};
  const prov = bc.provenance || {};
  return (
    <MDBox className="cl-band-identity">
      <MDBox>
        <MDBox display="flex" alignItems="center" gap={1.2} mb={1} flexWrap="wrap">
          <MDTypography component="span" data-discovery-verdict=""
            sx={{ ...TYPE.body, fontWeight: 600, color: verdictState(bc.verdict).ink }}>
            <span aria-hidden="true" style={{ marginRight: 6 }}>{verdictState(bc.verdict).glyph}</span>
            {bc.verdict || "no discovery verdict"}
          </MDTypography>
          <MDTypography sx={{ fontSize: PAL.fs.lead, fontWeight: 600, color: PAL.ink }}>
            {`${bc.contact_label || bc.contact || "band"} at ${fmt(bc.center_freq_hz, 1)} Hz`}
          </MDTypography>
          <MDTypography component="span" sx={{ ...TYPE.body, color: PAL.ink3 }}>
            {lbl.pro_metric_label || lbl.pro_metric || "metric"}
          </MDTypography>
          {bc.adaptive_valid ? (
            <MDTypography component="span" sx={{ ...TYPE.body, color: PAL.ink }}>
              inside the adaptive band (8–30 Hz)
            </MDTypography>
          ) : (
            <MDTypography component="span" sx={{ ...TYPE.body, color: STATE.caution.ink }}>
              <span aria-hidden="true" style={{ marginRight: 6 }}>{STATE.caution.glyph}</span>
              outside the adaptive band
            </MDTypography>
          )}
        </MDBox>
        <MDTypography variant="caption" sx={{ display: "block", fontSize: PAL.fs.body, color: PAL.ink3,
          mb: 1 }}>
          The first verdict here is the one this band was chosen with, when it was found. It is a different
          quantity from the verdict at the top of the page, which is about whether the device will
          accept the configuration and whether the evidence supports it.
        </MDTypography>

        <Grid container spacing={3}>
          <Grid item xs={12} md={6}>
            <MDTypography variant="caption" sx={{ fontSize: PAL.fs.body, fontWeight: 600, color: PAL.ink3 }}>Device identity</MDTypography>
            <MDBox mt={0.6}>
              <KV label="Hemisphere">{bc.hemisphere || "not reported"}</KV>
              <KV label="Contact (sensing)">{bc.contact || "not reported"}</KV>
              <KV label="Band">{`${fmt(bc.band_lo_hz, 1)} to ${fmt(bc.band_hi_hz, 1)} Hz `
                + `(${fmt(bc.bandwidth_hz, 1)} Hz wide)`}</KV>
              <KV label="Centre, and moved to the nearest band the device computes">
                {`${fmt(bc.center_freq_hz, 2)} to ${fmt(bc.snapped_center_freq_hz, 2)} Hz`}
              </KV>
              <KV label="Polarity">{bc.polarity || "not reported"}</KV>
              <KV label="Suggested mode">
                {bc.suggested_mode
                  || <span style={{ color: PAL.warnText }}><span aria-hidden="true" style={{ marginRight: 6 }}>▲</span>none suggested — see the note</span>}
              </KV>
            </MDBox>
          </Grid>
          <Grid item xs={12} md={6}>
            {/* ALWAYS SHOWN. This block used to sit behind a "show the discovery-stage
                statistics" toggle, collapsed by default. The PI on 2026-09-10: "there's no point
                in hiding it ever." A number a reader cannot see cannot be checked. */}
            <MDTypography variant="caption" sx={{ fontSize: PAL.fs.body, fontWeight: 600, color: PAL.ink3 }}>When the band was found: statistics</MDTypography>
            {(
              <MDBox mt={0.6}>
                <KV label="Odds ratio (per 1 SD)">
                  {`${fmt(ev.odds_ratio)} `}
                  {ev.or_lo != null && ev.or_hi != null
                    ? `(95% range ${fmt(ev.or_lo)} to ${fmt(ev.or_hi)})` : ""}
                  {ev.credible_ci === false
                    ? <span style={{ color: PAL.warnText }}> · ▲ range narrower than the
                        credibility rule allows</span>
                    : ev.credible_ci === true
                      ? <span style={{ color: PAL.ink }}> · ✓ credible</span> : null}
                </KV>
                <KV label="p from the mixed-effects model">{fmtP(ev.p_glmer)}</KV>
                {/* "grouped by week" is stated because the ROC panel lower down groups the SAME
                    data by individual pain rating, and a reader comparing the two counts must
                    be able to see they are counting different things (open item 15). */}
                <KV label="Samples, grouped by week">
                  {`${ev.n_matched_samples ?? "not reported"} samples across `
                    + `${ev.n_clusters ?? "not reported"} weeks`}
                </KV>
                <KV label="Stimulation stability">
                  {ev.stim_stable == null ? "not reported"
                    : ev.stim_stable ? "stim-stable" : "stim-dependent"}
                  {ev.stim_lrt_p != null
                    ? ` (likelihood-ratio test p = ${fmtP(ev.stim_lrt_p)})` : ""}
                </KV>
                {/* P-03 (June audit item [0]): each state's odds ratio beside its interval. This
                    row reads the band file; a band chosen on the grid carries none (nothing has
                    filled it since decision 145), so it says where this band's own are printed. */}
                <KV label="Odds ratio per stimulation state (off, low, high current)">
                  {ev.or_by_era
                    ? ["OFF", "LOW", "HIGH"].map((t) => {
                      const ci = ev.or_by_era_ci && ev.or_by_era_ci[t];
                      return `${t}: ${fmtOddsRatioWithInterval(ev.or_by_era[t],
                        ci ? ci[0] : null, ci ? ci[1] : null)}`;
                    }).join("  \u00B7  ")
                    : "not in the band file; this band's own, with intervals, are on the "
                      + "stability card above"}
                </KV>
                <KV label="Label and join">
                  {`${lbl.pro_metric || "not reported"} \u00B7 `
                    + `${(lbl.binarization && lbl.binarization.strategy) || "not reported"} \u00B7 `
                    + `${lbl.join || "not reported"} \u00B7 `
                    + `${lbl.n_pos_days ?? "not reported"} positive days, `
                    + `${lbl.n_neg_days ?? "not reported"} negative`}
                </KV>
              </MDBox>
            )}
          </Grid>
        </Grid>

        {(!bc.adaptive_valid || bc.suggested_mode == null) && bc.suggested_mode_reason ? (
          <MDBox mt={1}>
            <MDTypography variant="caption" sx={{ fontSize: PAL.fs.body, color: PAL.warnText }}>
              <span aria-hidden="true" style={{ marginRight: 6 }}>▲</span>
              {`Deployment note: ${bc.suggested_mode_reason}.`}
              {bc.adaptive_valid_reason ? ` ${bc.adaptive_valid_reason}.` : ""}
            </MDTypography>
          </MDBox>
        ) : null}

        <MDBox mt={1}>
          <MDTypography variant="caption" sx={{ fontSize: PAL.fs.body, color: PAL.ink3 }}>
            {prov.selection_biased ? "Selection-biased pool \u2014 " : ""}
            {prov.selection_note || ""}
            {envelope && envelope.committed_at
              ? ` \u00B7 committed ${new Date(envelope.committed_at).toLocaleString()}` : ""}
          </MDTypography>
        </MDBox>
      </MDBox>
    </MDBox>
  );
}

