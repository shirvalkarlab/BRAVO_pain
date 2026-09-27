/**
 * Figures for the saved checks against chance and against the current (first written 2026-09-24;
 * redrawn 2026-09-26 for the minimalist redesign, SPEC.md sections 3 and 7, WP4). Each draws only
 * what the saved result holds.
 *
 * How they are drawn:
 *  - plain SVG at the container's real pixel width (useMeasuredWidth), never scaled through a
 *    viewBox, so figure text is 12 px on screen; below 480 px the figure scrolls inside its card;
 *  - no gridlines and no legend boxes: series are named by a label at their right end, and a
 *    reference line (zero, or 0.5 = coin toss) is named at its end;
 *  - colours come from the shared data colours; text is in the shared inks, and a series' own
 *    colour is used for its label only when that colour is dark enough to read (4.5:1 on white);
 *  - pain scores are printed with the page's own labels ("Left Leg VAS"), never as raw keys.
 */
import React, { useMemo, useState } from "react";

import { T, TYPE, SPACE, RADIUS, GLYPH, contrastRatio } from "assets/theme/base/tokens";
import { CATEGORICAL, SIDE, CONTEXT, textInk } from "assets/theme/base/dataColors";
import { FONT_FAMILY, FIGURE_TEXT_PX } from "views/Reports/figureStyle";
import { painScoreLabel } from "views/Reports/painScores";

import useMeasuredWidth from "./useMeasuredWidth";

// Series colours, in a fixed order. Orange is left out of the general list because it is the
// right brain side on every page; it appears only where a series IS the right side.
const SERIES = [CATEGORICAL[0], CATEGORICAL[2], CATEGORICAL[3], CATEGORICAL[5], CATEGORICAL[4], CATEGORICAL[1]];
const READING = { current: CONTEXT, bands: CATEGORICAL[0], adjusted: CATEGORICAL[2] };

/** The ink a series' direct label is written in: its own colour when readable, else ink. */
const labelInk = (c) => (contrastRatio(textInk(c), T.surface) >= 4.5 ? textInk(c) : T.ink);

const TEXT = { fontSize: FIGURE_TEXT_PX, fontFamily: FONT_FAMILY };
const CAPTION = { ...TYPE.caption, color: T.ink3, marginTop: SPACE.xxs, maxWidth: "68ch" };
const BODY = { ...TYPE.body, color: T.ink2 };
const SELECT = {
  ...TYPE.body, color: T.ink, background: T.surface, border: `1px solid ${T.ink3}`,
  borderRadius: RADIUS.sm, padding: "4px 8px", marginLeft: SPACE.xs, marginRight: SPACE.sm,
  fontFamily: "inherit",
};
const LABEL_MARGIN = 170; // right margin that holds the direct labels

/** An SVG figure drawn at its container's measured width. `draw(width)` returns the marks. */
function FigureSvg({ height, label, draw }) {
  const [ref, width] = useMeasuredWidth();
  return (
    <div ref={ref} style={{ overflowX: "auto", maxWidth: "100%" }}>
      <svg width={width} height={height} role="img" aria-label={label} style={{ display: "block" }}>
        {draw(width)}
      </svg>
    </div>
  );
}

function frame(W, xs, ys, h = 240, ml = 56, mr = LABEL_MARGIN, mt = 16, mb = 44) {
  const [x0, x1] = xs; const [y0, y1] = ys;
  const X = (v) => ml + ((v - x0) / (x1 - x0)) * (W - ml - mr);
  const Y = (v) => h - mb - ((v - y0) / (y1 - y0)) * (h - mt - mb);
  return { X, Y, W, h, ml, mr, mt, mb, x0, x1, y0, y1 };
}

/** Push labels apart so none is closer than `gap` px to the one above it. */
function spread(items, gap = 15) {
  const out = [...items].sort((a, b) => a.y - b.y);
  for (let i = 1; i < out.length; i += 1) {
    if (out[i].y - out[i - 1].y < gap) out[i] = { ...out[i], y: out[i - 1].y + gap };
  }
  return out;
}

