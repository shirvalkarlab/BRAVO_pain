/**
 * Figures for the saved checks against chance and against the current (first written 2026-09-24;
 * redrawn 2026-09-26 for the minimalist redesign, SPEC.md sections 3 and 7, WP4). Each draws only
 * what the saved result holds.
 *
 * How they are drawn (since 2026-10-02):
 *  - Plotly figures (`PlotlyChart`, specs in `plotSpecs.js`): hovering a mark prints its own numbers,
 *    taken from the saved result and nothing else; each x axis ends on a labelled tick;
 *  - no gridlines and no legend boxes: series are named by a label at their right end, and a
 *    reference line (zero, or 0.5 = coin toss) is named at its end;
 *  - colours come from the shared data colours; text is in the shared inks, and a series' own
 *    colour is used for its label only when that colour is dark enough to read (4.5:1 on white);
 *  - pain scores are printed with the page's own labels ("Left Leg VAS"), never as raw keys.
 */
import React, { useMemo, useState } from "react";

import { T, TYPE, SPACE, GLYPH } from "assets/theme/base/tokens";
import { SIDE, CONTEXT } from "assets/theme/base/dataColors";
import { painScoreLabel } from "views/Reports/painScores";

import PlotlyChart from "./PlotlyChart";
import {
  SERIES, GROUP_INK, pairName, zeroMaSpec, currentExplainsSpec, currentMemorySpec,
  regressionToMeanSpec, carryOverSpec, ratingPersistenceSpec, steppedCurrentSpec,
  bandDetectorResearchSpec, bandDeviceSpec,
} from "./plotSpecs";

export { pairName };

const CAPTION = { ...TYPE.body, color: T.ink3, marginTop: SPACE.xxs, maxWidth: "68ch" };
const BODY = { ...TYPE.body, color: T.ink2 };
const SELECT = {
  ...TYPE.body, color: T.ink, background: T.surface, border: `1.5px solid ${T.accent}`,
  borderRadius: 6, padding: "4px 8px", marginLeft: SPACE.xs, marginRight: SPACE.sm,
  fontFamily: "inherit",
};

/** A key in HTML, for series that cannot carry a label at their end (interleaved dots). */
function InlineKey({ items }) {
  return (
    <div style={{ ...TYPE.body, color: T.ink, display: "flex", flexWrap: "wrap", gap: `${SPACE.xxs}px ${SPACE.sm}px`, marginTop: SPACE.xxs }}>
      {items.map(([text, color]) => (
        <span key={text} style={{ display: "inline-flex", alignItems: "center", gap: SPACE.xxs }}>
          <span aria-hidden="true" style={{ display: "inline-block", width: 8, height: 8, borderRadius: "50%", background: color }} />
          {text}
        </span>
      ))}
    </div>
  );
}

const SIDE_INK = { Left: SIDE.left, Right: SIDE.right };

const TABLE = { borderCollapse: "collapse", marginTop: SPACE.sm, ...TYPE.body, color: T.ink };
const CELL = { padding: "4px 16px 4px 8px", whiteSpace: "nowrap", borderBottom: `1px solid ${T.rule}` };
const HEADC = { ...CELL, ...TYPE.caption, textAlign: "left", color: T.ink3, fontWeight: 400, background: T.fillMuted };

/** 1. Band against pain with the current off: per band, one series per stretch; filled where the
 * band is still clear after allowing for the bands tested (q < 0.05 on the saved result). */
