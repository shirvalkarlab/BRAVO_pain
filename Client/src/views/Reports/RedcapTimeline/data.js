import {displayTarget, routeParticipant} from "utils/participantTargets";

export const DEFAULT_METRICS = ["mood_vas", "nrs_intensity", "vas_intensity", "left_leg_vas_intensity", "back_vas_intensity", "mpq_sens", "mpq_aff", "mpq_standard_0_45", "firey", "tingly", "electrocuting"];
const DAY = 86400000;
const pacific = new Intl.DateTimeFormat("en-CA", {timeZone: "America/Los_Angeles", year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit", hourCycle: "h23"});

export function localTime(seconds) {
  const parts = Object.fromEntries(pacific.formatToParts(new Date(seconds * 1000)).map(p => [p.type, p.value]));
  return `${parts.year}-${parts.month}-${parts.day} ${parts.hour}:${parts.minute}:${parts.second}`;
}

export function fullRange(metrics, now = Date.now()) {
  const days = metrics.flatMap(m => m.points.map(p => localTime(p.time).slice(0, 10))).sort();
  const today = localTime(now / 1000).slice(0, 10);
  return {start: days[0] || today, end: today};
}

export function filterPoints(points, start, end) {
  return points.filter(p => {
    const day = localTime(p.time).slice(0, 10);
    return day >= start && day <= end;
  });
}

const median = values => {
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
};

// Display-only centered five-survey median over every eligible observation.
// Phase boundaries and gaps do not restart or disconnect this visual smoother.
export function rollingMedian(points) {
  const sorted = [...points].sort((a, b) => a.time - b.time);
  return sorted.map((point, i) => ({...point,
    value: median(sorted.slice(Math.max(0, i - 2), i + 3).map(p => p.value)),
  }));
}

export const escapeText = text => String(text).replace(/[&<>"']/g, char => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[char]));

export function eventTimeLabel(event) {
  return event.time_precision === "day" ? `${localTime(event.time).slice(0, 10)} · time not recorded` : `${localTime(event.time)} Pacific`;
}

export function homeTiming(event, point) {
  if (event.time_precision === "day") {
    const sameDay = point && localTime(point.time).slice(0, 10) === localTime(event.time).slice(0, 10);
    return `${escapeText(eventTimeLabel(event))}. ${sameDay ? "Settings changed this day; survey may precede change." : "Exact change time is not recorded."}`;
  }
  return event.kind === "settings_observed"
    ? `Home settings observed ${escapeText(eventTimeLabel(event))}; activation time not established.`
    : escapeText(event.evidence || "Home-program timing details not recorded.");
}

const LABELS = {
  "Mode at observation": "Mode", "Stimulation status": "Stimulation", "High-pass filter": "HPF",
  "Sensing blanking": "Blanking", "Tablet target": "Target", "Stimulation contacts": "Contacts",
  "Pulse width": "PW", "Adaptive amplitude range": "Amplitude range", "Fixed / paused amplitude": "Paused amplitude",
  "Exported contact amplitudes (snapshot)": "Contact amplitudes", "Sensing source hemisphere": "Source",
  "Sensing contacts": "Contacts", "Biomarker center frequency": "Center", "Averaging duration": "Average",
  "Lower LFP threshold": "Lower threshold", "Upper LFP threshold": "Upper threshold",
  "Lower onset duration": "Lower onset", "Upper onset duration": "Upper onset",
  "Detection blanking duration": "Detection blanking", "Adaptive startup delay": "Startup delay",
};
const CONTROLLER = new Set(["Sensing source hemisphere", "Sensing contacts", "Biomarker center frequency",
  "Averaging duration", "Lower LFP threshold", "Upper LFP threshold", "Threshold mode",
  "Lower onset duration", "Upper onset duration", "Detection blanking duration", "Adaptive startup delay"]);
const PRIMARY = ["Stimulation contacts", "Frequency", "Amplitude", "Fixed / paused amplitude", "Adaptive amplitude range", "Pulse width"];
const rowText = (row, participant) => {
  const value = row.label === "Sensing source hemisphere" ? displayTarget(participant, row.value)
    : row.label === "Threshold mode" ? String(row.value).replace(/^(single|dual)[ _-]*threshold$/i, (_, mode) => `${mode[0].toUpperCase()}${mode.slice(1).toLowerCase()} threshold`)
    : row.value;
  return `${LABELS[row.label] || row.label}: ${value}`;
};
const running = rows => rows.some(row => row.label === "Adaptive state" && /^running$/i.test(String(row.value)));
const controllerRowText = (row, active, participant) => !active && /^(Lower|Upper) LFP threshold$/.test(row.label)
  ? `Stored ${LABELS[row.label].toLowerCase()} (not controlling stimulation): ${row.value}` : rowText(row, participant);
const chunks = values => {
  const lines = [];
  for (let i = 0; i < values.length; i += 3) lines.push(values.slice(i, i + 3).join(" · "));
  return lines;
};

// Reformat source-provided rows only: preserve units, unknowns, program labels
// and controller identity; never infer a setting from another field.
export function settingsSummary(settings, participant = routeParticipant()) {
  if (!settings) return "Home settings not established";
  const group = settings.group || [], left = settings.left || [], right = settings.right || [];
  const leftSource = left.find(row => row.label === "Sensing source hemisphere");
  const rightSource = right.find(row => row.label === "Sensing source hemisphere");
  const shared = leftSource && rightSource && ["Left", "Right"].includes(leftSource.value) && leftSource.value === rightSource.value
    ? left.filter(row => CONTROLLER.has(row.label) && right.some(other => other.label === row.label && other.value === row.value)) : [];
  const lines = chunks(group.map(row => rowText(row, participant)));
  for (const [title, rows] of [["L", left], ["R", right]]) {
    const target = rows.find(row => row.label === "Tablet target")?.value;
    const fallback = target ? `${title} ${String(target).replace(/^(?:Left|Right|L|R) /i, "")}` : title;
    const heading = displayTarget(participant, title, fallback);
    const contacts = rows.find(row => row.label === "Stimulation contacts");
    const primary = PRIMARY.filter(label => label !== "Stimulation contacts").flatMap(label => rows.filter(row => row.label === label));
    const values = primary.map(row => row.label === "Fixed / paused amplitude" ? `paused ${row.value}`
      : row.label === "Adaptive amplitude range" ? `range ${row.value}` : String(row.value));
    if (contacts || values.length) {
      const contactText = contacts ? String(contacts.value).replace(/Case\+/g, "C+").replace(/, /g, "") : "Contacts not recorded";
      lines.push(`${heading} ${contactText}`);
      if (values.length) lines.push(values.join(" · "));
    }
    const extra = rows.filter(row => row.label !== "Tablet target" && !PRIMARY.includes(row.label) && !shared.some(other => other.label === row.label && other.value === row.value));
    lines.push(...chunks(extra.map(row => controllerRowText(row, running(rows), participant))).map(line => `${heading}: ${line}`));
    if (!rows.length) lines.push(`${heading}: Settings not recorded`);
  }
  lines.push(...chunks(shared.map(row => controllerRowText(row, running(left) || running(right), participant))).map(line => `Shared sensing: ${line}`));
  return lines.map(escapeText).join("<br>");
}

export function unknownIntervalsInRange(intervals, range) {
  return intervals.filter(interval => localTime(interval.start).slice(0, 10) <= range.end
    && (interval.end === null || localTime(interval.end) > `${range.start} 00:00:00`));
}

export function metricTraces(metric, phases, range, smooth, visits = [], homeTransitions = [], showVisits = true, unknownIntervals = []) {
  const points = filterPoints(metric.points, range.start, range.end);
  const phaseMap = Object.fromEntries(phases.map(p => [p.key, p]));
  const homes = [...homeTransitions].sort((a, b) => a.time - b.time);
  const summaries = homes.map(home => settingsSummary(home.settings));
  const context = (point, visit) => {
    const title = visit ? "Visit day · Home program context; clinic testing may differ" : "Home program context";
    const unknown = unknownIntervals.find(interval => point.time >= interval.start && (interval.end === null || point.time < interval.end));
    if (unknown) return `${escapeText(phaseMap[point.phase]?.label || "")}<br>${title}<br>Home settings not established for this interval.<br>${escapeText(unknown.reason)}`;
    let lo = 0, hi = homes.length;
    while (lo < hi) {
      const middle = Math.floor((lo + hi) / 2);
      if (homes[middle].time <= point.time) lo = middle + 1;
      else hi = middle;
    }
    const setting = lo ? `${summaries[lo - 1]}<br>${homeTiming(homes[lo - 1], point)}` : "Home settings not established";
    return `${escapeText(phaseMap[point.phase]?.label || "")}<br>${title}<br>${setting}`;
  };
  const hover = `<b>${escapeText(metric.label)}: %{y:.1f}</b><br>%{x} Pacific<br>%{customdata}<extra></extra>`;
  const traces = [{type: "scatter", mode: "markers", name: "Observed surveys", x: points.map(p => localTime(p.time)), y: points.map(p => p.value),
    marker: {size: 7, opacity: 0.72, color: points.map(p => phaseMap[p.phase]?.color || "#777777")},
    customdata: points.map(p => context(p, false)), hovertemplate: hover}];
  if (smooth) {
    // Compute before date filtering and include visit observations even while
    // their X markers are hidden. This changes display only, never backend QC.
    const trend = filterPoints(rollingMedian([...metric.points, ...visits.map(p => ({...p, visit: true}))]), range.start, range.end);
    traces.push({type: "scatter", mode: "lines", name: "5-survey rolling median", x: trend.map(p => localTime(p.time)), y: trend.map(p => p.value),
      line: {color: "#A84747", width: 2.5}, connectgaps: true, customdata: trend.map(p => context(p, Boolean(p.visit))),
      hovertemplate: "<b>Rolling median: %{y:.1f}</b><br>%{x} Pacific<br>%{customdata}<extra></extra>"});
  }
  const testing = filterPoints(visits, range.start, range.end);
  if (showVisits && testing.length) traces.push({type: "scatter", mode: "markers", name: "Stimulation-test visit day",
    x: testing.map(p => localTime(p.time)), y: testing.map(p => p.value),
    marker: {symbol: "x", size: 11, color: "#8D4D0D", line: {width: 1}},
    customdata: testing.map(p => context(p, true)), hovertemplate: hover});
  return traces;
}

export function calendarTicks(range) {
  const start = Date.parse(`${range.start}T12:00:00Z`), end = Date.parse(`${range.end}T12:00:00Z`);
  if ((end - start) / DAY !== 27) return {};
  const values = Array.from({length: 28}, (_, i) => new Date(start + i * DAY).toISOString().slice(0, 10));
  return {tickmode: "array", tickvals: values, ticktext: values.map(day => `${Number(day.slice(5, 7))}/${Number(day.slice(8, 10))}`), tickangle: -45};
}

// Calendar days, including today; DST never changes the number of displayed days.
export function past28Range(today) {
  const start = new Date(`${today}T12:00:00Z`);
  start.setUTCDate(start.getUTCDate() - 27);
  return {start: start.toISOString().slice(0, 10), end: today};
}

export function transitionLayout(events) {
  const short = text => text.length > 28 ? `${text.slice(0, 27)}…` : text;
  return {
    shapes: events.map(event => ({type: "line", xref: "x", yref: "paper", x0: localTime(event.time), x1: localTime(event.time),
      y0: 0, y1: 1, line: {color: "#C62828", width: 1.5, dash: "dash"}, layer: "below"})),
    annotations: events.map((event, i) => {
      const parts = String(event.label).split(" · ");
      const label = event.kind === "settings_observed"
        ? `${escapeText(short(parts[0]))}${parts.length > 1 ? `<br>${escapeText(short(parts[1]))}` : ""}`
        : escapeText(short(String(event.label)));
      return {xref: "x", yref: "paper", x: localTime(event.time), y: 1.08 + (i % 3) * 0.15,
      text: `${event.number}. ${label}`, hovertext: `${settingsSummary(event.settings)}<br>${homeTiming(event)}<br>Click for complete settings`,
      name: event.id, showarrow: false, captureevents: true, font: {size: 12, color: "#B71C1C"},
      bgcolor: "rgba(255,255,255,0.9)", borderpad: 2, xanchor: "center"};
    }),
  };
}

export function stageShapes(phases, range) {
  return phases.filter(p => {
    const date = localTime(p.start).slice(0, 10);
    return date > range.start && date <= range.end;
  }).map(p => ({type: "line", xref: "x", yref: "paper", x0: localTime(p.start), x1: localTime(p.start), y0: 0, y1: 1,
    line: {color: p.color, width: 1.5, dash: "dash"}, layer: "below"}));
}
