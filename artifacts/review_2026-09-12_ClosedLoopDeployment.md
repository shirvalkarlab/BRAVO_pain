# Code review, 2026-09-12: the Closed-Loop Deployment module

**Read-only.** Every line number below was read from the working tree at commit `87db3b1a` on
2026-09-12 (`git status` clean at the start); re-grep before editing, because they move. Nothing was
run in the container and no suite was run. Two small read-only Python checks were run on the host
and are quoted where they matter. The test audit of this morning
(`artifacts/test_audit_2026-09-12_ClosedLoopDeployment.md`) is not repeated; its four hazards are
answered in their own section near the end.

## Summary

- **Critical: 0. High: 1. Medium: 5. Low: 6.** Plus a dead-code list that adds two names to the
  morning audit's list and confirms the rest.
- **The single most important finding (C1):** the page always tells the server the actuated side is
  "Left", and the server then reads the impedance, the artefact flags, the LFP amplitude bins, the
  capture amplitudes, the paused amplitude, the current-to-power slope (E1), the amplitude-to-pain
  slope (E3), the two capture currents and the simulation's amplitude series from the LEFT for any
  candidate, including a band picked on a RIGHT contact. Nothing on the page says so; the only
  symptom is a D39 "contralateral pairing" block whose sentence is wrong about why.
- Today's committed band is on the left (L 0-2+, 24.5 Hz), so every number the PI has watched live
  is unaffected. The first right-side band anyone picks on the "Choose a band" card will be judged
  on the wrong lead and the wrong stimulator, silently.
- The four hazards from this morning: 1 PARTLY (the ramp clip), 2 CONFIRMED (two rate floors),
  3 CONFIRMED (one-item stopping history, in Stim Optimizer), 4 CONFIRMED (the D26 row never fed).
- Two other things worth the PI's eye: the same three analysis packages are loaded twice into every
  server worker under two spellings (C4), and the D15 "this contact can be a control signal" pass is
  a statement about ONE_THREE_LEFT applied to every contact (C5).

Where things are, for a reader who has not opened the code: everything here is the **Closed-Loop
Deployment page** (`/reports/closed-loop/<participant>`). "The ledger" is the card titled
"Device rules · 51 checked". "The verdict" is the header at the top. "The triangle" is the evidence
panel with edges E1, E2, E3. "The three-source panel" is "Stimulation amplitude effects on band
power, measured three ways". "The simulation card" is "CL-DBS simulations" at the foot.

---

## C1. High. CONFIRMED. A right-side band is evaluated on the left side, and nothing says so.

**Where it lives.** Three places, all needed for the fix:

