import React from 'react';
import {createRoot} from 'react-dom/client';
import {act} from 'react-dom/test-utils';
import {SYNC_COMPLETED_EVENT} from 'utils/syncEvents';
import {SessionController} from 'database/session-control';
import {useHomeNeuralTimeline} from './useHomeNeuralTimeline';

jest.mock('database/session-control',()=>({SessionController:{query:jest.fn()}}));
let mockScope='account-a';
jest.mock('context',()=>({usePlatformContext:()=>[{}]}));
jest.mock('./requestScope',()=>({cacheScope:()=>mockScope}));
let root,element,observed;
function Probe({participant='p1',revision=0,window,live=false}) {observed=useHomeNeuralTimeline(participant,revision,window,live);return <div>{observed.data?.label || observed.error}</div>;}
const deferred=()=>{let resolve,reject;const promise=new Promise((yes,no)=>{resolve=yes;reject=no;});return {promise,resolve,reject};};
const render=async(props={})=>act(async()=>root.render(<Probe {...props}/>));
beforeEach(()=>{global.IS_REACT_ACT_ENVIRONMENT=true;mockScope='account-a';SessionController.query.mockReset();element=document.createElement('div');root=createRoot(element);});
afterEach(()=>{act(()=>root.unmount());jest.useRealTimers();});

test('queries participant scope only, caches the current render and refresh revision reads current reviewed data',async()=>{
  SessionController.query.mockResolvedValue({data:{label:'reviewed'}});
  await render();
  expect(SessionController.query).toHaveBeenLastCalledWith('/api/queryHomeNeuralTimeline',{ParticipantId:'p1'});
  expect(observed).toMatchObject({data:{label:'reviewed'},error:'',loading:false});
  await render();expect(SessionController.query).toHaveBeenCalledTimes(1);
  await render({revision:1});expect(SessionController.query).toHaveBeenCalledTimes(2);
});

test('switching participants immediately hides the old result and ignores stale success',async()=>{
  const old=deferred(),fresh=deferred();SessionController.query.mockReturnValueOnce(old.promise).mockReturnValueOnce(fresh.promise);
  await render();await render({participant:'p2'});
  expect(observed).toMatchObject({data:null,error:'',loading:true});
  await act(async()=>fresh.resolve({data:{label:'p2 reviewed'}}));
  await act(async()=>old.resolve({data:{label:'p1 private'}}));
  expect(observed.data.label).toBe('p2 reviewed');expect(element.textContent).not.toContain('private');
});

test('a new revision wins over a late response for the same participant',async()=>{
  const old=deferred();SessionController.query.mockReturnValueOnce(old.promise).mockResolvedValueOnce({data:{label:'latest'}});
  await render();await render({revision:1});await act(async()=>old.resolve({data:{label:'obsolete'}}));
  expect(observed.data.label).toBe('latest');
});

test('missing participant never queries and removing a participant hides data and cancels pending publication',async()=>{
  await render({participant:null});expect(SessionController.query).not.toHaveBeenCalled();
  expect(observed).toEqual({data:null,error:'',loading:false});
  const pending=deferred();SessionController.query.mockReturnValue(pending.promise);
  await render();await render({participant:null});
  await act(async()=>pending.resolve({data:{label:'late private'}}));
  expect(observed).toEqual({data:null,error:'',loading:false});expect(element.textContent).toBe('');
});

test.each([[{response:{status:403}},'You do not have access'],[{response:{status:500}},'could not be loaded'],[new Error('offline'),'could not be loaded']])('failure clears old data, shows actionable error and refresh recovers (%p)',async(error,message)=>{
  SessionController.query.mockResolvedValueOnce({data:{label:'previous'}}).mockRejectedValueOnce(error).mockResolvedValueOnce({data:{label:'recovered'}});
  await render();await render({revision:1});
  expect(observed).toMatchObject({data:null,loading:false});expect(observed.error).toContain(message);
  expect(element.textContent).not.toContain('previous');
  await render({revision:2});expect(observed).toMatchObject({data:{label:'recovered'},error:'',loading:false});
});

