/** One bounded retry for known read operations after a gateway or network failure.
 * A `/query` name is not a read contract: chosen-band choose/clear append history.
 * Keep this list tied to inspected API handlers, not a URL-prefix heuristic.
 * Analysis reads may warm their existing caches; no source/provider write is retried.
 */
const GATEWAY = new Set([502, 503, 504]);
const READS = new Set([
  "/api/queryRedcapTimeline", "/api/queryOuraTimeline", "/api/queryHomeNeuralTimeline",
  "/api/queryServerIdentity", "/api/queryStimProgram", "/api/queryControlAnalyses",
  "/api/queryBiomarkerAnalysis", "/api/queryStimOptimizer", "/api/queryClosedLoopDeployment",
  "/api/queryDeploymentSummary", "/api/queryDeploymentROC", "/api/queryDeploymentRocByEra",
  "/api/queryLsbPower", "/api/queryWiringComparison",
]);
const CANCEL_OR_TIMEOUT = new Set(["ERR_CANCELED", "ECONNABORTED", "ETIMEDOUT"]);

// A short disconnect can last longer than the backoff. Do not spend the only
// retry while the browser already knows it is offline. Reconnection gets at
// most 15 seconds; persistent failure still reaches the page's error state.
function waitForRetry(waitMs) {
  return new Promise((resolve) => setTimeout(resolve, waitMs)).then(() => {
    if (navigator.onLine !== false) return true;
    return new Promise((resolve) => {
      const finish = (ready) => {
        clearTimeout(timer);
        window.removeEventListener("online", online);
        resolve(ready);
      };
      const online = () => { if (navigator.onLine !== false) finish(true); };
      const timer = setTimeout(() => finish(false), 15000);
      window.addEventListener("online", online);
    });
  });
}

export function isRetryableRead(url, body) {
  if (url === "/api/queryClosedLoopChosenBand") return body?.Action === "read";
  return READS.has(url) && body?.Action === undefined;
}

export function retryOnGatewayError(url, send, waitMs = 1500, body) {
  const first = send();
  if (!isRetryableRead(url, body)) return first;
  return Promise.resolve(first).catch((error) => {
    if (!error || error.__CANCEL__ || CANCEL_OR_TIMEOUT.has(error.code)) throw error;
    const status = error.response?.status;
    // The installed XHR adapter may attach its response with status 0 when
    // the connection fails; zero is not an HTTP response status.
    const network = error.code === "ERR_NETWORK" && (!error.response || status === 0);
    if (!GATEWAY.has(status) && !network) throw error;
    return waitForRetry(waitMs).then((ready) => {
      if (!ready) throw error;
      return send();
    });
  });
}
