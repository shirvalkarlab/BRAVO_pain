#!/usr/bin/env python3
"""Re-import every Medtronic JSON for a participant through the BRAVO upload API.

Use this after deleting a participant's recordings (e.g. to clear records that had a bad implant
date) to repopulate the database from the raw exports. It walks a folder of Percept session JSONs
and POSTs each to /api/uploadData via the existing BRAVOPlatformRequest client — the SAME path the
web UI uses, so every file is decoded by the current pipeline (correct timestamps, center-frequency
stamping, chronic-trend extraction, all of it).

The server DEDUPLICATES by content: a file already stored returns HTTP 301 and is counted as
"already present" (not re-decoded). So this script is safe to re-run; only genuinely-missing files
are ingested.

AUTH: needs a Secure API key for your account. Get it from the BRAVO UI (Profile -> API access) or
your admin. Pass it via the BRAVO_API_KEY env var (preferred) or --api-key.

USAGE (run on the HOST — it talks to the server over HTTP, so it does NOT need to be inside the
container; just point --server at the running instance):

    export BRAVO_API_KEY=xxxxxxxx
    python3 reimport_rcs08.py \
        --folder "/Users/pshirvalkar/Library/CloudStorage/OneDrive-UCSF/Desktop/PNL/RCS008 jsons" \
        --participant RCS08 \
        --server http://localhost:27286 \
        --dry-run            # list what WOULD upload, contact nothing

    # then drop --dry-run to actually upload.

Notes:
- --participant matches an EXISTING participant by name or uid (case-insensitive). It does NOT
  create one; create the participant once in the UI first, then re-import into it.
- Folders are walked recursively, so the Stage 1/ subfolder is included.
- A small inter-request delay keeps the threaded decode + per-hash lock from thrashing on a big
  batch; tune with --delay.
"""
import argparse
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

# Import the platform client from this repo (script lives in BRAVO/ next to it).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from BRAVORequestAPI import BRAVOPlatformRequest


def find_jsons(folder):
    out = []
    for root, _dirs, files in os.walk(folder):
        for f in files:
            if f.lower().endswith(".json"):
                out.append(os.path.join(root, f))
    return sorted(out)


def _pinfo(p):
    """Pull (uid, name) from a participant dict, tolerating the API's capitalized keys
    (get_info returns 'Id'/'Name') as well as lowercase variants."""
    uid = p.get("Id") or p.get("uid") or p.get("id") or ""
    name = p.get("Name") or p.get("name") or ""
    return str(uid), str(name)


def resolve_participant(api, wanted):
    """Return the participant (uid, name) matching `wanted` (a name or uid), or (None, None).

    The /api/queryParticipants response is a LIST of get_info() dicts keyed 'Id'/'Name'. Under an
    active study with deidentification, 'Name' is replaced by the uid, so we match on uid too.
    """
    parts = api.QueryParticipants() or []
    w = str(wanted).strip().lower()
    # Exact uid match first (works even when names are deidentified), then name match.
    for p in parts:
        uid, name = _pinfo(p)
        if uid.lower() == w:
            return uid, name
    for p in parts:
        uid, name = _pinfo(p)
        if name.strip().lower() == w:
            return uid, name
    return None, None


