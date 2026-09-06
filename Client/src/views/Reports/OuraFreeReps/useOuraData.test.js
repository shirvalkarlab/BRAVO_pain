import React from 'react';
import {createRoot} from 'react-dom/client';
import {act} from 'react-dom/test-utils';
import {SessionController} from 'database/session-control';
import {useOuraData} from './useOuraData';

jest.mock('database/session-control',()=>({SessionController:{query:jest.fn()}}));
let root, element, observed;
function Probe({participant='p1', sleepId, revision, enabled}) {
  observed=useOuraData(participant,sleepId,revision,enabled);
  return <div>{observed.data?.label || observed.error}</div>;
}
const deferred=()=>{let resolve,reject;const promise=new Promise((yes,no)=>{resolve=yes;reject=no;});return {promise,resolve,reject};};
const render=async(props={})=>act(async()=>root.render(<Probe {...props}/>));
beforeEach(()=>{global.IS_REACT_ACT_ENVIRONMENT=true;SessionController.query.mockReset();element=document.createElement('div');root=createRoot(element);});
afterEach(()=>act(()=>root.unmount()));

test('dashboard and session queries use participant scope and changing revision rereads stored data',async()=>{
  SessionController.query.mockResolvedValue({data:{label:'fresh'}});
  await render();
  expect(SessionController.query).toHaveBeenLastCalledWith('/api/queryOuraFreeReps',{ParticipantId:'p1'});
  expect(observed).toMatchObject({data:{label:'fresh'},loading:false,error:''});
  await render({sleepId:'sleep-1'});
  expect(SessionController.query).toHaveBeenLastCalledWith('/api/queryOuraFreeReps',{ParticipantId:'p1',SleepId:'sleep-1'});
  await render({sleepId:'sleep-1',revision:1});
  expect(SessionController.query).toHaveBeenCalledTimes(3);
});

test('switching participant hides previous data immediately and ignores late success from old request',async()=>{
  const old=deferred(),fresh=deferred();
  SessionController.query.mockReturnValueOnce(old.promise).mockReturnValueOnce(fresh.promise);
  await render();await render({participant:'p2'});
  expect(observed).toMatchObject({data:null,loading:true,error:''});
  await act(async()=>fresh.resolve({data:{label:'p2 data'}}));
  await act(async()=>old.resolve({data:{label:'private p1 data'}}));
  expect(observed.data.label).toBe('p2 data');
  expect(element.textContent).not.toContain('p1');
});

test('disabling a loaded query hides data and disabling a pending query prevents late publication',async()=>{
  const pending=deferred();
  SessionController.query.mockResolvedValueOnce({data:{label:'secret'}}).mockReturnValueOnce(pending.promise);
  await render();await render({enabled:false});
  expect(observed).toEqual({data:null,error:'',loading:false});
  await render({participant:'p2'});await render({participant:'p2',enabled:false});
  await act(async()=>pending.resolve({data:{label:'late secret'}}));
  expect(observed.data).toBeNull();
  expect(SessionController.query).toHaveBeenCalledTimes(2);
});

test('initial disabled or missing-participant renders do not submit queries',async()=>{
  await render({enabled:false});expect(observed.loading).toBe(false);
  await render({participant:null});
  expect(SessionController.query).not.toHaveBeenCalled();
  expect(observed.data).toBeNull();
  expect(observed.loading).toBe(false);
});

test.each([
  [{response:{status:403}},'You do not have access'],
  [{response:{status:404}},'This sleep session is no longer available'],
  [{response:{status:500}},'Oura data could not be loaded'],
  [new Error('offline'),'Oura data could not be loaded'],
])('failure is explicit, no private data retained, and refresh can recover (%p)',async(error,message)=>{
  SessionController.query.mockResolvedValueOnce({data:{label:'old'}}).mockRejectedValueOnce(error).mockResolvedValueOnce({data:{label:'recovered'}});
  await render();await render({revision:1});
  expect(observed.data).toBeNull();expect(observed.loading).toBe(false);expect(observed.error).toContain(message);
  await render({revision:2});expect(observed.data.label).toBe('recovered');expect(observed.error).toBe('');
});

test('late failure after navigation cannot replace current participant state',async()=>{
  const old=deferred();
  SessionController.query.mockReturnValueOnce(old.promise).mockResolvedValueOnce({data:{label:'current'}});
  await render();await render({participant:'p2'});
  await act(async()=>old.reject({response:{status:403}}));
  expect(observed).toMatchObject({data:{label:'current'},error:'',loading:false});
});

test('unmount ignores pending resolution and does not issue any extra request',async()=>{
  const pending=deferred();SessionController.query.mockReturnValue(pending.promise);
  await render();act(()=>root.unmount());
  await act(async()=>pending.resolve({data:{label:'late'}}));
  expect(element.textContent).toBe('');expect(SessionController.query).toHaveBeenCalledTimes(1);
  root=createRoot(element);
});