test('late failure cannot overwrite the latest participant',async()=>{
  const old=deferred();SessionController.query.mockReturnValueOnce(old.promise).mockResolvedValueOnce({data:{label:'current'}});
  await render();await render({participant:'p2'});await act(async()=>old.reject({response:{status:403}}));
  expect(observed).toMatchObject({data:{label:'current'},error:'',loading:false});
});

test.each(['resolve','reject'])('unmount ignores pending %s without extra requests',async(method)=>{
  const pending=deferred();SessionController.query.mockReturnValue(pending.promise);await render();act(()=>root.unmount());
  await act(async()=>pending[method](method==='resolve'?{data:{label:'late'}}:new Error('late failure')));
  expect(element.textContent).toBe('');expect(SessionController.query).toHaveBeenCalledTimes(1);root=createRoot(element);
});


test.each(['resolve','reject'])('account change rejects a late %s even before the next render',async(method)=>{
 const pending=deferred();SessionController.query.mockReturnValueOnce(pending.promise).mockResolvedValue({data:{label:'new-account'}});
 await render();mockScope='account-b';
 await act(async()=>pending[method](method==='resolve'?{data:{label:'private-old-account'}}:new Error('old failure')));
 expect(element.textContent).not.toContain('private-old-account');expect(observed.error).toBe('');
 await render();expect(observed.data.label).toBe('new-account');
});

test('signed-out scope never sends a request and immediately hides the prior response',async()=>{
 SessionController.query.mockResolvedValue({data:{label:'private'}});await render();
 mockScope=null;await render();expect(observed).toEqual({data:null,error:'',loading:false});
 expect(SessionController.query).toHaveBeenCalledTimes(1);
});


test('summary window is explicit and default current/previous request remains unchanged after leaving summary',async()=>{
 SessionController.query.mockResolvedValue({data:{windows:[]}});
 await render({window:'past28'});expect(SessionController.query).toHaveBeenLastCalledWith('/api/queryHomeNeuralTimeline',{ParticipantId:'p1',window:'past28'});
 await render({window:{window:'custom',start_date:'2026-08-01',end_date:'2026-08-28'}});
 expect(SessionController.query).toHaveBeenLastCalledWith('/api/queryHomeNeuralTimeline',{ParticipantId:'p1',window:'custom',start_date:'2026-08-01',end_date:'2026-08-28'});
 await render({window:{window:'custom',start_date:'2026-08-01',end_date:'2026-08-28'}});expect(SessionController.query).toHaveBeenCalledTimes(2);
 await render();expect(SessionController.query).toHaveBeenLastCalledWith('/api/queryHomeNeuralTimeline',{ParticipantId:'p1'});
});

test('switching window immediately hides old records and rejects a late response for the previous range',async()=>{
 const old=deferred(),fresh=deferred();SessionController.query.mockReturnValueOnce(old.promise).mockReturnValueOnce(fresh.promise);
 await render({window:'past28'});await render({window:{window:'custom',start_date:'2026-07-01',end_date:'2026-07-28'}});
 expect(observed).toMatchObject({data:null,loading:true});await act(async()=>fresh.resolve({data:{label:'July only'}}));
 await act(async()=>old.resolve({data:{label:'Wrong recent records'}}));expect(observed.data.label).toBe('July only');
});

const REV1='a'.repeat(64),REV2='b'.repeat(64);
const finishSync=(participantUid='p1',scope='account-a',state='succeeded')=>window.dispatchEvent(new CustomEvent(SYNC_COMPLETED_EVENT,{detail:{participantUid,scope,state}}));

test('live revision checks only refetch changed data and never overlap; daily updates need no manual request',async()=>{
 jest.useFakeTimers();let finish;
 SessionController.query.mockResolvedValueOnce({data:{label:'first',revision:REV1}})
  .mockResolvedValueOnce({data:{revision:REV1}})
  .mockImplementationOnce(()=>new Promise(resolve=>{finish=resolve;}))
  .mockResolvedValue({data:{label:'new daily data',revision:REV2}});
 await render({live:true});await act(async()=>jest.advanceTimersByTime(60000));
 expect(SessionController.query).toHaveBeenCalledTimes(2);expect(observed.data.label).toBe('first');
 expect(SessionController.query).toHaveBeenLastCalledWith('/api/queryHomeNeuralTimeline',{ParticipantId:'p1',RequestType:'Revision'});
 await act(async()=>jest.advanceTimersByTime(120000));expect(SessionController.query).toHaveBeenCalledTimes(3);
 await act(async()=>finish({data:{revision:REV2}}));
 expect(SessionController.query).toHaveBeenCalledTimes(4);expect(observed.data.label).toBe('new daily data');
});

