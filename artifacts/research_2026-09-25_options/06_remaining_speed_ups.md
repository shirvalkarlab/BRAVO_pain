# Option 6: where the Closed-Loop and Stim Optimizer requests still spend their time, and how to cut it without moving a number

> Research report
> Researcher: option-6 investigation agent | Date: 2026-09-25
> Scope: measurement and proposals only. No repository file was changed except this report. The four
> probe scripts live in the gitignored scratch area (`BRAVO/_agent_bridge/_opt6_*.py`) and wrote
> nothing to the saved answers on disk that the pages read.

## Summary

Two request types were measured on the live participant (RCS08) after decisions 266-269:

- **The Closed-Loop page's report** for the left candidate (L 1-3+ at 24.5 Hz). A *first request after new
  data* has nothing saved on disk yet and builds everything; it took **113.8 s**. A *repeat request*
  reads the saved answers and took **14.6 s**.
- **The Stim Optimizer page's second request** (the two-stage plan) took **33.3 s** and **32.8 s**. This
  request is rebuilt whenever a new pain report or recording changes what it rests on.

The largest remaining costs, in plain terms:

1. **Reading and unpacking the 581 stored Percept session files to build the dated settings history:
   36.0 s** of a first request. It is spent decrypting (about 11.5 s) and reading JSON text (about 17.6 s).
   Every file is read again whenever one new file arrives.
2. **Cutting the recordings into 3-second pieces and computing their band power: 19.8 s** (first request
   only). Decision 266 already sped this up. Its remaining cost is the one fast-Fourier-transform call
   per piece that exactness requires.
3. **Building the heat-map grid on top of those pieces: about 13.8 s.** Of that, **7.4 s** is one numpy
   median function running row by row on 923,076 rows and raising 1.28 million warnings. This cost
   comes back after **every new pain report** and in the two background jobs that rebuild the grids.
4. **The CL-DBS simulation's controller loop: 8.4 s**, the same kind of per-step numpy loop that
   decision 269 compiled for the design rule.
5. **Working out the identity of the recording set 10 to 14 times per request: 5.4 s of the 14.6 s
   repeat request** and 7.2 s of a first request. On live data a three-column database query gives the
   identical answer in 0.017 s where the current query takes 0.41-0.64 s.
6. **The joined band-power table: about 8.5 s** on a first request, and again in each server worker
   process the first time it serves the page after a new recording arrives. Most of that cost is one
   Python function called 10,996,416 times to label each row's current as off, low or high.
7. **Stim Optimizer: the pre-registered calibration check on the pain maps takes 15.3 s of the 33 s.**
   It refits a Gaussian-process model once for every epoch held out. Most of each fit's time goes to the
   model library looking up its own settings, not to arithmetic.

A correctness question found while reading, not a speed-up: the Closed-Loop page's E2 and E3 may
read pain ratings frozen at the time of the last new recording. See "Found on the way", below.

Measured and ruled out: capping the linear-algebra library to one thread for the whole Closed-Loop
request. Across 52,727 response fields, 0 differed, but there was no speed gain (14.55 and 14.54 s
unchanged, against 14.44 and 15.41 s capped). Removing the simulation's repeated curve refits is also
not worth doing: they take 0.13 s.

**If proposals 1, 3, 4, 5 and 6 below are built, a repeat Closed-Loop request should drop from about
14.6 s to about 9 s, and a first request from about 114 s to about 85 s. Adding the settings-history
reuse (proposal 2) brings a first request to about 50 s.** These are estimates, not measurements, and
the smallest-risk item has been measured: proposal 1 gives the identical answer 38 times faster.

---

## Measurements

### How the measurements were taken

All runs used the server container, the live participant `2e3c75c00d7f4f37b53a048d195f11da`, and the
page's own request bodies. The background job launchers (stability grid, other scores, session-report
summary) were replaced by stubs in every run (decision 96). Four runs went through the bridge. The
bridge is shared with another session, and run 3 waited about 3 minutes in its queue.

