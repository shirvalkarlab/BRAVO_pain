# The one cache store: what it is, why it exists, and how to finish it

**Written 2026-09-07 for the session that continues this work in another tool.** Until this file
existed, the store, the provenance chain and the database ledger appeared in **no markdown file in
the repository at all** — 1,771 lines of new code with nothing written down about it. That was the
single largest thing at risk of being lost in the handover.

`ARCHITECTURE_modules_and_store.md` describes the cache **as it was measured before this work**.
This file describes **what replaced it**. Where the two disagree, this one is newer.

---

## 1. What was wrong, in one paragraph

Two implementations of the same cache existed: one in `Biomarkers/bravo_service.py` and one in
`ClosedLoopDeployment/adapter.py`. Each had its own directory resolver, loader, writer, sweeper,
event counters and lock. They were not a deliberate pair — each was written when its own module
needed a cache, they shared a root by construction accident, and **their per-entry limits differed
by a factor of four.** Stim Optimizer, the slowest endpoint at about 85.8 s, had no store at all.
Nothing failed; the second copy simply drifted from the first, and **no page could report what the
cache as a whole was doing, because each copy counted into its own event dictionary.**

**On the limits, stated carefully because the first version of this note got the arithmetic
wrong.** The two caps were 1,073,741,824 bytes in the biomarker module and 268,435,456 in the
closed-loop module. **268,435,456 bytes is 256 MiB, so the smaller cap would NOT have refused the
245.90 MB tile entry** — it fits, with 4 to 9 percent to spare depending on whether that
measurement was decimal or binary. **The problem is that single-digit headroom on the one entry the
cache exists to hold, and that crossing a cap is silent**: the write is refused, the tiles stay in
one worker's memory, and the page simply becomes slow again with nothing in the log a reader would
think to check. The shared store uses the larger cap, which leaves about 4.2 times the current
size.

---

## 2. What now exists

`BRAVO/modules/CacheStore/`, 1,771 lines including tests.

| File | Lines | What it holds |
|---|---|---|
| `store.py` | 600 | the one store: directory resolution, format choice, read, write, stamp, sweep, statistics, the off switch |
| `provenance.py` | 173 | the chain carried by every written-back product, and the refusal that uses it |
| `ledger.py` | 221 | the append-only record in the database of what wrote each product and from which inputs |
| `locks.py` | — | the short-lived Redis build lock (Track F step 2): one worker builds, the others read the file when it appears, and Redis being unreachable means building as before |
| `tests/test_store.py` | 342 | round trips, the key-decides rule, the stamp, the sweep, the limit, backward compatibility |
| `tests/test_provenance_cycle.py` | 227 | **the constructed-cycle proof** and its controls |
| `tests/test_one_store.py` | 199 | fails if a second store implementation comes back |

### The three properties that matter more than the speed

**1. The key decides whether to write, not the caller.** `store_if_absent` is the entry point that
makes this true by construction rather than by every caller remembering to check first. A page
whose key already matches leaves the directory **byte-identical**, and
`test_a_matching_key_leaves_the_directory_byte_identical` compares a hash of every file to prove
it.

**2. No pain rating is in the key or the payload of any recording-derived product.** The tiles are
built with no knowledge of any rating; the same tiles serve every pain score, every match rule and
every length of signal; and the reports are fetched fresh from REDCap on every request. A rating in
the key would discard a 37-second build every time a report was filed. A rating in the payload
would let a file serve a stale rating, **which is the one failure in this system with no visible
symptom.**

**3. A module cannot consume a product its own output helped produce.** This is the reason the
provenance step was ordered before anything that writes back, and it is worth stating in full.

### The cycle, and why it has no symptom

The approved design makes the cache a route between modules: biomarker exploration writes its
results, closed-loop deployment writes its verdict, Stim Optimizer reads both and writes its own
outputs. **Those arrows close a loop.** Stim Optimizer decides which stimulation settings still
need exploring, and that decision determines **which recordings come to exist**. If it then reads a
ground-truth verdict computed from those same recordings and treats it as independent evidence,
**its own exploration policy is confirming itself.** Nothing crashes, no page errors, every number
is internally consistent, and the record simply looks like converging evidence when it is a loop. A
reviewer reading the output could not tell, and neither could we.

So every stored product carries the keys of every input it derived from, **flattened** so the whole
history is in one sidecar and cannot be defeated by an input file having been swept. A module names
itself when it asks for a product, and a product whose chain already contains that module's own
output is refused. **The refusal raises rather than returning nothing**, because a silent miss would
rebuild the same self-derived product and hand it over anyway.

