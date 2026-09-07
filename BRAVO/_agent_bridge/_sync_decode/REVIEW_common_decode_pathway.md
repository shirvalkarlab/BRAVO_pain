# Should reading Percept recordings become one shared pathway? A measured review

**Participant** RCS08, uid `2e3c75c00d7f4f37b53a048d195f11da`. **Branch** `PS_closedloop_deployment`.
**All numbers below were measured on the live record on 2026-09-06 between 10:16 and 11:09 UTC**,
inside the running container through the bridge. Nothing is carried from a previous session and
nothing is estimated unless the word *projected* appears next to it.

**Line numbers were re-verified at 11:09 UTC.** Another agent is editing
`Biomarkers/bravo_service.py` and `Biomarkers/routines/availability.py` while this was written, and
`bravo_service.py` line numbers already moved during the session (a call site I first read at 3316
was at 3849 an hour later). Every line number quoted for those two files was re-read at 11:09 UTC
against a 6,301-line `bravo_service.py` and a 1,910-line `availability.py`.

---

## 0. The headline, and a correction to the premise

**The premise that reading recordings off disk is now the top cost does not hold for the Biomarker
page.** Reading and un-pickling every stored file for RCS08 costs **2.89 s of a 60.4 s request,
4.8 percent**. It looks larger than it is because the work is spread over sixteen threads: the
thread-seconds add to 39.8 but they compress into 2.89 s of wall clock. A cache of decoded bytes
cannot save more than about three seconds on that page, however it is built.

**The cost is re-derivation, not decoding.** In one Biomarker page request the channel-name
normaliser is called **72,425,865 times, and 72,332,380 of those (99.87 percent) come from one
line** — `availability.py:986`, the spectrum-record scan inside `per_pro_lsb`. That line walks the
whole list of 4,010 spectrum records once per pain report and re-normalises every record's channel
name and re-parses its timestamp on every pass. Both are properties of the record. The request
already had both values 72 million times over.

**The single largest saving in this review is not on the Biomarker page at all.** On the Stim
Optimizer request, `StimOptimizer/adapter.py:settings_stream` is called **three times at 31.87 s
each — 95.61 s of a 115.17 s request**. Two of the three are avoidable, **63.74 s, 55 percent of
that request**, and the argument for passing the already-built stream in already exists on both
callers and is documented in their docstrings. Nobody passes it.

**Measured prototype result.** A canonical form that normalises channel identity once and groups
records by it, read by a parallel copy of `per_pro_lsb`: **9.233 s → 0.551 s including the cost of
building the form, 16.75×, 8.68 s saved on a 60.4 s request**, with **159,600 fields compared
across 22,800 records and 0 differences**.

---

## 1. The decode census

Every place raw device data is read and turned into something else. `Database.loadSourceFile` is
the one primitive underneath all of it: open the stored file, verify its hash, decompress with
blosc2, un-pickle.

