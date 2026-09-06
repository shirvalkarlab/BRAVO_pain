import {useEffect, useState} from 'react';
import {usePlatformContext} from 'context';
import {SessionController} from 'database/session-control';
import {cacheScope} from 'database/resultCache';

// This is a read-only report; opening it never launches a model fit or device sync.
export function useHomeNeuralTimeline(participant, revision, window) {
  usePlatformContext();
  const scope = cacheScope();
  const options = JSON.stringify(typeof window === 'string' ? {window} : window || {});
  const key = JSON.stringify([participant, revision, scope, options]);
  const [state, setState] = useState({key: '', data: null, loading: false, error: ''});
  useEffect(() => {
    let active = true;
    if (!participant || !scope) return () => {active = false;};
    setState({key, data: null, loading: true, error: ''});
    SessionController.query('/api/queryHomeNeuralTimeline', {ParticipantId: participant, ...JSON.parse(options)}).then(response => {
      if (active && cacheScope() === scope) setState({key, data: response.data, loading: false, error: ''});
    }).catch(error => {
      if (active && cacheScope() === scope) setState({key, data: null, loading: false, error: error.response?.status === 403
        ? 'You do not have access to this participant’s home neural data.'
        : 'Home neural data could not be loaded. Use Refresh neural view to retry.'});
    });
    return () => {active = false;};
  }, [participant, revision, scope, key, options]);
  return state.key === key ? state : {data: null, loading: Boolean(participant && scope), error: ''};
}
