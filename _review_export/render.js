// ---- state ----
let state = { metric: DATA.label_metric || "nrs", strategy: "tertile",
  tol: 15, lowPct: 33, highPct: 67, colorMode: "multimodal" };

// pain series for the selected metric (epoch seconds + value)
function painSeriesFor(key) {
  const m = (DATA.pain_metrics || []).find((x) => x.key === key) || DATA.pain_metrics[0];
  const t = [], y = [];
  for (const p of m.points || []) {
    const ts = Date.parse(p.t.replace(" ", "T") + "Z") / 1000; // stored as naive UTC string
    if (Number.isFinite(ts) && Number.isFinite(p.v)) { t.push(ts); y.push(p.v); }
  }
  return { metric: key, label: m.label || key, t, y, range: m.range };
}

const PAIR_ORDER = ["ZERO_THREE", "ONE_THREE", "ZERO_TWO"];
const HEMI = ["LEFT", "RIGHT"];
function channelList() {
  const chs = [];
  for (const p of PAIR_ORDER) for (const h of HEMI) chs.push(`${p}_${h}`);
  return chs;
}
function recordsFor(ch, dtype) {
  return (DATA.records || []).filter((r) => String(r.channel).toUpperCase() === ch && r.dtype === dtype);
}

// Okabe-Ito sensing-frequency color ramp (multimodal mode)
const FREQ_BINS = [3.9,4.9,5.9,6.8,7.8,8.8,9.8,10.7,11.7,12.7,13.7,14.6,15.6,16.6,17.6,18.6,19.5,20.5,21.5,22.5,23.4,24.4,25.4,26.4];
function freqColor(hz) {
  if (hz == null) return "rgba(90,90,90,0.55)";
  const t = Math.max(0, Math.min(1, (hz - 3.9) / (26.4 - 3.9)));
  // viridis-ish: interpolate navy->teal->yellow
  const stops = [[68,1,84],[59,82,139],[33,145,140],[94,201,98],[253,231,37]];
  const x = t * (stops.length - 1), i = Math.floor(x), f = x - i;
  const a = stops[i], b = stops[Math.min(i + 1, stops.length - 1)];
  const c = a.map((v, k) => Math.round(v + (b[k] - v) * f));
  return `rgb(${c[0]},${c[1]},${c[2]})`;
}

function buildModel() {
  return computeMatchedScanModel(DATA.psd_scan_index, painSeriesFor(state.metric),
    state.tol, state.strategy, state.lowPct, state.highPct);
}

function D(epochSec) { return new Date(epochSec * 1000).toISOString(); }