**It is proven by constructing the cycle, not by asserting a rule.**
`tests/test_provenance_cycle.py` writes three real products through the real store — Stim
Optimizer's chosen ladder of currents, a biomarker result computed from that ladder, a closed-loop
verdict computed from that result — and then asks for the verdict as Stim Optimizer. It fails if the
refusal does not fire. **A test written against a hand-made chain would keep passing while the real
wiring leaked.** Every such test has its control: the same verdict built only from device
recordings **is** released, because a rule that refused everything would be trivially safe and
useless.

Raw kinds are exempt and named in `provenance.RAW_KINDS`: the tiles, the pain reports and the
therapy settings come from the device export or REDCap, and no module's choices produced them.

### The formats

Chosen from measurements on the real 6,629-row therapy table.

| Payload | Format | Why |
|---|---|---|
| a table | **Parquet with zstd** | 0.027 MB against pickle's 0.451, and a stable published format. **Pickle writes twice as fast and reads are tied** — this is a choice about size and durability, not speed. |
| a flat mapping of arrays | **compressed array file** | three-dimensional and numeric, not tabular; the 245.90 MB tile store reads in 0.05 s this way |
| anything else | pickle | what both predecessors used |

**Comma-separated and JSON files are excluded on correctness, not preference.** The therapy table
carries a timezone-aware timestamp and neither round-trips it, and that timestamp is what matches
therapy settings to neural signal — which is exactly where timezone errors have entered this
project before.

### The stamp

Every entry has a `<name>.meta.json` sidecar holding when it was written, what triggered it, which
module wrote it, how many recordings it covers, and the flattened provenance. **The sidecar is
moved into place after the payload and is the commit marker**, so a reader sees a complete entry or
no entry. It exists so a page can show the date of the last cache update without opening a 245 MB
file, and so a shared-memory freshness key has something authoritative to mirror.

### What the store refuses at write time, added on review 2026-09-07

A derived kind (anything not in `provenance.RAW_KINDS`) written with no `writer=` is refused and
counted, because its sidecar would look like a raw input to anything that later cited it. A
derived kind written with `provenance=None` is written but counted and logged. The ledger records
only writes under the production root, never under a caller's own root or the test override. Both
import spellings of the package resolve to one module object (`CacheStore/__init__.py`).

### Reading without the writer's key, added for step 8

`load_newest(kind, participant, consumer=...)` returns the newest entry of a kind for a
participant, with its stamp, applying the same consumer refusal as `load`. It exists because Stim
Optimizer cannot know the key the closed-loop module built its amplitude table under; it can only
ask for the newest one and then report, from the stamp, which tile entry it describes. An entry
whose payload is missing or unreadable is discarded and returned as `(None, stamp)`, so the
caller can say an entry existed and could not be read. `stamp_for_key(key)` returns the sidecar
of exactly the entry a product key names: a reader that cites an input by key must copy that
entry's chain, not the newest entry's, because the two agree only until the next write.

**A refused entry must be replaced, not skipped.** A stored product the store refuses to a
consumer is still on disk under its key. A recompute that writes "if absent" finds it, writes
nothing, and leaves every later request to be refused and recomputed again; the recompute
therefore writes through the plain `store`, which replaces it. The step 8 review found this.

### The off switch

`store.ENABLED = False` makes every read a miss and every write a no-op, deletes nothing, and
raises nothing. Two reasons: **if a stored product is ever suspected of being wrong, every page can
be made to recompute from the recordings with no code change and no deployment**; and "there is
nowhere to write" and "there is somewhere but do not use it" were the same state in both
predecessors, so the no-store behaviour could not be tested on a configured machine. It failed
exactly that way in the container before the switch existed.

---

## 3. What the two modules now contain instead

Both keep their old function names — `shared_cache_dir`, `_shared_path`, `_shared_load`,
`_shared_store`, `shared_cache_stats`, `clear_shared_cache` — because their own tests and three
bridge scripts call them. **Every one is now a delegation of a few lines.** The module-level
`_SHARED_CACHE_EVENTS` and `_SHARED_CACHE_LOCK` are **bound by reference to the store's own
objects**, so a count read in either module is the count the store actually made.

Net effect on the two files: **225 lines added, 342 removed.**

**The import is spelled twice on purpose:**

```python
try:
    from modules.CacheStore import store as _cache_store
except ImportError:
    from CacheStore import store as _cache_store
```

The container puts `/usr/src/BRAVO` on the path, which makes this package `modules.CacheStore`. The
host test suite runs from `BRAVO/modules` with that directory as the root, which makes it
`CacheStore`. **A single spelling breaks one of the two runners at import time**, which is how this
was found.

