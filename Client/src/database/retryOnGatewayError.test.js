import { retryOnGatewayError, isRetryableRead } from "./retryOnGatewayError";

const gateway = (status) => Object.assign(new Error("bad gateway"), { response: { status } });
const network = () => Object.assign(new Error("Network Error"), { code: "ERR_NETWORK" });

test.each([502, 503, 504])("a known read retries HTTP %s once and returns the second answer", async (status) => {
  const send = jest.fn().mockRejectedValueOnce(gateway(status)).mockResolvedValueOnce({ data: 1 });
  await expect(retryOnGatewayError("/api/queryStimOptimizer", send, 1)).resolves.toEqual({ data: 1 });
  expect(send).toHaveBeenCalledTimes(2);
});

test.each(["/api/queryRedcapTimeline", "/api/queryOuraTimeline", "/api/queryHomeNeuralTimeline",
  "/api/queryServerIdentity", "/api/queryStimProgram", "/api/queryControlAnalyses",
  "/api/queryBiomarkerAnalysis", "/api/queryClosedLoopDeployment", "/api/queryDeploymentSummary",
  "/api/queryDeploymentROC", "/api/queryDeploymentRocByEra", "/api/queryLsbPower",
  "/api/queryWiringComparison"])("known read %s recovers from a statusless network failure", async (url) => {
  const send = jest.fn().mockRejectedValueOnce(network()).mockResolvedValueOnce("recovered");
  await expect(retryOnGatewayError(url, send, 1, { ParticipantId: "synthetic" })).resolves.toBe("recovered");
  expect(send).toHaveBeenCalledTimes(2);
});

test.each([network(), gateway(503)])("a second failure is raised, not retried again (%p)", async (error) => {
  const send = jest.fn().mockRejectedValue(error);
  await expect(retryOnGatewayError("/api/queryClosedLoopDeployment", send, 1)).rejects.toBe(error);
  expect(send).toHaveBeenCalledTimes(2);
});

test.each(["/api/queryRedcapTimeline", "/api/queryClosedLoopDeployment"])(
  "the installed XHR adapter's status-zero ERR_NETWORK recovers once for %s", async (url) => {
    const error = Object.assign(network(), { response: { status: 0 }, __CANCEL__: false });
    const send = jest.fn().mockRejectedValueOnce(error).mockResolvedValue("recovered");
    await expect(retryOnGatewayError(url, send, 1, {})).resolves.toBe("recovered");
    expect(send).toHaveBeenCalledTimes(2);
  });

test.each([null, new Error("unknown failure"), gateway(400), gateway(401), gateway(403), gateway(404), gateway(500),
  { code: "ERR_NETWORK", response: { status: 403 } }, { code: "ERR_NETWORK", response: { status: 500 } },
  { response: { status: 0 } }, { code: "ERR_BAD_RESPONSE", response: { status: 0 } },
  { code: "ERR_NETWORK", response: {} },
  { code: "ERR_NETWORK", __CANCEL__: true }, { code: "ERR_CANCELED" }, { code: "ECONNABORTED" },
  { code: "ETIMEDOUT" }, { code: "ECONNABORTED", response: { status: 504 } }])(
  "authentication, application, cancellation and timeout failures are not retried (%p)", async (error) => {
    const send = jest.fn().mockRejectedValue(error);
    await expect(retryOnGatewayError("/api/queryRedcapTimeline", send, 1)).rejects.toBe(error);
    expect(send).toHaveBeenCalledTimes(1);
  });

test.each(["/api/updateSessions", "/api/login", "/api/manualSync", "/api/queryUnreviewedOperation", "",
  undefined, null, "/api/queryRedcapTimeline?other=true", "https://other.test/api/queryRedcapTimeline"])(
  "unknown or write endpoint %p is never retried", async (url) => {
    const error = gateway(502);
    const send = jest.fn().mockRejectedValue(error);
    await expect(retryOnGatewayError(url, send, 1)).rejects.toBe(error);
    expect(send).toHaveBeenCalledTimes(1);
  });

test.each([undefined, null, {}, { Action: "choose" }, { Action: "clear" }, { Action: "unknown" }])(
  "chosen-band writes or unspecified actions never retry (%p)", async (body) => {
    const error = network();
    const send = jest.fn().mockRejectedValue(error);
    await expect(retryOnGatewayError("/api/queryClosedLoopChosenBand", send, 1, body)).rejects.toBe(error);
    expect(send).toHaveBeenCalledTimes(1);
  });

