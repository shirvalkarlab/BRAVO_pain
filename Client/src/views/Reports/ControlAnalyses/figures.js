/**
 * Figures for the saved control analyses (2026-09-24). Each draws only what the saved result holds;
 * plain SVG, 11 px or larger, the palette's colour-blind-safe inks.
 */
import React, { useMemo, useState } from "react";


import { OKABE_ITO as OI } from "views/Reports/ClosedLoopSim/palette";

const INK = [OI.blue, OI.vermillion, OI.bluishGreen, OI.reddishPurple, OI.orange, OI.skyBlue];
const TXT = "#1A1A1A";
const SUB = "#5E5E5E";
const W = 640;

function frame(xs, ys, h = 240, ml = 52, mr = 14, mt = 16, mb = 38) {
  const [x0, x1] = xs; const [y0, y1] = ys;
  const X = (v) => ml + ((v - x0) / (x1 - x0)) * (W - ml - mr);
  const Y = (v) => h - mb - ((v - y0) / (y1 - y0)) * (h - mt - mb);
  return { X, Y, h, ml, mr, mt, mb };
}

function Axes({ f, xticks, yticks, xlab, ylab }) {
  return (
    <g>
      {yticks.map((v) => (
        <g key={`y${v}`}>
          <line x1={f.ml} x2={W - f.mr} y1={f.Y(v)} y2={f.Y(v)} stroke={v === 0 ? "#9E9E9E" : "#E4E4E4"} strokeWidth={v === 0 ? 1.4 : 1} />
          <text x={f.ml - 6} y={f.Y(v) + 4} fontSize={11} textAnchor="end" fill={SUB}>{v}</text>
        </g>
      ))}
      {xticks.map(([v, l]) => (
        <text key={`x${v}`} x={f.X(v)} y={f.h - f.mb + 16} fontSize={11} textAnchor="middle" fill={SUB}>{l}</text>
      ))}
      <text x={(W + f.ml) / 2} y={f.h - 4} fontSize={11} textAnchor="middle" fill={SUB}>{xlab}</text>
      <text x={13} y={(f.h - f.mb + f.mt) / 2} fontSize={11} textAnchor="middle" fill={SUB}
        transform={`rotate(-90 13 ${(f.h - f.mb + f.mt) / 2})`}>{ylab}</text>
    </g>
  );
}

const SELECT = { fontSize: 13, padding: "2px 6px", marginRight: 12 };
const WORD = { ZERO: "0", ONE: "1", TWO: "2", THREE: "3" };
/** A sensing pair as the pages write it: ONE_THREE_LEFT -> L 1-3+. */
export function pairName(ch) {
  const p = String(ch).split("_");
  return p.length === 3 && WORD[p[0]] && WORD[p[1]] && (p[2] === "LEFT" || p[2] === "RIGHT")
    ? `${p[2][0]} ${WORD[p[0]]}-${WORD[p[1]]}\u207A` : String(ch);
}

