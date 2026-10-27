/**
 * Shared set-up for the whole Closed-Loop page tests (`views/Reports/ClosedLoopSim/ClosedLoopPage.*.test.js`; 2026-10-05, when
 * the page tests were consolidated). Each test file still mocks its own modules and answers its own
 * requests; this holds what every one of them repeated. Not a test file: jest collects only `*.test.js`.
 */
import { render, act } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { wrap } from "testUtils/render";
import ClosedLoopSim from "views/Reports/ClosedLoopSim";

/** The band chosen on the Biomarkers page, as the browser keeps it: L 1-3+ at 24.5 Hz. */
export const LOCAL_BC = { contact: "ONE_THREE_LEFT", contact_label: "L 1-3+", center_freq_hz: 24.5, bandwidth_hz: 5,
  hemisphere: "Left", threshold_mode: "dual", schema_version: "bandcandidate_v1" };

/** A stand-in server answer: `{ data }` after `ms` milliseconds. */
export const answer = (data, ms) => new Promise((resolve) => setTimeout(() => resolve({ data }), ms));

/** Let the page run for n * 100 ms of real time, inside act. */
export const settle = async (n = 30) => {
  for (let i = 0; i < n; i += 1) {
    // eslint-disable-next-line no-await-in-loop
    await act(() => new Promise((r) => setTimeout(r, 100)));
  }
};

/** The real Closed-Loop page at /reports/closedloop/<uid>, inside the app's theme. */
export const renderClosedLoopPage = (uid) => render(wrap(
  <MemoryRouter initialEntries={[`/reports/closedloop/${uid}`]}>
    <Routes>
      <Route path="/reports/closedloop/:participant_uid" element={<ClosedLoopSim />} />
    </Routes>
  </MemoryRouter>));
