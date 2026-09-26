/**
 * "Does the evidence hang together?" -- the three measured links (SPEC 2026-09-26 section 5.2 item 5).
 *
 * THE REDESIGN OF 2026-09-26. The triangle drawing and the four-column sign table are gone. In their
 * place: one answer sentence; three aligned dot-and-interval strips, "Current → band power", "Band
 * power → pain" and "Current → pain", zero at the same place in each, the value and its 95% range
 * printed at the dot, a hollow dot where the range crosses zero; one sentence per link saying whether
 * its sign is the one the device's automatic adjustment assumes; and one fold holding the counts, the
 * reading with the current taken out (its words unchanged), and how the sign agreement was tested.
 * The history below explains choices that still hold (three separate scales, zero aligned, an
 * unbounded end drawn as an open arrow and spelled out, the module's own estimator sentence printed).
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
 * direction, and an edge with no point estimate has none. Withholding the arrowhead withholds the
 * assertion. Drawing the line at full weight and full length is equally deliberate: an unresolved
 * edge must read as present but undetermined, never as absent and never as zero, so it keeps its
 * full stroke and gains a hollow diamond carrying a question mark at its midpoint — a visible
 * placeholder for a sign rather than a sign.
 *
 * WHAT "RESOLVED" MEANS SINCE 2026-09-13. PI rule, his words: "Established means mean only for
 * flexibility", read as "point sign decides, but flag as provisional". `resolved` on the payload is
 * now the point sign (the estimate is finite and non-zero); whether the interval excludes zero is
 * the separate flag `statistically_established`. So an edge whose interval spans zero is drawn WITH
 * an arrowhead (it has a direction) and with a HOLLOW point marker (the interval spans zero), and
 * its label reads the numbers -- "sign − (interval spans zero)" -- rather than an adjective. Until
 * that date such an edge was drawn as unresolved.
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
import { useEffect, useRef, useState } from "react";
import { Card } from "@mui/material";
import MDBox from "components/MDBox";
import MDTypography from "components/MDTypography";

import PAL from "./palette";
import { TYPE, CARD, STATE } from "assets/theme/base/tokens";
import { SVG_TEXT } from "views/Reports/figureStyle";
import StateTrack from "./StateTrack";
import Fold from "./Fold";
import { TRACKS, coherenceReading } from "./stateTracks";
import { ciBound, fmtNum, fmtP, parseSignPattern } from "./deployFormat";

// What each edge measures, and the units its estimate carries. Held here rather than derived from
// the payload's `scale` field because `scale` names the power scale the estimate was computed on
// ("power_linear", "mA") and not the units of the slope itself.
const EDGE_META = {
  E1: {
    name: "Current \u2192 band power",
    question: "can the device move the signal?",
    units: "band power per mA",
    rising: "band power rises as the current rises",
    falling: "band power falls as the current rises",
  },
  E2: {
    name: "Band power \u2192 pain",
    question: "does the signal track the patient?",
    units: "pain points per unit of band power",
    rising: "pain rises as band power rises",
    falling: "pain falls as band power rises",
  },
  E3: {
    name: "Current \u2192 pain",
    question: "does the therapy work?",
    units: "pain points per mA",
    rising: "pain rises as the current rises",
    falling: "pain falls as the current rises",
  },
};
/** The link's plain name, for sentences that used to say "E1". */
export const linkName = (k) => (EDGE_META[k] ? EDGE_META[k].name : k);
const joinNames = (ks) => ks.map(linkName).join(" and ");

const edgeInk = (e) => (e && e.resolved ? PAL.ink : PAL.ink3);
// Review 2026-09-15, finding C1: E1 is one of two different quantities and the payload says which
// (`edges.E1.source`). The screening statistic -- the setting-epoch slope over the whole record,
// confounded with time, whose own note says it cannot be read as the causal effect of current on
// power -- was drawn exactly like the pooled titration slope. It is now drawn dotted (a direction,
// but not a measurement) and labelled with the word, so a reader never has to open the fold.
const isScreening = (e) => !!(e && e.source === "screening_historical");
const SCREENING_DASH = "1.5 3.5";

