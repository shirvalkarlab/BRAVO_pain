import { isObservedValue } from "./observedValues";

test("zero pain and activity scores are retained while missing readings are omitted", () => {
  expect([0, 4, null, undefined, NaN, Infinity, ""].filter(isObservedValue)).toEqual([0, 4]);
});
