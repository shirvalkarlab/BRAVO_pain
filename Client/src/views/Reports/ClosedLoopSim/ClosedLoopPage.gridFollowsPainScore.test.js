/**
 * The band grid follows the page's pain-score dropdown (the PI, 2026-10-04: "The band grid on the
 * closed-loop module should update when a different pain score is selected in the dropdown. That's
 * the whole point."). Until this test the grid asked for the Biomarkers page's last score whatever
 * the dropdown said, so its bands stayed fixed. The real page, stand-in answers: choose another score
 * and the grid is asked for again under it, keeping the Biomarkers page's matching settings.
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
    if (url === "/api/queryDeploymentSummary") return answer(SUMMARY, 5);
    if (url === "/api/queryClosedLoopDeployment") {
      if ((body.Candidates || []).length === 0) return answer({ band_sweep_grid: FULL.band_sweep_grid }, 5);
      return answer(REPORT, 5);
    }
    return answer({}, 1);
  });
});

const gridAsks = () => asked.filter((a) => a.url === "/api/queryClosedLoopDeployment"
  && !(a.body.Candidates || []).length && !a.body.ThreeSourcePooled && !a.body.ClosedLoopSimulation);
const settle = async (n = 30) => {
  for (let i = 0; i < n; i += 1) {
    // eslint-disable-next-line no-await-in-loop
    await act(() => new Promise((r) => setTimeout(r, 100)));
  }
};

it("asks for the grid again under the score chosen in the dropdown", async () => {
  const uid = "GRIDSCORE";
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
  const before = gridAsks().length;
  expect(before).toBeGreaterThan(0);
  expect(gridAsks()[before - 1].body.LabelMetric || "nrs").toBe("nrs");

  // Found directly: a role query over this whole page takes minutes.
  const labelled = document.querySelector('[aria-label^="Pain score"]');
  expect(labelled).not.toBeNull();
  const select = labelled.closest(".MuiInputBase-root").querySelector(".MuiSelect-select");
  await act(async () => { fireEvent.mouseDown(select); });
  const option = Array.from(document.querySelectorAll('li[role="option"]'))
    .find((li) => li.textContent === "Left Leg VAS");
  expect(option).toBeDefined();
  await act(async () => { fireEvent.click(option); });
  await settle();

  const after = gridAsks();
  expect(after.length).toBe(before + 1);
  expect(after[after.length - 1].body).toMatchObject({ LabelMetric: "left_leg_vas",
    SweepMetric: "left_leg_vas", MatchToleranceMin: 15, MatchDirection: "nearest" });
});
