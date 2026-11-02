/**
 * Programmed now against candidate thresholds, on the home record (the PI, 2026-10-26: "compare the
 * current settings or what was set in clinic with what might be optimal"). A LABEL ONLY: it changes
 * no threshold, verdict or gate. Drawn from the report's `threshold_comparison` block, which the
 * server works out on read (`ClosedLoopDeployment/threshold_comparison.py`) and never saves.
 *
 * One compact table under the threshold values: the thresholds the device runs now, then (a) the pair
 * this report places from clinic recordings, (b) the manufacturer's daytime 25th/75th percentiles of
 * home power, (c) an upper threshold fitted on the earlier 70% of reports. Each row: the share of
 * home readings above / between / below, by day and by night; the share of time the device would
 * hold the upper current; the pain score when power was above against the rest, with its interval
 * and rotation p; the design rule's noise-only crossings an hour. The limits sentence (how many
 * reports, no randomised comparison, a clinician programs) is always printed, never folded.
 */
import MDBox from "components/MDBox";
import MDTypography from "components/MDTypography";

import PAL from "./palette";

const COLS = [
  [1.5, "Thresholds"],
  [1.0, "Upper / lower"],
  [1.3, "Day: above / between / below"],
  [1.3, "Night: above / between / below"],
  [0.9, "Time at upper current"],
  [1.6, "Pain, above minus rest"],
  [0.9, "Noise crossings/h"],
];
export const COMPARISON_MIN_WIDTH = 760;

const pct = (x) => (x == null ? "–" : `${Math.round(100 * x)}`);
const num = (x, d = 0) => (x == null || !Number.isFinite(Number(x)) ? "–" : Number(x).toFixed(d));
const signed = (x, d = 0) => (x == null ? "–" : `${x > 0 ? "+" : x < 0 ? "−" : ""}${Math.abs(x).toFixed(d)}`);

/** "ZERO_THREE_LEFT" -> "L 0-3". */
export function pairWords(pair) {
  const u = String(pair || "").toUpperCase();
  const nums = { ZERO: "0", ONE: "1", TWO: "2", THREE: "3" };
  const digits = u.split("_").filter((p) => nums[p]).map((p) => nums[p]);
  const side = u.endsWith("LEFT") ? "L" : u.endsWith("RIGHT") ? "R" : "?";
  return digits.length ? `${side} ${digits.join("-")}` : String(pair || "");
}

/** The three shares as one cell, "34 / 28 / 38%". */
export function sharesText(s) {
  if (!s || s.above == null) return "–";
  return `${pct(s.above)} / ${pct(s.between)} / ${pct(s.below)}%`;
}

/** The pain difference as one cell: "+12 [−11, +30] p 0.23 (6 vs 7)"; a reason when none. */
export function painText(p) {
  const d = p && p.difference;
  if (!p || !p.n_reports) return "no reports";
  if (!d || d.value == null) {
    const n = d ? `${d.n_above} vs ${d.n_rest}` : `${p.n_reports}`;
    return `none (${n})`;
  }
  const ci = d.low == null ? "" : ` [${signed(d.low)}, ${signed(d.high)}]`;
  const pv = d.p_rotation == null ? "" : ` p ${num(d.p_rotation, 2)}`;
  return `${signed(d.value)}${ci}${pv} (${d.n_above} vs ${d.n_rest})`;
}

/** The design rule's cell: "≤599" or "–" when it does not apply. */
export function designText(r) {
  if (!r || !r.applies || r.crossings_per_hour_at_most == null) return "–";
  return `≤${num(r.crossings_per_hour_at_most)}`;
}

function rowName(r) {
  const own = r.key === "programmed" && r.same_band_as_report === false;
  return own ? `${r.label} (${pairWords(r.pair)} ${num(r.centre_hz, 2)} Hz)` : r.label;
}

function Line({ children, ink = PAL.ink2, testid }) {
  return (
    <MDTypography variant="caption" data-testid={testid}
      sx={{ display: "block", fontSize: PAL.fs.body, color: ink, mt: 0.4 }}>
      {children}
    </MDTypography>
  );
}

