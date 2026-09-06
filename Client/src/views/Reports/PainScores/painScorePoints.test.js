import { pointTimeMs, inActiveStage } from "./painScorePoints";

test("authoritative epochs override ambiguous display strings and preserve midnight UTC", () => {
  expect(pointTimeMs({ t_epoch: 1752620400, t: "2025-07-16 00:00:00" })).toBe(1752620400000);
  expect(pointTimeMs({ t: "2025-07-16 00:00:00" })).toBe(Date.UTC(2025, 6, 16));
  expect(pointTimeMs({ t: "2025-07-16T00:00:00-07:00" })).toBe(Date.UTC(2025, 6, 16, 7));
});
test("stage filtering uses UTC boundaries and rejects malformed points", () => {
  const stages = [{ key: "stage1", start: "2025-07-16 00:00:00", end: "2025-08-21 00:00:00" }];
  expect(inActiveStage(Date.UTC(2025, 6, 16), stages, [])).toBe(false);
  expect(inActiveStage(Date.UTC(2025, 7, 21), stages, [])).toBe(true);
  expect(inActiveStage(Date.UTC(2025, 6, 16), stages, ["stage1"])).toBe(true);
  expect(inActiveStage(pointTimeMs({ t: "invalid" }), stages, null)).toBe(false);
});

test("missing or whitespace-only timestamps remain missing rather than becoming epoch zero", () => {
  for (const point of [null, undefined, {}, { t: "  " }, { t: 0 }, { t_epoch: NaN }, { t_epoch: Infinity }]) {
    expect(Number.isNaN(pointTimeMs(point))).toBe(true);
  }
  expect(pointTimeMs({ t_epoch: 0 })).toBe(0);
  expect(pointTimeMs({ t_epoch: null, t: "2025-07-16T00:00:00Z" })).toBe(Date.UTC(2025, 6, 16));
});
test("valid observations remain visible when no stage map is supplied", () => {
  expect(inActiveStage(Date.UTC(2025, 6, 16), undefined, [])).toBe(true);
  expect(inActiveStage(Date.UTC(2025, 6, 16), null, null)).toBe(true);
});
