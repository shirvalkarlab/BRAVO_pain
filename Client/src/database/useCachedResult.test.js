/**
 * The hook's fetch discipline: exactly one request per deliberate act, and none otherwise.
 *
 * These exist because the property they pin was WRONG when the hook was first written, and it was
 * found by measuring rather than by reading: one press of Recompute issued TWO concurrent fetches.
 * `invalidate` publishes a store event, the hook re-reads on every event, that read finds nothing
 * cached, and the automatic first-load path started a request while the deliberate one was still
 * waiting behind the server-identity call. The guard at the time tested the `loading` STATE, which
 * cannot work: `setLoading(true)` schedules an update rather than applying one, so a second
 * synchronous pass still saw false. The guard is now a ref, claimed synchronously.
 *
 * On the closed-loop page the consequence was two concurrent requests into single-threaded embedded
 * R, so this is a correctness property and not an efficiency one.
 */
/* eslint-disable import/first */
import { act, render } from "@testing-library/react";
import React from "react";

// The mock must be declared before the module under test is imported, and it must name the
// specifier the hook itself uses. Two details cost a debugging round each and are recorded so the
// next person does not repeat them.
//
// First, the specifier is `database/session-control`, not `./session-control`. The neighbouring
// `resultCache.test.js` mocks the relative form and passes, but that is not evidence the relative
// form works here: `resultCache.js` never imports session-control at all, so nothing in that suite
// ever calls `query`. `cachedPanels.smoke.test.js`, which does render through this hook, uses the
// absolute form.
//
// Second, without an effective mock the failure is not a clear "module not mocked" message. The
// real `query` returns undefined under the test environment, so `refreshServerIdentity` calls
// `.then` on it and React reports `TypeError: Cannot read properties of undefined (reading
// 'then')` thrown from the commit phase, which reads like a fault in the component.
jest.mock("database/session-control", () => ({
  SessionController: {
    query: jest.fn(() => Promise.resolve({ data: { boot_token: "boot-test" } })),
  },
}));

import { invalidateAll, putResult, settingsKey } from "./resultCache";
import { useCachedResult } from "./useCachedResult";

const UID = "TEST01";
const MODULE = "closedLoop";

function Probe({ settings, fetcher, onApi }) {
  const api = useCachedResult({ moduleKey: MODULE, uid: UID, settings, fetcher });
  onApi(api);
  return <div>{api.loading ? "loading" : "idle"}</div>;
}

/** Let the identity call, the fetch and their follow-on state updates all settle. */
const settle = async () => {
  await act(async () => { await Promise.resolve(); });
  await act(async () => { await Promise.resolve(); });
  await act(async () => { await Promise.resolve(); });
};

beforeEach(() => { invalidateAll("test reset"); });

test("a cached entry is reused and one recompute issues exactly one fetch", async () => {
  const fetcher = jest.fn(() => Promise.resolve({ value: 1 }));
  let api = null;
  putResult(MODULE, UID, settingsKey({ a: 1 }), { value: 0 }, null);

  render(<Probe settings={{ a: 1 }} fetcher={fetcher} onApi={(x) => { api = x; }} />);
  await settle();
  expect(fetcher).toHaveBeenCalledTimes(0);      // a cached entry must not provoke a request

  await act(async () => { await api.recompute(); });
  await settle();
  expect(fetcher).toHaveBeenCalledTimes(1);      // the property this file exists for
});

test("a changed settings key shows the old result, marks it stale, and does NOT fetch", async () => {
  const fetcher = jest.fn(() => Promise.resolve({ value: 9 }));
  let api = null;
  putResult(MODULE, UID, settingsKey({ a: 1 }), { value: 0 }, null);

  render(<Probe settings={{ a: 2 }} fetcher={fetcher} onApi={(x) => { api = x; }} />);
  await settle();

  expect(fetcher).toHaveBeenCalledTimes(0);
  expect(api.data).toEqual({ value: 0 });        // the last completed run is still on screen
  expect(api.stale).toBe(true);
  expect(api.staleReasons.join(" ")).toMatch(/settings/i);
});

test("with nothing cached the hook fetches once, not once per store event", async () => {
  const fetcher = jest.fn(() => Promise.resolve({ value: 3 }));
  let api = null;
  render(<Probe settings={{ a: 1 }} fetcher={fetcher} onApi={(x) => { api = x; }} />);
  await settle();
  expect(fetcher).toHaveBeenCalledTimes(1);
  expect(api.data).toEqual({ value: 3 });
  expect(api.stale).toBe(false);
});

test("a rejected fetch keeps the original rejection, not only its message", async () => {
  const boom = Object.assign(new Error("Request failed"), { response: { status: 403 } });
  const fetcher = jest.fn(() => Promise.reject(boom));
  let api = null;
  render(<Probe settings={{ a: 1 }} fetcher={fetcher} onApi={(x) => { api = x; }} />);
  await settle();
  // Stringifying the rejection discarded the status, which the Biomarkers view needs in order to
  // tell an expired session from a server fault when it calls SessionController.displayError.
  expect(api.err).toMatch(/Request failed/);
  expect(api.errRaw && api.errRaw.response && api.errRaw.response.status).toBe(403);
});