| # | Where | Reads | Produces | Called by | Cached, and at what scope |
|---|---|---|---|---|---|
| 1 | `DataCurator.py:869–1106`, `MedtronicPercept/Percept.py:97–99` | the encrypted Percept JSON export | one stored `.bdat` per recording plus its database row | ingest only (`management/commands/ingest_percept_folder.py`) | on disk, permanently — this is the store |
| 2 | `Database.loadSourceFile` (`Database.py:744`) | one stored `.bdat` | the decoded recording dictionary | everything below | **not at all** |
| 3 | `bravo_service._load_recordings` (`:340`) | every `.bdat` of the requested types | list of decoded dictionaries, stamped with the database type and sensing centre | **26 call sites in `bravo_service.py`, 3 in `ClosedLoopDeployment/three_source_response.py`, 1 in `StimOptimizer/adapter.py` — 30 sites in 3 modules** | **not at all.** Round 2 of the same request in the same process decodes exactly as many files as round 1 |
| 4 | `bravo_service._load_patient_events` (`:406`) | `PatientControllerEvent` rows | button-press spectra, read off the row metadata | availability timeline | no file decode at all (data is on the row) |
| 5 | `availability.lsb_series` (`:445`) | decoded chronic + streaming band-power dictionaries | one band-power series per channel in device units | `_build_availability` | no |
| 6 | `availability.per_pro_lsb` (`:848`) | decoded voltage traces + spectrum records | one band-power value per pain report, three-tier | `bravo_service._pro_lsb_by_channel` (`:703`) | no |
| 7 | `availability.per_pro_lsb_spectrum` (`:1008`) | same | the whole 0–100 Hz band-power vector per pain report | `_lsb_spectrum_products`, `_raw_lsb_cache_cached` | in-process memo `_LSB_SPECTRUM_MEMO`, cap 8 |
| 8 | `availability.raw_lsb_spectrum_cache` (`:1158`) | same | 3-second tiles across all 98 band centres | `_raw_lsb_cache_cached` (`:1343`) | in-process memo cap 8, **plus a shared file** — 245.9 MB for RCS08, 1 hit / 0 misses this session |
| 9 | `bravo_service._welch_rows_into` (`:1694`) → `streaming_psd.welch_psd_for_instance` | decoded voltage traces | one spectrum row per recording-channel | `_assemble_psd_rows_cached` (`:2019`) | on disk per recording, `_recording_psd_cache_path` |
| 10 | `bravo_service._assemble_psd_rows` (`:1663`) | same | same | **nobody — dead code, see defect D6** | — |
| 11 | `streaming_psd.compute_psd_pain_correlation` (`:1066`) → `welch_psd_for_instance` | decoded voltage traces | spectra **and** their correlation against pain, in one pass | `pipeline.run_timedomain_branch` (`:622`) | **none.** This is the path the page actually uses: 386 spectra recomputed every request, 4.05 s, while 6,309 cached spectra sit unread on disk |
| 12 | `ClosedLoopDeployment.three_source_response.read_device_current` / `read_device_band_power` (`:1153–1173`) | decoded streaming band-power dictionaries | per-sample current and band power on the device's own clock | `build_for_participant` | through the shared tile file — **0 decodes measured on that endpoint** |
| 13 | `StimOptimizer/adapter.settings_stream` (`:118`) | the encrypted source files, re-read and re-decrypted | the therapy-settings table | **three sites: `StimOptimizer/bravo_service.py:153`, `adapter.py:423`, `adapter.py:485`** | **no. 31.87 s per call, called three times** |
| 14 | `Server/APIs/DataAnalysis.py` (`:89–189`) | decoded recordings | channel names rewritten to the electrode's custom name for display | the browse/view endpoints | no |

### Decode counts and wall clock, four endpoints, two consecutive requests each

| Endpoint | round 1 | round 2 | decode calls | distinct files | redundant calls | worst file |
|---|---|---|---|---|---|---|
| Biomarker page | 70.98 s | 60.56 s | **2,453** | 2,007 | **446** | decoded 2× |
| Band-by-length sweep | 5.50 s | 5.03 s | 832 | 832 | 0 | 1× |
| Closed-loop deployment | 0.435 s | 0.413 s | **0** | 0 | 0 | — |
| Stim Optimizer | 119.62 s | 112.53 s | 2,536 | 1,400 | **1,136** | **decoded 3×** |

Two facts to read off that table.

1. **No endpoint's decode count falls on the second request.** There is no cross-request memory of
   decoded recordings anywhere in the platform. **I did not reproduce the 6.06 s warm figure recorded
   earlier tonight** — a second request in the same process took 60.6 s and decoded the same 2,453
   files, so whatever makes a warm page 6 s is a whole-result cache hit outside
   `run_for_participant`, not a cheaper rebuild. Either way, the decode is paid in full on every
   request that is not an exact repeat, which is every slider move.
2. **The closed-loop page decodes nothing**, because it reads the shared tile file instead. That is
   the shared decoded form working, on one endpoint, for one product. It is the existence proof
   that the design in §3 is buildable here.

### Where the 60.4 s of a Biomarker page request goes

Wall-clock stopwatches around whole stages, no profiler. cProfile cannot be used for this: with
72 million calls to one tiny function it inflates that stage roughly six-fold and every comparison
drawn from it is wrong (the same request profiles at 143.6 s against a true 60.4 s).

| Stage | seconds | share |
|---|---|---|
| `_compute_analytics` — every statistic | 19.13 | 31.7% |
| `pipeline.run_biomarker` — the two source branches | 17.14 | 28.4% |
| `_build_availability` | 14.28 | 23.6% |
| `_programmed_adaptive_thresholds` | 5.55 | 9.2% |
| **`_load_recordings` — read and un-pickle every file, 6 calls** | **2.89** | **4.8%** |
| `_load_pros` — the REDCap pull | 1.10 | 1.8% |
| *(sums to 60.09 of 60.39 s)* | | |

Inside those, the items a shared decoded form could touch:

| Nested item | seconds | share |
|---|---|---|
| `per_pro_lsb`, 30 calls (inside `_build_availability`) | 9.51 | 15.7% |
| `welch_psd_for_instance`, 386 calls (inside `run_biomarker`) | 4.05 | 6.7% |
| `lsb_series`, 1 call | 1.25 | 2.1% |
| `_event_psd_lsb_blocks`, 2 calls | 0.72 | 1.2% |