1. `Client/src/views/Reports/ClosedLoopSim/useDeploymentReport.js:20-38` builds the request:
   ```js
   Hemisphere: hemisphere || "Left",
   ...
   sensing_hemisphere: bc.sensingHemisphere || null,
   actuated_hemisphere: hemisphere || "Left",
   ```
   and `index.js:409-412` calls the hook with no `hemisphere` at all:
   ```js
   const deploymentReport = useDeploymentReport({
     participantUid: participant_uid,
     bandCandidate: reportCandidate,
   });
   ```
   So every request the page has ever sent carries `Hemisphere: "Left"` and
   `actuated_hemisphere: "Left"`, whatever side the band is on. Only `sensing_hemisphere` follows
   the band (`bc.hemisphere`, set by the grid card from the sweep's own side, decision 122).
2. `BRAVO/modules/ClosedLoopDeployment/bravo_service.py:114` passes that value straight through
   (`hemisphere=(request_data or {}).get("Hemisphere", DEFAULT_HEMISPHERE)`), and
   `adapter.py:2412-2413` builds the side used for the device facts as
   ```python
   _hemi = (cands[0] or {}).get("actuated_hemisphere") or (cands[0] or {}).get(
       "sensing_hemisphere") or hemisphere
   ```
   which resolves to "Left" for every candidate because `actuated_hemisphere` is always present.
3. `pipeline.py:119-122` takes `hemisphere="Left"` from the same request value and
   `pipeline.py:191` calls `E.therapy_edge(design_matrix)` with no amplitude column, so
   `edges.py:291` uses its default `amp_col="amp_mA_Left"` regardless.

**What goes wrong, concretely, for a candidate on `ZERO_THREE_RIGHT`** (any right contact):

| What | Read from | Line | Should be |
|---|---|---|---|
| D16 impedance | the LEFT lead's worst pair (7286 ohm) | `device_facts.py:377` `candidate_impedance_ohm(imp, hemisphere)` with `hemisphere=_hemi` | the RIGHT lead |
| D17 artefact flags | the LEFT `ZERO_AND_THREE_Left` survey | `device_facts.py:653`, `_match_survey_channel(art, channel, hemisphere)` filters on `hemi.lower() != "left"` and strips `_RIGHT` from the channel name (`:714`) | the RIGHT survey |
| D09 LFP bins | nothing (right bins never match "left", so "not determinable") | `session_report_facts.py:386` | the RIGHT bins |
| D24 / D27 / D28 capture amplitudes and limits | the LEFT newest capture | `device_facts.py:621` `S["capture_newest"].get(hemisphere)` | the RIGHT capture |
| D34 paused amplitude | 2.5 mA (Left) | `device_facts.py:368-369` | 2.0 mA (Right, stated) |
| E1 historical slope | right-contact power against LEFT current | `pipeline.py:175`, `edges.py:87` `resolve_setting_column(..., hemisphere)` | right current |
| E3 amplitude-to-pain | LEFT current always | `pipeline.py:191`, `edges.py:291` | the actuated side |
| capture currents, thresholds | LEFT `amp_mA_Left` | `pipeline.py:222-273` | the actuated side |
| simulation amplitude series | LEFT current record | `adapter.py:1974` `side = str(hemisphere).upper()` | right |
| D39 | fails: `sens="right"`, `act="left"`, so it is treated as a contralateral pairing and blocks on `dual_lead_implant`/`contralateral_pairing_acknowledged` being absent | `constraints.py:1127-1137` | passes (same side) |

The ledger's D39 row is the only visible sign, and its sentence ("contralateral pairing ... not
acknowledged") describes a configuration nobody asked for. The manifest KV "Hemisphere" on the
simulation card (`index.js:739`) would read "Left" under a right band, which a careful reader might
notice; nothing else on the page would.

**Why it has not shown.** The band the PI committed is L 0-2+ (decision 139), so `_hemi` and the
request value agree with the sensing side. No test runs `report_for_participant` or `pipeline.run`
with a right-side candidate end to end (grep of `tests/` for a right-side `pipeline.run`: none;
`test_bravo_service.py:81` only checks that a caller-supplied "Right" reaches the adapter).

**Fix, in order.**

1. `useDeploymentReport.js:23` and `:31`: derive the side from the candidate when the caller gives
   none: `const side = hemisphere || bc.sensingHemisphere || "Left";` then
   `Hemisphere: side` and `actuated_hemisphere: side`. Same in
   `useClosedLoopSimulation.js:20` (it reuses `deploymentReportBody`, so it follows). Rebuild the
   bundle and check the chunk carries the new literal (CLAUDE.md §8).
2. `bravo_service.py:110-115`: when the request carries no `Hemisphere`, take
   `Candidates[0].actuated_hemisphere or Candidates[0].sensing_hemisphere`, and only then
   `DEFAULT_HEMISPHERE`. Update `tests/test_bravo_service.py:70-78`, which pins the "Left" default
   when no candidate side is given, to pin "the candidate's side wins over the default".
3. `adapter.py:2412-2413`: split `_hemi` into two names. Facts about the SENSING lead (impedance,
   artefact flags, LFP bins) must use the sensing side
   (`sensing_hemisphere or actuated_hemisphere or hemisphere`, the order `_prog_hemi` already uses at
   `:2441-2442`). Facts about the STIMULATED side (capture amplitudes, adaptive limits, capture pulse
   width, paused amplitude) use the actuated side. `device_facts.facts_for_participant` takes one
   `hemisphere=`; give it two keyword arguments, `sensing_hemisphere=` and `actuated_hemisphere=`,
   and route `candidate_impedance_ohm`, `_match_survey_channel`, `candidate_lfp_bins` to the first
   and `capture_newest`, `paused_amplitude_mA_by_hemisphere` to the second.
4. `pipeline.py:191`: `e3 = E.therapy_edge(design_matrix, amp_col=adapter.canonical_amp_col(hemisphere))`.
5. `pipeline.py:119-122` and `adapter.py:2506-2508`: pass the candidate-derived side, not the raw
   request value, so the manifest, E1, the capture currents and the simulation all name the side the
   band is on.

**Test to add** (`tests/test_core.py`): build the calibrated frame `test_calibrated_join.py::_cal_frame`
already builds with BOTH `amp_mA_Left` and `amp_mA_Right` columns, give the right side a strongly
negative power-on-current slope and the left side a flat one, run `pipeline.run` with a candidate
`{"channel": "ZERO_THREE_RIGHT", "sensing_hemisphere": "Right", "actuated_hemisphere": "Right", ...}`
and assert `rep.edges["E1"].sign == -1` and `rep.manifest["hemisphere"] == "Right"`; and a
`device_facts` test asserting that with `sensing_hemisphere="Right"` the impedance fact comes from the
`Right` block of a constructed impedance recording and `artifact_flags` from the `..._Right` survey.

**Live check.** On RCS08 through the bridge, capture the report for the committed left band before
and after: expect 0 differences apart from timing fields (the fix must move nothing on a left band).
Then request `ZERO_THREE_RIGHT` at 24.5 Hz before and after and print, side by side: D16's observed
line (ohms and lead), D17's channel key, `manifest.hemisphere`, `threshold.capture_amp_low/high`,
`edges.E1.estimate`, and the D39 row's kind. Before: left values and a D39 block. After: right values
and D39 passing.

---

## C2. Medium. CONFIRMED. The D26 ledger row can never be evaluated (hazard 4).

**Where.** `constraints.py:826-836` `_p_d26` reads `candidate["predicted_recapture_alert"]`.
The only place that value is produced is `authority.py:294`, on the `ThresholdPlan`, which
`pipeline.py:268` builds AFTER `check_eligibility` has already run at `pipeline.py:204`.
`pipeline._facts_for` (`:57-116`) never sets the key, and `device_facts.py` never produces it
(grep: the name appears only in `constraints.py`, `authority.py`, `types.py:135`,
`adapter.py:1502`). Decision 139 already notes the row reads "not supplied".

**What the page shows.** Ledger, D26 row: "advisory, could not be determined from the inputs given",
forever, while the same request computes the alert and serialises it at `adapter.py:1502`
(`threshold.predicted_recapture_alert`) — a number the page does not display.

**Fix.** In `pipeline.run`, move the "Phase 1: device eligibility" block (`:195-209`) to after the
threshold placement block (`:236-273`), and in `_facts_for` add one parameter `threshold=None` that
sets `f["predicted_recapture_alert"] = bool(threshold.predicted_recapture_alert)` when the plan
carries a non-None value. Nothing in threshold placement reads the eligibility report, so the move
is safe; D19 still sees the edges because they are estimated first.

**Test.** `tests/test_constraints.py` (or `test_pooled_e1.py`): run `pipeline.run` on the calibrated
fixture with a `pooled_e1` row whose slope is negative and whose standard error makes the interval
exclude zero; assert the D26 row is absent from `advisories` (it passed and D26 is not in
`_RECORD_VALUE_ON_PASS`). Then with a slope whose interval spans zero, assert a D26 row of kind
`advisory_failed` exists and `rep.threshold.predicted_recapture_alert is True`.

**Live check.** RCS08 committed band: before, D26 kind `advisory_not_determinable`; after,
`advisory_failed` with the "not assessed"/"not established" sentence (there is no stored pooled slope
on L 0-2+ at 24.5 Hz, decision 139), and every other ledger row identical field for field.

---

## C3. Medium. CONFIRMED. Two rate floors, and the ledger has never been told the 55 Hz one (hazard 2).

**Where.** `constraints.py:125` `LOW_RATE_SOFT_FLOOR_HZ = 30.0` (D44, an advisory quoted from the
movement-disorder page). `StimOptimizer/routines/percept_adaptive.py:396`
`MIN_ADAPTIVE_RATE_HZ = 55.0` (PI-stated, "the machine doesn't work below that"), enforced on the
Stim Optimizer page by `stage1_openloop.py:652-718` (decision 138). D31 (`constraints.py:979-1042`)
is the rule that should carry the BrainSense minimum, and it reads
`participant["brainsense_min_rate_hz"]` (`:1028`), which nobody supplies: `PI_STATED_FACTS`
(`device_facts.py:226-287`) carries `deployment_rate_hz: 55.0` (`:269`), a different key that no
predicate reads.

**What goes wrong.** A candidate at 40 Hz on the Closed-Loop page: D44 passes (40 >= 30), D31 finds
no (40 Hz, pw) pair in `BRAINSENSE_PROGRAMMED_PAIRS` and returns None ("value not read off the
programmer", blocks). The Stim Optimizer page says the same rate is "below the 55 Hz adaptive
minimum". Two pages, two reasons, one platform. On the live committed band (55 Hz) both pass, so
nothing shows today.

**Fix.** `device_facts.py:226` block: add `"brainsense_min_rate_hz": 55.0` with provenance
"stated by PI (percept_adaptive.MIN_ADAPTIVE_RATE_HZ)", and import the value from
`StimOptimizer.routines.percept_adaptive` rather than retyping it, so there is one 55. `pipeline._participant_facts`
already routes it (`brainsense_min_rate_hz` is in `PARTICIPANT_KEYS`, `constraints.py:380`). Leave
D44 at 30 Hz; it is a different, documented rule.

**Test.** `test_constraints.py`: a candidate at 40 Hz with `sensing_hemisphere="Left"` and a
participant carrying `brainsense_min_rate_hz=55.0` gives `_p_d31` False (not None); at 55 Hz with
`pulse_width_us=100` it gives True through the pair table. **Live:** RCS08 committed band before and
after: D31 row unchanged (recorded_value, 55 Hz), 0 other differences.

---

## C4. Medium. CONFIRMED. Every analysis package is loaded twice into each server worker.

**Where.** `BRAVO/settings.py:45-47` appends `modules/` to `sys.path`, so `from Biomarkers import
bravo_service` and `from modules.Biomarkers import bravo_service` BOTH import — as two different
module objects. Verified on the host with both roots on the path:

```
ClosedLoopDeployment.types same object: False
CacheStore.store same object (aliased in __init__): True
Biomarkers.routines.sweep_settings same object: False
```

`CacheStore/__init__.py:19-24` and `DecodeCommon/__init__.py:29-31` alias the two spellings on
purpose (decision 39). `Biomarkers/__init__.py`, `ClosedLoopDeployment/__init__.py` and
`StimOptimizer/__init__.py` do not. This module uses both spellings: bare at `adapter.py:35`
(the package importing itself), `:1935-1936`, `three_source_response.py:98, :1200-1201`,
`clinic_steps.py:71`, `stability.py:72` (bare tried first), `authority.py:47`; `modules.` at
`adapter.py:538, :863, :1640, :2355, :2557, :2693` and `bravo_service.py:41`. The view imports the
`modules.` spelling (`Server/APIs/DataAnalysis.py:924`).

**What it costs.** `Biomarkers.bravo_service` keeps in-process memos at module level
(`_RAW_LSB_CACHE_MEMO` at `bravo_service.py:794`, up to 8 tile entries; the availability and
recording-set memos of decision 130; the pain-report hold of decision 78). The Closed-Loop report
reaches the tile cache through the BARE copy (`three_source_response.py:1200`, `adapter.py:1935`)
while the Biomarkers page and Stim Optimizer reach it through the `modules.` copy. After both pages
have been visited, each of the four workers holds the participant's tile entry twice (the entry is
245.90 MB on disk). Every module-level switch also exists twice (`store.ENABLED` is safe because
CacheStore is aliased; Biomarkers' own flags such as the launcher guard of decision 107 and
`USE_CHANNEL_INDEX` are not), which is the "monkeypatch target under the package's second import
spelling" decision 125 met in a test.

**Fix.** Add the same aliasing block CacheStore uses to `Biomarkers/__init__.py`,
`ClosedLoopDeployment/__init__.py` and `StimOptimizer/__init__.py` (register the package under the
other spelling in `sys.modules` at import; submodules resolve through the package's `__path__`, so
for these packages the package-level alias is enough — verify with the three-line host check above,
which should print `True` three times after the change). Then `settings.py:23-31`'s note should say
the two spellings are one object.

**Live check.** In one `manage.py shell` in the container: import both spellings of
`Biomarkers.bravo_service` and assert `is`; then `len(bs._RAW_LSB_CACHE_MEMO)` after one Closed-Loop
report and one Biomarkers page request through the same process should be 1, not 2. Report the
resident set size of one worker before and after a Closed-Loop report (`/proc/<pid>/status VmRSS`),
alternating rounds.

---

## C5. Medium. CONFIRMED. D15 passes every contact on a statement about one.

**Where.** `device_facts.py:277-279`:
```python
"channel_is_brainsense_setup_channel": True,
```
in `PI_STATED_FACTS["2e3c…"]`, with the comment "CONFIRMED against the record ...: ONE_THREE_LEFT
appears as a configured sensing channel". `facts_for_participant` (`:371-373`) copies every stated
fact into `out` for whatever `channel=` it was called with, and `_p_d15` (`constraints.py:657-666`)
just returns the flag. The `channel` argument is never consulted for this rule. The record can
answer it: the stored summary already carries per-contact counts of groups with that contact as a
`SensingChannel` (`session_report_facts.py:184-210`, key `sensing_channels`; the committed
`_facts_RCS08.json` reads `ZERO_TWO_LEFT: 626, ZERO_THREE_RIGHT: 21975, ...`), and nothing reads them
for D15.

**What goes wrong.** On RCS08 today all six grid contacts appear in the record, so the pass is right
by luck and its provenance is wrong ("stated by PI 2026-09-04" on the ledger row for a contact the
PI never named). A contact that had never been configured for sensing would still pass.

**Fix.** In `session_report_facts_for` (`device_facts.py:589`), after the D17 block, derive
`out["channel_is_brainsense_setup_channel"] = count > 0` from `S["sensing_channels"]` for the
requested channel (match the spelling the way `_match_survey_channel` does: strip `_AND_` and the
side, then the side must agree), with provenance "measured: N groups carried this contact as a
SensingChannel". Delete the stated line at `:279`, or keep it and let the measured value win by
placing the derived facts before the stated copy for this key. Keep None when the summary has no
`sensing_channels` block.

**Test.** A summary fixture with `sensing_channels={"ZERO_THREE_LEFT": 5}`: channel
`ZERO_THREE_LEFT` gives True, `ONE_THREE_RIGHT` gives False, an empty summary gives no key. **Live:**
RCS08 committed band, D15 row before and after: same kind, provenance string changes from "stated" to
"measured: 626 groups", 0 other differences.

---

## C6. Medium. CONFIRMED by reading. E1 and the D26 verdicts are read from the pooled table BEFORE the same request rewrites it.

**Where.** `adapter.py:2496-2501` reads the pooled row (`pooled_shape_if_stored`, newest entry of
any key) and hands it to `pipeline.run` at `:2506`; the request then builds the three-source
comparison (`:2642`) and writes the pooled table at `:2767` (`write_pooled_shape`); the simulation at
`:2800` reads the table again (`write_simulation`, `adapter.py:2116`) and gets the NEW one.

**What goes wrong.** On the first request after a new ingest that adds a run of rising current (a
clinic visit), the triangle's E1 and the two D26 warnings come from the previous table (or none, on
a first-ever build), while the simulation card on the same page uses the new one. The page caches
the whole response until Recompute (`useCachedResult`), so the stale E1 persists. No value is
wrong; two panels on one page disagree about which table they read and the note does not say so.

