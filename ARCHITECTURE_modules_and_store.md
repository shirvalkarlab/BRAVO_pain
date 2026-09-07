# BRAVO — the three modules, the store between them, and where the time goes

**This document replaces the architecture, cache, performance and file-map content of the mega
handoff, the session handoffs and the module README.** Where those disagreed, the newer
measurement was taken; each resolution is recorded in
`.planning/2026-09-06-cache-store-and-record-consolidation/findings.md` §1.

**Every measurement below was taken in the running container on this participant's own record, and
every line citation was read from the working tree at commit `705bdb0`.** Timings are stated with
the request they were measured on, because two different requests were previously quoted against
each other as if they contradicted.

---

## 1. What the platform is

A Django backend and a React frontend. It ingests the exported files from the Medtronic Percept RC
and the patient-reported pain scores from REDCap, and produces analysis, figures and a
configuration a clinician can program by hand. **There is no interface that writes to the device.**

The repository root is `/Users/pshirvalkar/dev/BRAVO_pain`, remote
`github.com/shirvalkarlab/BRAVO_pain`, default branch `v3.1.0`, working branch
`PS_closedloop_deployment`.

**Three analysis modules, and this is the shape the store work is about.**

| Module | Path | What it does | What it stores today |
|---|---|---|---|
| **Biomarker exploration** | `BRAVO/modules/Biomarkers/` | scans frequency against pain, matches pain reports to recordings, commits to a band, sets a switching value | two directories, its own store implementation |
| **Closed-loop deployment** | `BRAVO/modules/ClosedLoopDeployment/` | judges whether a chosen configuration is deployable, compares the three ways of reaching band power | one directory, **a second, duplicated store implementation** |
| **Stim Optimizer** | `BRAVO/modules/StimOptimizer/` | decides which stimulation settings still need exploring | **nothing — no stored files at all, and it is the slowest endpoint** |

`BRAVO/modules/MedtronicPercept/` holds the parser for the exported files, and
`BRAVO/modules/DataCurator.py` is the ingest path.

---

## 2. The store as it stands, measured rather than recalled

One root, `$DATASERVER_PATH/cache/`, holding four directories, about **782 MB**.

| Directory | Files | Size | Read by a live page? | What is in it |
|---|---|---|---|---|
| `biomarker_psd` | 97 | 500.32 MB | yes | the assembled whole-participant matrix |
| `biomarker_shared` | 1 | 245.90 MB | yes | the 3-second tiles and their 98-band spectra |
| `biomarker_psd_rows` | **6,309** | 30.47 MB | **no — zero reads measured** | per-recording spectra |
| `closed_loop` | 2 | 5.52 MB | yes | the evidence inputs and the response |

### Three structural problems, and they are the reason for the work

**1. Two duplicated store implementations with mismatched limits.** The biomarker service and the
closed-loop adapter each carry their own directory resolver, loader, writer, event counters and
lock. Verified this session:

| | Biomarker side | Closed-loop side |
|---|---|---|
| Directory name | `bravo_service.py:911`, `biomarker_shared` | `ClosedLoopDeployment/adapter.py:357`, `closed_loop` |
| Per-entry limit | `bravo_service.py:917`, **1,073,741,824 bytes** | `adapter.py:362`, **268,435,456 bytes** |

**They share a root by construction accident rather than by design**, and the limits differ by
exactly a factor of four for no stated reason. The PI's instruction: *"fix this so only one
implementation exists as a superset callable by any module that needs it."*

**2. 6,309 files that no live page reads.** Four superseded key generations exist per recording and
there is no sweeper. The PI marked the directory for deletion — *"For Biomarker, PSD rows kill
it"* — conditional on nothing depending on it. **That must be verified before removal, and it must
be settled together with the proposal to wire the live path onto those same files**, because one
plan deletes what the other would connect.

**3. Stim Optimizer stores nothing and is the slowest endpoint**, at about 85.80 s per request, of
which 65.71 s is building the therapy settings stream.

### What the store is becoming

**The PI's four arrows turn the store from a one-way speed-up into the route by which the modules
read each other's computed results.** Resolved from the arrow bindings in his edited flowchart:

```
Biomarker exploration    ──►  the store
the store                ──►  Stim Optimizer
Closed-loop deployment   ──►  the store
Stim Optimizer           ──►  the store
```