And the items it could not: `sliding_window_analytics` 10.55 s, `spectral_feature_importance`
8.49 s, `run_chronic_threshold` 3.11 s. **The statistics and the two pipeline branches together are
36.3 s of the 60.4 s and no change to how recordings are read will move them.**

---

## 2. The measured decode count per request

**2,453 decode calls on 2,007 distinct stored files, 425–465 MB read and un-pickled, per Biomarker
page request.** Counted by wrapping `Database.loadSourceFile` and keying on the file pointer, not by
reading code. Identical on both of two consecutive requests in one process.

**446 files are decoded exactly twice.** Attributed to their call sites: two separate places load
the same three survey and montage types.

* `bravo_service.py:2658` (inside the per-request pain-report scope) — 446 files, 0.362 s
* `bravo_service.py:3849` (`run_for_participant` directly) — the same 446 files, 0.375 s

One of the two is pure waste: **0.37 s.** The other four `_load_recordings` calls are distinct type
sets and are not redundant.

**On the Stim Optimizer, 568 files are decoded three times each** — 1,136 redundant calls of 2,536,
44.8 percent. All three arrive through `adapter.settings_stream`, from
`StimOptimizer/bravo_service.py:153`, `adapter.py:423` (`evidence_inputs`) and `adapter.py:485`
(`build_design_matrix`). This is the same symptom that was fixed once in the closed-loop path; it is
still present here, with three callers instead of two.

---

## 3. Entanglement: is decoding separable from the analysis that follows it?

**Almost everywhere, yes — and that makes reshaping the data flow a refactor rather than a rewrite.**
This is the finding that should most change the PI's read of option 1.

### Cleanly separable (no analysis inside)

* `Database.loadSourceFile` — bytes to dictionary and nothing else.
* `bravo_service._load_recordings:340` — decode plus stamping the database type and sensing centre
  onto each dictionary. No arithmetic. Adding a cache in front of it changes no number.
* `availability.lsb_series:445` — reads band power the device already computed. No transform.

### Separable, but currently interleaved — the three places worth naming

All three have the same shape: a lookup that belongs to the recording is performed inside a loop
over pain reports, so the same derived value is rebuilt once per report.

1. **`availability.per_pro_lsb:986`** — the spectrum-record scan. `for ev in (event_psd_recordings
   or []): if not isinstance(ev, dict) or _canon_channel(ev.get("channel")) != channel: continue`,
   followed by `_to_epoch(ev.get("t"))` on line 989. Both inside the report loop that opens at
   line 933. **This one line accounts for 72,332,380 of the request's 72,425,865 channel-name
   normalisations.** Cost: 9.51 s of 60.4 s.
2. **`availability.per_pro_lsb_spectrum:1121`** — byte-for-byte the same scan, inside the report
   loop of the full-spectrum builder. Not exercised by the default page request, so I have no wall
   figure for it; it is on the path the band-length sweep and the raw tile cache use.
3. **`availability.per_pro_lsb:912`, `:1059`, `:1219`** — resolving a channel to its column with
   `ci = next((i for i, n in enumerate(names) if _canon_channel(n) == channel), None)` and then
   `np.asarray(r.get("Data"), dtype=float)` on the next lines. Once per recording per call, so the
   832 voltage traces are re-scanned and re-converted to float 30 times in one request.

**None of these three is entangled with the science.** I lifted the first into a prepared lookup
and the band-power values did not move — 159,600 fields, 0 differences. The three-tier precedence,
both tolerance windows, the dropped-packet rejection, the saturation rule and the tie-break all sit
*outside* the part that was lifted.

### Genuinely entangled — one place, and it is the one that would need a rewrite

**`streaming_psd.compute_psd_pain_correlation:1066`, reached from `pipeline.run_timedomain_branch:622`.**
One pass computes the spectra (`welch_psd_for_instance`, line 1115) *and* normalises them *and*
correlates every channel-by-frequency feature against the pain score. There is no point in it where
a spectrum exists as a separable product. Its docstring says the design is deliberate — each step
delegated to functions ported verbatim from the source notebook "so the analysis math is unchanged".
Pulling the spectra out of it is the one piece of this work that touches the statistics, and it is
the one piece I would not do casually. It is 4.05 s of the 60.4 s.

