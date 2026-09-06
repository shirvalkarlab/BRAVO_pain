jest.mock("database/session-control", () => ({ SessionController: { query: jest.fn() } }));
jest.mock("database/resultCache", () => ({cacheScope: jest.fn(() => 'test-account')}));
import { createAnalysisClient } from "./queryAnalysis";
import {cacheScope} from 'database/resultCache';
import {SessionController} from 'database/session-control';

const tick = async () => { await Promise.resolve(); await Promise.resolve(); await Promise.resolve(); };
beforeEach(() => {jest.useFakeTimers();cacheScope.mockReturnValue('test-account');SessionController.query.mockReset();});
afterEach(() => jest.useRealTimers());

test("202 is progress, identical requests share polling, completed data is fetched again next visit", async () => {
  const done = { status: 200, data: { InputManifest: { fingerprint: "current" } } };
  const request = jest.fn().mockResolvedValueOnce({ status: 202, data: { status: "running" }, headers: { "retry-after": "3" } })
    .mockResolvedValue(done);
  const client = createAnalysisClient(request);
  const a = client.createScope(), b = client.createScope();
  const p1 = a.query("/api/queryPainScores", { ParticipantId: "pt" });
  const p2 = b.query("/api/queryPainScores", { ParticipantId: "pt" });
  const resolved = jest.fn(); p1.then(resolved);
  await tick(); expect(request).toHaveBeenCalledTimes(1); expect(resolved).not.toHaveBeenCalled();
  jest.advanceTimersByTime(3000); await tick();
  expect(await p1).toBe(done); expect(await p2).toBe(done); expect(request).toHaveBeenCalledTimes(2);
  await a.query("/api/queryPainScores", { ParticipantId: "pt" });
  expect(request).toHaveBeenCalledTimes(3);
});
test("leaving all views stops polling without sending a server cancellation", async () => {
  const request = jest.fn().mockResolvedValue({ status: 202, data: { status: "running" } });
  const scope = createAnalysisClient(request).createScope();
  const resolved = jest.fn(); scope.query("/api/queryStimOptimizer", { ParticipantId: "pt" }).then(resolved);
  await tick(); scope.cancelAll(); jest.advanceTimersByTime(90000); await tick();
  expect(request).toHaveBeenCalledTimes(1); expect(resolved).not.toHaveBeenCalled();
});
test("one subscriber leaving does not stop another, stale participant response cannot replace current data", async () => {
  let finishOld;
  const request = jest.fn().mockImplementationOnce(() => new Promise((resolve) => { finishOld = resolve; }))
    .mockResolvedValue({ status: 200, data: { participant: "new" } });
  const client = createAnalysisClient(request), a = client.createScope(), b = client.createScope();
  const oldA = jest.fn(), oldB = jest.fn();
  a.query("/api/queryPainScores", { ParticipantId: "old" }).then(oldA);
  b.query("/api/queryPainScores", { ParticipantId: "old" }).then(oldB);
  await tick();
  const newResult = a.query("/api/queryPainScores", { ParticipantId: "new" });
  finishOld({ status: 200, data: { participant: "old" } }); await tick();
  expect(oldA).not.toHaveBeenCalled(); expect(oldB).toHaveBeenCalledTimes(1);
  expect((await newResult).data.participant).toBe("new");
});

test("repeated clicks in one view reuse the same pending analysis", async () => {
  const request = jest.fn().mockResolvedValue({ status: 202, data: { status: "running" } });
  const scope = createAnalysisClient(request).createScope();
  const first = scope.query("/api/queryBiomarkerAnalysis", { ParticipantId: "pt", LabelMetric: "nrs" });
  const again = scope.query("/api/queryBiomarkerAnalysis", { LabelMetric: "nrs", ParticipantId: "pt" });
  expect(again).toBe(first); await tick(); expect(request).toHaveBeenCalledTimes(1); scope.cancelAll();
});

