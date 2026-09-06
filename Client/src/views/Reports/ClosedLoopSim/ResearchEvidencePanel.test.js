import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { SessionController } from "database/session-control";
import { invalidateAll } from "database/resultCache";
import ResearchEvidencePanel from "./ResearchEvidencePanel";

const mockUser = { ID: "researcher", Role: "User" };
jest.mock("database/session-control", () => ({ SessionController: {
  getUser: () => mockUser, getSession: () => ({}), getServer: () => "local", query: jest.fn(),
} }));
const mockQuery = jest.fn();
mockQuery.cancel = jest.fn();
jest.mock("../Biomarkers/queryAnalysis", () => ({ useAnalysisQuery: () => mockQuery }));
jest.mock("@mui/material", () => ({ Card: ({ children }) => <div>{children}</div>,
  Grid: ({ children }) => <div>{children}</div>, Divider: () => <hr />, Icon: ({ children }) => <span>{children}</span> }));
jest.mock("components/MDBox", () => ({ children }) => <div>{children}</div>);
jest.mock("components/MDTypography", () => ({ children, role }) => <div role={role}>{children}</div>);
jest.mock("components/MDButton", () => ({ children, disabled, onClick }) => <button disabled={disabled} onClick={onClick}>{children}</button>);

beforeEach(() => { mockQuery.mockReset(); mockQuery.cancel.mockReset(); invalidateAll();
  SessionController.query.mockResolvedValue({ status: 200, data: { boot_token: "research-fixture", stable_across_workers: true } }); });
test("review is disabled without a selected band and never starts automatically", () => {
  render(<ResearchEvidencePanel participantUid="participant" bandCandidate={null} requestParams={{}} />);
  expect(screen.getByRole("button").disabled).toBe(true);
  expect(mockQuery).not.toHaveBeenCalled();
});
test("review keeps candidate controls and exposes unavailable data and historical retirement", async () => {
  mockQuery.mockResolvedValue({ data: { available: false, reason: "No approved spectra for the selected channel",
    readiness: { ready: false, reason: "Prospective evidence is required." },
    historical_findings: [{ source_commit: "source", reason: "Too few setting epochs." }] } });
  const props = { participantUid: "participant", bandCandidate: { contact: "ONE_THREE_LEFT", center_freq_hz: 20.5 },
    requestParams: { LabelMetric: "left_leg_vas", MatchDirection: "prior" } };
  const view = render(<ResearchEvidencePanel {...props} />);
  await waitFor(() => expect(screen.getByRole("button").disabled).toBe(false));
  fireEvent.click(screen.getByRole("button"));
  await waitFor(() => expect(mockQuery).toHaveBeenCalled());
  expect(mockQuery).toHaveBeenCalledWith("/api/queryClosedLoopResearch", { ParticipantId: "participant", Channel: "ONE_THREE_LEFT",
    CenterHz: 20.5, BandWidthHz: 5, LabelMetric: "left_leg_vas", MatchDirection: "prior" });
  await waitFor(() => expect(screen.getByRole("status").textContent).toContain("No approved spectra"));
  expect(screen.getByText(/both previously nominated configurations were retired/).textContent).toContain("not a new result");
  view.rerender(<ResearchEvidencePanel {...props} participantUid="new" />);
  expect(screen.queryByRole("status")).toBeNull();
  expect(mockQuery.cancel).toHaveBeenCalledWith("/api/queryClosedLoopResearch");
});

const selected = { participantUid: "participant", bandCandidate: { contact: "ONE_THREE_LEFT", center_freq_hz: 23.44,
  bandwidth_hz: 5 }, requestParams: { LabelMetric: "nrs" } };
