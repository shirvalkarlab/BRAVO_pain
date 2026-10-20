# Manual sync application contract

The participant navbar offers **Sync all streams** to the participant institute's administrator. It submits a fixed private request; the web application never runs host commands or holds upstream credentials. Ordinary **Refresh view** only reloads stored results.

`POST /api/manualSync` accepts exactly `ParticipantId` and `RequestType` (`Status` or `Start`). Normal authenticated session access and CSRF are required, including when debug mode is enabled. The participant must match both the configured participant and institute. A new request returns 202; status and an already-running request return 200 with the same job identifier. Other institute members receive 403. Configuration errors return a sanitized 503.

## Private configuration and mounts

`BRAVO_MANUAL_SYNC_CONFIG_FILE` is optional and defaults to empty. Configure it only after the root-managed source and target workers are installed and checked. Its JSON contains exactly:

```json
{
  "request_directory": "/data/bravo/manual-sync/request",
  "status_directory": "/run/bravo-private/manual-sync/status",
  "target_participant_uid": "<deployment participant UID>",
  "target_institute_uid": "<deployment institute UID>",
  "owner_uid": 10001,
  "source_mode": "retained_files",
  "upstream_available": false
}
```

The UID placeholders must be replaced with verified 32-character lowercase hexadecimal identifiers. The config is mode 0600 and must be application-owned for the non-root web application to read it. The protocol also accepts root ownership when a root caller reads its own host configuration. Both directories are mode 0700 and application-owned; files are mode 0600, regular, single-link, and must not traverse symlinks. Use matching, reviewed protocol code on both hosts. Provision the directories durably before enabling the feature.

**The status directory must be mounted read-only in the application**, separately from the writable request directory. The config should likewise be on the existing private read-only mount. Root workers may write the shared status directory under the application filesystem identity, restoring their original identity afterward. Never expose the private parent directory or provider credentials through a public mount. Config validation cannot establish a Docker mount's read-only property; deployment acceptance must check it.

Set `source_mode` to `upstream_files` and `upstream_available` to true only after the exact upstream adapter and participant/device allowlist are verified. Retained-file mode explicitly tells the user that it copies files already on the lab server. The configuration contains no command, provider token, source path chosen by a browser, or arbitrary host option.

## Completion and recovery

The request is fixed `request.json`, protected by `.request.lock`; source and target publish `source-status.json` and `target-status.json`. All payloads are bounded to 16 KiB. Submission coalesces nonterminal jobs. Workers additionally enforce their host data lock, replay ledger, and cooldown.

Source completion means files have been exported; the UI shows **Files copied; import pending**. Source failure keeps the request active until the target has attempted independent REDCap and Oura updates. Only a matching target result with all four streams successful can display overall completion. Partial failures retain separate stream results and never claim missing data were fetched. Unknown neural device identities require review; retained files are not silently assigned to a participant.

The UI polls while a job is active and prevents overlapping polls and repeated submissions. Closing the dialog does not cancel work. A service interruption preserves the last known result and reports unavailable status. There is no unsafe automatic timeout-based replacement of a possibly running job: an operator must reconcile the worker ledger/status under the host lock before publishing a terminal failure. Inspect the worker deployment guide for its exact service, backup, and acceptance sequence.

Local acceptance uses synthetic private mailboxes, real disposable Django session/CSRF tests, and frontend tests. Live acceptance additionally requires the deployed build, read-only status mount, exact target identities, normal admin and non-admin access, source/target worker guards, authenticated per-stream readback, and a duplicate click producing one job. No test command should point to production storage.
