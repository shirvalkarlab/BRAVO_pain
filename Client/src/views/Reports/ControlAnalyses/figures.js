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

/** 2. What the current explains: per pair and length, the current alone, every band and bands without the
 * current, each reading against its OWN shuffled-data 95th (decision 314): every band against the plain
 * rotations, the bands without the current against the rotations refitted with the current taken out
 * (decision 276); the current alone has no null. A bar is drawn in its reading's colour on its reading's row. */
export function CurrentExplainsFigure({ result }) {
  const rows = ((result && result.rows) || []).filter((r) => r.bands != null);
  const rowH = 32;
  const h = 30 + rows.length * rowH + 40;
  const f = frame([0.3, 0.95], [0, 1], h, 190, 14, 24, 38);
  const y = (i) => 24 + i * rowH + rowH / 2;
  const keys = [["current_alone", "current alone", OI.gray, -9, null], ["bands", "every band", OI.blue, 0, "null_p95"],
    ["bands_without_current", "bands without the current", OI.vermillion, 9, "bands_without_current_null_p95"]];
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
            {keys.map(([k, , col, dy, nk]) => nk && r[k] != null && r[nk] != null && (
              <line key={`null-${k}`} data-null-for={k} data-null-value={String(r[nk])} x1={f.X(r[nk])} x2={f.X(r[nk])}
                y1={y(i) + dy - 5} y2={y(i) + dy + 5} stroke={col} strokeWidth={2.4} />
            ))}
            {keys.map(([k, , col, dy]) => r[k] != null && (
              <circle key={k} data-reading={k} cx={f.X(r[k])} cy={y(i) + dy} r={4} fill={col} />
            ))}
          </g>
        ))}
      </svg>
      <div style={{ fontSize: 12, color: SUB }}>
        {keys.map(([k, lab, col]) => (
          <span key={k} style={{ marginRight: 14, whiteSpace: "nowrap" }}><span style={{ color: col, fontSize: 14 }}>{"\u25CF"}</span>{` ${lab}`}</span>
        ))}
        <span>{"| bar beside a dot, in its colour: the 95th percentile of its own shuffled data (pain's persistence kept; the current alone has none)"}</span>
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
const signedN = (v, d = 1) => (v == null ? "–" : `${v >= 0 ? "+" : ""}${v.toFixed(d)}`);

