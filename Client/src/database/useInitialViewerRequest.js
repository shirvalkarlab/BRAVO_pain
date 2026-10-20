import { useEffect } from "react";

// Bootstrap the ordinary saved-data read for a viewer. Moving a filter later
// must not quietly invalidate or recompute the displayed result.
export function useInitialViewerRequest(readOnly, participant, request, setRequest, snapshot) {
  useEffect(() => {
    if (readOnly && participant && !request) setRequest(snapshot());
  }, [readOnly, participant, request]); // eslint-disable-line react-hooks/exhaustive-deps
}