test('live refresh listens only to this account and participant, including partial terminal failures',async()=>{
 SessionController.query.mockResolvedValue({data:{label:'available data',revision:REV1}});await render({live:true});
 await act(async()=>{finishSync('other');finishSync('p1','other-account');window.dispatchEvent(new CustomEvent(SYNC_COMPLETED_EVENT));});
 expect(SessionController.query).toHaveBeenCalledTimes(1);
 await act(async()=>finishSync('p1','account-a','failed'));expect(SessionController.query).toHaveBeenCalledTimes(2);
 expect(observed.data.label).toBe('available data');
 await act(async()=>finishSync());expect(SessionController.query).toHaveBeenCalledTimes(3);
 mockScope='account-b';await act(async()=>finishSync());expect(SessionController.query).toHaveBeenCalledTimes(3);
});

test('hidden tabs pause checks; focus and returning visible refresh stored data',async()=>{
 jest.useFakeTimers();const visibility=jest.spyOn(document,'visibilityState','get');
 visibility.mockReturnValue('hidden');SessionController.query.mockResolvedValue({data:{revision:REV1}});
 await render({live:true});await act(async()=>{jest.advanceTimersByTime(60000);window.dispatchEvent(new Event('focus'));document.dispatchEvent(new Event('visibilitychange'));});
 expect(SessionController.query).toHaveBeenCalledTimes(1);
 visibility.mockReturnValue('visible');await act(async()=>window.dispatchEvent(new Event('focus')));
 await act(async()=>document.dispatchEvent(new Event('visibilitychange')));
 expect(SessionController.query).toHaveBeenCalledTimes(3);visibility.mockRestore();
});

test('refresh during an in-flight read queues once and suppresses the obsolete result',async()=>{
 jest.useFakeTimers();const first=deferred(),second=deferred();
 SessionController.query.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise);
 await render({live:true});await act(async()=>{finishSync();finishSync();jest.advanceTimersByTime(60000);});
 expect(SessionController.query).toHaveBeenCalledTimes(1);
 await act(async()=>first.resolve({data:{label:'obsolete',revision:REV1}}));
 expect(SessionController.query).toHaveBeenCalledTimes(2);expect(observed.data).toBeNull();
 await act(async()=>second.resolve({data:{label:'after sync',revision:REV2}}));expect(observed.data.label).toBe('after sync');
});

test.each(['offline','invalid'])('revision %s failure keeps existing charts and reports uncertainty',async(kind)=>{
 jest.useFakeTimers();SessionController.query.mockResolvedValueOnce({data:{label:'retained',revision:REV1}});
 if(kind==='offline') SessionController.query.mockRejectedValueOnce(new Error('offline'));
 else SessionController.query.mockResolvedValueOnce({data:{revision:'invalid'}});
 SessionController.query.mockResolvedValue({data:{revision:REV1}});
 await render({live:true});await act(async()=>jest.advanceTimersByTime(60000));
 expect(observed.data.label).toBe('retained');expect(observed.freshnessError).toContain('Automatic update check unavailable');
 await act(async()=>jest.advanceTimersByTime(60000));expect(observed.freshnessError).toBe('');
});

test.each(['resolve','reject'])('stale live revision %s cannot affect another participant or newer full read',async(outcome)=>{
 jest.useFakeTimers();const late=deferred();
 SessionController.query.mockResolvedValueOnce({data:{label:'p1',revision:REV1}}).mockReturnValueOnce(late.promise)
  .mockResolvedValue({data:{label:'p2',revision:REV2}});
 await render({live:true});await act(async()=>jest.advanceTimersByTime(60000));await render({participant:'p2',live:true});
 await act(async()=>late[outcome](outcome==='resolve'?{data:{revision:REV1}}:new Error('stale')));
 expect(observed.data.label).toBe('p2');expect(observed.freshnessError).toBe('');
});