**Those arrows close a cycle, and this is the risk the whole build is sequenced around.** Stim
Optimizer would read a ground-truth verdict computed from recordings **Stim Optimizer itself chose
to collect.** Nothing crashes. The exploration policy becomes **self-confirming**: it explores
where the last analysis said the signal was, the analysis is recomputed on recordings concentrated
there, and it agrees. **The record then looks like converging evidence when it is a loop.**

So the provenance step comes before anything that writes back:

1. Every written-back product stores **the keys of every input it derived from**, not only its own.
2. A module **refuses** to consume a product whose provenance already contains that module's own
   current output, and says why.
3. The chain is queryable, so *"which biomarker run informed this exploration queue?"* has an
   answer.
4. **The refusal is proven by constructing a deliberate cycle, not asserted to be impossible.**

### The approved layout

| What is stored | Format | Why that format |
|---|---|---|
| 3-second tiles and 98-band spectra (245.90 MB); the assembled matrix (500.32 MB) | **compressed array files** | three-dimensional and numeric, not tabular; reads in 0.05 s |
| Therapy settings delivered (6,629 rows × 9 columns) | **Parquet with zstd** | typed, tiny, and it carries a timezone-aware timestamp |
| The REDCap pain-report snapshot (765 × 28) — new | Parquet with zstd | **for reproducibility and for keying derived products, not for speed** |
| Therapy settings matched in time to pain scores — new | Parquet with zstd | what Stim Optimizer asked for; has never existed as a stored table |
| Biomarker results per band, correlation and discrimination — new | Parquet with zstd | all 22 centres, 8.5 to 29.5 Hz |
| The amplitude effect per band — new | Parquet with zstd | so Stim Optimizer knows what is still unresolved |
| The ground-truth verdict — new | Parquet with zstd | closed-loop writes it, Stim Optimizer reads it |
| Build locks, freshness keys, last-updated dates | **Redis** | 0.037 ms, and they must agree across all four workers |
| The provenance and version ledger | **MySQL** | small, heavily queried, needs joins, must be backed up with the database |

**The band range is settled at all 22 centres from 8.5 to 29.5 Hz.** The PI's flowchart note said
"8-20"; he corrected it: *"I meant all the bands that this week already covers from 8.5 to 29.5
Hz."* Taking 8 to 20 Hz literally would have dropped the 22 to 27 Hz range holding this record's
clearest amplitude response.

### The writing policy — the key decides, not the caller

**The PI adopted this over his own first proposal:** *"Use your recommendation for the writing
policy, that is the correct thinking and logic I want."*

- A write happens **when and only when the key does not match what is on disk.**
- A page whose key matches **never writes**, and that is testable: open the page and assert the
  directory is byte-identical afterwards.
- A page with no file, or a stale key, builds and writes **one** new file.
- Ingest warms it, so the first view after an upload is already fast.
- The key changes from exactly two things: **new or changed recordings, or a deliberate version
  bump in the code.**

**Why "ingestion is the only writer" was rejected**, having been the first proposal: the key
contains code-version values, so a deployment invalidates every participant's cache, and
ingestion-only writing would leave every page slow until each participant's next upload.

---

## 3. What may be cached and what may not — the distinction that protects the results

**Getting this wrong corrupts results silently, which is the only failure in this system with no
visible symptom.**

**The recordings have a cheap freshness check.** `bravo_service._lsb_spectrum_signature` hashes the
participant, the pain-report set, and every recording's start time, channel names and sample
count, together with the band-centre grid — all from values already in hand. So a product keyed on
it can safely live in a stored file **with no expiry at all**, and no expiry is what is
implemented, verified.

**The pain reports do not.** They are filed continuously and **there is no freshness check cheaper
than the fetch** — measured twice. So they are fetched fresh every request and matched live.

**The consequence, and it is the design's most important single property: the tile file cannot
serve a stale pain report, because no pain rating is in it.** An earlier instruction to key the
tile file on the pain-report set as well was **refused by the lane that built it, and that refusal
was correct** — the tiles know nothing about any rating and the same tiles serve every pain score,
every match rule and every length of signal, so keying on the report set would have **discarded a
37-second build every time a report was filed.** Proven both ways with the file warm: changing the
report set from 760 reports to 720 changes 19,464 of 27,305 values in the answer, **and causes zero
file writes.**

**And the in-memory signature could not have been the file key at all**, because it is computed
from the **decoded** recordings while the whole point of a file is to be found **before** any
decoding. The warming entry point especially must answer "is this already built?" without opening
569 stored files. So the file key is built from the database rows alone: **0.33 s for this
participant's 4,078 rows.** Verified independently that the key builder contains no pain report,
rating or REDCap term.