### What did NOT move, and why

`biomarker_psd` (97 files, 500.32 MB) and `biomarker_psd_rows` (6,309 files, 30.47 MB) are a
separate cache with its own resolver at `bravo_service._psd_cache_dir` and its own atomic writer.
**Folding them in is its own step in the plan** — "Move every cache to the single approved
location" — and doing it during the deduplication would have mixed a 500 MB migration into it.
`test_one_store.py` grandfathers exactly those two constructs in `_ALLOWED_PENDING_MIGRATION` and
**asserts the count is exactly one, so when that step lands the test fails and says to delete the
exemption.**

The tile kind also keeps its historical directory **and its historical file name**, because
245.90 MB of tiles are already on disk and cost 37 seconds to rebuild. The two closed-loop entries
were re-homed and rebuild once, which costs about 0.4 s.

---

## 4. The ledger

An append-only table `cache_store_ledger`, created on first use with a statement that does nothing
if it already exists — **so there is no migration to run by hand.** Both MySQL and SQLite are
supported because the container runs MySQL and the tests must run without it.

It answers what the sidecars cannot, because a sidecar is deleted when its entry is superseded:
which module wrote a product and how often it has been rebuilt; what the store held on the day a
figure was made; and **what a verdict derived from at the time, when its inputs have since been
swept.**

**Every function swallows its own exceptions.** Recording that a cache was written is bookkeeping;
refusing to serve a clinician's analysis because the bookkeeping failed would be the wrong trade in
every instance. `ledger.ENABLED = False` turns it off.

---

## 5. Test state, each read from a run on 2026-09-07

Two runners, two commands, and **a green run of one is not a green run of the platform.**

```
# container — Biomarkers (22 files) + CacheStore (4 files) + DecodeCommon (1); no pytest in there
python3 BRAVO/_agent_bridge/bridge_client.py --cwd /usr/src/BRAVO --timeout 900 --wait 900 \
  "python3 _agent_bridge/run_tests.py"
#   PASS=537 FAIL=0   (2026-09-07, after Track C step 4)

# host — ClosedLoopDeployment (11) + StimOptimizer (20) + CacheStore (4) + DecodeCommon (1); these use pytest
cd BRAVO/modules && PYTHONPATH=. python -B -m pytest \
  ClosedLoopDeployment/tests StimOptimizer/tests CacheStore/tests DecodeCommon/tests -q -W ignore
#   934 passed, 41 skipped   (2026-09-07, after Track C step 4, both orders)
```

Both figures were obtained twice, independently, and agreed. **Do not carry either number
forward — re-run.** Counts in this project's documents have gone stale inside a single session, and
one wrong count reached a pushed commit message that cannot be edited.

`run_tests.py` was extended this session to discover `CacheStore/tests` as well as
`Biomarkers/tests`. **`ClosedLoopDeployment` and `StimOptimizer` are deliberately excluded from
it** — their files (31 today) use pytest fixtures or `pytest.raises`, so importing them in the
container raises and would report one spurious failure per file.

---

## 6. What is left to build, in the plan's order

**Track A, steps 4 to 8, titled as in the approved plan.** Each writes a new table through
`store.store(..., writer=..., provenance=...)` and each must pass its provenance chain, or the
refusal cannot work. Progress against them is in `task_plan.md`, not here.

1. **Step 4, "Store the REDCap frame, and keep the freshness fetch anyway" — done 2026-09-07,
   second session.** The tidy pain-report table is written as kind `redcap_reports`, Parquet, keyed
   on the table's own content, once per distinct report set; the store keeps that kind's history
   rather than sweeping it (`KEEP_HISTORY_KINDS`); **no page reads it** — the fresh fetch on every
   request stays, and `Biomarkers/tests/test_redcap_snapshot.py` files a new report between two
   requests and requires the second to return it. The frame carries its store key
   (`PRO_STORE_KEY_ATTR`) so a derived product can cite it. Measured twice on the live record: no
   freshness check is cheaper than the fetch itself, so the stored copy buys reproducibility and a
   key for derived products, not speed.
2. **Step 5, "Write the therapy and pain matched table into the store" — done 2026-09-07, second
   session.** The settings stream read from the stored Percept files is kind `therapy_settings`,
   raw, keyed on the participant's source-file rows (`source_file_signature` in
   `StimOptimizer/adapter.py`); the epoch-level matched table is `therapy_pain_matched`, keyed on
   the settings key and the pain-report snapshot key, with both in its provenance, and registered
   as raw-derived because it is a deterministic join that embodies no exploration choice. The
   timezone-aware timestamp is why both are Parquet. On RCS08 the stored stream reads in about
   0.01 s against about 33 s to parse, equal field for field (decision 37).
