import React from "react";
import { render, screen, fireEvent, waitFor, act } from "@testing-library/react";
import ManualSyncButton from "./ManualSyncButton";
import { SYNC_COMPLETED_EVENT } from "utils/syncEvents";
import { SessionController } from "database/session-control";
jest.mock("database/session-control", () => ({ SessionController: { query: jest.fn() } }));
let mockScope="account-a";
jest.mock("views/Reports/RedcapTimeline/requestScope",()=>({cacheScope:()=>mockScope}));
function snapshot(state = null, mode = "retained_files") {
  return { CanSync: true, Available: true, Sources: { Mode: mode, UpstreamAvailable: mode === "upstream_files" }, Job: state ? { job_id:"a".repeat(32),updated_at:1750000010,state, last_success_at: null, streams: Object.fromEntries(["neural", "clinic", "redcap", "oura"].map(name => [name, { state: state === "succeeded" ? "succeeded" : "queued" }])) } : null };
}
beforeEach(() => {jest.clearAllMocks();mockScope="account-a";});
afterEach(() => jest.useRealTimers());
test("viewer and missing participant have no action", async () => {
  SessionController.query.mockRejectedValue({ response: { status: 403 } });
  const view = render(<ManualSyncButton participantUid={null} />);
  expect(SessionController.query).not.toHaveBeenCalled();
  view.rerender(<ManualSyncButton participantUid="a" />);
  await waitFor(() => expect(SessionController.query).toHaveBeenCalledTimes(1));
  expect(screen.queryByRole("button", { name: "Sync all streams" })).toBeNull();
});
test("start submits once and identifies retained files", async () => {
  let finish;
  SessionController.query.mockImplementation((url, body) => body.RequestType === "Status" ? Promise.resolve({ data: snapshot() }) : new Promise(resolve => { finish = resolve; }));
  render(<ManualSyncButton participantUid="a" />);
  fireEvent.click(await screen.findByRole("button", { name: "Sync all streams" }));
  fireEvent.click(screen.getByText("Sync in progress"));
  expect(SessionController.query.mock.calls.filter(([, b]) => b.RequestType === "Start")).toHaveLength(1);
  expect(screen.getByText(/files already available on the lab server/)).toBeTruthy();
  expect(screen.getByText(/Fetch latest upstream files: not connected/)).toBeTruthy();
  await act(async () => finish({ data: snapshot("running") }));
  fireEvent.click(screen.getByText("Sync in progress"));
  expect(SessionController.query.mock.calls.filter(([, b]) => b.RequestType === "Start")).toHaveLength(1);
});
test("polling restores active job and reports completion separately from view refresh", async () => {
  jest.useFakeTimers();
  SessionController.query.mockResolvedValueOnce({ data: snapshot("running") }).mockResolvedValue({ data: snapshot("succeeded") });
  render(<ManualSyncButton participantUid="a" />);
  await act(async () => {});
  fireEvent.click(screen.getByText("Sync in progress"));
  await act(async () => jest.advanceTimersByTime(5000));
  expect(screen.getByText(/All four streams are updated/)).toBeTruthy();
  expect(screen.getByRole("button", { name: "Refresh view" })).toBeTruthy();
  expect(SessionController.query.mock.calls.every(([,b]) => b.RequestType === "Status")).toBe(true);
  const count = SessionController.query.mock.calls.length;
  await act(async () => jest.advanceTimersByTime(10000));
  expect(SessionController.query).toHaveBeenCalledTimes(count);
});
test("partial failure does not claim completion", async () => {
  const failed = snapshot("failed"); failed.Job.streams.neural.state = "succeeded"; failed.Job.streams.oura.state = "failed";
  SessionController.query.mockResolvedValueOnce({ data: snapshot() }).mockResolvedValueOnce({ data: failed });
  render(<ManualSyncButton participantUid="a" />);
  fireEvent.click(await screen.findByRole("button", { name: "Sync all streams" }));
  expect(await screen.findByText(/Some streams could not be updated/)).toBeTruthy();
  expect(screen.queryByText(/All four streams are updated/)).toBeNull();
  const progress = screen.getByRole("list", { name: "Data stream progress" }).textContent;
  expect(progress).toContain("Neural files: Complete"); expect(progress).toContain("Oura observations: Failed");
});
test("uncertain submission checks status without resubmitting", async () => {
  SessionController.query.mockImplementation((url, body) => body.RequestType === "Status" ? Promise.resolve({ data: snapshot() }) : Promise.reject(new Error("offline")));
  render(<ManualSyncButton participantUid="a" />);
  fireEvent.click(await screen.findByRole("button", { name: "Sync all streams" }));
  expect(await screen.findByText(/Could not confirm the request/)).toBeTruthy();
  await waitFor(() => expect(SessionController.query.mock.calls.filter(([,b]) => b.RequestType === "Status")).toHaveLength(2));
  expect(SessionController.query.mock.calls.filter(([,b]) => b.RequestType === "Start")).toHaveLength(1);
});
test("upstream capability and exported files are distinguished from import completion", async () => {
  const value = snapshot("queued", "upstream_files"); value.Job.streams.neural.state = "exported";
  SessionController.query.mockResolvedValue({ data: value });
  render(<ManualSyncButton participantUid="a" />);
  fireEvent.click(await screen.findByRole("button", { name: "Sync in progress" }));
  expect(screen.getByText(/fetched from their connected source before import/)).toBeTruthy();
  expect(screen.getByText(/Fetch latest upstream files: available/)).toBeTruthy();
  expect(screen.getByRole("list", { name: "Data stream progress" }).textContent).toContain("Files copied; import pending");
});
test("unavailable service disables the action", async () => {
  SessionController.query.mockRejectedValue({ response: { status: 503 } });
  render(<ManualSyncButton participantUid="a" />);
  expect((await screen.findByRole("button", { name: "Sync all streams" })).disabled).toBe(true);
  expect(screen.getByText("Sync unavailable")).toBeTruthy();
});
test("late responses for another participant are ignored", async () => {
  let old;
  SessionController.query.mockImplementation((url, body) => body.ParticipantId === "a" ? new Promise(resolve => { old = resolve; }) : Promise.reject({ response: { status: 403 } }));
  const view = render(<ManualSyncButton participantUid="a" />); view.rerender(<ManualSyncButton participantUid="b" />);
  await act(async () => old({ data: snapshot("running") }));
  expect(screen.queryByRole("button", { name: "Sync in progress" })).toBeNull();
});