The awkward part: **the spectra it recomputes are already cached on disk by a different builder.**
`_assemble_psd_rows_cached:2019` maintains 6,309 files, 30.5 MB, and the page request never reads
one of them (`_load_recording_psd_rows` called 0 times, measured). Two builders, two caching
regimes, and the live path is the uncached one.

---

## 4. The design for the common pathway

### What the single intermediate form is

**One `ChannelIndex` per participant, keyed on canonical channel, holding the two routes separately
with their provenance attached.** Implemented at `modules/DecodeCommon/representation.py`.

```
ChannelIndex
  version            int, bumped when the fields or the grouping rule change
  td_by_channel      canonical channel -> { traces: [ ... ], t0: float64[n] }
      trace          { t0, t1, fs, col, miss, step, raw_channel, source }
  psd_by_channel     canonical channel -> { t: float64[n], records: [ ... ] }
```

* `col` is the channel's own column of samples, **microvolts, 250 per second, exactly as decoded**.
* `miss` is one dropped-packet flag per sample, collapsed by the any-channel rule.
* `t0`/`t1`/`t` are Unix epoch seconds, parsed once.
* `step` is the sample hop the band-power recipe advances by, taken from
  `analytics.TRANSFORM_STEP_SECONDS`, passed in as a required argument so this file cannot silently
  disagree with the recipe.
* `records` are the spectrum blocks the service already assembles, untouched, **in their original
  order** — because the reader breaks a tie between two equidistant records by taking the first, and
  sorting would change which one wins.

### Units, and where conversion happens

**The form converts nothing and stores no constant.** Every array is in the units it was decoded
in. The two calibrated constants stay exactly where they are:

* `LSB_PER_UV2_TRANSFORM = 352.62`, applied inside `analytics.td_to_lsb`, voltage-trace route.
* `LSB_PER_DEVICE_PSD = 73.63`, applied inside `analytics.device_psd_to_lsb`, device-spectrum route.

A reader of the form calls those same two functions. This is deliberate and it is the single most
important rule in the design: a shared decode layer must not become a second place where a unit
conversion can drift. **A test asserts the module text contains neither constant** — not a reading
of the file, an assertion on its source.

The band range the conversion is checked over, `LSB_VALIDATED_HZ_LO = 7.8` to
`LSB_DEPLOYABLE_HZ_HI = 30.0`, is also read from `analytics` by the reader, not restated.

### The two routes

**The form holds both, separately, with provenance — not one with a flag.** They do not cover the
same recordings: the device computes its own spectrum only on a patient button press or a
stimulation-off contact survey, so on RCS08's four rendered current ladders the device-spectrum
route produced nothing at all. Merging them into one array would invent coverage that does not
exist. Each grouping is its own dictionary, each prepared entry carries the `source` string its
record arrived with, and `summary()` reports offered-against-kept counts per route so a systematic
loss appears as a count rather than as an empty panel.

### Where it is cached, keyed on what, and who invalidates it

**Not in the prototype — built per request, which is already enough to buy the 8.68 s.** For a
cross-request cache the platform already has the right key and the right file discipline; the design
is to reuse both rather than invent either.

* **Key**: `_raw_lsb_recording_identity(participant_uid)` (`bravo_service.py:1163`) — built from
  the database rows alone, with no file decoded. Its own docstring records 0.33 s for RCS08's 4,078
  rows; that figure is read from the code and I did not re-measure it. That property is load-bearing: the point of
  a file is to be found before any heavy work is done. Add `CHANNEL_INDEX_VERSION` and
  `_CHANNEL_CANON_VERSION` to it, so a change to the normalisation rule or the field set is a miss
  and a rebuild, never a wrong answer.
* **File discipline**: `_shared_store` / `_shared_load` (`bravo_service.py:1057`, `:981`). Written
  to a temporary name carrying the process id and moved into place with `os.replace`, so a reader
  sees either the old complete file or the new complete file and never a partial one — four gunicorn
  workers can finish the same build at the same moment. **The stored signature is compared against
  the requested one rather than trusted from the file name**, so a hash collision or a file left by
  differently-keyed code is a miss.
* **Who invalidates**: nobody, explicitly. A new ingest changes the row identity, so the new entry
  lands under a new name and `_sweep_superseded_entries` removes that participant's older entries of
  the same kind *after* the replacement is in place.
* **Partial or corrupt cache**: every failure is a miss, never an exception — a half-written file, a
  payload written by a different numpy version, a permissions change. The correct answer is always
  still obtainable by rebuilding, so a clinician's page must never return an error for a cache
  problem. The unreadable file is deleted and counted in `_SHARED_CACHE_EVENTS`.