function renderTimeline(model) {
  const binMode = state.colorMode === "binarization" && model && model.binByKey;
  const binOf = (ch, tSec) => binMode ? (model.binByKey.get(`${ch}|${Math.round(tSec)}`) || "unmatched") : null;
  const chs = channelList();
  const lh = 1.0, traces = [], shapes = [], annotations = [];
  const nLanes = chs.length;
  const laneTop = (i) => 1 - i / (nLanes + 1);
  const HEMI_COLOR = { LEFT: "#9C8BC4", RIGHT: "#C4A48B" };

  chs.forEach((ch, i) => {
    const yb = laneTop(i + 1);
    const hemi = ch.endsWith("LEFT") ? "LEFT" : "RIGHT";
    const tdc = HEMI_COLOR[hemi];
    // (a) TD coverage blocks
    recordsFor(ch, "timedomain").forEach((r) => {
      const ts = r.t_start, te = ts + Math.max(r.dur_s || 0, 86400 * 1.0);
      let fc = tdc, op = 0.85;
      if (binMode) { const b = binOf(ch, ts);
        if (b === "high" || b === "low" || b === "excluded") { fc = BIN[b]; op = 0.92; }
        else { fc = DIM; op = 0.45; } }
      shapes.push({ type: "rect", xref: "x", yref: "paper", x0: D(ts), x1: D(te),
        y0: yb + 0.04 * (1 / (nLanes + 1)), y1: yb + 0.42 * (1 / (nLanes + 1)),
        fillcolor: fc, opacity: op, line: { width: 0 }, layer: "above" });
    });
    // (b) bandpower (chronic LSB) trend line
    const bp = recordsFor(ch, "bandpower");
    if (bp.length) {
      const xs = bp.map((r) => D(r.t_start));
      const cen = bp.map((r) => (r.meta && r.meta.center_hz) || null);
      const fc = binMode ? DIMF : freqColor(cen.find((c) => c != null));
      const ys = bp.map(() => yb + 0.62 * (1 / (nLanes + 1)));
      traces.push({ type: "scattergl", mode: "markers", x: xs, y: ys,
        marker: { size: 4, color: fc }, hoverinfo: "skip", showlegend: false });
    }
    // (c) PSD ticks (montage/survey) — pooled into the scan. In bin mode, hide non-poolable ticks.
    const inScan = (r) => binMode && model.binByKey.has(`${ch}|${Math.round(r.t_start)}`);
    const psdAll = recordsFor(ch, "psd");
    const psd = binMode ? psdAll.filter(inScan) : psdAll;
    if (psd.length) {
      const tickColor = (r) => { if (!binMode) return "#9AA0A6";
        const b = binOf(ch, r.t_start); return (b === "high" || b === "low" || b === "excluded") ? BIN[b] : DIM; };
      const colors = psd.map(tickColor);
      const sizes = colors.map((c) => (binMode && c !== DIM ? 13 : 9));
      traces.push({ type: "scattergl", mode: "markers",
        x: psd.map((r) => D(r.t_start)), y: psd.map(() => yb + 0.86 * (1 / (nLanes + 1))),
        marker: { symbol: "line-ns-open", size: sizes, color: colors, line: { width: binMode ? 2.0 : 1.2 } },
        hovertemplate: ch + " PSD<br>%{x}<extra></extra>", showlegend: false });
    }
    // lane label
    annotations.push({ xref: "paper", yref: "paper", x: -0.005, y: yb + 0.45 * (1 / (nLanes + 1)),
      xanchor: "right", text: ch.replace(/_/g, " "), showarrow: false, font: { size: 10, color: "#444" } });
  });

  // pain row at the bottom
  const ps = painSeriesFor(state.metric);
  const painBase = 0.02, painTop = 1 / (nLanes + 1) * 0.9;
  const pLo = Math.min(...ps.y), pHi = Math.max(...ps.y);
  const yScale = (v) => painBase + (painTop - painBase) * ((v - pLo) / Math.max(1e-9, pHi - pLo));
  const cuts = binMode ? model.cuts : null;
  const classifyPain = (v) => { if (!cuts || cuts.kind === "none") return "#C44E00";
    if (cuts.kind === "two-cut") return v <= cuts.lowCut ? BIN.low : (v >= cuts.highCut ? BIN.high : BIN.excluded);
    return v <= cuts.cut ? BIN.low : BIN.high; };
  const py = ps.y.map(yScale);
  const PAIN_NEUTRAL = "#3A4A63"; // not #C44E00 — that collides with high-pain vermillion
  traces.push({ type: "scattergl", mode: "lines", x: ps.t.map(D), y: py,
    line: { color: binMode ? "rgba(120,120,120,0.35)" : PAIN_NEUTRAL, width: 2 }, opacity: 0.5,
    hoverinfo: "skip", showlegend: false });
  traces.push({ type: "scattergl", mode: "markers", x: ps.t.map(D), y: py,
    marker: { size: binMode ? 6 : 5, color: binMode ? ps.y.map(classifyPain) : PAIN_NEUTRAL },
    opacity: binMode ? 0.92 : 0.6, hovertemplate: ps.label + " %{customdata}<br>%{x}<extra></extra>",
    customdata: ps.y, showlegend: false });
  annotations.push({ xref: "paper", yref: "paper", x: -0.005, y: painTop * 0.55,
    xanchor: "right", text: ps.label, showarrow: false, font: { size: 10, color: "#C44E00", weight: 700 } });

  // glyph key
  if (binMode) {
    [["HIGH pain", BIN.high], ["LOW pain", BIN.low], ["excluded middle", BIN.excluded], ["not in set", DIM]]
      .forEach(([nm, c]) => traces.push({ x: [null], y: [null], mode: "markers", type: "scatter",
        marker: { symbol: "square", size: 12, color: c }, name: nm }));
  } else {
    traces.push({ x: [null], y: [null], mode: "markers", type: "scatter",
      marker: { symbol: "square", size: 12, color: "#9C8BC4" }, name: "raw TD coverage" });
    traces.push({ x: [null], y: [null], mode: "markers", type: "scatter",
      marker: { symbol: "circle", size: 7, color: "#21918c" }, name: "chronic LSB · color = sensing Hz" });
    traces.push({ x: [null], y: [null], mode: "markers", type: "scatter",
      marker: { symbol: "line-ns-open", size: 10, color: "#9AA0A6", line: { width: 1.4 } }, name: "montage PSD" });
  }

  const layout = { height: 470, uirevision: "tl-" + state.metric, paper_bgcolor: "white", plot_bgcolor: "white",
    margin: { l: 120, r: 20, t: 16, b: 30 },
    font: { family: "Arial, sans-serif", size: 11, color: "#344767" },
    xaxis: { type: "date", showgrid: true, gridcolor: "#EEF1F4", linecolor: "#B0B7BF" },
    yaxis: { visible: false, range: [0, 1] },
    shapes, annotations, showlegend: true,
    legend: { orientation: "h", y: 1.08, x: 0, font: { size: 11 } } };
  Plotly.react("timeline", traces, layout, { responsive: true, displaylogo: false });

  document.getElementById("tlfoot").textContent = binMode
    ? "Binarization view: matched PSDs colored by pain bin (vermillion=high, blue=low, grey=excluded); everything not in the binarized set dimmed. Band-power lanes are not pooled by the scan."
    : "Multimodal view: neural lanes colored by sensing center frequency; PSD ticks mark captured spectra.";
}

