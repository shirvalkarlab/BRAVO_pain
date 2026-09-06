import React from "react";
import { act, render, waitFor } from "@testing-library/react";
import { SessionController } from "database/session-control";
import { cacheScope, cacheStats, getResult, invalidate, invalidateAll, putResult, setServerToken, settingsKey } from "./resultCache";
import { refreshServerIdentity, useCachedResult } from "./useCachedResult";
jest.mock("database/session-control", () => ({ SessionController: {
  query: jest.fn(), getUser: jest.fn(), getSession: jest.fn(), getServer: jest.fn(() => "local")
} }));
let api;
const user = { ID: "viewer", Role: "User", ReadOnly: true };
const identity = { data: { boot_token: "token", stable_across_workers: true }, status: 200 };
const deferred = () => { let resolve; let reject; const promise = new Promise((a, b) => { resolve = a; reject = b; }); return { promise, resolve, reject }; };
function Probe({ uid = "p", settings = { a: 1 }, ...rest }) {
  api = useCachedResult({ moduleKey: "m", uid, settings, ...rest }); return null;
}
const settle = () => act(async () => { await Promise.resolve(); await Promise.resolve(); });
beforeEach(() => {
  SessionController.getUser.mockReturnValue(user);
  SessionController.getSession.mockReturnValue({ ActiveStudy: "study" });
  SessionController.query.mockReset(); SessionController.query.mockResolvedValue(identity);
  cacheScope(); invalidateAll(); setServerToken("token", "p");
});
test("cache reuse waits for access/source validation and does not rerun analysis", async () => {
  putResult("m", "p", settingsKey({ a: 1 }), { answer: 1 });
  const gate = deferred(); SessionController.query.mockReturnValue(gate.promise);
  const fetcher = jest.fn(); render(<Probe fetcher={fetcher} />);
  expect(api.data).toBeNull(); await settle();
  expect(SessionController.query).toHaveBeenCalledWith("/api/queryServerIdentity", { ParticipantId: "p" });
  await act(async () => gate.resolve(identity));
  expect(api.data).toEqual({ answer: 1 }); expect(fetcher).not.toHaveBeenCalled();
});
test("one first load, visible stale settings, exactly one recompute despite store events", async () => {
  const fetcher = jest.fn().mockResolvedValue({ answer: 1 });
  const view = render(<Probe fetcher={fetcher} />);
  await waitFor(() => expect(api.data).toEqual({ answer: 1 }));
  view.rerender(<Probe settings={{ a: 2 }} fetcher={fetcher} />);
  expect(api.stale).toBe(true); expect(fetcher).toHaveBeenCalledTimes(1);
  await act(async () => { await Promise.all([api.recompute(), api.recompute()]); });
  expect(fetcher).toHaveBeenCalledTimes(2); expect(api.stale).toBe(false);
});
test("explicit-only panels validate but never launch analysis on mount or control change", async () => {
  const fetcher = jest.fn().mockResolvedValue({ answer: 1 });
  const view = render(<Probe fetcher={fetcher} autoFetch={false} />); await settle();
  view.rerender(<Probe settings={{ a: 2 }} fetcher={fetcher} autoFetch={false} />); await settle();
  expect(fetcher).not.toHaveBeenCalled();
  await act(async () => { await api.recompute(); }); expect(fetcher).toHaveBeenCalledTimes(1);
});
test("source/QC identity changes discard old result before recomputation", async () => {
  putResult("m", "p", settingsKey({ a: 1 }), { old: true });
  SessionController.query.mockResolvedValue({ data: { boot_token: "new", stable_across_workers: true } });
  const work = deferred(); const fetcher = jest.fn().mockReturnValue(work.promise);
  render(<Probe fetcher={fetcher} />); await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(1));
  expect(api.data).toBeNull(); await act(async () => work.resolve({ new: true }));
  expect(api.data).toEqual({ new: true });
});
test.each([401, 403, 500])("identity validation failure %s clears PHI and does not launch analysis", async (status) => {
  putResult("m", "p", settingsKey({ a: 1 }), { private: true });
  const err = Object.assign(new Error("Cannot validate"), { response: { status } });
  SessionController.query.mockRejectedValue(err);
  const fetcher = jest.fn(); render(<Probe fetcher={fetcher} />);
  await waitFor(() => expect(api.errRaw).toBe(err));
  expect(api.data).toBeNull(); expect(cacheStats().count).toBe(0); expect(fetcher).not.toHaveBeenCalled();
});
test("participant switching never displays or stores late previous participant response", async () => {
  const old = deferred(); const next = deferred(); const fetcher = jest.fn().mockReturnValueOnce(old.promise).mockReturnValueOnce(next.promise);
  const view = render(<Probe fetcher={fetcher} />); await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(1));
  view.rerender(<Probe uid="q" fetcher={fetcher} />);
  expect(api.data).toBeNull(); await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(2));
  await act(async () => old.resolve({ private: "p" })); expect(api.data).toBeNull();
  await act(async () => next.resolve({ private: "q" })); expect(api.data).toEqual({ private: "q" });
  expect(getResult("m", "p", settingsKey({ a: 1 }))).toBeNull();
});
test("account changes during an outstanding response cannot repopulate a cleared cache", async () => {
  const work = deferred(); const fetcher = jest.fn().mockReturnValue(work.promise);
  const view = render(<Probe fetcher={fetcher} />); await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(1));
  SessionController.getUser.mockReturnValue({}); view.rerender(<Probe fetcher={fetcher} />);
  await act(async () => work.resolve({ private: true })); expect(api.data).toBeNull(); expect(cacheStats().count).toBe(0);
});
test("a response arriving after unmount is discarded", async () => {
  const work = deferred(); const fetcher = jest.fn().mockReturnValue(work.promise);
  const view = render(<Probe fetcher={fetcher} />); await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(1));
  view.unmount(); await act(async () => work.resolve({ private: true })); expect(cacheStats().count).toBe(0);
});
test("202 and pending bundles are errors rather than completed results", async () => {
  const fetcher = jest.fn().mockResolvedValue({ status: 202, data: { status: "pending" } });
  render(<Probe fetcher={fetcher} />); await waitFor(() => expect(api.err).toMatch(/pending/));
  expect(api.data).toBeNull(); expect(cacheStats().count).toBe(0);
});
test("unstable worker identity disables retention without preventing an explicit analysis", async () => {
  SessionController.query.mockResolvedValue({ data: { boot_token: "worker", stable_across_workers: false } });
  const fetcher = jest.fn().mockResolvedValue({ value: 2 }); render(<Probe fetcher={fetcher} />);
  await waitFor(() => expect(api.data).toEqual({ value: 2 }));
  expect(api.notKept).toMatch(/workers/); expect(cacheStats().count).toBe(0);
});
test("cache invalidation starts one refresh for an already mounted automatic panel", async () => {
  const fetcher = jest.fn().mockResolvedValue({ value: 2 }); render(<Probe fetcher={fetcher} />);
  await waitFor(() => expect(api.data).toEqual({ value: 2 }));
  await act(async () => invalidate("m", "p"));
  await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(2));
});
test("disabled panels neither validate nor fetch and clear their visible data", async () => {
  const fetcher = jest.fn().mockResolvedValue({ value: 2 }); const view = render(<Probe fetcher={fetcher} enabled={false} />);
  await settle(); expect(SessionController.query).not.toHaveBeenCalled(); expect(fetcher).not.toHaveBeenCalled();
  view.rerender(<Probe fetcher={fetcher} />); await waitFor(() => expect(api.data).toEqual({ value: 2 }));
  view.rerender(<Probe fetcher={fetcher} enabled={false} />); expect(api.data).toBeNull();
});
test("identity validation rejects missing participants and missing tokens", async () => {
  await expect(refreshServerIdentity(null)).rejects.toThrow(/participant/);
  SessionController.query.mockResolvedValue({ data: {} });
  await expect(refreshServerIdentity("p")).rejects.toThrow(/validate/);
});
test("identity validation is shared while pending and rejects a changed account", async () => {
  const gate = deferred(); SessionController.query.mockReturnValue(gate.promise);
  const one = refreshServerIdentity("p"); const two = refreshServerIdentity("p");
  expect(one).toBe(two); await settle(); expect(SessionController.query).toHaveBeenCalledTimes(1);
  SessionController.getUser.mockReturnValue({ ID: "other" });
  gate.resolve(identity); await expect(one).rejects.toThrow(/account/);
});
test("invalidation during an outstanding analysis discards it and fetches the new revision", async () => {
  const old = deferred(); const fetcher = jest.fn().mockReturnValueOnce(old.promise).mockResolvedValue({ fresh: true });
  render(<Probe fetcher={fetcher} />); await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(1));
  await act(async () => invalidate("m", "p"));
  await act(async () => old.resolve({ old: true }));
  await waitFor(() => expect(api.data).toEqual({ fresh: true })); expect(fetcher).toHaveBeenCalledTimes(2);
});
test("missing fetcher does not invent a completed result", async () => {
  render(<Probe />); await settle(); expect(api.loading).toBe(false); expect(api.data).toBeNull();
});
test("explicit retry preserves non-auth error status and can recover", async () => {
  const error = Object.assign(new Error("Server failed"), { response: { status: 500 } });
  const fetcher = jest.fn().mockRejectedValueOnce(error).mockResolvedValue({ recovered: true });
  render(<Probe fetcher={fetcher} />); await waitFor(() => expect(api.errRaw).toBe(error));
  await act(async () => { await api.recompute(); }); expect(api.data).toEqual({ recovered: true }); expect(api.errRaw).toBeNull();
});
test("an analysis access rejection clears all prior participant results", async () => {
  const error = { response: { status: 403 } };
  const fetcher = jest.fn().mockRejectedValue(error); render(<Probe fetcher={fetcher} />);
  await waitFor(() => expect(api.errRaw).toBe(error)); expect(api.data).toBeNull();
});
test("memory-pressure fallback remains visible only for the validated scope and marks changed settings", async () => {
  Object.defineProperty(performance, "memory", { configurable: true, value: { usedJSHeapSize: 90, jsHeapSizeLimit: 100 } });
  const fetcher = jest.fn().mockResolvedValue({ value: 1 }); const view = render(<Probe fetcher={fetcher} />);
  await waitFor(() => expect(api.data).toEqual({ value: 1 })); expect(api.notKept).toMatch(/memory/);
  view.rerender(<Probe settings={{ a: 2 }} fetcher={fetcher} />); expect(api.stale).toBe(true);
  view.unmount(); Object.defineProperty(performance, "memory", { configurable: true, value: undefined });
});
test("identity-only saved result returns on remount without new analysis", async () => {
  putResult("m", "p", settingsKey({ a: 1 }), { saved: true });
  const fetcher = jest.fn(); render(<Probe fetcher={fetcher} autoFetch={false} />);
  await waitFor(() => expect(api.data).toEqual({ saved: true })); expect(fetcher).not.toHaveBeenCalled();
});
test("disabled recompute is a no-op and malformed identity cannot be used", async () => {
  render(<Probe enabled={false} />); await act(async () => { await api.recompute(); });
  expect(SessionController.query).not.toHaveBeenCalled();
  SessionController.query.mockResolvedValue(null); await expect(refreshServerIdentity("p")).rejects.toThrow(/validate/);
  SessionController.query.mockResolvedValue({ status: 202, data: { boot_token: "pending" } });
  await expect(refreshServerIdentity("p")).rejects.toThrow(/validate/);
});
test("first explicit Compute promotes the enabled hook's pending identity check exactly once", async () => {
  const gate = deferred(); SessionController.query.mockReturnValue(gate.promise);
  const oldFetcher = jest.fn().mockResolvedValue({ old: true });
  const currentFetcher = jest.fn().mockResolvedValue({ current: true });
  const view = render(<Probe enabled={false} autoFetch={false} fetcher={oldFetcher} />);
  view.rerender(<Probe enabled autoFetch={false} settings={{ a: 2 }} fetcher={currentFetcher} />);
  let first; let repeated;
  await act(async () => { first = api.recompute(); repeated = api.recompute(); });
  expect(first).toBe(repeated); expect(currentFetcher).not.toHaveBeenCalled();
  await act(async () => { gate.resolve(identity); await first; });
  expect(oldFetcher).not.toHaveBeenCalled(); expect(currentFetcher).toHaveBeenCalledTimes(1);
  expect(api.data).toEqual({ current: true });
  expect(getResult("m", "p", settingsKey({ a: 2 })).stale).toBe(false);
  expect(SessionController.query).toHaveBeenCalledTimes(1);
});
test("promoting validation snapshots the latest controls instead of the mount-time fetcher", async () => {
  const gate = deferred(); SessionController.query.mockReturnValue(gate.promise);
  const oldFetcher = jest.fn().mockResolvedValue({ old: true });
  const currentFetcher = jest.fn().mockResolvedValue({ current: true });
  const view = render(<Probe autoFetch={false} fetcher={oldFetcher} />);
  await settle();
  view.rerender(<Probe autoFetch={false} settings={{ a: 9 }} fetcher={currentFetcher} />);
  let pending; await act(async () => { pending = api.recompute(); });
  await act(async () => { gate.resolve(identity); await pending; });
  expect(oldFetcher).not.toHaveBeenCalled(); expect(currentFetcher).toHaveBeenCalledTimes(1);
  expect(getResult("m", "p", settingsKey({ a: 9 })).stale).toBe(false);
});
test("repeated Compute while analysis is running joins it without queuing a duplicate", async () => {
  const work = deferred(); const fetcher = jest.fn().mockReturnValue(work.promise);
  render(<Probe autoFetch={false} fetcher={fetcher} />); await settle();
  let first; let second;
  await act(async () => { first = api.recompute(); });
  await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(1));
  await act(async () => { second = api.recompute(); });
  expect(second).toBe(first);
  await act(async () => { work.resolve({ completed: true }); await first; });
  expect(fetcher).toHaveBeenCalledTimes(1); expect(api.data).toEqual({ completed: true });
});
