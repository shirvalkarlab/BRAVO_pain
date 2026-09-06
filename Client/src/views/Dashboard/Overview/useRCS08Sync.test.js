import React from "react";
import { createRoot } from "react-dom/client";
import { act } from "react-dom/test-utils";
import { SessionController } from "database/session-control";
import useRCS08Sync from "./useRCS08Sync";

jest.mock("database/session-control", () => ({SessionController: {query: jest.fn()}}));

let root;
let element;
let observed;
const response = (status, request_id = "job-1") => ({data: {status, request_id}});
const deferred = () => {
  let resolve;
  let reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return {promise, resolve, reject};
};
function Probe({enabled = true}) {
  observed = useRCS08Sync(enabled);
  return null;
}
async function mount(enabled = true) {
  root = createRoot(element);
  // This is React DOM's root, not Testing Library's already-wrapped render.
  // eslint-disable-next-line testing-library/no-unnecessary-act
  await act(async () => root.render(<Probe enabled={enabled}/>));
}
async function advance(milliseconds) {
  await act(async () => jest.advanceTimersByTime(milliseconds));
}
const starts = () => SessionController.query.mock.calls.filter((call) => call[1].RequestType === "Start");

test("status refresh delivers updated source dates without starting a data import", async () => {
  const first = {redcap: {available: true, value: "2026-09-03T20:00:00Z"}};
  const next = {redcap: {available: true, value: "2026-09-04T20:00:00Z"}};
  SessionController.query.mockResolvedValueOnce({data: {status: "idle", data_freshness: first}})
    .mockResolvedValue({data: {status: "idle", data_freshness: next}});
  await mount(); expect(observed.state.data_freshness).toEqual(first);
  await advance(10000); expect(observed.state.data_freshness).toEqual(next);
  expect(starts()).toHaveLength(0);
});

beforeEach(() => {
  global.IS_REACT_ACT_ENVIRONMENT = true;
  jest.useFakeTimers();
  SessionController.query.mockReset();
  element = document.createElement("div");
});
afterEach(() => {
  act(() => root.unmount());
  jest.useRealTimers();
});

test("returning to the page follows an existing job without starting another", async () => {
  SessionController.query.mockResolvedValue(response("running"));
  await mount();
  expect(observed.disabled).toBe(true);
  act(() => root.unmount());
  const calls = SessionController.query.mock.calls.length;
  await advance(30000);
  expect(SessionController.query).toHaveBeenCalledTimes(calls);
  await mount();
  expect(observed.state.status).toBe("running");
  expect(starts()).toHaveLength(0);
});

test("rapid double click submits once and a conflict attaches to the other user's job", async () => {
  const pending = deferred();
  SessionController.query.mockResolvedValueOnce(response("idle")).mockReturnValueOnce(pending.promise);
  await mount();
  act(() => { observed.start(); observed.start(); });
  expect(starts()).toHaveLength(1);
  await act(async () => pending.reject({response: {status: 409, data: {status: "running", request_id: "other-user"}}}));
  expect(observed.state.request_id).toBe("other-user");
  expect(observed.disabled).toBe(true);
  expect(observed.message).toBe("");
});

test("a lost start response checks status instead of submitting again", async () => {
  SessionController.query.mockResolvedValueOnce(response("idle"))
    .mockRejectedValueOnce(new Error("timeout"))
    .mockResolvedValue(response("running"));
  await mount();
  await act(async () => observed.start());
  expect(observed.disabled).toBe(true);
  await advance(0);
  expect(observed.state.status).toBe("running");
  expect(starts()).toHaveLength(1);
});

test("a status connection failure stays disabled and recovers without a new request", async () => {
  SessionController.query.mockResolvedValueOnce(response("running"))
    .mockRejectedValueOnce(new Error("offline"))
    .mockResolvedValue(response("completed"));
  await mount();
  await advance(3000);
  expect(observed.disabled).toBe(true);
  expect(observed.message).toContain("Reconnecting");
  await advance(3000);
  expect(observed.disabled).toBe(false);
  expect(observed.state.status).toBe("completed");
  expect(starts()).toHaveLength(0);
});

test("an old page's late response cannot replace the remounted page's status", async () => {
  const old = deferred();
  SessionController.query.mockReturnValueOnce(old.promise).mockResolvedValue(response("running", "new-job"));
  await mount();
  act(() => root.unmount());
  await mount();
  await act(async () => old.resolve(response("completed", "old-job")));
  expect(observed.state.request_id).toBe("new-job");
});

test("a sync lasting more than fifteen minutes remains active", async () => {
  SessionController.query.mockResolvedValue(response("running"));
  await mount();
  for (let poll = 0; poll < 310; poll++) await advance(3000);
  expect(observed.disabled).toBe(true);
  expect(observed.state.status).toBe("running");
  expect(observed.message).toBe("");
});


test("disabled pages do not query and can begin observing when enabled", async () => {
  await mount(false);
  act(() => { observed.start(); });
  expect(SessionController.query).not.toHaveBeenCalled();
  SessionController.query.mockResolvedValue(response("idle"));
  await act(async () => root.render(<Probe enabled={true}/>));
  expect(observed.disabled).toBe(false);
  expect(SessionController.query).toHaveBeenCalledTimes(1);
});

test("late status failure after leaving does not schedule new requests", async () => {
  const pending = deferred();
  SessionController.query.mockReturnValueOnce(pending.promise);
  await mount();
  act(() => root.unmount());
  await act(async () => pending.reject(new Error("late offline")));
  await advance(30000);
  expect(SessionController.query).toHaveBeenCalledTimes(1);
  await mount(false);
});

test("late start failure after leaving cannot change the new page state", async () => {
  const pending = deferred();
  SessionController.query.mockResolvedValueOnce(response("idle")).mockReturnValueOnce(pending.promise);
  await mount();
  act(() => { observed.start(); });
  act(() => root.unmount());
  SessionController.query.mockResolvedValue(response("running", "new-job"));
  await mount();
  await act(async () => pending.reject(new Error("late start failure")));
  expect(observed.state.request_id).toBe("new-job");
  expect(observed.message).toBe("");
  expect(starts()).toHaveLength(1);
});
