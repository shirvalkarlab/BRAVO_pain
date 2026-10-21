# BRAVO lab Aditya branch

- This is the public `shirvalkarlab/BRAVO_pain` Aditya integration snapshot. Read
  `docs/release-status.md`, `docs/publication-provenance.md` and the user guide.
- Preserve dirty/unrelated work and existing history. Do not reset, force-push,
  import unrelated source history or publish clinical data/configuration.
- Keep lab-facing code and documentation self-contained. Do not reference personal
  repositories, their branches or local checkout paths.
- Code imports are reviewed snapshots. Fixel supplies the base; Prasad owns
  scientific/backend semantics; Aditya supplies the presentation layer.
- Keep raw inputs, participant identities, clinical evidence, credentials,
  operational receipts, private models and deployment configuration outside Git.
  Public examples and tests must use independently constructed synthetic inputs.
- Tests use disposable database/cache/storage. Do not run live/store tests or
  provider imports against existing services merely to check a change.
- Preserve units, provenance, missing-data semantics and scientific uncertainty.
  Never infer participant anatomy, stimulation limits or eligibility from a code.
- Public publication must pass exact-candidate CI and independent review. Hosting
  is a separate explicitly authorized action with live identity/access checks.
- Run `scripts/session_bootstrap.sh` to inspect identity and status without changing
  branches. The optional `--fetch` refreshes only the lab `aditya` remote reference.
- Use non-capture browser inspection; do not take screenshots or enable browser
  AppleScript JavaScript for this project.