/**
 * One signed axis for one edge. Zero sits at the same horizontal position in every row, which is
 * the only thing shared between the three rows; the scale is per row because the units are.
 */
// THE CURRENT IN FORCE, NOT YET TAKEN OUT OF THIS EDGE (decision 234, the PI's ruling of
// 2026-09-22). The band-power-to-pain edge is estimated with no term for the stimulation current
// that was running when each rating was filed. On this participant's LEFT lead that matters and is
// measured: taking the current out shrinks every positive reading in the band family below, so the
// sign this edge shows rests partly on the current. Scoped deliberately -- the left lead, and the
// centres the measurement covered -- because a caveat that fires everywhere teaches a reader to
// ignore it. It comes out when the edge itself is re-estimated with the current taken out.
export const CURRENT_CONFOUND_HZ = [21.5, 27.5];
export const CURRENT_CONFOUND_NOTE =
  "Measured 2026-09-22, on this participant\u2019s left lead: taking the stimulation current in "
  + "force at each rating out of both the band power and the pain score shrinks every positive "
  + "reading in this band family \u2014 on L 0\u207b3\u207a, 22.5\u201327.5 Hz, +0.08 to +0.20 "
  + "becomes +0.01 to +0.12 against NRS; on L 1\u207b3\u207a the negative readings strengthen. "
  + "This link is not adjusted for it yet, so read its sign as resting partly on the current.";

/**
 * The same edge read again with the stimulation current taken out of the band power.
 *
 * WHY IT SITS HERE AND NOT BEHIND A SWITCH. The interim sentence above could only say that the
 * current had not been taken out and quote what that did to a different page's numbers. This is
 * the measurement itself, on this band, from this report (panel D item 4, 2026-09-22). It is
 * printed as a comparison and never as a replacement: the plain reading above resolves the edge,
 * carries the interval the verdict reads, and sets the verdict (the PI, 2026-09-22).
 *
 * A refusal prints its reason. "Could not be made" and "made, and came out at coin flipping" are
 * different findings, and this project has confused an absent measurement for a negative one
 * before.
 */
function AdjustedEdgeLine({ adjusted }) {
  const a = adjusted || null;
  if (!a) return null;
  const n = (v, d = 3) => (v == null || !Number.isFinite(Number(v)) ? null : Number(v).toFixed(d));
  // The current in the server's words, never its column (decision 314): an answer saved before the
  // words were sent reads "the stimulation current in force".
  const what = `${a.adjusted_for_words || "the stimulation current"} in force`;
  if (!a.available || n(a.auc) == null) {
    return (
      <MDTypography variant="caption" data-testid="e2-adjusted"
        sx={{ ...TYPE.body, display: "block", mb: 1, color: PAL.ink2 }}>
        {`With ${what} taken out of the band power: not made here (${a.why || "no reason was "
          + "recorded"}). An absent reading, not one at chance.`}
      </MDTypography>
    );
  }
  const span = (n(a.auc_low) && n(a.auc_high)) ? `, interval ${n(a.auc_low)} to ${n(a.auc_high)}` : "";
  const reports = a.n_pain_reports ? `, over ${a.n_pain_reports} pain reports` : "";
  const pr = n(a.partial_r) != null
    ? ` Correlation after taking the current out ${Number(a.partial_r) >= 0 ? "+" : ""}${n(a.partial_r)}.`
    : "";
  return (
    <MDTypography variant="caption" data-testid="e2-adjusted"
      sx={{ ...TYPE.body, display: "block", mb: 1, color: PAL.ink2 }}>
      {`With ${what} taken out of the band power: ${n(a.auc)}${span}${reports} (0.5 is coin `
        + `flipping).${pr} It describes the reading above; that one sets the verdict.`}
    </MDTypography>
  );
}