test("unsupported endpoints are rejected before any transport call", () => {
  const request = jest.fn();
  expect(() => createAnalysisClient(request).createScope().query("/api/deleteDeviceInformation", {}))
    .toThrow("Unsupported analysis endpoint");
  expect(request).not.toHaveBeenCalled();
});
test("array-valued analysis settings deduplicate by content and progress remains separate from results", async () => {
  const progress = jest.fn();
  const request = jest.fn().mockResolvedValueOnce({ status: 202, data: { message: "Computing" }, headers: { "retry-after": "0.2" } })
    .mockResolvedValue({ status: 200, data: { InputManifest: { fingerprint: "approved" } } });
  const client = createAnalysisClient(request), a = client.createScope(), b = client.createScope();
  const resultA = a.query("/api/queryStimOptimizer", { ParticipantId: "pt", Sites: ["left_leg", "back"] }, progress);
  const resultB = b.query("/api/queryStimOptimizer", { Sites: ["left_leg", "back"], ParticipantId: "pt" });
  await tick(); expect(progress).toHaveBeenCalledWith({ message: "Computing" });
  jest.advanceTimersByTime(999); await tick(); expect(request).toHaveBeenCalledTimes(1);
  jest.advanceTimersByTime(1); await tick();
  expect((await resultA).data.InputManifest.fingerprint).toBe("approved");
  expect(await resultB).toEqual(await resultA);
});
test("a cancelled queued request never starts, and cancelling a nonexistent endpoint is harmless", async () => {
  const request = jest.fn(); const scope = createAnalysisClient(request).createScope();
  scope.query("/api/queryPainScores", { ParticipantId: "pt" });
  scope.cancel("/api/queryPainScores"); scope.cancel("/api/queryPainScores");
  await tick(); expect(request).not.toHaveBeenCalled();
});
test("late completion of an abandoned request cannot evict a new identical subscription", async () => {
  let finishOld;
  const done = { status: 200, data: { InputManifest: { fingerprint: "fresh" } } };
  const request = jest.fn().mockImplementationOnce(() => new Promise(resolve => { finishOld = resolve; }))
    .mockResolvedValueOnce({ status: 202, data: { status: "running" } }).mockResolvedValue(done);
  const scope = createAnalysisClient(request).createScope();
  const oldSuccess = jest.fn(); scope.query("/api/queryPainScores", { ParticipantId: "pt" }).then(oldSuccess);
  await tick(); scope.cancel("/api/queryPainScores");
  const fresh = scope.query("/api/queryPainScores", { ParticipantId: "pt" });
  await tick(); finishOld({ status: 200, data: { InputManifest: { fingerprint: "old" } } }); await tick();
  expect(oldSuccess).not.toHaveBeenCalled();
  jest.advanceTimersByTime(3000); await tick(); expect(await fresh).toBe(done);
  expect(request).toHaveBeenCalledTimes(3);
});
test("transport errors reach active subscribers and a retry uses a fresh request", async () => {
  const error = new Error("network failure");
  const request = jest.fn().mockRejectedValueOnce(error).mockResolvedValueOnce({ status: 200, data: {} });
  const scope = createAnalysisClient(request).createScope();
  await expect(scope.query("/api/queryPainScores", { ParticipantId: "pt" })).rejects.toBe(error);
  await expect(scope.query("/api/queryPainScores", { ParticipantId: "pt" })).resolves.toEqual({ status: 200, data: {} });
  expect(request).toHaveBeenCalledTimes(2);
});
test("the React subscription stays stable on rerender and stops polling when the view unmounts", async () => {
  const React = require("react");
  const { createRoot } = require("react-dom/client");
  const { act } = require("react-dom/test-utils");
  const { useAnalysisQuery } = require("./queryAnalysis");
  const { SessionController } = require("database/session-control");
  const previousAct = global.IS_REACT_ACT_ENVIRONMENT;
  global.IS_REACT_ACT_ENVIRONMENT = true;
  const node = document.createElement("div"); document.body.appendChild(node);
  const root = createRoot(node); let query;
  function Probe() { query = useAnalysisQuery(); return null; }
  SessionController.query.mockResolvedValue({ status: 202, data: { status: "running" } });
  try {
    act(() => root.render(React.createElement(Probe)));
    const initial = query;
    act(() => root.render(React.createElement(Probe)));
    expect(query).toBe(initial);
    query("/api/queryDataAvailability", { ParticipantId: "hook-pt" });
    await tick(); expect(SessionController.query).toHaveBeenCalledTimes(1);
    act(() => root.unmount());
    jest.advanceTimersByTime(30000); await tick();
    expect(SessionController.query).toHaveBeenCalledTimes(1);
  } finally { node.remove(); global.IS_REACT_ACT_ENVIRONMENT = previousAct; }
});