/** 1. Band against pain with the current off: per band, one series per stretch; filled where q < 0.05. */
export function ZeroMaFigure({ result }) {
  const bands = (result && result.bands) || [];
  const pairs = useMemo(() => Array.from(new Set(bands.map((b) => b.pair))), [bands]);
  const scores = useMemo(() => Array.from(new Set(bands.map((b) => b.score))), [bands]);
  const [pair, setPair] = useState(pairs.includes("ONE_THREE_LEFT") ? "ONE_THREE_LEFT" : pairs[0]);
  const [score, setScore] = useState(scores.includes("vas") ? "vas" : scores[0]);
  const rows = bands.filter((b) => b.pair === pair && b.score === score);
  const stretches = Array.from(new Set(rows.map((b) => b.stretch)));
  const centres = rows.map((b) => b.centre);
  const f = frame([Math.min(...centres, 8) - 0.8, Math.max(...centres, 30) + 0.8], [-0.8, 0.8], 250);
  const cov = ((result && result.coverage) || []).filter((c) => c.pair === pair && c.score === score);
  return (
    <div data-testid="figure-zero_ma_within_stretch">
      <div style={{ fontSize: 13, color: TXT, margin: "4px 0 6px" }}>
        <label>Sensing pair <select value={pair} onChange={(e) => setPair(e.target.value)} style={SELECT}>
          {pairs.map((p) => <option key={p} value={p}>{pairName(p)}</option>)}</select></label>
        <label>Pain score <select value={score} onChange={(e) => setScore(e.target.value)} style={SELECT}>
          {scores.map((s) => <option key={s} value={s}>{s}</option>)}</select></label>
      </div>
      <svg viewBox={`0 0 ${W} ${f.h}`} width="100%" role="img" aria-label="Correlation of each band with pain in each stretch">
        <Axes f={f} xticks={[10, 15, 20, 25, 30].map((v) => [v, v])} yticks={[-0.6, -0.3, 0, 0.3, 0.6]}
          xlab="band centre (Hz)" ylab="correlation with pain" />
        {stretches.map((s, k) => rows.filter((b) => b.stretch === s).map((b) => {
          const x = f.X(b.centre) + (k - (stretches.length - 1) / 2) * 5;
          const col = INK[k % INK.length];
          return (
            <g key={`${s}-${b.centre}`}>
              {Number.isFinite(b.lo) && <line x1={x} x2={x} y1={f.Y(b.lo)} y2={f.Y(b.hi)} stroke={col} strokeWidth={1.6} />}
              <circle cx={x} cy={f.Y(b.rho)} r={3.8} fill={b.q < 0.05 ? col : "#FFFFFF"} stroke={col} strokeWidth={1.6} />
            </g>
          );
        }))}
      </svg>
      <div style={{ fontSize: 12, color: SUB, marginTop: 2 }}>
        {stretches.map((s, k) => (
          <span key={s} style={{ marginRight: 14, whiteSpace: "nowrap" }}>
            <span style={{ color: INK[k % INK.length], fontSize: 14 }}>{"●"}</span>{` ${s}`}
          </span>
        ))}
        <span>{"Filled: survives correction for the bands tested (q < 0.05). Lines: 95% intervals from whole days."}</span>
      </div>
      <table data-testid="zero-ma-coverage" style={{ fontSize: 12.5, color: TXT, borderCollapse: "collapse", marginTop: 8 }}>
        <thead><tr>{["Stretch", "Ratings", "Days rated", "With a recording within 60 min", "Same day", "Days"].map((h) => (
          <th key={h} style={{ textAlign: "left", padding: "2px 10px 2px 0", color: SUB, fontWeight: 500 }}>{h}</th>))}</tr></thead>
        <tbody>{cov.map((c) => (
          <tr key={c.stretch}>
            <td style={{ padding: "2px 10px 2px 0" }}>{c.stretch}</td><td>{c.reports}</td><td>{c.days_with_reports}</td>
            <td>{c.matched_60min}</td><td>{c.matched_same_day}</td><td>{c.days_matched}</td>
          </tr>))}</tbody>
      </table>
    </div>
  );
}

/** 2. What the current explains: per pair and length, the current alone, every band, bands without the current, and the shuffled-data 95th. */
export function CurrentExplainsFigure({ result }) {
  const rows = ((result && result.rows) || []).filter((r) => r.bands != null);
  const h = 30 + rows.length * 26 + 40;
  const f = frame([0.3, 0.95], [0, 1], h, 190, 14, 24, 38);
  const y = (i) => 24 + i * 26 + 13;
  const keys = [["current_alone", "current alone", OI.gray], ["bands", "every band", OI.blue],
    ["bands_without_current", "bands without the current", OI.vermillion]];
  return (
    <div data-testid="figure-current_explains">
      <svg viewBox={`0 0 ${W} ${h}`} width="100%" role="img" aria-label="Out-of-sample score of the current and the bands per sensing pair">
        {[0.4, 0.5, 0.6, 0.7, 0.8, 0.9].map((v) => (
          <g key={v}><line x1={f.X(v)} x2={f.X(v)} y1={18} y2={h - 38} stroke={v === 0.5 ? "#9E9E9E" : "#E4E4E4"} />
            <text x={f.X(v)} y={h - 22} fontSize={11} textAnchor="middle" fill={SUB}>{v}</text></g>
        ))}
        <text x={(W + 190) / 2} y={h - 6} fontSize={11} textAnchor="middle" fill={SUB}>out-of-sample score (0.5 is chance)</text>
        {rows.map((r, i) => (
          <g key={`${r.pair}-${r.seconds}`}>
            <text x={184} y={y(i) + 4} fontSize={12} textAnchor="end" fill={TXT}>{`${pairName(r.pair)}, ${r.seconds} s (${r.n})`}</text>
            {r.null_p95 != null && <line x1={f.X(r.null_p95)} x2={f.X(r.null_p95)} y1={y(i) - 9} y2={y(i) + 9} stroke={TXT} strokeWidth={2} />}
            {keys.map(([k, , col]) => r[k] != null && (
              <circle key={k} cx={f.X(r[k])} cy={y(i)} r={4.5} fill={col} />
            ))}
          </g>
        ))}
      </svg>
      <div style={{ fontSize: 12, color: SUB }}>
        {keys.map(([k, lab, col]) => (
          <span key={k} style={{ marginRight: 14, whiteSpace: "nowrap" }}><span style={{ color: col, fontSize: 14 }}>{"●"}</span>{` ${lab}`}</span>
        ))}
        <span>{"| the 95th percentile of shuffled data that keeps pain's own persistence"}</span>
      </div>
    </div>
  );
}