### Three things the key must carry that a content hash does not cover

1. **Patient-controller event rows carry no content hash — 0 of 3,246** — because their spectra
   **are** the row metadata rather than a stored file. The metadata itself is hashed, 0.127 s for
   all 3,246. **Without this, a change to a patient-event spectrum would be invisible to the
   cache, which is precisely a cache serving a stale answer.**
2. **The sensing centre, the rate schedule and the contact schedule** are stamped onto the
   recording at decode time and decide which contact pair a patient-event spectrum belongs to.
   **They can change with no change to any content hash.**
3. **Every constant the stored numbers depend on** — the tile width, the transform calibration,
   the device-spectrum constant and its checked span, the window and hop, the saturation limit,
   the channel-naming rule, and a hand-bumped rule version. **A file outlives the process that
   wrote it** and would otherwise be handed to new code.

### Two size decisions worth keeping

1. **The matcher's own converted matrix is stripped before storing**, or the tile file would double
   from 245 to **511 MB**.
2. **A superseded key's entry is removed only after its replacement is safely in place**, or a
   month of daily uploads would leave **seven gigabytes that can never be read again.**

### Why the tiles are stored as arrays rather than lists

245.29 MB against 272.05 MB as lists, but **0.05 s to read against 0.56 s** — a list of lists has
to be rebuilt as 29 million separate Python numbers.

**That choice caused a regression worth recording, because it is the shape of failure this project
keeps paying for.** A helper opened with `if not rows:`, and asking a two-dimensional array whether
it is truthy raises an ambiguity error. From that commit onward, one closed-loop path **raised for
any participant whose tiles came back from the file rather than a fresh build — the ordinary
case — and it failed quietly**: the calibrated route came back empty while the endpoint still
returned results from the other route, **so the page looked normal and carried a thinner answer.**
Fixed in the shared helper; the first attempt patched the two call sites and the failure moved one
level deeper into the same function. `_RAW_LSB_MATRICES = ("lsb",)` at `bravo_service.py:1249` is
the list of keys that become arrays. **If it grows, every `or []` on the new key needs the same
treatment.** No test caught it because every fixture in that suite built its families as lists;
there is now one that builds the array form.

---

## 4. The formats, measured on the real table

Measured on the real delivered-therapy table — **6,629 rows × 9 columns, 1.78 MB in memory**, best
of three reads, in the container.

| Format | Size | Write | Read | Types kept | Round-trips exactly |
|---|---|---|---|---|---|
| **Parquet, zstd** | **0.027 MB** | 0.004 s | 0.001 s | yes | yes |
| Parquet, snappy | 0.031 MB | 0.010 s | 0.002 s | yes | yes |
| HDF5, table, zlib | 0.082 MB | 0.067 s | 0.008 s | yes | yes |
| HDF5, table, blosc | 0.131 MB | 0.025 s | 0.007 s | yes | yes |
| Pickle, what the store used | 0.451 MB | **0.002 s** | 0.001 s | yes | yes |
| Comma-separated | 0.492 MB | 0.022 s | 0.003 s | **no** | **no** |
| JSON records | 0.999 MB | 0.023 s | 0.009 s | **no** | **no** |

**The decisive fact against comma-separated and JSON files is correctness, not preference.** The
table carries a timezone-aware timestamp column. Both formats lose it and neither round-trips
identically, **so every consumer would re-parse the timestamp that matches therapy to neural
signal — which is exactly where timezone errors enter.**

**Parquet does not win on every axis, and an earlier draft that said so was wrong.** Pickle
**writes twice as fast** and reads are tied. **Parquet is chosen for size and durability** —
seventeen times smaller, and a stable published format rather than a version-fragile one that is
unsafe to load.

Two further format facts:

- **Parquet reads 2 of the 9 columns in 0.0011 s.** HDF5 needs the whole table unless a column
  index was set at write time. For a store three modules read differently, that matters.
- **The large spectrum arrays are not tabular and must not be forced into a table format.**
- **`pyarrow` is not installed** in either the host environment or the container by default.

---

## 5. Redis and MySQL — what they are for, and the counter-intuitive measurement

