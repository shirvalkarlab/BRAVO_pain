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
  identityInFlight = SessionController.query("/api/queryServerIdentity", {})
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
  const [tick, setTick] = useState(0);
  const alive = useRef(true);
  useEffect(() => () => { alive.current = false; }, []);

  // Re-read on cache events so a Recompute control turns red when ANOTHER view commits something.
  useEffect(() => subscribe(() => setTick((t) => t + 1)), []);

  useEffect(() => { refreshServerIdentity(); }, []);

  const run = useCallback((why) => {
    if (!enabled || !uid || typeof fetcherRef.current !== "function") return Promise.resolve(null);
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
        if (alive.current) setErr(String((e && e.message) || e));
        return null;
      })
      .finally(() => { if (alive.current) setLoading(false); });
  }, [enabled, uid, moduleKey, key]);

  // The only automatic fetch: nothing cached at all. A changed key does NOT trigger one, which is
  // the difference between this and an ordinary data hook.
  useEffect(() => {
    if (!enabled || !uid) return;
    const cached = getResult(moduleKey, uid, key);
    if (cached) { setEntry(cached); return; }
    if (!loading) run("first load");
    // `loading` is deliberately not a dependency: including it would re-enter this effect when the
    // fetch it started sets it, and the guard exists only to avoid a duplicate first request.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, uid, moduleKey, key, tick, run]);

  const recompute = useCallback(() => {
    invalidate(moduleKey, uid);
    return refreshServerIdentity().then(() => run("explicit recompute"));
  }, [moduleKey, uid, run]);

  const live = (enabled && uid ? getResult(moduleKey, uid, key) : null) || entry;

  return {
    data: live ? live.bundle : null,
    loading,
    err,
    stale: !!(live && live.stale),
    staleReasons: (live && live.staleReasons) || [],
    computedAt: live ? live.computedAt : null,
    notKept: (entry && entry.notKept) || null,
    recompute,
    hasCached: !!live,
  };
}