const fullReport = () => ({ available: true, reason: "Research review completed", verdict: "blocked",
  readiness: { ready: false, reason: "Research only" },
  manifest: { source_commit: "latest-reviewed-commit", n_approved_daily_pros: 100, n_outcome_epochs: 20, n_table_rows: 200, outcome: "nrs",
    washin_s: 60, power_scale: "power_linear", inference: "Wild-cluster bootstrap-t below 40 clusters; cluster-robust otherwise", hypothetical_threshold_mode: "dual", selected_band: { threshold_mode: "dual" },
    programmer_mode: { programming_mode: "parkinsons", programming_mode_source: "reviewed source", programming_mode_status: "not live verification" },
    InputManifest: { fingerprint: "canonical-fingerprint", prasad_source_commit: "reviewed-commit" },
    device_fact_scope: "Only eligible post-implant metadata; current settings remain unknown",
    device_facts: { impedance_tested: true, impedance_ohms: 1100, lead_type: "directional", _provenance: { internal: true } },
    device_fact_provenance: { impedance_ohms: "Eligible impedance report" },
    spectral_sampling: "Selected sampling", settings_limitation: "Snapshot epochs", prospective_phases: "No prospective data" },
  edges: {
    E1: { estimate: -1.25, ci: [-2, -.5], p: .01, n_clusters: 6, cluster_unit: "setting_epoch", resolved: true,
      note: "Wild-cluster bootstrap-t on six setting epochs" },
    E2: { estimate: 3, ci: [1, 5], p: .02, n_clusters: 45, cluster_unit: "setting_epoch", resolved: true },
    E3: { estimate: null, ci: null, p: null, n_clusters: 40, cluster_unit: "setting_epoch", resolved: false },
  }, coherence: { coherent: null, note: "Cannot establish all three signs" }, blockers: ["Prospective evidence missing"],
  eligibility: { checked: 51, eligible: false,
    failures: [{ rule_id: "D19", title: "Feedback direction", why: "Adverse sign", observed: -1, source: "Guide", page: "19" }],
    unknowns: [{ rule_id: "D17", title: "Sensing check", why: "Not measured", observed: null, source: "Guide", page: "17" }],
    advisories: [
      { rule_id: "D09", kind: "advisory_failed", title: "Capture amplitude", why: "Below recommendation",
        observed: { low_bins: [20, 25] }, source: "Guide", page: "9" },
      { rule_id: "A1", kind: "advisory_no_predicate", title: "Context only" },
      { rule_id: "A2", kind: "predicate_error", title: "Predicate exception" },
    ],
    deferred: [{ rule_id: "D41", title: "Duplicate amplitude rule", why: "Covered by D19", source: "Guide", page: "41" }],
  } });