| Run | Command (from the host) | What it did |
|---|---|---|
| 1 | `bridge_client.py --cwd /usr/src/BRAVO/_agent_bridge --timeout 1800 --wait 5 "python3 _opt6_probe.py cl ..."` | Closed-Loop, saved answers pointed at a fresh scratch folder. Request 1 was the first request, request 2 a repeat, request 3 a repeat under the Python profiler. The step timings of requests 1 and 2 were lost to a `tail` in the command, so only the request-3 profile (`_opt6_cl_warm.txt`) was kept. |
| 2 | `... "python3 _opt6_full.py > _opt6_full.stdout 2>&1"` | Closed-Loop, fresh scratch folder. First request and repeat request timed step by step with no profiler (`_opt6_full.log`). Then three checks: E1 (recording-set identity, two ways), E2 (the simulation's curve refits, default threads against one thread), and E3 (the whole repeat request, default threads against one thread, alternating rounds, every field compared). |
| 3 | `... "python3 _opt6_prof.py > _opt6_prof.stdout 2>&1"` | One first request under the Python profiler, fresh scratch folder (`_opt6_prof_cold.txt`, `.pstats`). |
| 4 | `... "python3 _opt6_probe.py so2 > _opt6_so2.stdout 2>&1"` | Stim Optimizer's two-stage request with the saved answers **read** from the production folder, every write blocked, and the saved response bypassed. Requests 1 and 2 were timed, and request 3 was profiled (`_opt6_so2_warm.txt`). |

The timed steps nest inside each other: the heat-map grid contains the 3-second-piece build, the
report pipeline contains the threshold placement, and the placement contains the design-rule fit. Read
each row as the time spent inside that function, not as a slice of a pie. Profiler numbers run higher
than real time (the profiled first request took 127.4 s against 113.8 s unprofiled), and more so for
code that makes many small Python calls. Profiler numbers are used only to say where time goes inside
a step. The seconds quoted for proposals come from the unprofiled runs.

### Closed-Loop, first request after new data (run 2, no profiler): 113.8 s

| s | calls | step (function) |
|---:|---:|---|
| 37.57 | 1 | evidence inputs (`adapter.evidence_inputs_cached`), of which the dated settings history is **36.04** (`StimOptimizer.adapter.settings_stream`) |
| 33.62 | 1 | heat-map grid read-or-build (`band_sweep_grid_for_closed_loop`), of which the 3-second-piece build is **19.77** (`_build_raw_lsb_cache`), band power per pain report and length of signal **7.43** over 6 sensing pairs (`_band_time_sweep_power_by_seconds`), and statistics **1.95** (`band_time_sweep_from_power`) |
| 17.48 | 1 | report pipeline (`pipeline.run`), of which threshold placement from the record is **6.67** (it contains the design-rule fit) and E2 is **1.80** |
| 9.50 | 1 | CL-DBS simulation (`write_simulation`): two runs of the models **8.73**, controller loop **8.44** (`simulate_segments`), curve refits **0.27** |
| 7.19 | 14 | recording-set identity (`adapter.recording_set_signature`) |
| 6.98 | 2 | design rule (`write_design_rule`): two-component fit **3.61** (includes compiling the compiled filter), local-level fit **2.11** (92 filter calls), separation table **0.31** |
| 4.18 | 1 | band stability answer (`_validate_band_core`) |
| 2.68 | 9 | load and decrypt recordings |
| 2.26 | 1 | three-way current-to-power comparison, every run (15 comparisons) |
| 1.96 | 1 | robustness check (`write_robustness`), of which the controller replay is **1.38** |
| 1.50 / 1.02 / 0.46 | 1 each | pooled table, amplitude-effect table, ground-truth verdict written |
| 1.12 | 1 | REDCap pull |

### Closed-Loop, repeat request (run 2, no profiler): 14.6 s

| s | calls | step |
|---:|---:|---|
| 5.39 | 10 | recording-set identity |
| 3.14 | 1 | report pipeline (E2 **1.93**, placement **0.77**) |
| 3.13 | 1 | three-way comparison for the page's 4 runs (of which loading recordings is most of **2.24**) |
| 2.15 | 1 | band stability answer (REDCap pull **1.08** inside the request) |
| 1.31 | 2 | design rule: a lookup of the saved answer, all of it the recording-set identity |
| 0.64 | 1 | "last built" status line: all of it the recording-set identity |
| 0.43 / 0.43 / 0.42 | 1 each | evidence inputs, simulation, robustness: lookups of saved answers |

The repeat request under the profiler (run 1, 16.3 s) shows why the identity is slow. It fetches every
recording row with its JSON metadata and its source-file row joined in: 169,850 model objects and
169,839 JSON decodes, with 3.0 s in the MySQL driver alone. It then reads three short text fields
from each object.

### The three checks in run 2

- **E1, recording-set identity.** Current query 0.642 / 0.411 / 0.639 s. A three-column query
  (`Recording.objects.filter(source__in=...).values_list("uid", "hashed", "type")`) took
  0.017 / 0.017 / 0.018 s. The answer was **identical in all three rounds**:
  `(uid, 587 files, 6,567 recordings, d79142bc915cd84c77c13a8d9c0cce23)`.
- **E2, the simulation's 200 curve refits.** Default threads 0.12 / 0.13 s, one thread 0.13 / 0.13 s.
  200 curves, 3,200 fields, **0 differing**. The refits are too cheap to matter.
- **E3, the whole repeat request with the linear-algebra library capped at one thread** (the
  treatment the Stim Optimizer request already has). Default 14.55 s, capped 14.44 s, default 14.54 s,
  capped 15.41 s. Three comparisons (default against default, default against capped, capped against
  capped): **52,727 fields in common, 0 differing** in each. It is exact, but there is **no gain**, so it
  is not proposed.
- For reference, a first-request response compared with a repeat response has 52,721 fields in common
  and 15 differing. All 15 are bookkeeping (served from disk or not, seconds, "written", row counts of
  tables written only on the first request). Proofs must therefore compare a first request with a first
  request and a repeat with a repeat.

### Inside the first request (run 3, profiler, 127.4 s)

| Where | Profiled s | What it is |
|---|---:|---|
| Settings history (`_build_settings_stream`) | 36.48 | 581 files: decrypt 16.13 (base64 text decoding 7.54, signature check 1.79, AES 3.86, file read 4.56), JSON parsing 17.62, date parsing 1.36 |
| 3-second pieces (`_td_tiles_batched`) | 18.12 | band-power transform 12.52 (own 6.20, 299,593 FFT calls 2.94, median over sub-windows 2.50), per-recording loop 3.17 |
| Band power per report and length (`live_lsb_band_medians_by_length`) | 9.53 | `np.nanmedian` 7.26: 923,076 rows through `apply_along_axis`, 1,284,219 warnings raised and discarded |
| Joined table (`_joined_table_calibrated`) | 10.05 | `_era` called 10,996,416 times (4.91 own) plus the Series iteration around it (1.42), frame construction 2.49, merge 0.85 |
| Simulation (`simulate_segments`) | 11.78 | `simulate_series` 668 stretches 9.31: own 2.66, response curve evaluated 155,800 times 2.31, longest-run helper 271,208 calls 1.76, derivative 0.96, reversal counter 0.83; `np.histogram` 135,604 calls 1.78 |
| Design rule | 6.37 | local-level fit 2.38 (92 numpy filter calls, 26 ms each), two-component fit 3.65 (817 compiled filter calls), compiling the compiled filter 2.62 |
| Recording-set identity | 8.48 | 14 calls |
| Band stability answer | 5.76 | mixed model 3.71, of which about 2.9 is loading R packages the first time in a process |
| Robustness | 1.64 | controller replay over 248 stretches 1.54 |

### Stim Optimizer two-stage request (run 4): 33.3 s and 32.8 s

| s (req 1 / req 2) | calls | step |
|---:|---:|---|
| 23.90 / 24.11 | 1 | two-stage block (`two_stage_block`) |
| 21.39 / 21.58 | 4 | Stage 1 fits (`run_stage1`): the REDCap left leg, the REDCap back site, the clinic-sheet left leg, the clinic-sheet back |
| **15.33 / 15.48** | 10 | **calibration check (`stratum_calibration`), one per fitted rate stratum** |
| 14.63 / 14.70 | 2 | clinic-sheet fits (overlaps the two lines above) |
| 11.98 / 12.02 | 1 | the back site's own fit (overlaps) |
| 4.98 / 4.86 | 2 | evidence cells built and screened (`live_evidence`) |
| 3.99 / 3.86 | 1 | closed-loop readiness screen |
| 2.96 / 2.59 | 1 | evidence inputs (reading the saved 3-second pieces) |
| 2.22 / 2.04 | 2 | load and decrypt recordings |
| 1.10 / 1.02 | 1 | REDCap pull |

Profiled (61.2 s): 296 Gaussian-process fits, 3,120 optimiser runs, and 85,678 likelihood evaluations
take 41.0 s. The 20 leave-one-out prediction runs of the calibration check (`loo_predict`) take 33.5 s
of that. Inside the likelihood, the arithmetic is small (Cholesky and solves under 2 s). The time goes
to scikit-learn's kernel objects describing themselves. `get_params` is called 777,366 times and calls
`inspect.signature` every time (11.4 s). The `hyperparameters` property calls `dir()` 528,156 times
(2.7 s) and `str.startswith` 26 million times (2.1 s).

---

## Ranked costs

"First" is the Closed-Loop first request after new data (a new recording or session file makes almost
everything first). "Per report" means the cost comes back after every new pain report. "Repeat" is a
repeat Closed-Loop request. "SO" is the Stim Optimizer two-stage request.

| Rank | Cost | Measured s | When it is paid | Driver |
|---:|---|---:|---|---|
| 1 | Dated settings history | 36.0 | first; every time any session file is added | decrypt and parse all 581 files |
| 2 | 3-second-piece build | 19.8 | first (new recording) | one FFT call per piece (266's exactness rule) |
| 3 | Stim Optimizer calibration check | 15.3 | SO, every time its inputs change | a model refit per held-out epoch; library bookkeeping |
| 4 | Heat-map grid, excluding the pieces | about 13.8 (7.4 of it the median) | first; **per report**; background jobs for 6 scores | `np.nanmedian` row by row |
| 5 | Joined table | about 8.5 (pipeline 17.5 minus placement 6.7, E2 1.8, rest 0.5) | first; the first request in each worker process after new data | 11 million Python calls to label currents |
| 6 | Simulation controller loop | 8.4 | first (saved afterwards) | per-step numpy loop over about 200 copies of the model |
| 7 | Recording-set identity | 7.2 first, **5.4 repeat** | every request | full-row query, 10-14 times |
| 8 | Design rule | 7.0 (local level 2.1, compile about 1-2.6) | first | numpy filter loop; compile per worker |
| 9 | Stim Optimizer: other Stage 1 fits, evidence screen, inputs | about 12 | SO | model library overhead, statsmodels fits |
| 10 | Band stability answer | 4.2 first, 2.2 repeat | every request | mixed model; R packages loaded once per process |
| 11 | Loading recordings for the three-way comparison | 2.2 | repeat | decrypt and unpickle, in threads |
| 12 | Robustness replay | 1.4 | first | per-step numpy loop over 576 settings |

---

## Proposals

Each proposal below changes how a number is computed, never what the number is. For each one the
report gives the change, why every value stays the same, the expected gain, the risk, and how the
check that every number came out the same would be done. Proof tooling that already exists:
`_probe_step89_capture.py <label> <clL|clR|so|so2|bm>` captures a response with writes blocked. With
`CAPTURE_OLD_TREE=1` it runs a copied old `modules` tree for the "before" capture. **For the products
that are saved to disk (the simulation, design rule, robustness, settings history, 3-second pieces),
that capture reads the saved copy and so proves nothing.** Those proofs need a fresh scratch folder per
run, as `_opt6_full.py` does, with the saved products compared file by file as well as the response.

### Proposal 1: the recording-set identity, asked once per request and with a three-column query

- **Change.** In `ClosedLoopDeployment/adapter.recording_set_signature`, read only `uid`, `hashed` and
  `type` (`values_list`) instead of whole Recording objects joined to their source files. Also keep the
  answer in the same within-request memo that decision 267 added (`Biomarkers.bravo_service._request_memo`,
  which ends with the request).
- **Why exact.** Each row contributes the same three strings. All three are `CharField`s, so `str()` of
  the database value is the same text either way. The same sort, the same join and the same hash
  follow. `len(recs)` and the number of rows returned are the same count. The memo keeps the same scope
  as the tile key and recordings memos of decision 267. **Measured live: identical tuple in 3 of 3 rounds.**
- **Expected gain.** Each call drops from 0.41-0.64 s to 0.017 s, and the repeat count from 10-14 to 1.
  **About 5.3 s of the 14.6 s repeat request (36%), and about 7.1 s of a first request.** The Stim
  Optimizer request does not call it.
- **Risk.** Low. A future caller that relied on the objects being fetched gets nothing different, since
  the function returns only the tuple. The memo must not outlive the request, which the existing scope
  guarantees.
- **Proof.** One host test: the new function equals the old on a fixture database. Live: `clL` and `clR`
  captures before and after (about 59,000 fields each, expect 0 differing apart from timing), plus the E1
  comparison above. Timings: repeat requests in alternating rounds, before / after / before / after.

### Proposal 2: the dated settings history rebuilds only the files that changed

- **Change (preferred).** Keep, beside the saved settings history, the rows each source file
  contributed. Store them as the same Python dicts the builder already makes, pickled and filed under
  each file's uid, content hash and the builder's rule version. When the file set changes, take the
  newest previous entry as a donor. Reuse the rows of every file whose uid and hash match, and decrypt
  and parse only the new or changed files. Then assemble the list in the current file order and finish
  exactly as `_build_settings_stream` does now (build the frame, drop incomplete rows, sort, apply the
  implant-date cut).
- **Why exact.** Each file's rows are a pure function of that file's decrypted content (the content hash
  is in the label) and of the parsing code (the rule version is in the label). The assembled list is
  therefore the same list, in the same order, of equal dicts. The frame, the sort (which is not stable,
  so input order matters, and it is the same) and the cut are the same operations on the same input.
  Pickling round-trips pandas Timestamps with their timezone exactly. A frame is not stored, so there is
  no dtype inference to drift.
- **Alternative (smaller change, smaller gain).** Decrypt and parse the files in 4-6 worker processes and
  collect their rows in file order. This is exact by construction because each file's parse is the same
  code on the same bytes. Threads would not help: base64 decoding and JSON parsing hold Python's global
  lock.
- **Expected gain.** About 35 s of the 36.0 s on the first request after each new session file. The
  estimate is one new file at about 0.06 s plus reading the donor rows (6,797 dicts). The worker-process
  alternative is estimated at 36 s → 7-10 s. Both estimates are unmeasured.
- **Risk.** Medium. It adds a saved-answer kind. That kind is raw, so no provenance chain applies, and
  with one entry per participant the donor is simply the previous entry. A file that fails to decrypt
  must never be saved as "no rows": the stream with unreadable files is not saved today, and that rule
  must hold for the per-file rows too. The worker-process alternative has its own risk: forking inside
  a gunicorn worker that holds database connections, an embedded R session and OpenBLAS threads. The
  project's only fork pool so far (the stability grid) closes the database connections first and runs
  in a separate background process. Peak memory is one parsed session file per child.
- **Proof.** The frame built from scratch against the frame built incrementally after removing one file
  from the donor: `assert_frame_equal(check_exact=True)`, every float compared as hex, `attrs` compared.
  Then `so2` and `clL` captures with the saved settings history bypassed (fresh scratch folder), and
  alternating timings of the build alone.

### Proposal 3: the heat-map grid's medians computed as a whole matrix

- **Change.** In `Biomarkers/routines/availability.live_lsb_band_medians_by_length` (both the voltage-trace
  branch and the device-spectrum branch), replace `np.nanmedian(np.where(keep, v, np.nan), axis=1)`.
  Once per band, gather the first `cap_max` clean pieces of each rating into a small matrix, in the
  order the code already defines. Then for each length take the first `cap` columns, sort each row (NaN
  last), count the finite values `n`, and return the element at `(n-1)//2` when `n` is odd or
  `(lo + hi) / 2` when `n` is even. A row with no finite value returns NaN.
- **Why exact.** A median is an order statistic of the values kept, so the order in which they are
  visited cannot change it. For an even count, numpy computes it as the mean of the two middle values,
  that is `(lo + hi) / 2`. Addition of two numbers is exactly rounded and does not depend on their
  order, and division by 2 is exact. For an odd count it returns the middle value itself. The kept set
  is the same set: the same clean mask and the same rank-up-to-`cap` rule. NaN values at real pieces are
  kept by the rank rule and skipped by `nanmedian`, and the replacement skips them the same way.
- **Expected gain.** Most of the 7.4 s for 6 sensing pairs (estimated 7.4 → about 1.0-1.5 s), plus the
  1.28 million discarded warnings. This cost is paid on every grid build: first requests, the first
  page load after **every new pain report**, the background job that precomputes the other five pain
  scores (decision 107), and the stability grid's own rebuilds.
- **Risk.** Low to medium. The edge cases that must be pinned by tests: rows with no finite value,
  infinite values (numpy's `(inf + -inf)/2` is NaN, and so is the replacement's), `cap` larger than the
  pieces available, and the device-spectrum branch's `enough` rule.
- **Proof.** Function level first: every sensing pair × all 9 lengths × 22 bands, under each setting
  the page and the background jobs use (the three match directions, window reuse on and off, the
  daily-default 60-minute window, and the Biomarkers page's own settings). Compare as hex, expecting
  0 differing. Then `bm` captures with the saved grid bypassed (about 34,000 fields, 0 differing apart
  from timing and the grid's label), and alternating timings of a grid build.

### Proposal 4: the CL-DBS simulation's controller loop compiled, the decision-269 pattern

- **Change.** Move the per-step loop of `simulation.simulate_series` into a numba-compiled function that
  loops over time steps and, inside each step, over the model copies. That covers the response-curve
  lookups (`_bank_g`, `_bank_dg`), the threshold test, the onset and blanking counters, and the ramp.
  Return the same `amp_out`, `p_out` and `state_out` arrays and the same integer counters. Do the
  per-copy integer summaries in the same compiled pass: the longest run at each limit
  (`replay._longest_run_at_level_s`), the undone switches (`_count_reversals`), and the amplitude
  histogram counts that `simulate_segments` builds with 135,604 calls to `np.histogram`. Keep every
  floating-point mean (`np.mean(amp_out, axis=1)` and the fractions) in numpy, on arrays that are
  identical. Keep the numpy loop as the reference and as the fallback where numba is absent (CI now has
  numba, decision 271).
- **Why exact.** Each step is element-wise add, subtract, multiply, compare and min/max, done per copy in
  the same order. These are exactly rounded whichever code runs them. The one exponential
  (`alpha = 1 - exp(-dt/tau)`) stays in numpy outside the loop. The summaries moved into the loop are
  integer counts, and the longest run in seconds is `max_run * dt` as now. The floating-point sums stay
  in numpy. Decision 269 found no fused multiply-add on this container's numba (no `fastmath`), and the
  proof must re-check that. Signed zeros cannot arise at the clip bounds, because both amplitude limits
  are positive currents.
- **Expected gain.** About 7-8 s of the 8.4 s on a first request (estimated). The simulation is then
  saved, so repeat requests do not pay it. Unlike decision 269's kernel, this one has no recursive
  helper, so numba's on-disk cache may be usable and would remove the per-process compile. That needs
  testing under the server's libraries, given 269's segfault.
- **Risk.** Medium: the most code of any proposal here. The histogram must reproduce numpy's rule for
  array bin edges exactly (the last bin includes its right edge, and values are clipped to the limits
  first), and the missing-reading branch must hold the pending state as now.
- **Proof.** A host test like decision 269's: the compiled and numpy loops equal over constructed series
  with gaps, a missing first reading, and none, linear and quadratic curves, compared as hex and integer.
  Live: the saved simulation payload built fresh before and after (fresh scratch folder, the page's
  `ClosedLoopSimulation` read), for the left and right candidates and both timing runs, as a field count
  with 0 differing. The Closed-Loop response itself carries only a summary of the simulation.

### Proposal 5: the joined table labels currents as a whole column

- **Change.** In `ClosedLoopDeployment/adapter._joined_table_calibrated`, replace
  `T[f"era_{h}"] = [_era(x) for x in pd.to_numeric(T[c], errors="coerce")]` with three masks on the numeric
  column, written into an object array that is `None` where the current is missing.
- **Why exact.** The same three comparisons against the same two constants (`ERA_OFF_MAX_MA`,
  `ERA_LOW_MAX_MA`) decide each label. The column holds the same strings and the same `None`, with
  object dtype in both cases. A test must pin that the column is object dtype and that missing values
  are `None`, not NaN.
- **Expected gain.** Profiled at 6.3 s of the table's 10.1 s; estimated at 3-5 s in real time (the
  profiler inflates exactly this kind of code). The table is held in each worker's memory, not saved to
  disk. So besides the first request, this is also paid by the first Closed-Loop request in **each**
  gunicorn worker after a new recording, and after every `kill -HUP` reload.
- **Risk.** Low.
- **Proof.** `joined_table` output before and after on live inputs, every column and dtype, values as
  hex or string. Then `clL` and `clR` captures.

### Proposal 6: the design rule's local-level filter compiled too, and its compile saved to disk

- **Change.** Give `design_rule.filter_1state` a compiled twin, built the same way as decision 269's
  `_filter_2comp_kernel` and reusing its `_pairwise_sum` for the per-step log-likelihood sum. Separately,
  rewrite `_pairwise_sum` without recursion (an explicit loop over the same halving split) so that
  `cache=True` can be tried again.
- **Why exact.** This is decision 269's argument: the same element-wise operations in the same order,
  the same library logarithm, and the per-step sum in numpy's own pairwise order. A non-recursive
  pairwise sum that splits at the same points adds the same numbers in the same grouping.
- **Expected gain.** The local-level fit, 2.1 s → about 0.05 s. If the on-disk cache works, a further
  1-2.6 s saved on the first design-rule fit in each worker (2.6 s profiled). First requests only.
- **Risk.** Low for the filter, which follows 269's pattern. For the cache, **it is not known whether the
  segfault came from the recursion.** It must be tested under the server's libraries before relying on
  it, and left off if it crashes.
- **Proof.** As in 269: filters equal over parameter draws on panels with gaps and a missing first
  reading; the whole fit equal; the saved design-rule payload built fresh before and after.

### Proposal 7 (smaller): the robustness replay compiled

`robustness.run_stretch` is the same per-step pattern over 576 settings. Its running sums add one step
at a time per setting, and a compiled loop over steps and then settings adds in the same order.
Measured at 1.38 s on first requests, so the gain is at most 1.3 s. The proof is the saved robustness
payload built fresh before and after, together with the existing check that the fast bootstrap equals
`run_many`.

### Proposal 8 (larger, riskier): the 3-second-piece build over worker processes

Each recording's pieces are computed independently (`availability._td_tiles_batched` appends one
recording at a time), and decision 266 keeps one FFT call per piece. Splitting a channel's recordings
into contiguous chunks, running the chunks in worker processes, and appending the results in list order
is therefore the same arithmetic on the same library. The estimated gain is 19.8 s → 5-7 s with 4-6
processes. Parallelising over the 6 channels alone would help less, because the channels are uneven:
R 0-3+ holds most of the recordings. The risks are the fork concerns of proposal 2, a copy of the
recordings in each child, and the Redis build lock's meaning when the build is split. The proof is
decision 266's: 32,310,237 fields, 0 differing.

### Proposal 9 (Stim Optimizer): the Gaussian-process fits without the library's self-description cost

- **Change.** Make the scikit-learn kernels look up their own constructor signature and their list of
  `hyperparameter_*` attribute names once per class, not on every evaluation. There are two ways. One
  is to patch `sklearn.gaussian_process.kernels.signature` with a cached `inspect.signature`, together
  with a per-class cached name list behind `Kernel.hyperparameters`. The other is to use project
  subclasses of RBF, ConstantKernel and WhiteKernel inside `surrogate._make_kernel` that override those
  two lookups and keep the parent's class name, so the kernel text printed in the response
  (`hyperparameters["kernel"]`) does not change.
- **Why exact.** Only metadata about the kernel's own attributes is cached: a constructor signature and
  a list of attribute names. Neither changes during a fit. Every hyperparameter value is still read from
  the object each time. The optimiser, the random starts (`random_state=0`), and the likelihood arithmetic
  are untouched.
- **Expected gain.** Unmeasured. In the profile, the self-description work is roughly 20 s of 41 s of
  fitting time. The profiler exaggerates exactly this kind of code, so the real share is probably
  smaller. **A plausible range is 5-9 s of the 33 s request, to be measured before any claim.**
- **Risk.** Medium: it reaches into a third-party library (pinned at 1.5.2 in the container), and a
  version upgrade must re-run the proof. The subclass route is safer than patching the library module.
- **Proof.** A unit test that fits the same data with and without the change and compares theta, the
  log marginal likelihood and the predictions as hex. Then `so2` captures before and after (the
  response's label changes with the code, decision 41, so expect timing and that label, and 0 other
  differing fields), and alternating timings.

### Proposal 10 (Stim Optimizer): the calibration check's refits run in parallel

Each held-out epoch's refit in `ObjectiveGP.loo_predict` is independent and deterministic: a fresh
clone with `random_state=0`. So the refits can run in worker processes and be written back into their
own positions. The arithmetic is unchanged by construction. The estimated gain is 15.3 s → about 3-4 s.
The risks are the fork concerns of proposal 2 inside a gunicorn worker. The proof is the `so2` capture
as in proposal 9. The calibration check is carried on the response and drawn on no page (decisions 238
and 253). Whether it should stay on the request path at all is the PI's decision, not a speed-up.

### Smaller items noticed, not costed

- The two-stage request screens the evidence cells twice: all rates for the readiness card, then the
  frozen rate for the gate (`pipeline._select_after_freezing`). The second pass re-assesses cells the
  first already assessed. A within-request memo of `lfp_response.assess_response` per cell would be exact
  if the evidence cell is built identically both times. That has not been verified: the two calls pass
  different arguments (`stream`). Worth about 1 s at most.
- Loading R packages the first time in a process (about 2.9 s profiled) and numba compiling in a process
  can be moved to worker start-up. That moves the cost; it does not remove it.

### Where the decision-269 compiled-loop pattern applies

| Code | Applies? | Why |
|---|---|---|
| `design_rule.filter_1state` (the local-level fit) | **Yes** (proposal 6) | same shape as the compiled two-component filter |
| `simulation.simulate_series` plus its per-copy summaries | **Yes** (proposal 4) | element-wise per-step loop, integer summaries |
| `robustness.run_stretch` | **Yes, small** (proposal 7) | same pattern |
| `replay.dual_threshold`, occupancy, start-up bias | Not worth it | 0.02-0.06 s each |
| The FFT per 3-second piece | **No** | numba has no path to numpy's FFT, and decision 266 showed that batching rounds differently |
| The grid's medians | Not needed | whole-matrix numpy is exact and enough (proposal 3) |
| Gaussian-process fits | **No** | the cost is inside scikit-learn's Python objects (proposal 9 addresses it) |
| Settings history | **No** | the cost is decryption and JSON parsing |

---

## Not exactly speed-up-able

- **Batching the FFT across 3-second pieces.** The container's FFT library processes rows in pairs and
  rounds a leftover row differently (decision 266).
- **Batching the E2 bootstrap's least-squares fits into one computation.** It changes the arithmetic
  (decision 268).
- **A shared covariance recursion for the design rule.** Stretches have gaps, and 0 of 60 draws were
  identical (the plan's record for decision 269).
- **The analytic leave-one-out shortcut for the Gaussian process.** It moves the numbers, and
  `surrogate.loo_predict`'s own docstring rejects it because it leaks the held-out point into the fit.
  The same applies to fewer random restarts, warm starts, or looser optimiser tolerances anywhere
  (Gaussian process, Nelder-Mead).
- **The REDCap pull (1.0-1.1 s per request).** This is network time. A cache that outlives the request
  was rejected on staleness grounds (`pro_request_scope`'s docstring), and nothing here changes that.
- **The first request in a new worker process.** It pays for per-worker memos: the joined table, R
  packages, numba compiles. Proposals 5 and 6 make it cheaper. Only warming at start-up could move it,
  and that is not a speed-up of the computation.
- **The one-thread cap for the whole Closed-Loop request.** It is exact (0 of 52,727 differing), but
  measured as **no faster**, so it is not proposed.
- **Removing the simulation's duplicated curve refits.** It would be exact, but it is worth 0.13 s.

---

## Found on the way (a correctness question, not a speed-up)

While checking what proposal 5's table is keyed on, I found that the Closed-Loop page's E2
(band power to pain) and E3 (current to pain) may read **pain ratings that are out of date**. This is
the failure CLAUDE.md §8 rule 5 names: a rating saved inside a product that is filed only under the
recordings. What is established is established by reading the code; nothing was run to measure it
today.

- The saved evidence inputs (`adapter.evidence_inputs_cached`) hold three things: the band-power frame,
  the epochs, **and the epoch design matrix, whose `nrs`/`vas` columns are pain ratings**
  (`StimOptimizer.adapter.build_design_matrix` → `attach_pros`). They are filed under
  `inputs_signature`: the recording set, the rule version and the two calibration constants. No
  pain-report term enters that label, either in each worker's memory or on disk.
- The pipeline turns that design matrix into the pain frame merged into the joined table
  (`pipeline.run`), and E2 reads `nrs` from the joined table (`edges.state_edge`, `outcome="nrs"`). E3
  reads the design matrix directly (`edges.therapy_edge`). In addition, the joined table's in-memory
  memo (`joined_table_cached`) is filed under the frame, the epochs, the centres and the width only.
  The pain frame passed alongside is not part of that label, so a worker that already holds the
  table keeps its old ratings even if the design matrix is fresh.
- Decision 215's own full row saw this once: when that entry was rebuilt on 2026-09-20, "the design
  matrix 20 cells differing, all pain-report columns (the ten reports filed 2026-09-20)". The label was
  not changed to include the reports.
- How stale the ratings get depends on how often a new recording arrives, because any new recording
  changes the label. Proposals 1-10 do not touch this. It is worth one measurement before deciding
  anything: compare today's saved design matrix with a fresh `build_design_matrix` on RCS08, and check
  whether the E2 and E3 numbers on the page move.

---

## Recommendation

Order, by gain per unit of risk, each as its own commit with tests written first and its own check
that every number came out the same:

1. **Proposal 1 (recording-set identity).** The smallest change. Equality is already shown on live data,
   and it removes about 5.3 s from every repeat Closed-Loop request.
2. **Proposal 3 (grid medians).** It pays off after every pain report and in both background jobs, not
   only on first requests.
3. **Proposal 5 (joined-table labels).** A few lines. It also helps the first request in every worker.
4. **Proposal 4 (simulation loop compiled).** The largest remaining compiled-loop win, and decision
   269's pattern is proven here.
5. **Proposal 2 (settings history by file).** The largest single cost. It needs the PI's go-ahead on a
   new saved-answer kind (preferred) or on worker processes inside a request (alternative).
6. Proposals 6 and 7. Then, for the Stim Optimizer, **measure proposal 9 first**; if it is small,
   proposal 10.

Estimated effect (unmeasured except proposal 1's per-call time):

| | Now | After proposals 1, 3, 4, 5, 6 | Also proposal 2 | Also proposal 8 |
|---|---:|---:|---:|---:|
| Closed-Loop repeat request | 14.6 s | about 9 s | about 9 s | about 9 s |
| Closed-Loop first request | 113.8 s | about 85 s | about 50 s | about 37 s |
| Grid rebuild after a new report | about 14 s | about 8 s | | |
| Stim Optimizer two-stage | 33 s | unchanged | unchanged | proposals 9 and 10: to be measured |

Every "about" in that table has to be replaced by alternating-round timings beside a field count and a
difference count on the live participant before it is quoted anywhere else (house rules §4, CLAUDE.md
§8 rules 3-4).
