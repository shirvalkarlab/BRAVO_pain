import { SessionController } from "database/session-control";

// These views require participant data or installed analytical capability. Setup is separate.
export const DATA_VIEW_KEYS = new Set([
  "therapyHistory", "nerual-activity-snapshot", "time-series-analysis", "chronic-neural-activity",
  "multimodal-timeline-report", "events", "FormRecords", "PainScores", "FitbitDashboard",
  "GoogleHealthDashboard", "OuraRingDashboard", "EmpaticaDataExplorer", "3dImageViewer",
  "biomarkers", "stimOptimizer", "closedLoopSim", "AIHealthcare", "InClinicMedicationCycle",
  "PredictTherapyParameters", "ouraFreeReps", "redcapTimeline",
]);

export function featureAvailability(key, state, participantUid) {
  if (!DATA_VIEW_KEYS.has(key)) return { available: true, reason: "", kind: "setup" };
  if (!state || state.participantUid !== participantUid) {
    return { available: false, reason: "Checking data availability…", kind: "pending" };
  }
  const value = state.features && state.features[key];
  if (!value || typeof value.available !== "boolean") {
    return { available: false, reason: state.error || "Availability not reported", kind: "unknown" };
  }
  return { ...value, reason: value.reason || (value.available ? "" : "No eligible data") };
}

export function groupAvailability(children, state, participantUid) {
  const items = children.filter((item) => !item.hide && !item.title)
    .map((item) => featureAvailability(item.key, state, participantUid));
  if (!items.length || items.some((item) => item.available || item.setup)) return { available: true, reason: "" };
  const reasons = [...new Set(items.map((item) => item.reason))];
  return { available: false, reason: reasons.length === 1 ? reasons[0] : "No available views for this participant" };
}

// Overview and sidebar share an in-flight request, but never reuse stale completed counts.
const pending = new Map();
export function loadFeatureInformation(participantUid) {
  if (!pending.has(participantUid)) {
    const request = SessionController.query("/api/queryParticipantInformation", { ParticipantId: participantUid });
    pending.set(participantUid, request);
    const clean = () => { if (pending.get(participantUid) === request) pending.delete(participantUid); };
    request.then(clean, clean);
  }
  return pending.get(participantUid);
}

export function publishFeatureInformation(dispatch, participantUid, data) {
  // Transient UI state: do not write participant capabilities into persisted user preferences.
  dispatch({ name: "participantFeatureAvailability", value: { participantUid, features: data.FeatureAvailability || {} } });
}