| What | Redis | The stored file | Faster |
|---|---|---|---|
| Small value, set and get | **0.037 ms** | — | **Redis** |
| Therapy table, 0.027 MB | 1.28 ms | **1.16 ms** | the file |
| Tile store, 245.90 MB | 0.14 s | **0.05 s** | **the file, about 3x** |

**Redis is slower than the files for the large payloads.** The cache files are already in the
operating system's page cache, so a file read is a memory read, and Redis adds a socket round trip
plus a copy of every byte on top.

**So BRAVO has a computation problem — 37 s to build the tiles against 0.05 s to read them — not a
latency problem.** The one place Redis addresses the 37 s is stopping the four workers from doing
it simultaneously.

**Redis is therefore scoped to three things and no more:** the cross-worker build lock, the
freshness key and last-updated date, and Django's small cache values.

### Operational facts, each one a trap that has cost time

- **Redis 5.0.14 at `redis:6379`** — **not** `127.0.0.1`, which is refused, and the host name `db`
  does not resolve. `REDIS_HOST=redis` is already in the Django settings.
- **It predates version 6, so it rejects the newer handshake that a modern client library sends by
  default. Every client must be constructed with protocol version 2**, or every call fails with
  "unknown command HELLO".
- **`CONFIG REWRITE` is unavailable** — it fails with "the server is running without a config
  file", because the image runs with no mounted configuration. **The compose `command:` is the only
  durable route.**
- **The memory bound is already applied**, commit `b7036bf`: `maxmemory 512mb` and
  `maxmemory-policy allkeys-lru`, set live and durably on the redis service in **both**
  `docker-compose.yml` and `Docker/docker-compose.yml`, because both define a redis service and
  which one is deployed depends on how the stack was brought up. It had been unlimited with
  eviction disabled, which means growing until the host fills and then **refusing new writes**
  rather than evicting — the opposite of cache behaviour, on a box shared with MySQL and the four
  workers. **`allkeys-lru` and not `volatile-lru`, because the latter evicts only keys carrying an
  expiry, so one key written without one could restore exactly that wall.** 512 MB is about 1.2
  percent of the 42 GB the box reports, and suits what the instance is now for.
- **MySQL 8.0.46 at `mysql:3306`**, database `BRAVOServer`, 44 tables, round trip 0.031 ms.
- **Django's cache backend is still per-process memory.** That is the exact cause of the cold-worker
  penalty, and the Redis host name is already set — **so Redis was intended here and never wired.**
- **Four workers, not five.** The server is started with four; a process listing shows five lines
  because the first is the master. **Read the parent process identifiers before counting.**

---

## 6. Where a request actually spends its time

**Two different requests were previously quoted against each other. Both numbers are right; they
describe different requests.**

### The Biomarker page request — about 60.4 s

| Stage | Seconds |
|---|---|
| every statistic | 19.13 |
| the biomarker pipeline | 17.14 |
| building the availability record, of which the per-report band power is 9.51 | 14.28 |
| the programmed adaptive switching values | 5.55 |
| **reading and un-pickling all 2,007 stored files** | **2.89 — only 4.8 percent** |
| REDCap | 1.10 |

**Reading files is not the cost, and the brief that said it was was wrong.** It looks larger than
it is because loading is already spread over sixteen threads: **39.8 thread-seconds compress into
2.89 s of wall clock.** A cache of decoded bytes cannot save more than about three seconds on this
page, however it is built.

**The cost is re-derivation.** In one Biomarker request the channel-name normaliser is called
**72,425,865 times, and 72,332,380 of those — 99.87 percent — come from one line**: the
spectrum-record scan inside `per_pro_lsb` at `availability.py:986`, which walks all 4,010 spectrum
records once per pain report and re-normalises every record's channel name and re-parses its
timestamp on every pass. **Both are properties of the record, and the request already had both
values 72 million times over.**

### The warm band-by-length sweep request — about 7.8 s

| Piece | Seconds | Share |
|---|---|---|
| **recordings read off disk and un-pickled** | **1.647** | **21.1%** |
| every statistic, six sensing contact pairs | 1.248 | 16.0% |
| matching, six sensing contact pairs | 1.063 | 13.6% |
| pain reports fetched from REDCap | 0.725 | 9.3% |

On **this** request reading is the largest single item, which is where the "21.1 percent" figure
comes from. Three speedups already landed and each was proven to change no output value: the
matcher 18.263 → 0.852 s (21.4 times, commit `958cc89`, proven over 1,080 live configurations with
zero field differences), the REDCap fetch 1.662 → 0.651 s (`c70e0b0`), and the statistics
2.127 → 1.196 s (1.78 times, `2a4d063`, proven over 7,920 grid cells and 8,358 fields with zero
differences).

