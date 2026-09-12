/**
 * The one hook the three analysis views use to fetch a result that survives navigation.
 *
 * It wraps `database/resultCache` so that each view does not have to reimplement the same four
 * decisions — when to reuse, when to refetch, what to show while a refetch is in flight, and how
 * to describe a result that is no longer current. Getting any of those wrong in one view and right
 * in another is how three modules end up disagreeing about whether the page is up to date.
 *
 * THE BEHAVIOUR, stated plainly because it is the whole point.
 *
 *   - On mount with a cached result present, the result is returned IMMEDIATELY and nothing is
 *     fetched. There is no loading screen and no request, even if the settings have changed since.
 *   - When the settings have changed, or the server has restarted, or an upstream commit was
 *     declared, the cached result is STILL returned, together with `stale: true` and a plain
 *     sentence per reason. The view shows the last completed analysis and marks its Recompute
 *     control. It does not silently recompute, because that would reintroduce the wait the cache
 *     exists to remove, and it does not silently hide the result, because the reader asked to see
 *     it.
 *   - Nothing is fetched until either there is no cached result at all, or `recompute()` is
 *     called. That is the explicit act the PI asked for.
 *
 * `fetcher` must be a function returning a promise of the result bundle. It is called with no
 * arguments, so the caller closes over whatever it needs; and it is re-read from a ref on every
 * call, so a stale closure cannot be invoked after the settings change.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  clearUpstreamChanged, getResult, invalidate, invalidateAll, putResult, setServerToken,
  settingsKey, subscribe,
} from "database/resultCache";
import { SessionController } from "database/session-control";

/**
 * Ask the server for its boot token and hand it to the cache.
 *
 * Deliberately best-effort: if this request fails the cache simply has no token to compare and
 * keeps working on the settings key alone. Failing closed here — refusing to use the cache because
 * the token could not be read — would make an unrelated network problem look like a broken cache.
 */
let identityInFlight = null;
export function refreshServerIdentity() {
  if (identityInFlight) return identityInFlight;
  // Wrapped rather than chained directly off the call, so that a transport which returns something
  // other than a promise cannot throw. This is not a hypothetical tidiness fix: chaining `.then`
  // straight onto the call raised `TypeError: Cannot read properties of undefined (reading 'then')`
  // from inside a `useEffect`, which React reports as an error thrown during the commit phase and
  // which unmounts the whole panel. A best-effort request whose only job is to notice a server
  // restart must never be able to take a page down; if it cannot report a token the cache simply
  // compares on the settings key alone, which is the documented degraded behaviour.
  identityInFlight = Promise.resolve()
    .then(() => SessionController.query("/api/queryServerIdentity", {}))
    .then((res) => {
      const token = res && res.data ? res.data.boot_token : null;
      const changed = setServerToken(token);
      if (changed) {
        // Every entry was computed by code that is no longer running, so none of them can be
        // trusted — not just the one being read. They are dropped rather than marked, because
        // unlike a settings change there is no version of the question they still answer.
        invalidateAll("the server restarted or reloaded its analysis code");
      }
      return res && res.data ? res.data : null;
    })
    .catch(() => null)
    .finally(() => { identityInFlight = null; });
  return identityInFlight;
}

