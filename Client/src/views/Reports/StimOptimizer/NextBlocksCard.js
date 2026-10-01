/**
 * Which Left contact and rate to test at the next clinic visit (step C of the contact-aware Stim
 * Optimizer; the PI's rulings of 2026-10-01). The server (`routines/block_chooser.py`, response
 * `two_stage.stage1.clinic_stream.next_blocks`) ranks every (Left contact, rate) block at the
 * pulse widths in force, most promising first: the predicted change in pain against today's
 * setting plus 2 SD, at a current pair under both sides' maxima. A contact with too few clinic
 * stretches has no prediction of its own and gets the same bound from the spread of the pain
 * scores, so such blocks tie at the top. The PI: "show both lists on the page" -- the tied,
 * untested contacts as one list, the measured blocks ranked below it.
 */
import MDBox from "components/MDBox";
import MDTypography from "components/MDTypography";
import { T, TYPE } from "./typeScale";

const PRIOR_PREFIX = "no surface";
const BORROWED_PREFIX = "borrowed";

/** {tied: [{contact, rates}], measured: [block...]} -- tied = no prediction of its own. */
export function splitBlocks(nb) {
  const blocks = (nb && Array.isArray(nb.blocks)) ? nb.blocks : [];
  const tiedMap = new Map();
  const measured = [];
  blocks.forEach((b) => {
    if (String(b.basis || "").startsWith(PRIOR_PREFIX)) {
      if (!tiedMap.has(b.left_contact)) tiedMap.set(b.left_contact, []);
      tiedMap.get(b.left_contact).push(Number(b.rate_hz));
    } else {
      measured.push(b);
    }
  });
  const tied = Array.from(tiedMap.entries()).map(([contact, rates]) => ({ contact, rates: rates.sort((a, c) => a - c) }));
  return { tied, measured };
}

const hzList = (rates) => {
  const xs = rates.map((r) => `${r}`);
  return xs.length <= 1 ? `${xs[0] || ""} Hz` : `${xs.slice(0, -1).join(", ")} and ${xs[xs.length - 1]} Hz`;
};
const change = (v) => {
  const x = Number(v);
  if (!Number.isFinite(x)) return "—";
  if (Math.abs(x) < 0.005) return "no change";
  return `${Math.abs(x).toFixed(2)} ${x > 0 ? "better" : "worse"}`;
};
const source = (b) => (String(b.basis || "").startsWith(BORROWED_PREFIX)
  ? "borrowed from other rates and pulse widths" : "its own surface");
const mA = (v) => (v === null || v === undefined ? "—" : `${Number(v).toFixed(2)}`);

const cell = { padding: "4px 10px 4px 0", fontSize: TYPE.small, color: T.ink, textAlign: "left", verticalAlign: "top" };

/** "L C+1-2-: 26 steps at 0.5–2.5 mA over 3 visits, 22 rated; 14 more planned but never recorded
 *  as given" -- what the clinic sheets show a Left contact received (2026-10-01: unrated steps
 *  count as exposure; an untimed, unrated step is a plan, not a delivery). */
export function exposureLine(e) {
  const range = (e.amp_min_mA != null && e.amp_max_mA != null)
    ? (e.amp_min_mA === e.amp_max_mA ? ` at ${e.amp_min_mA} mA` : ` at ${e.amp_min_mA}–${e.amp_max_mA} mA`) : "";
  const visits = e.n_visits ? ` over ${e.n_visits} ${e.n_visits === 1 ? "visit" : "visits"}` : "";
  const plan = e.n_planned_only ? `; ${e.n_planned_only} more planned but never recorded as given` : "";
  return `${e.left_contact}: ${e.n_steps} ${e.n_steps === 1 ? "step" : "steps"}${range}${visits}, ${e.n_rated} rated${plan}`;
}