### Decode counts per request, and what they say

| Endpoint | Decode calls | Distinct files | Redundant | Seconds, two consecutive requests |
|---|---|---|---|---|
| Biomarker page | 2,453 | 2,007 | 446 decoded twice | 70.98 then 60.56 |
| Band-by-length sweep | 832 | — | 0 | 5.50 then 5.03 |
| Closed-loop deployment | **0** | — | — | 0.435 then 0.413 |
| Stim Optimizer | 2,536 | 1,400 | **568 decoded three times** | 119.6 then 112.5 |

**No endpoint's decode count falls on the second request — there is no cross-request memory of a
decoded recording anywhere.** The closed-loop module's zero is what the target looks like: it is
served entirely from the 245.9 MB tile file.

### The largest single measured waste

**The therapy settings stream was built three times per Stim Optimizer request**, at 31.87 s each —
95.61 s of a 115.17 s request — from three call sites. **Both downstream callers had accepted an
optional argument all along whose docstring says passing it avoids the rebuild, and nobody passed
it.**

One of the three passes was removed and the result measured rather than inherited: **the honest
saving is 32.78 s, not the 63.74 s the review projected**, and **65.71 s of stream-building
remains** because a third consumer still builds its own copy. The report came back identical,
754,853 characters both ways.

### The three spectrum builders

**Three exist with three different caching regimes, and the one the page uses is not either of the
obvious two.**

1. `bravo_service._assemble_psd_rows_cached:2019` — caches per recording on disk. **This is the
   6,309 files**, with four superseded key generations per recording and no sweeper.
2. `bravo_service._assemble_psd_rows:1663` — **has no live caller anywhere.** Dead code that reads
   as the uncached sibling of a live function.
3. `pipeline.run_timedomain_branch:622` → `streaming_psd.compute_psd_pain_correlation:1066` —
   **the path the page actually uses.** It recomputes 386 spectra every request, about 4.05 s, and
   never reads the disk cache: the loader was called zero times, measured.

**The third path is the one genuinely entangled site in the whole codebase**: one pass computes the
spectra **and** correlates them against pain, ported verbatim from the source notebook. **Every
other decode site separates cleanly.** So a common decode pathway is a refactor and not a rewrite —
but that one site touches the statistics, which is why changing it needs its own decision record
and a second sign-off.

### The cold-worker penalty, and how it was closed

The assembled products lived only in per-process memories capped at 8 entries. **With four workers
and reload enabled, the 37-second tile build was paid by the first request to reach each worker,
and by all four again after any Python edit.**

| What the worker sees | Before | After |
|---|---|---|
| cold, no file, first call in the process | 42.83 s | 45.28 s — builds, then writes |
| **a fresh process with the file already present** | **not possible** | **6.06 s** |
| the same process, second call | 5.41 s | 5.12 s |

**Every number above is from a new interpreter**, because a warm same-process call would have
proved nothing about the actual problem. **The 47-second penalty is gone from every worker but the
first**, and the cold build costs 2.45 s more — the key, the storable shape, and writing 245.9 MB —
paid once per ingest rather than once per worker per reload.

**Warming needed no new file.** The ingest decoder already ended by firing a background thread, so
the tile warm went there; `DataCurator.py` is unmodified. Both live callers are off the request
thread, and **it never raises**, because an upload must not fail because a cache could not be
warmed. Cold 40.46 s; already warm **0.43 s**, the key only with no file opened; the wired path
with tiles present 0.81 s, no rebuild and no write.

---

## 7. The canonical decoded form, prototyped and measured

`BRAVO/modules/DecodeCommon/` — `representation.py`, `per_pro_lsb_indexed.py` and tests, **32
tests passing**. **It is untracked and nothing in the platform imports it yet.**

What it does: groups decoded recordings by canonical channel **once**; holds the voltage-trace and
device-spectrum routes separately with their provenance; **stores no calibration constant**, with a
test asserting the source text contains neither 352.62 nor 73.63; and **holds no pain reports, so
it never needs a freshness check.**

Measured against the live path on captured inputs: **9.233 s → 0.551 s including the build, 16.75
times, with 22,800 records × 7 fields = 159,600 field comparisons and zero differences.** It was
built as a parallel function importing into nothing, measured in alternating rounds, **and it
declined to use a profiler for its stage breakdown** on the ground that the call volume inflates
one stage severalfold and invalidates every comparison drawn from it.