export function useCachedResult({ moduleKey, uid, settings, fetcher, enabled = true }) {
  const key = useMemo(() => settingsKey(settings), [settings]);
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;

  // Read the cache during the FIRST render rather than in an effect. Reading it in an effect would
  // paint one frame of the loading state before the cached result appeared, which is visible as a
  // flash on every navigation and defeats the purpose.
  const initial = enabled && uid ? getResult(moduleKey, uid, key) : null;
  const [entry, setEntry] = useState(initial);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState(null);
  const [errRaw, setErrRaw] = useState(null);
  const [tick, setTick] = useState(0);
  const alive = useRef(true);
  // Raised synchronously whenever a request is outstanding, so that the automatic-fetch effect and
  // an explicit recompute cannot both start one. A ref rather than state because the two paths can
  // run in the same synchronous pass, and a state update is not visible until the next render.
  const fetchInFlight = useRef(false);
  useEffect(() => () => { alive.current = false; }, []);

  // Re-read on cache events so a Recompute control turns red when ANOTHER view commits something.
  useEffect(() => subscribe(() => setTick((t) => t + 1)), []);

  useEffect(() => { refreshServerIdentity(); }, []);

  const run = useCallback((why) => {
    if (!enabled || !uid || typeof fetcherRef.current !== "function") return Promise.resolve(null);
    // Claimed synchronously, for the reason the automatic-fetch effect below explains: the
    // `loading` STATE is not readable by a second synchronous pass, so it cannot serve as a guard.
    if (fetchInFlight.current) return Promise.resolve(null);
    fetchInFlight.current = true;
    setLoading(true);
    setErr(null);
    return Promise.resolve()
      .then(() => fetcherRef.current())
      .then((bundle) => {
        if (!alive.current) return null;
        const stored = putResult(moduleKey, uid, key, bundle, { why: why || null });
        clearUpstreamChanged(moduleKey, uid);
        setEntry({
          bundle,
          key,
          savedAt: Date.now(),
          computedAt: Date.now(),
          stale: false,
          staleReasons: [],
          notKept: stored.stored ? null : stored.reason,
        });
        return bundle;
      })
      .catch((e) => {
        // The ORIGINAL rejection is kept alongside the message, because stringifying it here threw
        // away information the callers need: the Biomarkers view hands the failed response to
        // `SessionController.displayError`, which reads the status to distinguish a session that
        // has expired from a server fault, and a bare message collapses those into one sentence.
        if (alive.current) { setErrRaw(e); setErr(String((e && e.message) || e)); }
        return null;
      })
      .finally(() => {
        fetchInFlight.current = false;
        if (alive.current) setLoading(false);
      });
  }, [enabled, uid, moduleKey, key]);

  // The only automatic fetch: nothing cached at all. A changed key does NOT trigger one, which is
  // the difference between this and an ordinary data hook.
  //
  // THE GUARD IS A REF, NOT THE `loading` STATE, and the difference is not stylistic. An earlier
  // version tested `if (!loading)`, which cannot work: `setLoading(true)` schedules a state update
  // rather than applying one, so a second synchronous pass through this effect still sees `false`.
  // Measured consequence, found by a probe component rather than by reading the code: one press of
  // Recompute issued TWO fetches. `invalidate` publishes a store event, the hook re-reads on every
  // event, that read finds nothing cached, and this effect started an ordinary first-load request
  // while the deliberate one was still waiting behind the server-identity call. On the deployment
  // page that is two concurrent requests into single-threaded embedded R, so it is a correctness
  // problem and not merely wasteful.
  useEffect(() => {
    if (!enabled || !uid) return;
    const cached = getResult(moduleKey, uid, key);
    if (cached) { setEntry(cached); return; }
    if (fetchInFlight.current) return;
    run("first load");
    // `loading` is deliberately absent from the dependency list: it is state this effect's own
    // fetch sets, so depending on it would re-enter the effect it just started.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, uid, moduleKey, key, tick, run]);

  /**
   * Discard the cached result and compute a fresh one, issuing exactly one request.
   *
   * The server identity is refreshed FIRST, before anything is discarded, because it can itself
   * invalidate the whole store: if the server restarted while the tab was open, every entry was
   * computed by code that is no longer running, and finding that out after refetching one slot
   * would leave the other eight quietly wrong.
   *
   * The in-flight flag is raised synchronously here, before `invalidate` publishes its event, so
   * the automatic path above sees it on the very next pass. Callers no longer need to sequence
   * these steps themselves.
   */
  const recompute = useCallback(() => {
    if (fetchInFlight.current) return Promise.resolve(null);
    fetchInFlight.current = true;
    setLoading(true);
    return refreshServerIdentity()
      .then(() => {
        invalidate(moduleKey, uid);
        fetchInFlight.current = false;      // released so `run` can claim it in the usual way
        return run("explicit recompute");
      })
      .catch((e) => {
        fetchInFlight.current = false;
        if (alive.current) { setErr(String((e && e.message) || e)); setLoading(false); }
        return null;
      });
  }, [moduleKey, uid, run]);

  const live = (enabled && uid ? getResult(moduleKey, uid, key) : null) || entry;

  return {
    data: live ? live.bundle : null,
    loading,
    err,
    // The unmodified rejection, for callers that need the status rather than the message.
    errRaw,
    stale: !!(live && live.stale),
    staleReasons: (live && live.staleReasons) || [],
    computedAt: live ? live.computedAt : null,
    notKept: (entry && entry.notKept) || null,
    recompute,
    hasCached: !!live,
  };
}