**Fix.** Move the three-source block (`:2614-2656`) and the `write_pooled_shape` /
`write_run_points` calls (`:2766-2794`) above the `_pooled_e1` read at `:2495`, so the pipeline
reads the table this request wrote. `report_to_dict` is called after `_pl.run`, so the only
reordering is inside `report_for_participant`. If the builder prefers not to reorder, re-read the
row after `write_pooled_shape` and, when it differs from `_pooled_e1`, re-run `_pl.run` (it costs
about 0.05 s, `adapter.py:351`) and rebuild `out` from it.

**Live check.** Delete RCS08's `within_visit_pooled_shape` entry through the bridge (its own
override root, never `store.clear()` — decision 129), run the report once: before the fix
`edges.E1.cluster_unit` is "setting epoch" and `threshold.capture_verdicts.assessed` is False while
`within_visit_pooled_shape.written` is True; after the fix E1 is the pooled unit on the same request.
Then a second run: 0 differences from the first apart from timing.

---

## C7. Low. CONFIRMED. Three failures still reach the page as "normal" without a log line.

- `adapter.py:645-656`: the read of the stored stability grid (`STABILITY_GRID_KIND`) —
  `except Exception: stored_stability = {}`. On failure every row of the "Choose a band" card's
  stability column shows the dashed "not tested", indistinguishable from "the background job has not
  run yet", and `cross_setting_stability_from_store` reads 0. The guard test
  (`tests/test_report_contract.py:241-287`) skips this handler because it says nothing and does not
  name `_amp_stored`.
