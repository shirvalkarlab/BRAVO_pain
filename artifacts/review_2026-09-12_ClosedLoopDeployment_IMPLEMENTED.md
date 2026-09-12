# The 2026-09-12 Closed-Loop Deployment review, implemented

**Written 2026-09-12, on branch `PS_closedloop_deployment`, uncommitted (the orchestrator commits).**
This answers `artifacts/review_2026-09-12_ClosedLoopDeployment.md` finding by finding. Every number
below was measured today on RCS08 (`2e3c75c00d7f4f37b53a048d195f11da`) through the bridge, with the
report captured before any edit and again after each group of fixes; the captures are the
`rv_*.pkl` files in `BRAVO/_agent_bridge/_probe_tl/` (gitignored). Where two captures are compared,
the count is fields compared / fields differing / fields on one side only, never a tolerance; the
timing fields (`seconds`, `_utc`, `last_built` and the like) are excluded by name and counted
separately.

Everything here is the **Closed-Loop Deployment page** (`/reports/closed-loop/<participant>`).
"The ledger" is the card "Device rules · 51 checked"; "the triangle" is the evidence panel with edges
E1, E2, E3; "the three-source panel" is "Stimulation amplitude effects on band power, measured three
ways"; "the simulation card" is "CL-DBS simulations".

Not done, by instruction: **C4** (the analysis packages loaded twice under two spellings) is
scheduled separately. Nothing under `StimOptimizer/` was edited.

---

## The two suites, both green

Run after the last edit, both in one bridge job (`run_both_suites.sh`), verbatim:

```
host:      1106 passed, 43 skipped, 0 failed, 0 errors  [parallel: 1105 passed, 43 skipped in 9.95s | store, serial: 1 passed, 1148 deselected in 0.41s]
container: PASS=630 FAIL=0 LIVE_SKIPPED=6
```

The brief's baseline was host 1073 / 42 / 0 and container 598. This module adds 22 tests (18 in a
new file, `tests/test_review_2026_09_12_sides_and_ledger.py`, plus one each in `test_bravo_service.py`
and `test_report_contract.py` and two in `test_three_source_response.py`); the other 11 host tests and
all 32 container tests above the baseline come from the Biomarkers and Stim Optimizer builders working
in the same checkout at the same time, whose files this work did not touch. The one new skip is the
behaviour half of the C8 test, which needs a configured Django and skips on a runner without one (its
source assertions still run, and the live proof below covers the behaviour). Three existing tests were
updated to pin new wording, none deleted: `test_bravo_service.py` (the default side now applies only
when the candidate names none), and the two tests that pinned the pipeline's "D27:" sentence
(`test_core.py`, `test_d26_reads_pooled_slope.py`; see C10).

## The frontend

Two files under `Client/src/views/Reports/ClosedLoopSim/` changed (`useDeploymentReport.js`,
`useClosedLoopSimulation.js`); the bundle was rebuilt and the rebuilt files are part of this change.
The chunk that carries it is **`Client/build/static/js/554.6e2bc640.chunk.js`** (it contains the
compiled side rule `return n||(t||{}).sensingHemisphere||"Left"` and `actuated_hemisphere:o`); the
old chunk `554.cb19acbb.chunk.js` is gone. Neither touched file appears in the build's warnings.
The gunicorn workers were reloaded (`kill -HUP 1`) after the Python edits.

**Not watched in a browser**: this session is not signed in and typing a credential is a hard
limit. The right-side check below was made through the service the page calls, with the exact
request body the rebuilt page now sends.

---

## C1 (High) — a band on a right contact was judged on the left lead and the left stimulator

**What changed.**

- `Client/src/views/Reports/ClosedLoopSim/useDeploymentReport.js`: a new `reportSide()` -- the
  caller's side, else the band's own sensing side, else "Left" -- used for both `Hemisphere` and
  `actuated_hemisphere`. Before this, both were hard-wired to "Left" because the page never passes a
  side. `useClosedLoopSimulation.js` keys its cache slot on the same rule.