/** Direct labels at the right end of each series: a coloured dot, then the words. */
function DirectLabels({ f, items }) {
  return (
    <g>
      {spread(items).map((it) => (
        <g key={it.text}>
          <circle cx={f.W - f.mr + 12} cy={it.y} r={4} fill={it.color} />
          <text x={f.W - f.mr + 20} y={it.y + 4} {...TEXT} fill={labelInk(it.color)}>{it.text}</text>
        </g>
      ))}
    </g>
  );
}

/** A dashed reference line across the plot, named at its right end. */
function RefLine({ f, y, text, color = T.graphic }) {
  return (
    <g>
      <line x1={f.ml} x2={f.W - f.mr} y1={y} y2={y} stroke={color} strokeWidth={1} strokeDasharray="4 3" />
      {text && <text x={f.W - f.mr + 6} y={y + 4} {...TEXT} fill={T.ink3}>{text}</text>}
    </g>
  );
}

function Axes({ f, xticks, yticks, xlab, ylab }) {
  const bottom = f.h - f.mb;
  return (
    <g>
      <line x1={f.ml} x2={f.W - f.mr} y1={bottom} y2={bottom} stroke={T.graphic} strokeWidth={1} />
      <line x1={f.ml} x2={f.ml} y1={f.mt} y2={bottom} stroke={T.graphic} strokeWidth={1} />
      {yticks.map((v) => (
        <g key={`y${v}`}>
          <line x1={f.ml - 4} x2={f.ml} y1={f.Y(v)} y2={f.Y(v)} stroke={T.graphic} strokeWidth={1} />
          <text x={f.ml - 8} y={f.Y(v) + 4} {...TEXT} textAnchor="end" fill={T.ink3}>{v}</text>
        </g>
      ))}
      {xticks.map(([v, l]) => (
        <g key={`x${v}`}>
          <line x1={f.X(v)} x2={f.X(v)} y1={bottom} y2={bottom + 4} stroke={T.graphic} strokeWidth={1} />
          <text x={f.X(v)} y={bottom + 18} {...TEXT} textAnchor="middle" fill={T.ink3}>{l}</text>
        </g>
      ))}
      <text x={(f.W - f.mr + f.ml) / 2} y={f.h - 6} {...TEXT} textAnchor="middle" fill={T.ink3}>{xlab}</text>
      <text x={14} y={(bottom + f.mt) / 2} {...TEXT} textAnchor="middle" fill={T.ink3}
        transform={`rotate(-90 14 ${(bottom + f.mt) / 2})`}>{ylab}</text>
    </g>
  );
}

/** A key in HTML, for series that cannot carry a label at their end (interleaved dots). */
function InlineKey({ items }) {
  return (
    <div style={{ ...TYPE.caption, color: T.ink, display: "flex", flexWrap: "wrap", gap: `${SPACE.xxs}px ${SPACE.sm}px`, marginTop: SPACE.xxs }}>
      {items.map(([text, color]) => (
        <span key={text} style={{ display: "inline-flex", alignItems: "center", gap: SPACE.xxs }}>
          <span aria-hidden="true" style={{ display: "inline-block", width: 8, height: 8, borderRadius: "50%", background: color }} />
          {text}
        </span>
      ))}
    </div>
  );
}

const TABLE = { borderCollapse: "collapse", marginTop: SPACE.sm, ...TYPE.body, color: T.ink };
const CELL = { padding: "4px 16px 4px 8px", whiteSpace: "nowrap", borderBottom: `1px solid ${T.rule}` };
const HEADC = { ...CELL, ...TYPE.caption, textAlign: "left", color: T.ink3, fontWeight: 400, background: T.fillMuted };