- `adapter.py:858` and `:870` (`_inputs_provenance`): a failed chain read or a failed tile-key
  build drops an input from the `inputs` entry's provenance silently. A shorter chain is what
  lets the self-derived refusal miss (CLAUDE.md §10 rule 6).
- `adapter.py:2140` (`write_simulation`): the pooled table's chain is dropped from the simulation's
  provenance silently, same consequence.
- `adapter.py:2030` (`_run_windows_epoch_s`): a run whose local window string cannot be parsed
  (the ambiguous hour of a daylight-saving change is one way) is dropped from the simulation's run
  windows with no trace.

**Fix.** `_log.warning(..., exc_info=True)` in each; extend the guard at
`test_report_contract.py:283-284` to also flag a silent handler whose body assigns `stored_stability`.

---

## C8. Low. CONFIRMED. The same recordings are decoded twice on one request.

**Where.** `three_source_response.build_for_participant` (`:1200-1231`) calls
`bs._load_recordings` for the power-domain, time-domain and PSD families and builds the tile cache
memo; `adapter.simulation_inputs_for_participant` (`:1942-1949`) does the identical five calls again
on the same request whenever the simulation is not already stored (`write_simulation`, `:2102-2110`).
`_load_recordings` (`Biomarkers/bravo_service.py:370`) decodes from disk on every call; only the
tile cache is memoised, and it is memoised in the BARE copy (C4). Decision 77 measured the
time-domain load at 1.27 s and the PSD load at 0.38 s, so about 1.7 s of decoding is repeated per
report that writes a simulation, plus the event and montage PSD block builds.

