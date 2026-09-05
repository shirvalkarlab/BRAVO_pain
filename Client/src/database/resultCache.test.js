/**
 * The five behaviours the result cache exists to provide, pinned as tests.
 *
 * WHY THESE FIVE AND WHY TESTS AT ALL. Every one of them is invisible to a compiling build and to a
 * reader clicking through the application: a page that recomputes when it should have reused, or
 * reuses when it should have marked itself out of date, looks exactly like a page that does the
 * right thing. The only difference is a request that was or was not sent, and how long the reader
 * waited. So the properties are asserted directly — on the store for the ones that are about
 * storage, and through a probe component for the two that are about whether a request goes out,
 * because "does not fetch" is a statement about the hook and cannot be observed from the store.
 *
 * WHY THE UNMOUNT IS SIMULATED BY CALLING THE STORE RATHER THAN BY UNMOUNTING A COMPONENT. The
 * property under test is that the result outlives the component, and the store is where it has to
 * outlive it. Writing the test through a render would test React's unmount behaviour as much as the
 * store's, and would pass just as well if the result were being kept alive by something else on the
 * page.
 */
import React from "react";
import { act, render, waitFor } from "@testing-library/react";

import {
  MODULES, cacheStats, clearUpstreamChanged, getResult, invalidate, invalidateAll,
  markUpstreamChanged, putResult, serverToken, setServerToken, settingsKey,
} from "./resultCache";
import { refreshServerIdentity, useCachedResult } from "./useCachedResult";

// The hook asks the server for its boot token on mount. That is a real request, so it is replaced
// here — both to keep the suite offline and because two of the tests are about what happens when
// the token it returns changes.
jest.mock("./session-control", () => ({
  SessionController: { query: jest.fn(() => Promise.resolve({ data: { boot_token: "boot-1" } })) },
}));
// eslint-disable-next-line import/first
import { SessionController } from "./session-control";

const UID = "TEST01";

/**
 * The store is module state, so it carries between tests unless it is cleared. Everything that can
 * hold a value across a test is reset here: the entries, the upstream marks, and the server token.
 */
beforeEach(() => {
  invalidateAll("test setup");
  [MODULES.biomarkers, MODULES.stimOptimizer, MODULES.closedLoop].forEach((m) => {
    clearUpstreamChanged(m, UID);
  });
  setServerToken(null);
  SessionController.query.mockReset();
  SessionController.query.mockImplementation(() => Promise.resolve({ data: { boot_token: "boot-1" } }));
});

// ------------------------------------------------------------------------------------------------
// 1. A stored result is returned on a later read, with nothing fetched in between.
// ------------------------------------------------------------------------------------------------
test("a result stored for one module is returned on a later read", () => {
  const settings = { LabelMetric: "nrs", MatchToleranceMin: 60 };
  const key = settingsKey(settings);
  const bundle = { analytics: { rows: 3 } };

  expect(putResult(MODULES.biomarkers, UID, key, bundle).stored).toBe(true);

  // The read that stands for a remount: a fresh component would ask the store this exact question.
  const read = getResult(MODULES.biomarkers, UID, key);
  expect(read).not.toBeNull();
  expect(read.bundle).toBe(bundle);          // the same object, not a copy of its contents
  expect(read.stale).toBe(false);
  expect(read.staleReasons).toEqual([]);
  expect(SessionController.query).not.toHaveBeenCalled();
});

test("one module's result is not visible to another module or another participant", () => {
  const key = settingsKey({ a: 1 });
  putResult(MODULES.biomarkers, UID, key, { which: "biomarkers" });
  expect(getResult(MODULES.stimOptimizer, UID, key)).toBeNull();
  expect(getResult(MODULES.biomarkers, "SOMEONE_ELSE", key)).toBeNull();
});

// ------------------------------------------------------------------------------------------------
// 2. A changed settings key returns the OLD result, marked stale, with a reason — and no fetch.
// ------------------------------------------------------------------------------------------------
test("a changed settings key returns the old result marked stale, with a reason", () => {
  const oldBundle = { computed: "under the old settings" };
  putResult(MODULES.biomarkers, UID, settingsKey({ LabelMetric: "nrs" }), oldBundle);

  const read = getResult(MODULES.biomarkers, UID, settingsKey({ LabelMetric: "vas" }));
  expect(read).not.toBeNull();
  expect(read.bundle).toBe(oldBundle);       // kept, not discarded
  expect(read.stale).toBe(true);
  expect(read.staleReasons).toHaveLength(1);
  expect(read.staleReasons[0]).toMatch(/settings on this page have changed/);
});

// ------------------------------------------------------------------------------------------------
// 3. A changed server token drops everything.
// ------------------------------------------------------------------------------------------------
test("the store reports a changed server token, and an unchanged one as unchanged", () => {
  expect(setServerToken("boot-1")).toBe(false);   // first token seen: nothing to compare against
  expect(setServerToken("boot-1")).toBe(false);
  expect(setServerToken("boot-2")).toBe(true);
  expect(serverToken()).toBe("boot-2");
});

test("a changed server token drops every entry", async () => {
  setServerToken("boot-1");
  putResult(MODULES.biomarkers, UID, settingsKey({ a: 1 }), { big: true });
  putResult(MODULES.closedLoop, UID, settingsKey({ b: 2 }), { report: true });
  expect(cacheStats().count).toBe(2);

  // The drop is the identity refresh's decision, not the store's: the store marks a token mismatch
  // as a reason, and the hook module discards on it, because unlike a settings change there is no
  // version of the question a result computed by retired code still answers.
  SessionController.query.mockImplementation(
    () => Promise.resolve({ data: { boot_token: "boot-2" } }));
  await act(async () => { await refreshServerIdentity(); });

  expect(cacheStats().count).toBe(0);
  expect(getResult(MODULES.biomarkers, UID, settingsKey({ a: 1 }))).toBeNull();
});

