import { timelinePoints, timelineChannelUnit } from "./timelinePoints";
const millis = (values) => values.map((v) => v === null ? null : v.getTime());
test("zero intervals survive, gaps stay separated, unknown final duration is a point", () => {
  const result = timelinePoints([10, 20, 30, 40], [0, null, 3, 0], [5, 5, 5, null]);
  expect(millis(result.line.x)).toEqual([10000, 15000, null, 30000, 35000, null]);
  expect(result.line.y).toEqual([0, 0, null, 3, 3, null]);
  expect(millis(result.points.x)).toEqual([40000]);
  expect(result.points.y).toEqual([0]);
});
test("scalar durations never connect disjoint intervals", () => {
  const { line, points } = timelinePoints([10, 100], [2, -3], 5);
  expect(millis(line.x)).toEqual([10000, 15000, null, 100000, 105000, null]);
  expect(line.y).toEqual([2, 2, null, -3, -3, null]);
  expect(points.y).toEqual([]);
});
test("old N-1 duration payload keeps final observation without inventing interval", () => {
  const result = timelinePoints([10, 20], [4, 0], [10]);
  expect(result.points.y).toEqual([0]);
  expect(millis(result.points.x)).toEqual([20000]);
});
test.each([undefined, null, [], 0, -1, Infinity, [NaN], ["10"], [0], [-1], [Infinity], [1e100]])("unknown or invalid duration %p remains a point", (duration) => {
  const result = timelinePoints([10], [0], duration);
  expect(result.line.y).toEqual([]);
  expect(result.points.y).toEqual([0]);
});
test("invalid times/values excluded while zero/negative survey points survive", () => {
  const result = timelinePoints([0, 1, 2, 3, 4, 5, null, NaN, Infinity, 1e100], [0, -2, null, undefined, "3", Infinity, 2, 2, 2, 2]);
  expect(result.line.y).toEqual([]);
  expect(result.points.y).toEqual([0, -2]);
  expect(millis(result.points.x)).toEqual([0, 1000]);
});
test("empty input creates no traces", () => {
  expect(timelinePoints([], [])).toEqual({ line: { x: [], y: [] }, points: { x: [], y: [] } });
});
test("channel units preserve mA without inventing unknown or conflicting labels", () => {
  const a = { ChannelNames: ["power", "stim", "sleep"], ChannelUnits: ["", "mA", "Category"] };
  expect(timelineChannelUnit([a], "stim")).toBe("mA");
  expect(timelineChannelUnit([a], "power")).toBe("");
  expect(timelineChannelUnit([a], "sleep")).toBe("");
  expect(timelineChannelUnit([a], "missing")).toBe("");
  expect(timelineChannelUnit([{ ChannelNames: ["stim"] }], "stim")).toBe("");
  expect(timelineChannelUnit([a, { ChannelNames: ["stim"], ChannelUnits: ["V"] }], "stim")).toBe("");
  expect(timelineChannelUnit([a, a], "stim")).toBe("mA");
});