/** 4. A current with memory: held-out R2 against the time constant, one line per pain score; and the drift table. */
export function CurrentMemoryFigure({ result }) {
  const curves = (result && result.curves) || [];
  const taus = curves.length ? curves[0].rows.map((r) => r.tau_h) : [];
  const lab = (t) => (t === 0 ? "0" : t < 24 ? `${t} h` : `${t / 24} d`);
  const all = curves.flatMap((c) => c.rows.map((r) => r.r2));
  const lo = Math.min(-0.2, ...all); const hi = Math.max(0.3, ...all);
  const f = frame([-0.4, Math.max(taus.length - 0.6, 1)], [lo, hi], 240);
  const ticks = [lo, 0, hi].map((v) => Math.round(v * 10) / 10);
  const drift = (result && result.drift) || [];
  const strata = Array.from(new Set(drift.filter((d) => d.stratum).map((d) => d.stratum)));
  return (
    <div data-testid="figure-current_with_memory">
      <svg viewBox={`0 0 ${W} ${f.h}`} width="100%" role="img" aria-label="Held-out R squared against how long the current is remembered">
        <Axes f={f} xticks={taus.map((t, i) => [i, lab(t)])} yticks={Array.from(new Set(ticks))}
          xlab="how long the current is remembered (0 is the current in force)" ylab="held-out R2" />
        {curves.map((c, k) => (
          <g key={c.score}>
            <polyline fill="none" stroke={INK[k]} strokeWidth={2} points={c.rows.map((r, i) => `${f.X(i)},${f.Y(r.r2)}`).join(" ")} />
            {c.rows.map((r, i) => <circle key={i} cx={f.X(i)} cy={f.Y(r.r2)} r={4} fill={INK[k]} />)}
          </g>
        ))}
      </svg>
      <div style={{ fontSize: 12, color: SUB }}>
        {curves.map((c, k) => (
          <span key={c.score} style={{ marginRight: 14 }}><span style={{ color: INK[k], fontSize: 14 }}>{"●"}</span>{` ${c.score} (${c.n} ratings)`}</span>
        ))}
      </div>
      {strata.length > 0 && (
        <table data-testid="memory-drift" style={{ fontSize: 12.5, color: TXT, borderCollapse: "collapse", marginTop: 8 }}>
          <thead><tr><th style={{ textAlign: "left", color: SUB, fontWeight: 500, paddingRight: 10 }}>Pain surface</th>
            {taus.map((t) => <th key={t} style={{ color: SUB, fontWeight: 500, padding: "2px 10px" }}>{lab(t)}</th>)}</tr></thead>
          <tbody>{strata.map((s) => (
            <tr key={s}><td style={{ paddingRight: 10 }}>{s}</td>
              {taus.map((t) => {
                const d = drift.find((x) => x.stratum === s && x.tau_h === t);
                const moves = d && d.verdict === "moves between blocks of time";
                return <td key={t} style={{ textAlign: "center", color: moves ? OI.vermillion : SUB }}>{d ? (moves ? "moves" : "–") : ""}</td>;
              })}</tr>))}</tbody>
        </table>
      )}
      {strata.length > 0 && (
        <div style={{ fontSize: 12, color: SUB, paddingTop: 4 }}>
          {"\u201Cmoves\u201D: the surface's held-out misses are shared by whole blocks of time (decision 253), with each setting's current replaced by its remembered value."}
        </div>
      )}
    </div>
  );
}