/** 7. Regression to the mean at one setting (decision 253): the setting delivered most often in
 * one rate/pulse-width group, its own block averages against every other setting in the same
 * group, and whether the swing stands out from every other way of splitting the same
 * setting-periods (internal) or from any similar run elsewhere in the record (outside).
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
      <div data-testid="figure-regression_to_mean" style={{ fontSize: 12.5, color: SUB }}>
        {(result && result.reason) || "Nothing to read yet."}
      </div>
    );
  }
  const allMeans = [...(target.by_block || []), ...(other.by_block || [])].map((r) => r.mean);
  const ymax = Math.max(1, ...allMeans.map((v) => Math.abs(v)));
  const f = frame([-0.4, nBlocks - 0.6], [-ymax, ymax], 220);
  const yt = Array.from(new Set([-ymax, 0, ymax].map((v) => Math.round(v * 10) / 10)));
  const series = [
    ["target", `${setting.amp_mA_Left}/${setting.amp_mA_Right} mA (${result.n_target || 0} setting-periods)`, OI.blue, target],
    ["other", `every other setting in this group (${result.n_other || 0})`, OI.vermillion, other],
  ];
  return (
    <div data-testid="figure-regression_to_mean" style={{ fontSize: 12.5, color: TXT }}>
      <svg viewBox={`0 0 ${W} ${f.h}`} width="100%" role="img"
        aria-label="Block averages of the target setting against every other setting in the same group">
        <Axes f={f} xticks={blocks.map((b) => [b, `block ${b + 1}`])} yticks={yt}
          xlab="time block" ylab="pain relative to today (J)" />
        {series.map(([key, , col, g], k) => (
          <g key={key}>
            {(g.by_block || []).map((r) => {
              const x = f.X(r.block) + (k - 0.5) * 8;
              return (
                <g key={`${key}-${r.block}`}>
                  {Number.isFinite(r.se) && (
                    <line x1={x} x2={x} y1={f.Y(r.mean - r.se)} y2={f.Y(r.mean + r.se)} stroke={col} strokeWidth={1.6} />
                  )}
                  <circle cx={x} cy={f.Y(r.mean)} r={4.5} fill={col} />
                </g>
              );
            })}
          </g>
        ))}
      </svg>
      <div style={{ fontSize: 12, color: SUB }}>
        {series.map(([key, lab, col]) => (
          <span key={key} style={{ marginRight: 14 }}><span style={{ color: col, fontSize: 14 }}>{"●"}</span>{` ${lab}`}</span>
        ))}
        <span>{"Lines: ± 1 standard error, weighted by each setting-period's own rating noise."}</span>
      </div>
      <table data-testid="regression-to-mean-comparisons" style={{ borderCollapse: "collapse", marginTop: 10 }}>
        <thead><tr>{["Comparison", "Reads", "Usable"].map((h) => <th key={h} style={HEADC}>{h}</th>)}</tr></thead>
        <tbody>
          <tr>
            <td style={CELL}>{"Internal: specific to this current pair?"}</td>
            <td style={CELL}>{internal.p_two_sided != null
              ? `${(internal.p_two_sided * 100).toFixed(1)}% of splits match or exceed it (same direction ${(internal.p_same_direction * 100).toFixed(1)}%)`
              : (internal.reason || "not computable")}</td>
            <td style={CELL}>{internal.n_valid != null ? `${internal.n_valid} of ${internal.n_total} splits` : "–"}</td>
          </tr>
          <tr>
            <td style={CELL}>{"Outside: common anywhere in the record?"}</td>
            <td style={CELL}>{outside.fraction_ge != null
              ? `${(outside.fraction_ge * 100).toFixed(1)}% of runs elsewhere match or exceed it`
              : "not computable"}</td>
            <td style={CELL}>{outside.n_windows ? `${outside.n_windows} overlapping runs of ${outside.window_size}` : "–"}</td>
          </tr>
          <tr>
            <td style={CELL}>{"Extremity: how unusual was block 1?"}</td>
            <td style={CELL}>{extremity.value != null
              ? `${signedN(extremity.value)} standard errors from the record's own long-run average`
              : (extremity.reason || "not computable")}</td>
            <td style={CELL}>{"–"}</td>
          </tr>
        </tbody>
      </table>
      <div style={{ fontSize: 12, color: SUB, marginTop: 4 }}>
        {"Descriptive: never selects a setting or blocks a recommendation. The outside runs overlap heavily and are not independent looks."}
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
  const f = frame([0.4, 7.6], [-1, 1], 220);
  const targetsAll = r.calendar_days_needed || [];
  const targetsZero = (r.zero_ma && r.zero_ma.calendar_days_needed) || [];
  const targetRows = targetsAll.length ? targetsAll : targetsZero;
  return (
    <div data-testid="figure-rating_persistence" style={{ fontSize: 12.5, color: TXT }}>
      {scores.length > 1 && (
        <select aria-label="Pain score" value={score} onChange={(e) => setScore(e.target.value)} style={SELECT}>
          {scores.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
      )}
      {lags.length > 0 ? (
        <>
          <svg viewBox={`0 0 ${W} ${f.h}`} width="100%" role="img"
            aria-label="Day-to-day correlation of daily mean ratings at each lag">
            <Axes f={f} xticks={lags.map((l) => [l.lag_days, `${l.lag_days} d`])} yticks={[-1, -0.5, 0, 0.5, 1]}
              xlab="lag (calendar days)" ylab="correlation" />
            <polyline fill="none" stroke={INK[0]} strokeWidth={2}
              points={lags.filter((l) => l.r != null).map((l) => `${f.X(l.lag_days)},${f.Y(l.r)}`).join(" ")} />
            {lags.map((l) => l.r != null && <circle key={l.lag_days} cx={f.X(l.lag_days)} cy={f.Y(l.r)} r={4} fill={INK[0]} />)}
          </svg>
          <div style={{ fontSize: 12, color: SUB }}>
            {`${r.score} (${r.n_ratings} ratings, ${r.n_days} days). `}
            {r.effective_days != null && `${r.effective_days.toFixed(1)} of those days count as independent (${Math.round(100 * r.ratio)}%).`}
          </div>
        </>
      ) : (
        <div style={{ fontSize: 12.5, color: SUB }}>{"Too few days with a rating to read."}</div>
      )}
      {r.zero_ma && r.zero_ma.effective_days != null && (
        <div style={{ fontSize: 12.5, color: TXT, marginTop: 6 }}>
          {`0 mA stretch (${r.zero_ma.label}, ${r.zero_ma.n_days} days): ${r.zero_ma.effective_days.toFixed(1)} independent days (${Math.round(100 * r.zero_ma.ratio)}%).`}
        </div>
      )}
      {targetRows.length > 0 && (
        <table data-testid="rating-persistence-targets" style={{ borderCollapse: "collapse", marginTop: 10 }}>
          <thead><tr>{["Report 02's target", "Independent days", "Calendar days here (all data)", "Calendar days here (0 mA stretch)"].map((h) => (
            <th key={h} style={HEADC}>{h}</th>))}</tr></thead>
          <tbody>{targetRows.map((t, i) => (
            <tr key={t.name}>
              <td style={CELL}>{t.name}</td>
              <td style={CELL}>{t.independent_days}</td>
              <td style={CELL}>{targetsAll[i] && targetsAll[i].calendar_days != null ? Math.round(targetsAll[i].calendar_days) : "–"}</td>
              <td style={CELL}>{targetsZero[i] && targetsZero[i].calendar_days != null ? Math.round(targetsZero[i].calendar_days) : "–"}</td>
            </tr>))}</tbody>
        </table>
      )}
      <div style={{ fontSize: 12, color: SUB, marginTop: 4 }}>
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
const GROUP_INK = { family: OI.blue, far: OI.vermillion };
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
  const f = centres.length
    ? frame([Math.min(...centres) - 2, Math.max(...centres) + 2], [-ymax, ymax], 230)
    : frame([0, 1], [-1, 1], 230);
  const current = ratios.find((r) => `${r.route}||${r.pair}` === combo);
  return (
    <div data-testid="figure-stepped_current_all_bands" style={{ fontSize: 12.5, color: TXT }}>
      {combos.length > 1 && (
        <select aria-label="Route and sensing pair" value={combo} onChange={(e) => setCombo(e.target.value)} style={SELECT}>
          {combos.map((c) => {
            const [route, pair] = c.split("||");
            return <option key={c} value={c}>{`${route}, ${pairName(pair)}`}</option>;
          })}
        </select>
      )}
      {rows.length > 0 ? (
        <>
          <svg viewBox={`0 0 ${W} ${f.h}`} width="100%" role="img"
            aria-label="Change in settled band power per mA, relative to the band's own settled power">
            <Axes f={f} xticks={[10, 20, 30, 40, 50].map((v) => [v, v])} yticks={[-ymax, 0, ymax].map((v) => Math.round(v * 1000) / 1000)}
              xlab="band centre (Hz)" ylab="change per mA (fraction of band power)" />
            {rows.map((b) => {
              const grp = b.group === "family" || b.group === "far" ? b.group : null;
              const col = grp ? GROUP_INK[grp] : OI.gray;
              return (
                <g key={b.centre_hz}>
                  {b.lo != null && b.hi != null && (
                    <line x1={f.X(b.centre_hz)} x2={f.X(b.centre_hz)} y1={f.Y(b.lo)} y2={f.Y(b.hi)} stroke={col} strokeWidth={1.6} />
                  )}
                  {b.relative_slope_per_mA != null && <circle cx={f.X(b.centre_hz)} cy={f.Y(b.relative_slope_per_mA)} r={4} fill={col} />}
                </g>
              );
            })}
          </svg>
          <div style={{ fontSize: 12, color: SUB }}>
            <span style={{ marginRight: 14 }}><span style={{ color: GROUP_INK.family, fontSize: 14 }}>{"●"}</span>{" 21.5–27.5 Hz family"}</span>
            <span style={{ marginRight: 14 }}><span style={{ color: GROUP_INK.far, fontSize: 14 }}>{"●"}</span>{" far bands (< 12 Hz or > 32 Hz)"}</span>
            <span>{"Lines: 95% intervals resampling whole ladder runs."}</span>
          </div>
        </>
      ) : (
        <div style={{ fontSize: 12.5, color: SUB }}>{"No stored titration-ladder points for this participant."}</div>
      )}
      {current && current.far_over_family_ratio != null && (
        <div style={{ fontSize: 12.5, color: TXT, marginTop: 6 }}>
          {`Family ${(100 * current.family_median_abs_relative_slope).toFixed(1)}% per mA at the median band; `}
          {`far bands ${(100 * current.far_median_abs_relative_slope).toFixed(1)}%; `}
          {`ratio (far over family) ${current.far_over_family_ratio.toFixed(2)}.`}
        </div>
      )}
      {ratios.length > 0 && (
        <table data-testid="stepped-current-ratios" style={{ borderCollapse: "collapse", marginTop: 10 }}>
          <thead><tr>{["Route", "Sensing pair", "Family bands", "Far bands", "Family change/mA", "Far change/mA", "Ratio (far / family)"].map((h) => (
            <th key={h} style={HEADC}>{h}</th>))}</tr></thead>
          <tbody>{ratios.map((r) => (
            <tr key={`${r.route}${r.pair}`}>
              <td style={CELL}>{r.route}</td><td style={CELL}>{pairName(r.pair)}</td>
              <td style={CELL}>{r.n_family_bands}</td><td style={CELL}>{r.n_far_bands}</td>
              <td style={CELL}>{r.family_median_abs_relative_slope != null ? `${(100 * r.family_median_abs_relative_slope).toFixed(1)}%` : "–"}</td>
              <td style={CELL}>{r.far_median_abs_relative_slope != null ? `${(100 * r.far_median_abs_relative_slope).toFixed(1)}%` : "–"}</td>
              <td style={CELL}>{r.far_over_family_ratio != null ? r.far_over_family_ratio.toFixed(2) : "–"}</td>
            </tr>))}</tbody>
        </table>
      )}
      <div style={{ fontSize: 12, color: SUB, marginTop: 4 }}>
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
  const keys = [["current_alone", "current alone", OI.gray, -9], ["bands", "every band", OI.blue, 0],
    ["bands_without_current", "every band, current taken out", OI.vermillion, 9]];
  if (!rows.length) {
    return <div data-testid="figure-band_detector_research" style={{ fontSize: 12.5, color: SUB }}>{"No sensing pair could be read."}</div>;
  }
  const ml = 200; const rowH = 36;
  const h = 24 + rows.length * rowH + 40;
  const f = frame([-0.6, 0.8], [0, 1], h, ml, 14, 24, 38);
  const y = (i) => 24 + i * rowH + rowH / 2;
  return (
    <div data-testid="figure-band_detector_research">
      <svg viewBox={`0 0 ${W} ${h}`} width="100%" role="img" aria-label="Held-out rank correlation of pain with its prediction, per sensing pair and length">
        {[-0.4, -0.2, 0, 0.2, 0.4, 0.6].map((v) => (
          <g key={v}><line x1={f.X(v)} x2={f.X(v)} y1={18} y2={h - 38} stroke={v === 0 ? "#6E6E6E" : "#E4E4E4"} strokeWidth={v === 0 ? 1.4 : 1} />
            <text x={f.X(v)} y={h - 22} fontSize={11} textAnchor="middle" fill={SUB}>{v}</text></g>
        ))}
        <text x={(W + ml) / 2} y={h - 6} fontSize={11} textAnchor="middle" fill={SUB}>{"held-out rank correlation of pain with its prediction (0 is chance)"}</text>
        {rows.map((r, i) => {
          const d = r.reading;
          return (
            <g key={`${r.pair}-${r.seconds}`}>
              <text x={ml - 6} y={y(i) + 4} fontSize={12} textAnchor="end" fill={TXT}>{`${pairName(r.pair)}, ${r.seconds} s (${d.n})`}</text>
              {keys.map(([k, , col, dy]) => {
                const b = d[k];
                if (k === "current_alone" || !b || b.rho == null || b.null_p95 == null) return null;
                const v = Math.max(-0.6, Math.min(0.8, b.null_p95));
                return <line key={`null-${k}`} data-null-for={k} data-null-value={String(b.null_p95)} x1={f.X(v)} x2={f.X(v)}
                  y1={y(i) + dy - 5} y2={y(i) + dy + 5} stroke={col} strokeWidth={2.4} />;
              })}
              {keys.map(([k, , col, dy]) => {
                const b = d[k];
                if (!b || b.rho == null) return null;
                const lo = b.lo == null ? b.rho : Math.max(-0.6, b.lo);
                const hi = b.hi == null ? b.rho : Math.min(0.8, b.hi);
                return (
                  <g key={k}>
                    <line x1={f.X(lo)} x2={f.X(hi)} y1={y(i) + dy} y2={y(i) + dy} stroke={col} strokeWidth={1.6} />
                    <circle cx={f.X(Math.max(-0.6, Math.min(0.8, b.rho)))} cy={y(i) + dy} r={4.5}
                      fill={b.q != null && b.q < 0.05 ? col : "#FFFFFF"} stroke={col} strokeWidth={1.6} />
                  </g>
                );
              })}
            </g>
          );
        })}
      </svg>
      <div style={{ fontSize: 12, color: SUB }}>
        {keys.map(([k, lab, col]) => (
          <span key={k} style={{ marginRight: 14, whiteSpace: "nowrap" }}><span style={{ color: col, fontSize: 14 }}>{"\u25CF"}</span>{` ${lab}`}</span>
        ))}
        <span>{"| lines: 95% intervals resampling whole days; filled: q < 0.05; short bar beside a dot, in its colour: the 95th percentile of its own rotated ratings (the current taken out on each rotation for the vermillion one; the current alone has none)"}</span>
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
  const f = frame([8, 30.5], [0.2, 1.0], h, 52, 14, 22, 38);
  const first = bands.length ? bands[0].reading : {};
  const alone = first.current_alone && first.current_alone.auc;
  const series = [["band", OI.blue, -0.18], ["band_without_current", OI.vermillion, 0.18]];
  return (
    <div style={{ marginBottom: 8 }}>
      <div style={{ fontSize: 12.5, color: TXT }}>{`${pairName(p.pair)} (${first.n != null ? first.n : 0} ratings in the two pain groups with a device-timed reading)`}</div>
      <svg viewBox={`0 0 ${W} ${h}`} width="100%" role="img" aria-label={`Area under the curve per band, ${pairName(p.pair)}`}>
        <Axes f={f} xticks={[[10, "10"], [15, "15"], [20, "20"], [25, "25"], [30, "30"]]} yticks={[0.2, 0.4, 0.6, 0.8, 1.0]}
          xlab="band centre (Hz)" ylab="area under the curve" />
        <line x1={f.ml} x2={W - f.mr} y1={f.Y(0.5)} y2={f.Y(0.5)} stroke="#6E6E6E" strokeWidth={1.4} />
        {alone != null && <line x1={f.ml} x2={W - f.mr} y1={f.Y(alone)} y2={f.Y(alone)} stroke={OI.gray} strokeWidth={1.4} strokeDasharray="5 4" />}
        {bands.map((b) => (
          <g key={b.centre_hz} data-band={b.centre_hz}>
            {b.carries_folded_multiple && <line x1={f.X(b.centre_hz)} x2={f.X(b.centre_hz)} y1={f.Y(0.2) - 6} y2={f.Y(0.2)} stroke={TXT} strokeWidth={1.4} />}
            {series.map(([k, col, dx]) => {
              const r = b.reading[k];
              if (!r || r.auc == null) return null;
              const cx = f.X(b.centre_hz + dx);
              return (
                <g key={k}>
                  {r.lo != null && <line x1={cx} x2={cx} y1={f.Y(Math.max(0.2, r.lo))} y2={f.Y(Math.min(1.0, r.hi))} stroke={col} strokeWidth={1.4} />}
                  <circle cx={cx} cy={f.Y(Math.max(0.2, Math.min(1.0, r.auc)))} r={3.6}
                    fill={r.q != null && r.q < 0.05 ? col : "#FFFFFF"} stroke={col} strokeWidth={1.4} />
                </g>
              );
            })}
          </g>
        ))}
      </svg>
    </div>
  );
}

export function BandDetectorDeviceFigure({ result, clinicSheets }) {
  const mode = (result && result.modes && result.modes[clinicSheets ? "on" : "off"]) || {};
  const pairs = (mode.pairs || []).filter((p) => (p.bands || []).length);
  return (
    <div data-testid="figure-band_detector_device">
      {pairs.length ? pairs.map((p) => <DevicePanel key={p.pair} p={p} />)
        : <div style={{ fontSize: 12.5, color: SUB }}>{"No sensing pair could be read."}</div>}
      <div style={{ fontSize: 12, color: SUB }}>
        <span style={{ marginRight: 14, whiteSpace: "nowrap" }}><span style={{ color: OI.blue, fontSize: 14 }}>{"\u25CF"}</span>{" the band"}</span>
        <span style={{ marginRight: 14, whiteSpace: "nowrap" }}><span style={{ color: OI.vermillion, fontSize: 14 }}>{"\u25CF"}</span>{" the band, current taken out"}</span>
        <span>{"| lines: 95% intervals resampling whole days; filled: q < 0.05 over the pair's bands; dashed: the current alone; tick under a band: it carries a folded multiple of the rate in force (advisory)"}</span>
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
