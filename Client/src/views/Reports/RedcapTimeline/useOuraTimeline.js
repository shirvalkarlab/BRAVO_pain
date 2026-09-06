import {useEffect, useState} from 'react';
import {usePlatformContext} from 'context';
import {cacheScope} from 'database/resultCache';
import {SessionController} from 'database/session-control';

export function useOuraTimeline(participant, revision) {
  usePlatformContext();
  const scope = cacheScope();
  const key = JSON.stringify([participant, revision, scope]);
  const [state, setState] = useState({key: '', data: null, loading: true, error: ''});
  useEffect(() => {
    let active = true;
    if (!participant || !scope) return () => {active = false;};
    setState({key, data: null, loading: true, error: ''});
    SessionController.query('/api/queryOuraTimeline', {ParticipantId: participant}).then(response => {
      if (active && cacheScope() === scope) setState({key, data: response.data, loading: false, error: ''});
    }).catch(error => {
      if (active && cacheScope() === scope) setState({key, data: null, loading: false, error: error.response?.status === 403
        ? 'You do not have access to this participant’s Oura data.' : 'Oura data could not be loaded. Use Refresh Oura view to retry.'});
    });
    return () => {active = false;};
  }, [participant, revision, scope, key]);
  return state.key === key ? state : {data: null, loading: Boolean(participant && scope), error: ''};
}
