import {displayTargetText, isRCS08Participant, routeParticipant} from "utils/participantTargets";

const REPORTS = new Set(["therapy-history", "nerual-activity-snapshot", "time-series-analysis",
  "chronic-neural-activity", "multimodal-timeline-report"]);

export function isTargetDisplayReport(pathname) {
  const parts = String(pathname).split("/").filter(Boolean);
  return parts.length === 3 && parts[0] === "reports" && REPORTS.has(parts[1])
    && isRCS08Participant(parts[2]);
}

export function rawTraceName(trace) {
  return trace.meta?.bravoRawName ?? trace.name;
}

const mapText = (participant, value) => Array.isArray(value)
  ? value.map(text => displayTargetText(participant, text)) : displayTargetText(participant, value);

// Create a presentation copy only. Keep data arrays, IDs, axes, customdata,
// legendgroup and raw names intact for selection, alignment and raw exports.
export function displayReportTrace(trace, participant) {
  if (!isRCS08Participant(participant) || trace.meta?.bravoPreserveLabel) return trace;
  // Existing scalar/array Plotly meta may be referenced by %{meta}; leave that
  // contract untouched. Built-in neural report traces use no such meta today.
  if (trace.meta != null && (typeof trace.meta !== "object" || Array.isArray(trace.meta))) return trace;
  const name = displayTargetText(participant, rawTraceName(trace));
  const hovertemplate = mapText(participant, trace.hovertemplate);
  const hovertext = mapText(participant, trace.hovertext);
  const text = mapText(participant, trace.text);
  if (name === trace.name && hovertemplate === trace.hovertemplate && hovertext === trace.hovertext && text === trace.text) return trace;
  return {...trace, name, hovertemplate, hovertext, text,
    meta: {...trace.meta, bravoRawName: rawTraceName(trace)}};
}

export function reportDisplayTraces(traces, pathname = typeof window === "undefined" ? "" : window.location.pathname) {
  if (!isTargetDisplayReport(pathname)) return traces;
  const participant = routeParticipant(pathname);
  return traces.map(trace => displayReportTrace(trace, participant));
}
