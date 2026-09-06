import { CL, CLOSED_LOOP_SLOTS, markClosedLoopFamilyStale, recomputeClosedLoop, recomputeSlots } from "./moduleCacheKeys";
import { invalidate, markUpstreamChanged } from "database/resultCache";
import { refreshServerIdentity } from "database/useCachedResult";
jest.mock("database/resultCache", () => ({ MODULES: { closedLoop: "closedLoop" }, invalidate: jest.fn(), markUpstreamChanged: jest.fn() }));
jest.mock("database/useCachedResult", () => ({ refreshServerIdentity: jest.fn() }));
beforeEach(() => { jest.clearAllMocks(); refreshServerIdentity.mockResolvedValue({}); });
test("family keeps separate canonical slots and marks every panel stale", () => {
  expect(new Set(CLOSED_LOOP_SLOTS).size).toBe(7); expect(CL.report).toBe("closedLoop");
  markClosedLoopFamilyStale("p", "new band");
  for (const key of CLOSED_LOOP_SLOTS) expect(markUpstreamChanged).toHaveBeenCalledWith(key, "p", "new band");
});
test("family recompute waits for identity validation before publishing invalidation", async () => {
  let resolve; refreshServerIdentity.mockReturnValue(new Promise((r) => { resolve = r; }));
  const pending = recomputeClosedLoop("p"); expect(invalidate).not.toHaveBeenCalled();
  resolve({}); await pending;
  expect(refreshServerIdentity).toHaveBeenCalledWith("p"); expect(invalidate).toHaveBeenCalledTimes(7);
});
test("failed identity validation cannot start analysis recomputation", async () => {
  refreshServerIdentity.mockRejectedValue(new Error("denied"));
  await expect(recomputeSlots("p", [CL.report])).rejects.toThrow("denied");
  expect(invalidate).not.toHaveBeenCalled();
});
test("empty recompute selection performs validation without invalidating a module", async () => {
  await recomputeSlots("p"); expect(invalidate).not.toHaveBeenCalled();
});