export function currentConfoundApplies(candidate) {
  const ch = String((candidate || {}).channel || "").toUpperCase();
  const hz = Number((candidate || {}).center_hz);
  if (!/LEFT$/.test(ch) || !Number.isFinite(hz)) return false;
  return hz >= CURRENT_CONFOUND_HZ[0] && hz <= CURRENT_CONFOUND_HZ[1];
}

/** The element's real pixel width, so SVG text drawn at 12 px stays 12 px on screen. */
function useMeasuredWidth(fallback = 480) {
  const ref = useRef(null);
  const [w, setW] = useState(fallback);
  useEffect(() => {
    const el = ref.current;
    if (!el) return undefined;
    const read = () => { if (el.clientWidth > 0) setW(el.clientWidth); };
    read();
    if (typeof ResizeObserver === "undefined") return undefined;
    const ro = new ResizeObserver(read);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return [ref, w];
}

/** Whether the 95% range stays on one side of zero: the payload's own flag, else the interval. */
function isEstablished(e) {
  if (!e) return false;
  if (e.statistically_established != null) return !!e.statistically_established;
  const lo = ciBound(e.ci, 0);
  const hi = ciBound(e.ci, 1);
  return !!(!lo.unbounded && !hi.unbounded && lo.value != null && hi.value != null
    && ((lo.value > 0 && hi.value > 0) || (lo.value < 0 && hi.value < 0)));
}

/** "falls as the current rises; the range crosses zero, so not yet certain" (SPEC section 6). */
export function linkReading(k, e) {
  const meta = EDGE_META[k] || {};
  if (!e || !e.resolved) return "no estimate";
  const est = Number(e.estimate);
  const dir = est > 0 ? meta.rising : meta.falling;
  const sure = isEstablished(e)
    ? "the 95% range stays on one side of zero"
    : "the range crosses zero, so not yet certain";
  const screening = isScreening(e)
    ? "; a screening reading, read off the whole history, where current and time move together; "
      + "not a measured effect of current"
    : "";
  return `${dir.charAt(0).toUpperCase()}${dir.slice(1)}; ${sure}${screening}`;
}

/**
 * One link as a dot and its 95% range on its own scale. Zero sits at the same horizontal position in
 * every row, which is the only thing the three rows share: their units differ, so a magnitude
 * comparison between rows would mean nothing. Hollow dot: the range crosses zero.
 */
function LinkStrip({ k, e }) {
  const [ref, W] = useMeasuredWidth();
  const H = 44;
  const pad = 12;
  const x0 = pad;
  const x1 = Math.max(W - pad, x0 + 40);
  const zero = (x0 + x1) / 2;
  const meta = EDGE_META[k] || {};
  const lo = ciBound(e && e.ci, 0);
  const hi = ciBound(e && e.ci, 1);
  const est = e && Number.isFinite(Number(e.estimate)) ? Number(e.estimate) : null;
  const resolved = !!(e && e.resolved);
  const established = isEstablished(e);
  const ink = edgeInk(e);

  // The half-span is set by the largest finite magnitude the row has to show, with headroom so a
  // dot never sits on the frame. An unbounded end contributes nothing: it leaves the axis as an
  // open arrow instead, because no finite scale can contain it.
  const mags = [est, lo.unbounded ? null : lo.value, hi.unbounded ? null : hi.value]
    .filter((v) => v != null).map(Math.abs);
  const span = (mags.length ? Math.max(...mags) : 1) * 1.35 || 1;
  const px = (v) => zero + (v / span) * ((x1 - x0) / 2);
  const yAxis = 30;
  const loX = lo.unbounded ? x0 : px(lo.value);
  const hiX = hi.unbounded ? x1 : px(hi.value);
  const atDot = est == null ? null
    : `${fmtNum(est, 3)} (${lo.unbounded ? "unbounded" : fmtNum(lo.value, 3)} to `
      + `${hi.unbounded ? "unbounded" : fmtNum(hi.value, 3)})`;
  const dotX = est != null ? px(est) : zero;
  const anchor = dotX > x1 - 120 ? "end" : (dotX < x0 + 120 ? "start" : "middle");

  return (
    <MDBox py={1.5} sx={{ borderTop: `1px solid ${PAL.rule}` }}>
      <MDBox display="flex" alignItems="baseline" gap={1.5} flexWrap="wrap">
        <MDTypography component="h3" sx={{ ...TYPE.body, fontWeight: 600, color: PAL.ink }}>
          {meta.name}
        </MDTypography>
        <MDTypography sx={{ ...TYPE.caption, color: PAL.ink3 }}>
          {`${meta.question} · ${meta.units}`}
        </MDTypography>
      </MDBox>
      <div ref={ref} style={{ width: "100%" }}>
        <svg width={W} height={H} role="img" style={{ display: "block" }}
          aria-label={`${meta.name}: ${atDot || "no estimate"}, on its own scale with zero aligned`}>
          <defs>
            <marker id={`cle-open-${k}`} viewBox="0 0 10 10" refX="2" refY="5" markerWidth="7"
              markerHeight="7" orient="auto-start-reverse">
              <path d="M 9 0 L 1 5 L 9 10" fill="none" stroke={ink} strokeWidth="1.6" />
            </marker>
          </defs>
          <line x1={x0} y1={yAxis} x2={x1} y2={yAxis} stroke={PAL.rule} strokeWidth="1" />
          <line x1={zero} y1={yAxis - 10} x2={zero} y2={yAxis + 8} stroke={PAL.graphic} strokeWidth="1" />
          <text x={zero} y={yAxis + 14} textAnchor="middle" dominantBaseline="hanging"
            style={SVG_TEXT} fill={PAL.ink3} fontSize={PAL.fs.caption}>0</text>
          {/* The 95% range. A screening E1 is drawn finely dotted: a direction, not a measurement. */}
          {e && resolved ? (
            <line x1={loX} y1={yAxis} x2={hiX} y2={yAxis} stroke={ink} strokeWidth="2"
              data-edge={k} strokeDasharray={isScreening(e) ? SCREENING_DASH : undefined}
              markerStart={lo.unbounded ? `url(#cle-open-${k})` : undefined}
              markerEnd={hi.unbounded ? `url(#cle-open-${k})` : undefined} />
          ) : null}
          {est != null ? (
            <circle cx={dotX} cy={yAxis} r="5" fill={established ? ink : PAL.surface}
              stroke={ink} strokeWidth="1.5" />
          ) : null}
          <text x={dotX} y={yAxis - 12} textAnchor={anchor} style={SVG_TEXT} fontSize={PAL.fs.caption}
            fill={PAL.ink}>{atDot || "no estimate"}</text>
        </svg>
      </div>
      <MDTypography sx={{ ...TYPE.body, color: resolved && !established ? PAL.warnText : PAL.ink2 }}>
        {resolved && !established ? <span aria-hidden="true" style={{ marginRight: 6 }}>{STATE.caution.glyph}</span> : null}
        <span>{linkReading(k, e)}</span>
        {e && e.p != null ? <span style={{ color: PAL.ink3 }}>{` · p ${fmtP(e.p)}`}</span> : null}
      </MDTypography>
      {e && e.confounded_by && e.confounded_by.length > 0 ? (
        <MDTypography sx={{ ...TYPE.body, color: PAL.warnText }}>
          <span aria-hidden="true" style={{ marginRight: 6 }}>{STATE.caution.glyph}</span>
          {`Confounded by: ${e.confounded_by.join(", ")}.`}
        </MDTypography>
      ) : null}
    </MDBox>
  );
}

/** The counts behind one link, and the module's own sentence about how it was made. */
function LinkMethod({ k, e }) {
  if (!e) return null;
  const meta = EDGE_META[k] || {};
  return (
    <MDBox mb={1.5}>
      <MDTypography sx={{ ...TYPE.body, fontWeight: 600, color: PAL.ink }}>{meta.name}</MDTypography>
      <MDTypography sx={{ ...TYPE.body, color: PAL.ink2 }}>
        {/* Since 2026-09-11 E1 is the pooled titration slope (decision 9), whose unit is a run of
            stepped current (up or down) rather than a setting epoch; the sentence follows the unit. */}
        {/^run of (rising|stepped) current/.test(e.cluster_unit || "")
          ? `${e.n} settled points in ${e.n_clusters} run${e.n_clusters === 1 ? "" : "s"} of stepped current.`
          : `${e.n} readings from ${e.n_clusters} separate ${e.cluster_unit}`
            + `${e.n_clusters === 1 ? "" : " groups"}.`}
      </MDTypography>
      {e.note ? (
        <MDTypography sx={{ ...TYPE.body, color: PAL.ink2 }}>{e.note}</MDTypography>
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
/** The observed and required signs, and the reading computed from them. */
function readCoherence(coherence, edges) {
  const expected = parseSignPattern(coherence && coherence.expected_pattern);
  const observedRaw = parseSignPattern(coherence && coherence.observed_pattern);
  // Prefer the coherence block's own observed pattern, and fall back to the signs on the edges
  // themselves if it is absent, so the comparison still renders when only one source is present.
  const observed = {};
  ["E1", "E2", "E3"].forEach((k) => {
    const fromEdge = edges && edges[k] && edges[k].sign != null ? Number(edges[k].sign) : null;
    observed[k] = observedRaw[k] != null ? observedRaw[k] : fromEdge;
  });
  return { observed, expected, r: coherenceReading(observed, expected) };
}

/** The answer under the title, in one sentence, computed from the signs rather than asserted. */
export function evidenceAnswer(coherence, edges) {
  if (!coherence) return "The sign agreement has not been tested for this band.";
  const { r } = readCoherence(coherence, edges);
  if (!r.haveAllSigns) {
    return "Cannot tell yet: at least one link has no estimate, so the three cannot be checked "
      + "against each other.";
  }
  if (r.edgesAgreeInternally && r.matchesControlLaw) {
    return "Yes: the three links agree with each other and with what the device's automatic "
      + "adjustment assumes.";
  }
  if (r.edgesAgreeInternally) {
    return "The three links agree with each other, but not with what the device's automatic "
      + "adjustment assumes.";
  }
  return "No: the three links do not agree with each other, so at least one of them is unreliable.";
}

/**
 * The two questions the answer has to keep apart, and one sentence per link.
 *
 * "The three links disagree with each other" says the measurements are not yet trustworthy and the
 * remedy is more or better measurement. "The three links agree with each other and are the wrong
 * way round for the device's automatic adjustment" says the measurements are fine and the remedy is
 * a different band, a different side, or a mode whose adjustment runs the other way. Those are
 * different people doing different things, so the two are answered separately.
 */
function CoherenceReading({ coherence, edges }) {
  if (!coherence) return null;
  const { observed, expected, r } = readCoherence(coherence, edges);
  const word = (v) => (v == null ? "no sign" : Number(v) > 0 ? "rises (+)" : "falls (\u2212)");

  return (
    <MDBox mt={2}>
      <MDBox component="ul" sx={{ listStyle: "none", m: 0, p: 0 }} data-testid="link-sentences">
        {["E1", "E2", "E3"].map((k) => {
          const bad = r.mismatchedEdges.indexOf(k) >= 0;
          const known = observed[k] != null && expected[k] != null;
          return (
            <MDBox component="li" key={`cmp-${k}`} sx={{ ...TYPE.body, color: PAL.ink2, py: 0.25 }}>
              <span aria-hidden="true" style={{ display: "inline-block", width: "1.4em",
                color: !known ? PAL.ink3 : (bad ? PAL.warnText : PAL.ink) }}>
                {!known ? STATE.notChecked.glyph : (bad ? STATE.caution.glyph : STATE.pass.glyph)}
              </span>
              <b style={{ fontWeight: 600, color: PAL.ink }}>{linkName(k)}</b>
              {`: measured ${word(observed[k])}; the automatic adjustment assumes ${word(expected[k])}`}
              {known ? (bad ? ", the opposite." : ", as it needs.") : "."}
            </MDBox>
          );
        })}
      </MDBox>

      <MDTypography sx={{ ...TYPE.body, color: PAL.ink, mt: 1.5, maxWidth: "68ch" }}>
        <b style={{ fontWeight: 600 }}>{"Do the three links agree with each other? "}</b>
        {!r.haveAllSigns
          ? "Cannot be answered: at least one link has no sign, so the combination cannot be checked."
          : r.edgesAgreeInternally
            ? "Yes. Combining current \u2192 band power with band power \u2192 pain reproduces the "
              + "sign of current \u2192 pain."
            : "No. Combining current \u2192 band power with band power \u2192 pain does not reproduce "
              + "the sign of current \u2192 pain: at least one of them is unreliable."}
      </MDTypography>
      <MDTypography sx={{ ...TYPE.body, color: PAL.ink, mt: 1, maxWidth: "68ch" }}>
        <b style={{ fontWeight: 600 }}>{"Are those signs the ones the device's automatic adjustment assumes? "}</b>
        {!r.haveAllSigns
          ? "Cannot be answered while a sign is missing."
          : r.matchesControlLaw
            ? "Yes. Every link has the sign the selected mode needs."
            : `No. ${joinNames(r.mismatchedEdges)} `
              + `${r.mismatchedEdges.length === 1 ? "has" : "have"} the opposite sign to the one `
              + "the selected mode needs."}
      </MDTypography>
      {r.haveAllSigns && r.edgesAgreeInternally && !r.matchesControlLaw ? (
        <MDTypography sx={{ ...TYPE.body, color: PAL.warnText, mt: 1, maxWidth: "68ch" }}>
          <span aria-hidden="true" style={{ marginRight: 6 }}>{STATE.caution.glyph}</span>
          {"Read those two answers together. The measurements are not in conflict with each "
            + "other; they are in conflict with what the device would do with them. The remedy "
            + "is therefore a different band, a different side, or a mode whose adjustment runs "
            + "the other way \u2014 not more measurement of this one."}
        </MDTypography>
      ) : null}
    </MDBox>
  );
}

/** The module's own note about the sign test, both halves, and the resampling behind it. */
function SignTestMethod({ coherence }) {
  if (!coherence) return null;
  const noteText = coherence.note || "";
  const cut = noteText.search(/PROVISIONAL\s*:/i);
  const provisionalHalf = cut >= 0 ? noteText.slice(cut).trim() : null;
  const restOfNote = cut >= 0 ? noteText.slice(0, cut).trim() : (noteText || null);
  return (
    <MDBox mt={2}>
      <MDTypography sx={{ ...TYPE.body, fontWeight: 600, color: PAL.ink }}>
        How the sign agreement was tested
      </MDTypography>
      {provisionalHalf ? (
        <MDTypography sx={{ ...TYPE.body, color: PAL.ink2 }}>{provisionalHalf}</MDTypography>
      ) : null}
      {restOfNote ? (
        <MDTypography sx={{ ...TYPE.body, color: PAL.ink2, mt: 0.5 }}>{restOfNote}</MDTypography>
      ) : null}
      <MDTypography sx={{ ...TYPE.body, color: PAL.ink2, mt: 0.5 }}>
        {coherence.p_coherent != null
          ? `Chance, over resampled data, that the sign pattern holds: ${fmtNum(coherence.p_coherent, 3)}`
            + `${coherence.n_boot ? `, from ${coherence.n_boot} resamples.` : "."}`
          : "No resampled probability is reported for this sign pattern, so the answer above rests "
            + "on the point signs rather than on a resampled spread of them."}
      </MDTypography>
    </MDBox>
  );
}

export default function EvidenceTrianglePanel({ report }) {
  const { data, loading, err } = report || { data: null, loading: false, err: null };
  // Which band this report is about, for the scope of the caveat under the second link.
  const candidate = ((data || {}).candidates || [])[0] || null;
  const showCurrentConfound = currentConfoundApplies(candidate);
  const title = (
    <MDTypography component="h2" sx={{ ...TYPE.title, color: PAL.ink }}>
      Does the evidence hang together?
    </MDTypography>
  );

  if (loading) {
    return (
      <Card sx={{ ...CARD, p: 3 }}>
        {title}
        <MDTypography sx={{ ...TYPE.lead, color: PAL.ink2, mt: 1 }}>Measuring the three links…</MDTypography>
      </Card>
    );
  }
  if (!data) {
    return (
      <Card sx={{ ...CARD, p: 3 }}>
        {title}
        <MDTypography sx={{ ...TYPE.lead, color: PAL.ink2, mt: 1 }}>
          {`The three links have not been measured for this configuration${err ? ` (${err})` : ""}.`}
        </MDTypography>
      </Card>
    );
  }

  const edges = data.edges || {};

  return (
    <Card sx={{ ...CARD, p: 3 }}>
      {title}
      <MDTypography data-testid="evidence-answer" sx={{ ...TYPE.lead, color: PAL.ink, mt: 1, maxWidth: "68ch" }}>
        {evidenceAnswer(data.coherence, edges)}
      </MDTypography>
      <MDTypography sx={{ ...TYPE.caption, color: PAL.ink3, mt: 0.5 }}>
        {"Three measured links, each on its own scale with zero lined up; a hollow dot means its "
          + "95% range crosses zero."}
        {data.pain_score && data.pain_score.key ? (
          <span data-testid="triangle-pain-score">
            {` Pain score: ${data.pain_score.label || data.pain_score.key}.`}
          </span>
        ) : null}
      </MDTypography>

      <MDBox mt={2}>
        <StateTrack track={TRACKS.coherence} data={data} showBlurb={false} dense />
      </MDBox>

      <MDBox mt={2}>
        {["E1", "E2", "E3"].map((k) => (
          <MDBox key={k}>
            <LinkStrip k={k} e={edges[k]} />
            {/* The interim sentence only while the report carries no adjusted reading, so the page
                never says "not adjusted for it yet" beside a number that has been adjusted. */}
            {k === "E2" && showCurrentConfound && !(edges.E2 && edges.E2.adjusted) ? (
              <MDTypography variant="caption" data-testid="e2-current-confound"
                sx={{ ...TYPE.body, display: "block", mb: 1, color: PAL.warnText, maxWidth: "68ch" }}>
                <span aria-hidden="true" style={{ marginRight: 6 }}>{STATE.caution.glyph}</span>
                {CURRENT_CONFOUND_NOTE}
              </MDTypography>
            ) : null}
          </MDBox>
        ))}
      </MDBox>

      <CoherenceReading coherence={data.coherence} edges={edges} />

      <MDBox mt={2}>
        <Fold show="How this was worked out (counts, the reading with the current taken out, how the sign agreement was tested)"
          hide="Hide how this was worked out" mt={0}>
          {["E1", "E2", "E3"].map((k) => <LinkMethod key={k} k={k} e={edges[k]} />)}
          {edges.E2 && edges.E2.adjusted ? (
            <MDBox mb={1.5}>
              <MDTypography sx={{ ...TYPE.body, fontWeight: 600, color: PAL.ink }}>
                Band power → pain, read again with the current taken out
              </MDTypography>
              <AdjustedEdgeLine adjusted={edges.E2.adjusted} />
            </MDBox>
          ) : null}
          <SignTestMethod coherence={data.coherence} />
          <MDTypography sx={{ ...TYPE.body, color: PAL.ink2, mt: 2, maxWidth: "68ch" }}>
            How to read the strips: each link has its own scale and its own units, because the three
            quantities are not comparable in size; only zero is lined up, which is what makes the
            signs comparable by eye. A filled dot means the 95% range stays on one side of zero; a
            hollow dot means it crosses zero, so the sign rests on the point value alone. An open
            arrow at an end means that end of the range is unbounded. A finely dotted range on
            current → band power marks a screening reading, read off the whole history where
            current and time move together; it is replaced by the stepped-current measurement once
            one is stored for the band.
          </MDTypography>
        </Fold>
      </MDBox>
    </Card>
  );
}
