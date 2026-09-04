/**
 * The evidence triangle, drawn as a graph beside three separate signed axes, with the three-valued
 * coherence answer beneath.
 *
 * WHAT THIS REPLACES. The panel this supersedes rendered the three edges as a six-column table whose
 * verdict column had no header, and it carried the topology — that these are three edges of a closed
 * loop, and that the amplitude-to-power and power-to-pain edges compose to predict the
 * amplitude-to-pain edge, which is the whole reason their signs have to cohere — entirely in a
 * caption. A reader who did not already know the argument could not recover it from the display.
 *
 * WHY THREE SEPARATE AXES RATHER THAN ONE SHARED AXIS. The three edges are measured in LFP power per
 * milliamp, pain points per unit of LFP power, and pain points per milliamp. Those are three
 * different quantities, and plotting them against one numeric axis would present non-comparable
 * measurements as visual peers and invite a magnitude comparison that has no meaning. Only ZERO is
 * aligned across the three axes, because the sign comparison is the actual question the coherence
 * test asks and alignment at zero is what makes that comparison readable by eye.
 *
 * WHY AN UNRESOLVED EDGE IS DRAWN AT FULL WEIGHT WITH NO ARROWHEAD. An arrowhead asserts a
 * direction, and an edge whose interval spans zero has not established one. Withholding the
 * arrowhead withholds the assertion. Drawing the line at full weight and full length is equally
 * deliberate: an unresolved edge must read as present but undetermined, never as absent and never as
 * zero, so it keeps its full stroke and gains a hollow diamond carrying a question mark at its
 * midpoint — a visible placeholder for a sign rather than a sign.
 *
 * WHY AN UNBOUNDED LIMIT IS AN OPEN ARROW WITH THE WORD SPELLED OUT. The serialiser maps a
 * non-finite interval endpoint to null, and the previous panel rendered that through a formatter
 * that returns an em-dash — visually identical to a limit that failed to compute. "The upper limit
 * could be arbitrarily large" and "we have no upper limit" call for different responses from a
 * reader, so an unbounded endpoint is drawn as an open arrow running off the axis AND printed as the
 * literal word "unbounded" in the numeric readout, so the encoding does not depend on the reader
 * noticing an arrowhead.
 *
 * WHY THERE IS NO CLUSTER-COUNT ASTERISK ANY MORE. The panel this replaces held its own copy of
 * MIN_RELIABLE_CLUSTERS = 40 in JavaScript, with a comment asking a future reader to keep it in step
 * with edges.py, and marked any row below it as "resolved*" with the explanation behind a hover
 * tooltip. Both halves of that were wrong by the time this was written. The constant in edges.py is
 * no longer a floor at all: it is a SWITCH between two estimators, so that at or above forty
 * clusters the cluster-robust (CR0) interval is reported directly, and below it the interval and the
 * p-value come from a wild cluster bootstrap-t with Rademacher weights imposed under the null. A
 * duplicated constant in the frontend cannot express a switch, and the payload carries no structured
 * field naming which estimator ran. What the payload does carry is each edge's own `note`, written
 * by the module, which states the estimator, the cluster unit and the cluster count in words. That
 * sentence is therefore printed verbatim beside each edge, and no threshold is recomputed here. A
 * tooltip would also have been the wrong home for it regardless, because this page prints and a
 * tooltip does not.
 */
import { Card, Divider, Grid } from "@mui/material";
import MDBox from "components/MDBox";
import MDTypography from "components/MDTypography";

import PAL from "./palette";
import StateTrack from "./StateTrack";
import { TRACKS, coherenceReading } from "./stateTracks";
import { ciBound, fmtNum, fmtP, parseSignPattern } from "./deployFormat";

// What each edge measures, and the units its estimate carries. Held here rather than derived from
// the payload's `scale` field because `scale` names the power scale the estimate was computed on
// ("power_linear", "mA") and not the units of the slope itself.
const EDGE_META = {
  E1: {
    from: "Amplitude", to: "Band power",
    question: "can the device move the signal?",
    units: "LFP power per mA",
    rising: "band power RISES as amplitude rises",
    falling: "band power FALLS as amplitude rises",
  },
  E2: {
    from: "Band power", to: "Pain",
    question: "does the signal track the patient?",
    units: "pain points per unit of LFP power",
    rising: "pain RISES as band power rises",
    falling: "pain FALLS as band power rises",
  },
  E3: {
    from: "Amplitude", to: "Pain",
    question: "does the therapy work?",
    units: "pain points per mA",
    rising: "pain RISES as amplitude rises",
    falling: "pain FALLS as amplitude rises",
  },
};

