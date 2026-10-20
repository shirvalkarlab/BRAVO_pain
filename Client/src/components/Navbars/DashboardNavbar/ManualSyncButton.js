import React, { useEffect, useRef, useState } from "react";
import { Alert, Button, CircularProgress, Dialog, DialogActions, DialogContent, DialogTitle, Stack, Typography } from "@mui/material";
import { SessionController } from "database/session-control";
import { cacheScope } from "views/Reports/RedcapTimeline/requestScope";
import { SYNC_COMPLETED_EVENT } from "utils/syncEvents";

const streams = [["neural", "Neural files"], ["clinic", "Clinic workbooks"], ["redcap", "REDCap surveys"], ["oura", "Oura observations"]];
const labels = { queued: "Waiting", running: "Updating", exported: "Files copied; import pending", succeeded: "Complete", failed: "Failed", blocked: "Waiting for a failed step to be resolved", not_configured: "Not connected" };
const errors = { changed_source: "Source report changed; review required.", unknown_device: "Unrecognized device; review required.", failed: "The update failed.", maintenance_active: "A backup is in progress.", not_configured: "This source is not connected.", source_failed: "The source file update failed.", import_failed: "The copied files could not be imported.", provider_failed: "The connected service could not be updated.", worker_unavailable: "The sync service needs attention.", busy: "Another update is running.", deferred: "Source files are still changing; try again later." };
const active = (job) => job && ["queued", "running"].includes(job.state);

export default function ManualSyncButton({ participantUid }) {
  const [snapshot, setSnapshot] = useState(null);
  const [open, setOpen] = useState(false);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState("");
  const identity = useRef(null);
  const scope = cacheScope();
  const notified = useRef(null);
  const snapshotOwner = useRef(null);
  const current = token => identity.current === token && cacheScope() === token.scope;
  const pending = useRef(false);
  const polling = useRef(null);

  const readStatus = async (token, clearError = true) => {
    if (polling.current === token) return;
    polling.current = token;
    try {
      const response = await SessionController.query("/api/manualSync", { ParticipantId: participantUid, RequestType: "Status" });
      if (current(token)) { snapshotOwner.current=token; setSnapshot(response.data); if (clearError) setError(""); }
    } catch (failure) {
      if (!current(token)) return;
      if (failure.response?.status === 403) setSnapshot({ CanSync: false });
      else if (failure.response?.status === 503) { setSnapshot(previous => ({ ...previous, CanSync: true, Available: false })); setError("Synchronization is currently unavailable. Please contact the platform administrator."); }
      else setError("Could not check synchronization status. Existing data remain available.");
    } finally { if (polling.current === token) polling.current = null; }
  };

  useEffect(() => {
    const token = {scope};
    identity.current = token;
    setSnapshot(null); setOpen(false); setError(""); setStarting(false);
    pending.current = false; polling.current = null;
    notified.current = null; snapshotOwner.current=null;
    if (participantUid && scope) readStatus(token);
    return () => { if (current(token)) identity.current = null; };
  }, [participantUid, scope]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!active(snapshot?.Job)) return undefined;
    const token = identity.current;
    const interval = setInterval(() => readStatus(token), 5000);
    return () => clearInterval(interval);
  }, [participantUid, scope, snapshot?.Job?.state]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const job = snapshot?.Job;
    if (snapshotOwner.current !== identity.current || !job?.job_id || !["succeeded", "failed"].includes(job.state) || !scope || cacheScope() !== scope) return;
    const marker = `${job.job_id}:${job.updated_at}:${job.state}`;
    if (notified.current === marker) return;
    notified.current = marker;
    window.dispatchEvent(new CustomEvent(SYNC_COMPLETED_EVENT, { detail: { participantUid, scope, state: job.state } }));
  }, [participantUid, scope, snapshot]);

  const start = async () => {
    setOpen(true);
    if (pending.current || active(snapshot?.Job) || !snapshot?.Available) return;
    pending.current = true; setStarting(true); setError("");
    const token = identity.current;
    try {
      const response = await SessionController.query("/api/manualSync", { ParticipantId: participantUid, RequestType: "Start" });
      if (current(token)) {snapshotOwner.current=token;setSnapshot(response.data);}
    } catch (failure) {
      if (current(token)) {
        setError("Could not confirm the request. Check the status before trying again.");
        await readStatus(token, false);
      }
    } finally {
      if (current(token)) { pending.current = false; setStarting(false); }
    }
  };

  if (!participantUid || !scope || !snapshot?.CanSync) return null;
  const job = snapshot.Job;
  const working = starting || active(job);
  return <>
    <Button size="small" variant="outlined" onClick={start} disabled={starting || !snapshot.Available} sx={{ mx: 1, whiteSpace: "nowrap" }}>
      {working ? "Sync in progress" : "Sync all streams"}
    </Button>
    {!snapshot.Available && <Typography variant="caption" role="status">Sync unavailable</Typography>}
    <Dialog open={open} onClose={() => setOpen(false)} fullWidth maxWidth="sm" aria-labelledby="manual-sync-title">
      <DialogTitle id="manual-sync-title">Sync all streams</DialogTitle>
      <DialogContent>
        <Stack spacing={2}>
          <Typography variant="body2">Update the stored data for this participant. You can close this window while the sync continues.</Typography>
          <Typography variant="body2">{snapshot.Sources?.Mode === "upstream_files"
            ? "Neural files and clinic workbooks will be fetched from their connected source before import."
            : "Neural files and clinic workbooks use the files already available on the lab server."}</Typography>
          <Typography variant="body2">Fetch latest upstream files: {snapshot.Sources?.UpstreamAvailable ? "available" : "not connected"}.</Typography>
          {error && <Alert severity="error">{error}</Alert>}
          {working && <Stack direction="row" spacing={1} alignItems="center"><CircularProgress size={18} /><Typography role="status">{starting ? "Submitting request…" : job.state === "queued" ? "Waiting for the sync service…" : "Sync is running…"}</Typography></Stack>}
          {job && <ul aria-label="Data stream progress" style={{ paddingLeft: 20, margin: 0 }}>
            {streams.map(([key, name]) => <li key={key}><Typography variant="body2"><strong>{name}:</strong> {labels[job.streams[key].state] || "Status unavailable"}{job.streams[key].error_code && ` — ${errors[job.streams[key].error_code] || "Please contact the platform administrator."}`}</Typography></li>)}
          </ul>}
          {job?.state === "succeeded" && <Alert severity="success">All four streams are updated. The Aditya data-stream views load the latest stored data automatically.</Alert>}
          {job?.state === "failed" && <Alert severity="error">Some streams could not be updated. Completed steps are shown above. The Aditya data-stream views reload available stored data; failed streams may still show older observations. Ask the platform administrator to check the failed steps.</Alert>}
          {job?.last_success_at && <Typography variant="caption">Last successful manual sync: {new Date(job.last_success_at * 1000).toLocaleString()}</Typography>}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={() => setOpen(false)}>Close</Button>
        {job && !working && <Button onClick={() => window.location.reload()}>Refresh view</Button>}
      </DialogActions>
    </Dialog>
  </>;
}
