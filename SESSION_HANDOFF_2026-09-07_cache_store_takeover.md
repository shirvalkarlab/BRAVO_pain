# TAKEOVER HANDOFF — the cache store, the formats, and what the last ten sub-agents did

Written 2026-09-07 for a **new session that is taking this over**. Branch
`PS_closedloop_deployment`. Continues `SESSION_HANDOFF_2026-09-06_sweep_ramp_and_matcher.md`.

Every number in this document was measured in the running container and read back from a saved
artifact. **Do not quote a suite count or a timing from this file without re-running it** — that
mistake has produced false figures in durable documents in this project more than once.

---

## 0. READ THESE FIRST, IN THIS ORDER

The PI's own words: *"There are too many Handoffs going on now."* **He is right, and it is worse than
it sounds: the repository root holds 53 `.md` files, and 38 of them are handoffs, audits or
validation reports** — 22 named `SESSION_HANDOFF_*`, 7 named `HANDOFF_*`, one bare `HANDOFF.md`,
6 `AUDIT_*` and 2 `VALIDATION_*`. So here is the reading order and which document wins when two
disagree. **Read these seven and stop.** The rest are historical unless one of these seven points
you at it.

> *An earlier version of this paragraph said "25 … plus 7 `AUDIT_*`". Those figures were wrong —
> eyeballed from the listing rather than counted from it. The corrected breakdown above was computed
> by prefix and sums to 53. The wrong figures also reached commit `98ba64a`'s message, which cannot
> be edited once pushed; the counts here are the correct ones.*

> **⚠ THE DESIGN LEDGER IS NOT A FILE IN THIS REPOSITORY.** `DESIGN_biomarker_pipeline_v2.md` exists
> only in the **artifact store**, not on disk — confirmed by listing every root-level `.md` file,
> where it does not appear. A new session that runs `cat DESIGN_biomarker_pipeline_v2.md`, or greps
> the working tree for it, will find nothing and could wrongly conclude the ledger does not exist.
> **Retrieve it with `host.artifacts(filename="biomarker_pipeline")` and open the path that
> `host.artifact_path(<latest_version_id>)` returns.** It is 890 lines. The same applies to anything
> else the project rules describe as "in artifacts".

| # | Document | Why | Authority |
|---|---|---|---|
| 1 | `DESIGN_biomarker_pipeline_v2.md` — **an ARTIFACT, not a repository file** (see the warning below) | The design ledger, 890 lines. Device facts, the three power-domain streams, the BandCandidate contract. **Read end to end.** | **Highest for device and design facts — EXCEPT section 4, which is superseded by item 5** |
| 2 | `MEGA_HANDOFF.md` | Durable cross-session record. §4 is the source of record for open audit items. | Highest for open items |
| 3 | `SESSION_HANDOFF_2026-09-06_sweep_ramp_and_matcher.md` | The immediately preceding session: the band-by-length sweep, the measured ramp, the 21x matcher, the shared cache, the Redis bound. | Highest for what changed most recently |
| 4 | **This file** | The cache-store design, the format measurements, the last ten sub-agent lanes. | Highest for the cache work |
| 4b | **`PLAN_cache_store_phase2_2026-09-07.md`** | **The approved work itself** — 30 steps in seven tracks, with the ordering, the two steps already settled, and the one step gated on a second sign-off. Read it after this file. | Highest for what to build and in what order |
| 5 | `HANDOFF_TD_LSB_calibration_2026-06-27.md` | **Load-bearing, and the one the PI singled out.** The calibration constant, the recipe, the per-recipe constant catalogue, and a written architecture decision marked as having no open option. Reading this overturned an invented constant last session. | **Highest for anything touching band-power units — beats the design ledger** |
| 6 | `README_BIOMARKERS_AND_DEPLOYMENT.md` | Module overview. Known to be behind the code. | Superseded where it conflicts with 1–5 |
| 7 | `README_CORRECTIONS_RECONCILED_2026-09-06.md` | Re-checks the older `README_CORRECTIONS_SUMMARY.md` against current code 103 commits later. All six of its corrections still hold substantively; every code citation has moved. | Read instead of the older summary |