test("chosen-band read is explicitly retryable and does not alter the body", async () => {
  const body = Object.freeze({ ParticipantId: "synthetic", Action: "read" });
  const send = jest.fn().mockRejectedValueOnce(network()).mockResolvedValue("read result");
  await expect(retryOnGatewayError("/api/queryClosedLoopChosenBand", send, 1, body)).resolves.toBe("read result");
  expect(send).toHaveBeenCalledTimes(2);
  expect(isRetryableRead("/api/queryRedcapTimeline", { Action: "choose" })).toBe(false);
  expect(isRetryableRead("/api/queryRedcapTimeline", null)).toBe(true);
});

test("success is returned without waiting or replay", async () => {
  const send = jest.fn().mockResolvedValue("first result");
  await expect(retryOnGatewayError("/api/queryRedcapTimeline", send)).resolves.toBe("first result");
  expect(send).toHaveBeenCalledTimes(1);
});

test("default retry delay is bounded at 1500 milliseconds", async () => {
  jest.useFakeTimers();
  try {
    const send = jest.fn().mockRejectedValueOnce(network()).mockResolvedValue("recovered");
    const result = retryOnGatewayError("/api/queryRedcapTimeline", send);
    for (let i=0;i<5;i+=1) await Promise.resolve();
    expect(jest.getTimerCount()).toBe(1);
    jest.advanceTimersByTime(1499); expect(send).toHaveBeenCalledTimes(1);
    jest.advanceTimersByTime(1);
    await expect(result).resolves.toBe("recovered"); expect(send).toHaveBeenCalledTimes(2);
  } finally { jest.useRealTimers(); }
});

const flushMicrotasks=async()=>{for(let i=0;i<10;i+=1) await Promise.resolve();};

test('a five-second disconnect waits for reconnection before its one safe retry',async()=>{
 jest.useFakeTimers();const connection=jest.spyOn(navigator,'onLine','get').mockReturnValue(false);
 const remove=jest.spyOn(window,'removeEventListener');
 try {
  const send=jest.fn().mockRejectedValueOnce(network()).mockResolvedValue('recovered online');
  const result=retryOnGatewayError('/api/queryRedcapTimeline',send);
  await flushMicrotasks();jest.advanceTimersByTime(1500);await flushMicrotasks();
  expect(send).toHaveBeenCalledTimes(1);
  window.dispatchEvent(new Event('online'));await flushMicrotasks();expect(send).toHaveBeenCalledTimes(1);
  jest.advanceTimersByTime(3500);expect(send).toHaveBeenCalledTimes(1);
  connection.mockReturnValue(true);window.dispatchEvent(new Event('online'));
  await expect(result).resolves.toBe('recovered online');expect(send).toHaveBeenCalledTimes(2);
  expect(remove).toHaveBeenCalledWith('online',expect.any(Function));expect(jest.getTimerCount()).toBe(0);
  window.dispatchEvent(new Event('online'));jest.advanceTimersByTime(20000);expect(send).toHaveBeenCalledTimes(2);
 } finally {connection.mockRestore();remove.mockRestore();jest.useRealTimers();}
});

test('persistent offline failure reaches a terminal error and removes its listener at the deadline',async()=>{
 jest.useFakeTimers();const connection=jest.spyOn(navigator,'onLine','get').mockReturnValue(false);
 const remove=jest.spyOn(window,'removeEventListener');
 try {
  const error=network(),send=jest.fn().mockRejectedValue(error);
  const result=retryOnGatewayError('/api/queryClosedLoopDeployment',send);
  const rejected=expect(result).rejects.toBe(error);
  await flushMicrotasks();jest.advanceTimersByTime(1500);await flushMicrotasks();
  jest.advanceTimersByTime(14999);await flushMicrotasks();expect(send).toHaveBeenCalledTimes(1);
  jest.advanceTimersByTime(1);await rejected;
  expect(remove).toHaveBeenCalledWith('online',expect.any(Function));expect(jest.getTimerCount()).toBe(0);
  connection.mockReturnValue(true);window.dispatchEvent(new Event('online'));await flushMicrotasks();
  expect(send).toHaveBeenCalledTimes(1);
 } finally {connection.mockRestore();remove.mockRestore();jest.useRealTimers();}
});
