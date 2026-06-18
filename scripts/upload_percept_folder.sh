#!/usr/bin/env bash
# Upload Percept session JSONs to BRAVO via the API (POST /api/uploadData), instead of the
# browser drag-and-drop. The web uploader is slow/fragile for many or large files (FilePond fires
# concurrent XHRs that queue on the dev server, and even an already-uploaded 500 KB file can spin
# for a minute). This driver logs in once and POSTs each file sequentially — ~0.2 s per request,
# and the server dedups by content hash (HTTP 301 = already present, skipped).
#
# Usage:
#   scripts/upload_percept_folder.sh --folder <DIR> --participant <UID> [options]
#
# Options:
#   --folder DIR        folder to scan for .json session files (required)
#   --participant UID   BRAVO participant uid to attach uploads to (required)
#   --match REGEX       only upload files whose path matches this case-insensitive regex
#                       (default: all *.json). Use to filter a MIXED-patient folder, e.g.
#                       --match 'rcs08' to skip other subjects.
#   --host URL          BRAVO base URL (default: http://localhost)
#   --email ADDR        login email    (or set BRAVO_UPLOAD_EMAIL)
#   --password PW       login password (or set BRAVO_UPLOAD_PASSWORD; no default -- required)
#   --institute NAME    institute (default: "" = the logged-in user's institute)
#   --datatype TYPE     upload DataType (default: DefaultType — the working path for .json;
#                       MedtronicJSON errors on missing automatic_concatenation)
#   --no-recursive      do not descend into subfolders (default: recursive)
#
# Example:
#   scripts/upload_percept_folder.sh \
#     --folder "$HOME/Library/CloudStorage/OneDrive-UCSF/Desktop/PNL/RCS008 jsons" \
#     --participant 1eda36458758461383721208bbe6bb87 --match 'rcs08'
set -euo pipefail

FOLDER="" PARTICIPANT="" MATCH="" HOST="http://localhost"
# Credentials come from the environment (BRAVO_UPLOAD_EMAIL / BRAVO_UPLOAD_PASSWORD) or --email/
# --password. No hardcoded default password -- a committed credential is a security risk and would
# also stop working the moment the demo account changed.
EMAIL="${BRAVO_UPLOAD_EMAIL:-}" PASSWORD="${BRAVO_UPLOAD_PASSWORD:-}" INSTITUTE="" DATATYPE="DefaultType"
RECURSIVE=1
while [ $# -gt 0 ]; do
  case "$1" in
    --folder) FOLDER="$2"; shift 2;;
    --participant) PARTICIPANT="$2"; shift 2;;
    --match) MATCH="$2"; shift 2;;
    --host) HOST="$2"; shift 2;;
    --email) EMAIL="$2"; shift 2;;
    --password) PASSWORD="$2"; shift 2;;
    --institute) INSTITUTE="$2"; shift 2;;
    --datatype) DATATYPE="$2"; shift 2;;
    --no-recursive) RECURSIVE=0; shift;;
    *) echo "Unknown option: $1" >&2; exit 2;;
  esac
done
[ -n "$FOLDER" ] && [ -n "$PARTICIPANT" ] || { echo "ERROR: --folder and --participant are required" >&2; exit 2; }
[ -d "$FOLDER" ] || { echo "ERROR: folder not found: $FOLDER" >&2; exit 2; }
[ -n "$EMAIL" ] && [ -n "$PASSWORD" ] || { echo "ERROR: login credentials required -- pass --email/--password or set BRAVO_UPLOAD_EMAIL/BRAVO_UPLOAD_PASSWORD" >&2; exit 2; }

JAR="$(mktemp)"; trap 'rm -f "$JAR"' EXIT
echo "Logging in to $HOST as $EMAIL ..."
code=$(curl -s -c "$JAR" -b "$JAR" -X POST -H 'Content-Type: application/json' \
  -d "{\"Email\":\"$EMAIL\",\"Password\":\"$PASSWORD\"}" "$HOST/api/login" -o /dev/null -w '%{http_code}')
[ "$code" = "200" ] || { echo "ERROR: login failed (HTTP $code)" >&2; exit 1; }

# Collect files (NUL-delimited; handles spaces). -iname for case-insensitive .json.
FIND_ARGS=("$FOLDER")
[ "$RECURSIVE" -eq 1 ] || FIND_ARGS+=(-maxdepth 1)
FIND_ARGS+=(-type f -iname '*.json' -print0)

total=0 ok=0 dup=0 fail=0 skip=0
while IFS= read -r -d '' f; do
  if [ -n "$MATCH" ] && ! echo "$f" | grep -iqE "$MATCH"; then skip=$((skip+1)); continue; fi
  total=$((total+1))
  code=$(curl -s -c "$JAR" -b "$JAR" -X POST "$HOST/api/uploadData" \
    -F "ParticipantId=$PARTICIPANT" -F "DataType=$DATATYPE" -F "Institute=$INSTITUTE" \
    -F 'Metadata={"device_location":"","automatic_deidentification":false,"infer_from_device":true,"automatic_concatenation":false}' \
    -F "File=@$f" -o /dev/null -w '%{http_code}')
  case "$code" in
    200) ok=$((ok+1)); tag="OK   ";;
    301) dup=$((dup+1)); tag="DUP  ";;
    *)   fail=$((fail+1)); tag="FAIL($code)";;
  esac
  printf "[%4d] %s  %s\n" "$total" "$tag" "$(basename "$f")"
done < <(find "${FIND_ARGS[@]}")

echo "----"
echo "Done: $ok uploaded, $dup duplicates (skipped), $fail failed, $skip filtered out (of $((total+skip)) json files)."
[ "$fail" -eq 0 ]
