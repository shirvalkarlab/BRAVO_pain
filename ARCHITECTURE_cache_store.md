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
# container — Biomarkers (19 files) + CacheStore (3 files); no pytest in there
python3 BRAVO/_agent_bridge/bridge_client.py --cwd /usr/src/BRAVO --timeout 900 --wait 900 \
  "python3 _agent_bridge/run_tests.py"
#   PASS=455 FAIL=0

# host — ClosedLoopDeployment (10) + StimOptimizer (18) + CacheStore (3); these use pytest
cd BRAVO/modules && PYTHONPATH=. python -B -m pytest \
  ClosedLoopDeployment/tests StimOptimizer/tests CacheStore/tests -q -W ignore
#   814 passed, 41 skipped
```

Both figures were obtained twice, independently, and agreed. **Do not carry either number
forward — re-run.** Counts in this project's documents have gone stale inside a single session, and
one wrong count reached a pushed commit message that cannot be edited.

`run_tests.py` was extended this session to discover `CacheStore/tests` as well as
`Biomarkers/tests`. **`ClosedLoopDeployment` and `StimOptimizer` are deliberately excluded from
it** — all 28 of their files use pytest fixtures or `pytest.raises`, so importing them in the
container raises and would report 28 spurious failures.

---

## 6. What is left to build, in the plan's order

**Track A, the remaining five steps.** Each writes a new table through
`store.store(..., writer=..., provenance=...)` and each must pass its provenance chain, or the
refusal cannot work:

1. **The REDCap pain-report snapshot** — and **keep the fresh fetch anyway.** Measured twice on the
   live record: no freshness check is cheaper than the fetch itself, so the stored copy buys
   reproducibility, not speed.
2. **Therapy settings matched in time to pain scores** — the timezone-aware timestamp is why this
   is Parquet.
3. **Biomarker results per band centre and contact pair.** All 22 centres, 8.5 to 29.5 Hz, read
   from the store's own centre list rather than a hardcoded range.
4. **The amplitude effect on each band**, with slope, **curvature**, and the number and range of
   currents actually tested. Curvature is required, not optional: a rise-then-fall response exists
   in this record and a straight-line fit reads it as no response.
5. **The ground-truth verdict**, which closed-loop writes and Stim Optimizer reads — **the exact
   edge the refusal exists for.** The rule itself is decided and is in
   `METHODS_measurement_and_findings.md` §6.

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
