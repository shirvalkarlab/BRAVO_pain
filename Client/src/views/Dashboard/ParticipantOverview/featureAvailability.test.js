jest.mock("database/session-control", () => ({ SessionController: { query: jest.fn() } }));
import { featureAvailability, groupAvailability, loadFeatureInformation } from "./featureAvailability";
import { SessionController } from "database/session-control";

const state = { participantUid: "pt", features: {
  FitbitDashboard: { available: false, reason: "No Fitbit data", kind: "data", setup: true },
  OuraRingDashboard: { available: true, reason: "", kind: "data" },
  FormRecords: { available: true, reason: "", kind: "data" },
  "chronic-neural-activity": { available: true, reason: "", kind: "data" },
  "3dImageViewer": { available: false, reason: "No imaging data", kind: "data" },
  PredictTherapyParameters: { available: false, reason: "Predictor models not installed", kind: "code" },
  biomarkers: { available: true, reason: "Exploratory analysis", kind: "research" },
} };

test("missing Fitbit is disabled without disabling actual Oura, survey and neural data", () => {
  expect(featureAvailability("FitbitDashboard", state, "pt")).toMatchObject({ available: false, reason: "No Fitbit data", setup: true });
  for (const key of ["OuraRingDashboard", "FormRecords", "chronic-neural-activity"]) {
    expect(featureAvailability(key, state, "pt").available).toBe(true);
  }
});
test("code missing is distinct from no data, and research is not mistaken for unavailable", () => {
  expect(featureAvailability("PredictTherapyParameters", state, "pt").kind).toBe("code");
  expect(featureAvailability("3dImageViewer", state, "pt").kind).toBe("data");
  expect(featureAvailability("biomarkers", state, "pt")).toMatchObject({ available: true, kind: "research" });
});
test("device presence and another participant's status never assert data availability", () => {
  expect(featureAvailability("OuraRingDashboard", state, "other")).toMatchObject({ available: false, kind: "pending" });
  expect(featureAvailability("OuraRingDashboard", { participantUid: "pt", DBSDevices: [{}] }, "pt"))
    .toMatchObject({ available: false, kind: "unknown" });
  expect(featureAvailability("AnalysisBuilder", null, "pt").available).toBe(true);
  expect(featureAvailability("ExistingSourceFiles", null, "pt").available).toBe(true);
});
test("groups with no viewable data disable, but sensor setup remains reachable", () => {
  expect(groupAvailability([{ key: "3dImageViewer" }], state, "pt"))
    .toEqual({ available: false, reason: "No imaging data" });
  expect(groupAvailability([{ key: "FitbitDashboard" }], state, "pt").available).toBe(true);
});
test("simultaneous sidebar/overview requests share only the in-flight response and refresh later", async () => {
  let finish;
  SessionController.query.mockImplementationOnce(() => new Promise((resolve) => { finish = resolve; }));
  const a = loadFeatureInformation("pt"), b = loadFeatureInformation("pt");
  expect(a).toBe(b); expect(SessionController.query).toHaveBeenCalledTimes(1);
  finish({ data: { FeatureAvailability: state.features } }); await a;
  SessionController.query.mockResolvedValueOnce({ data: { FeatureAvailability: {} } });
  await loadFeatureInformation("pt"); expect(SessionController.query).toHaveBeenCalledTimes(2);
});

test("backend failures and incomplete capability entries stay distinct from affirmative absence", () => {
  expect(featureAvailability("FitbitDashboard", { participantUid: "pt", features: {
    FitbitDashboard: { available: false },
  } }, "pt").reason).toBe("No eligible data");
  expect(featureAvailability("FitbitDashboard", { participantUid: "pt", features: {
    FitbitDashboard: { available: "yes" },
  }, error: "Server unavailable" }, "pt")).toMatchObject({ available: false, kind: "unknown", reason: "Server unavailable" });
});
test("mixed unavailable reasons describe a disabled group without disabling setup-only groups", () => {
  expect(groupAvailability([{ key: "3dImageViewer" }, { key: "PredictTherapyParameters" }], state, "pt"))
    .toEqual({ available: false, reason: "No available views for this participant" });
  expect(groupAvailability([{ hide: true, key: "3dImageViewer" }, { title: true }], state, "pt").available).toBe(true);
});
test("failed availability requests are not cached across retries or other participants", async () => {
  const error = new Error("disconnected");
  SessionController.query.mockRejectedValueOnce(error).mockResolvedValueOnce({ data: {} });
  await expect(loadFeatureInformation("retry-pt")).rejects.toBe(error);
  const result = await loadFeatureInformation("retry-pt");
  expect(result).toEqual({ data: {} });
  expect(SessionController.query).toHaveBeenLastCalledWith("/api/queryParticipantInformation", { ParticipantId: "retry-pt" });
});
test("published capabilities retain participant identity and treat missing maps as unknown", () => {
  const { publishFeatureInformation } = require("./featureAvailability");
  const dispatch = jest.fn();
  publishFeatureInformation(dispatch, "pt", { FeatureAvailability: state.features });
  expect(dispatch).toHaveBeenLastCalledWith({ name: "participantFeatureAvailability",
    value: { participantUid: "pt", features: state.features } });
  publishFeatureInformation(dispatch, "other", {});
  expect(dispatch).toHaveBeenLastCalledWith({ name: "participantFeatureAvailability",
    value: { participantUid: "other", features: {} } });
});
