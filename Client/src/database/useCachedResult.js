import { useCallback, useEffect, useRef, useState } from "react";
import { SessionController } from "database/session-control";
import { cacheScope, cacheVersion, getResult, invalidate, invalidateParticipant, isCompletedResult,
  putResult, serverToken, setServerToken, settingsKey, subscribe } from "database/resultCache";

const identityRequests = new Map();

/** Read-only access/input/QC validation. Failure never falls back to an unvalidated result. */
export function refreshServerIdentity(uid) {
  const scope = cacheScope();
  if (!uid || !scope) return Promise.reject(new Error("An authenticated participant is required"));
  const key = settingsKey([scope, uid]);
  if (identityRequests.has(key)) return identityRequests.get(key);
  const promise = Promise.resolve()
    .then(() => SessionController.query("/api/queryServerIdentity", { ParticipantId: uid }))
    .then((res) => {
      if (cacheScope() !== scope) throw new Error("The signed-in account or study changed");
      if (!res || res.status === 202 || !res.data || !res.data.boot_token) throw new Error("Could not validate the analysis identity");
      setServerToken(res.data.boot_token, uid);
      if (res.data.stable_across_workers === false) invalidateParticipant(uid, "server identity is not stable across workers");
      return res.data;
    })
    .catch((error) => {
      if (cacheScope() === scope) {
        setServerToken(null, uid);
        invalidateParticipant(uid, "analysis identity could not be verified");
      }
      throw error;
    })
    .finally(() => { if (identityRequests.get(key) === promise) identityRequests.delete(key); });
  identityRequests.set(key, promise);
  return promise;
}

/** Navigation reuses completed results only after server validation. Settings changes are marked. */
export function useCachedResult({ moduleKey, uid, settings, fetcher, enabled = true,
  autoFetch = true, identity = null }) {
  const scope = cacheScope(identity);
  const key = settingsKey(settings);
  const stamp = settingsKey([scope, moduleKey, uid, enabled]);
  const latest = useRef(null);
  latest.current = { stamp, fetcher, key, identity };
  const alive = useRef(false);
  const flight = useRef(null);
  const attempt = useRef(null);
  const [validation, setValidation] = useState(null);
  const [entry, setEntry] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [tick, setTick] = useState(0);

  useEffect(() => { alive.current = true; return () => { alive.current = false; flight.current = null; }; }, []);
  useEffect(() => subscribe((event) => {
    if (!event.uid || event.uid === uid) setTick((n) => n + 1);
  }), [uid]);

  const run = useCallback((explicit = false, verified = null) => {
    if (!enabled || !uid || !scope || latest.current.stamp !== stamp) return Promise.resolve(null);
    if (flight.current && flight.current.stamp === stamp) {
      // A first Compute can enable this hook and join its mount-time identity check in the same
      // commit. Promote that validation to an explicit run; joining must not swallow the click.
      if (explicit && !flight.current.started) {
        flight.current.explicit = true;
        flight.current.captured = latest.current;
      }
      return flight.current.promise;
    }
    const request = { stamp, explicit, captured: latest.current, started: false };
    const stillHere = () => alive.current && flight.current === request && latest.current.stamp === stamp && cacheScope(request.captured.identity) === scope;
    flight.current = request;
    setLoading(true);
    setError(null);
    request.promise = Promise.resolve(verified || refreshServerIdentity(uid))
      .then(async (verifiedIdentity) => {
        if (!stillHere()) return null;
        setValidation({ stamp, token: verifiedIdentity.boot_token, cacheable: verifiedIdentity.stable_across_workers !== false });
        const captured = request.captured;
        if (request.explicit) invalidate(moduleKey, uid);
        const version = cacheVersion(moduleKey, uid);
        attempt.current = `${stamp}:${version}`;
        const cached = verifiedIdentity.stable_across_workers !== false && getResult(moduleKey, uid, captured.key, captured.identity);
        if (!request.explicit && cached) return cached.bundle;
        if (!request.explicit && !autoFetch) return null;
        if (typeof captured.fetcher !== "function") return null;
        request.started = true;
        const bundle = await captured.fetcher();
        if (!stillHere() || version !== cacheVersion(moduleKey, uid) || serverToken(uid) !== verifiedIdentity.boot_token) return null;
        if (!isCompletedResult(bundle)) throw new Error("Analysis is still pending; use the completed analysis response");
        const kept = verifiedIdentity.stable_across_workers === false
          ? { stored: false, reason: "server identity could not be shared across workers" }
          : putResult(moduleKey, uid, captured.key, bundle, null, captured.identity);
        setEntry({ stamp, version, bundle, key: captured.key, computedAt: Date.now(),
          notKept: kept.stored ? null : kept.reason });
        return bundle;
      })
      .catch((err) => {
        if (stillHere()) {
          setError(err);
          // Authentication failures never leave a previous result on screen.
          if (!serverToken(uid) || [401, 403].includes(err && err.response && err.response.status)) {
            invalidateParticipant(uid, "access or identity validation failed");
            setEntry(null); setValidation(null);
          }
        }
        return null;
      })
      .finally(() => {
        if (flight.current === request) {
          const active = stillHere();
          flight.current = null;
          if (active) { setLoading(false); setTick((n) => n + 1); }
        }
      });
    return request.promise;
  }, [enabled, uid, scope, stamp, moduleKey, autoFetch]);

  // Validate once on each mounted account/study/participant scope, including explicitly run panels.
  useEffect(() => {
    setValidation(null); setEntry(null); setError(null); attempt.current = null;
    if (enabled && uid && scope) run(); else setLoading(false);
  }, [stamp, enabled, uid, scope, run]);

  useEffect(() => {
    if (!enabled || !autoFetch || !validation || validation.stamp !== stamp || error) return;
    const version = cacheVersion(moduleKey, uid);
    if (attempt.current === `${stamp}:${version}` || (flight.current && flight.current.stamp === stamp)) return;
    if (!getResult(moduleKey, uid, key, identity)) run();
  }, [tick, validation, enabled, autoFetch, stamp, moduleKey, uid, key, identity, error, run]);

  const validated = enabled && validation && validation.stamp === stamp && validation.token === serverToken(uid);
  const cached = validated && validation.cacheable ? getResult(moduleKey, uid, key, identity) : null;
  const local = validated && entry && entry.stamp === stamp && entry.version === cacheVersion(moduleKey, uid) ? entry : null;
  const live = cached || local;
  const staleReasons = cached ? cached.staleReasons : local && local.key !== key
    ? ["the settings on this page have changed since this result was computed"] : [];
  const recompute = useCallback(() => run(true), [run]);
  return { data: live ? live.bundle : null, loading: enabled && loading,
    err: error ? String(error.message || error) : null, errRaw: error,
    stale: staleReasons.length > 0, staleReasons, computedAt: live ? live.computedAt : null,
    notKept: local ? local.notKept : null, recompute, hasCached: !!live };
}
