# BRAVO standalone checkout instructions

These instructions travel with the private `aditya` source release. Read any
parent workspace instructions too; do not replace or weaken them.

## Session start and Git

- Once per task/resumed session, run `scripts/session_bootstrap.sh` from this
  checkout. If the parent workspace bootstrap has already run during this
  session, do not run another bootstrap. Report remote mismatches, fetch errors,
  dirty worktrees, missing branches and divergence; never force an update.
- `aditya` is the application working branch. `development` tracks
  `origin/development`; `PS_closedloop_deployment` tracks
  `shirvalkar/PS_closedloop_deployment`. Keep both source branches pristine.
- With any tracked or untracked local work, fetch only: do not switch, stash,
  reset, merge, rebase, discard, or update ANY local branch automatically.
- Review Fixel changes first, then selectively review/adapt Prasad changes.
  Bootstrap is not integration permission. Preserve the private published
  ancestry; never overwrite it with older local history or force-push.
- Use the installed rigorous-project-workflow skill for substantive work.
  Commit coherent reviewed units regularly, stage exact paths, and exclude
  private assets/results. Follow `docs/workflow/validation.md` and
  `docs/workflow/git-checkpoints.md` when present. Acceptance requires the actual
  published SHA's CI result plus relevant private-data and live application checks.
- Push only to explicitly authorized destinations. Public lab publication
  requires the owner's separate approval; private publication is not that approval.

## Live application and credentials

- Before reporting readiness after startup/replacement/restore, run
  `scripts/bravo-appliance check`, verify the deployed Aditya source/image, and
  inspect the actual Chrome URL and loaded BRAVO page. HTTP 200 alone is insufficient.
- Use text-only browser inspection. Never use screenshots, screen sharing,
  capture helpers, or enable Chrome's AppleScript JavaScript setting.
- For authorized local checks, reuse normal login and existing credentials in
  ignored owner-only `secrets/local-test-accounts.json`. Prefer viewer access;
  use admin only for a feature requiring it. Never print credentials or store
  them in Git, logs, documentation or messages. Do not bypass authentication.
- Sign-in does not authorize new accounts, credential changes, data sync or
  scientific edits. Follow the current task's scope and existing authorization.

## Data, hosting and maintenance

- Read `README.md`, `docs/local-deployment.md`, `docs/automatic-updates.md`, and
  `docs/workflow/weekly-review.md` before hosting or scheduler changes.
- Resolve this machine's actual neural input, comparison input and Dropbox export
  paths. Do not copy another user's absolute paths or regenerate restored keys.
- Keep credentials, participant models, processing policies, private operational
  ledgers and data outside Git. Preserve source originals; apply the documented
  de-identification path before importing raw Percept reports into BRAVO.
- Only one host owns nightly/weekly jobs. Verify the destination before disabling
  the old schedule and enabling the replacement. CLI installation alone does not
  establish authenticated connectors or working desktop automations.
- Preserve the user's current scientific decisions. Hold uncertain integration
  portions and record evidence, a recommendation and the outstanding question.
- Plots must be scientifically accurate, legible and interpretable to a lab
  member without code knowledge or tooltip access. Preserve missing-data gaps,
  provenance, units, hemisphere labels and configured-versus-observed distinctions.
