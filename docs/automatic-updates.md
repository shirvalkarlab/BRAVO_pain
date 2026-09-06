# Nightly Aditya maintenance

Requested by Aditya on September 3, 2026. The Codex heartbeat `bravo-nightly-maintenance` is scheduled for 03:00 Pacific daily on the current machine. It is the single automatic maintenance orchestrator. The application sync daemon serves manual requests only; its independent nightly timer has been removed from the Aditya deployment.

Watch `origin/development` and `shirvalkar/PS_closedloop_deployment` independently. Aditya removed the 48-hour observation hold on September 6, 2026 for the current run and future nightly maintenance. Fetch and review current Fixel changes first, then selectively adapt Prasad changes during the authorized window. Missing observation history never delays integration. Record exact source heads and recheck them before promotion; a changed head requires renewed review and validation, not a timed hold.

Routine in-scope execution is already authorized, including when Aditya gives approval from another computer. The 03:00 job starts without asking for a manual go-ahead. Platform safeguards and genuinely missing essential information still apply. Preserve dirty work and divergent tracking branches; never force updates, stash automatically, or discard changes.

Prepare reviewed updates in an isolated candidate checkout based on the currently deployed Aditya revision. Review and selectively adapt Prasad changes; review Fixel development changes before integrating. Preserve Aditya's canonical REDCap, Oura, and neural QC, source exclusions, timestamp corrections, input manifests, permissions, feature availability, and existing customizations. Branch stability alone does not establish compatibility.

Before promoting a candidate, run focused regressions, canonical-data consistency checks, authenticated endpoint checks, and application health checks. Test upgrades against an isolated database copy when migrations are involved. Failed checks or unresolved conflicts leave the existing deployment running and require a concise notification. Do not claim a research method is clinically validated or ready for programming because its software tests pass.

Serialize promotions. Recheck both the source head and deployed Aditya revision immediately before promotion. If either relevant revision changed, refresh the affected review and revalidate the candidate. Back up state before any migration, keep the previous application image available, and define migration-compatible rollback before replacement. Never roll back patient data by silently restoring an older database over newer records.

## Nightly sequence

Use one daily maintenance run between 03:00 and 07:00 America/Los_Angeles, at most four hours. A late start gets only the remaining time before 07:00; do not catch up automatically outside that window. This extends the former two-hour window at the user's September 5, 2026 request. Explicit user pauses still stop work; the longer window does not authorize resuming a paused task. The required order is:

1. Fetch and record both Fixel development and Prasad source heads; review current updates immediately, with no 48-hour hold.
2. Integrate eligible Fixel development changes first. Then integrate eligible Prasad changes against that validated candidate. If only one is eligible, process that source alone. Validate and deploy the accepted candidate before data processing. If a stage fails, retain the last validated application; continue data sync on that application only when compatible, and report the failed integration.
3. Sync the configured REDCap, Oura, and neural inputs, preserving their approved exclusions, timestamp corrections, and provenance.
4. Recompute affected inexpensive calculations and prewarm routine report caches (including the compact Oura–FreeReps overview) plus pain-score/data-availability defaults using the newly deployed code and completed data revision. Full biomarker searches, heavy optimizer analyses, and closed-loop deployment are explicitly excluded from automatic prewarming. Reuse unchanged results only when data, QC policy, processing configuration, and analysis code identities match.
5. Verify readiness and record completed/skipped/failed stages. Notify on meaningful failure, completed integration, or required action; unchanged checks remain quiet.

Aim for routine viewing by 20+ people to return/render within 10 seconds wherever feasible. Expensive research calculations run only on demand; valid completed results can be reused. Arbitrary new parameter combinations may still require a first calculation; prewarming cannot cover every possible analysis. Persistent completed caches survive application restarts, and simultaneous equivalent requests share one job.

The one-shot data/cache phase is:

```sh
docker compose --env-file .env.appliance exec -T bravo-sync python3 manage.py run_rcs08_maintenance
```

Run from the BRAVO checkout after the eligible source-update stages. An optional `--deadline-epoch` may shorten, never extend, the 07:00 cutoff. The supervisor also caps nightly worker time at four hours; the explicit manual-sync worker retains its existing two-hour cap. It supervises a separate worker, shares a preparation lock with manual sync, stops the worker process group by its deadline, and invalidates report revisions if interrupted. Complete committed streams remain; remaining work is retryable. Optional preparation is skipped when too little time remains. Inspect returned stage statuses, not just command exit status.

The schedule exists now; full ordered overnight execution remains unverified until a scheduled run has actually completed. The current goal owns candidate deployment and local deadline/lock tests. Destination-laptop migration requires verifying paths, runtime and the automation there; do not leave two host automations enabled.

After replacement, verify `scripts/bravo-appliance check`, the intended localhost address, authenticated application responses, and deployed Aditya image identity. Verify Chrome's actual loaded page using text-only inspection when a browser session is available. No screenshots, screen sharing, Tailscale, public tunnel, or Prasad deployment is part of this workflow. Record source heads, integration decisions, validation evidence, deployed image, and rollback reference for each attempt.

Keep the single current-machine automation; move it during the future hosted-laptop setup only after verifying machine paths and deployment configuration. Notify on integration/deployment completion, failure, or required user action; unchanged upstream state needs no routine notification.
