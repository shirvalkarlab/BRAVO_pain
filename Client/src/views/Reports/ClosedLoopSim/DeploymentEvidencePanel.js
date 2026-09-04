/**
 * Device eligibility, the three edges, and the coherence verdict — the top of the rebuilt page.
 *
 * Three things the previous layout could not say, each of which changed what a reader should do:
 *
 *  1. A THREE-STATE verdict. "Blocked by the device" and "not supported by the evidence" are
 *     different problems with different remedies — the first is fixed at the programmer, the second
 *     only by measurement — and the old boolean collapsed them into one "not ready".
 *  2. WHY the device would refuse, rule by rule, with the page citation. A rule whose value has not
 *     been read off the programmer is shown as UNKNOWN and blocks, rather than passing quietly;
 *     a rule that cannot be evaluated must never look like a rule that passed.
 *  3. The three edges WITH their clustering unit and cluster count. The audit's central finding was
 *     that treating correlated observations as independent inflated significance throughout this
 *     project, so an estimate shown without its clustering provenance is not interpretable. Where
 *     the cluster count is below the floor at which the robust estimator is trustworthy, the row
 *     says so instead of presenting a confidence interval as though it were reliable.
 */
import { Card, Chip, Divider, Grid, Tooltip } from "@mui/material";
import MDBox from "components/MDBox";
import MDTypography from "components/MDTypography";

import PAL from "./palette";

// An advisory is worth showing only when it reports a SHORTFALL. The rule table carries 29
// advisories, most of which are context the reader does not need on every page load; surfacing all
// of them would bury the two or three that describe a measurement falling short of a device
// recommendation.
//
// The discriminator is `kind`, which the evaluator already sets per outcome: "advisory_failed" is
// the predicate returning false, as against "advisory_no_predicate" (recorded for the reader, never
// checked), "advisory_not_determinable" (inputs absent) and "predicate_error". An earlier version
// of this filter tested a `passed` field that the payload does not carry, so it matched nothing and
// rendered an empty section — the failure mode worth guarding here is a silently empty panel, not a
// noisy one.
const shortfall = (a) => a && a.kind === "advisory_failed";

const fmt = (v, d = 3) => (v == null || !Number.isFinite(Number(v)) ? "—" : Number(v).toFixed(d));

// Below this many clusters the cluster-robust variance estimator is anti-conservative: its
// intervals are too NARROW, so it manufactures resolution rather than losing it. Mirrors
// MIN_RELIABLE_CLUSTERS in modules/ClosedLoopDeployment/edges.py; keep the two in step.
const MIN_RELIABLE_CLUSTERS = 40;

const VERDICTS = {
  supported: {
    color: PAL.pass, label: "SUPPORTED AND PROGRAMMABLE",
    blurb: "The device permits this configuration and the evidence supports it. Confirm every value "
         + "against the programmer before entering it.",
  },
  unsupported: {
    color: PAL.warn, label: "NOT SUPPORTED BY THE EVIDENCE",
    blurb: "The device would permit this configuration, but the measurements do not establish that "
         + "it would work. This is a measurement problem, not a programming one — the remedy is the "
         + "titration session, not a different setting.",
  },
  blocked: {
    color: PAL.fail, label: "BLOCKED BY THE DEVICE",
    blurb: "At least one device rule forbids this configuration, or has a value that has not been "
         + "read off the programmer. Nothing downstream matters until this is resolved.",
  },
};

