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
  expect(cacheStats().count).toBe(8);
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


// Exercise large budget boundaries without allocating hundred-megabyte fixtures. Only the
// entry-size serialization is intercepted; scope/key JSON serialization stays real. Small
// real-string tests below separately check the UTF-16 measurement and lossy-value rejection.
function mockEntryBytes() {
  const stringify = JSON.stringify;
  return jest.spyOn(JSON, "stringify").mockImplementation((value, replacer, ...rest) => {
    if (typeof replacer === "function" && value?.bundle?.testBytes !== undefined) {
      return { length: value.bundle.testBytes / 2 };
    }
    return stringify(value, replacer, ...rest);
  });
}
afterEach(() => jest.restoreAllMocks());

test("one participant can keep multiple modules; the separate entry ceiling still applies", () => {
  for (let i = 0; i < 25; i += 1) expect(putResult(`module-${i}`, "p", "k", { answer: i }).stored).toBe(true);
  expect(cacheStats()).toMatchObject({ count: 24, maxEntries: 24, participantCount: 1, maxParticipants: 8 });
  expect(getResult("module-0", "p", "k")).toBeNull();
  expect(getResult("module-24", "p", "k")).not.toBeNull();
});

test("participant bound evicts all slots of the least recently used other participant", () => {
  const time = jest.spyOn(Date, "now").mockReturnValue(1);
  putResult("old-panel", "active", "k", {});
  time.mockReturnValue(2); putResult("one", "abandoned", "k", {});
  time.mockReturnValue(3); putResult("two", "abandoned", "k", {});
  for (let i = 0; i < 6; i += 1) {
    time.mockReturnValue(4 + i); putResult("m", `other-${i}`, "k", {});
  }
  time.mockReturnValue(20); putResult("fresh-panel", "active", "k", {});
  time.mockReturnValue(21); getResult("old-panel", "active", "k");
  time.mockReturnValue(22); putResult("m", "ninth", "k", {});
  expect(cacheStats().participantCount).toBe(8);
  expect(getResult("one", "abandoned", "k")).toBeNull();
  expect(getResult("two", "abandoned", "k")).toBeNull();
  expect(getResult("old-panel", "active", "k")).not.toBeNull();
  expect(getResult("fresh-panel", "active", "k")).not.toBeNull();
});

test("participant LRU uses reads rather than save time or only its oldest module", () => {
  const time = jest.spyOn(Date, "now").mockReturnValue(1);
  putResult("m", "first", "k", {});
  for (let i = 0; i < 7; i += 1) {
    time.mockReturnValue(2 + i); putResult("m", `p${i}`, "k", {});
  }
  time.mockReturnValue(20); getResult("m", "first", "k");
  time.mockReturnValue(21); putResult("m", "new", "k", {});
  expect(getResult("m", "first", "k")).not.toBeNull();
  expect(getResult("m", "p0", "k")).toBeNull();
});

test("byte limit evicts another participant before older current-participant modules", () => {
  mockEntryBytes();
  const time = jest.spyOn(Date, "now").mockReturnValue(1);
  const mb = 1024 * 1024;
  putResult("one", "p", "k", { testBytes: 60 * mb });
  time.mockReturnValue(2); putResult("m", "other", "k", { testBytes: 60 * mb });
  time.mockReturnValue(3); putResult("two", "p", "k", { testBytes: 60 * mb });
  expect(getResult("one", "p", "k")).not.toBeNull();
  expect(getResult("m", "other", "k")).toBeNull();
  expect(cacheStats()).toMatchObject({ totalBytes: 120 * mb, count: 2, participantCount: 1 });
});

test("byte eviction falls back to current participant LRU and permits exact budget", () => {
  mockEntryBytes();
  const time = jest.spyOn(Date, "now").mockReturnValue(1);
  const max = cacheStats().maxTotalBytes;
  expect(max).toBe(150 * 1024 * 1024);
  putResult("one", "p", "k", { testBytes: max / 2 });
  time.mockReturnValue(2); putResult("two", "p", "k", { testBytes: max / 2 });
  expect(cacheStats().totalBytes).toBe(max);
  time.mockReturnValue(3); getResult("one", "p", "k");
  time.mockReturnValue(4); putResult("three", "p", "k", { testBytes: max / 2 });
  expect(getResult("two", "p", "k")).toBeNull();
  expect(getResult("one", "p", "k")).not.toBeNull();
  expect(cacheStats().totalBytes).toBe(max);
  putResult("all", "p", "k", { testBytes: max });
  expect(cacheStats()).toMatchObject({ count: 1, totalBytes: max });
});