- `ClosedLoopDeployment/bravo_service.py`: `request_hemisphere()` -- the request's `Hemisphere`,
  else the first candidate's actuated side, else its sensing side, else the default. Used for the
  report and for the stored-simulation read.
- `ClosedLoopDeployment/adapter.py` (`report_for_participant`): the one `_hemi` is now two,
  `_sens_hemi` and `_act_hemi`; facts about the sensing lead go to the first, facts about the
  stimulated side to the second, and `hemisphere` (what the pipeline, the prescription and the
  simulation receive) is the actuated side derived from the candidate, with the request's value only
  a fallback. The programmed rate/pulse-width lookup now reads the same `_sens_hemi`.
- `ClosedLoopDeployment/device_facts.py`: `facts_for_participant` and `session_report_facts_for`
  take `sensing_hemisphere=` and `actuated_hemisphere=` (`hemisphere=` still fills whichever is not
  given). Impedance, lead family, artefact flags, LFP bins and the D15 count read the sensing side;
  capture amplitudes, adaptive limits, capture pulse width and paused amplitude read the actuated side.
- `ClosedLoopDeployment/pipeline.py`: the side is derived from the candidate before the manifest
  is written; E3 regresses pain on the actuated side's current column (`therapy_edge(...,
  amp_col=...)`) instead of always the left one.

**Tests (all assert values).** A joined table with both sides' currents where only the right one
moves the power: a right-side candidate gets E1 sign −1 resolved, manifest "Right", capture currents
1.0 to 4.5 mA (the right stimulator's range) and E3 sign −1; the same table read for a left candidate
gets the left range 2.0 to 2.2 mA. Device facts with a constructed impedance record (left worst 7286
ohm on a SenSight lead, right worst 4100 ohm on a 1x4 lead) and a constructed summary: asked about
`ZERO_THREE_RIGHT` on the right, the impedance is 4100, the lead type "1x4", the artefact flags
`["SQC_ARTIFACT_PRESENT"]` from the `ZERO_AND_THREE_Right` survey, the bins the right survey's, the
capture 1.5 to 2.5 mA at 160 us and the paused amplitude 2.0 mA; asked about the left, every one of
those is the left's. A contralateral pairing (sensing Right, actuated Left) reads the right lead and the
left stimulator. The service test pins that a candidate naming only its side is evaluated on that side.

**Live, the committed left band (L 0-2+, 24.5 Hz), before any edit against after this group (C1
with C2, C3, C5, C10, C11 -- they share `device_facts.py`):** 58,599 fields before, 58,601 after,
58,599 in common, **4 differing, 2 only-after**, every one named and owned by another finding:

| field | before | after | finding |
|---|---|---|---|
| `eligibility.advisories.D26.observed` | empty | the D26 sentence (see C2) | C2 |
| `eligibility.advisories.D31.observed` | "BrainSense minimum rate of None Hz" | "of 55.0 Hz" | C3 |
| `device_facts_provenance.channel_is_brainsense_setup_channel` | "stated by PI 2026-09-04" | "measured: 626 groups carried ZERO_TWO_LEFT as a SensingChannel on the Left side" | C5 |
| `device_facts_provenance.lead_type` | "measured: LeadModel LEAD_B33015" | "... on the Left lead" | C11 |
| `device_facts.brainsense_min_rate_hz`, its provenance | absent | 55.0 | C3 |

So the C1 change itself moved nothing on the left band, as the review required.

**Live, `ZERO_THREE_RIGHT` at 24.5 Hz, the request the page used to send (`Hemisphere: Left`,
`actuated_hemisphere: Left`) against the one it now sends (both "Right"):**

| what | before (old page request) | after (new page request) |
|---|---|---|
| D16 observed | impedance **7286.0** ohm (the LEFT lead's worst pair) | impedance **5034.0** ohm (the RIGHT lead's) |
| D17 channel key | `ZERO_AND_THREE_Left`: 12 of 108 surveys flag an artefact | `ZERO_AND_THREE_Right`: 30 of 105 |
| D09 (LFP bins) | the LEFT survey: largest 0.81 uVp in 22-27 Hz | the RIGHT survey: largest 0.56 uVp |
| `manifest.hemisphere` | Left | **Right** |
| `threshold.capture_amp_low / high` | 1.0 / 4.8 mA (the LEFT stimulator's range) | 1.0 / **4.5** mA (the right's) |
| `edges.E3.estimate` (n) | −0.1543 (90) on the LEFT current | −0.1918 (91) on the right current |
| `edges.E1.estimate` | 10.8331 | 10.8331 (the pooled slope was already keyed on the contact) |
| D34 paused amplitude | 2.5 mA (Left) | 2.0 mA (Right) |
| D39 | unknown, "contralateral pairing ... not acknowledged" | **passes** (same side), row absent |
| D27 | passed (the LEFT capture, 100 us) | **fails**: the right side's newest capture is at 150 us, above the 120 us ceiling |
| verdict | blocked | blocked |

Whole-response count for that pair: 58,624 fields before, 58,622 after, 58,612 in common, 12 only-
before, 10 only-after, **489 non-timing differences**, all in the threshold, replay, prescription,
protocol and E3 blocks that follow the current column, plus the 36 LFP bins and the ledger rows named
above. **The D27 failure is a real finding for the PI**: on RCS08 the device's own newest capture on
the right runs at 150 us (decision 136 already recorded 100 us Left / 150 us Right), so any right-side
band fails D27 on the device's own record; the old page passed it by reading the left capture.

## C2 (Medium) — the D26 row is fed from the threshold plan

**What changed.** `pipeline.py`: the eligibility check moved after threshold placement, and
`_facts_for(..., threshold=)` fills `predicted_recapture_alert` from the plan and
`predicted_recapture_alert_reason` from the plan's own verdict sentences. `constraints.py` gained an
observed-values line for D26 (`_o_d26`) and lists both keys in `CANDIDATE_KEYS`.

**One correction to the review's expectation.** On the committed band the plan IS placed but no
pooled titration slope is stored (decision 139), and `authority.threshold_placement` then reports the
alert as None -- its own rule, "a prediction made from no number would be a fabrication". So the row
stays `advisory_not_determinable` there, and now SAYS why. Live, committed band, before: D26 observed
empty. After: "a threshold plan was placed, but the alert could not be predicted from it: D26
inverted capture: not assessed -- no pooled titration slope is stored for this band ...". On the right
band, which has a pooled slope: `advisory_not_determinable` -> **`advisory_failed`**, with "a
RECAPTURE THRESHOLDS alert IS predicted from the threshold plan placed for this candidate: ...".

**Tests.** An established negative pooled slope: no alert, no D26 row (D26 is not recorded on
pass); a slope whose interval spans zero: `advisory_failed`, `predicted_recapture_alert is True`, the
sentence carries "not yet established"; a plan with no pooled slope: not determinable with "a
threshold plan was placed, but ..."; no plan at all (no therapeutic current): not determinable with
"no threshold plan was placed".

## C3 (Medium) — one 55 Hz

**What changed.** `device_facts.py` imports `MIN_ADAPTIVE_RATE_HZ` from
`StimOptimizer.routines.percept_adaptive` (both spellings) and puts it in the stated-facts block as
`brainsense_min_rate_hz`, provenance naming the constant; `pipeline._participant_facts` already routes
it to the participant dict D31 reads. D44's 30 Hz is untouched.

**Test.** The stated value is the imported constant and equals 55.0; 40 Hz on the left is now
**False** (below the minimum, never demonstrated), where without the minimum it was None; 55 Hz at
100 us on the left is True through the pair table. **Live**: the committed band's D31 row keeps its
kind (`recorded_value`, 55 Hz); only its observed line gained "minimum rate of 55.0 Hz".

## C5 (Medium) — D15 measured per contact

**What changed.** `device_facts.session_report_facts_for` derives
`channel_is_brainsense_setup_channel` from the summary's `sensing_channels` counts through a new pure
`setup_channel_count(mapping, channel, side)`: sided keys whose pair matches and whose side agrees
are summed; sideless keys (`ZERO_AND_THREE`) are not attributed to a side; no `sensing_channels`
block means no key (not determinable, never a pass). The stated `True` is deleted from
`PI_STATED_FACTS` with a note saying why.

**Test.** `ZERO_THREE_LEFT` with 5 sided groups: True, "measured: 5 groups ..."; `ONE_THREE_RIGHT`
with none: **False**; the sideless 100 is never counted; an empty summary yields no key. **Live**:
committed band, same kind (passed, unrecorded); provenance "stated by PI 2026-09-04" ->
"measured: 626 groups carried ZERO_TWO_LEFT as a SensingChannel on the Left side"; the right band
reads 21,975 groups.

## C6 (Medium) — E1 and the D26 verdicts read the table this request wrote

**What changed.** `adapter.report_for_participant`: the three-source build, the pooled-table write
and the per-run points write now run BEFORE the pooled row is read for the pipeline; their payloads
gather in `_pre` and are copied onto `out` once it exists. The response-contract guards
(`test_report_contract.py`) were extended to hold `_pre[...]` handlers to the same rules as
`out[...]`, and a new test pins that `_pre` reaches `out` and that the write precedes the read in
source order. Also: the simulation's store key now carries the pooled table's rule version, so a
simulation built from an old table is never served after the table's rule changes.

**Live.** The stored pooled-shape entry was removed (one kind only, `store.clear(kind=...)`, never a
whole-store clear) and the right band requested once: the same response reports
`within_visit_pooled_shape.written True, 294 rows`, and its E1 is 13.440865950443092 over 11 points
in 6 runs, **equal to the slope in the row that request had just stored** (13.440865950443092, n 11,
n_visits 6), and the two capture verdicts read as assessed. Before the reorder that request would
have read the previous table (or none) for E1 while the simulation card used the new one. A repeat
request on the committed band: 58,010 fields, 12 non-timing differences, every one a served-from-store
bookkeeping field (`written`, `n_rows`, `store_key`, `served_from_store`).

## C7 (Low) — four silent handlers now log

`adapter.py`: the stored stability-grid read (`band_sweep_grid_for_closed_loop`), the two chain
reads in `_inputs_provenance`, the pooled-chain read in `write_simulation` and the unparseable
run-window in `_run_windows_epoch_s` all log a warning with the traceback. The guard in
`test_report_contract.py` now also flags a silent handler that assigns `stored_stability`.

## C9 (Low) — measured first, then fixed

**Measured on RCS08 before any change**: 123 exposure epochs, one open-ended; last `t_start`
2026-09-03 20:07 UTC, last `t_end` 2026-09-11 17:30:53 UTC; newest spectrum 2026-09-11 17:30:04
UTC. Of **304,488** spectrum rows, **0** fell in no epoch; of **5,430,456** joined-table rows, **0**
had `setting_epoch == -1`. So on this record the report and the simulation had discarded nothing;
the fix is a tidy-up with a 0-difference proof. `_assign_epoch` now extends an `open_ended` epoch to
+inf (`t >= t_start`); the simulation's private copy (closed end, no nanosecond cast) is deleted and it
calls `_assign_epoch`. Tests: a sample past the last export belongs to the open epoch, not with the
column absent or False; the simulation's source calls `_assign_epoch` and has no `searchsorted(es`
left. The reliable-change floor's own `t < ends[i]` cut (`reliable_change.py:131`) is not changed: it
receives plain arrays with no open-ended flag, and the review's fix instruction did not cover it.

## C10 (Low) — one home for each rule

- The two capture ceilings (5.0 mA, 120 us) live only in `session_report_facts`; `constraints`
  imports them under its old names and `authority` imports them from `constraints`. A test asserts
  the three names are one object.
- `active_sensing_group_facts` uses `session_report_facts.session_report_files` and
  `newest_by_stamp` instead of an inline `"Session" in name` and a by-date `max`. Live: the D30 row
  is unchanged.
- The pipeline's two ceiling sentences no longer begin "D27:"; they name the PROPOSED capture
  amplitude ("the proposed upper capture amplitude of 6.00 mA (the highest therapeutic current on
  record for this cell) exceeds the 5.0 mA artefact ceiling ...") and say that the ledger's D27 row
  judges the device's own newest capture, a different amplitude. The two tests that pinned "D27" in
  those sentences were updated to pin the new wording and that the sentences still block.

## C11 (Low) — the rule table's contract, and the lead family per side

`CANDIDATE_KEYS` now lists `lfp_bins_uvp` (D09) and `capture_pulse_width_us` (D27), plus the two
D26 keys. `impedance_facts` reports `lead_model_by_hemisphere` and `lead_type_by_hemisphere`, and
`facts_for_participant` takes the sensing lead's own family (the old left-lead value is the fallback
when no side is known). Test: a 1x4 right lead beside a SenSight left lead gives "1x4" for a right
candidate and "sensight" for a left one. Live: RCS08 has SenSight on both sides, so only the
provenance text changed ("... on the Left lead").

## C12 (Low) — one therapeutic current

`pipeline.py`: when the cell has exactly one nonzero current, a blocker is appended ("only one
therapeutic Left amplitude on record for this cell (2.5 mA), so no low and high capture amplitudes
exist (D24) and no thresholds were placed"). Test: such a table gives `rep.threshold is None`, that
blocker, and `is_licensed() False` even with an established pooled slope. Not reachable on RCS08.

## Hazard 1 — the 20 s post-ramp margin, wired in. THIS CHANGES NUMBERS.

**What changed.** `three_source_response._tile_panel` now passes `ramp_end_t=steps["t0"]` and
`ramp_margin_s=within_visit.RAMP_EXCLUDE_S` (20 s) to `mean_power_before_next_change`, so the
settled window on every setting starts no earlier than 20 s after the current stopped moving. Rule
versions bumped so no entry built without the margin is served as if built with it:
`run_points.RULE_VERSION` v3, `amplitude_effect.RULE_VERSION` v2, `POOLED_RULE_VERSION` v3, and --
beyond the review's list, because its voltage-trace route carries these numbers --
`ground_truth.RULE_VERSION` v3; `simulation.RULE_VERSION` v5 with the pooled rule version in its key.
A test plants a distinct value in the first 20 s after each current change and asserts the settled
means are exactly the later value (100.0, three settings), and that the old rule (no margin) would
have carried the planted value into the mean.

**Measured on RCS08, the stored tables before against after, rows keyed on their identifying
columns:**

- **Per-run points**: 3,017 rows before, **2,724** after, 2,723 in common, **294 only-before, 1
  only-after**; of the rows in common **59,906 fields compared, 15 differing in 8 rows**
  (`n_pieces_averaged` 8, `why_not_used` 5, `settled_band_power_device_units` 2). The 294 rows that
  vanished are ONE run, "2025-09-04 14:15, left stimulator turned up, other side at zero" on
  ONE_THREE_LEFT, across its 98 bands and 3 settings: its only usable setting (2.5 mA) had exactly 10
  pieces in the 30 s window, and after the 20 s margin none of its settings keeps the 10 required, so
  the run now contributes no settled value (the one only-after row is that run's "no settled value"
  placeholder). Two more settled points are lost elsewhere: ONE_THREE_LEFT 2026-08-18 12:51 at 3.5 mA
  (10 -> 8 pieces, "the current finished moving only 45 seconds before it was changed again") and
  ZERO_THREE_RIGHT 2025-10-21 16:41 at 3.0 mA (10 -> 5 pieces, 34 seconds).
- **Pooled table**: 294 rows both times; **6,174 fields compared, 2,263 differing in 194 rows** --
  every assessed row. ONE_THREE_LEFT: 13 points across 4 runs -> **11 across 3**; ZERO_THREE_RIGHT: 12
  points -> **11** (still 6 runs); ZERO_TWO_LEFT (the committed contact): **0 rows changed**, still 5
  points in 1 run, still "not assessed". Examples: ONE_THREE_LEFT 24.5 Hz slope −3.79 -> +17.31 per
  mA (p 0.42 -> 0.074); ONE_THREE_LEFT 20.5 Hz (the number decision 128 quotes) −3.62 -> +0.46 (p
  0.73 -> 0.97); ZERO_THREE_RIGHT 24.5 Hz 10.83 -> 13.44 (p 0.47 -> 0.45).
- **Amplitude-effect table**: 1,078 rows -> 980 (the dropped run's 98 rows), 36,260 fields compared
  on the rest, 2,836 differing in 194 rows. **Ground-truth table**: 2,958 -> 2,667 rows, 66,600 fields
  compared, 23 differing in 8 rows.

**Live on the committed band (L 0-2+, 24.5 Hz)**: 58,601 fields before, 58,010 after, 58,005 in
common, 2,899 non-timing differences -- **every one under the three-source panels
(`three_source_response`, `three_source_pooled`) and the four table-bookkeeping blocks; the
ledger, the three edges, the thresholds, the prescription and the verdict have 0 differences**,
because the committed contact has no pooled slope with or without the margin. On the right band E1
moves from 10.8331 to 13.4409 per mA, both unresolved.

**This is the PI's to confirm.** The margin is the rule the Stim Optimizer's own settled-tile
reading already applies (`RAMP_EXCLUDE_S`), and commit `790ed21`'s clip was written for exactly this
use and never called here; but on this record it removes one run and two points and changes the sign
of several ONE_THREE_LEFT slopes. Reverting is one line (drop the two keyword arguments) plus the
five rule-version bumps.

## C8 (Low, optional) — the recordings decoded once per request

`three_source_response.build_for_participant(..., loaded_sink=)` hands back the decoded power,
time-domain and PSD recordings and the tile cache entry (never in the payload); the report passes
them to `write_simulation(..., loaded=)` and `simulation_inputs_for_participant(..., loaded=)`,
which loads only what it was not handed. **Measured on RCS08 in alternating rounds** (decode twice,
hand over, decode twice, hand over), the simulation's inputs for the committed band: **98,719 fields
compared, 0 differing, 0 on one side only**; decoding again cost **2.327 s and 2.305 s** against
**0.010 s and 0.010 s** with the recordings handed over (386 time-domain, 446 PSD and 273 streaming
recordings skipped). The final committed-band capture against the previous one: 58,010 fields, 6
non-timing differences, none from this change -- four are the band-stability model's p-value and
interval moving at the 10th significant figure between two R fits, two are the Biomarkers grid's
store stamp, which the Biomarkers builder rewrote in the same checkout while this ran.

---

## Things the PI should read

1. **A right-side band on RCS08 fails D27 on the device's own record** (the right capture runs at
   150 us, above the 120 us artefact ceiling). Until today the page passed it by reading the left
   capture. Nothing on the page said so.
2. **Hazard 1 removes one run and two settled points from the pooled titration slopes** and changes
   the sign of several ONE_THREE_LEFT slopes (numbers above). The committed band is unaffected.
3. **The D26 row on the committed band stays "could not be determined"**, now with the reason on
   it, because no pooled slope is stored for L 0-2+ at 24.5 Hz; a titration session (open item 30)
   is what fills it.
4. The reliable-change floor's epoch cut (`reliable_change.py`) still ends the open epoch at the
   last export; the review named it and the fix instruction did not include it.