---

## 8. The frontend, and the failure mode that gives no diagnostic signal

- **The repository commits the built bundle** and the web server serves the mounted build. **So a
  frontend change needs a rebuild, and the rebuilt chunks must go in the same commit as the source
  edit** or the served bundle drifts from the source.
- **A React component that exists in the source and in no served bundle can neither render nor
  report a failure.** The page is simply blank there. This has happened: a panel was committed
  without a rebuild, the build manifest was stamped 41 minutes before the source was written, and
  the PI reported "the matrices don't display" with no error anywhere to find. **This is the
  leading suspect for the evidence triangle not displaying.**
- **Check the served bundle before touching component code**, and **search for string literals the
  panel owns rather than component names**, because a production build renames components.
- One result cache serves all three analysis views: `Client/src/database/resultCache.js`, the hook
  `useCachedResult.js`, and the shared control `RecomputeBar.js`. **These are the PI's files — do
  not edit them without asking.** Two defects in that contract are open and the three views work
  around both: a deliberate recompute issues **two** fetches, and the entry limit is six against
  nine slots for one participant, with a count being the wrong unit when one entry is nineteen
  megabytes and another twenty kilobytes.

---

## 9. What is not an input, however much it looks like one

**The Google Drive clinic visit sheets never reach the platform.** There is no Sheets access of any
kind in the codebase — no client library, no interface, nothing. They were parsed offline and live
only in the analysis folder, and three code comments state the server has no copy.

Consequences:

1. Nothing in the running platform reads a visit sheet.
2. **At-home versus in-clinic is decided from the Medtronic recording type**, not from any sheet.
3. **The ladder of currents comes from the device's own log, deliberately** — the sheets carry
   planned values that were sometimes never delivered, including four stimulation rates the device
   export never recorded.

**Making them a real input is new ingest work, not a cache question.**

---

## 10. File map

**Biomarker module** — `BRAVO/modules/Biomarkers/`

- `routines/analytics.py` — the conversion constants and helpers (`td_transform_band_power`,
  `td_to_lsb`, `device_psd_band_power`, `harmonic_landings_hz`, `THRESHOLD_MODES`); the deployment
  statistics; the bootstrap and interval helpers; the spectral scan; the stimulation-era
  assignment; and the band-by-length sweep with its selection-aware verdict.
- `routines/availability.py` — the per-report band-power selection (`per_pro_lsb`,
  `per_pro_lsb_spectrum`), the tile store (`raw_lsb_spectrum_cache`), the matcher
  (`live_lsb_spectrum_match`), and the deployment-only modelled line (`modeled_lsb_at_center`).
- `routines/streaming_psd.py` — the Welch path and the missing-fraction floor.
- `routines/stats_utils.py` — the autocorrelation, the reference distribution, the block length,
  and `bh_fdr`.
- `routines/redcap_client.py` — the pain-report fetch, vendored.
- `routines/psd_lsb_model.py` — the frozen per-participant conversion model.
- `bravo_service.py` — the endpoint, the store implementation, the matching wiring, the sweep
  entry point `band_time_sweep_for_participant:6188`, and the warm entry `warm_psd_cache:2269`.
- `data/psd_lsb_models/RCS08.json` — the frozen asset.
- `pipeline.py` — the older branch that owns the entangled spectrum-and-correlation pass.

**Closed-loop module** — `BRAVO/modules/ClosedLoopDeployment/`: `adapter.py` (the second store
implementation, and `report_for_participant`), `three_source_response.py`,
`three_source_plots.py`, `clinic_steps.py`, `constraints.py`.

**Stim Optimizer** — `BRAVO/modules/StimOptimizer/`: `adapter.py` (`settings_stream`),
`routines/within_visit.py` (`ramp_windows_from_amplitude`, `mean_power_before_next_change`,
`amplitude_response_shape`), `routines/lfp_evidence.py`.

**Decode chain** — `modules/MedtronicPercept/{Percept,BrainSenseStream,IndefiniteStream,Session}.py`;
the ingest concatenation toggle in `modules/DataCurator.py`.

**Interface** — `Server/APIs/DataAnalysis.py` and `Server/APIs/urls.py`. **Both are
carriage-return files while all other source is not** — edit them with a line-ending-preserving
editor only, or a plain write strips them and produces an enormous spurious difference.