**Fix.** Have `build_for_participant` return the loaded `power`, `td`, `psd` and `cache` in its
payload under underscore keys (or a second return value), and pass them into
`simulation_inputs_for_participant` as optional arguments. Measure in alternating rounds on RCS08
with the simulation entry deleted before each run; the field-count comparison of the two payloads
must be 0 differences apart from `seconds`.

---

## C9. Low. PLAUSIBLE. The epoch assignment ignores the open-ended last epoch, and the simulation has its own copy with a different boundary rule.

**Where.** `adapter.py:111-134` `_assign_epoch` uses `(t >= a) & (t < b)` and treats `b` as
finite always; `StimOptimizer/adapter.py:357-361` sets the last epoch's `t_end` to the last
settings observation and marks it `open_ended`, and its own `attach_pros` (`:404-415`) extends that
epoch to +inf for exactly this reason. So any tile recorded after the newest export's session time
falls in no epoch (index -1) and gets no amplitude. `adapter.py:1992-2007` (the simulation's
amplitude lookup) re-implements the same assignment with `t <= ee[k]` (closed at the end, where
`_assign_epoch` is half-open) and without the nanosecond cast `_assign_epoch` documents at
`:121-130`. `reliable_change.short_gap_pairwise_sd` (`reliable_change.py:130`) has the same
`t < ends[i]` cut.

