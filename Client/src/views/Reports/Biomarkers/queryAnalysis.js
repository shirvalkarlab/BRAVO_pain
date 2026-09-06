import { useEffect, useMemo } from "react";
import { SessionController } from "database/session-control";
import { cacheScope } from "database/resultCache";

const ENDPOINTS = new Set([
  "queryBiomarkerAnalysis", "queryDataAvailability", "queryPainScores", "queryBandValidation",
  "emitBandCandidate", "queryDeploymentROC", "queryLsbPower", "queryPsdLsbConversion",
  "queryPsdLsbConversionModel", "queryDeploymentRocByEra", "queryDeploymentSummary", "queryStimOptimizer", "queryClosedLoopResearch",
].map((name) => `/api/${name}`));

function stableKey(value) {
  if (Array.isArray(value)) return `[${value.map(stableKey).join(",")}]`;
  if (value && typeof value === "object") return `{${Object.keys(value).sort()
    .map((key) => `${JSON.stringify(key)}:${stableKey(value[key])}`).join(",")}}`;
  return JSON.stringify(value);
}

/** Shared polling with per-view subscriptions. Leaving a view stops polling, not the server job. */
export function createAnalysisClient(request, getScope = () => null) {
  const tasks = new Map();
  function subscribe(url, body, onProgress) {
    if (!ENDPOINTS.has(url)) throw new Error("Unsupported analysis endpoint");
    const owner = getScope();
    const key = stableKey([owner, url, body]);
    let task = tasks.get(key);
    if (!task) {
      task = { subscribers: new Set(), timer: null };
      tasks.set(key, task);
      const forget = () => { if (tasks.get(key) === task) tasks.delete(key); };
      task.stop = () => { clearTimeout(task.timer); forget(); };
      const obsolete = () => !task.subscribers.size || owner !== getScope();
      const discard = () => { task.subscribers.clear(); task.stop(); };
      task.run = async () => {
        if (obsolete()) { discard(); return; }
        try {
          const response = await request(url, body);
          if (obsolete()) { discard(); return; }
          if (response.status === 202) {
            for (const sub of task.subscribers) if (sub.onProgress) sub.onProgress(response.data);
            const retry = Number(response.headers && response.headers["retry-after"]);
            task.timer = setTimeout(task.run, Math.min(10000, Math.max(1000, (retry || 3) * 1000)));
          } else {
            forget();
            for (const sub of task.subscribers) sub.resolve(response);
            task.subscribers.clear();
          }
        } catch (error) {
          if (obsolete()) { discard(); return; }
          forget();
          for (const sub of task.subscribers) sub.reject(error);
          task.subscribers.clear();
        }
      };
      Promise.resolve().then(task.run);
    }
    let subscription;
    const promise = new Promise((resolve, reject) => {
      subscription = { resolve, reject, onProgress };
      task.subscribers.add(subscription);
    });
    // Cancelled views receive neither a stale success nor a spurious error state.
    const cancel = () => {
      task.subscribers.delete(subscription);
      if (!task.subscribers.size) task.stop();
    };
    return { promise, cancel };
  }
  return { createScope() {
    const owner = getScope();
    const pending = new Map();
    return {
      query(url, body, onProgress) {
        if (owner !== getScope()) return Promise.reject(new Error("The signed-in account or study changed; reopen this analysis."));
        const previous = pending.get(url);
        const requestKey = stableKey(body);
        if (previous && previous.requestKey === requestKey) return previous.promise;
        if (previous) previous.cancel();
        const next = subscribe(url, body, onProgress);
        next.requestKey = requestKey;
        pending.set(url, next);
        const clean = () => { if (pending.get(url) === next) pending.delete(url); };
        next.promise.then(clean, clean);
        return next.promise;
      },
      cancel(url) { const item = pending.get(url); if (item) item.cancel(); pending.delete(url); },
      cancelAll() { for (const item of pending.values()) item.cancel(); pending.clear(); },
    };
  } };
}

const client = createAnalysisClient((url, body) => SessionController.query(url, body), cacheScope);
export function useAnalysisQuery() {
  const owner = cacheScope();
  const scope = useMemo(() => client.createScope(), [owner]);
  useEffect(() => () => scope.cancelAll(), [scope]);
  scope.query.cancel = scope.cancel;
  return scope.query;
}
