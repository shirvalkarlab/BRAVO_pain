# Decisions, and the single list of what is still open

**This document replaces §3 and §4 of the mega handoff and the scattered open-item lists in the
session handoffs and the design ledger.** It is the only place either list lives now.

Commit references are pointers into history, not the current head. **A decision marked superseded
keeps its row, because in each of those cases the mistake is the lesson** — but only the
superseding decision describes the code as it stands.

---

## Part 1 — The decision log

### Signal processing and the conversion to device units

| # | Decision | Why | Ref |
|---|---|---|---|
| 13 | **The 60 Hz mains notch is off by default.** | The device is implanted and battery-powered, so there is no mains coupling, and notching removes real signal. The option is retained. | `f915257` |
| 14 | **Only the two 256-point modes may be converted** — Dual and Single Inverse. | A 64-point spectrum integrates a different set of frequency bins, so it is a different quantity and the same gain cannot convert it. | `f915257` |
| 15 | **Converting a spectrum back to a time series and forward again adds nothing.** The direct route from spectrum to device units is the rigorous one. | A phase-randomised reconstruction matches the direct band integral within 0.8 percent, median ratio 1.008, r = 0.999, on all 113 paired blocks. A band integral is phase-independent. | `f915257` |
| 18 | **The primary conversion from the voltage trace is the transform route at 352.62.** | It reaches r = 0.9927 and a root-mean-square error of 60.6 device units. The Welch route produces a spectrum from the voltage trace and cannot consume the device's own spectrum, so it was never a valid substitute when no voltage trace exists. | CS-1 |
| 4 | **Windows of the voltage trace with more than 10 percent missing samples are dropped entirely** rather than analysed. | The zero-fill from the concatenation repair entered the spectrum as real zeros and deflated band power. | `adcaf15`, `c438ce1` |
| 3 | **The concatenation repair is left in place**; matching is unchanged. | Re-decoded both ways: 67 matched against 67, zero changes. | no change |
| 2 | **The pain-report timestamp is California local wall-clock time and must be converted.** | Device start times are already universal, so parsing the report as universal smears every match by seven to eight hours. | `a4e4e68` |

### The frozen per-participant conversion model

| # | Decision | Why | Ref |
|---|---|---|---|
| 11 | **Freeze the per-participant model as a stored asset**, with a tiered fallback from band to channel-and-frequency to channel-pooled to none, and mark a modelled switching value as indeterminate. | The device reports its own units while the offline route reports microvolts squared, and a band the device never sensed needs an estimated switching value that is clearly flagged as estimated. | `771f3c2` |
| 16 | **The 8.8 Hz band on the right 0-3 contact is restricted to on or after 2026-03-01**, not the configuration-change date of 2025-12-05. | The configuration-change date sits inside a declining settling transient, −0.078 per month in the logarithm, p = 0.039, with stationarity only from about 2026-02-15. Using the earlier date would inject the higher-gain transient and bias the deployable switching value. The frozen fit is unchanged. | `e9d7a80` |
| 17 | **An impedance term of 1.02 is rejected.** | Significant only under a naive fit, because 2,985 measurements share 230 impedance readings. With a grouping-aware standard error it is not significant, p = 0.26. It is a slow-time proxy rather than a physical gain, and its effect on the switching value, 1.22-fold, is smaller than the model's own spread. | `a9c3a01` |

### How results are reported, and the gates