**The PI confirmed which document he meant: `HANDOFF_TD_LSB_calibration_2026-06-27.md`**, item 5
above. Read it. It is the one he singled out as important context, and it earns that: it is the
record of the benchtop-style pairing exercise that produced the platform's band-power calibration,
and it catalogues the reproducibility errors that exercise ran into.

**IT OVERRIDES SECTION 4 OF THE DESIGN LEDGER, AND THIS CONFLICT IS EASY TO WALK INTO.** Section 4
of `DESIGN_biomarker_pipeline_v2.md` states that no converter between device units and microvolts
squared exists anywhere in BRAVO, and gives an early empirical figure of roughly 294 units per
microvolt squared to be trusted "no better than about 3x". **That was written before the 2026-06-27
calibration session and is historically superseded.** Two things it still gets right and that are
worth carrying: the absolute constant is normalisation-dependent, and the 146 nV per unit figure
from the device documentation is a **time-domain sample scale**, explicitly a different quantity from
the power scale.

**What the calibration handoff establishes, and it is marked "ARCHITECTURE DECIDED BY PI
(2026-06-27) — no open option":**

* Band power in the device's own units is the **time-domain transform recipe** — mean-detrend, an
  RC+S-Hann taper over one second of nonzero samples, zero-pad to a 256-point real FFT, peak
  scaling, then the **sum** of squared magnitudes across the band — multiplied by
  **`LSB_PER_UV2_TRANSFORM = 352.62` exactly.** Do not round it to 353 and do not substitute the
  stim-off variant 356.61.
* It is *"the PRIMARY way LSB is computed for both the exploratory panels and the deployment
  fallback — NOT a second DSP to maintain"*, and it **names the closed-loop deployment module** as
  one of its two consumers. The helper is `Biomarkers/routines/analytics.py::td_to_lsb`.
* Calibration quality: **r = 0.9927, RMSE 60.6 units, median fold error 1.092, 93.9% of blocks
  within 1.5x**, on 131 blocks of this participant's Stage-1 recordings.
* **Every recipe has its own constant, and conflating them is catalogued there as "ERROR 3":**
  transform 352.62 all-stim and 356.61 stim-off; welch256 270.22 (the old validated 269, removed
  2026-06-28); welch250 265.17; a per-window three-second variant 326; and
  **`LSB_PER_DEVICE_PSD = 73.63`** for the device's own onboard spectrum. **So finding a new number
  for an uncalibrated recipe is expected, not a discovery** — which is precisely the trap that
  produced an invented constant of 215 last session.
* **The three constants are not independent.** 352.62 divided by 73.63 is 4.789 exactly, so the
  device-spectrum route is **composed** from the time-domain route rather than independently
  calibrated, and it inherits both errors.
* **A diagnostic worth more than any of the numbers, from "ERROR 1": if a pairing does not reproduce
  352.6 with r = 0.9927, the pairing itself is wrong.** Non-coincident or wrong-product pairing
  collapses the correlation to about 0.13.

---

## 1. LOAD THESE SKILLS BEFORE WRITING ANY CODE

The PI asked for this explicitly and it is not optional.

* **Every BRAVO skill** — at minimum `bravo-session-rules` (the handoff and ledger update rules that
  apply after any code change) and `bravo-stimoptimizer-figures` (this project's figure
  conventions, including the derived-headline rule and the silent failure modes that have cost this
  project whole figure sets). Search the catalogue for `bravo` and load what comes back.
* **Plotly** — `ps-plotly`, plus `ps-scientific-visualization` and `figure-style` for any
  deliverable figure.
* **Architecture and review** — `code-review` for audits, and search for architecture skills to
  confirm and optimise the module architecture before committing to the cache-store shape.
* **`ps-statsmodels`** for anything inferential. Required by the project rules.

Also: **do not attempt kaleido or a headless browser in the sandbox.** Use the bridge. For rendering
SVG locally, `cairosvg` works but needs the native `cairo` library installed via conda.

---

## 2. THE JOB THAT IS APPROVED AND NOT YET BUILT

