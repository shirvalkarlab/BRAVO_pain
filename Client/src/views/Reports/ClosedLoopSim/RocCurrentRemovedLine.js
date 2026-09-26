/**
 * One line under the deployment ROC figure: the area under the curve read again with the
 * stimulation current in force at each sample taken out of the band power (2026-09-26), from the
 * routine the deployment summary already prints it with (Biomarkers `routines/deployment_current.py`,
 * decision 293), carried on this panel's own endpoint as `auc_current_removed`. Descriptive only:
 * the plain area sets every gate. A refusal prints its reason, never a number; a response without
 * the field prints nothing.
 */
import PropTypes from "prop-types";
import MDTypography from "components/MDTypography";

const fmt = (v, d = 2) => (v == null || !Number.isFinite(Number(v)) ? "—" : Number(v).toFixed(d));
const NOTE = { fontSize: 11.5, color: "#5E5E5E", mt: 0.4, display: "block" };

export default function RocCurrentRemovedLine({ plainAuc, adjusted }) {
  const a = adjusted;
  if (!a) return null;
  if (!a.available || a.auc == null) {
    return (
      <MDTypography variant="caption" data-testid="roc-current-removed" sx={NOTE}>
        {`With the stimulation current taken out: not computed (${a.why || "no reason was recorded"}). `
          + "That is an absent measurement, not a finding."}
      </MDTypography>
    );
  }
  const n0 = a.n_samples_without_current || 0;
  const same = a.plain_on_same_samples;
  return (
    <MDTypography variant="caption" data-testid="roc-current-removed" sx={NOTE}>
      <b>{`AUC ${fmt(plainAuc)} plainly; ${fmt(a.auc)} (${fmt(a.auc_low)}–${fmt(a.auc_high)}) with the stimulation current taken out.`}</b>
      {` The same samples and high-or-low split, over ${a.n_pain_reports} pain reports and `
        + `${a.n_distinct_currents} distinct ${a.hemisphere || ""} currents, with the current in force at each `
        + `sample taken out of the band power as ${a.shape_words || "a straight line"}, in the plain number's `
        + "direction (below 0.5 would mean the direction reversed). "
        + (n0 > 0 && same && same.auc != null
          ? `${n0} sample${n0 === 1 ? "" : "s"} before the first dated setting have no current; the plain `
            + `reading on the samples that do is ${fmt(same.auc)}. `
          : "")
        + "Descriptive only: the plain area sets every gate."}
    </MDTypography>
  );
}

RocCurrentRemovedLine.propTypes = {
  plainAuc: PropTypes.number,
  adjusted: PropTypes.shape({ available: PropTypes.bool, auc: PropTypes.number, why: PropTypes.string }),
};
RocCurrentRemovedLine.defaultProps = { plainAuc: null, adjusted: null };