function renderHist(model) {
  const matchedMode = model && model.matchedValues && model.matchedValues.length > 0;
  const ps = painSeriesFor(state.metric);
  const vals = matchedMode ? model.matchedValues : ps.y;
  const cuts = matchedMode ? model.cuts : computeCuts(vals, state.strategy, state.lowPct, state.highPct);
  document.getElementById("histttl").textContent = matchedMode ? "Data available to binarize" : "Binarization preview (no matches)";
  if (!vals.length) { Plotly.purge("hist"); return; }
  const vmin = Math.min(...vals), vmax = Math.max(...vals);
  // Integer metrics (NRS, count sums): width-1 bins centered ON the integers so a bar over 8 == NRS 8.
  const integerMode = ["nrs", "mpq_sum", "npq_sum", "mpq_aff", "mpq_sen"].includes(state.metric)
    || vals.every((v) => Math.abs(v - Math.round(v)) < 1e-9);
  let edges;
  if (integerMode) {
    const lo = Math.round(vmin), hi = Math.round(vmax);
    edges = Array.from({ length: (hi - lo) + 2 }, (_, i) => lo - 0.5 + i);
  } else {
    const span = vmax - vmin, binW = span > 15 ? 2 : 0.5;
    const lo = Math.floor(vmin / binW) * binW;
    const nB = Math.max(1, Math.ceil((vmax - lo) / binW) || 1);
    edges = Array.from({ length: nB + 1 }, (_, i) => lo + i * binW);
  }
  const nB = edges.length - 1;
  const cnt = new Array(nB).fill(0);
  for (const v of vals) { let i = 0; while (i < nB - 1 && v >= edges[i + 1]) i++; cnt[i]++; }
  const ctr = cnt.map((_, i) => (edges[i] + edges[i + 1]) / 2);
  const widths = cnt.map((_, i) => (edges[i + 1] - edges[i]) * 0.92);
  let colors;
  if (cuts.kind === "two-cut") colors = ctr.map((c) => c <= cuts.lowCut ? BIN.low : (c >= cuts.highCut ? BIN.high : BIN.excluded));
  else if (cuts.kind === "one-cut") colors = ctr.map((c) => c <= cuts.cut ? BIN.low : BIN.high);
  else colors = ctr.map(() => BIN.low);
  const shapes = [];
  if (cuts.kind === "two-cut") {
    shapes.push({ type: "line", xref: "x", yref: "paper", x0: cuts.lowCut, x1: cuts.lowCut, y0: 0, y1: 1, line: { color: BIN.low, width: 2, dash: "dash" } });
    shapes.push({ type: "line", xref: "x", yref: "paper", x0: cuts.highCut, x1: cuts.highCut, y0: 0, y1: 1, line: { color: BIN.high, width: 2, dash: "dash" } });
  } else if (cuts.kind === "one-cut") {
    shapes.push({ type: "line", xref: "x", yref: "paper", x0: cuts.cut, x1: cuts.cut, y0: 0, y1: 1, line: { color: "#344767", width: 2, dash: "dash" } });
  }
  const layout = { uirevision: "hist-" + state.metric, paper_bgcolor: "white", plot_bgcolor: "white", margin: { l: 48, r: 14, t: 16, b: 40 },
    font: { family: "Arial, sans-serif", size: 11, color: "#344767" }, bargap: 0.02,
    xaxis: { title: { text: ps.label }, gridcolor: "#EEF1F4", linecolor: "#B0B7BF" },
    yaxis: { title: { text: matchedMode ? "Matched PSD samples" : "PRO reports" }, gridcolor: "#EEF1F4", linecolor: "#B0B7BF" },
    shapes, showlegend: false };
  Plotly.react("hist", [{ x: ctr, y: cnt, type: "bar", marker: { color: colors }, width: widths,
    hovertemplate: ps.label + "=%{x:.1f}<br>%{y} samples<extra></extra>" }], layout, { displaylogo: false, displayModeBar: false });
  document.getElementById("histfoot").textContent = matchedMode
    ? `Histogram of the matched PSDs' pain values at ±${state.tol} min — exactly the neural data fed to binarization. Recolors live as you drag the window.`
    : "No PSD matched a pain report at this window — widen the match window.";
}