function EdgeRow({ k, e }) {
  if (!e) return null;
  const few = e.n_clusters != null && e.n_clusters < MIN_RELIABLE_CLUSTERS;
  const ci = e.ci && e.ci[0] != null ? `[${fmt(e.ci[0])}, ${fmt(e.ci[1])}]` : "—";
  // An unresolved edge is shown in the neutral ink, never the failure ink: "we have not established
  // a direction" is not the same finding as "the direction is wrong".
  const ink = e.resolved ? (few ? PAL.warn : PAL.pass) : PAL.neutral;
  return (
    <MDBox display="flex" alignItems="flex-start" py={0.75}
           sx={{ borderTop: "1px solid rgba(0,0,0,0.08)" }}>
      <MDBox width="9%"><MDTypography variant="button" fontWeight="bold">{k}</MDTypography></MDBox>
      <MDBox width="17%"><MDTypography variant="caption">{fmt(e.estimate)}</MDTypography></MDBox>
      <MDBox width="26%"><MDTypography variant="caption">{ci}</MDTypography></MDBox>
      <MDBox width="12%"><MDTypography variant="caption">{fmt(e.p, 4)}</MDTypography></MDBox>
      <MDBox width="24%">
        <Tooltip title={few
          ? `${e.n_clusters} clusters is below the ${MIN_RELIABLE_CLUSTERS} at which the `
            + "cluster-robust estimator becomes reliable. Below it the interval is too narrow, so "
            + "apparent resolution may be manufactured. Prefer the permutation test here."
          : "Cluster unit and count that the standard error was computed at."}>
          <MDTypography variant="caption" sx={{ color: few ? PAL.warn : "inherit" }}>
            {e.n_clusters} {e.cluster_unit}{few ? " ⚠" : ""}
          </MDTypography>
        </Tooltip>
      </MDBox>
      <MDBox width="12%">
        <MDTypography variant="caption" fontWeight="bold" sx={{ color: ink }}>
          {e.resolved ? (few ? "resolved*" : "resolved") : "unresolved"}
        </MDTypography>
      </MDBox>
    </MDBox>
  );
}