### How a consumer asks for a subset without materialising everything

Three levels, all measured in the prototype:

1. **One channel**: `index.td(channel)` / `index.psd(channel)` — a dictionary lookup on the
   canonical name. The reader never normalises a name.
2. **One time window**: `np.searchsorted(td_t0, t, side="right")` on the pre-sorted start times
   bounds the traces that could cover an instant; `np.argmin(np.abs(psd_t - t))` finds the nearest
   spectrum record in one array operation instead of a linear scan.
3. **One band**: unchanged — the band is an argument to `analytics.td_to_lsb` /
   `analytics.device_psd_to_lsb`, which read the one band asked for. The form deliberately does not
   pre-compute band powers, so asking for one band never materialises 98.

Nothing copies on read. `col`, `miss`, `t`, `freq` and `power` are views shared by every reader; the
class docstring states the read-only contract and a test asserts three reads leave the arrays
unchanged. The current code has the same property and the same unwritten rule — stating it is the
only change.

### What must NOT be cached: the REDCap pain reports

**The form is built from recordings alone. No pain report, no REDCap column, nothing derived from
either.** This is not an omission, it is the design.

Reports are filed continuously, so a stored copy that outlived one request would eventually serve an
analysis silently missing the newest ones, with every correlation and every `established` verdict
wrong while the page looked normal. A cross-request cache was made conditional on a freshness key
cheaper than the pull, and measured twice on the live record there is none: REDCap's
record-edit-log check costs the same few tenths of a second as an outright fresh narrowed fetch.
Recordings have a cheap content key — the row's stored hash — and reports do not. **Because the form
holds no report, it never needs a freshness check at all**, which is exactly why the key can be the
row identity and the entry can live on disk.

One consequence to keep: the per-recording spectrum cache currently mixes the two by putting a
pain-report-set signature into the key of voltage-trace entries
(`_recording_psd_cache_path`, `pro_sig`). That is correct for what it stores — those spectra are
centred on the reports — but it means a single new report invalidates every voltage-trace spectrum.
The canonical form should not repeat it: keep the report-dependent product downstream of the form,
not inside it.

---

## 5. The prototype, measured

**Files.** `BRAVO/modules/DecodeCommon/` — `representation.py` (the form),
`per_pro_lsb_indexed.py` (one parallel reader), `tests/test_decode_common.py` (32 tests).
**Nothing in the platform imports it.** `availability.per_pro_lsb` is untouched and remains the only
path the running server uses; the prototype is a parallel function, not a flag on the existing one,
because the existing one lives in a file another agent is editing.

**The narrow path chosen**, and why: `per_pro_lsb`. It is the largest single item a decoded-form
change can address on the busiest endpoint (9.51 s of 60.4 s), it is the location of 99.87 percent
of the measured re-derivation, and its output is a flat list of small dictionaries that can be
compared field by field for exact equality. Nothing wider was attempted.

### Timing — alternating rounds, live record

Arguments captured from a real page request: 30 calls, 760 pain reports each, 832 voltage-trace
recordings, 4,010 spectrum records.

| | round 1 | round 2 | round 3 | mean |
|---|---|---|---|---|
| current `availability.per_pro_lsb` | 9.304 s | 9.291 s | 9.104 s | **9.233 s** |
| `per_pro_lsb_indexed` | 0.324 s | 0.330 s | 0.324 s | **0.326 s** |
| building the form (once, all 30 calls share it) | — | — | — | **0.225 s** |

**9.233 s → 0.551 s. 16.75×. 8.682 s saved on a request measured at 60.4 s — 14.4 percent of it.**

The three rounds span 0.20 s on the current path and 0.006 s on the indexed path, so the difference
is not a scheduling artefact. The saving is smaller than the raw call-count reduction (72,332,380
normalisations down to roughly four thousand) would suggest, because each individual call is
microseconds — the honest figure is the wall clock, not the count.

### Equality — field by field, exact

| | |
|---|---|
| calls compared | 30 |
| records compared | **22,800** |
| fields compared per record | 7 (`t`, `lsb`, `tier`, `center_hz`, `used_s`, `saturated`, `reason`) |
| **fields compared** | **159,600** |
| **differences** | **0** |
| channel names checked against the platform's normalisation rule | 42 |
| mismatches | **0** |

Exact equality, not tolerance: `==` on every field, with a NaN-equals-NaN case. The comparison
covers all three tiers as they actually occur on the live record.

### The 32 tests, and what they are for

