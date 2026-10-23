/**
 * Page review 2026-10-02 (item 4.7): 17-20 POSTs to /api/updateSessions on every first load, one per
 * key the page boot copies into the context (index.js) plus the side menu and layout keys. The
 * server keeps only three of them (WebSession.py `defaultSessionConfigs`: language, miniSidenav,
 * darkMode) and drops the rest, yet each POST still reads the processing settings and saves the
 * user. So only those three are sent; every key is still kept in the browser.
 */
import axios from "axios";

jest.mock("axios", () => ({ post: jest.fn(() => Promise.resolve({ data: {} })), get: jest.fn() }));

// eslint-disable-next-line import/first
import { SessionController } from "./session-control";

const posts = () => axios.post.mock.calls.filter(([url]) => String(url).endsWith("/api/updateSessions"));

// react-scripts resets mocks before every test, so the reply is set here, not only in the factory
beforeEach(() => { axios.post.mockReset(); axios.post.mockImplementation(() => Promise.resolve({ data: {} })); });

describe("setSession sends only the keys the server keeps", () => {
  it("a page-only key is kept in the browser and not sent", () => {
    SessionController.setSession("report", "Biomarkers", true);
    SessionController.setSession("hideSidenav", false, true);
    expect(posts()).toHaveLength(0);
    expect(JSON.parse(localStorage.getItem("sessionContext")).report).toBe("Biomarkers");
  });
  it("the three server-kept keys are sent", () => {
    SessionController.setSession("darkMode", true, true);
    SessionController.setSession("language", "en", true);
    SessionController.setSession("miniSidenav", false, true);
    expect(posts()).toHaveLength(3);
  });
  it("nothing is sent when the caller asks for no update", () => {
    SessionController.setSession("darkMode", true, false);
    expect(posts()).toHaveLength(0);
  });
});
