/**
 * The provisional caveat beside a verdict that rests on point signs alone.
 *
 * THE RULE THIS DRAWS. PI, 2026-09-13, his words: "Established means mean only for flexibility."
 * Of three readings put to him he chose "point sign decides, but flag as provisional": an edge of
 * the amplitude-power-pain triangle has a direction when its point estimate has a sign; its
 * interval and p-value stay on the page as caveats and block nothing; and a verdict licensed while
 * any interval spans zero is flagged provisional. The module serialises that as
 * `verdict_detail.provisional`, `verdict_detail.n_edges_unestablished`,
 * `verdict_detail.unestablished_edges` and the verdict string itself ("supported (point signs
 * only; N of 3 intervals span zero)").
 *
 * WHY ONE COMPONENT. The same line has to appear in three places -- under the "does the evidence
 * support this configuration" answer, beside the "is there anything to transcribe" answer, and on
 * the parameter table the reader transcribes from -- and it must never sit inside a fold (house
 * rule: values, verdicts and warnings are never folded). One component means the three cannot
 * drift, and the numbers are read off the edges themselves rather than restated.
 *
 * WHAT IT PRINTS. The count, then each edge whose interval spans zero with its interval and p, as
 * numbers rather than adjectives: "E1 −3.79 [−12.5, +4.93] p = 0.42". Nothing when the report is
 * not licensed (there is no verdict to qualify) or when every interval excludes zero.
 */
import MDBox from "components/MDBox";
import MDTypography from "components/MDTypography";

import PAL from "./palette";
import { ciBound, fmtNum, fmtP } from "./deployFormat";

/** The edges whose interval spans zero (or has no interval), read off the payload's own flags. */
export function provisionalCaveat(rep) {
  if (!rep || !rep.available) return null;
  const vd = rep.verdict_detail || {};
  if (vd.provisional !== true) return null;
  const edges = rep.edges || {};
  const names = Array.isArray(vd.unestablished_edges) && vd.unestablished_edges.length
    ? vd.unestablished_edges
    : ["E1", "E2", "E3"].filter((k) => edges[k] && edges[k].statistically_established === false);
  const total = vd.n_edges != null ? Number(vd.n_edges) : Object.keys(edges).length || 3;
  const n = vd.n_edges_unestablished != null ? Number(vd.n_edges_unestablished) : names.length;
  return {
    n,
    total,
    edges: names.map((k) => {
      const e = edges[k] || {};
      const lo = ciBound(e.ci, 0);
      const hi = ciBound(e.ci, 1);
      const est = Number.isFinite(Number(e.estimate)) ? Number(e.estimate) : null;
      const sign = e.sign != null ? (Number(e.sign) > 0 ? "+" : "−") : "?";
      return {
        k,
        sign,
        text: `${k} sign ${sign}: ${fmtNum(est, 3)} [`
          + `${lo.unbounded ? "unbounded" : fmtNum(lo.value, 3)}, `
          + `${hi.unbounded ? "unbounded" : fmtNum(hi.value, 3)}] p = ${fmtP(e.p)}`,
      };
    }),
  };
}

/** One sentence for a caption, or "" when there is nothing provisional. */
export function provisionalSentence(rep) {
  const c = provisionalCaveat(rep);
  if (!c) return "";
  return `Provisional: point signs only; ${c.n} of ${c.total} intervals span zero (`
    + `${c.edges.map((e) => e.text).join("; ")}).`;
}

export default function ProvisionalNote({ deploymentReport, dense = false, mt = 0.6 }) {
  const rep = deploymentReport && deploymentReport.data ? deploymentReport.data : deploymentReport;
  const c = provisionalCaveat(rep);
  if (!c) return null;
  return (
    <MDBox className="cl-provisional" mt={mt} px={dense ? 0.8 : 1} py={dense ? 0.4 : 0.6}
      sx={{ backgroundColor: PAL.warnFill || "#FFF7E6", borderRadius: "4px",
        border: `1px solid ${PAL.warnBorder || PAL.warn}` }}>
      <MDTypography variant="caption" sx={{ display: "block", fontSize: dense ? 10 : 10.5,
        fontWeight: "bold", letterSpacing: 0.3, color: PAL.warnText || PAL.warn }}>
        {`PROVISIONAL — POINT SIGNS ONLY; ${c.n} OF ${c.total} INTERVALS SPAN ZERO`}
      </MDTypography>
      {c.edges.map((e) => (
        <MDTypography key={e.k} variant="caption" sx={{ display: "block", fontSize: dense ? 10 : 10.5,
          fontFamily: PAL.mono, color: "#2A2A2A" }}>
          {e.text}
        </MDTypography>
      ))}
      <MDTypography variant="caption" sx={{ display: "block", fontSize: dense ? 9.5 : 10,
        color: "#4A4A4A", mt: 0.2 }}>
        The verdict rests on the sign of each point estimate (PI rule, 2026-09-13: "established
        means mean only"). An interval that spans zero is a caveat on the page, not a block.
      </MDTypography>
    </MDBox>
  );
}
