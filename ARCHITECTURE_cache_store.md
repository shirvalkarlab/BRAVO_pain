# The one cache store

Compacted 2026-09-19; the full original with its measurements is at
`docs/archive/2026-09-19/ARCHITECTURE_cache_store.md`. `ARCHITECTURE_modules_and_store.md` describes
the cache as it was before this work; where they disagree, this file is newer.

## 1. Why it exists

Two cache implementations lived in `Biomarkers/bravo_service.py` and `ClosedLoopDeployment/adapter.py`,
shared a root by accident, and their per-entry caps differed by exactly four (1,073,741,824 against
268,435,456 bytes). The smaller cap is 256 MiB, so it did fit the 245.90 MB tile entry, with only
4 to 9 percent to spare on the one entry the cache exists to hold. That headroom is the problem,
because crossing a cap is silent: the write is refused, the tiles stay in one worker's memory, and the
page becomes slow with nothing in the log. The one store uses the larger cap. Stim Optimizer, the slowest endpoint,
had no store at all (decision 30).

## 2. What exists: `BRAVO/modules/CacheStore/`

`store.py` (directory resolution, format choice, read, write, stamp, sweep, statistics, off switch),
`provenance.py` (the chain every written-back product carries, and the refusal), `ledger.py` (the
append-only database record of what wrote each product and from which inputs), `locks.py` (the
short-lived Redis build lock), and tests: `test_store.py`, `test_provenance_cycle.py` (the
constructed-cycle proof), `test_one_store.py` (fails if a second store implementation comes back;
grandfathers only the per-recording spectrum cache's own directory and writer, decision 51),
`test_keep_newest.py`.

**The import is spelled twice on purpose**, and both spellings resolve to one module object:

```python
try:
    from modules.CacheStore import store as _cache_store   # container: /usr/src/BRAVO on the path
except ImportError:
    from CacheStore import store as _cache_store           # host suite: BRAVO/modules is the root
```

Both modules keep their old names (`shared_cache_dir`, `_shared_load`, `_shared_store`, ...) as
delegations of a few lines; their event counters are bound by reference to the store's own.

## 3. The three properties that matter more than speed

1. **The key decides whether to write, not the caller.** `store_if_absent` makes it true by
   construction; a matching key leaves the directory byte-identical, and a test hashes every file to
   prove it (decision 26).
2. **No pain rating in the key or payload of any recording-derived product.** Tiles are built with
   no knowledge of ratings and serve every score, match rule and length; reports are fetched fresh.
   A rating in the key discards a 37 s build on every report; a rating in the payload lets a file
   serve a stale rating, the one failure with no visible symptom (decision 23).
3. **A module cannot consume a product its own output helped produce.** Stim Optimizer decides
   which settings to explore, which decides which recordings exist; if it read a verdict computed
   from those recordings as independent evidence, its own policy would confirm itself with no
   error and no symptom. So every stored product carries the keys of every input, flattened into
   its sidecar; a module names itself as `consumer=` when it reads; a chain that already holds that
   module's output is refused, and **the refusal raises** rather than returning nothing.
   `test_provenance_cycle.py` proves it by writing three real products through the real store
   (ladder, biomarker result from it, verdict from that) and asking for the verdict as Stim
   Optimizer; its control is the same verdict from device recordings only, which IS released
   (decision 31). Raw kinds (tiles, pain reports, therapy settings, the assembled spectrum matrix, the
   acquisition timeline) are exempt, named in `provenance.RAW_KINDS`; `therapy_pain_matched` is raw-derived because its
   join embodies no choice (decision 37).

## 4. Mechanics

- **Formats.** Tables: Parquet+zstd (0.027 MB against pickle's 0.451 on the therapy table; pickle
  writes twice as fast, reads tie; the choice is size and durability). Flat mappings of arrays:
  compressed array files (the 245.90 MB tiles read in 0.05 s). Otherwise pickle. **CSV and JSON are
  excluded on correctness**: the therapy table's timezone-aware timestamp does not round-trip, and
  that timestamp matches settings to signal (decision 29).
- **How many entries a kind keeps.** One per participant per kind by default, replaced whole.
  `store.KEEP_NEWEST_BY_KIND` names the exceptions: the three sweep kinds keep 12 (six scores at a
  reader's settings and six at the daily defaults; a rating-keyed kind under the default deleted five
  of six grids while every write reported success, decision 107), `closed_loop_simulation` and
  `closed_loop_design_rule` keep 6 (one per candidate band), Stim Optimizer keeps its two request
  shapes. Unbounded history was rejected: a store that only grows is not a cache.
  A writer may name a keep group in the sidecar (`extra["keep_group"]`): the newest entry of each
  group survives the removal and does not count toward the limit, older ones age out as before. The
  heat-map grid at the daily default settings names one per pain score, so a reader working at other
  settings cannot evict the grid the Stim Optimizer reads (decision 318).
- **The stamp.** Every entry has a `<name>.meta.json` sidecar: when written, trigger, writer,
  recording count, flattened provenance. It is moved into place after the payload and is the commit
  marker, so a reader sees a complete entry or none; pages read the build date from it, never from
  a file timestamp.
- **Refused at write time.** A derived kind with no `writer=` is refused and counted; a derived
  kind with `provenance=None` is written but counted and logged; the ledger records production-root
  writes only (decision 39). Participant identifiers become part of file names only after
  sanitising to letters, digits, dash, underscore.
- **Reading without the writer's key.** `load_newest(kind, participant, consumer=)` applies the
  same refusal; `stamp_for_key(key)` returns exactly the entry a key names, so a citing product
  copies that entry's chain, not the newest one's. **A refused entry must be replaced, not skipped**:
  a recompute writes through plain `store`, or every later request is refused and recomputed again
  (decision 41). Readers on another page must match the writer's settings tag, not take the newest
  of any settings (decision 131).
- **The off switch.** `store.ENABLED = False` makes every read a miss and every write a no-op,
  deletes nothing: any suspected-wrong product can be recomputed everywhere with no deployment,
  and the no-store path is testable on a configured machine. **Tests use this switch, and clear only
  while their own directory override is in force**; a clear after the override is restored empties
  the production root (decisions 116, 129), and a launcher reachable from a unit test started real
  background jobs against it (decision 96): three times a test has reached the production store.
- **The build lock.** `locks.py`: Redis lock on the tile key, 300 s expiry against a ~37 s build;
  a waiter reads the file when its sidecar appears, builds anyway after 150 s; Redis unreachable
  means build as before. Four concurrent cold requests: one build, all served in ~41 s, against
  ~368 s with four contending builds (decision 46).
- **The ledger.** `cache_store_ledger`, created on first use (no migration), MySQL and SQLite. It
  answers what sidecars cannot once an entry is swept: who wrote a product, how often it was
  rebuilt, what a verdict derived from at the time. Every function swallows its own exceptions;
  `ledger.ENABLED = False` turns it off.
- **What moved and what did not.** The assembled spectrum matrix is the raw kind
  `biomarker_psd_matrix` (decision 53). The 6,309-file per-recording spectrum directory stays where
  it is, fronted by a stamp over the recording set (0.35 s against 3.1 s), because one-snapshot-
  per-kind would force a full rewrite on every new recording (decision 51). Tiles keep their
  historical directory and file name.

## 5. The equality-proof procedure (not optional; the canonical statement)

Every step that changes how a number is produced or stored proves the numbers did not move; every
speed-up reports its timings honestly.

1. Capture the full response **before** the change on the live participant
   `2e3c75c00d7f4f37b53a048d195f11da`, through the bridge, with the stored answer bypassed.
2. Capture it again **after**.
3. Report **a field count and a difference count**, and name what the differing fields are
   (timing, store key, the intended change). **Never a tolerance**: "within 1e-9" hides a real
   change in a value that happens to be small.
4. **Timings in alternating rounds** (before, after, before, after): the operating system's file
   cache favours whichever ran second.
5. **A speed claim and its equality proof appear in the same report.**

Worked example: the matcher vectorisation (`958cc89`), 21.4x over 1,080 configurations with zero
field differences. Test counts are never carried forward from a document; re-run both suites
(`CLAUDE.md` §1).
