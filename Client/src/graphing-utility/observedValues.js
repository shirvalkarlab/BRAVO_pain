// A score of zero is an observation; absent and non-finite values are not.
export const isObservedValue = (value) => value !== null && value !== undefined && value !== "" &&
  (typeof value !== "number" || Number.isFinite(value));
