import { retryOnGatewayError, isRetryableRead } from "./retryOnGatewayError";

const gateway = (s) => Object.assign(new Error("bad gateway"), { response: { status: s } });

test("a read that gets a 502 is sent once more and the second answer is returned", async () => {
  const send = jest.fn().mockRejectedValueOnce(gateway(502)).mockResolvedValueOnce({ data: 1 });
  await expect(retryOnGatewayError("/api/queryStimOptimizer", send, 1)).resolves.toEqual({ data: 1 });
  expect(send).toHaveBeenCalledTimes(2);
});

test("a second failure is raised, not retried again", async () => {
  const send = jest.fn().mockRejectedValue(gateway(503));
  await expect(retryOnGatewayError("/api/queryStimOptimizer", send, 1)).rejects.toBeTruthy();
  expect(send).toHaveBeenCalledTimes(2);
});

test("a server error (500) or a 404 is never retried", async () => {
  const send = jest.fn().mockRejectedValue(gateway(500));
  await expect(retryOnGatewayError("/api/queryStimOptimizer", send, 1)).rejects.toBeTruthy();
  expect(send).toHaveBeenCalledTimes(1);
});

test("a write is never retried, even on a 502", async () => {
  const send = jest.fn().mockRejectedValue(gateway(502));
  await expect(retryOnGatewayError("/api/updateSessions", send, 1)).rejects.toBeTruthy();
  expect(send).toHaveBeenCalledTimes(1);
  expect(isRetryableRead("/api/queryClosedLoopChosenBand")).toBe(true);
});
