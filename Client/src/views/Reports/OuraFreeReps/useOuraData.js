import { useEffect, useState } from "react";
import { SessionController } from "database/session-control";

export function useOuraData(participant, sleepId = null, revision = 0, enabled = true) {
  const [state, setState] = useState({key: "", data: null, error: "", loading: true});
  const key = JSON.stringify([participant, sleepId, revision, enabled]);
  useEffect(() => {
    let active = true;
    if (!participant || !enabled) return () => { active = false; };
    setState({key, data: null, error: "", loading: true});
    const body = {ParticipantId: participant};
    if (sleepId) body.SleepId = sleepId;
    SessionController.query("/api/queryOuraFreeReps", body).then(response => {
      if (active) setState({key, data: response.data, error: "", loading: false});
    }).catch(error => {
      if (!active) return;
      const status = error.response?.status;
      const message = status === 403 ? "You do not have access to this participant’s Oura data."
        : status === 404 ? "This sleep session is no longer available. Refresh the data."
        : "Oura data could not be loaded. Please retry.";
      setState({key, data: null, error: message, loading: false});
    });
    return () => { active = false; };
  }, [key, participant, sleepId, enabled]); // revision is represented by key
  if (state.key !== key) return {data: null, error: "", loading: Boolean(participant && enabled)};
  return state;
}
