/**
 * An expired login goes to the login screen, and back to the same page after logging in (the PI,
 * 2026-11-18).
 *
 * Why: on 2026-11-17 the Closed-Loop page's Recompute button looked dead. The login had run out, the
 * server answered every request 403 "Authentication credentials were not provided.", and the page
 * kept showing its old copy without saying why. Only that exact answer counts: a logged-in user
 * refused a participant also gets a 403, with other words, and stays an ordinary error.
 */
export const RETURN_KEY = "bravo_return_after_login";

const NO_LOGIN = /authentication credentials were not provided/i;

export function isLoginExpired(error) {
  const r = error && error.response;
  if (!r || r.status !== 403 || !r.data) return false;
  return NO_LOGIN.test(String(r.data.detail || ""));
}

let sent = false;

// Swappable so the page tests can watch the redirect (jsdom cannot change the address).
export const loginRedirect = {
  go: (path) => window.location.assign(path),
  reset: () => { sent = false; },
};

// Several panels fail together when a login runs out; the first one sends, the rest do nothing.
export function sendToLogin() {
  if (sent) return;
  sent = true;
  try {
    const { pathname, search } = window.location;
    if (pathname && pathname !== "/login") window.sessionStorage.setItem(RETURN_KEY, pathname + (search || ""));
  } catch (e) { /* storage blocked: the login screen's own default page is used */ }
  loginRedirect.go("/login");
}

// The page to return to, once; only this site's own pages, never the login screen itself.
export function takeReturnPath() {
  let path = null;
  try {
    path = window.sessionStorage.getItem(RETURN_KEY);
    window.sessionStorage.removeItem(RETURN_KEY);
  } catch (e) { return null; }
  if (!path || !path.startsWith("/") || path.startsWith("//") || path.startsWith("/login")) return null;
  return path;
}
