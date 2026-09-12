# What BRAVO caches, and what it does not — the map, for approval

Measured in the running container on 2026-09-06. Every size and count below came from
`os.listdir` and `os.path.getsize` on the live store, and every timing from the alternating-round
measurements committed tonight. Nothing here is recalled.

---

## 1. The three inputs, and why only one of them is cached

| # | Input | Reaches the server? | Cached? |
|---|---|---|---|
| **1** | **Medtronic Percept RC** Session Report JSON, 569 stored files for RCS08 | yes, by upload | **YES — the only cached input** |
| **2** | **REDCap pain reports**, 760 reports, 765 rows x 28 columns | yes, fetched per request (0.651 s) | **NO, deliberately** |
| **3** | **Google Drive visit sheets** (at-home and in-clinic stim testing tabs) | **NO** | no |

**Input 2 is never cached and that decision is already recorded.** Reports are filed continuously,
so a cache outliving one request would eventually serve an analysis silently missing the newest
ones — every correlation and every "established" verdict wrong while the page looked normal. It was
measured twice: REDCap's own record-edit-log freshness check costs about as much as a fresh narrowed
fetch, so a cache would buy nothing and risk everything.

**Input 3 does not reach the server at all, and I want this on the record because it is easy to
assume otherwise.** The visit sheets were parsed offline on 2026-09-05 from the Google Drive master
folder, and they live in the analysis folder. Three separate places in the code say the server has
no copy. So:

- **Nothing in the running platform reads a visit sheet.**
- **At-home versus in-clinic is decided from the Medtronic recording type**, not from any sheet —
  `MedtronicBrainSenseTimeDomain` and `MedtronicIndefiniteStream` for streaming, and
  `MedtronicChronicBrainSense` for the chronic record.
- The ladder of currents used in the analysis comes **from the device's own log**, not the sheet.
  That was a deliberate decision: the sheets carry planned values that were sometimes never
  delivered, including four stimulation rates the device export never recorded.

If you want the sheets to become a real third input, that is new ingestion work and not a cache
question. It is not in this plan.

---

## 2. What is on disk today: one root, four directories, two implementations

Root: `$DATASERVER_PATH/cache/`

| Directory | Files | Size | What it holds | Read by a live page? |
|---|---|---|---|---|
| `biomarker_psd` | 97 | **500.32 MB** | whole-participant assembled matrix | yes |
| `biomarker_shared` | 1 | **245.90 MB** | 3-second tiles + 98-band spectra | yes |
| `biomarker_psd_rows` | **6,309** | 30.47 MB | per-recording spectra | **NO — zero reads measured** |
| `closed_loop` | 2 | 5.52 MB | evidence inputs + response | yes |

**Total about 782 MB.** Three problems visible in that table:

1. **Two separate implementations of the same store.** `Biomarkers.bravo_service` and
   `ClosedLoopDeployment.adapter` each carry their own `shared_cache_dir`, `_shared_load`,
   `_shared_store`, event counters and lock — duplicated code with **different byte caps, 1074 MB
   against 268 MB**. They share a root by coincidence of construction, not by design.
2. **6,309 files no live page reads.** Either wire them in or remove them; at present they are
   confusion that costs 30 MB.
3. **The Stim Optimizer has no on-disk cache at all** — and it is the slowest endpoint on the
   platform at 85.80 s, of which **65.71 s is rebuilding the same therapy settings stream twice.**

---

## 3. Your rule, the case it breaks on, and what I recommend instead

**Your rule:** ingestion is the only thing that writes or updates a cache.

**I agree with the intent and I want to narrow the wording, because the literal version has a
failure case you would find unpleasant and would not see coming.**

### The failure case

The cache key deliberately contains code-version values — the tile width, both calibration
constants, the window and hop, the channel-naming rule and a rule version. That is correct and
load-bearing: **a cache file outlives the process that wrote it**, so if the recipe changes the old
file must not be served to new code.

But it means a **code deploy changes every participant's key**. Every cache becomes a miss. And if
only ingestion may write, then **every page stays slow until each participant's next upload** —
which for RCS08 could be weeks. The platform would be silently degraded, working but slow, with
nothing on screen to say why.

You had already spotted the tension yourself: *"If there's no cache file that exists, I think the
sensible thing would be to write one new one."* That instruction is incompatible with ingestion
being the sole writer, so the rule you actually want is narrower than the one you stated.

### The recommendation: the KEY is the trigger, not the caller

**A write happens when, and only when, the key does not match what is on disk.** The key changes
from exactly two things: new or changed recordings, which is an ingestion; or a deliberate version
bump in the code.

| Situation | What happens |
|---|---|
| Page opened, key matches the file on disk | **read only — nothing is written, ever** |
| New upload arrives | ingestion builds and writes, so the first page view is already fast |
| Page opened, no file or a stale key (first deploy, version bump, never-ingested participant) | **builds once and writes one new file**, exactly as you said |
| Nothing has changed | **nothing is re-derived** — your actual goal |

This gets you everything you asked for and removes the deploy trap:

- Nothing is re-derived when nothing has changed.
- A page can never *refresh* a cache that is already correct, which is the property worth testing,
  and the test is simple: open a page and assert the cache directory is byte-identical afterwards.
- One writer function, called from either place, rather than two code paths that can drift.

### Three things I recommend alongside it

1. **One store, one implementation, one location.** One module owns the store and the other two call
   it with a `kind` argument. Today "one location" is aspiration; this makes it enforceable, with a
   test that fails if any code resolves a cache directory of its own.
2. **Decide `biomarker_psd_rows`.** 6,309 files, zero reads. Wire in or delete.
3. **Give the Stim Optimizer a `kind` in the same store.** It is the slowest page and the only one
   with no cache, and 65.71 s of its 85.80 s is one stream built twice.

---

## 4. The date on every page

Each cache file will carry, inside it, the moment it was written, what triggered the write, and how
many recordings it covers. The date shown on a page is read **from inside the file**, never from the
filesystem timestamp — a copy, a restore or a backup would falsify a file timestamp while the
contents stayed the same age.

Where no cache exists yet, the page says so rather than showing a blank or a misleading date.

---

## 5. What I need from you

1. **The diagram** — say what to change. Both formats are attached; the Excalidraw one is editable,
   so you can move boxes and hand it straight back.
2. **The writing policy** — the recommendation above, or your literal rule, or something else.
3. **`biomarker_psd_rows`** — wire in or delete.
4. **The Stim Optimizer cache** — in scope now, or later.