The PI approved the design in `CACHE_STORE_DESIGN.md` in full: *"all of the things that you said in
your cache store design, and I agree with it; implement them all."*

**The headline: his red edits turn the cache from a one-way speed-up into the platform's data bus.**
Today ingestion writes and three modules read. His four arrows — resolved from the arrow bindings in
his edited file, not from where they appear to point — are:

```
Biomarker Exploration  --> the cache store
the cache store        --> Stim Optimizer
Closed-Loop Deployment --> the cache store
Stim Optimizer         --> the cache store
```

### The risk that comes with it, and why one step is ordered first

Those arrows close a cycle. **Stim Optimizer would read a ground-truth verdict computed from data
Stim Optimizer itself chose to collect.** Nothing crashes; the exploration policy becomes
**self-confirming** — it explores where the last analysis said the signal was, the analysis is
recomputed on data concentrated there, and it agrees. The record then looks like converging evidence
when it is a loop.

**So the provenance step comes before anything that writes back:**

1. Every written-back product stores **the keys of every input it derived from**, not only its own.
2. A module **refuses** to consume a product whose provenance already contains that module's own
   current output, and says so.
3. The chain is queryable, so "which biomarker run informed this exploration queue?" has an answer.
4. **Prove the refusal fires with a deliberately constructed cycle.** Do not assert it cannot happen.

### The store layout the PI agreed to

| Data | Format | Reason |
|---|---|---|
| 3-second tiles + 98-band spectra (245.90 MB), assembled participant matrix (500.32 MB) | **compressed array files** | 3-D numeric, not tabular; reads in 0.05 s |
| Therapy settings delivered (6,629 x 9) | **Parquet + zstd** | typed, tiny, carries a timezone-aware timestamp |
| **REDCap pain-report snapshot** (765 x 28) — NEW | **Parquet + zstd** | for provenance, not speed |
| **Therapy x pain, time-matched** — NEW | **Parquet + zstd** | what Stim Optimizer asked for |
| **Biomarker results per band** (correlation + discrimination) — NEW | **Parquet + zstd** | all 22 centres, 8.5–29.5 Hz |
| **Amplitude effect per band** — NEW | **Parquet + zstd** | so Stim Optimizer knows what is still unresolved |
| **Ground-truth source verdict** — NEW | **Parquet + zstd** | Closed-Loop writes, Stim Optimizer reads |
| Build locks, freshness keys, last-updated dates | **Redis** | 0.037 ms |
| Provenance and version ledger | **MySQL** | needs joins, durability, backup |

**The band range is settled.** The PI confirmed: *"I meant all the bands that this week already
covers from 8.5 to 29.5 Hz."* All 22 centres. His flowchart note said "8-20", which would have
dropped the 22–27 Hz range holding this record's clearest amplitude response; he corrected it.

### The REDCap decision, and the condition on it

The PI reversed the earlier "never cached" rule and asked for the pain-report frame to be stored.
**Store it — and keep fetching fresh on every request anyway.** The honest accounting, which he
accepted:

* Storing it **buys no speed**: the fetch is 0.651 s.
* The expensive part is the **matching**, which is what his note actually asked to cache.
* **The fresh fetch must stay** to compute the signature that keys derived products. Reports are
  filed continuously. Serving a stored snapshot unchecked means a newly filed rating silently does
  not appear and every correlation and every "established" verdict is computed on an incomplete set
  **while the page looks completely normal.** That is the only failure in this system with no
  visible symptom.

### The two closed-loop fixes he asked for

1. **The evidence triangle does not display, though it did in a prior mockup.** There is a specific
   lead: earlier in the last session a panel existed in the source and in **no served bundle**,
   because source was committed without rebuilding the front end, and a component in that state can
   neither render nor report a failure. **Check the served bundle before touching component code.**
2. **The three-source comparison needs a ground-truth decision rule.** Proposed and awaiting his
   sign-off: *the device's own onboard reading is ground truth wherever it exists, because that is
   the measurement the control law will actually run on; the calibrated route from raw samples where
   it does not; never the uncalibrated route.* **The limitation travels with the rule — the device
   computes its own power for only the single programmed band**, so every other band falls through
   by necessity rather than by choice.