| # | Decision | Why | Ref |
|---|---|---|---|
| 7 | **The interval on a discrimination value is not folded** — the bootstrap keeps the signed value. | Folding hid null bands, and an honest lower bound must be allowed to fall below 0.5. | `c50be37` |
| 8 | **A per-epoch discrimination value is signed, and the orientation is fixed once on the pooled result** rather than per epoch. | A folded per-epoch value masks a sign reversal inside an epoch, which is a closed-loop failure mode. | PR #5 |
| 9 | **Deployment gates have three states, and the stability gate abstains when its test cannot run.** | **A gate that goes green on absence of evidence is unsafe for a claim that something is ready to program.** | PR #5 |
| 12 | **Validation is forward-chaining and out of sample**, with the switching value fitted on the training part only and the held-out value not re-folded. | The in-sample value masked forward reversals: 26.4 Hz went from 0.55 to 0.24, and 8.8 Hz from 0.52 to 0.37. | `d9d58a4` |
| 19 | **Intervals account for autocorrelated ratings** through a moving-block bootstrap and an effective sample size, with the de-folded lower bound as the gate. | Honest intervals under autocorrelated ratings, and it stops the beats-chance requirement from being re-manufactured by a bias-corrected interval. | `8509e96`, `2ef0408`, `abe8a23` |
| 6 | **The net-benefit cut-point rule was removed.** | Its objective equals the prevalence multiplied by the cost, so it always picks the identical point as the cost rule — two controls that cannot disagree. | PR #3 |
| 10 | **The recommendation is single-sourced**, with an explicit difference between what is recommended and what is currently programmed, and conservative abstention on ramp guidance. | An actionable recommendation while keeping the fail-closed discipline. | `b0597f8` |

### The deployment fallback, and the units error behind its change

| # | Decision | Why | Ref |
|---|---|---|---|
| ~~20~~ | ~~**The deployment fallback converts the cut-point through the frozen model**, and fails closed when no fitted entry exists.~~ **SUPERSEDED BY 21.** | The reasoning was that the cut-point's own model should convert it. **The lesson kept from this row is the units error that followed.** | `184ea74`, `fa2c416` |
| 21 | **The deployment fallback models the device's power line off the raw voltage trace at the cut-point's own centre frequency, and anchors by rank.** The switching value is never converted. | **Decision 20 was a units error: the cut-point is a z-scored logarithm of power, not a linear microvolts squared, so feeding it to the frozen model mis-read every value — a z at or below zero came out as a device reading near zero.** The new path honours the centre exactly with no snapping, fails closed when neither route is available, and leaves the exploration timeline unchanged. | `09798f7` |

### Platform and interface

| # | Decision | Why | Ref |
|---|---|---|---|
| 1 | **The R interface converter is constructed without the frame converter.** | The frame converter turned a control list into a form the R bridge cannot hand back to the model fitter. | `33f45a5` |
| 5 | **The closed-loop figures draw once and mutate by restyling a trace index**, with the request parameters memoised and a permanent drawing element. | A new object identity on every render refetched all four panels, so every figure flashed back to its loading state. **This is a hard constraint** — rebuilding a figure on interaction reintroduces it. | `255e0ef` |

### The cache store, decided 2026-09-06 and 2026-09-07

