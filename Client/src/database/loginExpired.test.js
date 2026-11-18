/**
 * An expired login goes to the login screen, and back to the same page afterwards (the PI,
 * 2026-11-18). Found 2026-11-17: the Closed-Loop page's Recompute looked dead for hours because
 * every request was answered 403 "Authentication credentials were not provided." and the page kept
 * its old copy without a word.
 */
import { isLoginExpired, sendToLogin, takeReturnPath, loginRedirect, RETURN_KEY } from "./loginExpired";

const expired = { response: { status: 403, data: { detail: "Authentication credentials were not provided." } } };

test("only the server's no-login answer counts as an expired login", () => {
  expect(isLoginExpired(expired)).toBe(true);
  // A logged-in user refused a participant is a different 403 and stays an ordinary error.
  expect(isLoginExpired({ response: { status: 403, data: { detail: "You do not have permission to perform this action." } } })).toBe(false);
  expect(isLoginExpired({ response: { status: 403 } })).toBe(false);
  expect(isLoginExpired({ response: { status: 500, data: { detail: "Authentication credentials were not provided." } } })).toBe(false);
  expect(isLoginExpired(new Error("Network Error"))).toBe(false);
  expect(isLoginExpired(null)).toBe(false);
});

test("sending to login remembers the page, goes once, and the path is handed back once", () => {
  const go = jest.fn();
  const saved = loginRedirect.go;
  loginRedirect.go = go;
  try {
    window.history.pushState({}, "", "/reports/closed-loop/abc?x=1");
    sendToLogin();
    sendToLogin();   // several panels fail together: one redirect
    expect(go).toHaveBeenCalledTimes(1);
    expect(go).toHaveBeenCalledWith("/login");
    expect(window.sessionStorage.getItem(RETURN_KEY)).toBe("/reports/closed-loop/abc?x=1");
    expect(takeReturnPath()).toBe("/reports/closed-loop/abc?x=1");
    expect(takeReturnPath()).toBe(null);
  } finally {
    loginRedirect.go = saved;
    loginRedirect.reset();
  }
});

test("a remembered path that is not this site's own page is ignored", () => {
  window.sessionStorage.setItem(RETURN_KEY, "https://elsewhere.example/x");
  expect(takeReturnPath()).toBe(null);
  window.sessionStorage.setItem(RETURN_KEY, "//elsewhere.example/x");
  expect(takeReturnPath()).toBe(null);
  window.sessionStorage.setItem(RETURN_KEY, "/login");
  expect(takeReturnPath()).toBe(null);
});