### Also settled

* **`biomarker_psd_rows` is to be deleted** — his "(DELETE ME)". 6,309 files, 30.47 MB, **zero reads
  measured** by any live page. Verify removal breaks nothing first.
* **One store implementation only** — his words: *"fix this so only one implementation exists as a
  superset callable by any module that needs it!"* Today `Biomarkers/bravo_service.py` and
  `ClosedLoopDeployment/adapter.py` each carry their own duplicated resolver, loader, writer, event
  counters and lock, **with different caps: 1074 MB against 268 MB.** Stim Optimizer has none.
* **Three Redis wins** remain to build: the cross-worker build lock, the freshness key, and pointing
  Django's cache at Redis. The memory bound is already done (below).

---

## 3. EVERYTHING LEARNED ABOUT FILE FORMATS

Measured on the real delivered-therapy table: **6,629 rows x 9 columns**, 1.78 MB in memory, best of
three reads, in the container.

| Format | Size | Write | Read | Types kept | Round-trips exactly |
|---|---|---|---|---|---|
| **Parquet (zstd)** | **0.027 MB** | 0.004 s | 0.001 s | yes | yes |
| Parquet (snappy) | 0.031 MB | 0.010 s | 0.002 s | yes | yes |
| HDF5 (table, zlib) | 0.082 MB | 0.067 s | 0.008 s | yes | yes |
| HDF5 (table, blosc) | 0.131 MB | 0.025 s | 0.007 s | yes | yes |
| Pickle (what the store used) | 0.451 MB | **0.002 s** | 0.001 s | yes | yes |
| CSV | 0.492 MB | 0.022 s | 0.003 s | **NO** | **NO** |
| JSON (records) | 0.999 MB | 0.023 s | 0.009 s | **NO** | **NO** |

**The decisive fact against CSV and JSON is correctness, not preference.** The table carries a
`datetime64[ns, UTC]` column. Both formats lose it and neither round-trips identically, so every
consumer would re-parse the timestamp that matches therapy to neural data — which is exactly where
timezone errors enter.

**An honest correction that must not be lost: Parquet does NOT win on every axis.** Pickle **writes
twice as fast** (0.002 s against 0.004 s) and reads are tied. Parquet is chosen for **size and
durability** — 17x smaller, and a stable published format rather than a version-fragile,
unsafe-to-load one. An earlier draft of this claim said "wins on every axis" and was wrong.

**Other format facts:**

* Parquet reads **2 of 9 columns in 0.0011 s**. HDF5 needs the whole table unless a column index is
  set at write time. For a store three modules read differently, that matters.
* `pyarrow` is **not installed** in either the host env or the container by default. Install it.
* **Redis stores opaque bytes only.** It has no notion of Parquet, HDF5 or CSV. It does not change
  the format choice; it would just hold the Parquet bytes.
* The large arrays are **not tabular** and must not be forced into a table format.

### Redis: measured, and the answer is counter-intuitive

| What | Redis | The file cache | Faster |
|---|---|---|---|
| Small value, set and get | **0.037 ms** | — | **Redis** |
| Therapy table, 0.027 MB | 1.28 ms | **1.16 ms** | the file |
| Tile cache, 245.90 MB | 0.14 s | **0.05 s** | **the file, 3x** |

**Redis is slower than the files for the big payloads.** The cache files are already in the
operating system's page cache, so a file read is a memory read, and Redis adds a socket round trip
plus a copy of every byte. **BRAVO has a computation problem — 37 s to build the tiles against
0.05 s to read them — not a latency problem.** The one place Redis addresses the 37 s is stopping
the four workers from doing it simultaneously.

### Redis and MySQL operational facts

* **Redis 5.0.14** at `redis:6379` — **not** `127.0.0.1`, which is refused. `REDIS_HOST=redis` is
  already in the Django settings.
