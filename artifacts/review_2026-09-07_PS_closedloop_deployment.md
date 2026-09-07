# Code review of branch `PS_closedloop_deployment`, 2026-09-07

**Scope.** The ten commits ahead of `origin` (from `7f1882f` to `7278f15c`: the record
consolidation, the one store with its provenance chain and ledger, the decoded-form prototype,
the handover package, the framework merge, Track A steps 4 and 5) plus the uncommitted Track A
step 6 work in the tree at the time of review. Code: 21 files, 4,101 lines inserted and 345
removed in the commits, and about 700 lines uncommitted. Documents: 84 markdown files, 11,291
lines. There is no pull request, no `.github/workflows`, and no mechanised size gate in this
repository, so nothing ran automatically; the per-commit code line counts were read from
`git log --numstat`: 2,763 for the store commit, 823 for the prototype, 515 for step 5, 385 for
step 4, and 0 for the six document-only commits.

**Method.** Six reviewers in parallel, one perspective each (security, performance, architecture,
test coverage, code quality, scope adherence), every finding verified against the working tree
rather than the diff text; then adversarial questioning and root-cause analysis by the
orchestrating session. The security findings were set aside by the principal investigator's
instruction during the review: the data are de-identified. They are listed at the end so the
decision is on record, not acted on.

## Verdict

**Needs work, and the work was done in the same session.** No critical defect in the committed
code. Two high findings and eight medium findings were fixed before the step 6 commit; the
fixes are listed with their tests below. Three items are left for the principal investigator's
decision and are named in the last section.

## What was done well

- **The refusal is proven by constructing the cycle, not asserted.** Three real products written
  through the real store close a loop, and the test fails if the refusal does not fire; every
  such test has a control that a product built from raw inputs is released.
- **The guard against a second store reads the other modules' source** and fails on the constructs
  that made the first duplication, rather than asking a future reader to remember.
- **Every equality proof is exact**: field count and difference count, NaN equal to NaN, column
  types and index compared, no tolerance anywhere. Timing claims are reported in alternating
  rounds beside their equality proof.
- **The commit messages carry the numbers and the counts they claim**, and every count the
  reviewers could check by counting test functions was correct.
- **Failures degrade to a recompute, never to a failed clinician's page**, consistently across the
  store and the ledger.

## Findings fixed in this session, with the test that pins each