3. **Step 6, "Write the biomarker results back after computing them" — done 2026-09-07, second
   session.** Two tidy tables, `biomarker_band_correlation` and `biomarker_band_discrimination`
   (`Biomarkers/routines/band_results_tables.py`), one row per contact pair, band centre and
   length of signal, every value copied from the sweep response, and the response itself as
   `biomarker_band_sweep`, served back when the key matches. All 22 centres, 8.5 to 29.5 Hz, read
   from the tile store's own centre list rather than a hardcoded range (decision 38).
4. **Step 7, "Write the amplitude effect on each band where Stim Optimizer can read it" — done
   2026-09-07, second session.** `ClosedLoopDeployment/amplitude_effect.py` derives one row per
   device-recorded run of rising current and band centre from the three-source comparison's
   voltage-trace panel: the number and range of currents tested, the slope of log power on current
   with its standard error and p-value, the curvature test and peak current, the fold change, and
   the harmonic-landing and checked-span flags; the closed-loop request writes it as
   `amplitude_effect_by_band` with the tile entry in its provenance (decision 40). Curvature is
   required, not optional: a rise-then-fall response exists in this record and a straight-line fit
   reads it as no response. **On this record the device ladders hold at most six settled settings
   per run, below the curvature routine's floor of eight, so the table reports curvature as not
   assessed everywhere; the documented finding rests on the clinic sheet (open item 18).**
5. **Step 8, "Have Stim Optimizer read the store and write its outputs back" — done 2026-09-07,
   second session.** `StimOptimizer/bravo_service.py` reads the matched table (through
   `adapter.build_design_matrix`, step 5) and the newest `amplitude_effect_by_band` as
   `consumer="stim_optimizer"`, **the exact edge the refusal exists for**, and reports which tile
   entry that table describes and whether it is the current one. It writes back
   `stim_optimizer_summary`, `exploration_ladder`, `exploration_batch`, `stim_optimizer_manifest`
   and the whole response as `stim_optimizer_response`, under one key naming every input and every
   setting, with each input's own chain flattened in (decision 41). A matching key is served from
   the store; a refused entry is reported and recomputed; a failed write is reported in the
   response. Proven on RCS08 after the review: 21,381 response values, 0 differences, in each of
   two alternating rounds, fresh 50.04 and 50.47 s against served 1.37 and 1.44 s. **The first live run wrote
   nothing back and every test passed** — the pipeline's queue carries a `rank` column the test
   stub lacked — which is why the live proof is not optional. Reviewed by five perspectives
   before the commit: a refused entry is now replaced rather than left to refuse every later
   request, the chain is taken from the entry the key names (`store.stamp_for_key`), and a digest
   of the module's own code is in the key
   (`artifacts/review_2026-09-07_step8_stim_optimizer_store.md`). **Track A is complete.**

**The ground-truth verdict is Track G step 2, done 2026-09-07.** The rule is decision 33
(`METHODS_measurement_and_findings.md` §6); `ClosedLoopDeployment/ground_truth.py` applies it to
every run, band and setting of the three-source comparison, the closed-loop request writes it as
`ground_truth_verdict` with the tile entry in its provenance, and Stim Optimizer reads it as
`stim_optimizer` (decision 47). The device route's saturation ceiling that the rule requires is
a provisional constant, open item 20.

Then the other tracks: the canonical decoded form, the re-derivation speedups, the Redis build
lock, moving the remaining caches into the one location, and the statistics site that needs its own
sign-off.

---

## 7. The equality-proof procedure, which is not optional

Every step that changes how a number is produced or stored must prove the numbers did not move,
and every step that speeds something up must report its timings honestly. The procedure, as
approved:

1. **Capture the full response before the change** on the live participant
   `2e3c75c00d7f4f37b53a048d195f11da`, through the bridge.
2. **Capture it again after.**
3. **Report a field count and a difference count** — how many values were compared, and how many
   differed. **Never a tolerance.** "Within 1e-9" hides a real change in a value that happens to be
   small.
4. **Timings in alternating rounds** — before, after, before, after — because the operating
   system's file cache favours whichever ran second, and a single pair of runs measures that
   instead of the change.
5. **A speed claim and its equality proof appear in the same report.** One without the other is not
   a result.

The 21.4x matcher change is the worked example: proven over 1,080 configurations with **zero** field
differences.