test("polls do not overlap and transient failures retain progress", async () => {
  jest.useFakeTimers(); let finish;
  SessionController.query.mockResolvedValueOnce({ data: snapshot("running") })
    .mockImplementationOnce(() => new Promise(resolve => { finish = resolve; }))
    .mockRejectedValueOnce({ response: { status: 503 } })
    .mockRejectedValueOnce(new Error("offline"))
    .mockResolvedValue({ data: snapshot("succeeded") });
  render(<ManualSyncButton participantUid="a" />); await act(async () => {});
  fireEvent.click(screen.getByText("Sync in progress"));
  await act(async () => jest.advanceTimersByTime(10000));
  expect(SessionController.query).toHaveBeenCalledTimes(2);
  await act(async () => finish({ data: snapshot("running") }));
  await act(async () => jest.advanceTimersByTime(5000));
  expect(screen.getByText(/Synchronization is currently unavailable/)).toBeTruthy();
  expect(screen.getByRole("list", { name: "Data stream progress" })).toBeTruthy();
  await act(async () => jest.advanceTimersByTime(5000));
  expect(screen.getByText(/Could not check synchronization status/)).toBeTruthy();
  await act(async () => jest.advanceTimersByTime(5000));
  expect(screen.getByText(/All four streams are updated/)).toBeTruthy();
});
test.each(["resolve", "reject"])("late %s of Start does not alter another participant", async outcome => {
  let finish;
  SessionController.query.mockImplementation((url, body) => {
    if (body.ParticipantId === "b") return Promise.reject({ response: { status: 403 } });
    if (body.RequestType === "Status") return Promise.resolve({ data: snapshot() });
    return new Promise((resolve, reject) => { finish = outcome === "resolve" ? resolve : reject; });
  });
  const view = render(<ManualSyncButton participantUid="a" />);
  fireEvent.click(await screen.findByRole("button", { name: "Sync all streams" }));
  view.rerender(<ManualSyncButton participantUid="b" />);
  await act(async () => finish(outcome === "resolve" ? { data: snapshot("running") } : new Error("late")));
  expect(screen.queryByText("Sync in progress")).toBeNull();
  expect(screen.queryByText(/Could not confirm/)).toBeNull();
});
test("late failed status is ignored and cannot release the new participant's poll", async () => {
  jest.useFakeTimers(); let old;
  SessionController.query.mockImplementationOnce(() => new Promise((resolve, reject) => { old = reject; }))
    .mockResolvedValueOnce({ data: snapshot("running") });
  const view = render(<ManualSyncButton participantUid="a" />);
  view.rerender(<ManualSyncButton participantUid="b" />); await act(async () => {});
  await act(async () => old(new Error("late")));
  expect(screen.queryByText(/Could not check/)).toBeNull();
  expect(screen.getByText("Sync in progress")).toBeTruthy();
});
test("failed device review, last success, close and view refresh are explicit", async () => {
  const result = snapshot("failed");
  result.Job.streams.neural = { state: "failed", error_code: "unknown_device" };
  result.Job.streams.clinic = { state: "unexpected", error_code: "unrecognized" };
  result.Job.streams.redcap.error_code = "changed_source";
  result.Job.last_success_at = 1750000000;
  SessionController.query.mockResolvedValueOnce({ data: snapshot() }).mockResolvedValue({ data: result });
  const location = window.location; delete window.location; window.location = { reload: jest.fn() };
  try {
    render(<ManualSyncButton participantUid="a" />);
    fireEvent.click(await screen.findByRole("button", { name: "Sync all streams" }));
    expect(await screen.findByText(/Unrecognized device; review required/)).toBeTruthy();
    expect(screen.getByText(/Status unavailable.*Please contact/)).toBeTruthy();
    expect(screen.getByText(/Source report changed; review required/)).toBeTruthy();
    expect(screen.getByText(/Last successful manual sync:/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Refresh view" }));
    expect(window.location.reload).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole("button", { name: "Close" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    fireEvent.click(screen.getByRole("button", { name: "Sync all streams" }));
    await screen.findByRole("dialog");
    fireEvent.keyDown(screen.getByRole("dialog"), { key: "Escape", code: "Escape" });
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  } finally { window.location = location; }
});

test.each(['succeeded','failed'])('historical %s status never emits completion on mount or remount',async(state)=>{
 const events=[];const listener=event=>events.push(event.detail);window.addEventListener(SYNC_COMPLETED_EVENT,listener);
 const terminal=snapshot(state);if(state==='failed')terminal.Job.streams.oura.state='failed';
 SessionController.query.mockResolvedValue({data:terminal});
 const view=render(<ManualSyncButton participantUid="a"/>);await act(async()=>{});
 expect(events).toEqual([]);
 view.rerender(<ManualSyncButton participantUid="a"/>);await act(async()=>{});expect(events).toHaveLength(0);
 // An uncertain/duplicate Start returning the same old job is not a new completion.
 fireEvent.click(screen.getByRole('button',{name:'Sync all streams'}));await act(async()=>{});expect(events).toHaveLength(0);
 view.unmount();render(<ManualSyncButton participantUid="a"/>);await act(async()=>{});expect(events).toHaveLength(0);
 window.removeEventListener(SYNC_COMPLETED_EVENT,listener);
});

test.each(['succeeded','failed'])('observed running job emits one scoped %s completion',async(state)=>{
 jest.useFakeTimers();const events=[];const listener=event=>events.push(event.detail);window.addEventListener(SYNC_COMPLETED_EVENT,listener);
 SessionController.query.mockResolvedValueOnce({data:snapshot('running')}).mockResolvedValue({data:snapshot(state)});
 const view=render(<ManualSyncButton participantUid="a"/>);await act(async()=>{});expect(events).toHaveLength(0);
 await act(async()=>jest.advanceTimersByTime(5000));
 expect(events).toEqual([{participantUid:'a',scope:'account-a',state}]);
 view.rerender(<ManualSyncButton participantUid="a"/>);await act(async()=>jest.advanceTimersByTime(10000));expect(events).toHaveLength(1);
 window.removeEventListener(SYNC_COMPLETED_EVENT,listener);
});

test.each(['succeeded','failed'])('a newly started job already %s in its response emits completion once',async(state)=>{
 const events=[];const listener=event=>events.push(event.detail);window.addEventListener(SYNC_COMPLETED_EVENT,listener);
 const terminal=snapshot(state);terminal.Job.job_id='b'.repeat(32);
 SessionController.query.mockResolvedValueOnce({data:snapshot('succeeded')}).mockResolvedValue({data:terminal});
 render(<ManualSyncButton participantUid="a"/>);await act(async()=>{});expect(events).toHaveLength(0);
 fireEvent.click(screen.getByRole('button',{name:'Sync all streams'}));await act(async()=>{});
 expect(events).toEqual([{participantUid:'a',scope:'account-a',state}]);
 fireEvent.click(screen.getByRole('button',{name:'Close'}));await waitFor(()=>expect(screen.queryByRole('dialog')).toBeNull());
 fireEvent.click(screen.getByRole('button',{name:'Sync all streams'}));await act(async()=>{});expect(events).toHaveLength(1);
 window.removeEventListener(SYNC_COMPLETED_EVENT,listener);
});

test('uncertain Start can recover a new terminal job through Status without replaying the write',async()=>{
 const events=[];const listener=event=>events.push(event.detail);window.addEventListener(SYNC_COMPLETED_EVENT,listener);
 SessionController.query.mockResolvedValueOnce({data:snapshot()}).mockRejectedValueOnce(new Error('offline'))
   .mockResolvedValueOnce({data:snapshot('succeeded')});
 render(<ManualSyncButton participantUid="a"/>);await act(async()=>{});
 fireEvent.click(screen.getByRole('button',{name:'Sync all streams'}));await act(async()=>{});
 expect(events).toEqual([{participantUid:'a',scope:'account-a',state:'succeeded'}]);
 expect(SessionController.query.mock.calls.map(([,body])=>body.RequestType)).toEqual(['Status','Start','Status']);
 window.removeEventListener(SYNC_COMPLETED_EVENT,listener);
});

test('changing account cannot publish old job completion into the new account or reuse old status',async()=>{
 let finish;const events=[];const listener=event=>events.push(event.detail);window.addEventListener(SYNC_COMPLETED_EVENT,listener);
 SessionController.query.mockImplementationOnce(()=>new Promise(resolve=>{finish=resolve;})).mockResolvedValue({data:snapshot()});
 const view=render(<ManualSyncButton participantUid="a"/>);mockScope='account-b';view.rerender(<ManualSyncButton participantUid="a"/>);
 await act(async()=>finish({data:snapshot('succeeded')}));expect(events).toHaveLength(0);
 expect(SessionController.query).toHaveBeenCalledTimes(2);
 mockScope=null;view.rerender(<ManualSyncButton participantUid="a"/>);await act(async()=>{});
 expect(screen.queryByRole('button',{name:'Sync all streams'})).toBeNull();expect(SessionController.query).toHaveBeenCalledTimes(2);
 window.removeEventListener(SYNC_COMPLETED_EVENT,listener);
});

test('accepted old terminal snapshot is not re-emitted when account scope changes before replacement status',async()=>{
 const events=[];const listener=event=>events.push(event.detail);window.addEventListener(SYNC_COMPLETED_EVENT,listener);
 let finish;SessionController.query.mockResolvedValueOnce({data:snapshot('succeeded')}).mockImplementationOnce(()=>new Promise(resolve=>{finish=resolve;}));
 const view=render(<ManualSyncButton participantUid="a"/>);await act(async()=>{});expect(events).toHaveLength(0);
 mockScope='account-b';view.rerender(<ManualSyncButton participantUid="a"/>);await act(async()=>{});expect(events).toHaveLength(0);
 await act(async()=>finish({data:snapshot()}));expect(events).toHaveLength(0);
 window.removeEventListener(SYNC_COMPLETED_EVENT,listener);
});