export default function NextBlocksCard({ nextBlocks }) {
  if (!nextBlocks || nextBlocks.available !== true) return null;
  const { tied, measured } = splitBlocks(nextBlocks);
  const pw = nextBlocks.pulse_widths_us || {};
  // Left-0-mA and unreadable contacts are not a contact anyone could choose.
  const exposure = Object.values(nextBlocks.exposure || {})
    .filter((e) => e && e.left_contact && e.left_contact.startsWith("L ") && (e.n_steps > 0 || e.n_planned_only > 0));
  return (
    <MDBox data-testid="next-blocks-card" mt={2}>
      <MDTypography variant="caption" component="div" sx={{ fontSize: TYPE.body, color: T.ink, mb: 1 }}>
        {`Which Left contact and rate to test next, at today's pulse widths (left ${pw.Left ?? "—"} µs, right ${pw.Right ?? "—"} µs). `
          + "Each is scored by the predicted change in pain against today's setting plus 2 standard deviations "
          + "(the best change that is still plausible), at a current pair under both sides' maxima. "
          + "Clinic sheets only; home surveys are not used to choose."}
      </MDTypography>
      {nextBlocks.ranking_note && (
        <MDTypography variant="caption" component="div" sx={{ fontSize: TYPE.body, color: T.ink, mb: 1 }}>
          {`${nextBlocks.ranking_note}.`}
        </MDTypography>
      )}

      {tied.length > 0 && (
        <MDBox data-testid="next-blocks-tied" mb={2}>
          <MDTypography variant="caption" component="div" sx={{ fontSize: TYPE.body, fontWeight: 600, color: T.ink, mb: 0.5 }}>
            {`Not yet tested enough to predict (${tied.length} ${tied.length === 1 ? "contact" : "contacts"}, all tied at the top)`}
          </MDTypography>
          {tied.map((t) => (
            <MDTypography key={t.contact} variant="caption" component="div" sx={{ fontSize: TYPE.small, color: T.ink }}>
              {`${t.contact}: ${hzList(t.rates)}`}
            </MDTypography>
          ))}
        </MDBox>
      )}

      {exposure.length > 0 && (
        <MDBox data-testid="next-blocks-exposure" mb={2}>
          <MDTypography variant="caption" component="div" sx={{ fontSize: TYPE.body, fontWeight: 600, color: T.ink, mb: 0.5 }}>
            What the clinic sheets show each Left contact received (rated or not)
          </MDTypography>
          {exposure.map((e) => (
            <MDTypography key={e.left_contact} variant="caption" component="div" sx={{ fontSize: TYPE.small, color: T.ink }}>
              {exposureLine(e)}
            </MDTypography>
          ))}
        </MDBox>
      )}

      {measured.length > 0 && (
        <MDBox data-testid="next-blocks-measured">
          <MDTypography variant="caption" component="div" sx={{ fontSize: TYPE.body, fontWeight: 600, color: T.ink, mb: 0.5 }}>
            Measured, ranked by the best plausible change
          </MDTypography>
          <table style={{ borderCollapse: "collapse", width: "100%" }}>
            <thead>
              <tr>
                {["Left contact", "Rate", "Predicted change in pain (points)", "Best plausible", "Currents L / R (mA)", "Stretches", "From"].map((h) => (
                  <th key={h} style={{ ...cell, color: T.ink2, fontWeight: 600 }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {measured.map((b) => (
                <tr key={`${b.left_contact}-${b.rate_hz}`}>
                  <td style={cell}>{b.left_contact}</td>
                  <td style={cell}>{`${b.rate_hz} Hz`}</td>
                  <td style={cell}>{change(b.predicted_improvement)}</td>
                  <td style={cell}>{change(b.optimistic_improvement)}</td>
                  <td style={cell}>{`${mA(b.amp_mA_left)} / ${mA(b.amp_mA_right)}`}</td>
                  <td style={cell}>{b.n_stretches}</td>
                  <td style={cell}>{source(b)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </MDBox>
      )}
    </MDBox>
  );
}