| # | Decision | Why | When |
|---|---|---|---|
| 22 | **The recordings may be cached with no expiry; the pain reports may not be cached at all.** | The recordings have a freshness check cheaper than the work, built from values already in hand. The pain reports do not — measured twice, the cheapest check costs the same as an outright fresh fetch. | 2026-09-06 |
| 23 | **No pain rating enters the tile file or its key.** | The tiles know nothing about any rating and the same tiles serve every pain score, match rule and length of signal. Keying on the report set would discard a 37-second build every time a report was filed. Proven both ways: changing the report set changes 19,464 of 27,305 answer values **and causes zero writes.** | 2026-09-06 |
| 24 | **The file key is built from the database rows alone, never from the decoded recordings.** | The point of a file is to be found **before** decoding; the warming path especially must answer "is this built?" without opening 569 files. Costs 0.33 s for 4,078 rows. | 2026-09-06 |
| 25 | **The key carries the patient-event row metadata, the decode-time stamping, and every constant the stored numbers depend on.** | Patient-event rows have no content hash at all — 0 of 3,246 — because their spectra are the metadata. The sensing centre and schedules can change with no content change. And a file outlives the process that wrote it. | 2026-09-06 |
| 26 | **The key decides whether to write, not the caller.** A page whose key matches never writes, and that is asserted by test. | Adopted over the first proposal that ingestion be the only writer, which would have left every page slow until each participant's next upload, because the key contains code-version values so a deployment invalidates everything. | 2026-09-06 |
| 27 | **Redis is scoped to build locks, freshness keys and Django's small cache values. The large stored products stay as files.** | Measured: the 245.90 MB tile store reads in 0.05 s from the filesystem against about 0.14 s through Redis, roughly three times slower, because the files are already in the page cache. **The problem is computation, not latency.** | 2026-09-06 |
| 28 | **Redis is bounded at 512 MB with least-recently-used eviction across all keys**, set live and durably on the redis service in both compose files. | It had been unlimited with eviction disabled, which means growing until the host fills and then **refusing new writes** — the opposite of cache behaviour, on a box shared with the database and four workers. Across all keys rather than only expiring ones, because one key written without an expiry could restore that wall. **Authorised out of the plan's order because it was a live hazard.** | 2026-09-06, `b7036bf` |
| 29 | **Stored tables use Parquet with zstd; the spectrum arrays stay as compressed array files.** | Chosen for size and durability, seventeen times smaller than the alternative, and a stable published format. **Pickle writes twice as fast and reads are tied — that caveat travels with the choice.** Comma-separated and JSON files are excluded **on correctness**: the therapy table carries a timezone-aware timestamp and both lose it. | 2026-09-06 |
| 30 | **One store implementation as a superset callable by any module; the duplicate is deleted.** | Two implementations exist with their own resolver, loader, writer, counters and lock, sharing a root by construction accident, with per-entry limits differing by exactly a factor of four for no stated reason. | 2026-09-07 |
| 31 | **The provenance chain and its proven refusal come before anything that writes back to the store.** The refusal is proven by constructing a deliberate cycle. | The four arrows let Stim Optimizer read a verdict computed from recordings Stim Optimizer chose to collect. **Nothing crashes — the exploration policy becomes self-confirming and the record looks like converging evidence when it is a loop.** | 2026-09-07 |
| 32 | **The band range is all 22 centres from 8.5 to 29.5 Hz.** | The PI's flowchart said "8-20" and he corrected it: *"I meant all the bands that this week already covers."* Taking 8 to 20 Hz literally would have dropped the 22 to 27 Hz range holding this record's clearest amplitude response. | 2026-09-07 |
| 33 | **The ground-truth rule for the three-source comparison** — the device's own band power where it exists **and passes a per-channel saturation ceiling check**; the calibrated voltage-trace route where it does not; the composed device-spectrum route below that and tagged composed; never the uncalibrated integrated-density route. Where both exist for one band and setting, **both values and the fold ratio between them are written**. Every row carries its route, its window count, and whether the band sits inside the checked conversion span. | The device's own reading is the exact quantity the control law compares against a switching value typed in those units. **The ceiling check is required because about 1 percent of simultaneous windows are device-side spikes, and a rule adopting the unfiltered reading adopts those spikes as truth.** The fold ratio is the only continuous check on whether the calibration serving the other 97 bands still holds. | 2026-09-07 |
| 34 | **The written record is consolidated into five reference documents; the 50 superseded documents are moved to an archive with `git mv`, never deleted.** No suite count is written into any of them. | *"There are too many Handoffs going on now."* Counts in those documents went stale within single sessions and one reached a pushed commit message that cannot be edited. | 2026-09-07 |
| 35 | **The pain-report snapshot (Track A step 4) is keyed on the content of the tidy table alone, is read by no page, and the store keeps that kind's history rather than sweeping it.** Decision 22 stands: the reports are fetched fresh on every request. | The stored copy buys reproducibility and a key for derived products, not speed. The same table requested two ways is one report set. A swept snapshot would leave the ledger row and not the table, which is the one thing an audit needs; each is about 28 KB, one per distinct report set. Proven on the live record: 9,120 fields compared between the stored and the fetched table, 0 differences; a second fetch leaves the directory byte-identical. | 2026-09-07 |
| 36 | **The project's plan is kept with the `planning-with-files` plugin, in its parseable shape, in legacy mode with structure-aware injection and without attestation or a completion gate; the planning files stay committed.** `CLAUDE.md` §4 carries the rules. | The plugin's completion check read nothing from the earlier heading shape. Attestation blocks context injection whenever the plan file changes until it is re-attested, and the plan changes after every phase. The gate can refuse a stop, and here the PI decides when work stops. Committing keeps the plan with the code it describes. | 2026-09-07 |