test('revision response predating a completion-triggered full read cannot roll it back',async()=>{
 jest.useFakeTimers();const late=deferred();SessionController.query.mockResolvedValueOnce({data:{label:'first',revision:REV1}})
 .mockReturnValueOnce(late.promise).mockResolvedValue({data:{label:'latest',revision:REV2}});
 await render({live:true});await act(async()=>jest.advanceTimersByTime(60000));await act(async()=>finishSync());
 await act(async()=>late.resolve({data:{revision:REV1}}));
 expect(SessionController.query).toHaveBeenCalledTimes(3);expect(observed.data.label).toBe('latest');
});

test('summary hook stays passive and live listeners and timer are removed on unmount',async()=>{
 jest.useFakeTimers();SessionController.query.mockResolvedValue({data:{revision:REV1}});
 await render();await act(async()=>{finishSync();window.dispatchEvent(new Event('focus'));jest.advanceTimersByTime(60000);});
 expect(SessionController.query).toHaveBeenCalledTimes(1);
 await render({live:true});act(()=>root.unmount());root=createRoot(element);
 await act(async()=>{finishSync();window.dispatchEvent(new Event('focus'));jest.advanceTimersByTime(60000);});
 expect(SessionController.query).toHaveBeenCalledTimes(2);
});

test('completion queued behind a failing full read retries without exposing obsolete failure',async()=>{
 const old=deferred(),fresh=deferred();SessionController.query.mockReturnValueOnce(old.promise).mockReturnValueOnce(fresh.promise);
 await render({live:true});await act(async()=>finishSync());await act(async()=>old.reject(new Error('superseded failure')));
 expect(observed.error).toBe('');expect(SessionController.query).toHaveBeenCalledTimes(2);
 await act(async()=>fresh.resolve({data:{label:'current',revision:REV2}}));expect(observed.data.label).toBe('current');
});

test.each([401,403])('revision authorization denial %s clears prior participant charts and can recover only through a new full read',async(status)=>{
 jest.useFakeTimers();SessionController.query.mockResolvedValueOnce({data:{label:'private participant data',revision:REV1}})
 .mockRejectedValueOnce({response:{status}}).mockResolvedValueOnce({data:{revision:REV1}})
 .mockResolvedValueOnce({data:{label:'new authorized read',revision:REV1}});
 await render({live:true});await act(async()=>jest.advanceTimersByTime(60000));
 expect(observed.data).toBeNull();expect(element.textContent).not.toContain('private participant data');
 expect(observed.error).toContain('do not have access');expect(observed.freshnessError).toBe('');
 await act(async()=>jest.advanceTimersByTime(60000));expect(observed.data.label).toBe('new authorized read');
 expect(SessionController.query).toHaveBeenCalledTimes(4);
});

test('composed page and local refresh revisions compare by value rather than array identity',async()=>{
 SessionController.query.mockResolvedValue({data:{label:'stable',revision:REV1}});
 await render({revision:[0,0],live:true});await render({revision:[0,0],live:true});expect(SessionController.query).toHaveBeenCalledTimes(1);
 await render({revision:[1,0],live:true});expect(SessionController.query).toHaveBeenCalledTimes(2);
 await render({revision:[1,1],live:true});expect(SessionController.query).toHaveBeenCalledTimes(3);
});

test('legacy callers omitting live keep a passive saved-data read',async()=>{
 function LegacyProbe(){observed=useHomeNeuralTimeline('p1',0);return null;}
 jest.useFakeTimers();SessionController.query.mockResolvedValue({data:{label:'legacy',revision:REV1}});
 // Direct ReactDOM roots require act; this is not a Testing Library render.
 // eslint-disable-next-line testing-library/no-unnecessary-act
 await act(async()=>root.render(<LegacyProbe/>));await act(async()=>{finishSync();jest.advanceTimersByTime(60000);});
 expect(SessionController.query).toHaveBeenCalledTimes(1);expect(observed.data.label).toBe('legacy');
});
