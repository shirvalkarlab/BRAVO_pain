import {useEffect, useState} from "react";
import {usePlatformContext} from "context";
import {cacheScope} from "database/resultCache";
import {SessionController} from "database/session-control";

export function useRedcapTimeline(participant, revision) {
  usePlatformContext();
  const scope = cacheScope();
  const [state, setState] = useState({key: "", data: null, error: "", loading: true});
  const key = JSON.stringify([participant, revision, scope]);
  useEffect(() => {
    let active = true;
    if (!participant || !scope) return () => {active = false;};
    setState({key, data: null, error: "", loading: true});
    SessionController.query("/api/queryRedcapTimeline", {ParticipantId: participant}).then(response => {
      if (active && cacheScope() === scope) setState({key, data: response.data, error: "", loading: false});
    }).catch(error => {
      if (active && cacheScope() === scope) setState({key, data: null, loading: false, error: error.response?.status === 403
        ? "You do not have access to this participant’s REDCap data."
        : "The reviewed REDCap timeline could not be loaded. Please retry; if this continues, check data sync."});
    });
    return () => {active = false;};
  }, [participant, revision, scope, key]);
  return state.key === key ? state : {data: null, error: "", loading: Boolean(participant && scope)};
}
