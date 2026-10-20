import React from 'react';
import {createRoot} from 'react-dom/client';
import {act} from 'react-dom/test-utils';
import {SYNC_COMPLETED_EVENT} from 'utils/syncEvents';
import {SessionController} from 'database/session-control';
import {useRedcapTimeline} from './useRedcapTimeline';

jest.mock('database/session-control',()=>({SessionController:{query:jest.fn()}}));
let mockScope='account-a:study-a';
jest.mock('context',()=>({usePlatformContext:()=>[{}]}));
jest.mock('./requestScope',()=>({cacheScope:()=>mockScope}));
let root,element,observed;
function Probe({participant='p1',revision=0}) {observed=useRedcapTimeline(participant,revision);return <div>{observed.data?.label || observed.error}</div>;}
const deferred=()=>{let resolve,reject;const promise=new Promise((yes,no)=>{resolve=yes;reject=no;});return {promise,resolve,reject};};
const render=async(props={})=>act(async()=>root.render(<Probe {...props}/>));
beforeEach(()=>{global.IS_REACT_ACT_ENVIRONMENT=true;mockScope='account-a:study-a';SessionController.query.mockReset();element=document.createElement('div');root=createRoot(element);});
afterEach(()=>{act(()=>root.unmount());jest.useRealTimers();});

