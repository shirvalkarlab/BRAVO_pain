#!/bin/bash
# Copy new Percept device exports from Dropbox (rclone) onto the Jetstream2 server and ingest them
# into BRAVO. Run on the Jetstream2 host, from anywhere:
#
#   bash /media/volume/pnlstore/BRAVO_pain/BRAVO/_agent_bridge/ingest_new_exports.sh           # dry run: counts only, writes nothing
#   bash /media/volume/pnlstore/BRAVO_pain/BRAVO/_agent_bridge/ingest_new_exports.sh --ingest  # copy and ingest
#
# Settings, read from the environment:
#   BRAVO_EXPORTS_REMOTE   rclone remote and folder holding the exports (default below; check it
#                          with `rclone lsd dropbox:`)
#   BRAVO_EXPORTS_SINCE    copy only files changed on Dropbox since this date (default 2026-09-29;
#                          "all" copies every export; files BRAVO already holds are skipped either way)
#
# Exports are ingested one at a time, oldest session first; an export already held (same bytes) is
# skipped, so running twice is safe. The copies carry the patient's name in their file names: they
# go to a gitignored folder and are deleted when the script ends, whatever happens. The two server
# loops pick up the new recordings by themselves (saved answers within 10 minutes, grids daily).
set -uo pipefail

REMOTE="${BRAVO_EXPORTS_REMOTE:-dropbox:RCS08}"
SINCE="${BRAVO_EXPORTS_SINCE:-2026-09-29}"
REPO=/media/volume/pnlstore/BRAVO_pain
IN="$REPO/BRAVO/_agent_bridge/incoming"
CONTAINER=bravo_pain-bravo-server-1
PARTICIPANT=2e3c75c00d7f4f37b53a048d195f11da          # RCS08
MODE="${1:---dry-run}"

if ! command -v rclone >/dev/null; then
  echo "rclone is not installed on this machine. Install it (no sudo needed):"
  echo "  curl -fsSL https://downloads.rclone.org/rclone-current-linux-amd64.zip -o /tmp/rclone.zip &&"
  echo "  unzip -oj /tmp/rclone.zip '*/rclone' -d ~/bin && chmod +x ~/bin/rclone"
  echo "then connect Dropbox: run 'rclone authorize dropbox' on your Mac, and 'rclone config' here"
  echo "(new remote named 'dropbox', type dropbox, paste the token the Mac printed)."
  exit 1
fi
if ! rclone lsd "${REMOTE%%:*}:" >/dev/null 2>&1; then
  echo "rclone has no working remote '${REMOTE%%:*}'. Configured remotes: $(rclone listremotes | tr '\n' ' ')"
  exit 1
fi

mkdir -p "$IN"
trap 'find "$IN" -name "*.json" -type f -delete 2>/dev/null' EXIT

AGE=()
[ "$SINCE" != "all" ] && AGE=(--max-age "$SINCE")
echo "copying exports from '$REMOTE' (changed since: $SINCE) ..."
if ! timeout 3600 rclone copy "$REMOTE" "$IN" --include "*.json" "${AGE[@]}"; then
  echo "COPY FAILED or ran past 1 hour; nothing ingested."
  exit 1
fi
echo "copied: $(find "$IN" -name '*.json' -type f | wc -l) export files"

run() {    # the folder-ingest command in the server container, with a time limit
  docker exec -w /usr/src/BRAVO -e BRAVO_INGEST_WARM=0 -e BRAVO_REMEMBER_REQUESTS=0 "$CONTAINER" \
    timeout --kill-after=30 "$1" python3 manage.py ingest_percept_folder \
    --participant "$PARTICIPANT" --folder /usr/src/BRAVO/_agent_bridge/incoming "${@:2}" 2>&1 \
    | grep -v -E ' (DEBUG|INFO) '
}

run 600 --dry-run
if [ "$MODE" != "--ingest" ]; then
  echo "dry run only: nothing was written. Re-run with --ingest to ingest the NEW files above."
  exit 0
fi
run 10800 --continue-on-error
echo "done. The copies in $IN are being deleted."