---

## Part 2 — Open items

**Dropped by the PI, do not re-open as work:** generalising beyond RCS08, and patient-information
hygiene as a work item — the latter is an operational note in `OPERATIONS_runbook.md` §9 only.

### Open on the PI

1. **Commit identity.** The session rules ask for commits under his name and email; they have been
   made under a machine identity instead, because attributing machine-written commits to a named
   researcher in the permanent record of a research repository is his decision. **Raised three
   times, unanswered.** Nothing already pushed has been rewritten. Whichever he picks, apply it
   consistently and record it here.
2. **The go-ahead to begin the store implementation.** He requires an explicit manual go-ahead
   before implementation, and plan approval is not that. **Nothing in the second phase has been
   started.**
3. **Whether a switching value can sit on a band whose response is peaked**, and whether to fit one
   straight line across 1 to 4.8 mA or something admitting curvature. The device places its
   switching value between two power readings, and a band that rises to about 2.1 mA and then falls
   satisfies the same value on both sides of its peak. **The earlier linear retraction does not
   settle this** — a linear test has almost no power against a rise-then-fall, and a curvature test
   on the one clean day gives p = 0.125. Neither is significant; both rest on 8 steps from a single
   visit day.
4. **Two defects in the shared result-cache contract, which are his files.** The three views work
   around both and say so in their comments. A deliberate recompute issues **two** fetches per
   press. The entry limit is six against nine slots for one participant, **and a count is the wrong
   unit when one entry is nineteen megabytes and another twenty kilobytes** — either raise the bound
   or give the store a sub-key. Smaller: a failed request is stringified, so the exploration view can
   no longer hand the response object to the error display and its wording is lost.
5. **Whether the band-by-length sweep becomes the headline statistic.**
6. **A second sign-off before touching the entangled spectrum-and-correlation pass**, which is the
   one site where computing the spectra and correlating them against pain happen together, ported
   verbatim from the source notebook.

### Open engineering, not blocked on anyone

7. **The 6,309-file spectrum directory must be settled in one decision, not two.** Zero reads by any
   live page were measured, and the PI marked it for deletion. But a separate proposal would wire
   the live path onto those same files. **One plan deletes what the other connects** — decide
   together.
8. **65.71 seconds of therapy-settings-stream building remains** in the Stim Optimizer request,
   because a third consumer still builds its own copy. One of three passes was removed for a
   measured saving of 32.78 s.
9. **The evidence triangle is not displaying.** Check the served bundle before touching component
   code, searching for string literals the panel owns rather than component names.
10. **The pre-registered 110 Hz heat map should be replaced, not re-rendered.** On its visit the two
    stimulators' currents correlate at 1.0 with a longest single-side stretch of zero, **so no
    side attribution is possible from it at all.** The honest replacement is the left 1-3 contact at
    110 Hz built from the two days with the right stimulator at exactly 0.0 mA — the same 15 steps
    behind the p = 0.064 result. Offered, not yet built.
11. **55 Hz has almost no side-attributable coverage on the left electrode, and that is a protocol
    gap.** Of six visit days with 55 Hz recordings there, exactly one has the right stimulator held
    at zero. **There is no cross-day replication at 55 Hz at all.**