export default function ThresholdComparison({ data }) {
  const b = data && data.threshold_comparison;
  if (!b) return null;
  if (b.available === false) {
    return (
      <MDBox mt={1.2} data-testid="threshold-comparison">
        <Line ink={PAL.ink3}>{`Programmed now vs candidates: not available (${b.reason || "no reason given"}).`}</Line>
      </MDBox>
    );
  }
  const band = b.band || {};
  const rows = b.rows || [];
  const head = `${b.pain_score || "pain"} · home record ${pairWords(band.pair)} `
    + `${band.home_freq_hz == null ? "none" : `${num(band.home_freq_hz, 2)} Hz`} · n=${b.n_reports || 0} reports`;
  return (
    <MDBox mt={1.2} data-testid="threshold-comparison">
      <MDTypography variant="caption" sx={{ display: "block", fontSize: PAL.fs.body, fontWeight: 600, color: PAL.ink }}>
        Programmed now vs candidates
      </MDTypography>
      <MDTypography variant="caption" sx={{ display: "block", fontSize: PAL.fs.body, color: PAL.ink2, mb: 0.4 }}>
        {head}
      </MDTypography>
      <MDBox sx={{ overflowX: "auto", maxWidth: "100%" }}>
        <MDBox sx={{ minWidth: COMPARISON_MIN_WIDTH }}>
          <MDBox display="flex" flexDirection="row" py={0.4} sx={{ backgroundColor: PAL.fillMuted }}>
            {COLS.map(([flex, h]) => (
              <MDBox key={h} flex={flex} sx={{ px: 0.5 }}>
                <MDTypography variant="caption" sx={{ fontSize: PAL.fs.caption, fontWeight: 600, color: PAL.ink3 }}>
                  {h}
                </MDTypography>
              </MDBox>
            ))}
          </MDBox>
          {rows.map((r, i) => {
            const cells = [
              rowName(r),
              `${num(r.upper, 1)} / ${num(r.lower, 1)}`,
              sharesText(r.shares && r.shares.day),
              sharesText(r.shares && r.shares.night),
              r.time_high && r.time_high.high != null ? `${pct(r.time_high.high)}%` : "–",
              painText(r.pain),
              designText(r.design_rule),
            ];
            return (
              <MDBox key={r.key} data-testid="threshold-comparison-row"
                sx={{ borderTop: i === 0 ? "none" : `1px solid ${PAL.rule}` }}>
                <MDBox display="flex" flexDirection="row" py={0.35}>
                  {cells.map((c, j) => (
                    <MDBox key={COLS[j][1]} flex={COLS[j][0]} sx={{ px: 0.5 }}>
                      <MDTypography variant="caption" sx={{ fontSize: PAL.fs.body, color: PAL.ink,
                        fontWeight: j === 0 ? 600 : 400 }}>
                        {c}
                      </MDTypography>
                    </MDBox>
                  ))}
                </MDBox>
                {(r.flags || []).length ? (
                  <MDTypography variant="caption" sx={{ display: "block", fontSize: PAL.fs.body, color: PAL.warnText, px: 0.5 }}>
                    <span aria-hidden="true" style={{ marginRight: 6 }}>▲</span>{r.flags.join("; ")}
                  </MDTypography>
                ) : null}
              </MDBox>
            );
          })}
        </MDBox>
      </MDBox>
      {(b.notes || []).map((n) => <Line key={n}>{n}</Line>)}
      {b.too_few_reports ? (
        <MDTypography variant="caption" data-testid="threshold-comparison-limits"
          sx={{ display: "block", fontSize: PAL.fs.body, color: PAL.warnText, mt: 0.4 }}>
          <span aria-hidden="true" style={{ marginRight: 6 }}>▲</span>{b.limits}
        </MDTypography>
      ) : <Line testid="threshold-comparison-limits">{b.limits}</Line>}
    </MDBox>
  );
}
