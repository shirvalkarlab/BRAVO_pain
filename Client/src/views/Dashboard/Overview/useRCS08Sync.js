import { useEffect, useRef, useState } from "react";
import { SessionController } from "database/session-control";

const isActive = (state) => ["queued", "running"].includes(state?.status);

// The server owns the job. A mounted page only starts requests and observes it.
export default function useRCS08Sync(enabled) {
  const [state, setState] = useState(null);
  const [checking, setChecking] = useState(true);
  const [message, setMessage] = useState("");
  const startRef = useRef(() => {});

  useEffect(() => {
    if (!enabled) return;
    let stopped = false;
    let timer;
    let inFlight = false;
    let known = false;
    let current = null;
    setChecking(true);
    setState(null);

    const accept = (next) => {
      if (stopped) return;
      current = next;
      known = true;
      setState(next);
      setChecking(false);
      setMessage("");
    };
    const schedule = (delay) => {
      if (!stopped) timer = setTimeout(poll, delay);
    };
    const poll = async () => {
      if (stopped || inFlight) return;
      inFlight = true;
      try {
        const response = await SessionController.query(
          "/api/syncRCS08", {RequestType: "Status"}, {}, 15000
        );
        accept(response.data);
      } catch (error) {
        if (!stopped) {
          known = false;
          setChecking(true);
          setMessage("Cannot check sync status right now. Reconnecting automatically; an accepted sync continues in the background.");
        }
      } finally {
        inFlight = false;
        schedule(isActive(current) || !known ? 3000 : 10000);
      }
    };

    startRef.current = async () => {
      // This synchronous guard also catches two clicks before React rerenders.
      if (stopped || inFlight || !known || isActive(current)) return;
      clearTimeout(timer);
      inFlight = true;
      known = false;
      setChecking(true);
      setMessage("Requesting sync…");
      try {
        const response = await SessionController.query(
          "/api/syncRCS08", {RequestType: "Start"}, {}, 15000
        );
        accept(response.data);
      } catch (error) {
        if (error?.response?.status === 409) {
          // Another tab or user got there first: follow the existing request.
          accept(error.response.data);
        } else if (!stopped) {
          setMessage("Could not confirm the sync request. Checking its status before allowing another request…");
        }
      } finally {
        inFlight = false;
        schedule(0);
      }
    };
    poll();
    return () => {
      stopped = true;
      clearTimeout(timer);
      startRef.current = () => {};
    };
  }, [enabled]);

  return {
    state,
    message,
    checking,
    disabled: checking || isActive(state),
    start: () => startRef.current(),
  };
}