const WORD = { ZERO: "0", ONE: "1", TWO: "2", THREE: "3" };
/** A sensing pair as the pages write it: ONE_THREE_LEFT -> L 1-3+. */
export function pairName(ch) {
  const p = String(ch).split("_");
  return p.length === 3 && WORD[p[0]] && WORD[p[1]] && (p[2] === "LEFT" || p[2] === "RIGHT")
    ? `${p[2][0]} ${WORD[p[0]]}-${WORD[p[1]]}⁺` : String(ch);
}

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
  const centres = rows.map((b) => b.centre);
  const cov = ((result && result.coverage) || []).filter((c) => c.pair === pair && c.score === score);
  const ink = (k) => SERIES[k % SERIES.length];
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
      <FigureSvg height={250} label="Correlation of each band with pain in each stretch" draw={(W) => {
        const f = frame(W, [Math.min(...centres, 8) - 0.8, Math.max(...centres, 30) + 0.8], [-0.8, 0.8], 250, 56, 24);
        return (
          <>
            <Axes f={f} xticks={[10, 15, 20, 25, 30].map((v) => [v, v])} yticks={[-0.6, -0.3, 0, 0.3, 0.6]}
              xlab="band centre (Hz)" ylab="correlation with pain" />
            <RefLine f={f} y={f.Y(0)} />
            {stretches.map((s, k) => rows.filter((b) => b.stretch === s).map((b) => {
              const x = f.X(b.centre) + (k - (stretches.length - 1) / 2) * 5;
              const col = ink(k);
              return (
                <g key={`${s}-${b.centre}`}>
                  {Number.isFinite(b.lo) && <line x1={x} x2={x} y1={f.Y(b.lo)} y2={f.Y(b.hi)} stroke={col} strokeWidth={1.5} />}
                  <circle cx={x} cy={f.Y(b.rho)} r={4} fill={b.q < 0.05 ? col : T.surface} stroke={col} strokeWidth={1.5} />
                </g>
              );
            }))}
          </>
        );
      }} />
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
  const rows = ((result && result.rows) || []).filter((r) => r.bands != null);
  const rowH = 36;
  const h = 24 + rows.length * rowH + 48;
  const y = (i) => 24 + i * rowH + rowH / 2;
  const keys = [["current_alone", "current alone", READING.current, -9, null],
    ["bands", "every band", READING.bands, 0, "null_p95"],
    ["bands_without_current", "every band, current taken out", READING.adjusted, 9, "bands_without_current_null_p95"]];
  return (
    <div data-testid="figure-current_explains">
      <FigureSvg height={h} label="How well the current and the bands predict pain in weeks they were not fitted on, per sensing pair" draw={(W) => {
        const f = frame(W, [0.3, 0.95], [0, 1], h, 150, LABEL_MARGIN + 30, 24, 48);
        return (
          <>
            <line x1={f.ml} x2={W - f.mr} y1={h - 48} y2={h - 48} stroke={T.graphic} strokeWidth={1} />
            {[0.4, 0.5, 0.6, 0.7, 0.8, 0.9].map((v) => (
              <g key={v}>
                <line x1={f.X(v)} x2={f.X(v)} y1={h - 48} y2={h - 44} stroke={T.graphic} strokeWidth={1} />
                <text x={f.X(v)} y={h - 30} {...TEXT} textAnchor="middle" fill={T.ink3}>{v}</text>
              </g>
            ))}
            <line x1={f.X(0.5)} x2={f.X(0.5)} y1={18} y2={h - 48} stroke={T.graphic} strokeWidth={1} strokeDasharray="4 3" />
            <text x={f.X(0.5)} y={14} {...TEXT} textAnchor="middle" fill={T.ink3}>{"0.5 = coin toss"}</text>
            <text x={(W - f.mr + f.ml) / 2} y={h - 8} {...TEXT} textAnchor="middle" fill={T.ink3}>
              {"how well it predicts pain in weeks it was not fitted on (0.5 = coin toss)"}
            </text>
            {rows.map((r, i) => (
              <g key={`${r.pair}-${r.seconds}`}>
                <text x={f.ml - 10} y={y(i) + 4} {...TEXT} textAnchor="end" fill={T.ink}>{`${pairName(r.pair)}, ${r.seconds} s (${r.n})`}</text>
                {keys.map(([k, , col, dy, nk]) => nk && r[k] != null && r[nk] != null && (
                  <line key={`null-${k}`} data-null-for={k} data-null-value={String(r[nk])} x1={f.X(r[nk])} x2={f.X(r[nk])}
                    y1={y(i) + dy - 5} y2={y(i) + dy + 5} stroke={col} strokeWidth={2.5} />
                ))}
                {keys.map(([k, , col, dy]) => r[k] != null && (
                  <circle key={k} data-reading={k} cx={f.X(r[k])} cy={y(i) + dy} r={4} fill={col} />
                ))}
              </g>
            ))}
            {rows.length > 0 && <DirectLabels f={f} items={keys.map(([, lab, col, dy]) => ({ y: y(0) + dy, text: lab, color: col }))} />}
          </>
        );
      }} />
      <div style={CAPTION}>
        {"Short bar beside a dot, in its colour: the level chance alone reaches 1 time in 20, from its own shuffled data (pain's slow rises and falls kept; the current alone has none). Numbers in brackets: ratings."}
      </div>
    </div>
  );
}

