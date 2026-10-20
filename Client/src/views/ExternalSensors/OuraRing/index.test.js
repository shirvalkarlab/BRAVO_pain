import React from "react";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import OuraRingDashboard from "./index";
import { SessionController } from "database/session-control";
jest.mock("react-router-dom", () => ({ useParams: () => ({ participant_uid: "synthetic" }) }));
jest.mock("context", () => ({ usePlatformContext: () => [{ user: {}, language: "en" }, jest.fn()] }));
jest.mock("layouts/DatabaseLayout", () => ({ children }) => <main>{children}</main>);
jest.mock("components/MDBox", () => ({ children }) => <div>{children}</div>);
jest.mock("components/MDTypography", () => ({ children }) => <p>{children}</p>);
jest.mock("components/MDButton", () => ({ children, onClick }) => <button onClick={onClick}>{children}</button>);
jest.mock("components/MDInput", () => () => null);
jest.mock("components/MuiAlertDialog", () => () => null);
jest.mock("components/LoadingProgress", () => () => <span>Loading</span>);
jest.mock("@mui/x-date-pickers/AdapterMoment", () => ({ AdapterMoment: function Adapter() {} }));
jest.mock("@mui/x-date-pickers/LocalizationProvider", () => ({ LocalizationProvider: ({ children }) => <div>{children}</div> }));
jest.mock("@mui/x-date-pickers/DatePicker", () => ({ DatePicker: () => <span>Date selector</span> }));
jest.mock("database/session-control", () => ({ SessionController: { query: jest.fn(), displayError: jest.fn(), getDownloadLink: jest.fn() } }));
beforeEach(() => jest.clearAllMocks());
function setup(auth, failRefresh = false) {
  SessionController.query.mockImplementation((url, request) => {
    if (request.RequestType === "RequestURL") return Promise.resolve({ data: auth });
    if (request.RequestType === "RefreshOuraRingData" && failRefresh) return Promise.reject(new Error("Expired"));
    if (request.RequestType === "RequestOverview") return Promise.resolve({ data: { Sleep: [{ observed: true }], HeartRate: [] } });
    return Promise.resolve({ data: {} });
  });
  return render(<OuraRingDashboard />);
}
test("managed load reads stored data without period writes or unsupported controls", async () => {
  setup({ ManagedByServer: true, DatePeriods: [], CanRefresh: true });
  await screen.findByText("Sleep: 1 stored records");
  expect(screen.queryByText("Add Date Periods")).toBeNull();
  expect(screen.queryByText("Delete Authentication")).toBeNull();
  expect(screen.queryByText("Date selector")).toBeNull();
  expect(SessionController.query.mock.calls.some(([, r]) => r.RequestType === "SetAuthPeriod")).toBe(false);
  expect(SessionController.displayError).not.toHaveBeenCalled();
  fireEvent.click(screen.getByText("Refresh Oura Ring Data"));
  await waitFor(() => expect(SessionController.query.mock.calls.filter(([, r]) => r.RequestType === "RequestOverview")).toHaveLength(2));
});
test("managed viewer can read and download without refresh control", async () => {
  setup({ ManagedByServer: true, DatePeriods: [], CanRefresh: false });
  await screen.findByText("Sleep: 1 stored records");
  expect(screen.queryByText("Refresh Oura Ring Data")).toBeNull();
  expect(screen.getByText("Download Oura Ring Data")).toBeTruthy();
});
test("managed failure keeps prior observations visible", async () => {
  setup({ ManagedByServer: true, DatePeriods: [], CanRefresh: true }, true);
  await screen.findByText("Sleep: 1 stored records");
  fireEvent.click(screen.getByText("Refresh Oura Ring Data"));
  await waitFor(() => expect(SessionController.displayError).toHaveBeenCalledTimes(1));
  expect(screen.getByText("Sleep: 1 stored records")).toBeTruthy();
});
test("ordinary OAuth date-period response keeps existing controls", async () => {
  setup([]);
  await screen.findByText("Sleep: 1 stored records");
  expect(screen.getByText("Add Date Periods")).toBeTruthy();
  expect(screen.getByText("Delete Authentication")).toBeTruthy();
  expect(SessionController.query.mock.calls.some(([, r]) => r.RequestType === "SetAuthPeriod")).toBe(true);
});
test("ordinary OAuth URL remains a sign-in flow", async () => {
  setup({ OAuthURL: "https://example.test/authorize" });
  await screen.findByText("Verify Token");
  expect(screen.queryByText("Stored Oura observations")).toBeNull();
});