async function showReport(data) {
  mockQuery.mockResolvedValue({ data });
  const view = render(<ResearchEvidencePanel {...selected} />);
  await waitFor(() => expect(screen.getByRole("button").disabled).toBe(false));
  fireEvent.click(screen.getByRole("button"));
  await waitFor(() => expect(screen.getByRole("status")).toBeTruthy());
  fireEvent.click(screen.getByText("Detailed numeric evidence and source provenance"));
  return view;
}
test("renders the upstream evidence triangle, unresolved device checks, advisory shortfalls and provenance", async () => {
  await showReport(fullReport());
  expect(screen.getByText("Device rules failed or unresolved")).toBeTruthy();
  const table = screen.getByRole("table", { name: "Closed-loop evidence triangle" });
  expect(table.textContent).toContain("E1: Amplitude → power");
  expect(table.textContent).toContain("6 setting_epoch");
  expect(table.textContent).toContain("Wild-cluster bootstrap-t on six setting epochs");
  expect(table.textContent).not.toContain("unverified clusters");
  expect(table.textContent).toContain("Interval unavailable");
  expect(table.textContent).toContain("Interval excludes zero; retrospective association only");

  expect(table.textContent).toContain("0.0100");
  expect(screen.getByText(/Sign consistency:/).textContent).toContain("not established");
  expect(screen.getByText(/D09: Capture amplitude/).textContent).toContain('"low_bins":[20,25]');
  fireEvent.click(screen.getByText("Show these 1 rules (A1)"));
  fireEvent.click(screen.getByText("Show these 1 rules (A2)"));
  expect(screen.getByText(/Context only/)).toBeTruthy();
  expect(screen.getByText(/Predicate exception/)).toBeTruthy();
  expect(screen.getByText(/D17: Sensing check/).textContent).toContain("unknown");
  expect(screen.getByText(/D41: Duplicate/).textContent).toContain("Covered by D19");
  expect(screen.getByText(/Approved input fingerprint/).textContent).toContain("canonical-fingerprint");
  expect(screen.getByText(/Approved input fingerprint/).textContent).toContain("latest-reviewed-commit");
  expect(screen.getByText(/Candidate threshold mode:/).textContent).toContain("dual (hypothetical; not live programmer verification)");
  expect(screen.queryByText(/SUPPORTED AND PROGRAMMABLE/)).toBeNull();
  expect(screen.getByText(/impedance ohms:/).textContent).toContain("1100. Eligible impedance report");
  expect(screen.queryByText(/internal/)).toBeNull();
  expect(screen.getByText(/current settings remain unknown/)).toBeTruthy();
});
test.each([true, false])("keeps sign coherence %s distinct from an unestablished direction", async (coherent) => {
  const data = fullReport();
  data.coherence.coherent = coherent;
  data.verdict = coherent ? "supported" : "unsupported";
  data.eligibility = { eligible: true };
  data.edges.E1.estimate = Infinity;
  data.edges.E1.ci = [-1, 1];
  data.edges.E1.resolved = false;
  data.edges.E1.n_clusters = null;
  data.manifest.hypothetical_threshold_mode = null;
  data.manifest.selected_band = {};
  await showReport(data);
  expect(screen.getByText(/Sign consistency:/).textContent).toContain(coherent ? "Sign consistency: coherent." : "Sign consistency: not coherent.");
  expect(screen.getByText(/All evaluated blocking rules pass/)).toBeTruthy();
  expect(screen.getByRole("table").textContent).toContain("Direction unresolved");
  expect(screen.getByText(coherent ? "Retrospective evidence criteria met; research only" : "Evidence does not establish support")).toBeTruthy();
  expect(screen.getByText(/Candidate threshold mode:/).textContent).toContain("unknown");
});
test("a sparse available report cannot look like a pass", async () => {
  await showReport({ available: true, reason: "Partial report" });
  expect(screen.getByText("Research disposition not established")).toBeTruthy();
  expect(screen.getByText(/Sign consistency:/).textContent).toContain("not established");
  expect(screen.getByText(/Device rules:/).textContent).toContain("0 checked, 0 failed, 0 unknown");
  expect(screen.getByText(/Programmer mode:/).textContent).toContain("unknown");
});
test("equal recreated controls preserve an in-flight review, changed controls discard stale success", async () => {
  let complete;
  mockQuery.mockImplementation(() => new Promise((resolve) => { complete = resolve; }));
  const view = render(<ResearchEvidencePanel {...selected} />);
  await waitFor(() => expect(screen.getByRole("button").disabled).toBe(false));
  fireEvent.click(screen.getByRole("button"));
  await waitFor(() => expect(typeof complete).toBe("function"));
  view.rerender(<ResearchEvidencePanel {...selected} requestParams={{ LabelMetric: "nrs" }} />);
  expect(screen.getByRole("button").textContent).toContain("Reviewing evidence");
  expect(mockQuery.cancel).not.toHaveBeenCalled();
  view.rerender(<ResearchEvidencePanel {...selected} bandCandidate={{ ...selected.bandCandidate, bandwidth_hz: 10 }} />);
  await waitFor(() => expect(screen.getByRole("button").disabled).toBe(false));
  complete({ data: fullReport() });
  await waitFor(() => expect(screen.queryByRole("status")).toBeNull());
  await waitFor(() => expect(screen.getByRole("button").disabled).toBe(false));
  fireEvent.click(screen.getByRole("button"));
  await waitFor(() => expect(mockQuery).toHaveBeenCalledTimes(2));
  expect(mockQuery.mock.calls[1][1].BandWidthHz).toBe(10);
});
test("a failed request can be retried and stale failures do not replace a new selection", async () => {
  mockQuery.mockRejectedValueOnce(new Error("Offline"));
  const view = render(<ResearchEvidencePanel {...selected} />);
  await waitFor(() => expect(screen.getByRole("button").disabled).toBe(false));
  fireEvent.click(screen.getByRole("button"));
  await waitFor(() => expect(screen.getByRole("alert").textContent).toContain("Retry"));
  let fail;
  mockQuery.mockImplementation(() => new Promise((resolve, reject) => { fail = reject; }));
  await waitFor(() => expect(screen.getByRole("button").disabled).toBe(false));
  fireEvent.click(screen.getByRole("button"));
  expect(screen.queryByRole("alert")).toBeNull();
  await waitFor(() => expect(typeof fail).toBe("function"));
  view.rerender(<ResearchEvidencePanel {...selected} bandCandidate={{ ...selected.bandCandidate, center_freq_hz: 25 }} />);
  fail(new Error("Stale"));
  await waitFor(() => expect(screen.queryByRole("alert")).toBeNull());
});
test("review is disabled for missing participant or center", () => {
  const view = render(<ResearchEvidencePanel {...selected} participantUid={null} />);
  expect(screen.getByRole("button").disabled).toBe(true);
  view.rerender(<ResearchEvidencePanel {...selected} bandCandidate={{ contact: "ONE_THREE_LEFT" }} />);
  expect(screen.getByRole("button").disabled).toBe(true);
});
