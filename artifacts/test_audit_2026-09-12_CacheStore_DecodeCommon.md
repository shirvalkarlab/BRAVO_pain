# Test audit, 2026-09-12: the saved-answers store (CacheStore) and the decoded form (DecodeCommon)

**Read-only analysis. Nothing was deleted or changed; the decision is the principal investigator's.**
Branch `PS_closedloop_deployment`, working directory `/Users/pshirvalkar/dev/BRAVO_pain` (not a
worktree, checked with `pwd`). Every test body and the production code it calls was read; callers
were counted with `grep` over `BRAVO/modules` and `BRAVO/Server`, excluding every `tests/` folder
and the `_agent_bridge` scratch area. The suites were NOT run here; the orchestrator runs them.

**Words used below, defined once.**

- *the store* — the saved answers on disk, `BRAVO/modules/CacheStore/store.py`.
- *the label* — what a saved answer is filed under, built from everything that could change it
  (the code calls it the key or signature).
- *the companion file* — the small `.meta.json` written beside every saved answer, recording when
  it was written, by which module, and from which inputs (the code calls it the sidecar or stamp).
- *the input list* — the list of every saved answer a new one was built from, carried in the
  companion file (the code calls it the provenance chain).
- *the refusal* — the rule that a module may not read a saved answer whose input list contains
  that module's own output. It is the reason the input list exists (decision 31).
- *the two runners* — the container's own runner (`_agent_bridge/run_tests.py`, no pytest, calls
  every top-level `test_` function with no arguments) and the host's pytest run. These nine files
  run on BOTH on purpose.

---

## 1. Summary table

| File | Lines | Tests | KEEP | DEAD-TARGET | SUPERSEDED | SHAPE-ONLY | MISNAMED | DUPLICATE | LIVE-DATA |
|---|---|---|---|---|---|---|---|---|---|
| `CacheStore/tests/test_store.py` | 578 | 29 | 26 | 1 | 0 | 0 | 2 | 0 | 0 |
| `CacheStore/tests/test_provenance_cycle.py` | 277 | 10 | 10 | 0 | 0 | 0 | 0 | 0 | 0 |
| `CacheStore/tests/test_one_store.py` | 217 | 8 | 4 | 0 | 0 | 0 | 1 | 0 | 3 |
| `CacheStore/tests/test_closed_loop_reads_band_sweep.py` | 171 | 3 | 3 | 0 | 0 | 0 | 0 | 0 | 0 |
| `CacheStore/tests/test_keep_newest.py` | 136 | 5 | 5 | 0 | 0 | 0 | 0 | 0 | 0 |
| `CacheStore/tests/test_locks.py` | 130 | 7 | 7 | 0 | 0 | 0 | 0 | 0 | 0 |
| `CacheStore/tests/test_ledger.py` | 84 | 4 | 4 | 0 | 0 | 0 | 0 | 0 | 0 |
| **CacheStore total** | **1,593** | **66** | **59** | **1** | **0** | **0** | **3** | **0** | **3** |
| `DecodeCommon/tests/test_decode_common.py` | 489 | 36 | 34 | 0 | 0 | 1 | 0 | 1 | 0 |
| `DecodeCommon/tests/test_matching.py` | 174 | 10 | 10 | 0 | 0 | 0 | 0 | 0 | 0 |
| **DecodeCommon total** | **663** | **46** | **44** | **0** | **0** | **1** | **0** | **1** | **0** |

Line and test counts are from `wc -l` and `grep -c "^def test_"` run today, not carried from a
document. **Neither module has a test that uses a pytest-only construct**: `grep` for `pytest`,
`@fixture`, `monkeypatch` across the nine files finds only docstrings saying pytest is absent, and
every `test_` function takes no arguments, so all 112 run on both runners.

**Tests likely to take more than 5 seconds: none found by reading.** The only sleeps are three in
`test_locks.py` of 0.1 to 0.15 s. The largest constructed inputs are three 200-second recordings
at 250 Hz (`test_identical_across_a_mixed_record_of_many_reports`) and 600 small random trials
(`test_direction_handling_matches_the_source_function_exactly`). No test loads the live record.

---

## 2. Per file: every test that is not KEEP, with its evidence

