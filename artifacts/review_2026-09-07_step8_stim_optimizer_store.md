# Review of Track A step 8 before its commit — "Have Stim Optimizer read the store and write its outputs back"

**Date:** 2026-09-07, second session. **Branch:** `PS_closedloop_deployment`, working tree before
the step 8 commit. **Method:** five independent readers of the diff, each with one perspective
(provenance and the dependency cycle; key completeness and the pain-rating rule; the tests and the
two runners; scope and plain correctness; what the code says about itself), then two refuters
per finding on the six most severe. Security was out of scope on the principal investigator's
instruction (the data are de-identified). Seventeen agents, 33 distinct findings, 6 verified,
0 refuted, 27 lower-severity findings not put to refuters.

**Verdict after the fixes below: approved for commit.** Every confirmed finding and every
unverified finding that was a defect is fixed and pinned by a test; the three that are not defects
are recorded as accepted at the end.

## What the reviewers confirmed

1. **After the store refused a stored response, the recompute never replaced it** (rated high by
   one reader, medium by three). The write-back used the "write only if absent" path, which found
   the refused entry under the same key and wrote nothing; the response then reported the entry as
   written; every later request with the same inputs was refused and recomputed again. Reproduced
   by two refuters on the host with the test file's own stubs.
2. **The response's chain was copied from whichever matched-table sidecar was newest**, not from
   the entry the response key names (two readers, confirmed by four refuters, one lowering it to
   low because the refusal itself was unaffected). The store keeps one entry per kind and
   participant and sweeps the rest, so "newest" and "the one named" agree only until the next
   write.
3. **The response key named none of the numbers the fit depends on**, only a version string bumped
   by hand (confirmed by two refuters). An edit to a bound in the pipeline or a routine would have
   left an older response being served.

## What was changed in answer to the review

| Finding | Change | Pinned by |
|---|---|---|
| refused entry never replaced | after a refusal, all five products are written through the store's plain write, which replaces the entry; the response reports `replaced_refused_entry` | `test_a_stored_response_derived_from_the_ladder_is_refused_reported_and_recomputed` now makes a third request and requires it to be served, not refused |
| chain from the newest sidecar | `store.stamp_for_key` finds the sidecar of exactly the entry a key names; the response cites the matched table's own chain and the amplitude table's chain as read | `test_stamp_for_key_finds_the_entry_named_and_not_the_newest` |
| key names no constants | a digest of the Stim Optimizer module and its routines is in the key, so any edit to the arithmetic invalidates every stored response (decision 26 accepted this for the tiles) | the served test still passes; the digest is a constant within one deployment |
| the figure backend in the four tables' keys, so two request shapes swept each other's tables | the tables are keyed without the backend; only the response is | `test_the_four_tables_are_keyed_without_the_figure_backend` |
| a response computed without the settings census stored under the same key as a healthy one | such a response is computed and not stored, with the reason in the response | `test_a_response_computed_without_the_settings_census_is_not_stored` |
| the real tile-key helper ran in no test, used one import spelling, and swallowed every failure | it tries both spellings and returns `(key, reason)`; a missing key's reason reaches the response | `test_the_real_tiles_key_helper_tries_both_spellings_and_reports_why`, `test_a_missing_tile_key_is_reported_with_its_reason` |
| a served response said its own kind was not written; the stored copy could not know | the response's flag is set before the write and corrected in memory on failure; the served copy's store block is rebuilt for the current request, so a refusal or write error recorded by an earlier request never comes back with it | the served test and the refused test |
| a column mismatch in the amplitude table raised out of the whole request | the summary runs inside the block and reports `summary_error`; the request completes | `test_a_table_the_summary_cannot_read_does_not_take_the_request_down` |
| an unreadable amplitude entry was reported as "no table has been written" and left in place | `load_newest` discards it and returns its stamp, so the block says an entry existed and could not be read | `test_an_amplitude_entry_whose_payload_cannot_be_read_is_said_so_and_discarded`, `test_load_newest_reports_an_unreadable_entry_and_discards_it` |
| a band with no fitted line was listed as "without detectable movement"; the list omitted the range of currents | three states (detected; fitted and not detected; not assessed), and every flagged row carries the number and range of currents and the smallest standard error of the slope | `test_a_band_with_no_fitted_line_is_not_assessed_rather_than_without_movement` |
| rows the grouping dropped were counted but not reported | `n_rows_in_window` and `n_rows_not_grouped` | same test |
| `RESPONSE_TIMING_FIELDS` named a field that does not exist | removed | — |
| `load_newest`'s docstring claimed a check it did not make | rewritten to say what it does | — |
| a comment used "arm" bare | defined once where it first appears | — |
| the container runner's comment carried stale file counts | corrected, dated | — |

## Accepted as they are, with the reason

- **The closed-loop readiness block sits inside a response whose key carries the pain-report
  snapshot.** The block is a copy for display; the closed-loop page's own product is the one
  keyed on recordings alone. Rebuilding the copy when reports change costs time, not correctness.
- **The Stim Optimizer consumer edge is proven on the host only.** The container runner does not
  discover `StimOptimizer/tests`, which use pytest, and that is documented in `run_tests.py`,
  `CLAUDE.md` and the handoff. The store-side refusal it depends on is proven in the container by
  `CacheStore/tests`.
- **A code-level chain cannot see through a clinician programming what Stim Optimizer
  recommended.** Open item 16, unchanged.

## What the reviewers found right

Every read of a derived kind is made as `stim_optimizer`; every write passes a writer and a
flattened chain; the matched table's own chain is flattened into the response; no pain rating,
report set or REDCap value enters any key or payload except through the matched table's key,
which is the intended route; a request that hands in its own reports is neither served from nor
written to the store; the key varies with nothing per request; the matched-table key survives
both pandas versions; every test name asserts something the test proves; the duplicate-`rank`
failure the live record exposed was fixed with a queue shaped like the pipeline's.
