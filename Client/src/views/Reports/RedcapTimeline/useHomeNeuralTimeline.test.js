import React from 'react';
import {createRoot} from 'react-dom/client';
import {act} from 'react-dom/test-utils';
import {SessionController} from 'database/session-control';
import {useHomeNeuralTimeline} from './useHomeNeuralTimeline';

jest.mock('database/session-control',()=>({SessionController:{query:jest.fn()}}));
let mockScope='account-a';
jest.mock('context',()=>({usePlatformContext:()=>[{}]}));
jest.mock('database/resultCache',()=>({cacheScope:()=>mockScope}));
let root,element,observed;
function Probe({participant='p1',revision=0,window}) {observed=useHomeNeuralTimeline(participant,revision,window);return <div>{observed.data?.label || observed.error}</div>;}
const deferred=()=>{let resolve,reject;const promise=new Promise((yes,no)=>{resolve=yes;reject=no;});return {promise,resolve,reject};};
const render=async(props={})=>act(async()=>root.render(<Probe {...props}/>));
beforeEach(()=>{global.IS_REACT_ACT_ENVIRONMENT=true;mockScope='account-a';SessionController.query.mockReset();element=document.createElement('div');root=createRoot(element);});
afterEach(()=>act(()=>root.unmount()));

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