// ------------------------------------------------------------------------------------------------
// 4. An upstream change marks another module's entry without discarding it.
// ------------------------------------------------------------------------------------------------
test("markUpstreamChanged makes another module's entry stale without discarding it", () => {
  const key = settingsKey({ band: "0-3 at 10 Hz" });
  const bundle = { verdict: "computed for the previous band" };
  putResult(MODULES.closedLoop, UID, key, bundle);
  expect(getResult(MODULES.closedLoop, UID, key).stale).toBe(false);

  markUpstreamChanged(MODULES.closedLoop, UID, "a new band candidate was committed");

  const read = getResult(MODULES.closedLoop, UID, key);
  expect(read).not.toBeNull();
  expect(read.bundle).toBe(bundle);                       // still there
  expect(read.stale).toBe(true);
  expect(read.staleReasons).toContain("a new band candidate was committed");
  expect(cacheStats().count).toBe(1);

  // And the mark is cleared by storing a fresh result, so a rebuilt page does not stay amber.
  putResult(MODULES.closedLoop, UID, key, { verdict: "recomputed" });
  expect(getResult(MODULES.closedLoop, UID, key).stale).toBe(false);
});

// ------------------------------------------------------------------------------------------------
// 5. The hook: no fetch on a changed key, one fetch when there is nothing, and a rebuild on request.
// ------------------------------------------------------------------------------------------------
/**
 * A component whose only job is to run the hook and report what it returned.
 *
 * It writes into an object the test owns rather than rendering anything, because every assertion
 * here is about values and about how many times the fetcher ran, and asserting those through
 * rendered text would test the formatting as well.
 */
function Probe({ settings, fetcher, sink }) {
  const r = useCachedResult({
    moduleKey: MODULES.stimOptimizer, uid: UID, settings, fetcher,
  });
  sink.current = r;
  return null;
}

/**
 * Render the probe and wait until the hook has reported something.
 *
 * The wait is what makes the assertions meaningful: the mount effects start a server-identity
 * request and, when nothing is cached, a fetch, and both settle a tick or two after the first
 * paint. `waitFor` is the sanctioned way to let them settle — wrapping the render in `act` by hand
 * is what the testing library's own lint rule warns against, because the render already does it.
 */
async function mountProbe(props) {
  render(<Probe {...props} />);
  await waitFor(() => expect(props.sink.current).not.toBeNull());
}

test("the hook fetches once when nothing is cached", async () => {
  const fetcher = jest.fn(() => Promise.resolve({ arms: {} }));
  const sink = { current: null };
  await mountProbe({ settings: { Backend: "plotly" }, fetcher, sink });
  await waitFor(() => expect(sink.current.data).toEqual({ arms: {} }));

  expect(fetcher).toHaveBeenCalledTimes(1);
  expect(sink.current.stale).toBe(false);
});

test("a changed settings key does not fetch: the old result is shown and marked", async () => {
  putResult(MODULES.stimOptimizer, UID, settingsKey({ WashinMin: 1.0 }),
    { arms: { computedUnder: "one minute" } });

  const fetcher = jest.fn(() => Promise.resolve({ arms: { computedUnder: "five minutes" } }));
  const sink = { current: null };
  await mountProbe({ settings: { WashinMin: 5.0 }, fetcher, sink });
  // Give the mount effects room to issue a request if they were going to. They are not, which is
  // the property under test.
  await waitFor(() => expect(sink.current.data).not.toBeNull());

  expect(fetcher).not.toHaveBeenCalled();
  expect(sink.current.data).toEqual({ arms: { computedUnder: "one minute" } });
  expect(sink.current.stale).toBe(true);
  expect(sink.current.staleReasons[0]).toMatch(/settings on this page have changed/);
});

test("recompute() refetches and clears the stale flag", async () => {
  putResult(MODULES.stimOptimizer, UID, settingsKey({ WashinMin: 1.0 }), { arms: { n: 1 } });

  const fetcher = jest.fn(() => Promise.resolve({ arms: { n: 2 } }));
  const sink = { current: null };
  await mountProbe({ settings: { WashinMin: 5.0 }, fetcher, sink });
  expect(fetcher).not.toHaveBeenCalled();
  expect(sink.current.stale).toBe(true);

  await act(async () => { await sink.current.recompute(); });

  expect(fetcher).toHaveBeenCalled();
  expect(sink.current.data).toEqual({ arms: { n: 2 } });
  expect(sink.current.stale).toBe(false);
  expect(sink.current.staleReasons).toEqual([]);
});

test("discarding an entry is enough on its own to make a mounted hook refetch exactly once", async () => {
  // This is the property the views rely on instead of calling `recompute()` directly, so it is
  // asserted rather than assumed. See views/Reports/moduleCacheKeys for why they do that.
  const fetcher = jest.fn(() => Promise.resolve({ arms: { n: 1 } }));
  const sink = { current: null };
  await mountProbe({ settings: { WashinMin: 1.0 }, fetcher, sink });
  await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(1));

  await act(async () => { invalidate(MODULES.stimOptimizer, UID); });
  await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(2));
  expect(sink.current.stale).toBe(false);
});