**Why it is only plausible.** The settings stream's time is each export's `SessionDate`
(`StimOptimizer/adapter.py:256-266`), and the recordings inside an export precede it, so on the
steady state the uncovered tail is at most the recordings that arrive between exports. Not measured.

**Fix.** Make `_assign_epoch` read `epochs["open_ended"]` and use `t >= a` for that row; delete the
copy at `adapter.py:1992-2007` and call `_assign_epoch` there. **Measure first:** on RCS08 count the
joined-table rows with `setting_epoch == -1` whose `t` exceeds the last `t_start`; if the count is
0 the fix is a tidy-up with a 0-difference proof; if not, it is the number of tiles the report and
the simulation have been discarding.

---

## C10. Low. CONFIRMED. Device constants and two "which files are session reports" rules are written more than once.

- `CAPTURE_ARTEFACT_AMP_MA = 5.0` / `CAPTURE_ARTEFACT_PW_US = 120.0` in `constraints.py:120-121`,
  `authority.py:54-55` and `session_report_facts.py:46-47` (`CAPTURE_AMP_CEILING_MA`,
  `CAPTURE_PW_CEILING_US`). Three literals for one rule; `authority.py:36-49` explains why this exact
  shape drifted once before (0.5 against 1.0). Fix: import from `constraints` in the two others
  (`authority` can, `constraints` imports `device_facts` not `authority`; `session_report_facts` is
  imported by `device_facts`, which `constraints` imports — so put the two numbers in
  `session_report_facts` and have `constraints` and `authority` import them, which follows the
  existing direction).