def main():
    ap = argparse.ArgumentParser(description="Re-import Medtronic JSONs for a participant.")
    ap.add_argument("--folder", required=True, help="Folder of session JSONs (walked recursively).")
    ap.add_argument("--participant", required=True, help="Existing participant name or uid.")
    ap.add_argument("--server", default=os.environ.get("BRAVO_SERVER", "http://localhost:27286"),
                    help="Base URL of the running BRAVO server.")
    ap.add_argument("--api-key", default=os.environ.get("BRAVO_API_KEY"),
                    help="Secure API key (or set BRAVO_API_KEY).")
    ap.add_argument("--workers", type=int, default=8,
                    help="Parallel upload connections (default 8). The server decodes each file with "
                         "its own thread pool and serializes identical-content uploads on a per-hash "
                         "lock, so very high values give diminishing returns; 6-12 is a good range.")
    ap.add_argument("--delay", type=float, default=0.0,
                    help="Seconds to pause between submitting uploads (default 0; parallelism "
                         "replaces inter-request spacing).")
    ap.add_argument("--dry-run", action="store_true", help="List files; upload nothing.")
    args = ap.parse_args()

    if not args.api_key and not args.dry_run:
        ap.error("No API key. Set BRAVO_API_KEY or pass --api-key (not needed for --dry-run).")

    if not os.path.isdir(args.folder):
        ap.error(f"Folder not found: {args.folder}")

    files = find_jsons(args.folder)
    print(f"Found {len(files)} JSON file(s) under {args.folder}")
    if not files:
        return

    if args.dry_run:
        for f in files:
            print(f"  would upload: {os.path.relpath(f, args.folder)}")
        print(f"\nDry run — nothing uploaded. {len(files)} file(s) would be sent to "
              f"participant '{args.participant}' on {args.server}.")
        return

    api = BRAVOPlatformRequest(args.api_key, server=args.server)
    # Authenticate / load profile (sets api.User, needed for the Institute field on upload).
    api.GetUserInfo()

    uid, name = resolve_participant(api, args.participant)
    if not uid:
        print(f"ERROR: participant '{args.participant}' not found. Create it in the UI first, "
              f"then re-run.", file=sys.stderr)
        sys.exit(2)
    print(f"Target participant: {name!r} (uid={uid})\n")

    # The MedtronicJSON decode path (DataCurator.MedtronicPerceptJSONDecoder) reads these metadata
    # keys directly: metadata["automatic_concatenation"] and metadata["automatic_deidentification"].
    # The web UI's DefaultType route injects them server-side, but the MedtronicJSON route does NOT,
    # so we MUST supply them here or the decode raises KeyError('automatic_concatenation'). Pass the
    # full set the decoder expects.
    upload_meta = {
        "device_location": "",
        "infer_from_device": True,
        "automatic_concatenation": False,
        "automatic_deidentification": False,
    }

    total = len(files)
    workers = max(1, args.workers)

    # requests.Session (held inside BRAVOPlatformRequest) is not guaranteed thread-safe, so give
    # each worker thread its OWN authenticated client via thread-local storage rather than sharing
    # `api` across threads. Each thread-local client authenticates once on first use.
    _tl = threading.local()

    def _client():
        c = getattr(_tl, "client", None)
        if c is None:
            c = BRAVOPlatformRequest(args.api_key, server=args.server)
            c.GetUserInfo()  # sets c.User (needed for the Institute field on upload)
            _tl.client = c
        return c

    counts = {"ok": 0, "err": 0, "done": 0}
    lock = threading.Lock()

    def _upload(path):
        rel = os.path.relpath(path, args.folder)
        try:
            with open(path, "rb") as fh:
                # Returns True for both 200 (ingested) and 301 (duplicate) — both are success.
                _client().UploadMedtronicJSON(uid, fh, metadata=upload_meta)
            ok, msg = True, None
        except Exception as exc:
            ok, msg = False, str(exc)
        with lock:
            counts["done"] += 1
            i = counts["done"]
            if ok:
                counts["ok"] += 1
                print(f"  [{i}/{total}] OK  {rel}")
            else:
                counts["err"] += 1
                print(f"  [{i}/{total}] ERR {rel}: {msg}", file=sys.stderr)
        return ok

    t0 = time.time()
    print(f"Uploading {total} file(s) with {workers} parallel connection(s)...\n")
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = []
        for path in files:
            futures.append(pool.submit(_upload, path))
            if args.delay:
                time.sleep(args.delay)  # optional throttle on SUBMISSION rate
        for _ in as_completed(futures):
            pass
    dt = time.time() - t0

    rate = total / dt if dt > 0 else 0.0
    print(f"\nDone in {dt:.1f}s ({rate:.1f} files/s).  "
          f"uploaded/accepted={counts['ok']}  errors={counts['err']}  total={total}")
    print("Note: files already stored are accepted as duplicates (HTTP 301) and not re-decoded.")
    print("Reload the Biomarkers report and hard-refresh (Cmd+Shift+R) to see the repopulated data.")


if __name__ == "__main__":
    main()