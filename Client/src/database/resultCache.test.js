import { SessionController } from "database/session-control";
import { cacheScope, cacheStats, clearUpstreamChanged, getResult, invalidate, invalidateAll,
  isCompletedResult, markUpstreamChanged, memoryInfo, putResult, serverToken, setServerToken,
  settingsKey, subscribe, underMemoryPressure } from "./resultCache";
jest.mock("database/session-control", () => ({ SessionController: {
  getUser: jest.fn(), getSession: jest.fn(), getServer: jest.fn(() => "local")
} }));
const user = { ID: "viewer", Role: "User", ReadOnly: true };
beforeEach(() => {
  SessionController.getUser.mockReturnValue(user);
  SessionController.getSession.mockReturnValue({ ActiveStudy: "study" });
  cacheScope(); invalidateAll(); setServerToken("token", "p");
  Object.defineProperty(performance, "memory", { configurable: true, value: undefined });
});
test("keys normalize field order but retain scientific setting differences", () => {
  expect(settingsKey({ z: [{ b: 2, a: 1 }], a: undefined })).toBe(settingsKey({ z: [{ a: 1, b: 2 }] }));
  expect(settingsKey({ value: Infinity })).toBe(settingsKey({ value: null }));
  expect(settingsKey()).toBe("null");
  const cycle = {}; cycle.a = cycle;
  expect(settingsKey(cycle)).not.toBe(settingsKey(cycle));
});
test("stores completed result and stable computation time while reads touch LRU", () => {
  const time = jest.spyOn(Date, "now").mockReturnValue(10);
  expect(putResult("m", "p", "k", { answer: 1 }).stored).toBe(true);
  time.mockReturnValue(20);
  expect(getResult("m", "p", "k")).toMatchObject({ computedAt: 10, stale: false, bundle: { answer: 1 } });
  expect(getResult("other", "p", "k")).toBeNull();
  expect(getResult("m", "other", "k")).toBeNull();
  time.mockRestore();
});
test("changed controls are visibly stale; upstream invalidation has a reason", () => {
  putResult("m", "p", "old", { value: 2 });
  markUpstreamChanged("m", "p", "band changed");
  expect(getResult("m", "p", "new").staleReasons).toHaveLength(2);
  clearUpstreamChanged("m", "p");
  expect(getResult("m", "p", "old").stale).toBe(false);
  invalidate("m", "p"); expect(getResult("m", "p", "old")).toBeNull();
});
test.each([null, { status: 202 }, { status: "running" }, { data: { status: "queued" } }])("pending response cannot enter cache: %s", (pending) => {
  expect(isCompletedResult(pending)).toBe(false);
  expect(putResult("m", "p", "k", pending).stored).toBe(false);
  expect(cacheStats().count).toBe(0);
});
test("unknown/zero scientific values are retained in completed payloads", () => {
  expect(isCompletedResult({ value: null, other: 0 })).toBe(true);
});
test("identity changes hard-miss and isolate optional input/QC identity", () => {
  putResult("m", "p", "k", { value: 1 }, null, { qc: "a" });
  expect(getResult("m", "p", "k", { qc: "a" })).not.toBeNull();
  expect(getResult("m", "p", "k", { qc: "b" })).toBeNull();
  expect(setServerToken("changed", "p")).toBe(true);
  expect(getResult("m", "p", "k", { qc: "a" })).toBeNull();
  expect(serverToken("p")).toBe("changed");
});
test.each(["account", "study", "permission", "logout", "reauthentication"])("never reuses after %s change", (change) => {
  putResult("m", "p", "k", { private: true });
  if (change === "account") SessionController.getUser.mockReturnValue({ ID: "other" });
  if (change === "study") SessionController.getSession.mockReturnValue({ ActiveStudy: "other" });
  if (change === "permission") SessionController.getUser.mockReturnValue({ ...user, ReadOnly: false });
  if (change === "logout") SessionController.getUser.mockReturnValue({});
  if (change === "reauthentication") SessionController.getUser.mockReturnValue({ ...user });
  expect(getResult("m", "p", "k")).toBeNull();
  expect(cacheStats().count).toBe(0);
});
test("missing participant or account cannot retain a result", () => {
  expect(putResult("m", null, "k", {}).stored).toBe(false);
  SessionController.getUser.mockReturnValue({});
  expect(putResult("m", "p", "k", {}).stored).toBe(false);
});
test("memory guard bounds retention without localStorage or exposing cache identifiers", () => {
  const write = jest.spyOn(Storage.prototype, "setItem");
  expect(memoryInfo()).toBeNull(); expect(underMemoryPressure()).toBe(false);
  for (let i = 0; i < 25; i += 1) putResult("m", `p${i}`, "k", { value: i });
  expect(cacheStats().count).toBe(24);
  expect(cacheStats().entries).toBeUndefined();
  Object.defineProperty(performance, "memory", { configurable: true,
    value: { usedJSHeapSize: 90, jsHeapSizeLimit: 100 } });
  expect(underMemoryPressure()).toBe(true);
  expect(putResult("m", "p", "k", {}).stored).toBe(false);
  expect(cacheStats().count).toBe(0); expect(write).not.toHaveBeenCalled(); write.mockRestore();
});
test("one throwing subscriber cannot break another subscriber", () => {
  const notified = jest.fn();
  const stopA = subscribe(() => { throw new Error("test"); }); const stopB = subscribe(notified);
  putResult("m", "p", "k", {}); expect(notified).toHaveBeenCalledTimes(1);
  stopA(); stopB(); invalidateAll(); expect(notified).toHaveBeenCalledTimes(1);
});
test("upstream default reasons and participant invalidation cannot affect other participants", () => {
  putResult("m", "p", "k", {}); putResult("m", "q", "k", {});
  markUpstreamChanged("m", "p"); markUpstreamChanged("m", "q", "other");
  expect(getResult("m", "p", "k").staleReasons).toContain("an input changed");
  setServerToken("updated", "p");
  expect(getResult("m", "q", "k").staleReasons).toEqual(["other"]);
  expect(setServerToken("updated", "p")).toBe(false);
  setServerToken(null, "p"); expect(serverToken("p")).toBeNull();
});
test("default token and undefined participant cache scopes remain explicit", () => {
  expect(serverToken()).toBeNull(); setServerToken("global"); expect(serverToken()).toBe("global");
  expect(putResult(null, "p", "k", {}).stored).toBe(false);
  SessionController.getUser.mockReturnValue(null); expect(cacheScope()).toBeNull(); expect(cacheScope()).toBeNull();
  SessionController.getUser.mockReturnValue(user); SessionController.getSession.mockReturnValue(null);
  expect(cacheScope()).not.toBeNull();
});
test("pending data status is rejected even without an outer HTTP status", () => {
  expect(isCompletedResult({ data: { status: 202 } })).toBe(false);
  expect(isCompletedResult({ data: { status: "complete", value: 0 } })).toBe(true);
});
