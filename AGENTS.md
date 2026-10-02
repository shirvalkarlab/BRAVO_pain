# AGENTS.md

Instructions for any coding agent other than Claude Code (Codex and others). **`CLAUDE.md` is the
single source of truth: read it, and `HOUSE_RULES_writing_and_claims.md`, before any work.** Where
this file and `CLAUDE.md` disagree, `CLAUDE.md` wins. Rewritten 2026-09-27; the drop-in framework
text that was here (worktree workers, pull requests into `main`, clearing stashes) did not apply to
this repository and is in git history only.

BRAVO_pain is a research platform, not a framework: it turns recorded brain signal and pain reports
into a stimulation configuration a clinician programs into an implanted device by hand. Nothing here
writes to the device.

## The facts most likely to cause damage if missed (correct on 2026-09-27)

1. **Branch:** `PS_closedloop_deployment` is the default branch; work lands on it directly. There is
   no `main`; `v3.1.0` is a tag label, not a merge target.
2. **Push and identity are settled** (the PI, 2026-09-07): push this branch's meaningful work, with
   `git -c user.name="Prasad Shirvalkar" -c user.email="prasad.shirvalkar@ucsf.edu"` on every
   commit. Never rewrite pushed history, clear stashes or delete branches.
3. **No worktrees:** the server container mounts only the main checkout, so worktree code runs
   against nothing.
4. **Quality gates:** two test suites (both run inside the server container through
   `BRAVO/_agent_bridge/bridge_client.py`; a green run of one is not a green platform), the frontend
   build (required after any `Client/src` change; the built bundle is committed) and the page tests.
   No linter, type checker or formatter exists. **CI exists** (`.github/workflows/ci.yml`) and runs
   one suite, the page tests, the build and a secret scan on every push. Commands: `CLAUDE.md` §1.
5. **The durable record is `DECISIONS_and_open_items.md`**, not an issue tracker; read it before
   changing anything that looks obviously improvable.
6. **Patient data:** device export file names carry real patient names; keep that folder out of the
   repository. `RCS08` is the de-identified code.
7. `Client/src/database/resultCache.js`, `useCachedResult.js` and `RecomputeBar.js` may be edited
   (the PI lifted the old no-edit rule, 2026-10-02); a change comes with a cache test and the full
   page-test run.
8. **Plan approval is not a go-ahead to implement**; the PI gives that explicitly.
