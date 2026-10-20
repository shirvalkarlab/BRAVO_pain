/**
 * The two-stage plan is requested AT THE SAME TIME as the page's own Stim Optimizer request, not
 * after it (speed-up item C2, 2026-10-01). The two are stored as separate answers and computed in
 * separate web workers, so waiting for the first only added the second's whole computing time to
 * the page's wait whenever neither was saved yet.
 */
import { render } from "@testing-library/react";

const calls = [];
jest.mock("database/useCachedResult", () => ({
  useCachedResult: (opts) => {
    calls.push(opts);
    return { data: null, loading: false, err: null, stale: false, recompute: () => {} };
  },
}));
jest.mock("database/session-control", () => ({ SessionController: { query: jest.fn() } }));

// eslint-disable-next-line import/first
import useTwoStagePlan from "./useTwoStagePlan";

beforeEach(() => { calls.length = 0; });

function Probe(props) { useTwoStagePlan(props); return null; }
const renderHook = (props) => render(<Probe {...props} />);

it("asks for the plan before the page's own answer has arrived", () => {
  renderHook({ participantUid: "p1", baseRequest: { A: 1 } });
  expect(calls[calls.length - 1].enabled).toBe(true);
  expect(calls[calls.length - 1].settings).toEqual({ A: 1, TwoStage: true });
});

it("asks for nothing without a participant, or when the page turns it off", () => {
  renderHook({ participantUid: null, baseRequest: {} });
  expect(calls[calls.length - 1].enabled).toBe(false);
  renderHook({ participantUid: "p1", baseRequest: {}, enabled: false });
  expect(calls[calls.length - 1].enabled).toBe(false);
});