12. **The device's own spectrum route is empty during every current ladder**, because the device
    computes a spectrum only on a patient button press or a stimulation-off contact survey.
    **Populating it needs a button press at each held setting — a visit-protocol change, not a code
    change.**
13. **No live end-to-end test asserts that the timeline circle equals the spectral point at the same
    band centre.** The identity holds by construction through one shared store but is not pinned
    across the two call sites.
14. **The within-rating sliding-window overlay with its saturation quality-control flag is built and
    not drawn.** The natural next step is a hover detail on a rating's 30-second trace.
15. **Audit backlog.** All four high-severity items and one medium are resolved and the medium
    bucket is cleared. Remaining: reconcile the clustering granularity between the per-rating and
    the per-week reports, **which needs a judgment call from the PI before coding**; embed picture
    snapshots of the four figures into the printed sheet, which needs the container because the
    sandbox export path is broken; and a batchable cluster of labelling and navigation niceties.

### Resolved by this consolidation — do not re-open

- **"Reading recordings off disk is the largest cost and should be optimised next."** Two different
  requests were being compared. On the whole Biomarker page, reading and un-pickling all 2,007
  stored files is 2.89 s of a 60.4 s request, 4.8 percent, because loading is already spread over
  sixteen threads. **The dominant cost is re-derivation: 72,425,865 channel-name normalisations per
  request, 99.87 percent of them from one line, worth 9.51 s.** The 21.1 percent figure is real and
  describes the warm band-by-length sweep instead.
- **"The module README needs three edits."** Its content is superseded by this document set, and the
  three edits are incorporated: the closed-loop module's use of the calibrated route, the removal of
  a screening gate that exists nowhere in the code, and the section that deliberately ignores the
  length-of-signal slider.

### Then

**Design the closed-loop simulation module against the `BandCandidate` contract.**

---

## Part 3 — Commit lineage

**Read from `git log`, not from recollection.** These are pointers into history; none of them is the
current head unless said so.

### The merged history into the default branch `v3.1.0`

| Pull request | Commit | What it carried |
|---|---|---|
| #3 | `52337f5` merge, `255e0ef` fix | the pain biomarker engine, and the figure-reset fix |
| #4 | `52010ec` | the closed-loop phase-2 figures |
| #5 | `c50be37` | the four-lens audit, waves 1 and 2 |
| #6 | `b0597f8` | the actionability items, the conversion panel, and forward compatibility |
| #7 | `d9d58a4` merge, `b2e01f1` | forward-chaining out-of-sample validation |
| #8 | `a191b758` | interface, performance, and the R thread-safety pass |
| #9 | **`39dfb2f`** | **the whole 61-commit working-branch line merged into `v3.1.0` on 2026-06-29** |

Earlier branch points worth keeping: `f915257` (the modality-sensitive conversion, the threshold-mode
guard), `e9d7a80` (the 8.8 Hz cut date), `184ea74` and `fa2c416` (removing the dead Welch route and
its constant), `09798f7` (the deployment fallback rebuilt off the raw voltage trace),
`e8a0d3f` (a rebuild dropping a retired tier label). `cd09845` and `f6849c4` are stale heads quoted
in archived documents.

### The current working branch, newest first