- `session_report_facts.is_session_report` (`:405-407`) and the inline `"Session" in (s.name or "")`
  at `device_facts.py:930`. One rule, two spellings.
- "newest session report": `session_report_facts.newest_by_stamp` (`:444-449`, by the date token in
  the name) and `device_facts.py:933` (`max(sfs, key=lambda s: s.date or 0)`, by `SourceFile.date`,
  which `DataCurator.py:369` sets to the session timestamp). They agree today; nothing pins that.
- `_p_d27` in `constraints.py:839-870` and the D27 check in `authority.threshold_placement`
  (`:256-266`) test the same ceiling on different amplitudes: the ledger reads the device's newest
  capture (3.0 mA, decision 136) while the pipeline reads the highest current ever delivered
  (4.8 mA, decision 139). At 5.5 mA delivered the pipeline would BLOCK on "D27" while the ledger's
  D27 row passes. Either rename the pipeline's sentence so it does not cite D27, or feed it the
  same capture amplitude.

---

## C11. Low. CONFIRMED. Two small contract gaps in the rule table.

- `constraints.py:271-367` `CANDIDATE_KEYS` says "Every candidate key any predicate reads", and
  `_p_d09` reads `lfp_bins_uvp` (`:582`) and `_p_d27` reads `capture_pulse_width_us` (`:862`);
  neither is listed. A caller reading the list to see what to declare will not see them.
- `device_facts.py:139-140`: `lead_type` is taken from the LEFT lead's `LeadModel` for both sides,
  so D16's short-circuit limit (250 or 350 ohm, `constraints.py:115`) is the left lead's whichever
  side is being judged. Same leads on RCS08; a per-side value costs one line.

---

## C12. Low. CONFIRMED. A record with one therapeutic current gives no thresholds and no blocker.

`pipeline.py:266-273`: when `hi_a > lo_a` is false (one nonzero current ever delivered on that
contact and centre) the threshold block is skipped and nothing is appended to `rep.blockers`;
`types.DeploymentReport.is_licensed` (`:226-249`) does not require a threshold, so with a stored
pooled slope (E1 resolved from the titration runs) such a report could read "supported" with no
prescription. Not reachable on RCS08 (many currents). Fix: append a blocker naming the single
current, the way `:261-263` does for no nonzero current. Test: a frame with one nonzero amplitude
gives `rep.threshold is None` and a blocker.

---

## The four known hazards

**1. The ramp clip of commit `790ed21` is not wired — PARTLY.**
`three_source_response.py:844-847` calls `mean_power_before_next_change` without `ramp_end_t`, and
`ramp_windows_from_amplitude` (`within_visit.py:122`) has no caller outside tests (grep). But the
device-derived ladder's `t0` is already the last increment of each move
(`three_source_response.py:664-666`, `"t0": float(t[e])` with `e` the move end), and the window is
clipped at `max(t_end - 30, t0)` (`within_visit.py:1136`), so it cannot reach into the ramp. What is
missing is only the 20 s post-ramp margin (`RAMP_EXCLUDE_S = 20.0`, `within_visit.py:67`) that the
clip adds. Fix: pass `ramp_end_t=steps["t0"].to_numpy(dtype=float)` and
`ramp_margin_s=within_visit.RAMP_EXCLUDE_S` at `:844-847`, bump `run_points.RULE_VERSION`,
`amplitude_effect.RULE_VERSION` and `POOLED_RULE_VERSION`, and report the field count and
difference count on RCS08's 3,017 per-run points rows (decision 125) before and after — that number
is the answer to whether the margin matters on this record.

**2. Two rate floors — CONFIRMED.** See C3 for lines and fix.