### `test_store.py` (29 tests; 26 KEEP)

- `test_stats_reports_what_is_on_disk_and_what_the_store_has_done` -- **DEAD-TARGET, protected** --
  `store.stats()` has **0 callers outside tests** (`grep -rn "\.stats("` over every production
  file that imports the store finds none; the two modules' own `shared_cache_stats` functions in
  `Biomarkers/bravo_service.py:1198` and `ClosedLoopDeployment/adapter.py:713` read the event
  counters directly and never call it). It is a diagnostic for the bridge and for an operator,
  and `ARCHITECTURE_cache_store.md` §2 lists "statistics" as part of the store, so it is kept on
  purpose. **Not on the delete list**; the PI decides whether the operator surface stays.
- `test_the_stamp_is_readable_without_opening_the_payload` -- **MISNAMED** -- the name promises the
  payload is not opened, but the body never checks that: it asserts the companion file's values
  (`stamp["trigger"] == "ingest"`, `stamp["n_recordings"] == 832`, `stamp["writer"] ==
  "biomarkers"`, `stamp["format"] == "npz"`, a timezone-aware timestamp) and never watches
  whether the payload file was read. The neighbouring test
  `test_a_mismatched_sidecar_is_a_miss_without_the_payload_being_opened` already shows how: it
  replaces `st._load_payload` with a spy and asserts `opened == []`. The value assertions are
  good and should stay; the name's claim needs the spy or the name needs shortening.
- `test_the_two_predecessors_mismatched_limits_are_gone_and_the_larger_one_won` -- **MISNAMED** --
  three of its five assertions compare two numbers defined in the test file itself
  (`_OLD_SMALL_CAP_BYTES == 268_435_456`, `_OLD_SMALL_CAP_BYTES > _MEASURED_TILE_BYTES`,
  `_OLD_SMALL_CAP_BYTES / _MEASURED_TILE_BYTES < 1.10`) and can never fail against production
  code. The "mismatched limits are gone" half of the name is not checked here at all; it is
  checked by `test_the_per_entry_limits_no_longer_differ` in `test_one_store.py`, and only in the
  container. What this test genuinely pins is `st.MAX_BYTES_DEFAULT == 1 GiB` and that the limit
  is more than four times the measured 245.90 MB tile entry -- a worthwhile pin of a value the
  store applies on every write (`store.py:710`), under a name that says something else.

### `test_one_store.py` (8 tests; 4 KEEP)

The two tests the brief asked about first are KEEP for the reason `ARCHITECTURE_cache_store.md` §2
gives: `test_no_other_module_builds_a_cache_directory_of_its_own` asserts the grandfathered count
is exactly one so that folding the per-recording cache into the store makes it fail and say to
delete the exemption (decision 51 kept that cache outside the store on a measurement; CLAUDE.md §2
principle 4 names this test). Verified today: `os.path.join(base, "cache")` appears exactly once
in the three scanned files, at `Biomarkers/bravo_service.py:2053`.

- `test_no_other_module_pickles_a_cache_entry_itself` -- **MISNAMED** -- the name says no other
  module writes a cache file itself; the body waves through every line spelled exactly
  `os.replace(tmp, path)` with no count. There are **three** such lines today
  (`Biomarkers/bravo_service.py:2126, 2161, 2255`, the manifest, the saved list and the
  per-recording writer of the one cache decision 51 kept outside the store) where the exemption
  note describes "its own atomic writer", singular. A fourth private writer using that spelling
  would pass. The cache-root test beside it asserts its count (`allowed_seen == 1`); this one
  should assert three.
- `test_both_modules_resolve_under_the_one_root` -- **LIVE-DATA (container only)** -- returns
  silently, as a pass, when `from Biomarkers import bravo_service` raises for any reason
  (`_modules_or_none` catches `Exception`). On the host it always passes without checking
  anything, because that import needs Django. **The skip can silently make it never run**: on
  2026-09-10 a stale worker answered "No module named 'ClosedLoopDeployment'" (decision 113), and
  under that condition this test would report PASS. Checked today through the bridge: the bare
  import works in the container, so the test does run there now.