**Frontend** — `Client/src/views/Reports/Biomarkers/` (the timeline, the analytics panel, the
band-by-length panel), `Client/src/views/Reports/ClosedLoopSim/` (the deployment panels, code-split
into its own chunk), and `Client/build/` (the committed compiled bundle).

**The agent bridge** — `BRAVO/_agent_bridge/bridge_client.py` and `run_tests.py`. See
`OPERATIONS_runbook.md`.

**Tests worth knowing by name** — `Biomarkers/tests/test_analytics.py` holds roughly 96 of the
container test functions; `test_availability.py` covers the store, saturation and tier logic;
`test_per_pro_lsb.py` and `test_match_to_pro.py` cover the matching rules and the one-report cap;
`Client/src/database/resultCache.test.js` holds the ten behaviour tests for the shared result
cache, and `ClosedLoopSim/cachedPanels.smoke.test.js` checks that the five rewired panels render
and that the stale notice appears.

**The frontend files, named, because every archived document referred to them by name.**

| Where | Files |
|---|---|
| `Client/src/views/Reports/Biomarkers/` | `index.js` (state and the slider handlers), `BiomarkerAnalytics.js`, `BiomarkerDataTimeline.js` (which replaced the older `BiomarkerTimeline.js`), `BinarizationPreview.js`, `binarizationModel.js`, `PsdLsbPanel.js`, `SpectralFeatureImportance.js`, `BandTimeSweepPanel.js` |
| `Client/src/views/Reports/ClosedLoopSim/` | `index.js`, `BandCandidateStore.js`, `DeploymentVerdictStrip.js`, `DeploymentRocPanel.js`, `DeploymentEvidencePanel.js`, `LsbPowerPanel.js`, `ConversionModelPanel.js`, `EraRefitPanel.js`, `DeploySignoffCard.js`, `ThreeSourceResponsePanel.js`, `palette.js`, `deployPrint.css` |
| Shared, and **the PI's own files — do not edit without asking** | `Client/src/database/resultCache.js`, `useCachedResult.js`, `RecomputeBar.js`, `views/Reports/moduleCacheKeys.js` |

**The `CUTPOINT_TRACE = 2` constant in `DeploymentRocPanel.js` is the single source for the
cut-point trace index**, and the restyle-by-trace-index pattern depends on it.

---

## 11. The named routines and response keys the decisions and open items refer to

**Every archived document referred to these by name, so a reader following a decision or an open
item needs the spelling.** They live in the response payload or in the module source; the code is
authoritative for behaviour.

**Response keys in the deployment payload:** `deployment_summary`, `deployment_roc`,
`deployment_roc_by_era`, `deployment_forward_chaining`, `forward_validation`, `temporal_validity`,
`band_stim_stability`, `threshold_drift`, `threshold_drift_by_week`, `band_lsb_and_power`,
`band_mixedmodel_inference`, `spectral_feature_importance`, `lsb_series`, `lfp_evidence`,
`replay_result`, `validation_readout`.

**Keys whose meaning is load-bearing and easy to misread:**

| Key | What it is |
|---|---|
| `auc_lo`, `auc_lo_defold` | the lower bound on a discrimination value; **the de-folded one is the gate**, so that a lower bound may honestly fall below 0.5 (decision 7) |
| `stim_stable` | **three-valued**, and it abstains rather than passing when its test cannot run (decision 9) |
| `n_clusters` | the grouping count behind the per-rating result. **It disagrees with the per-week report's unit, and reconciling them is the open item awaiting a judgment call** |
| `n_low`, `n_high`, `n_obs`, `n_boot_ok` | the counts behind a split, a fit and the successful bootstrap resamples |
| `n_td`, `n_psd`, `n_channel` | how many voltage-trace and spectrum records, and channels, stood behind a value |
| `pro_first`, `rating_group`, `pro_df`, `t_epoch` | the pain-report ordering, its grouping, the report table, and the epoch timestamp |
| `weekly_era`, `stage1_openloop` | the stimulation-epoch labels |
| `not_assessed` | **the required wording when depth was reduced** — never reported as an absence |
| `freq_extrapolated` | true when the band centre sits outside 7.8 to 28.3 Hz, so the conversion is extrapolating |
| `psd_modeled` | the modelled tier marker; a value carrying it never sets a deployed number |
| `band_power`, `band_power_linear` | band power, and the closed-loop module's calibrated linear route |

