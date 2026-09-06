#!/usr/bin/env bash
# Fetch reviewed sources once per session; never integrate application changes.
set -euo pipefail
repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_dir"
note() { printf '[BRAVO bootstrap] %s\n' "$*"; }
fail() { note "ERROR: $*" >&2; exit 1; }
git rev-parse --is-inside-work-tree >/dev/null || fail 'not a Git checkout'

verify_remote() {
  local actual
  actual="$(git remote get-url --all "$1")" || fail "missing remote $1"
  # Do not print unexpected URLs: they may contain credentials.
  [[ "$actual" == "$2" ]] || fail "remote $1 does not match the documented URL; left unchanged"
}
verify_remote origin https://github.com/Fixel-Institute/BRAVO.git
verify_remote shirvalkar https://github.com/shirvalkarlab/BRAVO_pain.git
if git remote | grep -qx aditya-private; then
  verify_remote aditya-private https://github.com/ABehal2020/BRAVO.git
fi

dirty_at_start="$(git status --porcelain --untracked-files=normal)"
if [[ -n "$dirty_at_start" ]]; then
  note 'Dirty worktree: fetching only; ALL local branches and files will remain unchanged.'
  git status --short
fi
fetch_failed=0
git fetch --prune --no-tags origin '+refs/heads/*:refs/remotes/origin/*' || fetch_failed=1
git fetch --no-tags shirvalkar '+refs/heads/PS_closedloop_deployment:refs/remotes/shirvalkar/PS_closedloop_deployment' || fetch_failed=1
[[ "$fetch_failed" == 0 ]] || fail 'source fetch failed; no local branches updated'

partial=0
clean_now() { [[ -z "$(git status --porcelain --untracked-files=normal)" ]]; }
if [[ -z "$dirty_at_start" ]] && clean_now; then
  if ! git show-ref --verify --quiet refs/heads/aditya; then
    note 'Local aditya branch is missing; no branch switch or local updates.'
    exit 1
  fi
  if [[ "$(git branch --show-current)" != aditya ]]; then
    git switch aditya || fail 'could not switch to aditya; no local source branches updated'
  fi
fi

review_branch() {
  local branch="$1" upstream="$2" old new
  if ! old="$(git rev-parse --verify "refs/heads/$branch" 2>/dev/null)"; then
    note "$branch is missing; create its tracking branch deliberately after review"
    partial=1; return
  fi
  if ! new="$(git rev-parse --verify "refs/remotes/$upstream" 2>/dev/null)"; then
    note "$upstream is missing after fetch; $branch left unchanged"
    partial=1; return
  fi
  if [[ "$old" == "$new" ]]; then
    note "$branch is current at ${old:0:8}"; return
  fi
  if ! git merge-base --is-ancestor "$old" "$new"; then
    note "$branch has unique commits or diverged from $upstream; left unchanged"
    partial=1; return
  fi
  if [[ -n "$dirty_at_start" ]] || ! clean_now; then
    note "$branch is behind $upstream; dirty worktree leaves it unchanged"
    partial=1; return
  fi
  if git worktree list --porcelain | grep -qx "branch refs/heads/$branch"; then
    note "$branch is checked out in a worktree; left unchanged"
    partial=1; return
  fi
  # Compare-and-swap refuses a concurrent update; ancestry was checked above.
  git update-ref -m "BRAVO bootstrap fast-forward from $upstream" "refs/heads/$branch" "$new" "$old" || fail "concurrent update of $branch; review state"
  note "$branch fast-forwarded to ${new:0:8}"
}
review_branch development origin/development
review_branch PS_closedloop_deployment shirvalkar/PS_closedloop_deployment
note "Working branch: $(git branch --show-current)"
if [[ "$partial" == 1 ]]; then
  note 'Complete with local source branches intentionally left unchanged; review messages above.'
else
  note 'Complete. Application integration, deployment and pushes require separate review.'
fi
