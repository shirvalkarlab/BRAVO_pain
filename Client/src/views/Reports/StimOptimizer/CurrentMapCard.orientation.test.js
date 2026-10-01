/**
 * The current map's squares put each predicted rating at its own (left current, right current).
 *
 * The server sends `surface.mu[i][j]` for LEFT current `amps_mA[i]` and RIGHT current `amps_mA[j]`
 * (`stage1_openloop._fit_rate_stratum`: a meshgrid over (rate, left, right) with indexing "ij",
 * serialised row by row). Plotly draws `z[row][col]` at x = x[col], y = y[row], and the square's x
 * axis is the left current. So the drawn z must be the server's grid transposed. From 2026-09-14
 * (3779bfb8) to 2026-09-26 it was passed unchanged, which drew every map mirrored across its
 * diagonal: on RCS08's clinic 60/160 us 55 Hz map, the square showed 1.93 at (left 2.25, right 3.5
 * mA) where the fit predicts 1.01. A deliberately asymmetric surface pins the orientation.
 */
import "@testing-library/jest-dom";
import { render as rtlRender, screen, fireEvent } from "@testing-library/react";
import { ThemeProvider } from "@mui/material/styles";
import theme from "assets/theme";
import { PlatformContextProvider } from "context";
import Plotly from "plotly.js-dist";
import CurrentMapCard from "./CurrentMapCard";
import response from "./__fixtures__/rcs08_stim_optimizer_two_stage.json";

jest.mock("plotly.js-dist", () => {
  const noop = () => {};
  return { react: jest.fn(() => Promise.resolve()), purge: noop, restyle: noop, relayout: noop, newPlot: noop };
});

const wrap = (ui) => (
  <ThemeProvider theme={theme}>
    <PlatformContextProvider initialStates={{ darkMode: false }}>{ui}</PlatformContextProvider>
  </ThemeProvider>
);

// Left index i counts in tens and right index j in ones, so mu[i][j] names its own cell.
function asymmetricPlan() {
  const base = response.two_stage;
  const rows = base.stage1.rate_strata.map((r) => {
    if (!r.fitted || !r.surface) return r;
    const n = r.surface.amps_mA.length;
    const mu = Array.from({ length: n }, (_, i) => Array.from({ length: n }, (__, j) => 10 * i + j));
    const safe = Array.from({ length: n }, () => Array.from({ length: n }, () => true));
    return { ...r, surface: { ...r.surface, mu, safe, pain_reference: 0 } };
  });
  return { ...base, stage1: { ...base.stage1, rate_strata: rows } };
}

// The map's section starts closed and its squares are drawn only once it has been opened (speed-up
// item C5, 2026-10-01), so each test opens it the way a reader does before reading the drawing.
const openMap = () => fireEvent.click(screen.getByRole("button", { name: /Where have currents been tried/ }));

describe("CurrentMapCard: the predicted rating is drawn at its own left and right current", () => {
  beforeEach(() => Plotly.react.mockClear());

  it("draws the server's mu[left][right] at x = left current, y = right current", () => {
    const plan = asymmetricPlan();
    rtlRender(wrap(<CurrentMapCard plan={plan} />));
    openMap();
    // the home-survey squares only (div ids "cms-surface-..."); the clinic squares keep their data
    const heatmaps = Plotly.react.mock.calls
      .filter((c) => /^cms-surface-/.test(c[0]))
      .map((c) => c[1] && c[1][0])
      .filter((t) => t && t.type === "heatmap");
    expect(heatmaps.length).toBeGreaterThan(0);
    heatmaps.forEach((t) => {
      const n = t.x.length;
      // row index = y (right current), column index = x (left current)
      for (let row = 0; row < n; row += 1) {
        for (let col = 0; col < n; col += 1) {
          expect(t.z[row][col]).toBe(10 * col + row);
        }
      }
    });
  });

  it("puts one off-diagonal cell where its currents say (left 0 mA, right the top current)", () => {
    const plan = asymmetricPlan();
    rtlRender(wrap(<CurrentMapCard plan={plan} />));
    openMap();
    const t = Plotly.react.mock.calls.filter((c) => /^cms-surface-/.test(c[0]))
      .map((c) => c[1] && c[1][0]).find((x) => x && x.type === "heatmap");
    const n = t.x.length;
    // server: left index 0, right index n-1 -> 10*0 + (n-1)
    expect(t.x[0]).toBe(t.y[0]);
    expect(t.z[n - 1][0]).toBe(n - 1);          // y = right top, x = left 0
    expect(t.z[0][n - 1]).toBe(10 * (n - 1));   // y = right 0, x = left top
  });
});