They are not there to show the prototype works. They are there so it cannot quietly disagree with
the code it is measured against. **Six** assert the normalisation, timestamp and dropped-packet rules
agree with `availability`'s on every case including ring names, session-relative start times and
two-dimensional missing fields. **Ten** pin what the built form holds — grouping, ordering, the
first-column-only rule, transposed sample blocks, offered-against-kept counts. **Fourteen**
construct recordings where the answer is known and assert the two implementations return the
identical record — device-sensed, modelled-point-must-lose,
sensed-flag-wrong-length fail-closed, voltage trace, ring-named voltage trace, report outside every
recording, railed window falling through to the spectrum, spectrum route, band outside the checked
conversion range, equidistant tie-break in both list orders, record just outside tolerance, record
belonging to another channel, no pain reports at all, and a mixed 40-report case that reaches three
tiers. **Two** are discipline checks: the form carries no calibration constant, and reading it
leaves its arrays unchanged.

**`DECODECOMMON PASS=32 FAIL=0`** (run through the container, which has no pytest, with a runner
that calls each test with no arguments — the same way `_agent_bridge/run_tests.py` does).

### Is the saving smaller than projected?

**On the Biomarker page, the *decode* saving is far smaller than the premise implied, and the
*re-derivation* saving is larger.** Caching decoded bytes across requests can recover at most the
2.89 s that `_load_recordings` costs, and removing the one duplicated load recovers 0.37 s of that.
Lifting the re-derivation recovered 8.68 s, measured. Anyone budgeting this work off the "reading
recordings is 21 percent" figure would size it wrongly in both directions.

---

## 6. Defects found, ranked by consequence

### Could produce a wrong scientific number

**D1 — `bravo_service.py:1780`: a spectrum computation failure silently drops the recording.**
`except Exception: continue`, no log. A recording that fails Welch contributes no spectrum and is
indistinguishable downstream from a recording that does not exist. The comment above the block
explains the *adjacent* all-NaN case and reads as if it covered this one. A systematic failure — a
scipy upgrade, a shape change — would quietly shrink the sample every correlation is computed on
while the page looked normal. This project has already lost every Stim Optimizer figure once to a
caught `ImportError`.

**D2 — `analytics.py:1255`: the clustered significance value returns NaN on any failure, unlogged.**
`except Exception: return _np.nan, int(n), n_clusters`, wrapping the whole `statsmodels` fit. That
value feeds the multiple-comparison correction and therefore decides whether a band reads
`established`. Whether a NaN is treated as not-significant or dropped from the correction is the
difference between a band being reported and not, and a reader cannot tell a genuine
non-significance from a fit that threw.

**D3 — the per-recording spectrum cache is keyed on hand-maintained version strings, not on the
values they stand for.** `_recording_psd_cache_path` embeds `_CHANNEL_CANON_VERSION = "v2_ring_aware"`
and `_TD_MISSING_VERSION = "v1_missing_aware"` (`bravo_service.py:1598`, `:1615`). The actual
governing value, `streaming_psd.WELCH_MAX_MISSING_FRAC = 0.10`, is not in the key. Change the
fraction without remembering to bump the string and every one of the 6,309 stored entries is served
under the old rule, silently. The Welch window length *is* in the key directly (`w30p0`), which is
the pattern the other two should follow. Mitigating fact, worth stating: the frequency grid is not
in the key either, but each stored row carries its own `freq` array, so a grid change is safe.

**D4 — a channel that fails silently disappears from the payload.** `bravo_service.py:746`,
`except Exception as e: _log.warning("Biomarkers: per-PRO LSB failed for %s", ...)`. It logs, which
is why this is ranked below D1 and D2, but the response carries no marker: a reader sees 22 channels
instead of 23 and has no way to know one was dropped rather than absent.

### Wastes large amounts of time, changes no number

**D5 — `StimOptimizer/adapter.settings_stream` is rebuilt three times per request: 63.74 s of a
115.17 s request.** Three call sites — `StimOptimizer/bravo_service.py:153`, `adapter.py:423`,
`adapter.py:485` — each read, decrypt and parse the same 568 stored files at 31.87 s a time.
**Both downstream callers already accept a `settings_stream` argument** and their docstrings
(`adapter.py:413`, `:476`) say passing it avoids the rebuild. Nobody passes it. This is the largest
single measured saving in the review and the most self-contained.

**D6 — `bravo_service._assemble_psd_rows:1663` is dead code that looks live.** 29 lines (1663-1691, next `def` at 1694), no caller
anywhere in `modules/` or `Server/`; the only reference is a docstring in
`_assemble_psd_rows_cached:2026` asserting the two produce identical rows. It reads as the
uncached sibling of a live function, which invites someone to reason about caching behaviour from a
function that never runs.