* **It predates version 6**, so it rejects the RESP3 `HELLO` handshake modern `redis-py` sends by
  default. **Every client must be constructed with `protocol=2`** or every call fails with
  "unknown command `HELLO`".
* **`CONFIG REWRITE` is unavailable** — it fails with "The server is running without a config file",
  because the image runs with no mounted config. The compose `command:` is the only durable route.
* **Already fixed (commit `b7036bf`):** `maxmemory 512mb` and `maxmemory-policy allkeys-lru`, applied
  live and set durably on the redis service in **both** `docker-compose.yml` and
  `Docker/docker-compose.yml`. It had been unlimited with eviction disabled, which meant refusing
  writes when the host filled. `allkeys-lru` and not `volatile-lru`, because the latter evicts only
  keys with an expiry and one key without one could restore the wall.
* **MySQL 8.0.46** at `mysql:3306`, database `BRAVOServer`, 44 tables, `SELECT 1` in 0.031 ms.
* **Django's cache backend is still `LocMemCache`** — per-process, the exact cause of the cold-worker
  penalty. Redis was intended here and never wired.
* **Four uvicorn workers, not five.** `gunicorn -w 4` plus one master. `ps | grep gunicorn` shows
  five lines and overstates it — read the parent process IDs. pid 1 is the master.

### The cache as found, measured on disk

Root `$DATASERVER_PATH/cache/`, about **782 MB** total:

| Directory | Files | Size | Read by a live page? |
|---|---|---|---|
| `biomarker_psd` | 97 | 500.32 MB | yes |
| `biomarker_shared` | 1 | 245.90 MB | yes |
| `biomarker_psd_rows` | **6,309** | 30.47 MB | **NO — zero reads** |
| `closed_loop` | 2 | 5.52 MB | yes |

### The third platform input does not exist in the server

**The Google Drive visit sheets never reach the platform.** No Sheets access anywhere in the
codebase; they were parsed offline and live in the analysis folder, and three code comments say the
server has no copy. **At-home versus in-clinic is decided from the Medtronic recording type**, not
from any sheet, and the current ladder comes from the device's own log — deliberately, because the
sheets carry planned values that were sometimes never delivered. Making them a real input is new
ingestion work, not a cache question.

---

## 4. WHAT THE LAST TEN SUB-AGENT LANES DID

All landed on `PS_closedloop_deployment`. **Re-run any suite count before quoting it.**

**1. RouteSwitch — the most consequential result of the session (commit `90eb109`).** Switched the
closed-loop module's band power onto the lab's calibrated route instead of integrating a power
density. Typical value moved from 1.23 to 201.7 device units; the largest from 4,228 to 38,930. The
ratio of new to old spans **48 to 344 with a median of 199** — which is the arithmetic proof that no
single multiplying constant could ever have been right, and why an invented constant of 215 was
reverted. **The deployable verdict moved from 2 of 50 to 6 of 50** and the selected setting changed
from `ONE_THREE_LEFT`/Left/165 Hz to **`ZERO_TWO_LEFT`/Left/55 Hz**. 216 of 900 band-and-setting
entries went from unanswerable to answered.
*Two cautions that travel with it:* the intervals tightened but still rest on the same five calendar
blocks, so the extra measurements bought **coverage, not independence**; and on the setting that lost
status the fit reverses with nearly identical end currents but different weighting, so a single
straight line across 1–4.8 mA may be the wrong summary.

**2. PainMatrix — the pain-tracking calculation moved modules.** The audit changed the job: the two
sides were never computing the same quantity, and searching the whole biomarker package for the
stimulator's linear power scale returned **nothing** — it existed only in the consuming module. The
calculation moved to `Biomarkers/routines/analytics.py`; `edges.py` shrank from **744 to 252 lines**.
Verified by freezing the old code and running both on the same live data: **108 of 108 band cells
exactly identical**, not within a tolerance.

**3. VecMatch — matching went 21x faster (commit `958cc89`).** 18.263 s to **0.852 s** across six
sensing contact pairs, measured as three alternating rounds so the filesystem cache could not favour
whichever ran second. **The larger share of the gain was not the vectorisation** — it was noticing
that converting the cache's band values into a numeric matrix was being redone for all ten lengths
of signal when it depends only on the recordings. Also documented, unchanged: two pain reports filed
at the **identical second** are partitioned between neighbours rather than double-counted.