- `test_the_two_modules_count_into_the_same_events` -- **LIVE-DATA (container only)** -- same
  silent-pass condition as above. When it runs it checks identity (`B._SHARED_CACHE_EVENTS is
  st._EVENTS`), which is the right check for "one set of counters".
- `test_the_per_entry_limits_no_longer_differ` -- **LIVE-DATA (container only)** -- same silent-pass
  condition. When it runs it checks `B._SHARED_CACHE_MAX_BYTES == AD._SHARED_CACHE_MAX_BYTES ==
  st.MAX_BYTES_DEFAULT`; both modules bind that name to the store's constant
  (`bravo_service.py:1161`, `adapter.py:438`).

### `test_provenance_cycle.py` (10 tests; 10 KEEP)

All KEEP. The three cycle tests build the loop through the real store (a chosen ladder, a band
result derived from it, a verdict derived from that) and require the refusal to raise when Stim
Optimizer asks for the verdict; `ARCHITECTURE_cache_store.md` §2 says this constructed cycle, not
a hand-written chain, is the proof, and decision 31 is the rule. Each has its control (the same
verdict from device recordings only is released). `refusal_for`, `writers_in`, `flatten` and
`module_of` have no callers outside the store package, but `store.load` and `store.load_newest`
call `refusal_for` (`store.py:518, 426`), which calls `writers_in`, and every write-back site
calls `flatten` (`adapter.py:1574, 1661, 1735, 1829`; `bravo_service.py:8010`), so all four are
live. `SelfDerivedProduct` is caught in production at `StimOptimizer/bravo_service.py:186, 238,
517`.

### `test_closed_loop_reads_band_sweep.py` (3 tests; 3 KEEP, with a caveat)

All KEEP: the refusal property (released to `closed_loop`, `biomarkers` and `stim_optimizer`;
refused when the chain cites `ground_truth_verdict`) is checked by outcome, with its control.
**Caveat, decision 96's class of risk**: the fixture copies the real input list by hand rather
than calling the producer. Read side by side today, the copy still matches
`Biomarkers/bravo_service.py:8010-8012` (tiles plus pain-report snapshot, both raw kinds). But
the docstring's "read exactly the way ClosedLoopDeployment would" is out of date: since decision
131 the Closed-Loop reader uses `load_newest(..., match=)` on the companion file's
`extra["sweep_settings"]` tag (`adapter.py:583`), not the keyed `load` this test uses, and the
fixture writes no such tag. The refusal rule is the same code in both readers, so the test still
proves what its name says; the four length assertions (`len(grid["center_freqs_hz"]) == 3` and
three like it) only re-read the test's own fixture and prove nothing about production.

### `test_keep_newest.py` (5 tests; 5 KEEP)

All KEEP, pinning decision 107 (six scores in, six back; an unlisted kind still keeps one; the
limit holds and the oldest goes; payload and companion file go together; one participant does not
evict another). Every test reads back through `store.load` and compares the value
(`got[m] == {"metric": m}`).

### `test_locks.py` (7 tests; 7 KEEP)

All KEEP. `locks.build_lock` is live at `Biomarkers/bravo_service.py:1496` (decision 46), and
each test asserts the role and reason a caller gets (`o.role == "builder"`, `"served"`,
`"fallback"` with `"waited"`, `"unavailable"`, `"disabled"` in the reason). **One file-level
hazard, not a classification**: this file has no `sys.path` insertion and imports
`modules.CacheStore`; on the host that spelling is importable only because an alphabetically
earlier file in the same folder inserted the BRAVO root first. Verified: from `BRAVO/modules` with
`PYTHONPATH=.`, `from modules.CacheStore import locks` raises `ModuleNotFoundError`. Running this
file alone with pytest fails at import; running the folder passes.

### `test_ledger.py` (4 tests; 4 KEEP)

