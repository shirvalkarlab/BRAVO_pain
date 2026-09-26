/**
 * The committed band's identity and its discovery-stage statistics, read from the band file.
 *
 * Moved out of the page file into the decision card's "Details" fold by decision 302 (the PI,
 * 2026-09-26: the detail below a permitted, supported configuration is hidden or collapsible). It
 * no longer draws a card of its own, because a card inside the decision card's fold would be a card
 * inside a card. A band chosen on the grid carries no discovery statistics, and the rows say so.
 */
import { Chip, Grid } from "@mui/material";

import MDBox from "components/MDBox";
import MDTypography from "components/MDTypography";

import PAL from "./palette";
import Fold from "./Fold";
import { fmtOddsRatioWithInterval } from "./deployFormat";

const fmt = (v, d = 2) => (v == null || !Number.isFinite(Number(v)) ? "not reported"
  : Number(v).toFixed(d));
const fmtP = (p) => (p == null || !Number.isFinite(Number(p)) ? "not reported"
  : Number(p) < 0.001 ? Number(p).toExponential(1) : Number(p).toFixed(3));

// Verdict badge color for the committed candidate's own discovery-stage verdict, which is a
// different quantity from anything on the reconciled header and is labelled as such below.
function verdictColor(verdict) {
  const v = verdict || "";
  if (/VALIDATED \(stim-stable\)/.test(v)) return PAL.passText;
  if (/VALIDATED \(stim-dependent\)/.test(v)) return PAL.warn;
  if (/failed/.test(v)) return PAL.failText;
  return PAL.neutral;
}

// White text on the warn fill measures 2.25:1, which is below every WCAG threshold, so the badge
// text colour adapts to its fill: near-black on the amber, white on the others.
function verdictTextColor(verdict) {
  return verdictColor(verdict) === PAL.warn ? PAL.onWarn : "white";
}

// A labeled key/value row used across the identity block.
function KV({ label, children }) {
  return (
    <MDBox display="flex" flexDirection="row" alignItems="baseline" gap={1} mb={0.4}>
      <MDTypography variant="caption" sx={{ fontSize: 11, fontWeight: "bold", minWidth: 150,
        color: "#4A4A4A" }}>{label}</MDTypography>
      <MDTypography variant="caption" sx={{ fontSize: 11.5 }}>{children}</MDTypography>
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
          <MDBox px={1.4} py={0.4} sx={{ backgroundColor: verdictColor(bc.verdict),
            color: verdictTextColor(bc.verdict),
            borderRadius: "10px", fontSize: 11, fontWeight: "bold" }}>
            {bc.verdict || "no discovery verdict"}
          </MDBox>
          <MDTypography variant="h6" sx={{ fontSize: 16 }}>
            {`${bc.contact_label || bc.contact || "band"} at ${fmt(bc.center_freq_hz, 1)} Hz`}
          </MDTypography>
          <Chip size="small" label={lbl.pro_metric_label || lbl.pro_metric || "metric"}
            sx={{ height: 20, fontSize: 11 }} />
          {bc.adaptive_valid
            ? <Chip size="small" label="inside the adaptive band (8–30 Hz)"
                sx={{ height: 20, fontSize: 11.5, backgroundColor: PAL.passText, color: "white" }} />
            : <Chip size="small" label="outside the adaptive band"
                sx={{ height: 20, fontSize: 11.5, backgroundColor: PAL.warn,
                  color: PAL.onWarn }} />}
        </MDBox>
        <Fold show="What the badge means" hide="Hide" mt={0} dense>
          <MDTypography variant="caption" sx={{ display: "block", fontSize: 11.5, color: "#5E5E5E",
            mb: 1 }}>
            The badge above is the discovery-stage verdict this band was committed with. It is a
            different quantity from the reconciled verdict at the top of the page, which is about
            whether the device will accept the configuration and whether the evidence supports it.
          </MDTypography>
        </Fold>

        <Grid container spacing={3}>
          <Grid item xs={12} md={6}>
            <MDTypography variant="caption" sx={{ fontSize: 11.5, fontWeight: "bold",
              letterSpacing: 0.4, color: "#5E5E5E" }}>DEVICE IDENTITY</MDTypography>
            <MDBox mt={0.6}>
              <KV label="Hemisphere">{bc.hemisphere || "not reported"}</KV>
              <KV label="Contact (sensing)">{bc.contact || "not reported"}</KV>
              <KV label="Band">{`${fmt(bc.band_lo_hz, 1)} to ${fmt(bc.band_hi_hz, 1)} Hz `
                + `(${fmt(bc.bandwidth_hz, 1)} Hz wide)`}</KV>
              <KV label="Centre, and FFT-snapped">
                {`${fmt(bc.center_freq_hz, 2)} to ${fmt(bc.snapped_center_freq_hz, 2)} Hz`}
              </KV>
              <KV label="Polarity">{bc.polarity || "not reported"}</KV>
              <KV label="Suggested mode">
                {bc.suggested_mode
                  || <span style={{ color: PAL.warnText }}>none suggested — see the note</span>}
              </KV>
            </MDBox>
          </Grid>
          <Grid item xs={12} md={6}>
            {/* ALWAYS SHOWN. This block used to sit behind a "show the discovery-stage
                statistics" toggle, collapsed by default. The PI on 2026-09-10: "there's no point
                in hiding it ever." A number a reader cannot see cannot be checked. */}
            <MDTypography variant="caption" sx={{ fontSize: 11.5, fontWeight: "bold",
              letterSpacing: 0.4, color: "#5E5E5E" }}>DISCOVERY-STAGE STATISTICS</MDTypography>
            {(
              <MDBox mt={0.6}>
                <KV label="Odds ratio (per 1 SD)">
                  {`${fmt(ev.odds_ratio)} `}
                  {ev.or_lo != null && ev.or_hi != null
                    ? `(95% CI ${fmt(ev.or_lo)} to ${fmt(ev.or_hi)})` : ""}
                  {ev.credible_ci === false
                    ? <span style={{ color: PAL.failText }}> · interval narrower than the
                        credibility rule allows</span>
                    : ev.credible_ci === true
                      ? <span style={{ color: PAL.passText }}> · credible</span> : null}
                </KV>
                <KV label="Mixed-effects p">{fmtP(ev.p_glmer)}</KV>
                {/* "grouped by week" is stated because the ROC panel lower down groups the SAME
                    data by individual pain rating, and a reader comparing the two counts must
                    be able to see they are counting different things (open item 15). */}
                <KV label="Samples, grouped by week">
                  {`${ev.n_matched_samples ?? "not reported"} samples across `
                    + `${ev.n_clusters ?? "not reported"} weeks`}
                </KV>
                <KV label="Stim stability">
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
          <MDBox mt={1} p={1} sx={{ backgroundColor: PAL.warnFill, borderRadius: "6px" }}>
            <MDTypography variant="caption" sx={{ fontSize: 11.5, color: PAL.warnText }}>
              {`Deployment note: ${bc.suggested_mode_reason}.`}
              {bc.adaptive_valid_reason ? ` ${bc.adaptive_valid_reason}.` : ""}
            </MDTypography>
          </MDBox>
        ) : null}

        <MDBox mt={1}>
          <MDTypography variant="caption" color="text" sx={{ fontSize: 11.5, fontStyle: "italic" }}>
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