**D7 — the page's spectrum path ignores the disk cache the platform maintains for it.** 386 spectra
recomputed per request (4.05 s) through `pipeline.run_timedomain_branch:622` while 6,309 cached
spectra (30.5 MB) sit unread. Measured: `_load_recording_psd_rows` called 0 times during a page
request. Routing the live path through the cache is not a small change, because the recompute is
entangled with the correlation (§3), which is why this is a defect report and not a suggestion.

**D8 — 446 files decoded twice per page request, 0.37 s.** `bravo_service.py:2658` and `:3849` load
the same three survey and montage types independently.

**D9 — the spectrum cache directory accumulates superseded key generations.** Four entries exist for
the same recording and hash — bare, `_w30p0`, `_w30p0_v2_ring_aware`,
`_w30p0_v2_ring_aware_v1_missing_aware` — and only the last can ever be read. 6,309 files, 30.5 MB
today, so this is a tidiness problem now rather than a disk problem; the shared tile cache does have
a sweeper (`_sweep_superseded_entries`) and this one does not.

**D10 — `_programmed_adaptive_thresholds:2385` issues a query per therapy group.** 5.55 s of the
request, with `_hemi_of_group` called 18,628 times and 37,348 database queries in the profile. Not a
decode problem and outside a common pathway, but it is 9.2 percent of the page and larger than
everything decode-related put together.

### Not defects, recorded because I checked them

* **`availability._lsb_family_mat:1329` keys its memo on object identity** (`is`, not equality),
  which normally risks a recycled address. It holds a reference to the row list it was built from,
  which stops the identity ever being recycled under it, and marks the matrix non-writeable. Sound.
* **In-process memos hand every caller the same dictionary** (`_LSB_SPECTRUM_MEMO`,
  `_RAW_LSB_CACHE_MEMO`, cap 8). One writer mutates a shared cached object —
  `_lsb_family_mat` parks its converted matrix back inside the family dictionary — and it is
  reasoned about in the docstring and guarded. I found no unguarded mutation of a shared cached
  object, but the pattern has no structural protection: the next caller to write a key into a
  memoised dictionary will not be caught by anything.
* **`/usr/src/BRAVO` IS a live mount of the host `BRAVO/` subtree** (`mac on /usr/src/BRAVO type
  virtiofs`). A file written on the host is visible in the container immediately; I verified this for
  both `_agent_bridge/` and `modules/`. The session brief said otherwise, and copying individual
  files in is not necessary. Worth correcting wherever that instruction is kept.

---

## 7. The decision, for the PI

Baseline for all three: **60.4 s** for a warm-in-process Biomarker page request and **71.0 s** for
the first in a fresh process, both measured tonight. These are not the same measurement as the
53.44 s cold figure recorded earlier this evening — that was a real gunicorn worker, mine is a
single process through the bridge — so the savings below are given in **seconds measured** and as a
share of **my** 60.4 s baseline, not mixed with the 53.44 s.

### Option 1 — reshape the platform's data flow onto one canonical form

| | |
|---|---|
| Saving, **measured** | **8.68 s** (`per_pro_lsb` through the form) **+ 0.37 s** (the duplicated load) = **9.05 s, 15.0%** |
| Saving, **projected, not measured** | +2.5 s if the form is cached across requests (the 2.89 s of `_load_recordings` less the cost of the row-identity key, quoted in the code as 0.33 s and not re-measured by me); +up to 4.05 s if the spectrum path is routed through the existing disk cache; +the same lift on `per_pro_lsb_spectrum`, whose shape is identical but which the default page does not call |
| Projected total | **12–16 s of 60.4 s, 20–26%** |
| Call sites | **30 `_load_recordings` sites across 3 modules**, plus 9 consumers that re-derive (`per_pro_lsb`, `per_pro_lsb_spectrum`, `raw_lsb_spectrum_cache`, `lsb_series`, `_welch_rows_into`, `_assemble_psd_rows_cached`, `settings_stream`, `read_device_current`, `read_device_band_power`) |
| Modules | Biomarkers, StimOptimizer, ClosedLoopDeployment, and the ingest side untouched |
| Specific risk | **One place is genuinely entangled and it is the one that touches the statistics**: `compute_psd_pain_correlation` computes spectra and correlates them against pain in a single pass, ported verbatim from the source notebook. Everything else lifted cleanly. Second risk: two of the files most in need of the change are being edited by another agent right now, so this cannot start until that lands. |

### Option 2 — adopt the form selectively, on the re-derivation sites only