| Severity | Finding | Fix | Test |
|---|---|---|---|
| High (architecture) | `store()` accepted a derived kind with no writer and no provenance; the sidecar then looked like a raw input to anything citing it. | `store()` refuses a non-raw kind with no writer and counts a non-raw write with no chain. | `test_store.py::test_a_derived_kind_with_no_writer_is_refused_and_a_raw_kind_is_not` |
| High (test coverage) | The two import spellings of the store (`modules.CacheStore` and `CacheStore`) became two module objects in one process once both roots were on the path; a sandbox applied under one left the adapter's copy untouched, and a test passed or failed with the order of the suites on the command line. | The package registers itself and its three modules under the other spelling on first import, so both names hand back one object; the settings-store test binds to the adapter's own module. | `test_one_store.py::test_both_import_spellings_are_one_module_object`; the host suite now passes in both orders |
| High (orchestrator) | The live ledger held 227 rows of which 218 were written by the test suites (214 for `test-participant` from the container's tile tests, 4 for `u`); the ledger carries no directory, so nothing could tell them apart. | The ledger records production-root writes only; the 218 rows were deleted. | `test_store.py::test_the_ledger_records_production_writes_and_not_writes_under_an_override` |
| Medium (test coverage) | `ledger.py` had no test file; a docstring claimed one existed. | A connection hook the tests point at an in-memory SQLite database; the create, insert, history and count statements run for real. | `test_ledger.py`, four tests |
| Medium (test coverage) | `provenance.check()` had no caller and no test. | Deleted; the store calls `refusal_for` directly. | — |
| Medium (test coverage) | The refusal propagating out of `build_design_matrix`, and the real unreadable-file path in the settings parser, were untested. | Two tests: a tampered sidecar makes the refusal fire and propagate; a loader that raises on one of two files yields one row and an unreadable count of one, and the stream is not stored. | `test_settings_store.py`, last two tests |
| Medium (architecture) | The attribute name that carries a store key was typed twice, in two modules; a drift would silently stop the matched table being cited. | Defined once in `store.py` and imported by both modules. | covered by the existing settings-store and snapshot tests |
| Medium (architecture) | The registered kind `settings_stream` (Stim Optimizer's future chosen ladder) collided in name with the function that reads the device's programmed history, a raw thing. | Kind renamed `exploration_ladder`. | `test_provenance_cycle.py` |
| Medium (architecture) | The closed-loop module's `inputs` and `response` entries were written with no provenance and read with no consumer. | `inputs` now cites the settings stream, the matched table with its chain, and the tile entry; both reads pass `consumer="closed_loop"`. `response` still has no chain (no participant in scope; the path is reached by no endpoint). | existing `test_adapter_caching.py` |
| Medium (performance) | `load()` read the whole payload before comparing the sidecar's signature, so a caller that only wanted to know whether to write paid for a read. | The sidecar is compared first; a mismatch is a miss without opening the payload. A payload whose file type disagrees with its sidecar is treated as unreadable. | `test_store.py::test_a_mismatched_sidecar_is_a_miss_without_the_payload_being_opened` |
| Medium (performance) | The sweep endpoint enumerated and hashed the recording rows twice per request, once for the tile cache and once for its own key. | The tile signature is built once and handed to the tile cache lookup. | live proof, below |
| Medium (quality) | `store_keys` named three addresses whether or not the writes landed. | `store_written` says which of the three actually landed. | `test_band_sweep_store.py` |
| Medium (quality) | The best-row match on length used exact float equality while the centre match rounded. | Both round to six places. | `test_band_results_tables.py` |
| Medium (scope) | Track A step 1's checkbox read as complete although the plan's deletion sub-task was deferred. | The checkbox now names the deferral and where it lives (Track C step 1, open item 7). | — |
| Medium (scope) | `BAND_SWEEP_TIMING_FIELDS` was declared but the test that compares a served response to a fresh one did not use it. | The test skips exactly those fields. | `test_band_sweep_store.py` |
| Low (quality) | Unexpected read and write failures in the store were logged at the same level as routine misses. | Warning level. | — |

## Findings left open, with the reason

1. **Serving the sweep response from the store goes beyond step 6's written text.** The approved
   plan asks for two tables; the branch also stores the response and serves it when the key
   matches. The reasoning is decision 26 (the key decides) and decision 10 in the task plan; the
   scope reviewer is right that this is a runtime change to a live page beyond the step's wording.
   It is kept, and it is named here for the principal investigator's sign-off.
2. **A code-level provenance chain cannot see through a clinician programming what Stim Optimizer
   recommended.** The matched table is raw-derived because the code that builds it embodies no
   choice, but the device history it joins is what a clinician chose to program, and a human sits
   in that loop. This is a limit of the method, not a defect to fix; recorded as open item 16.
3. **The ledger's insert is one blocking statement per write**; a request that writes three
   products pays three round trips. Not measured; a batched insert is a small change for a later
   step when more kinds are written per request.
4. **The security findings, set aside on instruction.** (a) A request-supplied participant id
   reaches a cache file name unsanitised when the participant lookup returns nothing, so a value
   containing a path separator would write under a path outside the kind directory. This is an
   input-validation matter rather than a de-identification one; a one-line check in the store's
   path builder would close it. (b) Stored pickles are trusted because only the server writes under
   the cache root. (c) The REDCap record identifier and field map are in the snapshot's sidecar;
   both are de-identified. (d) File permissions follow the process umask.

## Root cause, for the two findings that were systemic

**Issue.** Test writes reached the production ledger and the production cache root.
**Why 1.** The store records a ledger row and writes a file for any root it is given.
**Why 2.** The test sandboxes turned the ledger off and pointed the store elsewhere by convention,
one context manager per test file.
**Why 3.** The ledger has no notion of where a write went; the sidecar does, the ledger row does
not.
**Why 4.** The ledger was built as a mirror of the sidecar, and the sidecar is always beside its
payload, so location seemed implied.
**Why 5.** Nothing in the store distinguishes "the server's cache" from "a directory a caller
named", because the override was added for tests after the store's rules were written.
**Systemic fix.** The store itself now gates the ledger on the production root, so a test that
forgets the toggle cannot pollute it; the same rule would gate any future audit sink.

**Issue.** Two store module objects in one process.
**Why 1.** Two import spellings, each correct on one runner.
**Why 2.** The store's own tests put the BRAVO root on the path so they can use the container's
spelling on the host.
**Why 3.** Python keys modules by name, so the same file under two names is two modules.
**Why 4.** Nothing asserted the one-store rule at the object level; the guard test read source
text for private stores, not identity of the shared one.
**Systemic fix.** The package aliases itself under the other name, and a test asserts identity
whenever both names are importable.