| Commit | What it did |
|---|---|
| **`705bdb0`** | **current head** — corrected the root-file counts in the takeover handoff, computed rather than eyeballed |
| `98ba64a` | corrected the takeover handoff: the design ledger is an artifact, not a repository file |
| `37c447f` | handed the cache-store work over |
| **`b7036bf`** | **bounded Redis's memory and gave it a real eviction policy** (decision 28) |
| `e8c2000` | recorded the shared tile cache, the decode review, and a regression shipped and then found |
| `931cb81` | fixed the regression test's last assertion, **and corrected a suite count stated in `b657968` without verifying it** |
| `b657968` | built the settings stream once per Stim Optimizer request; fixed the array-spectra regression |
| `2bef090` | shared the 3-second tile cache between worker processes and warmed it at ingest |
| `b700717` | recorded the display diagnosis — a missed frontend rebuild. **Its message also carries the wrong claim that the container path is not a live mount** |
| `7ab2d1b` | rebuilt the served bundle so the sweep panel reached the browser. **Same wrong claim in its message** |
| `15d38ef` | updated the durable handoffs and reconciled the two-month-old corrections summary |
| `2a4d063` | batched the sweep's shuffles and resamples across the ten integration times, **changing no number** — 1.78x |
| `c70e0b0` | asked REDCap for only the columns the page reads — 1.662 s to 0.651 s |
| `958cc89` | **the matcher vectorised, 21.4x**, proven over 1,080 configurations with zero field differences |
| `790ed21` | clipped the pre-change look-back at the measured end of the ramp |
| `e1cc557` | **the band-by-length sweep**, and made the reported best pay for having been chosen |
| `bfc3b8f` | **refused a recording whose current never holds still**, instead of describing it as a 615-second ramp |
| `0f6a75b` | moved the three-source comparison to the bottom of the page and stopped asserting contamination |
| `eb33ade` | measured the ramp from the device instead of assuming 45 s; averaged the settled values |
| `90eb109` | **read the closed-loop band power from the calibrated route** — moved the deployable verdict from 2 of 50 to 6 of 50 settings, changed the selected configuration from the left 1-3 contact at 165 Hz to the left 0-2 contact at 55 Hz, and reversed the sign of the current-to-power relationship |
| `688a185` | recorded that the closed-loop band power was not on the device's scale, **and withdrew an invented constant** |
| `0d8a862` | corrected visit counts in a handoff that had restated a sub-agent's prose unchecked |
| `97c9664` | fixed a units error in the current-response comparison |
| `8e31342` | cached the cold build across workers; moved the pain relationship into the biomarker module |
| `6c3c9f2` | **corrected the brain-side labels in the pre-registration, by amendment rather than by editing** |
| `856def2`, `b6f22ec`, `6f66905` | pre-registered the 110 Hz hypothesis; made the staged path reachable on live recordings |

### Source-of-record documents that are not repository files

- **The design ledger** `DESIGN_biomarker_pipeline_v2.md`, revision 13 — artifact
  `f9b3d791-7e95-44bb-bd81-8aebcf9e1b3b`, latest version
  `c7bf4b85-4867-4e3a-b8de-2ba900d1fd9b`. A duplicate record `917ae0bd-7f0a-4fd5-af3d-8a00d4446936`
  exists, so a search returns two rows. An archived index cited `bab71722-0293-453e-9d21-36b77a26cbac`,
  which is superseded.
- **The four-lens audit of record** `closedloop_audit_report.md`, version
  `e3a12136-e0e1-4fff-b95f-baa42d0a0a46` — **the source for the remaining audit backlog in open
  item 15.** The medium and low decision sheets are in `docs/archive/2026-09-07/`.
- **The cache inventory** — `CACHE_MAP.md`, `cache_map.png`, `cache_map.excalidraw`,
  `cache_map.html` and `build_cache_map.py`, saved as artifacts and also present in the untracked
  `cl_docs/` folder. The PI's own edited flowchart is the artifact `newcachemap.excalidraw`.

### Environments

- **`bravo_app`** — Python 3.11 on the host, for decoding free of Django and pure-function checks.
- **`rocqa`** — plotting, with the headless-browser picture export **broken in this sandbox**.
- **The live container** — Python 3.12.3, rpy2 3.5.15, pymer4 0.8.2, pandas 2.2.3, sklearn 1.5.2.
- **The device exported files** are at the shared-drive grant `…/PNL/RCS008 jsons`, whose file
  names carry real patient names; keep that folder out of the repository.
