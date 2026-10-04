/**
 * Choosing a band on the grid computes that band (the PI, 2026-10-04, after decision 416: "I changed
 * the band to a new band and it gives me stale notice"). The page's result cache never fetches on a
 * changed request by itself -- it shows the held answer marked stale and waits for Recompute -- so a
 * new band landed on the previous band's answers, marked stale, every time. Choosing a band is the
 * reader's explicit act, so it now counts as Recompute for every answer that depends on the band
 * (the report, the summary, the ROC, the band-power and per-era panels, the simulation), never for
 * the grid or the pooled three-source view, and the pain score and the ROC's settings start again
 * from the new band's defaults.
 */
import { fireEvent } from "@testing-library/react";
import "@testing-library/jest-dom";
import { render, act } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { ThemeProvider } from "@mui/material/styles";

import theme from "assets/theme";
import { PlatformContextProvider } from "context";

jest.mock("plotly.js-dist", () => {
  const mark = (gd) => {
    if (gd && gd.classList) { gd.classList.add("js-plotly-plot"); gd._fullLayout = { width: 700, height: 300 }; }
    return Promise.resolve(gd);
  };
  // Plain functions, not jest.fn: the test setup resets every jest.fn's behaviour before each test.
  return {
    react: mark, newPlot: mark, purge: () => {}, restyle: () => Promise.resolve(),
    relayout: () => Promise.resolve(), toImage: () => Promise.resolve("data:image/png;base64,AAAA"),
  };
});
jest.mock("database/session-control", () => ({ SessionController: { query: jest.fn() } }));
jest.mock("layouts/DatabaseLayout", () => ({ children }) => <div>{children}</div>);

// eslint-disable-next-line import/first
import { SessionController } from "database/session-control";
// eslint-disable-next-line import/first
import { invalidateAll } from "database/resultCache";
// eslint-disable-next-line import/first
import ClosedLoopSim from "./index";
// eslint-disable-next-line import/first
import REPORT from "./__fixtures__/rcs08_cl_L13_24p5_2026-09-25.json";
// eslint-disable-next-line import/first
import SUMMARY from "./__fixtures__/rcs08_summary_L13_24p5_2026-09-25.json";
// eslint-disable-next-line import/first
import FULL from "./__fixtures__/rcs08_deployment_payload_2026-09-15.json";


const LOCAL_BC = { contact: "ONE_THREE_LEFT", contact_label: "L 1-3+", center_freq_hz: 24.5, bandwidth_hz: 5,
  hemisphere: "Left", threshold_mode: "dual", schema_version: "bandcandidate_v1" };
const answer = (data, ms) => new Promise((resolve) => setTimeout(() => resolve({ data }), ms));

let asked;
beforeEach(() => {
  invalidateAll("test setup");
  window.localStorage.clear();
  asked = [];
  SessionController.query.mockReset();
  SessionController.query.mockImplementation((url, body) => {
    asked.push({ url, body });
    if (url === "/api/queryServerIdentity") return answer({ boot_token: "t" }, 1);
    if (url === "/api/queryParticipantInformation") return answer({ Name: "RCS08" }, 2);
    if (url === "/api/queryClosedLoopChosenBand") {
      return answer({ available: true, record: { band_candidate: LOCAL_BC, committed_at: 2 } }, 5);
    }
    if (url === "/api/recordClosedLoopChosenBand" || /ChosenBand/.test(url)) {
      return answer({ available: true, recorded: true }, 2);
    }
    // The stand-in server answers for the band it was asked about, as the real one does.
    if (url === "/api/queryDeploymentSummary") {
      return answer({ ...SUMMARY, identity: { ...SUMMARY.identity, contact: body.Channel,
        center_freq_hz: Number(body.CenterHz) } }, 5);
    }
    if (url === "/api/queryClosedLoopDeployment") {
      if ((body.Candidates || []).length === 0) return answer({ band_sweep_grid: FULL.band_sweep_grid }, 5);
      const c = body.Candidates[0];
      return answer({ ...REPORT, candidates: [{ ...(REPORT.candidates || [{}])[0], channel: c.channel,
        center_hz: c.center_hz }] }, 5);
    }
    return answer({}, 1);
  });
});

const settle = async (n = 30) => {
  for (let i = 0; i < n; i += 1) {
    // eslint-disable-next-line no-await-in-loop
    await act(() => new Promise((r) => setTimeout(r, 100)));
  }
};
const reportAsks = () => asked.filter((a) => a.url === "/api/queryClosedLoopDeployment"
  && (a.body.Candidates || []).length && !a.body.ClosedLoopSimulation);

it("computes the newly chosen band instead of showing the old one as stale", async () => {
  const uid = "NEWBAND";
  window.localStorage.setItem(`bravo.bandCandidate.${uid}`,
    JSON.stringify({ band_candidate: LOCAL_BC, participant_uid: uid, committed_at: 2 }));
  render(
    <ThemeProvider theme={theme}>
      <PlatformContextProvider initialStates={{ darkMode: false }}>
        <MemoryRouter initialEntries={[`/reports/closedloop/${uid}`]}>
          <Routes>
            <Route path="/reports/closedloop/:participant_uid" element={<ClosedLoopSim />} />
          </Routes>
        </MemoryRouter>
      </PlatformContextProvider>
    </ThemeProvider>);
  await settle();
  const gridsBefore = asked.filter((a) => a.url === "/api/queryClosedLoopDeployment"
    && !(a.body.Candidates || []).length && !a.body.ThreeSourcePooled).length;
  const reportsBefore = reportAsks().length;
  const summariesBefore = asked.filter((a) => a.url === "/api/queryDeploymentSummary").length;

  // another band on the same contact's tab: the first radio that is not the chosen one
  const radios = Array.from(document.querySelectorAll('input[type="radio"][name^="cl-use-band-"]'));
  const other = radios.find((r) => !r.checked);
  expect(other).toBeDefined();
  await act(async () => { fireEvent.click(other); });
  await settle();

  // the chosen band's own requests come first; the neighbours' (decision 425) follow once they are in
  const newReports = reportAsks().slice(reportsBefore);
  const cand = newReports[0].body.Candidates[0];
  expect(cand.center_hz).not.toBe(LOCAL_BC.center_freq_hz);
  expect(newReports.filter((a) => a.body.Candidates[0].center_hz === cand.center_hz).length).toBe(1);
  const newSummaries = asked.filter((a) => a.url === "/api/queryDeploymentSummary").slice(summariesBefore);
  expect(Number(newSummaries[0].body.CenterHz)).toBe(cand.center_hz);
  expect(newSummaries.filter((a) => Number(a.body.CenterHz) === cand.center_hz).length).toBe(1);
  expect(asked.filter((a) => a.url === "/api/queryClosedLoopDeployment"
    && !(a.body.Candidates || []).length && !a.body.ThreeSourcePooled).length).toBe(gridsBefore);
  expect(document.body.textContent).not.toMatch(/settings have changed since/);
  expect(document.body.textContent).not.toMatch(/not the chosen band/);
});