test.each(['new-account','new-study','logged-out'])("pending responses cannot cross into %s with identical inputs", async nextScope => {
  let owner='old-account',finishOld;
  const request=jest.fn().mockImplementationOnce(()=>new Promise(resolve=>{finishOld=resolve;}))
    .mockResolvedValue({status:200,data:{source:nextScope}});
  const client=createAnalysisClient(request,()=>owner), old=client.createScope(), oldResult=jest.fn();
  old.query('/api/queryPainScores',{ParticipantId:'same'}).then(oldResult);await tick();
  owner=nextScope;
  const fresh=client.createScope().query('/api/queryPainScores',{ParticipantId:'same'});
  await tick();finishOld({status:200,data:{source:'old-account'}});await tick();
  expect(oldResult).not.toHaveBeenCalled();expect((await fresh).data.source).toBe(nextScope);
  expect(request).toHaveBeenCalledTimes(2);
  await expect(old.query('/api/queryPainScores',{ParticipantId:'same'})).rejects.toThrow('account or study changed');
});

test('a scope change before a queued request or next poll never sends old work under new credentials',async()=>{
  let owner='old';const request=jest.fn().mockResolvedValue({status:202,data:{status:'running'}});
  const client=createAnalysisClient(request,()=>owner);
  client.createScope().query('/api/queryPainScores',{ParticipantId:'same'});owner='new';await tick();
  expect(request).not.toHaveBeenCalled();
  client.createScope().query('/api/queryPainScores',{ParticipantId:'same'});await tick();
  expect(request).toHaveBeenCalledTimes(1);owner='third';jest.advanceTimersByTime(3000);await tick();
  expect(request).toHaveBeenCalledTimes(1);
});

test('old-scope errors cannot replace a new-scope successful result',async()=>{
  let owner='old',failOld;const request=jest.fn().mockImplementationOnce(()=>new Promise((resolve,reject)=>{failOld=reject;}))
    .mockResolvedValue({status:200,data:{source:'new'}});
  const client=createAnalysisClient(request,()=>owner), oldError=jest.fn();
  client.createScope().query('/api/queryPainScores',{ParticipantId:'same'}).catch(oldError);await tick();
  owner='new';const fresh=client.createScope().query('/api/queryPainScores',{ParticipantId:'same'});
  failOld(new Error('old permission denied'));await tick();expect(oldError).not.toHaveBeenCalled();
  expect((await fresh).data.source).toBe('new');
});

test('a mounted view gets a fresh transport subscription after account or study changes',async()=>{
  const React=require('react'),{createRoot}=require('react-dom/client'),{act}=require('react-dom/test-utils');
  const {useAnalysisQuery}=require('./queryAnalysis');
  global.IS_REACT_ACT_ENVIRONMENT=true;const node=document.createElement('div'),root=createRoot(node);let query,finishOld;
  function Probe(){query=useAnalysisQuery();return null;}
  SessionController.query.mockImplementationOnce(()=>new Promise(resolve=>{finishOld=resolve;}))
    .mockResolvedValue({status:200,data:{source:'new-study'}});
  act(()=>root.render(React.createElement(Probe)));const old=query, oldValue=jest.fn();
  old('/api/queryPainScores',{ParticipantId:'same'}).then(oldValue);await tick();
  cacheScope.mockReturnValue('new-study');act(()=>root.render(React.createElement(Probe)));
  expect(query).not.toBe(old);const fresh=query('/api/queryPainScores',{ParticipantId:'same'});await tick();
  finishOld({status:200,data:{source:'old'}});await tick();
  expect(oldValue).not.toHaveBeenCalled();expect((await fresh).data.source).toBe('new-study');
  act(()=>root.unmount());
});