export function ZeroMaFigure({ result }) {
  const bands = (result && result.bands) || [];
  const pairs = useMemo(() => Array.from(new Set(bands.map((b) => b.pair))), [bands]);
  const scores = useMemo(() => Array.from(new Set(bands.map((b) => b.score))), [bands]);
  const [pair, setPair] = useState(pairs.includes("ONE_THREE_LEFT") ? "ONE_THREE_LEFT" : pairs[0]);
  const [score, setScore] = useState(scores.includes("vas") ? "vas" : scores[0]);
  const rows = bands.filter((b) => b.pair === pair && b.score === score);
  const stretches = Array.from(new Set(rows.map((b) => b.stretch)));
  const cov = ((result && result.coverage) || []).filter((c) => c.pair === pair && c.score === score);
  const ink = (k) => SERIES[k % SERIES.length];
  const spec = useMemo(() => zeroMaSpec({ rows, stretches }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [result, pair, score]);
  return (
    <div data-testid="figure-zero_ma_within_stretch">
      <div style={{ ...BODY, margin: `${SPACE.xxs}px 0 ${SPACE.xs}px` }}>
        <span aria-hidden="true">Sensing pair</span>
        <select aria-label="Sensing pair" value={pair} onChange={(e) => setPair(e.target.value)} style={SELECT}>
          {pairs.map((p) => <option key={p} value={p}>{pairName(p)}</option>)}</select>
        <span aria-hidden="true">Pain score</span>
        <select aria-label="Pain score" value={score} onChange={(e) => setScore(e.target.value)} style={SELECT}>
          {scores.map((s) => <option key={s} value={s}>{painScoreLabel(s)}</option>)}</select>
      </div>
      <PlotlyChart spec={spec} height={280} label="Correlation of each band with pain in each stretch" />
      <InlineKey items={stretches.map((s, k) => [s, ink(k)])} />
      <div style={CAPTION}>
        {"Filled dot: still clear after allowing for the bands tested. Lines: 95% range, resampling whole days. Above zero, pain is higher when band power is higher."}
      </div>
      <table data-testid="zero-ma-coverage" style={TABLE}>
        {/* The page's window since decision 331 (15 min), 60 min in runs saved before it. */}
        <thead><tr>{["Stretch", "Ratings", `With a recording within ${(cov[0] && cov[0].page_window_min) || 60} min`, "With a recording the same day"].map((h) => (
          <th key={h} style={HEADC}>{h}</th>))}</tr></thead>
        <tbody>{cov.map((c) => (
          <tr key={c.stretch}>
            <td style={CELL}>{c.stretch}</td>
            <td style={CELL}>{`${c.reports} on ${c.days_with_reports} days`}</td>
            <td style={CELL}>{c.matched_page_window != null ? c.matched_page_window : c.matched_60min}</td>
            <td style={CELL}>{`${c.matched_same_day} on ${c.days_matched} days`}</td>
          </tr>))}</tbody>
      </table>
    </div>
  );
}

/** 2. What the current explains: per pair and length, the current alone, every band and bands without the
 * current, each reading against its OWN shuffled-data 95th (decision 314): every band against the plain
 * rotations, the bands without the current against the rotations refitted with the current taken out
 * (decision 276); the current alone has no null. A bar is drawn in its reading's colour on its reading's row. */
export function CurrentExplainsFigure({ result }) {
  const rows = useMemo(() => ((result && result.rows) || []).filter((r) => r.bands != null), [result]);
  const spec = useMemo(() => currentExplainsSpec({ rows }), [rows]);
  const h = 64 + rows.length * 36 + 72;
  return (
    <div data-testid="figure-current_explains">
      <PlotlyChart spec={spec} height={h} label="How well the current and the bands predict pain in weeks they were not fitted on, per sensing pair" />
      <div style={CAPTION}>
        {"Short bar beside a dot, in its colour: the level chance alone reaches 1 time in 20, from its own shuffled data (pain's slow rises and falls kept; the current alone has none). Numbers in brackets: ratings."}
      </div>
    </div>
  );
}

/** 4. A current with memory: held-out R squared against the time constant, one line per pain score; and the drift table. */
export function CurrentMemoryFigure({ result }) {
  const curves = useMemo(() => (result && result.curves) || [], [result]);
  const taus = curves.length ? curves[0].rows.map((r) => r.tau_h) : [];
  const lab = (t) => (t === 0 ? "0" : t < 24 ? `${t} h` : `${t / 24} d`);
  const spec = useMemo(() => currentMemorySpec({ curves }), [curves]);
  const drift = (result && result.drift) || [];
  const strata = Array.from(new Set(drift.filter((d) => d.stratum).map((d) => d.stratum)));
  return (
    <div data-testid="figure-current_with_memory">
      <PlotlyChart spec={spec} height={270} label="Share of pain predicted in weeks not fitted on, against how long the current is remembered" />
      <div style={CAPTION}>
        {"Measured in weeks the fit did not see. Above zero, remembering the current predicts pain better than guessing the average."}
      </div>
      {strata.length > 0 && (
        <table data-testid="memory-drift" style={TABLE}>
          <thead><tr><th style={HEADC}>Pain map</th>
            {taus.map((t) => <th key={t} style={{ ...HEADC, textAlign: "center" }}>{lab(t)}</th>)}</tr></thead>
          <tbody>{strata.map((s) => (
            <tr key={s}><td style={CELL}>{s}</td>
              {taus.map((t) => {
                const d = drift.find((x) => x.stratum === s && x.tau_h === t);
                const moves = d && d.verdict === "moves between blocks of time";
                return (
                  <td key={t} style={{ ...CELL, textAlign: "center", color: moves ? T.caution : T.ink3 }}>
                    {d ? (moves ? `${GLYPH.caution} moves` : "does not move") : "not given"}
                  </td>
                );
              })}</tr>))}</tbody>
        </table>
      )}
      {strata.length > 0 && (
        <div style={CAPTION}>
          {`${GLYPH.caution} moves: the predicted pain at the same setting changed from one block of weeks to the next, even with each setting's current replaced by its remembered value.`}
        </div>
      )}
    </div>
  );
}

const signedN = (v, d = 1) => (v == null ? "not given" : `${v >= 0 ? "+" : ""}${v.toFixed(d)}`);

/** 7. Regression to the mean at one setting (decision 253): the setting delivered most often in
 * one rate/pulse-width group, its own block averages against every other setting in the same
 * group, and whether the swing stands out from every other way of splitting the same
 * stretches (internal) or from any similar run elsewhere in the record (outside).
 * Descriptive: it never selects a setting. */
export function RegressionToMeanFigure({ result }) {
  const setting = (result && result.setting) || {};
  const internal = (result && result.internal_comparison) || {};
  const outside = (result && result.outside_comparison) || {};
  const extremity = (result && result.extremity) || {};
  const readable = !!result && setting.amp_mA_Left != null;
  const spec = useMemo(() => (readable ? regressionToMeanSpec({ result }) : null), [result, readable]);
  if (!readable) {
    return (
      <div data-testid="figure-regression_to_mean" style={BODY}>
        {(result && result.reason) || "Nothing to read yet."}
      </div>
    );
  }
  return (
    <div data-testid="figure-regression_to_mean" style={{ ...BODY, color: T.ink }}>
      <PlotlyChart spec={spec} height={250} label="Block averages of the target setting against every other setting in the same group" />
      <div style={CAPTION}>{"Lines: ± 1 standard error, weighted by each stretch's own rating noise."}</div>
      <table data-testid="regression-to-mean-comparisons" style={TABLE}>
        <thead><tr>{["Question", "Answer", "Based on"].map((hd) => <th key={hd} style={HEADC}>{hd}</th>)}</tr></thead>
        <tbody>
          <tr>
            <td style={CELL}>{"Is the swing specific to this current pair?"}</td>
            <td style={CELL}>{internal.p_two_sided != null
              ? `${(internal.p_two_sided * 100).toFixed(1)}% of splits match or exceed it (same direction ${(internal.p_same_direction * 100).toFixed(1)}%)`
              : (internal.reason || "not computable")}</td>
            <td style={CELL}>{internal.n_valid != null ? `${internal.n_valid} of ${internal.n_total} splits` : "not given"}</td>
          </tr>
          <tr>
            <td style={CELL}>{"Is a swing this size common anywhere in all the data?"}</td>
            <td style={CELL}>{outside.fraction_ge != null
              ? `${(outside.fraction_ge * 100).toFixed(1)}% of runs elsewhere match or exceed it`
              : "not computable"}</td>
            <td style={CELL}>{outside.n_windows ? `${outside.n_windows} overlapping runs of ${outside.window_size}` : "not given"}</td>
          </tr>
          <tr>
            <td style={CELL}>{"How unusual was block 1?"}</td>
            <td style={CELL}>{extremity.value != null
              ? `${signedN(extremity.value)} standard errors from the long-run average of all the data`
              : (extremity.reason || "not computable")}</td>
            <td style={CELL}>{"not given"}</td>
          </tr>
        </tbody>
      </table>
      <div style={CAPTION}>
        {"Descriptive: never selects a setting or blocks a recommendation. The runs elsewhere overlap heavily, so they are not independent looks."}
      </div>
    </div>
  );
}

/** 3. Time of day and weekends: per sensing pair, how many bands carry a daily cycle or a weekend
 * difference; and pain at weekends against weekdays within the week. */
export function TimeOfDayFigure({ result }) {
  const bands = (result && result.bands) || [];
  const pairs = Array.from(new Set(bands.map((b) => b.channel)));
  const pain = ((result && result.pain) || []).filter((p) => p.within_week != null);
  const count = (ch, f) => bands.filter((b) => b.channel === ch && !b.why && f(b)).length;
  return (
    <div data-testid="figure-time_of_day" style={{ ...BODY, color: T.ink }}>
      <table style={{ ...TABLE, marginTop: 0 }}>
        <thead><tr>{["Sensing pair", "Recordings", "Daily cycle above chance", "Higher at weekends", "Lower at weekends"].map((h) => <th key={h} style={HEADC}>{h}</th>)}</tr></thead>
        <tbody>{pairs.map((ch) => {
          const first = bands.find((b) => b.channel === ch && !b.why);
          return (
            <tr key={ch}><td style={CELL}>{pairName(ch)}</td><td style={CELL}>{first ? first.n : "not given"}</td>
              <td style={CELL}>{`${count(ch, (b) => b.R_daily_ci[0] > b.R_daily_shuffle_p95)} of 22`}</td>
              <td style={CELL}>{count(ch, (b) => b.r_weekend_ci[0] > 0)}</td>
              <td style={CELL}>{count(ch, (b) => b.r_weekend_ci[1] < 0)}</td></tr>
          );
        })}</tbody>
      </table>
      <table style={TABLE}>
        <thead><tr>{["Pain score", "Weekend minus weekday, within the week", "95% range", "p", "Weeks"].map((h) => <th key={h} style={HEADC}>{h}</th>)}</tr></thead>
        <tbody>{pain.map((p) => (
          <tr key={p.score}><td style={CELL}>{painScoreLabel(p.score)}</td><td style={CELL}>{p.within_week.toFixed(2)}</td>
            <td style={CELL}>{`${p.ci[0].toFixed(2)} to ${p.ci[1].toFixed(2)}`}</td><td style={CELL}>{p.p.toFixed(3)}</td>
            <td style={CELL}>{p.n_weeks}</td></tr>))}</tbody>
      </table>
    </div>
  );
}

/** 5. Pain around each on/off switch: mean pain (ratings) before and in each window after. */
export function OnOffFigure({ result }) {
  const rows = (result && result.switches) || [];
  const windows = rows.length ? rows[0].after.map((w) => w.days) : [];
  const cell = (w) => (w && w.mean != null ? `${w.mean.toFixed(2)} (${w.n})` : "not given");
  return (
    <div data-testid="figure-onoff_switches" style={{ ...BODY, color: T.ink }}>
      <table style={{ ...TABLE, marginTop: 0 }}>
        <thead><tr><th style={HEADC}>{"Switch"}</th><th style={HEADC}>{"14 days before"}</th>
          {windows.map((d) => <th key={d} style={HEADC}>{`${d} days after`}</th>)}</tr></thead>
        <tbody>{rows.map((r) => (
          <tr key={r.label}><td style={CELL}>{r.label}</td><td style={CELL}>{cell(r.before)}</td>
            {r.after.map((w) => <td key={w.days} style={CELL}>{cell(w)}</td>)}</tr>))}</tbody>
      </table>
      <div style={CAPTION}>{"Mean pain, with the number of ratings in brackets. Descriptive: no statistics, and a window may run into the next switch."}</div>
    </div>
  );
}

/** 6. Up the ladder and down: pain on the way down minus on the way up at each current, per side;
 * filled where the fall came after the rise, hollow where it came first; the held re-ratings; the
 * ladders' settled band power. */
const signed = (v, d = 2) => (v == null ? "not given" : `${v >= 0 ? "+" : ""}${v.toFixed(d)}`);
const ORDER_WORDS = {
  "one order": "Every fall came after its rise, so carry-over cannot be told apart from pain drifting over the visit.",
};

export function CarryOverFigure({ result }) {
  const pain = (result && result.pain) || [];
  const holds = (result && result.holds) || [];
  const ladder = (result && result.ladder) || [];
  const items = pain.map((p) => p.item);
  const [item, setItem] = useState(items.includes("overall") ? "overall" : items[0]);
  const p = pain.find((x) => x.item === item) || { by_current: [], by_side: {}, summary: {} };
  const pts = useMemo(() => p.by_current || [], [p]);
  const spec = useMemo(() => carryOverSpec({ pts }), [pts]);
  const sides = Object.entries(p.by_side || {});
  const headline = ORDER_WORDS[p.verdict] || (p.sentence ? `${p.sentence[0].toUpperCase()}${p.sentence.slice(1)}.` : "");
  const sidesDrawn = Object.entries(SIDE_INK).filter(([sd]) => pts.some((r) => r.side === sd));
  return (
    <div data-testid="figure-carry_over_ladder" style={{ ...BODY, color: T.ink }}>
      {items.length > 1 && (
        <select aria-label="Pain site" value={item} onChange={(e) => setItem(e.target.value)} style={{ ...SELECT, marginLeft: 0 }}>
          {pain.map((x) => <option key={x.item} value={x.item}>{x.words}</option>)}
        </select>
      )}
      <div style={{ ...TYPE.body, color: T.ink, padding: `${SPACE.xxs}px 0`, maxWidth: "68ch" }}>
        {pts.length ? `${headline}${sides.length ? ` By side: ${sides.map(([sd, x]) => `${sd.toLowerCase()} ${signed(x.mean)} (${x.n_pairs} currents)`).join(", ")}.` : ""}`
          : `No current was rated for ${p.words || item} on both the way up and the way down within one visit.`}
      </div>
      {pts.length > 0 && (
        <PlotlyChart spec={spec} height={260} label="Pain on the way down minus on the way up, at each current" />
      )}
      {pts.length > 0 && (
        <>
          <InlineKey items={sidesDrawn.map(([sd, c]) => [`${sd.toLowerCase()} side stepped`, c])} />
          <div style={CAPTION}>{"Filled: the fall came after the rise; hollow: the fall came first. Below zero: less pain on the way down."}</div>
        </>
      )}
      <table data-testid="carry-over-holds" style={TABLE}>
        <thead><tr>{["Pain site", "Stimulation", "Rated twice at one setting", "Second minus first (95% range)", "Lower / higher / same"].map((h) => <th key={h} style={HEADC}>{h}</th>)}</tr></thead>
        <tbody>{holds.filter((h) => h.n_pairs).map((h) => (
          <tr key={`${h.item}${h.on}`}><td style={CELL}>{h.words}</td><td style={CELL}>{h.on ? "on" : "off"}</td>
            <td style={CELL}>{`${h.n_pairs} times, ${h.n_visits} visits, median ${h.minutes_median == null ? "gap not given" : `${h.minutes_median.toFixed(0)} min apart`}`}</td>
            <td style={CELL}>{`${signed(h.mean)} (${h.lo == null ? "no interval" : `${signed(h.lo)} to ${signed(h.hi)}`})`}</td>
            <td style={CELL}>{`${h.n_lower} / ${h.n_higher} / ${h.n_same}`}</td></tr>))}</tbody>
      </table>
      {ladder.length > 0 && (
        <table data-testid="carry-over-ladder-power" style={TABLE}>
          <thead><tr>{["Settled band power, recording route", "Sensing pair", "Ladder runs and bands (8.5–29.5 Hz)", "Median band, down against up (bands higher / lower)", "Order"].map((h) => <th key={h} style={HEADC}>{h}</th>)}</tr></thead>
          <tbody>{ladder.map((L) => (
            <tr key={`${L.source}${L.pair}`}><td style={CELL}>{L.source}</td><td style={CELL}>{pairName(L.pair)}</td>
              <td style={CELL}>{`${L.n_runs} runs, ${L.n_bands} bands`}</td>
              <td style={CELL}>{`${L.median_over_bands == null ? "not given" : `${signed(100 * L.median_over_bands, 1)}%`} (${L.bands_higher} / ${L.bands_lower})`}</td>
              <td style={CELL}>{L.verdict === "one order" ? "every fall after its rise" : "both orders"}</td></tr>))}</tbody>
        </table>
      )}
    </div>
  );
}

/** A4: day-to-day correlation of the pain ratings, and report 02's visit-count target restated as
 * calendar days once that correlation is taken out (critique finding M2). Per score: the
 * correlation of daily mean ratings at lags 1-7 days, the effective (independent) day count for
 * all the data we have and for the 0 mA stretch where one exists, and the 52/73/98
 * independent-day targets from report 02, each restated as calendar days at the observed rate.
 * Descriptive: corrects a planning number only. */
export function RatingPersistenceFigure({ result }) {
  const rows = (result && result.rows) || [];
  const scores = rows.map((r) => r.score);
  const [score, setScore] = useState(scores.includes("vas") ? "vas" : scores[0]);
  const r = rows.find((x) => x.score === score) || { lags: [] };
  const lags = useMemo(() => r.lags || [], [r]);
  const spec = useMemo(() => ratingPersistenceSpec({ lags, score: r.score, nRatings: r.n_ratings, nDays: r.n_days }), [lags, r]);
  const targetsAll = r.calendar_days_needed || [];
  const targetsZero = (r.zero_ma && r.zero_ma.calendar_days_needed) || [];
  const targetRows = targetsAll.length ? targetsAll : targetsZero;
  return (
    <div data-testid="figure-rating_persistence" style={{ ...BODY, color: T.ink }}>
      {scores.length > 1 && (
        <div>
          <span aria-hidden="true">Pain score</span>
          <select aria-label="Pain score" value={score} onChange={(e) => setScore(e.target.value)} style={SELECT}>
            {scores.map((s) => <option key={s} value={s}>{painScoreLabel(s)}</option>)}
          </select>
        </div>
      )}
      {lags.length > 0 ? (
        <>
          <PlotlyChart spec={spec} height={250} label="Day-to-day correlation of daily mean ratings at each lag" />
          <div style={CAPTION}>
            {`${painScoreLabel(r.score)} (${r.n_ratings} ratings, ${r.n_days} days). `}
            {r.effective_days != null && `${r.effective_days.toFixed(1)} of those days count as independent (${Math.round(100 * r.ratio)}%).`}
          </div>
        </>
      ) : (
        <div style={BODY}>{"Too few days with a rating to read."}</div>
      )}
      {r.zero_ma && r.zero_ma.effective_days != null && (
        <div style={{ ...BODY, color: T.ink, marginTop: SPACE.xs }}>
          {`0 mA stretch (${r.zero_ma.label}, ${r.zero_ma.n_days} days): ${r.zero_ma.effective_days.toFixed(1)} independent days (${Math.round(100 * r.zero_ma.ratio)}%).`}
        </div>
      )}
      {targetRows.length > 0 && (
        <table data-testid="rating-persistence-targets" style={TABLE}>
          <thead><tr>{["Report 02's target", "Independent days", "Calendar days here (all data)", "Calendar days here (0 mA stretch)"].map((h) => (
            <th key={h} style={HEADC}>{h}</th>))}</tr></thead>
          <tbody>{targetRows.map((t, i) => (
            <tr key={t.name}>
              <td style={CELL}>{t.name}</td>
              <td style={CELL}>{t.independent_days}</td>
              <td style={CELL}>{targetsAll[i] && targetsAll[i].calendar_days != null ? Math.round(targetsAll[i].calendar_days) : "not given"}</td>
              <td style={CELL}>{targetsZero[i] && targetsZero[i].calendar_days != null ? Math.round(targetsZero[i].calendar_days) : "not given"}</td>
            </tr>))}</tbody>
        </table>
      )}
      <div style={CAPTION}>
        {"Descriptive: corrects a planning number only; recommends no visit count and blocks nothing."}
      </div>
    </div>
  );
}

/** A5: does settled band power change with current as much in bands with no plausible pain
 * relationship (below 12 Hz, above 32 Hz) as in the pain-linked family (21.5-27.5 Hz)? (critique
 * finding M1.) Per recording route and sensing pair: each band's change per mA (relative to its
 * own settled power), and the ratio of the far bands' typical change to the family's -- near 1 is
 * what an electrical effect of stepping the current would predict, well under 1 is what a
 * pain-specific family would. Descriptive: never selects a band. */
export function SteppedCurrentAllBandsFigure({ result }) {
  const bands = (result && result.bands) || [];
  const ratios = (result && result.ratios) || [];
  const keyOf = (b) => `${b.route}||${b.pair}`;
  const combos = Array.from(new Set(bands.map(keyOf)));
  const [combo, setCombo] = useState(combos[0]);
  const rows = useMemo(() => bands.filter((b) => keyOf(b) === combo), [bands, combo]);   // eslint-disable-line react-hooks/exhaustive-deps
  const spec = useMemo(() => steppedCurrentSpec({ rows }), [rows]);
  const current = ratios.find((r) => `${r.route}||${r.pair}` === combo);
  const pct = (v) => (v != null ? `${(100 * v).toFixed(1)}%` : "not given");
  return (
    <div data-testid="figure-stepped_current_all_bands" style={{ ...BODY, color: T.ink }}>
      {combos.length > 1 && (
        <select aria-label="Route and sensing pair" value={combo} onChange={(e) => setCombo(e.target.value)} style={{ ...SELECT, marginLeft: 0 }}>
          {combos.map((c) => {
            const [route, pair] = c.split("||");
            return <option key={c} value={c}>{`${route}, ${pairName(pair)}`}</option>;
          })}
        </select>
      )}
      {rows.length > 0 ? (
        <>
          <PlotlyChart spec={spec} height={260} label="Change in settled band power per mA, relative to the band's own settled power" />
          <InlineKey items={[["21.5–27.5 Hz family", GROUP_INK.family], ["far bands (< 12 Hz or > 32 Hz)", GROUP_INK.far], ["other bands", CONTEXT]]} />
          <div style={CAPTION}>{"Lines: 95% range, resampling whole ladder runs."}</div>
        </>
      ) : (
        <div style={BODY}>{"No stored titration-ladder points for this participant."}</div>
      )}
      {current && current.far_over_family_ratio != null && (
        <div style={{ ...BODY, color: T.ink, marginTop: SPACE.xs }}>
          {`Family ${(100 * current.family_median_abs_relative_slope).toFixed(1)}% per mA at the median band; `}
          {`far bands ${(100 * current.far_median_abs_relative_slope).toFixed(1)}%; `}
          {`ratio (far over family) ${current.far_over_family_ratio.toFixed(2)}.`}
        </div>
      )}
      {ratios.length > 0 && (
        <table data-testid="stepped-current-ratios" style={TABLE}>
          <thead><tr>{["Route", "Sensing pair", "Family: change per mA (bands)", "Far: change per mA (bands)", "Ratio (far / family)"].map((h) => (
            <th key={h} style={HEADC}>{h}</th>))}</tr></thead>
          <tbody>{ratios.map((r) => (
            <tr key={`${r.route}${r.pair}`}>
              <td style={CELL}>{r.route}</td><td style={CELL}>{pairName(r.pair)}</td>
              <td style={CELL}>{`${pct(r.family_median_abs_relative_slope)} (${r.n_family_bands})`}</td>
              <td style={CELL}>{`${pct(r.far_median_abs_relative_slope)} (${r.n_far_bands})`}</td>
              <td style={CELL}>{r.far_over_family_ratio != null ? r.far_over_family_ratio.toFixed(2) : "not given"}</td>
            </tr>))}</tbody>
        </table>
      )}
      <div style={CAPTION}>
        {"A ratio near 1 is what an electrical effect of stepping the current would predict; well under 1 is what a family specific to pain would. Descriptive: never selects a band."}
      </div>
    </div>
  );
}

/** Band detector, research version (the PI's ruling 5b, 2026-09-25): per sensing pair and length of
 * signal, pain predicted as a number out of sample -- the held-out rank correlation (0 is chance, never
 * folded) of the current alone, every band, and every band with the current taken out, each with its
 * 95% interval; each band reading has a short bar at its OWN rotated ratings' 95th percentile, the
 * current-taken-out one against rotations refitted with the current taken out (decision 314). Draws the run
 * matching the page's clinic-sheet switch (ruling 5a). */
export function BandDetectorResearchFigure({ result, clinicSheets }) {
  const mode = (result && result.modes && result.modes[clinicSheets ? "on" : "off"]) || {};
  const rows = useMemo(() => (mode.rows || []).filter((r) => r.reading && r.reading.bands && r.reading.bands.rho != null), [mode]);
  const spec = useMemo(() => bandDetectorResearchSpec({ rows }), [rows]);
  if (!rows.length) {
    return <div data-testid="figure-band_detector_research" style={BODY}>{"No sensing pair could be read."}</div>;
  }
  const h = 64 + rows.length * 36 + 72;
  return (
    <div data-testid="figure-band_detector_research">
      <PlotlyChart spec={spec} height={h} label="How well pain is predicted in weeks not fitted on, per sensing pair and length of signal" />
      <div style={CAPTION}>
        {"Lines: 95% range, resampling whole days. Filled dot: still clear after allowing for the readings tested. Short bar beside a dot, in its colour: the level chance alone reaches 1 time in 20, from its own rotated ratings (the pain ratings slid along in time; for the reading with the current taken out, the current is taken out on each rotation too; the current alone has none). Numbers in brackets: ratings."}
      </div>
    </div>
  );
}

/** Band detector, device-shaped version (the PI's rulings 5b and 5c, 2026-09-25): per sensing pair,
 * one band at a time, the area under the curve of a held-out logistic regression of the two pain
 * groups on the band's reading at the device's own timing (0.5 is chance), plainly and with the
 * current taken out, each with its 95% interval; filled where q < 0.05 over the pair's 22 bands; the
 * dashed line is the current alone; a tick under a band marks a folded multiple of the rate in force
 * (advisory). Draws the run matching the page's clinic-sheet switch (ruling 5a). */
function DevicePanel({ p }) {
  const spec = useMemo(() => bandDeviceSpec({ p }), [p]);
  const bands = (p.bands || []).filter((b) => b.reading && b.reading.band && b.reading.band.auc != null);
  const first = bands.length ? bands[0].reading : {};
  return (
    <div style={{ marginBottom: SPACE.sm }}>
      <div style={{ ...TYPE.body, color: T.ink }}>{`${pairName(p.pair)} (${first.n != null ? first.n : 0} ratings in the two pain groups with a device-timed reading)`}</div>
      <PlotlyChart spec={spec} height={260} label={`AUC of each band, high pain against low, ${pairName(p.pair)}`} />
    </div>
  );
}

export function BandDetectorDeviceFigure({ result, clinicSheets }) {
  const mode = (result && result.modes && result.modes[clinicSheets ? "on" : "off"]) || {};
  const pairs = (mode.pairs || []).filter((p) => (p.bands || []).length);
  return (
    <div data-testid="figure-band_detector_device">
      {pairs.length ? pairs.map((p) => <DevicePanel key={p.pair} p={p} />)
        : <div style={BODY}>{"No sensing pair could be read."}</div>}
      <div style={CAPTION}>
        {"Up the side: how well the band tells high-pain reports from low-pain ones (0.5 = coin toss, 1 = perfect). Lines: 95% range, resampling whole days. Filled dot: still clear after allowing for the pair's bands. Tick under a band: it carries a folded multiple of the stimulation rate in force (advisory)."}
      </div>
    </div>
  );
}

export const FIGURES = {
  zero_ma_within_stretch: ZeroMaFigure,
  current_explains: CurrentExplainsFigure,
  time_of_day: TimeOfDayFigure,
  current_with_memory: CurrentMemoryFigure,
  onoff_switches: OnOffFigure,
  carry_over_ladder: CarryOverFigure,
  regression_to_mean: RegressionToMeanFigure,
  rating_persistence: RatingPersistenceFigure,
  stepped_current_all_bands: SteppedCurrentAllBandsFigure,
  band_detector_research: BandDetectorResearchFigure,
  band_detector_device: BandDetectorDeviceFigure,
};