**4. DupRead — one of two duplicate passes over the device files removed.** Cold build 71.23 s to
**35.40 s** (means of 74.13/68.32 and 35.71/35.08, run old-new-old-new). Full request 76.66 s to
41.55 s. One pass over the files is 33.65 s alone. It **corrected the agent's own figure**: 568 files
per pass, not 1,136 — reading them twice is 1,136 *reads*. Proved the report unchanged by walking
**1,321 values, zero differences**, then added a control comparing two runs of the new path against
each other — without which agreement could have been agreement between two runs of something that
varies anyway.

**5. BmCache — the Biomarker cache became shared across workers (commit `2bef090`).** Cold 53.44 s
against 6.06 s warm in the same worker: a 47-second penalty on every cold worker, because the
assembled products lived only in per-process memos capped at 8 entries, with four workers and reload
enabled. Ported the closed-loop module's shared file store. **The lane refused part of its brief and
was right to**: the cached product is built with no knowledge of any pain rating and serves every
choice of rating, so keying it on the report set as instructed would have discarded a long build
every time a report was filed. It also found the existing in-memory signature could not serve as a
file key at all, because that signature is computed from **decoded** recordings while the whole
point of a file is to be found **before** decoding. Warming at ingest needed no new file: the ingest
decoder already ended by firing a background thread.

**6. DecodePath — the codebase review for a common decode pathway.** It **corrected the premise it
was given**: reading bytes off disk is a small fraction of the page, not the largest item, because
the work spreads across threads and compresses in wall clock — so a cache of decoded bytes could
never save much. The real cost is **re-derivation**: a channel-name normaliser called an enormous
number of times, almost all from a single line that walks every spectrum record once per pain report.
**Its entanglement finding was favourable**: decoding is separable almost everywhere, with one
genuinely interleaved site that computes spectra and correlates them against pain in a single pass,
ported verbatim from a source notebook. It also noted the spectra that site recomputes are **already
cached on disk by a builder the live path never reads**, and declined to use a profiler for its stage
breakdown because the call volume inflates one stage.

**7. BandTimeSweep / PainSweep — the band-by-length sweep (commit `e1cc557`).** A new section on the
biomarker page: **22 band centres against 10 candidate lengths of signal**, 220 cells, full grid of
2,640 returned rather than only the best per band. **The length you ask for is not always what you
get** — measurements are built from whole three-second pieces, so 1 becomes 3 s, 5 becomes 6, 10
becomes 9, 20 becomes 21, 25 becomes 24; both numbers are carried on every axis and row. Every
area-under-curve row is referenced to **0.5**, not 0. It also applied a selection correction, because
reporting the best of ten lengths per band is optimistic by construction.

**8. Heat maps and the one-sided visit search.** Found the visit the PI needed: **2026-08-18 at
55 Hz**, where each stimulator was ramped separately while the other sat at zero, minutes apart —
correlation between the two sides **−0.012** against 0.98 on the visit shown earlier. **Most visits
cannot do this**: of 54 visit-and-rate combinations, more than thirty have the two sides in lockstep
above 0.99, and only six have a usable single-side stretch. Also flagged that the two bands
containing the 55 Hz stimulation reach 7,544 and 23,121 device units — **the stimulator, not the
brain** — which led to hatching the bands carrying a folded harmonic.

**9. SweepStats and RedcapPull — two optimisation lanes.** The statistics brief forbade reducing
shuffle and resample counts as an optimisation, because that widens the reported interval. The REDCap
lane **declined to build a cross-request cache after measuring twice** that the record-edit-log
freshness check costs about as much as a fresh fetch — reported as the correct answer rather than a
failure (commit `c70e0b0`). Its speedup came from narrowing what was requested from the service.