test("oversized new or replacement entry is declined without displacing valid results", () => {
  mockEntryBytes();
  const max = cacheStats().maxTotalBytes;
  putResult("m", "p", "old", { testBytes: 20 });
  markUpstreamChanged("m", "p", "source changed");
  const listener = jest.fn(); const stop = subscribe(listener);
  expect(putResult("m", "p", "new", { testBytes: max + 2 })).toEqual({ stored: false, reason: "result exceeds the cache byte budget" });
  expect(putResult("new", "q", "k", { testBytes: max + 2 }).stored).toBe(false);
  expect(getResult("m", "p", "new")).toMatchObject({ key: "old", stale: true });
  expect(cacheStats()).toMatchObject({ count: 1, totalBytes: 20 });
  expect(listener).not.toHaveBeenCalled(); stop();
});

test("replacement and every invalidation path release their recorded byte accounting", () => {
  mockEntryBytes();
  putResult("m", "p", "k", { testBytes: 80 });
  putResult("m", "p", "k", { testBytes: 20 });
  putResult("other", "q", "k", { testBytes: 40 });
  expect(cacheStats().totalBytes).toBe(60);
  invalidate("m", "p"); expect(cacheStats().totalBytes).toBe(40);
  setServerToken("old", "q"); setServerToken("new", "q");
  expect(cacheStats()).toMatchObject({ totalBytes: 0, participantCount: 0 });
  putResult("m", "p", "k", { testBytes: 80 }); invalidateAll();
  expect(cacheStats().totalBytes).toBe(0);
  putResult("m", "p", "k", { testBytes: 80 });
  SessionController.getUser.mockReturnValue({ ...user });
  expect(cacheStats()).toMatchObject({ totalBytes: 0, participantCount: 0 });
  putResult("m", "p", "k", { testBytes: 80 });
  SessionController.getUser.mockReturnValue(null);
  expect(cacheStats().totalBytes).toBe(0);
});

test("actual JSON UTF-16 accounting includes Unicode payloads and metadata", () => {
  putResult("m", "p", "k", { value: "a" }, { note: "a" });
  const baseline = cacheStats().totalBytes;
  putResult("m", "p", "k", { value: "é😀" }, { note: "a" });
  expect(cacheStats().totalBytes - baseline).toBe(4); // 3 UTF-16 units replacing one.
  putResult("m", "p", "k", { value: "é😀" }, { note: "abcdef" });
  expect(cacheStats().totalBytes - baseline).toBe(14);
  expect(cacheStats().byteMeasurement).toBe("serialized UTF-16 at insertion; not heap usage");
});

test.each([undefined, () => {}, Symbol("private"), 1n, NaN, Infinity, -Infinity, new Map([["private", "data"]]), new Set([1]), new Date(0)])(
  "non-JSON nested payloads cannot receive a nominal fallback size: %s", (value) => {
    expect(putResult("m", "p", "k", { value }).stored).toBe(false);
    expect(cacheStats().count).toBe(0);
  }
);

test("cycles, hidden toJSON conversion and serialization failure preserve prior result", () => {
  putResult("m", "p", "k", { valid: [null, 0, false] });
  const cycle = {}; cycle.self = cycle;
  for (const invalid of [cycle, { toJSON: () => ({ small: true }) }, { toJSON: () => { throw new Error("private"); } }]) {
    expect(putResult("m", "p", "k", invalid).stored).toBe(false);
  }
  expect(putResult("m", "p", "k", {}, cycle).stored).toBe(false);
  expect(getResult("m", "p", "k").bundle).toEqual({ valid: [null, 0, false] });
});

test("heap pressure introduced during serialization declines retention", () => {
  const stringify = JSON.stringify;
  jest.spyOn(JSON, "stringify").mockImplementation((value, replacer, ...rest) => {
    if (typeof replacer === "function") Object.defineProperty(performance, "memory", {
      configurable: true, value: { usedJSHeapSize: 90, jsHeapSizeLimit: 100 }
    });
    return stringify(value, replacer, ...rest);
  });
  expect(putResult("m", "p", "k", {}).stored).toBe(false);
  expect(cacheStats().totalBytes).toBe(0);
});

test("new aggregate statistics expose neither identifiers nor request/payload content", () => {
  putResult("module-private", "participant-private", "settings-private", { secret: "payload-private" }, { note: "meta-private" });
  const stats = cacheStats();
  expect(stats).toMatchObject({ count: 1, participantCount: 1, memoryMeasurable: false });
  expect(Object.keys(stats).sort()).toEqual(["byteMeasurement", "count", "maxEntries", "maxParticipants", "maxTotalBytes", "memory", "memoryMeasurable", "participantCount", "totalBytes"].sort());
  expect(JSON.stringify(stats)).not.toMatch(/private|viewer|token|study/);
});

test("first participant token learned after caching is a hard miss, never merely stale", () => {
  setServerToken(null, "p");
  putResult("m", "p", "k", { value: 1 });
  putResult("m", "q", "k", { value: 2 });
  expect(setServerToken("first-identity", "p")).toBe(false);
  expect(getResult("m", "p", "k")).toBeNull();
  expect(getResult("m", "q", "k").bundle).toEqual({ value: 2 });
});