const edgeInk = (e) => (e && e.resolved ? PAL.accent : PAL.neutral);

/**
 * The triangle as a graph. Amplitude sits at the lower left, band power at the apex and pain at the
 * lower right, so E1 and E2 form the two sides that compose and E3 is the base they have to
 * reproduce. That placement is the argument the panel is making, drawn as geometry.
 */
function TriangleGraph({ edges }) {
  const W = 330;
  const H = 210;
  const N = { amp: [46, 168], pow: [165, 34], pain: [284, 168] };
  const nodeR = 5;

  // Each edge runs between two node centres, shortened at both ends so the stroke does not run
  // under the node marker or the label.
  const seg = (a, b, trim = 16) => {
    const dx = b[0] - a[0];
    const dy = b[1] - a[1];
    const L = Math.sqrt(dx * dx + dy * dy) || 1;
    const ux = dx / L;
    const uy = dy / L;
    return [[a[0] + ux * trim, a[1] + uy * trim], [b[0] - ux * trim, b[1] - uy * trim]];
  };

  const EDGES = [
    { k: "E1", a: N.amp, b: N.pow, lx: 74, ly: 96, anchor: "start" },
    { k: "E2", a: N.pow, b: N.pain, lx: 256, ly: 96, anchor: "end" },
    { k: "E3", a: N.amp, b: N.pain, lx: 165, ly: 192, anchor: "middle" },
  ];

  return (
    <svg width="100%" viewBox={`0 0 ${W} ${H}`} role="img"
      aria-label="The amplitude, band power and pain triangle">
      <defs>
        {/* One arrowhead per ink, because a marker cannot inherit the stroke colour of its line in
            every browser. Only a resolved edge is ever drawn with one. */}
        <marker id="cle-head-accent" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6"
          markerHeight="6" orient="auto-start-reverse">
          <path d="M 0 0 L 10 5 L 0 10 z" fill={PAL.accent} />
        </marker>
      </defs>

      {EDGES.map((E) => {
        const e = edges && edges[E.k];
        const [p0, p1] = seg(E.a, E.b);
        const mid = [(p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2];
        const resolved = !!(e && e.resolved);
        const ink = edgeInk(e);
        const sign = e && e.sign != null ? Number(e.sign) : null;
        return (
          <g key={E.k}>
            <line x1={p0[0]} y1={p0[1]} x2={p1[0]} y2={p1[1]} stroke={ink}
              strokeWidth="2.2"
              strokeDasharray={resolved ? undefined : "5 3"}
              markerEnd={resolved ? "url(#cle-head-accent)" : undefined} />
            {/* An unresolved edge carries a hollow diamond with a question mark at its midpoint:
                a placeholder for a sign, in the position a sign would occupy. */}
            {!resolved ? (
              <g>
                <rect x={mid[0] - 7} y={mid[1] - 7} width="14" height="14" fill="#FFFFFF"
                  stroke={PAL.neutral} strokeWidth="1.6"
                  transform={`rotate(45 ${mid[0]} ${mid[1]})`} />
                <text x={mid[0]} y={mid[1] + 3.6} textAnchor="middle" fontSize="9.5"
                  fontWeight="700" fill={PAL.neutral}>?</text>
              </g>
            ) : null}
            <text x={E.lx} y={E.ly} textAnchor={E.anchor} fontSize="10.5" fontWeight="700"
              fill={ink}>{E.k}</text>
            <text x={E.lx} y={E.ly + 11} textAnchor={E.anchor} fontSize="9" fill="#6A6A6A">
              {resolved
                ? (sign > 0 ? "positive" : sign < 0 ? "negative" : "sign not reported")
                : "direction not established"}
            </text>
          </g>
        );
      })}

      {[["amp", "Amplitude", "mA", "middle", 0, 22],
        ["pow", "Band power", "LFP power", "middle", 0, -14],
        ["pain", "Pain", "0\u201310 rating", "middle", 0, 22]].map(([key, label, unit, anchor,
        ox, oy]) => (
          <g key={key}>
            <circle cx={N[key][0]} cy={N[key][1]} r={nodeR} fill="#2A2A2A" />
            <text x={N[key][0] + ox} y={N[key][1] + oy} textAnchor={anchor} fontSize="11"
              fontWeight="700" fill="#2A2A2A">{label}</text>
            <text x={N[key][0] + ox} y={N[key][1] + oy + 11} textAnchor={anchor} fontSize="9"
              fill="#7A7A7A">{unit}</text>
          </g>
      ))}
    </svg>
  );
}

/**
 * One signed axis for one edge. Zero sits at the same horizontal position in every row, which is
 * the only thing shared between the three rows; the scale is per row because the units are.
 */
function EdgeAxis({ k, e }) {
  const W = 340;
  const H = 58;
  const x0 = 8;
  const x1 = W - 8;
  const zero = (x0 + x1) / 2;
  const meta = EDGE_META[k] || {};
  const lo = ciBound(e && e.ci, 0);
  const hi = ciBound(e && e.ci, 1);
  const est = e && Number.isFinite(Number(e.estimate)) ? Number(e.estimate) : null;
  const resolved = !!(e && e.resolved);
  const ink = edgeInk(e);

  // The half-span is set by the largest finite magnitude the row has to show, with headroom so a
  // point marker never sits on the frame. An unbounded endpoint contributes nothing to the span —
  // it is drawn as an arrow leaving the axis instead, because no finite scale can contain it.
  const mags = [est, lo.unbounded ? null : lo.value, hi.unbounded ? null : hi.value]
    .filter((v) => v != null).map(Math.abs);
  const span = (mags.length ? Math.max(...mags) : 1) * 1.35 || 1;
  const px = (v) => zero + (v / span) * ((x1 - x0) / 2);

  const yAxis = 34;
  const loX = lo.unbounded ? x0 : px(lo.value);
  const hiX = hi.unbounded ? x1 : px(hi.value);

  const readout = e == null ? "not estimated"
    : `${fmtNum(est, 4)}  [${lo.unbounded ? "unbounded" : fmtNum(lo.value, 4)}, `
      + `${hi.unbounded ? "unbounded" : fmtNum(hi.value, 4)}]  p = ${fmtP(e.p)}`;

  return (
    <MDBox mb={0.6}>
      <MDBox display="flex" flexDirection="row" alignItems="baseline" gap={0.8} flexWrap="wrap">
        <MDTypography variant="caption" sx={{ fontSize: 11, fontWeight: "bold", color: ink }}>
          {k}
        </MDTypography>
        <MDTypography variant="caption" sx={{ fontSize: 10.5, color: "#4A4A4A" }}>
          {`${meta.from} \u2192 ${meta.to} \u00B7 ${meta.question}`}
        </MDTypography>
        <MDTypography variant="caption" sx={{ fontSize: 10, fontWeight: "bold",
          color: resolved ? PAL.accent : PAL.neutral, letterSpacing: 0.3 }}>
          {resolved ? "DIRECTION ESTABLISHED" : "DIRECTION NOT ESTABLISHED"}
        </MDTypography>
      </MDBox>

      <svg width="100%" viewBox={`0 0 ${W} ${H}`} role="img"
        aria-label={`${k} estimate and interval, on its own axis with zero aligned`}>
        <defs>
          <marker id={`cle-open-${k}`} viewBox="0 0 10 10" refX="2" refY="5" markerWidth="7"
            markerHeight="7" orient="auto-start-reverse">
            <path d="M 9 0 L 1 5 L 9 10" fill="none" stroke={ink} strokeWidth="1.6" />
          </marker>
        </defs>

        {/* The axis, then the zero reference. Zero is at the same x in all three rows. */}
        <line x1={x0} y1={yAxis} x2={x1} y2={yAxis} stroke="rgba(0,0,0,0.18)" strokeWidth="1" />
        <line x1={zero} y1={yAxis - 15} x2={zero} y2={yAxis + 11} stroke="#2A2A2A"
          strokeWidth="1.2" />
        <text x={zero} y={yAxis + 22} textAnchor="middle" fontSize="9" fill="#6A6A6A">0</text>

        {/* The interval. An unbounded end leaves the axis as an open arrow rather than stopping at
            the frame, so it cannot be read as an interval that happens to end there. */}
        {e ? (
          <line x1={loX} y1={yAxis} x2={hiX} y2={yAxis} stroke={ink} strokeWidth="3.4"
            markerStart={lo.unbounded ? `url(#cle-open-${k})` : undefined}
            markerEnd={hi.unbounded ? `url(#cle-open-${k})` : undefined} />
        ) : null}

        {/* The point estimate: filled when the direction is established, hollow when it is not, so
            a point estimate cannot be read as a result. */}
        {est != null ? (
          <circle cx={px(est)} cy={yAxis} r="5"
            fill={resolved ? ink : "#FFFFFF"} stroke={ink} strokeWidth="2" />
        ) : null}

        {/* The words at the terminal, for an unbounded limit. */}
        {hi.unbounded ? (
          <text x={x1 - 4} y={yAxis - 8} textAnchor="end" fontSize="9" fill={ink}>
            upper limit unbounded
          </text>
        ) : null}
        {lo.unbounded ? (
          <text x={x0 + 4} y={yAxis - 8} textAnchor="start" fontSize="9" fill={ink}>
            lower limit unbounded
          </text>
        ) : null}

        <text x={x0} y={12} fontSize="9" fill="#7A7A7A">{meta.units}</text>
      </svg>

      <MDTypography variant="caption" sx={{ display: "block", fontSize: 10.5,
        fontFamily: PAL.mono, color: "#2A2A2A" }}>
        {readout}
      </MDTypography>
      {e ? (
        <MDTypography variant="caption" sx={{ display: "block", fontSize: 10.5, color: "#4A4A4A" }}>
          {`${e.n} observations in ${e.n_clusters} ${e.cluster_unit}`}
          {e.n_clusters === 1 ? "" : " clusters"}
          {e.sign != null
            ? ` \u00B7 ${Number(e.sign) > 0 ? meta.rising : meta.falling}`
            : ""}
        </MDTypography>
      ) : null}
      {/* The module's own sentence about how this estimate was made, printed rather than
          reconstructed. It names the estimator and the cluster count, which is what the removed
          asterisk was gesturing at. */}
      {e && e.note ? (
        <MDTypography variant="caption" sx={{ display: "block", fontSize: 10.5, color: "#6A6A6A",
          mt: 0.2 }}>
          {e.note}
        </MDTypography>
      ) : null}
      {e && e.confounded_by && e.confounded_by.length > 0 ? (
        <MDTypography variant="caption" sx={{ display: "block", fontSize: 10.5,
          color: PAL.warnText }}>
          {`Confounded by: ${e.confounded_by.join(", ")}.`}
        </MDTypography>
      ) : null}
    </MDBox>
  );
}

/**
 * The two questions the coherence answer has to keep apart, each answered in its own row.
 *
 * This is the part of the panel that the RCS08 state made necessary. The three edges there are all
 * resolved and their signs compose consistently — raising amplitude raises band power, higher band
 * power goes with LESS pain, and raising amplitude reduces pain — so the physiology the three edges
 * describe is internally coherent. What fails is the separate question of whether that physiology is
 * the physiology the device's control law assumes. Dual Threshold ramps amplitude UP when band power
 * rises above the upper threshold, because the control law assumes power FALLS as amplitude rises
 * and therefore reads high power as insufficient stimulation; on a band whose power rises with
 * amplitude the device would ramp up, drive power higher, and ramp again.
 *
 * Reporting one red "incoherent" for both would be wrong in a way that changes what a reader does.
 * "The three edges disagree with each other" says the measurements are not yet trustworthy and the
 * remedy is more or better measurement. "The three edges agree with each other and are anti-aligned
 * with the control law" says the measurements are fine and the remedy is a different band, a
 * different hemisphere, or a mode whose control law runs the other way. Those are different people
 * doing different things.
 */
function CoherenceReading({ coherence, edges }) {
  if (!coherence) return null;
  const expected = parseSignPattern(coherence.expected_pattern);
  const observedRaw = parseSignPattern(coherence.observed_pattern);
  // Prefer the coherence block's own observed pattern, and fall back to the signs on the edges
  // themselves if it is absent, so the comparison table still renders when only one of the two
  // sources is present.
  const observed = {};
  ["E1", "E2", "E3"].forEach((k) => {
    const fromEdge = edges && edges[k] && edges[k].sign != null ? Number(edges[k].sign) : null;
    observed[k] = observedRaw[k] != null ? observedRaw[k] : fromEdge;
  });
  const r = coherenceReading(observed, expected);

  const word = (s) => (s == null ? "not reported" : Number(s) > 0 ? "positive (+)" : "negative (\u2212)");

  return (
    <MDBox mt={1}>
      {/* The per-edge comparison, which is the evidence for the two statements below it. */}
      <MDBox display="flex" flexDirection="row" py={0.3}>
        {[["18%", "edge"], ["30%", "sign observed"], ["30%", "sign the control law needs"],
          ["22%", ""]].map(([w, h]) => (
            <MDBox key={`h${w}${h}`} width={w}>
              <MDTypography variant="caption" sx={{ fontSize: 9.5, fontWeight: "bold",
                letterSpacing: 0.3, color: "#8A8A8A" }}>{h.toUpperCase()}</MDTypography>
            </MDBox>
        ))}
      </MDBox>
      {["E1", "E2", "E3"].map((k) => {
        const bad = r.mismatchedEdges.indexOf(k) >= 0;
        return (
          <MDBox key={`cmp-${k}`} display="flex" flexDirection="row" py={0.25}
            sx={{ borderTop: "1px solid rgba(0,0,0,0.07)" }}>
            <MDBox width="18%">
              <MDTypography variant="caption" sx={{ fontSize: 11, fontWeight: "bold" }}>
                {k}
              </MDTypography>
            </MDBox>
            <MDBox width="30%">
              <MDTypography variant="caption" sx={{ fontSize: 11, fontFamily: PAL.mono,
                color: bad ? PAL.fail : "#2A2A2A" }}>{word(observed[k])}</MDTypography>
            </MDBox>
            <MDBox width="30%">
              <MDTypography variant="caption" sx={{ fontSize: 11, fontFamily: PAL.mono,
                color: "#2A2A2A" }}>{word(expected[k])}</MDTypography>
            </MDBox>
            <MDBox width="22%">
              <MDTypography variant="caption" sx={{ fontSize: 10, fontWeight: "bold",
                color: bad ? PAL.fail : PAL.pass }}>
                {observed[k] == null || expected[k] == null ? "" : bad ? "OPPOSITE" : "AS NEEDED"}
              </MDTypography>
            </MDBox>
          </MDBox>
        );
      })}

      {/* The two statements, computed from the signs above rather than asserted. */}
      <MDBox mt={1} p={1} sx={{ borderRadius: "4px", backgroundColor: PAL.neutralFill,
        border: `1px solid ${PAL.neutralBorder}` }}>
        <MDTypography variant="caption" sx={{ display: "block", fontSize: 11.5, color: "#2A2A2A" }}>
          <b>{"Do the three edges agree with each other?  "}</b>
          {!r.haveAllSigns
            ? "Cannot be answered: at least one edge has no reported sign, so the composition "
              + "cannot be checked."
            : r.edgesAgreeInternally
              ? "Yes. Composing the amplitude-to-power and power-to-pain edges reproduces the sign "
                + "of the amplitude-to-pain edge, so the three measurements tell one "
                + "self-consistent story about the physiology."
              : "No. Composing the amplitude-to-power and power-to-pain edges does not reproduce "
                + "the sign of the amplitude-to-pain edge, so the three measurements are not "
                + "describing one consistent relationship and at least one of them is unreliable."}
        </MDTypography>
        <MDTypography variant="caption" sx={{ display: "block", fontSize: 11.5, mt: 0.6,
          color: "#2A2A2A" }}>
          <b>{"Are those signs the ones the device's control law assumes?  "}</b>
          {!r.haveAllSigns
            ? "Cannot be answered while a sign is missing."
            : r.matchesControlLaw
              ? "Yes. Every edge has the sign the selected control law requires."
              : `No. ${r.mismatchedEdges.join(" and ")} `
                + `${r.mismatchedEdges.length === 1 ? "has" : "have"} the opposite sign to the one `
                + "the selected control law requires."}
        </MDTypography>
        {r.haveAllSigns && r.edgesAgreeInternally && !r.matchesControlLaw ? (
          <MDTypography variant="caption" sx={{ display: "block", fontSize: 11.5, mt: 0.6,
            color: PAL.warnText }}>
            {"Read those two answers together, because the combination is the finding and it is not "
              + "the same as either one alone. The measurements are not in conflict with each "
              + "other; they are in conflict with what the device would do with them. The remedy "
              + "is therefore a different band, a different hemisphere, or a control law that runs "
              + "the other way \u2014 not more measurement of this one."}
          </MDTypography>
        ) : null}
      </MDBox>

      {/* The module's own note, verbatim, because it names the control-law page citation. */}
      {coherence.note ? (
        <MDTypography variant="caption" sx={{ display: "block", fontSize: 11, mt: 0.8,
          color: "#4A4A4A" }}>
          {coherence.note}
        </MDTypography>
      ) : null}
      <MDTypography variant="caption" sx={{ display: "block", fontSize: 10.5, mt: 0.4,
        color: "#8A8A8A" }}>
        {coherence.p_coherent != null
          ? `Bootstrap probability that the sign pattern holds: ${fmtNum(coherence.p_coherent, 3)}`
            + `${coherence.n_boot ? `, from ${coherence.n_boot} replications.` : "."}`
          : "No bootstrap probability is reported for this sign pattern, so the answer above rests "
            + "on the point signs rather than on a resampled distribution over them."}
      </MDTypography>
    </MDBox>
  );
}

export default function EvidenceTrianglePanel({ report }) {
  const { data, loading, err } = report || { data: null, loading: false, err: null };

  if (loading) {
    return (
      <Card><MDBox p={2}>
        <MDTypography variant="button">Estimating the three edges…</MDTypography>
      </MDBox></Card>
    );
  }
  if (!data) {
    return (
      <Card><MDBox p={2}>
        <MDTypography variant="h6" sx={{ fontSize: 15 }}>
          The evidence triangle: amplitude, band power and pain
        </MDTypography>
        <MDTypography variant="caption" sx={{ display: "block", fontSize: 11.5,
          color: PAL.neutral }}>
          {`The three edges have not been estimated for this configuration${err ? ` (${err})` : ""}.`}
        </MDTypography>
      </MDBox></Card>
    );
  }

  const edges = data.edges || {};

  return (
    <Card>
      <MDBox p={2}>
        <MDTypography variant="h6" sx={{ fontSize: 15 }}>
          The evidence triangle: amplitude, band power and pain
        </MDTypography>
        <MDTypography variant="caption" sx={{ display: "block", fontSize: 11.5, color: "#4A4A4A" }}>
          Three measured relationships and one question about them. The amplitude-to-power and
          power-to-pain edges compose to predict the amplitude-to-pain edge, so their signs have to
          agree with each other, and separately they have to be the signs the selected control law
          assumes.
        </MDTypography>

        <Grid container spacing={2} mt={0.5}>
          <Grid item xs={12} md={5}>
            <TriangleGraph edges={edges} />
            <MDTypography variant="caption" sx={{ display: "block", fontSize: 10.5,
              color: "#8A8A8A", mt: 0.5 }}>
              A solid line with an arrowhead is an edge whose direction the data established. A
              dotted line with a hollow diamond is an edge that was estimated and whose direction
              the data did not establish; it is drawn at full weight because it is present and
              undetermined, not absent and not zero.
            </MDTypography>
          </Grid>
          <Grid item xs={12} md={7}>
            {["E1", "E2", "E3"].map((k) => <EdgeAxis key={k} k={k} e={edges[k]} />)}
            <MDTypography variant="caption" sx={{ display: "block", fontSize: 10.5,
              color: "#8A8A8A" }}>
              Each edge has its own axis and its own units because the three quantities are not
              comparable in magnitude. Only zero is aligned across the three, which is what makes
              the sign comparison below readable.
            </MDTypography>
          </Grid>
        </Grid>

        <Divider sx={{ my: 1.2 }} />

        <StateTrack track={TRACKS.coherence} data={data} />
        <CoherenceReading coherence={data.coherence} edges={edges} />
      </MDBox>
    </Card>
  );
}