export default function DeploymentEvidencePanel({ report }) {
  const { data, loading, err } = report || { data: null, loading: false, err: null };

  if (loading) {
    return (
      <Card><MDBox p={2}>
        <MDTypography variant="button">Evaluating device eligibility and the evidence triangle…</MDTypography>
      </MDBox></Card>
    );
  }
  if (!data) {
    return (
      <Card><MDBox p={2}>
        <MDTypography variant="h6">Closed-loop deployability</MDTypography>
        <MDTypography variant="caption" sx={{ color: PAL.neutral }}>
          {err || "No candidate configuration selected."} Deployability is evaluated for a specific
          channel and centre frequency, not for a participant, so choose one on the Biomarker
          Exploration page first.
        </MDTypography>
      </MDBox></Card>
    );
  }

  const v = VERDICTS[data.verdict] || VERDICTS.unsupported;
  const el = data.eligibility;
  const co = data.coherence;
  const detail = data.verdict_detail || {};

  return (
    <Card>
      <MDBox p={2}>
        {/* 1 — the three-state verdict */}
        <MDBox display="flex" alignItems="center" mb={0.5} flexWrap="wrap" gap={1}>
          <Chip label={v.label} size="small"
                sx={{ backgroundColor: v.color, color: "#fff", fontWeight: 700 }} />
          <MDTypography variant="h6">Closed-loop deployability</MDTypography>
        </MDBox>
        <MDTypography variant="caption" sx={{ display: "block", mb: 1.5 }}>{v.blurb}</MDTypography>

        <Grid container spacing={2}>
          {/* 2 — device eligibility */}
          <Grid item xs={12} md={5}>
            <MDTypography variant="button" fontWeight="bold">Device eligibility</MDTypography>
            <MDTypography variant="caption" sx={{ display: "block", mb: 0.5 }}>
              {el ? el.summary : "not checked"}
            </MDTypography>
            {el && el.failures && el.failures.map((f) => (
              <MDBox key={`f-${f.rule_id}`} py={0.4}>
                <MDTypography variant="caption" sx={{ color: PAL.fail }}>
                  <b>{f.rule_id}</b> {f.title} <i>({f.page})</i>
                </MDTypography>
              </MDBox>
            ))}
            {el && el.unknowns && el.unknowns.map((u) => (
              <MDBox key={`u-${u.rule_id}`} py={0.4}>
                <Tooltip title={u.why || ""}>
                  <MDTypography variant="caption" sx={{ color: PAL.warn }}>
                    <b>{u.rule_id}</b> {u.title} — value not read off the programmer, so it blocks
                  </MDTypography>
                </Tooltip>
              </MDBox>
            ))}
            {el && el.eligible && (
              <MDTypography variant="caption" sx={{ color: PAL.pass }}>
                All evaluable rules pass.
              </MDTypography>
            )}

            {/* Advisories that carry a real shortfall. D09 is the reason this block exists: it was
                softened from blocking to advisory on 2026-09-04 because the guide RECOMMENDS the
                1.2 uVp capture amplitude and states it two ways without explaining the difference.
                Softening a rule must not make it invisible — a signal below the capture floor is
                the difference between a threshold that holds and one that drifts, so it is shown
                in the warning ink with the specific bins named. */}
            {el && (el.advisories || []).filter(shortfall).length > 0 && (
              <MDBox mt={1}>
                <MDTypography variant="caption" fontWeight="bold" sx={{ color: PAL.warn }}>
                  Advisory — reported, not blocking
                </MDTypography>
                {(el.advisories || []).filter(shortfall).map((a) => (
                  <MDBox key={`a-${a.rule_id}`} py={0.35}>
                    <Tooltip title={a.why || ""}>
                      <MDTypography variant="caption" sx={{ color: PAL.warn, display: "block" }}>
                        <b>{a.rule_id}</b> {a.title} <i>({a.page})</i>
                        {a.observed ? <><br />{a.observed}</> : null}
                      </MDTypography>
                    </Tooltip>
                  </MDBox>
                ))}
              </MDBox>
            )}
          </Grid>

          {/* 3 — the evidence triangle, with sample-size provenance */}
          <Grid item xs={12} md={7}>
            <MDTypography variant="button" fontWeight="bold">
              The evidence triangle: amplitude → power → pain
            </MDTypography>
            <MDBox display="flex" pt={0.5} pb={0.25}>
              {[["9%", "edge"], ["17%", "estimate"], ["26%", "95% CI"], ["12%", "p"],
                ["24%", "clustered at"], ["12%", ""]].map(([w, h]) => (
                  <MDBox key={h + w} width={w}>
                    <MDTypography variant="caption" fontWeight="bold"
                                  sx={{ color: PAL.neutral }}>{h}</MDTypography>
                  </MDBox>
              ))}
            </MDBox>
            {["E1", "E2", "E3"].map((k) => <EdgeRow key={k} k={k} e={data.edges && data.edges[k]} />)}
            <MDTypography variant="caption" sx={{ display: "block", mt: 0.75, color: PAL.neutral }}>
              E1 amplitude→power (can the device move the signal), E2 power→pain (does the signal
              track the patient), E3 amplitude→pain (does the therapy work). An asterisk marks an
              interval computed on fewer than {MIN_RELIABLE_CLUSTERS} clusters, where it is likely
              too narrow.
            </MDTypography>

            <Divider sx={{ my: 1 }} />
            <MDTypography variant="button" fontWeight="bold">Sign coherence&nbsp;</MDTypography>
            <MDTypography variant="button" sx={{
              color: co && co.coherent === true ? PAL.pass
                   : co && co.coherent === false ? PAL.fail : PAL.neutral }}>
              {co == null ? "—" : co.coherent === true ? "coherent"
                : co.coherent === false ? "not coherent" : "not established"}
            </MDTypography>
            {co && co.note && (
              <MDTypography variant="caption" sx={{ display: "block", mt: 0.5 }}>{co.note}</MDTypography>
            )}
          </Grid>
        </Grid>

        {detail.blockers && detail.blockers.length > 0 && (
          <MDBox mt={1.5}>
            <MDTypography variant="button" fontWeight="bold" sx={{ color: PAL.fail }}>
              Blockers
            </MDTypography>
            {detail.blockers.map((b, i) => (
              <MDTypography key={`b${i}`} variant="caption" sx={{ display: "block" }}>• {b}</MDTypography>
            ))}
          </MDBox>
        )}
      </MDBox>
    </Card>
  );
}