test('queries participant scope only, caches the current render and refresh revision reads current reviewed data',async()=>{
  SessionController.query.mockResolvedValue({data:{label:'reviewed'}});
  await render();
  expect(SessionController.query).toHaveBeenLastCalledWith('/api/queryRedcapTimeline',{ParticipantId:'p1'});
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


test.each(['resolve','reject'])('account change rejects pending %s before another render',async(method)=>{
 const pending=deferred();SessionController.query.mockReturnValueOnce(pending.promise).mockResolvedValue({data:{label:'new-account'}});
 await render();mockScope='account-b:study-a';
 await act(async()=>pending[method](method==='resolve'?{data:{label:'private-old-account'}}:new Error('old failure')));
 expect(element.textContent).not.toContain('private-old-account');expect(observed.error).toBe('');
 await render();expect(observed.data.label).toBe('new-account');
});

test('study replacement hides previous data and reloads the same participant',async()=>{
 const pending=deferred();SessionController.query.mockResolvedValueOnce({data:{label:'old-study'}}).mockReturnValueOnce(pending.promise);
 await render();mockScope='account-a:study-b';await render();
 expect(observed).toMatchObject({data:null,error:'',loading:true});expect(element.textContent).not.toContain('old-study');
 await act(async()=>pending.resolve({data:{label:'new-study'}}));expect(observed.data.label).toBe('new-study');
 expect(SessionController.query).toHaveBeenCalledTimes(2);
});

test('signed-out scope hides old data and sends no request',async()=>{
 SessionController.query.mockResolvedValue({data:{label:'private'}});await render();
 mockScope=null;await render();expect(observed).toEqual({data:null,error:'',loading:false});
 expect(element.textContent).toBe('');expect(SessionController.query).toHaveBeenCalledTimes(1);
});

const revisionA='a'.repeat(64),revisionB='b'.repeat(64);
const complete=(participantUid='p1',scope=mockScope,state='succeeded')=>window.dispatchEvent(new CustomEvent(SYNC_COMPLETED_EVENT,{detail:{participantUid,scope,state}}));

test('mounted stream automatically rereads matching manual success and partial failure, never starts a provider fetch',async()=>{
 SessionController.query.mockResolvedValue({data:{label:'stored',revision:revisionA}});await render();
 await act(async()=>{complete('other');complete('p1','other-account');});expect(SessionController.query).toHaveBeenCalledTimes(1);
 SessionController.query.mockResolvedValue({data:{label:'partial available',revision:revisionB}});
 await act(async()=>complete('p1',mockScope,'failed'));expect(observed.data.label).toBe('partial available');
 await act(async()=>complete());expect(SessionController.query).toHaveBeenCalledTimes(3);
 expect(SessionController.query.mock.calls.every(([url,body])=>url==='/api/queryRedcapTimeline' && !body.RequestType)).toBe(true);
});

test('daily stored revision updates without manual sync; unchanged revisions do not reload full data',async()=>{
 jest.useFakeTimers();SessionController.query.mockResolvedValueOnce({data:{label:'before',revision:revisionA}})
 .mockResolvedValueOnce({data:{revision:revisionA}}).mockResolvedValueOnce({data:{revision:revisionB}})
 .mockResolvedValueOnce({data:{label:'after daily sync',revision:revisionB}});
 await render();await act(async()=>jest.advanceTimersByTime(60000));expect(SessionController.query).toHaveBeenCalledTimes(2);
 await act(async()=>jest.advanceTimersByTime(60000));expect(observed.data.label).toBe('after daily sync');
 expect(SessionController.query.mock.calls.map(([,body])=>body.RequestType)).toEqual([undefined,'Revision','Revision',undefined]);
});

test('automatic read failure clears failed data and retries on unchanged stored revision',async()=>{
 jest.useFakeTimers();SessionController.query.mockResolvedValueOnce({data:{label:'before',revision:revisionA}})
 .mockRejectedValueOnce(new Error('read failed')).mockResolvedValueOnce({data:{revision:revisionA}})
 .mockResolvedValueOnce({data:{label:'recovered',revision:revisionA}});
 await render();await act(async()=>complete());expect(observed.data).toBeNull();expect(observed.error).toContain('could not be loaded');
 await act(async()=>jest.advanceTimersByTime(60000));expect(observed.data.label).toBe('recovered');expect(observed.error).toBe('');
});

test('paired focus and visibility events do not discard a successful in-flight full read',async()=>{
 const pending=deferred();SessionController.query.mockReturnValueOnce(pending.promise).mockRejectedValue(new Error('unnecessary full read failed'));
 await render();await act(async()=>{window.dispatchEvent(new Event('focus'));document.dispatchEvent(new Event('visibilitychange'));});
 await act(async()=>pending.resolve({data:{label:'success retained',revision:revisionA}}));
 expect(SessionController.query).toHaveBeenCalledTimes(1);
 expect(observed).toMatchObject({data:{label:'success retained'},loading:false,error:''});
});

test('focus and visibility coalesce a revision check and unchanged data do not reload',async()=>{
 const check=deferred();SessionController.query.mockResolvedValueOnce({data:{label:'retained',revision:revisionA}}).mockReturnValueOnce(check.promise);
 await render();await act(async()=>{window.dispatchEvent(new Event('focus'));document.dispatchEvent(new Event('visibilitychange'));});
 expect(SessionController.query).toHaveBeenCalledTimes(2);
 expect(SessionController.query).toHaveBeenLastCalledWith('/api/queryRedcapTimeline',{ParticipantId:'p1',RequestType:'Revision'});
 await act(async()=>check.resolve({data:{revision:revisionA}}));
 expect(SessionController.query).toHaveBeenCalledTimes(2);expect(observed.data.label).toBe('retained');
});

test('focus revision change reloads once, while a sync during the read still queues newer data',async()=>{
 const beforeSync=deferred(),afterSync=deferred();SessionController.query.mockResolvedValueOnce({data:{label:'old',revision:revisionA}})
 .mockResolvedValueOnce({data:{revision:revisionB}}).mockReturnValueOnce(beforeSync.promise).mockReturnValueOnce(afterSync.promise);
 await render();await act(async()=>window.dispatchEvent(new Event('focus')));
 expect(SessionController.query).toHaveBeenCalledTimes(3);
 await act(async()=>{document.dispatchEvent(new Event('visibilitychange'));complete();});
 await act(async()=>beforeSync.resolve({data:{label:'obsolete before sync',revision:revisionB}}));
 expect(SessionController.query).toHaveBeenCalledTimes(4);expect(observed.data?.label).not.toBe('obsolete before sync');
 await act(async()=>afterSync.resolve({data:{label:'newest after sync',revision:'c'.repeat(64)}}));
 expect(observed).toMatchObject({data:{label:'newest after sync'},loading:false,error:''});
});
