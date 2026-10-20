import {useEffect, useState} from 'react';
import {usePlatformContext} from 'context';
import {SessionController} from 'database/session-control';
import {SYNC_COMPLETED_EVENT} from 'utils/syncEvents';
import {cacheScope} from './requestScope';

// A mounted view reads saved data only. Revision checks never start provider
// fetches or analyses. Each stream has one scoped, serialized read lifecycle.
export function useStoredTimeline(participant, revision, config, selectedWindow, live) {
  const {endpoint, accessError, loadError, freshnessError} = config;
  usePlatformContext();
  const scope = cacheScope();
  const options = JSON.stringify(typeof selectedWindow === 'string' ? {window:selectedWindow} : selectedWindow || {});
  const key = JSON.stringify([participant, revision, scope, options, live, endpoint]);
  const [state, setState] = useState({key: '', data: null, loading: false, error: ''});
  useEffect(() => {
    let active=true, loading=false, queued=false, polling=false, knownRevision=null, generation=0;
    if (!participant || !scope) return () => {active=false;};
    const current=()=>active && cacheScope() === scope;
    const body={ParticipantId:participant,...JSON.parse(options)};
    const load=async()=>{
      if (!current()) return;
      if (loading) {queued=true;return;}
      loading=true;generation++;
      setState(previous=>({key,data:live && previous.key === key ? previous.data : null,loading:true,error:'',...(live?{freshnessError:''}:{})}));
      try {
        const response=await SessionController.query(endpoint,body);
        if (current() && !queued) {
          knownRevision=response.data.revision;
          setState({key,data:response.data,loading:false,error:'',...(live?{freshnessError:''}:{})});
        }
      } catch(error) {
        if (current() && !queued) {
          knownRevision=null;
          setState({key,data:null,loading:false,error:[401,403].includes(error.response?.status)
            ? accessError : loadError,...(live?{freshnessError:''}:{})});
        }
      } finally {
        loading=false;
        if (current() && queued) {queued=false;load();}
      }
    };
    const poll=async()=>{
      if (!current() || document.visibilityState === 'hidden' || polling || loading) return;
      polling=true;
      const startedGeneration=generation;
      try {
        const response=await SessionController.query(endpoint,{...body,RequestType:'Revision'});
        if (current() && generation === startedGeneration) {
          if (typeof response.data.revision !== 'string' || !/^[a-f0-9]{64}$/.test(response.data.revision)) throw new Error('Invalid revision');
          setState(previous=>({...previous,freshnessError:''}));
          if (response.data.revision !== knownRevision) load();
        }
      } catch(error) {
        if (current() && generation === startedGeneration) {
          if ([401,403].includes(error.response?.status)) {
            knownRevision=null;
            setState({key,data:null,loading:false,error:accessError,freshnessError:''});
          } else setState(previous=>({...previous,
            freshnessError}));
        }
      } finally {polling=false;}
    };
    // Focus and visibility often arrive together. Revalidate the stored revision,
    // coalescing with an active read/check, rather than queueing another full
    // payload and suppressing a successful response. A sync completion below is
    // different: it must queue a newer full read behind any pre-sync request.
    const visible=()=>poll();
    const completed=event=>{
      if(event.detail?.participantUid === participant && event.detail.scope === scope) load();
    };
    load();
    if(live) {
      const timer=setInterval(poll,60000);
      window.addEventListener('focus',visible);
      document.addEventListener('visibilitychange',visible);
      window.addEventListener(SYNC_COMPLETED_EVENT,completed);
      return()=>{active=false;clearInterval(timer);window.removeEventListener('focus',visible);document.removeEventListener('visibilitychange',visible);window.removeEventListener(SYNC_COMPLETED_EVENT,completed);};
    }
    return()=>{active=false;};
  }, [participant, scope, key, options, live, endpoint, accessError, loadError, freshnessError]);
  return state.key === key ? state : {data:null,loading:Boolean(participant && scope),error:''};
}
