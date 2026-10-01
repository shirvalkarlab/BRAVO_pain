/**
 * Which Left contact and rate to test at the next clinic visit (step C; the PI, 2026-10-01: "yes
 * show both lists on the page"). The server ranks every (Left contact, rate) block most promising
 * first; blocks with too few stretches to predict tie at the top. The card shows the two lists
 * apart: the tied, untested contacts as one list, the measured blocks ranked below it.
 */
import "@testing-library/jest-dom";
import { render, screen, within } from "@testing-library/react";
import { ThemeProvider } from "@mui/material/styles";
import theme from "assets/theme";
import { PlatformContextProvider } from "context";
import NextBlocksCard, { splitBlocks } from "./NextBlocksCard";

const wrap = (ui) => (
  <ThemeProvider theme={theme}>
    <PlatformContextProvider initialStates={{ language: "en", user: {} }}>{ui}</PlatformContextProvider>
  </ThemeProvider>
);

const PRIOR = "no surface: the stream's own spread";
const BORROWED = "borrowed across rates and pulse widths: this contact's own clinic stretches, read at the pulse widths in force; limited by the maxima only";
const nb = {
  available: true, n_tied_at_top: 3, prior_sd: 1.39, k_sd: 2.0,
  pulse_widths_us: { Left: 100, Right: 150 },
  ranking_note: "3 blocks tie at the top with the same plausible improvement (2.78 NRS points); the model cannot rank them, so it offers no single next block",
  blocks: [
    { rank: 1, left_contact: "L C+1-2-", rate_hz: 55, basis: PRIOR, optimistic_improvement: 2.78, predicted_improvement: 0, amp_mA_left: null, amp_mA_right: null, n_stretches: 0 },
    { rank: 2, left_contact: "L C+1-2-", rate_hz: 110, basis: PRIOR, optimistic_improvement: 2.78, predicted_improvement: 0, amp_mA_left: null, amp_mA_right: null, n_stretches: 0 },
    { rank: 3, left_contact: "L C+2a-", rate_hz: 55, basis: PRIOR, optimistic_improvement: 2.78, predicted_improvement: 0, amp_mA_left: null, amp_mA_right: null, n_stretches: 0 },
    { rank: 4, left_contact: "L 1+2-", rate_hz: 85, basis: BORROWED, optimistic_improvement: 1.11, predicted_improvement: -0.74, amp_mA_left: 1.75, amp_mA_right: 1.75, n_stretches: 20 },
    { rank: 5, left_contact: "L C+2-", rate_hz: 55, basis: "fitted surface", optimistic_improvement: 0.61, predicted_improvement: 0.55, amp_mA_left: 3.5, amp_mA_right: 3.0, n_stretches: 10 },
  ],
};

test("the tied blocks are grouped by contact and the measured ones keep their rank order", () => {
  const { tied, measured } = splitBlocks(nb);
  expect(tied).toEqual([{ contact: "L C+1-2-", rates: [55, 110] }, { contact: "L C+2a-", rates: [55] }]);
  expect(measured.map((b) => b.left_contact)).toEqual(["L 1+2-", "L C+2-"]);
});

test("the card shows both lists, the tie said in plain words, and each measured row's source", () => {
  render(wrap(<NextBlocksCard nextBlocks={nb} />));
  const tied = screen.getByTestId("next-blocks-tied");
  expect(within(tied).getByText(/L C\+1-2-/)).toBeInTheDocument();
  expect(within(tied).getByText(/55 and 110 Hz/)).toBeInTheDocument();
  const measured = screen.getByTestId("next-blocks-measured");
  const rows = within(measured).getAllByRole("row").slice(1);
  expect(rows).toHaveLength(2);
  expect(rows[0]).toHaveTextContent("L 1+2-");
  expect(rows[0]).toHaveTextContent("0.74 worse");
  expect(rows[0]).toHaveTextContent("borrowed from other rates and pulse widths");
  expect(rows[1]).toHaveTextContent("0.55 better");
  expect(rows[1]).toHaveTextContent("its own surface");
  expect(screen.getByText(/cannot rank/)).toBeInTheDocument();
});

test("nothing is drawn when the response carries no ranking", () => {
  render(wrap(<NextBlocksCard nextBlocks={null} />));
  expect(screen.queryByTestId("next-blocks-card")).toBeNull();
});

test("each Left contact's exposure in the clinic sheets is said, planned-only steps apart", () => {
  const withExposure = { ...nb, exposure: {
    "L C+1-2-": { left_contact: "L C+1-2-", n_steps: 26, n_rated: 22, amp_min_mA: 0.5, amp_max_mA: 2.5, n_visits: 3, n_planned_only: 14 },
    "off (Left 0 mA)": { left_contact: "off (Left 0 mA)", n_steps: 100, n_rated: 60, amp_min_mA: null, amp_max_mA: null, n_visits: 20, n_planned_only: 0 },
  } };
  render(wrap(<NextBlocksCard nextBlocks={withExposure} />));
  const ex = screen.getByTestId("next-blocks-exposure");
  expect(ex).toHaveTextContent("L C+1-2-: 26 steps at 0.5–2.5 mA over 3 visits, 22 rated; 14 more planned but never recorded as given");
  expect(ex).not.toHaveTextContent("off (Left 0 mA)");
});
