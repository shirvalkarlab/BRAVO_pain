/**
 * One retry for a read that failed because the web server had no worker to hand it to (502, 503 or
 * 504). The page review of 2026-10-02 saw a first load and a "Recompute anyway" each answered by a
 * 502 while the workers were busy; the same request a moment later succeeded, but the page had
 * already replaced its result with an error. Only `/api/query...` reads are retried, never a
 * write (`update...`, `login`, `choose`), and only once.
 */
const GATEWAY = new Set([502, 503, 504]);

export const isRetryableRead = (url) => /^\/api\/query[A-Za-z]/.test(String(url || ""));

export function retryOnGatewayError(url, send, waitMs = 1500) {
  const first = send();
  if (!isRetryableRead(url)) return first;
  return Promise.resolve(first).catch((error) => {
    const status = error && error.response && error.response.status;
    if (!GATEWAY.has(status)) throw error;
    return new Promise((resolve) => setTimeout(resolve, waitMs)).then(() => send());
  });
}