function renderReadout(model) {
  const c = model.counts;
  document.getElementById("readout").innerHTML =
    `<b>${c.n_matched.toLocaleString()}</b> of ${c.n_sessions.toLocaleString()} neural samples matched a pain report ` +
    `(±${state.tol} min${Number.isFinite(c.median_abs_offset_min) ? `, median offset ${c.median_abs_offset_min.toFixed(1)} min` : ""}) → ` +
    `<span class="hi">${c.n_high.toLocaleString()} high</span> / <span class="lo">${c.n_low.toLocaleString()} low</span>` +
    (c.n_excluded_middle ? ` / <span class="mid">${c.n_excluded_middle.toLocaleString()} excluded</span>` : "") +
    ((c.n_matched_td != null && c.n_matched > 0) ? ` <span class="mid">(${c.n_matched_td} TD-streaming · ${c.n_matched_montage} montage PSD)</span>` : "");
  const cuts = model.cuts;
  let cutTxt = cuts.kind === "two-cut" ? `low ≤ ${cuts.lowCut?.toFixed(1)}, high ≥ ${cuts.highCut?.toFixed(1)}`
    : (cuts.kind === "one-cut" ? `cut at ${cuts.cut?.toFixed(1)}` : "—");
  document.getElementById("summary").innerHTML =
    `<div><b>Metric:</b> ${painSeriesFor(state.metric).label}</div>` +
    `<div><b>Strategy:</b> ${state.strategy}</div>` +
    `<div><b>Cut(s):</b> ${cutTxt}</div>` +
    `<div><b>Pooled neural samples:</b> ${c.n_sessions.toLocaleString()} (TD streaming + montage/survey, 6 bipolar channels)</div>` +
    `<div><b>Matched:</b> ${c.n_matched.toLocaleString()} &nbsp; <span class="hi">high ${c.n_high}</span> · <span class="lo">low ${c.n_low}</span>` +
    (c.n_excluded_middle ? ` · <span class="mid">excl ${c.n_excluded_middle}</span>` : "") + `</div>` +
    `<div style="margin-top:8px;color:#777;font-size:12px;">Drag the match window or change the strategy — every panel recomputes live, no server round-trip.</div>`;
}

function renderAll() {
  const model = buildModel();
  renderTimeline(model); renderHist(model); renderReadout(model);
}

// ---- wire controls ----
const sel = document.getElementById("metric");
(DATA.pain_metrics || []).forEach((m) => { const o = document.createElement("option");
  o.value = m.key; o.textContent = m.label || m.key; if (m.key === state.metric) o.selected = true; sel.appendChild(o); });
sel.onchange = (e) => { state.metric = e.target.value; renderAll(); };
document.getElementById("strategy").onchange = (e) => {
  state.strategy = e.target.value;
  document.getElementById("pctwrap").style.display = state.strategy === "percentile" ? "block" : "none";
  renderAll(); };
document.getElementById("lowpct").oninput = (e) => { state.lowPct = +e.target.value; renderAll(); };
document.getElementById("highpct").oninput = (e) => { state.highPct = +e.target.value; renderAll(); };
const tol = document.getElementById("tol"), tolnum = document.getElementById("tolnum");
tol.oninput = (e) => { state.tol = +e.target.value; tolnum.value = e.target.value; renderAll(); };
tolnum.oninput = (e) => { const v = +e.target.value; if (v > 0) { state.tol = v; tol.value = v; renderAll(); } };
document.querySelectorAll("#colormode button").forEach((b) => b.onclick = () => {
  state.colorMode = b.dataset.mode;
  document.querySelectorAll("#colormode button").forEach((x) => x.classList.remove("active"));
  b.classList.add("active"); renderAll(); });
renderAll();