/** 4. A current with memory: held-out R squared against the time constant, one line per pain score; and the drift table. */
export function CurrentMemoryFigure({ result }) {
  const curves = (result && result.curves) || [];
  const taus = curves.length ? curves[0].rows.map((r) => r.tau_h) : [];
  const lab = (t) => (t === 0 ? "0" : t < 24 ? `${t} h` : `${t / 24} d`);
  const all = curves.flatMap((c) => c.rows.map((r) => r.r2));
  const lo = Math.min(-0.2, ...all); const hi = Math.max(0.3, ...all);
  const ticks = [lo, 0, hi].map((v) => Math.round(v * 10) / 10);
  const drift = (result && result.drift) || [];
  const strata = Array.from(new Set(drift.filter((d) => d.stratum).map((d) => d.stratum)));
  const ink = (k) => SERIES[k % SERIES.length];
  return (
    <div data-testid="figure-current_with_memory">
      <FigureSvg height={240} label="Share of pain predicted in weeks not fitted on, against how long the current is remembered" draw={(W) => {
        const f = frame(W, [-0.4, Math.max(taus.length - 0.6, 1)], [lo, hi], 240);
        return (
          <>
            <Axes f={f} xticks={taus.map((t, i) => [i, lab(t)])} yticks={Array.from(new Set(ticks))}
              xlab="how long the current is remembered (0 is the current in force)" ylab="share of pain predicted (R²)" />
            <RefLine f={f} y={f.Y(0)} />
            {curves.map((c, k) => (
              <g key={c.score}>
                <polyline fill="none" stroke={ink(k)} strokeWidth={2} points={c.rows.map((r, i) => `${f.X(i)},${f.Y(r.r2)}`).join(" ")} />
                {c.rows.map((r, i) => <circle key={i} cx={f.X(i)} cy={f.Y(r.r2)} r={3.5} fill={ink(k)} />)}
              </g>
            ))}
            <DirectLabels f={f} items={curves.filter((c) => c.rows.length).map((c, k) => ({
              y: f.Y(c.rows[c.rows.length - 1].r2), text: `${painScoreLabel(c.score)} (${c.n} ratings)`, color: ink(k) }))} />
          </>
        );
      }} />
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
  const target = (result && result.target) || { by_block: [] };
  const other = (result && result.other) || { by_block: [] };
  const internal = (result && result.internal_comparison) || {};
  const outside = (result && result.outside_comparison) || {};
  const extremity = (result && result.extremity) || {};
  const nBlocks = (result && result.n_blocks) || 3;
  const blocks = Array.from({ length: nBlocks }, (_, i) => i);
  if (!result || setting.amp_mA_Left == null) {
    return (
      <div data-testid="figure-regression_to_mean" style={BODY}>
        {(result && result.reason) || "Nothing to read yet."}
      </div>
    );
  }
  const allMeans = [...(target.by_block || []), ...(other.by_block || [])].map((r) => r.mean);
  const ymax = Math.max(1, ...allMeans.map((v) => Math.abs(v)));
  const yt = Array.from(new Set([-ymax, 0, ymax].map((v) => Math.round(v * 10) / 10)));
  const series = [
    ["target", `${setting.amp_mA_Left}/${setting.amp_mA_Right} mA (${result.n_target || 0} stretches)`, CATEGORICAL[0], target],
    ["other", `every other setting in this group (${result.n_other || 0})`, CONTEXT, other],
  ];
  return (
    <div data-testid="figure-regression_to_mean" style={{ ...BODY, color: T.ink }}>
      <FigureSvg height={220} label="Block averages of the target setting against every other setting in the same group" draw={(W) => {
        const f = frame(W, [-0.4, nBlocks - 0.6], [-ymax, ymax], 220, 56, LABEL_MARGIN + 80);
        return (
          <>
            <Axes f={f} xticks={blocks.map((b) => [b, `block ${b + 1}`])} yticks={yt}
              xlab="block of weeks, in time order" ylab="pain against today's setting" />
            <RefLine f={f} y={f.Y(0)} />
            {series.map(([key, , col, g], k) => (
              <g key={key}>
                {(g.by_block || []).map((r) => {
                  const x = f.X(r.block) + (k - 0.5) * 8;
                  return (
                    <g key={`${key}-${r.block}`}>
                      {Number.isFinite(r.se) && (
                        <line x1={x} x2={x} y1={f.Y(r.mean - r.se)} y2={f.Y(r.mean + r.se)} stroke={col} strokeWidth={1.5} />
                      )}
                      <circle cx={x} cy={f.Y(r.mean)} r={4.5} fill={col} />
                    </g>
                  );
                })}
              </g>
            ))}
            <DirectLabels f={f} items={series.filter(([, , , g]) => (g.by_block || []).length).map(([, lab, col, g]) => ({
              y: f.Y(g.by_block[g.by_block.length - 1].mean), text: lab, color: col }))} />
          </>
        );
      }} />
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
const SIDE_INK = { Left: SIDE.left, Right: SIDE.right };
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
  const pts = p.by_current || [];
  const ymax = Math.max(2, ...pts.map((r) => Math.abs(r.diff)));
  const xmax = Math.max(4.5, ...pts.map((r) => r.current_mA));
  const yt = [-ymax, 0, ymax].map((v) => Math.round(v * 10) / 10);
  const xt = Array.from({ length: Math.floor(xmax) + 1 }, (_, i) => [i, `${i}`]);
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
        <FigureSvg height={230} label="Pain on the way down minus on the way up, at each current" draw={(W) => {
          const f = frame(W, [-0.2, xmax + 0.3], [-ymax, ymax], 230);
          return (
            <>
              <Axes f={f} xticks={xt} yticks={Array.from(new Set(yt))} xlab="current on the side that was stepped (mA)"
                ylab="down minus up (pain points)" />
              <RefLine f={f} y={f.Y(0)} text="no difference" />
              {pts.map((r, i) => (
                <circle key={i} cx={f.X(r.current_mA)} cy={f.Y(r.diff)} r={5.5}
                  fill={r.falling_first ? T.surface : SIDE_INK[r.side] || SERIES[0]} stroke={SIDE_INK[r.side] || SERIES[0]} strokeWidth={2} />
              ))}
            </>
          );
        }} />
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
  const lags = r.lags || [];
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
          <FigureSvg height={220} label="Day-to-day correlation of daily mean ratings at each lag" draw={(W) => {
            const f = frame(W, [0.4, 7.6], [-1, 1], 220, 56, 24);
            return (
              <>
                <Axes f={f} xticks={lags.map((l) => [l.lag_days, `${l.lag_days} d`])} yticks={[-1, -0.5, 0, 0.5, 1]}
                  xlab="days apart" ylab="correlation" />
                <RefLine f={f} y={f.Y(0)} />
                <polyline fill="none" stroke={SERIES[0]} strokeWidth={2}
                  points={lags.filter((l) => l.r != null).map((l) => `${f.X(l.lag_days)},${f.Y(l.r)}`).join(" ")} />
                {lags.map((l) => l.r != null && <circle key={l.lag_days} cx={f.X(l.lag_days)} cy={f.Y(l.r)} r={4} fill={SERIES[0]} />)}
              </>
            );
          }} />
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
const GROUP_INK = { family: CATEGORICAL[0], far: CATEGORICAL[2] };
export function SteppedCurrentAllBandsFigure({ result }) {
  const bands = (result && result.bands) || [];
  const ratios = (result && result.ratios) || [];
  const keyOf = (b) => `${b.route}||${b.pair}`;
  const combos = Array.from(new Set(bands.map(keyOf)));
  const [combo, setCombo] = useState(combos[0]);
  const rows = bands.filter((b) => keyOf(b) === combo);
  const centres = rows.map((b) => b.centre_hz);
  const vals = rows.flatMap((b) => [b.relative_slope_per_mA, b.lo, b.hi].filter((v) => v != null));
  const ymax = Math.max(0.05, ...vals.map((v) => Math.abs(v)));
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
          <FigureSvg height={230} label="Change in settled band power per mA, relative to the band's own settled power" draw={(W) => {
            const f = frame(W, [Math.min(...centres) - 2, Math.max(...centres) + 2], [-ymax, ymax], 230, 64, 24);
            return (
              <>
                <Axes f={f} xticks={[10, 20, 30, 40, 50].map((v) => [v, v])} yticks={[-ymax, 0, ymax].map((v) => Math.round(v * 1000) / 1000)}
                  xlab="band centre (Hz)" ylab="change per mA (share of band power)" />
                <RefLine f={f} y={f.Y(0)} />
                {rows.map((b) => {
                  const grp = b.group === "family" || b.group === "far" ? b.group : null;
                  const col = grp ? GROUP_INK[grp] : CONTEXT;
                  return (
                    <g key={b.centre_hz}>
                      {b.lo != null && b.hi != null && (
                        <line x1={f.X(b.centre_hz)} x2={f.X(b.centre_hz)} y1={f.Y(b.lo)} y2={f.Y(b.hi)} stroke={col} strokeWidth={1.5} />
                      )}
                      {b.relative_slope_per_mA != null && <circle cx={f.X(b.centre_hz)} cy={f.Y(b.relative_slope_per_mA)} r={4} fill={col} />}
                    </g>
                  );
                })}
              </>
            );
          }} />
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
  const rows = (mode.rows || []).filter((r) => r.reading && r.reading.bands && r.reading.bands.rho != null);
  const keys = [["current_alone", "current alone", READING.current, -9], ["bands", "every band", READING.bands, 0],
    ["bands_without_current", "every band, current taken out", READING.adjusted, 9]];
  if (!rows.length) {
    return <div data-testid="figure-band_detector_research" style={BODY}>{"No sensing pair could be read."}</div>;
  }
  const rowH = 36;
  const h = 24 + rows.length * rowH + 48;
  const y = (i) => 24 + i * rowH + rowH / 2;
  return (
    <div data-testid="figure-band_detector_research">
      <FigureSvg height={h} label="How well pain is predicted in weeks not fitted on, per sensing pair and length of signal" draw={(W) => {
        const f = frame(W, [-0.6, 0.8], [0, 1], h, 150, LABEL_MARGIN + 30, 24, 48);
        return (
          <>
            <line x1={f.ml} x2={W - f.mr} y1={h - 48} y2={h - 48} stroke={T.graphic} strokeWidth={1} />
            {[-0.4, -0.2, 0, 0.2, 0.4, 0.6].map((v) => (
              <g key={v}>
                <line x1={f.X(v)} x2={f.X(v)} y1={h - 48} y2={h - 44} stroke={T.graphic} strokeWidth={1} />
                <text x={f.X(v)} y={h - 30} {...TEXT} textAnchor="middle" fill={T.ink3}>{v}</text>
              </g>
            ))}
            <line x1={f.X(0)} x2={f.X(0)} y1={18} y2={h - 48} stroke={T.graphic} strokeWidth={1} strokeDasharray="4 3" />
            <text x={f.X(0)} y={14} {...TEXT} textAnchor="middle" fill={T.ink3}>{"0 = chance"}</text>
            <text x={(W - f.mr + f.ml) / 2} y={h - 8} {...TEXT} textAnchor="middle" fill={T.ink3}>
              {"how well it predicts pain in weeks it was not fitted on (rank correlation; 0 = chance)"}
            </text>
            {rows.map((r, i) => {
              const d = r.reading;
              return (
                <g key={`${r.pair}-${r.seconds}`}>
                  <text x={f.ml - 10} y={y(i) + 4} {...TEXT} textAnchor="end" fill={T.ink}>{`${pairName(r.pair)}, ${r.seconds} s (${d.n})`}</text>
                  {keys.map(([k, , col, dy]) => {
                    const b = d[k];
                    if (k === "current_alone" || !b || b.rho == null || b.null_p95 == null) return null;
                    const v = Math.max(-0.6, Math.min(0.8, b.null_p95));
                    return <line key={`null-${k}`} data-null-for={k} data-null-value={String(b.null_p95)} x1={f.X(v)} x2={f.X(v)}
                      y1={y(i) + dy - 5} y2={y(i) + dy + 5} stroke={col} strokeWidth={2.5} />;
                  })}
                  {keys.map(([k, , col, dy]) => {
                    const b = d[k];
                    if (!b || b.rho == null) return null;
                    const lo = b.lo == null ? b.rho : Math.max(-0.6, b.lo);
                    const hi = b.hi == null ? b.rho : Math.min(0.8, b.hi);
                    return (
                      <g key={k}>
                        <line x1={f.X(lo)} x2={f.X(hi)} y1={y(i) + dy} y2={y(i) + dy} stroke={col} strokeWidth={1.5} />
                        <circle cx={f.X(Math.max(-0.6, Math.min(0.8, b.rho)))} cy={y(i) + dy} r={4.5}
                          fill={b.q != null && b.q < 0.05 ? col : T.surface} stroke={col} strokeWidth={1.5} />
                      </g>
                    );
                  })}
                </g>
              );
            })}
            <DirectLabels f={f} items={keys.map(([, lab, col, dy]) => ({ y: y(0) + dy, text: lab, color: col }))} />
          </>
        );
      }} />
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
  const bands = (p.bands || []).filter((b) => b.reading && b.reading.band && b.reading.band.auc != null);
  const h = 230;
  const first = bands.length ? bands[0].reading : {};
  const alone = first.current_alone && first.current_alone.auc;
  const series = [["band", "the band", READING.bands, -0.18], ["band_without_current", "the band, current taken out", READING.adjusted, 0.18]];
  const last = bands.length ? bands[bands.length - 1] : null;
  return (
    <div style={{ marginBottom: SPACE.sm }}>
      <div style={{ ...TYPE.body, color: T.ink }}>{`${pairName(p.pair)} (${first.n != null ? first.n : 0} ratings in the two pain groups with a device-timed reading)`}</div>
      <FigureSvg height={h} label={`How well each band tells high pain from low, ${pairName(p.pair)}`} draw={(W) => {
        const f = frame(W, [8, 30.5], [0.2, 1.0], h, 56, LABEL_MARGIN, 22, 44);
        const labels = last ? series.filter(([k]) => last.reading[k] && last.reading[k].auc != null)
          .map(([k, lab, col]) => ({ y: f.Y(Math.max(0.2, Math.min(1.0, last.reading[k].auc))), text: lab, color: col })) : [];
        return (
          <>
            <Axes f={f} xticks={[[10, "10"], [15, "15"], [20, "20"], [25, "25"], [30, "30"]]} yticks={[0.2, 0.4, 0.6, 0.8, 1.0]}
              xlab="band centre (Hz)" ylab="tells high pain from low" />
            <RefLine f={f} y={f.Y(0.5)} text="0.5 = coin toss" />
            {alone != null && (
              <g>
                <line x1={f.ml} x2={W - f.mr} y1={f.Y(alone)} y2={f.Y(alone)} stroke={CONTEXT} strokeWidth={1.5} strokeDasharray="6 4" />
                <text x={W - f.mr + 6} y={f.Y(alone) + (Math.abs(alone - 0.5) < 0.04 ? -8 : 4)} {...TEXT} fill={T.ink3}>{"current alone"}</text>
              </g>
            )}
            {bands.map((b) => (
              <g key={b.centre_hz} data-band={b.centre_hz}>
                {b.carries_folded_multiple && <line x1={f.X(b.centre_hz)} x2={f.X(b.centre_hz)} y1={f.Y(0.2) - 6} y2={f.Y(0.2)} stroke={T.ink} strokeWidth={1.5} />}
                {series.map(([k, , col, dx]) => {
                  const r = b.reading[k];
                  if (!r || r.auc == null) return null;
                  const cx = f.X(b.centre_hz + dx);
                  return (
                    <g key={k}>
                      {r.lo != null && <line x1={cx} x2={cx} y1={f.Y(Math.max(0.2, r.lo))} y2={f.Y(Math.min(1.0, r.hi))} stroke={col} strokeWidth={1.5} />}
                      <circle cx={cx} cy={f.Y(Math.max(0.2, Math.min(1.0, r.auc)))} r={3.5}
                        fill={r.q != null && r.q < 0.05 ? col : T.surface} stroke={col} strokeWidth={1.5} />
                    </g>
                  );
                })}
              </g>
            ))}
            <DirectLabels f={f} items={labels} />
          </>
        );
      }} />
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