**Routines by name:** `td_transform_band_power`, `td_to_lsb`, `device_psd_band_power`,
`modeled_lsb_at_center`, `harmonic_landings_hz`, `raw_lsb_spectrum_cache`,
`live_lsb_spectrum_match`, `per_pro_lsb`, `per_pro_lsb_spectrum`, `per_pro_lsb_overlay`,
`band_time_sweep_for_participant`, `warm_psd_cache`, `shared_cache_stats`, `clear_shared_cache`,
`build_pooled_detail_from_matrix`, `ramp_windows_from_amplitude`, `mean_power_before_next_change`,
`amplitude_response_shape`, `settings_stream`, `report_for_participant`, `bh_fdr`,
`_pro_timestamps_utc`, `_lsb_spectrum_signature`, `_rpy2_converter_ctx`, `_band_power_notched`,
`_freq_extrapolated`.

**Parameters and helpers with a fixed meaning:** `center_hz` and `half_hz` (a band is
`center ± half`, and `half_hz = 2.5` gives the 5 Hz device band), `td_list` and `psd_list` and
`n_td` (the two routes' record lists), `TIMEDOMAIN_TYPES` (which recording products count as
carrying a voltage trace), `FixBreaking` (the ingest concatenation repair — decision 3 left it in
place), `left_leg_vas` (the region-specific pain score that forms half of the composite metric),
`LabelMetric`, `BinarizationStrategy`, `LowPct`, `HighPct`, `MatchToleranceMin`, `MatchExtentSec`,
`MaxPerRating`, `RefractoryMin`, `AllowWindowReuse`, `UseLiveMatching` (the request fields).

**`BandCandidate`** is the name of the serializable object the biomarker module emits and the
closed-loop module consumes, version 1, schema in the design ledger.

**`per_pro_lsb_overlay` is built and not drawn** — see `DECISIONS_and_open_items.md` open item 14.

### Two more numeric constants, verified in the code this session

| Name | Value | Where | What it guards |
|---|---|---|---|
| `BOOT_CI_VALID_FLOOR` | **100** | `analytics.py:32` | the fewest successful bootstrap resamples before an interval may be reported at all |
| `MIN_RELIABLE_CLUSTERS` | **40** | `analytics.py:4352` | the fewest independent groupings before a result is treated as reliable |

### The rest of the live names an archived document referred to

**All of the following were confirmed present in the current source this session**, so none of them
is historical. Grouped by what they belong to.

- **The closed-loop and deployment payload:** `operating_points` and `operating_point` (the
  server-side full-array cut-point table, which closed audit item [5]), `live_evidence`,
  `lsb_overview`, `stability_verdict`, `selected_band`, `ValidationReadout`.
- **Portability across stimulation states:** `stim_state_portability` and `portable_by_ci`, which
  report a configuration as portable or fragile **from the interval rather than from a point
  estimate** — `bravo_service.py:5967`.
- **The stimulation-epoch machinery:** `stim_era`, `align_pros`, `pain_series`, `pain_high`,
  `t_epoch`.
- **The spectrum routes:** `welch_psd_for_instance` and `welch_rating_centered`
  (`streaming_psd.py:461`), `psd_scan_index`, `n_psd_bridge`, `lsb_from_uv2`,
  `bravo_chronic_to_lfp_df`, `PowerDomain`, `SurveyForms`, `MatchDirection`.
- **The statistics:** `auc_power`, `auc_perm`, `block_len` (the moving-block length from the
  autocorrelation), `n_excluded`.
- **Stim Optimizer's two-stage screen:** `run_two_stage`, `screen_cells`
  (`routines/lfp_evidence.py:1119`), `optimum_resolved`, and
  `surface_can_resolve_its_optimum` — **the last of these is the honest guard: it asks whether the
  measured surface can resolve its own optimum at all before any optimum is reported**
  (`StimOptimizer/bravo_service.py:211`).
- **Entry points:** `run_for_participant`, and `td_quantity_s`, which is the length-of-signal
  request field's name inside the matching code.

**Scratch analysis scripts named in archived documents** — `phase1_scan_v2.py`,
`phase2_glmer_v2.py`, `phase2b_hetero_v2.py`, `edges.py`, `bravo_harness`,
`all_sessions_amplitude_response.py`, `build_cache_map.py` — **are not platform code.** They live
in the untracked `cl_docs/` folder or were session-only. They are named here so that a reader who
finds one in an archived document knows it is not part of the module.