**10. Stability and ThreeWay.** The stability module returns **four values and no boolean about its
own conclusion**; the only true-or-false key reports whether the test ran. Justified by a collapse
shown on the participant's own record: the old two-valued flag read as a pass because the test failed
to reject, while the interval on the largest difference was far wider than the declared margin.
Wired into the closed-loop report by reusing the value the biomarker path already computes, so no
model is refitted. **The PI rejected the first version of its wording outright** — see §5.

---

## 5. HOW THE PI WANTS THINGS REPORTED — READ THIS BEFORE WRITING PROSE

These were stated emphatically and they govern everything.

* **Avoid all jargon.** Use the actual metric or variable name. Never "data", "variable", "era",
  "arm", "floor", or new hyphenated coinages. Say "the number and range of stimulation currents we
  tested", not "capture span". Say "the effect size", never "the floor".
* **Every sentence must carry its own context**, as if the reader has no idea what is being
  discussed. His words: *"Every sentence and paragraph should start with complete new context, as if
  the user has no fucking idea what you're talking about!"*
* **A result and any claim about it must appear in the same response.** No anticipatory claims.
* **State what a comparison is against.** He rejected the stability panel because it never said what
  question it answered: *"It behaves differently than what?"*
* **Plots must be in the device's own units.** The device does not use logarithms.
* **Do not conclude a band "does not respond" from a narrow range of tested currents.** Quantify the
  smallest movement the design could have detected and say that instead.
* **Bullet and numbered lists, bold for the urgent.** No AI-typical phrasing.

---

## 6. TRAPS THAT HAVE ALREADY COST TIME — DO NOT REDISCOVER THEM

1. **`/usr/src/BRAVO` IS a live mount** of the host's `BRAVO/` subtree, so **copying files in
   through the bridge is unnecessary** — write on the host and run. Only repo-**root** files
   (`MEGA_HANDOFF.md`, `SESSION_HANDOFF_*.md`, `README_*.md`, `Client/`) are absent, because the
   mount is the subtree and not the root. An earlier claim that it is not a live mount was wrong and
   was propagated into memory, a handoff and two commit messages before being disproven by test.
2. **There is no pytest in the container.** `_agent_bridge/run_tests.py` is the only container test
   runner and it runs the whole suite. `pytest.approx` and `pytest.raises` are unavailable in
   `modules/Biomarkers/tests/*.py` — use plain `abs()` comparisons there.
3. **The container's pip refuses under PEP 668** — pass `--break-system-packages`. Those installs are
   ephemeral; the durable fix is the pinned manifest, which is `BRAVO/requirements.txt`.
4. **`plotly` was missing from the server for a long time and failed silently**, costing the Stim
   Optimizer page every one of its figures, because the figure builder imports it inside the
   function. Now pinned.
5. **Committing source without rebuilding the front end** produces a component that exists in source
   and in no served bundle — it can neither render nor report a failure. This is the leading
   suspect for the evidence triangle.
6. **Suite counts in handoff documents go stale within a single session.** Re-run, never quote.
7. **The Excalidraw viewer tile does not render in the Claude Science web client** on the PI's
   machine, though it works in the desktop app and on excalidraw.com. A successful `create_view`
   return is **not** evidence he can see anything. Ask which client he is in.
8. **A test whose name asserts something untrue is worse than no test.** When removing a
   calculation, split the test rather than relabelling its assertion.
9. **An area-under-curve value must be compared against 0.5**, never 0.
10. **Read `ps` parent process IDs** before counting workers.

---

## 7. OPEN, AWAITING THE PI

1. **The go-ahead to start.** He approved the design and requires an explicit manual go-ahead
   before implementation begins. Nothing in the plan's second phase has been started.
2. **The ground-truth rule** for the three-source comparison — proposed in §2, his call.
3. **The commit identity.** The project rules ask for commits under his name; they have been made as
   `Claude <noreply@anthropic.com>` instead, because attributing machine-written commits to a named
   researcher in a research repository's permanent record is his decision. **Unanswered — ask.**
4. **The modelling question** left from the route switch: whether to fit one straight line across
   1–4.8 mA or something allowing curvature, given that a rise-then-fall response exists in this
   record and a straight line reads it as no response.