const CELL = { padding: "2px 10px 2px 0", whiteSpace: "nowrap" };
const HEADC = { ...CELL, textAlign: "left", color: SUB, fontWeight: 500 };

/** 3. Time of day and weekends: per sensing pair, how many bands carry a daily cycle or a weekend
 * difference; and pain at weekends against weekdays within the week. */
export function TimeOfDayFigure({ result }) {
  const bands = (result && result.bands) || [];
  const pairs = Array.from(new Set(bands.map((b) => b.channel)));
  const pain = ((result && result.pain) || []).filter((p) => p.within_week != null);
  const count = (ch, f) => bands.filter((b) => b.channel === ch && !b.why && f(b)).length;
  return (
    <div data-testid="figure-time_of_day" style={{ fontSize: 12.5, color: TXT }}>
      <table style={{ borderCollapse: "collapse" }}>
        <thead><tr>{["Sensing pair", "Recordings", "Daily cycle above chance", "Higher at weekends", "Lower at weekends"].map((h) => <th key={h} style={HEADC}>{h}</th>)}</tr></thead>
        <tbody>{pairs.map((ch) => {
          const first = bands.find((b) => b.channel === ch && !b.why);
          return (
            <tr key={ch}><td style={CELL}>{pairName(ch)}</td><td style={CELL}>{first ? first.n : "\u2013"}</td>
              <td style={CELL}>{`${count(ch, (b) => b.R_daily_ci[0] > b.R_daily_shuffle_p95)} of 22`}</td>
              <td style={CELL}>{count(ch, (b) => b.r_weekend_ci[0] > 0)}</td>
              <td style={CELL}>{count(ch, (b) => b.r_weekend_ci[1] < 0)}</td></tr>
          );
        })}</tbody>
      </table>
      <table style={{ borderCollapse: "collapse", marginTop: 10 }}>
        <thead><tr>{["Pain score", "Weekend minus weekday, within the week", "95% interval", "p", "Weeks"].map((h) => <th key={h} style={HEADC}>{h}</th>)}</tr></thead>
        <tbody>{pain.map((p) => (
          <tr key={p.score}><td style={CELL}>{p.score}</td><td style={CELL}>{p.within_week.toFixed(2)}</td>
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
  const cell = (w) => (w && w.mean != null ? `${w.mean.toFixed(2)} (${w.n})` : "\u2013");
  return (
    <div data-testid="figure-onoff_switches" style={{ fontSize: 12.5, color: TXT }}>
      <table style={{ borderCollapse: "collapse" }}>
        <thead><tr><th style={HEADC}>{"Switch"}</th><th style={HEADC}>{"14 days before"}</th>
          {windows.map((d) => <th key={d} style={HEADC}>{`${d} days after`}</th>)}</tr></thead>
        <tbody>{rows.map((r) => (
          <tr key={r.label}><td style={CELL}>{r.label}</td><td style={CELL}>{cell(r.before)}</td>
            {r.after.map((w) => <td key={w.days} style={CELL}>{cell(w)}</td>)}</tr>))}</tbody>
      </table>
      <div style={{ fontSize: 12, color: SUB, marginTop: 4 }}>{"Mean pain, with the number of ratings in brackets. Descriptive: no statistics, and a window may run into the next switch."}</div>
    </div>
  );
}

/** 6. Up the ladder and down: pain on the way down minus on the way up at each current, per side;
 * filled where the fall came after the rise, hollow where it came first; the held re-ratings; the
 * ladders' settled band power. */
const SIDE_INK = { Left: OI.blue, Right: OI.vermillion };
const signed = (v, d = 2) => (v == null ? "\u2013" : `${v >= 0 ? "+" : ""}${v.toFixed(d)}`);
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
  const f = frame([-0.2, xmax + 0.3], [-ymax, ymax], 230);
  const yt = [-ymax, 0, ymax].map((v) => Math.round(v * 10) / 10);
  const xt = Array.from({ length: Math.floor(xmax) + 1 }, (_, i) => [i, `${i}`]);
  const sides = Object.entries(p.by_side || {});
  const headline = ORDER_WORDS[p.verdict] || (p.sentence ? `${p.sentence[0].toUpperCase()}${p.sentence.slice(1)}.` : "");
  return (
    <div data-testid="figure-carry_over_ladder" style={{ fontSize: 12.5, color: TXT }}>
      {items.length > 1 && (
        <select aria-label="Pain site" value={item} onChange={(e) => setItem(e.target.value)} style={SELECT}>
          {pain.map((x) => <option key={x.item} value={x.item}>{x.words}</option>)}
        </select>
      )}
      <div style={{ padding: "4px 0" }}>
        {pts.length ? `${headline}${sides.length ? ` By side: ${sides.map(([sd, x]) => `${sd.toLowerCase()} ${signed(x.mean)} (${x.n_pairs} currents)`).join(", ")}.` : ""}`
          : `No current was rated for ${p.words || item} on both the way up and the way down within one visit.`}
      </div>
      {pts.length > 0 && (
        <svg viewBox={`0 0 ${W} ${f.h}`} width="100%" role="img" aria-label="Pain on the way down minus on the way up, at each current">
          <Axes f={f} xticks={xt} yticks={Array.from(new Set(yt))} xlab="current on the side that was stepped (mA)"
            ylab="down minus up (points of pain)" />
          {pts.map((r, i) => (
            <circle key={i} cx={f.X(r.current_mA)} cy={f.Y(r.diff)} r={5.5}
              fill={r.falling_first ? "#FFFFFF" : SIDE_INK[r.side] || INK[0]} stroke={SIDE_INK[r.side] || INK[0]} strokeWidth={2} />
          ))}
        </svg>
      )}
      {pts.length > 0 && (
        <div style={{ fontSize: 12, color: SUB }}>
          {Object.entries(SIDE_INK).map(([sd, c]) => <span key={sd} style={{ marginRight: 14 }}><span style={{ color: c, fontSize: 14 }}>{"\u25CF"}</span>{` ${sd.toLowerCase()} side stepped`}</span>)}
          <span>{"filled: the fall came after the rise; hollow: the fall came first. Below zero: less pain on the way down."}</span>
        </div>
      )}
      <table data-testid="carry-over-holds" style={{ borderCollapse: "collapse", marginTop: 10 }}>
        <thead><tr>{["Pain site", "Stimulation", "Rated twice at one setting", "Median minutes apart", "Second minus first", "95% interval", "Lower / higher / same"].map((h) => <th key={h} style={HEADC}>{h}</th>)}</tr></thead>
        <tbody>{holds.filter((h) => h.n_pairs).map((h) => (
          <tr key={`${h.item}${h.on}`}><td style={CELL}>{h.words}</td><td style={CELL}>{h.on ? "on" : "off"}</td>
            <td style={CELL}>{`${h.n_pairs} times, ${h.n_visits} visits`}</td>
            <td style={CELL}>{h.minutes_median == null ? "\u2013" : h.minutes_median.toFixed(0)}</td>
            <td style={CELL}>{signed(h.mean)}</td>
            <td style={CELL}>{h.lo == null ? "\u2013" : `${signed(h.lo)} to ${signed(h.hi)}`}</td>
            <td style={CELL}>{`${h.n_lower} / ${h.n_higher} / ${h.n_same}`}</td></tr>))}</tbody>
      </table>
      {ladder.length > 0 && (
        <table data-testid="carry-over-ladder-power" style={{ borderCollapse: "collapse", marginTop: 10 }}>
          <thead><tr>{["Settled band power, route", "Sensing pair", "Ladder runs", "Bands (8.5\u201329.5 Hz)", "Median band, down against up", "Higher / lower", "Order"].map((h) => <th key={h} style={HEADC}>{h}</th>)}</tr></thead>
          <tbody>{ladder.map((L) => (
            <tr key={`${L.source}${L.pair}`}><td style={CELL}>{L.source}</td><td style={CELL}>{pairName(L.pair)}</td>
              <td style={CELL}>{L.n_runs}</td><td style={CELL}>{L.n_bands}</td>
              <td style={CELL}>{L.median_over_bands == null ? "\u2013" : `${signed(100 * L.median_over_bands, 1)}%`}</td>
              <td style={CELL}>{`${L.bands_higher} / ${L.bands_lower}`}</td>
              <td style={CELL}>{L.verdict === "one order" ? "every fall after its rise" : "both orders"}</td></tr>))}</tbody>
        </table>
      )}
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
};