All KEEP. `ledger.record` is live (`store.py:748`, on every production-root write). The two
read-back functions, `history()` and `counts_by_kind()`, have **0 callers outside the store
package**; they are the audit readers `ARCHITECTURE_cache_store.md` §4 describes ("what a verdict
derived from at the time, when its inputs have since been swept"), read by hand when an audit
needs them, and they are the only way these tests can check a row landed without raw SQL. Not a
deletion candidate; recorded so nobody mistakes them for dead code.

### `test_decode_common.py` (36 tests; 34 KEEP)

- `test_the_version_is_an_integer_a_stored_copy_can_be_keyed_on` -- **SHAPE-ONLY** -- the whole
  body is `assert isinstance(CHANNEL_INDEX_VERSION, int) and CHANNEL_INDEX_VERSION >= 1`: a type
  check and a lower bound, never the value (3 today, `representation.py:73`). Its name also
  assumes a stored copy of the form exists to be labelled by it; `grep -rn CHANNEL_INDEX_VERSION`
  over Biomarkers, ClosedLoopDeployment and StimOptimizer finds **0 uses** -- the form is built per
  request and never stored, so nothing keys on this number. A rewrite should either pin the value
  (so a bump is a deliberate edit) or go.
- `test_reading_the_same_form_twice_gives_the_same_answer` -- **DUPLICATE** of
  `test_the_form_is_not_mutated_by_being_read` -- it calls `per_pro_lsb_indexed` twice on one form
  and compares the two outputs. The reader holds no state and draws no random numbers (`grep` for
  `random`, `lru_cache`, `_MEMO`, `global` in `per_pro_lsb_indexed.py`: 0 hits), so the only way a
  second read could differ is if the first mutated the form -- exactly what the neighbouring test
  checks directly, by comparing the form's arrays before and after three reads. No added value.

Two tests are KEEP with a note. `test_a_recording_with_an_unreadable_start_time_is_dropped_and_counted`
and `test_a_spectrum_record_with_an_unreadable_time_is_dropped_and_counted` check the drop (live:
`build_channel_index` is called at `availability.py:1265` on every page that reads the form)
through `ChannelIndex.summary()`, which has **0 production callers** (the one `.summary()` hit in
production, `ClosedLoopDeployment/adapter.py:1333`, is a different object). The "counted" half of
each name describes a diagnostic nothing reads.

The fourteen `test_identical_*` tests and `test_the_platform_entry_points_give_the_scan_answer_under_both_switch_settings`
compare the live reader against `availability._per_pro_lsb_scan`, which production reaches only
when `USE_CHANNEL_INDEX` is switched off (`availability.py:1283`; the switch is `True`). That is
by design: decision 43 keeps the scan as "the reference implementation" the indexed reader is
proven equal to, so comparing against it is the proof, not a comparison of a function with a copy
of itself. `test_the_form_stores_no_calibration_constant` scans the module's source for the two
constants; decision 42 names that test explicitly. `test_a_naive_start_time_is_read_as_utc_on_every_host`
and `test_a_timezone_aware_start_time_is_unchanged_by_the_naive_utc_rule` pin decision 102 with an
expected value built independently of both functions under test.

### `test_matching.py` (10 tests; 10 KEEP)

All KEEP. `matching.matched_samples` is live at `Biomarkers/adapter.py:199` and
`Biomarkers/routines/streaming_psd.py:865` (decisions 76, 117). The 600-trial comparison against
`streaming_psd._match_to_pro` is against the reference implementation decision 117 keeps for
exactly this proof; the other nine assert specific matched values, offsets and report indices on
hand-built fixtures.

---

## 3. Safe to delete now

One test. Everything else that is not KEEP is either protected by a decision or worth rewriting.

1. `DecodeCommon/tests/test_decode_common.py::test_reading_the_same_form_twice_gives_the_same_answer`
   -- DUPLICATE of `test_the_form_is_not_mutated_by_being_read` (the reader has no state and no
   randomness, so the two tests can only fail together). Deleting it changes the container count
   and the host count by one each.

Not on this list, and why: `test_stats_reports_what_is_on_disk_and_what_the_store_has_done` targets
a function with 0 production callers, but `ARCHITECTURE_cache_store.md` §2 lists it as part of the
store and it is the bridge's diagnostic -- a decision, not a deletion. No test pins a rule the
decision log has reversed (SUPERSEDED-RULE: 0 in both modules).

## 4. Rewrite, do not delete

1. `test_store.py::test_the_stamp_is_readable_without_opening_the_payload` -- add the
   `_load_payload` spy the neighbouring test already uses and assert `opened == []`, or drop
   "without opening the payload" from the name. The value assertions stay.
2. `test_store.py::test_the_two_predecessors_mismatched_limits_are_gone_and_the_larger_one_won`
   -- keep the two live assertions (`MAX_BYTES_DEFAULT == 1 GiB`; more than 4x the measured tile
   entry), drop the three that compare test-file constants with each other, and rename to what it
   checks (the value of the one limit and its headroom). The "gone" half lives in
   `test_one_store.py` and should be named there, not here.
3. `test_one_store.py::test_no_other_module_pickles_a_cache_entry_itself` -- count the exempted
   `os.replace(tmp, path)` lines and assert the count is 3, the way the cache-root test asserts
   its count is 1, so a fourth private writer is caught and the exemption note can say "three
   writers of the one per-recording cache" instead of one.
4. `test_decode_common.py::test_the_version_is_an_integer_a_stored_copy_can_be_keyed_on` -- pin
   the value (`== 3`) so a bump is deliberate, and rename to drop "a stored copy can be keyed on",
   since nothing stores the form; or delete it if the PI agrees the number guards nothing.

## 5. Findings beside the classifications

These are not about any one test's class; they are what the reading turned up.

1. **The one-store guard scans three files; seven production files now import the store.**
   `test_one_store.py`'s `_CONSUMERS` names `Biomarkers/bravo_service.py`,
   `ClosedLoopDeployment/adapter.py` and `StimOptimizer/adapter.py`. `grep -rln CacheStore` over
   production also finds `StimOptimizer/bravo_service.py`, `ClosedLoopDeployment/session_report_facts.py`,
   `ClosedLoopDeployment/device_facts.py` and `Biomarkers/routines/streaming_psd.py`. Grepped
   today, none of the four contains a cache-root join, an `os.replace`, or a store subdirectory
   name used as a path, so the guard is not wrong today -- its scope is behind the code.
2. **Three container-only tests pass silently on any import failure** (§2, `test_one_store.py`).
   A `return` on `except Exception` reads as PASS in `run_tests.py`'s count. Decision 113 saw a
   worker in exactly that state.
3. **`store.load_newest(match=...)`, added for decision 131, has no test in `CacheStore/tests`.**
   Its only tests are `ClosedLoopDeployment/tests/test_grid_matches_biomarkers_settings.py`, which
   run on the host only. The store's own behaviour for a `match` that rejects the newest entry
   and accepts an older one is unpinned on the container runner.
4. **`test_the_ledger_records_production_writes_and_not_writes_under_an_override`'s positive half
   never runs in the container.** The block that proves a production-root write IS recorded is
   guarded by `if st.root_dir() == os.path.join(prod, "cache")`, which is false whenever Django
   supplies the storage path, so it runs on the host only. The two refusal halves run everywhere.
   The guard is what keeps the test from writing into the production root, so it is correct; it
   is recorded here so the container's PASS on this test is not read as covering both halves.
5. **The legacy no-companion-file branch serves no file today.** `test_the_existing_tile_files_are_still_found_by_their_historical_name`
   pins the branch in `store.load` (`store.py:505`) that reads a tile file written before the
   store existed. Checked through the bridge today: the container's `biomarker_shared` folder
   holds 1 tile `.pkl`, and 0 of them lack a `.meta.json`. The branch and the test are
   backward-compatibility for a state the record no longer has; classed KEEP because the branch is
   still in production `load`, and named here so the PI can decide whether to retire both together.
6. **`test_locks.py` depends on import order** (§2).
7. **Every test in both modules runs on both runners** (§1): no fixtures, no `pytest.raises`, no
   parameters.

## 6. What was done to this tree

No file under `BRAVO/modules`, `BRAVO/Server`, or the repository root was edited. One disposable
probe script, `BRAVO/_agent_bridge/_audit_probe_one_store.py`, was written and run once through
the bridge (read-only: it imports two modules by their bare names and lists one folder). It is
matched by `.gitignore` line 369 (`BRAVO/_agent_bridge/_*`), confirmed with `git check-ignore`,
and does not appear in `git status`. Two helper shell scripts live in the session scratchpad
outside the repository.
