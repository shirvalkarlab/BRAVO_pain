# Agent Instructions

> ## ⚠ READ THIS BEFORE ANY OTHER LINE IN THIS FILE
>
> **This file arrived as part of a drop-in framework and its first paragraph does not describe this
> repository.** BRAVO_pain is not a framework; it is a research platform that turns recorded brain
> signal into a stimulation configuration a clinician programs into an implanted device by hand.
>
> **`CLAUDE.md` §10 overrides this file wherever they disagree, and three disagreements are
> dangerous rather than cosmetic:**
>
> 1. **DO NOT PUSH, AND DO NOT CHOOSE A COMMIT IDENTITY.** Mode B below says work is not complete
>    until `git push` succeeds, says never to stop before pushing, and says never to say "ready to
>    push when you are". **In this repository, pushing is the principal investigator's decision and
>    so is whose name goes on the commits** — that question has been asked three times and is still
>    open, which is why the existing local commits carry a machine identity. This branch is
>    deliberately ahead of every remote. Following Mode B would put commits into the permanent
>    record of a research repository under a name nobody authorised.
> 2. **THERE IS NO `main` BRANCH.** Mode B says pull requests target `main` and describes
>    trunk-based development from it. The default branch here is **`v3.1.0`** and the working branch
>    **`PS_closedloop_deployment`** is long-lived — 61 commits of it were merged as pull request #9
>    and work continued on it afterwards.
> 3. **"RUN QUALITY GATES — TESTS, LINTER, TYPE CHECKER, BUILD" NAMES TWO THINGS THAT DO NOT
>    EXIST.** There is no linter, no type checker, no formatter and no continuous integration
>    anywhere in this repository. The gates are exactly three: the container test suite, the host
>    test suite, and the frontend build. **The two suites run in different places and a green run of
>    one is not a green run of the platform.** Commands are in `CLAUDE.md` §1.
>
> Also note that `.claude/rules/`, `.claude/skills/`, `.claude/hooks/` and `.claude/agents/` exist
> on this machine **but are gitignored** (`.gitignore` line 336), `./artifacts/` exists and is
> empty, and `.claude/commands/` and `./scratchpad/` **do not exist**, so nothing in this file may be
> reported as loaded or available because a heading names it. `GitHub Issues` is not in use either —
> the durable list is `DECISIONS_and_open_items.md`. The plan itself is kept with the
> `planning-with-files` plugin; `CLAUDE.md` §4 says how.
>
> **Everything below this box is the unmodified framework text. It is useful for the worktree
> isolation protocol and the recovery cases, which have no equivalent here and are worth keeping.**

---

This repository is a drop-in framework for Claude Code: specialized commands, reusable skills, and safety hooks for AI-assisted development. These instructions apply to any coding agent working in this repo, not just Claude Code.

## Where Things Live

- `.claude/` — skills (command-style workflows + knowledge library), rules, hooks, and agent/worker definitions
- `./artifacts/` — durable planning documents (PR-FAQs, PRDs, ADRs, design specs, plans); committed to the repo
- `./scratchpad/` — ephemeral working notes and draft content; gitignored, disposable

## Task Tracking

Two-tier convention:

1. **Durable record**: GitHub Issues (or a committed `ISSUES.md` for repos without a tracker).
2. **In-flight work**: your tool's native task/todo list, owned by whichever agent is orchestrating — sub-agents receive focused prompts and return results rather than sharing mutable state.
3. **Handoffs**: reference concrete artifacts under `./artifacts/` by file path.

## Landing the Plane (Session Completion)

This protocol has two modes. Check which one applies before following either — it depends on whether the current agent's frontmatter declares `isolation: worktree`.

### Mode A — Isolated workers (`isolation: worktree` in agent frontmatter)

An isolated worker runs in its own throwaway git worktree, not the shared checkout — this exists specifically to stop parallel workers from racing on one git index. Because the worktree is throwaway and the branch is not the integration branch, the worker does not push; the orchestrator does.

1. **Run quality gates** (if code changed) — tests, linter, type checker, build
2. **Commit** on the assigned worktree branch — atomic, complete, working changes only
3. **Report back to the orchestrator**: the commit SHA and a summary of files changed, tests added/modified, and any follow-up work discovered
4. **Stop there** — do NOT `git push`, do NOT merge, do NOT switch branches. The orchestrator merges the worktree branch into the feature branch, re-runs gates, pushes, and cleans up the worktree.

#### Recovery

Three failure cases and how the orchestrator recovers from each:

1. **Worker stops at its `maxTurns` ceiling without a completion report.** Inspect the worktree state (`git -C <worktree-path> status`, `git -C <worktree-path> log`) to see what was actually done. Resume the SAME worker with a focused continuation message — its context is preserved — rather than respawning a new worker from scratch.
2. **Orchestrator session is lost after a worker committed but before merge.** Reclaim in-flight work by listing worktree branches (`git branch --list 'worktree-agent-*'`) and diffing each against the feature branch (`git log <branch> --not <feature-branch>`) to find unlanded commits. Review what's there, then merge or discard deliberately — do not assume the commits are safe to drop.
3. **`git merge --ff-only` is rejected because the feature branch advanced** (e.g., parallel workers landed from the same base). Rebase the worker branch onto the current feature-branch tip, re-run quality gates on the rebased result, then retry the fast-forward merge.

### Mode B — Non-isolated agents and sessions (no `isolation: worktree`)

**When ending a work session**, complete ALL steps below. Work is NOT complete until `git push` succeeds.

1. **File issues for remaining work** — create tracker issues for anything that needs follow-up
2. **Run quality gates** (if code changed) — tests, linter, type checker, build
3. **Update issue status** — close finished work, update in-progress items
4. **Push to remote** — this is mandatory:
   ```bash
   git pull --rebase
   git push
   git status  # MUST show "up to date with origin"
   ```
5. **Clean up** — clear stashes, prune merged branches
6. **Verify** — all changes committed AND pushed
7. **Hand off** — leave clear context (and artifact references) for the next session

**Critical rules:**
- Work is NOT complete until `git push` succeeds
- Never stop before pushing — that leaves work stranded locally
- Never say "ready to push when you are" — push it yourself
- If push fails, resolve and retry until it succeeds
- PRs target `main` — trunk-based: a dependent unit waits for its prerequisite to merge to `main` and branches from there, rather than stacking on the prerequisite's branch