| | |
|---|---|
| Saving, **measured** | **8.68 s, 14.4%** |
| Saving, projected | + the same lift on `per_pro_lsb_spectrum` (unmeasured; the band-length sweep is where it would show) |
| Call sites | 2 functions in `availability.py` plus their 3 callers. Roughly 60 lines changed. |
| Modules | Biomarkers only |
| Specific risk | Low, and bounded by the equality proof: 159,600 fields, 0 differences. The real risk is *organisational* — a second grouping helper next to the old per-report scans, with nothing forcing a new consumer to use it, is how the platform ended up with three spectrum builders in the first place. |

### Option 3 — self-contained fixes only, no shared form

| | |
|---|---|
| Saving, **measured** | **63.74 s on the Stim Optimizer request (55% of 115.2 s)** from D5, plus **0.37 s on the Biomarker page** from D8 |
| Saving, projected | up to 4.05 s on the page from D7, but D7 is not self-contained — see §3 |
| Call sites | D5: 2 call sites, both already accepting the argument. D8: 1 call site deleted. D6: 29 lines deleted. |
| Modules | StimOptimizer, Biomarkers |
| Specific risk | Very low for D5 and D8. **But it fixes almost nothing on the Biomarker page**, which is the page the PI is actually waiting on: 0.37 s of 60.4 s. |

### Recommendation

**No single option dominates, because the largest saving and the page the PI cares about are in
different places. Take option 3's D5 first, then option 2. Do not start option 1 yet.**

The reasoning, in order.

1. **D5 is 63.74 seconds for a two-line change on a parameter that already exists.** Nothing else in
   this review has that ratio. It should not wait behind an architecture decision.
2. **Option 2 buys 8.68 measured seconds on the page for about sixty lines, with 159,600 fields
   proven identical.** It is the whole of option 1's *measured* benefit for a fraction of its reach.
   Option 1's extra 3–7 seconds are projections I did not measure.
3. **Option 1's case rests on the entanglement finding being favourable, and it is — but its two
   target files are being rewritten right now.** Starting it tonight would collide. The finding to
   carry forward is that when the moment comes it is a refactor, not a rewrite: one entangled site
   out of the whole census, and I lifted the largest one without moving a number.
4. **The one thing I would argue for beyond the numbers**: option 2 done as a *shared* grouping that
   options 1 and 3 both read, rather than as a local fix inside `per_pro_lsb`. The measured pathology
   is not that one function is slow; it is that the platform has three spectrum builders, three
   copies of the same event scan and one dead sibling, because there was never one place for a
   decoded recording to be. A local fix leaves that intact and cheaper to repeat.

**And the correction the PI should hear first**: reading bytes off disk is 4.8 percent of the page.
The statistics and the two pipeline branches are 60 percent, and no decode design touches them. If
the goal is a faster Biomarker page rather than a cleaner data flow, the largest single item is
`sliding_window_analytics` at 10.55 s, and it is not a decode problem at all.

---

## Reproducing every number above

All probes are read-only and live in `BRAVO/_agent_bridge/_sync_decode/`. Run through the bridge:

```
cd BRAVO/_agent_bridge
python3 bridge_client.py --cwd /usr/src/BRAVO --timeout 3600 --wait 3700 \
  "PYTHONPATH=/usr/src/BRAVO:/usr/src/BRAVO/modules python3 _agent_bridge/_sync_decode/<probe>.py \
   2e3c75c00d7f4f37b53a048d195f11da"
```

| Probe | Produces |
|---|---|
| `census_probe.py` | the 2,453 decode calls, 2,007 distinct files, 446 doubled, two rounds |
| `canon_attrib_probe.py` | the 72,425,865 normalisations attributed to their calling line |
| `stage_probe.py` | the wall-clock stage table, no profiler |
| `profile_probe.py` | the cProfile view, for comparison only — inflated, see §1 |
| `endpoint_census.py` | decode counts and seconds for all four endpoints, two rounds each |
| `attrib_endpoint.py` | which call sites decode one file three times |
| `dup_probe.py` | the two duplicated page load sites; `settings_stream` 3 × 31.87 s |
| `psdcache_probe.py` | the spectrum cache: 6,309 files, 0 reads during a page request |
| `ab_prototype.py` | the prototype timing and the 159,600-field equality comparison |
| `run_decode_tests.py` | `DECODECOMMON PASS=32 FAIL=0` |

**Container Biomarkers suite: `PASS=420 FAIL=0`**, read from a run at 10:53 UTC. My files add no
import to any existing module, so the count is the platform's own.
