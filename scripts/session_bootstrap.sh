#!/usr/bin/env bash
# Read-only identity/status audit; optional fetch touches only the remote aditya ref.
set -euo pipefail
repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
url="$(git -C "$repo_dir" remote get-url origin)"
if [[ "$url" != 'https://github.com/shirvalkarlab/BRAVO_pain.git' && "$url" != 'git@github.com:shirvalkarlab/BRAVO_pain.git' ]]; then
  printf 'Unexpected origin: %s; left unchanged\n' "$url" >&2; exit 1
fi
case "${1:-}" in
  '') ;;
  --fetch) git -C "$repo_dir" fetch --no-tags origin refs/heads/aditya:refs/remotes/origin/aditya ;;
  *) printf 'Usage: %s [--fetch]\n' "$0" >&2; exit 2 ;;
esac
git -C "$repo_dir" log -1 --format='%h %cI %s'
git -C "$repo_dir" status --short --branch
printf 'No checkout/reset/stash/merge or application execution performed.\n'