**3. A one-item stopping history — CONFIRMED (Stim Optimizer, out of this module's scope).**
`StimOptimizer/pipeline.py:268` `ACQ.check_stopping([m["mu_star"]], ...)`; `acquisition.py:286-293`
computes gains over consecutive history entries, so with one entry `plateau` is False and the
plateau, stop and ceiling branches cannot fire. For the Stim Optimizer reviewer.

**4. The D26 row never fed — CONFIRMED.** See C2.

---

## Dead code (category F), each with zero non-test callers by grep across `modules/` and `Server/`

Confirms the morning audit and adds two names. None is protected by a decision; decisions 100 and
101 say explicitly that the zero-caller functions were "NOT deleted" pending the PI's call, so this
is a list to decide on, not a change.

- `adapter.amplitude_response_cached` (`:975`), `_remember_response`, `response_cache_stats`
  (`:1051`), `clear_response_cache` (`:1060`), `clinic_steps_signature` (`:934`, one caller: the
  function above), `_tiles_signature` (`:954`) and the `"response"` store kind (`_SHARED_KINDS`,
  `:449`). Decisions 85, 100, 101 name the path as uncalled.
- `adapter.inputs_cache_stats` (`:882`), `clear_inputs_cache` (`:889`): 0 callers (new to this list).
- `session_report_facts.programmed_pairs_table` (`:358`): 0 callers (new to this list).
- `edges.max_statistic_permutation` (`:333`), `clinic_steps.settled_window` (`:130`),
  `stability.assess_band_stability` (`:276`), `registry.py` whole file (decision 109 records "no
  code imports registry.py").
- `prescription.duty_cycle` is computed and serialised (`adapter.py:1453-1463`) and shown nowhere
  since decision 128 removed the card; live, not dead, and not flagged.

Not dead and not to touch: `LSB_RULE_OF_THUMB` / `LFP_POWER_LSB_TO_UV2` (`constraints.py:161`,
CLAUDE.md §2.4), the pre-2026-09-05 `log_psd` branch of `joined_table` (`adapter.py:1118-1160`,
"still accepted", the audit's "kept on purpose" list).

---

## Checked and NOT flagged, with the decision that explains each

- D16 judged on the newest fixed-current test with the automatic reading printed beside it:
  decision 133. One reading worth the PI's eye but not a defect: the sentence at
  `constraints.py:1350-1354` says any future automatic-mode reading above 10 kilohm was "ruled a
  spurious fail ... by the principal investigator on 2026-09-12", which generalises a ruling made on
  one pair of readings to every future one.
- D19 passes on the point sign with the interval printed: decision 134 (`pipeline.py:71-81`).
- D30 derived from the device's active sensing group, read live from the newest report rather than
  the summary: decision 135 (`device_facts.py:916-941`, `adapter.py:2463-2491`).
- D26 verdicts warn and do not block; `is_licensed` ignores `warnings`: decision 139
  (`types.py:234-241`, `pipeline.py:359-365`).
- The session-report summary resolver (current / stale / committed, rebuild in the background):
  decision 136 (`device_facts.py:525-586`). Read carefully: "current" is granted only when the
  stored key equals the participant's file-set key (`:554-560`); a stale summary is always labelled
  and never served as current.
- The stated-facts block (`device_facts.py:226-287`): PI decisions of 2026-09-04/05, with provenance
  on every row.
- The pooled table and per-run points read as "newest of any key" (`load_newest`): decision 103 and
  decision 41's pattern; the current-key check before building (`:1774-1785`, `:1866-1881`) is what
  keeps it fresh.
- The grid card matched on the Biomarkers page's settings tag and built on demand when nothing
  matches: decision 131.
- The `"response"` kind written with no `provenance=`: decision 101 says deliberate, no production
  caller.
- D28 no longer testing the zero lower limit (D07 owns it): `constraints.py:881-892`, 2026-09-04.
- D01 deferring to D02 and the deferral mechanism: `constraints.py:2444-2566`; the safety property
  ("deferral can never turn a blocked configuration into a supported one") holds by reading —
  a row is set aside only when its owner reached an adverse kind.
- Verdict aggregation: no path lets an advisory block or demotes a blocker
  (`constraints.py:2631-2651` advisories never enter `failures`/`unknowns`; `types.py:243-249`).
- The hemisphere-correct half of the report — `_prog_hemi` for D27/D31's programmed rate and pulse
  width prefers the sensing side (`adapter.py:2440-2445`), decision 132 — is right and is the
  pattern C1's fix should copy.
- The `every-return-path carries cache_status` and `handler reports its own key` guards
  (`tests/test_report_contract.py`): decisions 100, 101; still true by reading of
  `report_for_participant`'s three returns.
- `_p_d09` passing on any bin inside the band: PI decision 2026-09-04 (`constraints.py:1629-1636`).
- The `simulation_if_stored` match on the sidecar's candidate tag: decision 128 (the
  decision-107 defect met and fixed).
- `pipeline.py:133-137` deriving a pain frame from the design matrix when none is given, and
  `:138-147` adding the candidate's own centre to the grid: both explained in place.
