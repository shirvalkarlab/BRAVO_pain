import { screenedLine } from "./ClosedLoopChecks";

test("all combinations unbuilt reads 'none of N', not a count that looks like a subset", () => {
  expect(screenedLine({ n_cells_screened: 12, n_cells_unbuildable: 12,
    unbuildable_reasons: { "no recording at the frozen rate": 12 } }))
    .toBe("none of 12 combinations could be built (no recording at the frozen rate)");
});

test("some unbuilt keeps both counts and names the commonest reason", () => {
  expect(screenedLine({ n_cells_screened: 12, n_cells_unbuildable: 5,
    unbuildable_reasons: { "too few readings": 3, "no recording": 2 } }))
    .toBe("12 combinations screened, 5 could not be built (too few readings, +1 more)");
});

test("nothing reported gives an empty line", () => {
  expect(screenedLine({})).toBe("");
});
