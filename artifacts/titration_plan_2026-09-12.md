# The titration session the Stim Optimizer page now recommends for the next visit

**UPDATED 2026-09-14 — two rulings that change the numbers below, kept in place as history rather
than rewritten (this project's own convention for a superseded row).** (1) The stated ceiling for
RCS08 is now **4.5 mA on both sides**, not 5.0 mA (`safety_ceiling.PI_STATED_CEILING_MA`; decision
145's table row is struck-and-corrected the same way). (2) The ladder's DOWN leg is now 1.0 mA
steps, not the same 0.5 mA steps as the way up (his words: "keep the 1.0 mA down legs"); each step
is now two clinic-sheet rows, a 60 s ramp row then the unchanged 60 s test row (2 min a step, not
one 60 s row); the other side is held at its own current in force while one side's ladder runs,
rather than left unstated; and an optional "joint corners" block gives the pain surface's
off-diagonal points. At the new 4.5 mA ceiling the ladder is **10 distinct currents on the way up,
15 steps in all** (0 → 0.5 → … → 4.5, then 3.5 → 2.5 → 1.5 → 0.5 → 0), not the 11/21 the table
below states for the old 5.0 mA ceiling. See `titration_plan.py`'s own module docstring for the
full reasoning; the live numbers below are from before this update and are kept as a record of
what the card said that day, not as the current answer.

**Built 2026-09-12 evening**, on the PI's decision: *"make #4 a feature of next stim opt
recommendation combined with 30."* Item 4 is the 20 s post-ramp margin (decision 144: it ships
OFF, because on the 11-13 points the record holds it flips a verdict by removing two of them);
open item 30 is the titration session that would give the current-to-power slope enough settled
points that no margin could flip it, and would show whether 20 s after a current step is settled
on this device. The two are now one thing: the page recommends the session, designed from RCS08's
own record, and says that the margin switches on once such a session has been recorded.

**Where it is on screen.** Stim Optimizer page, a new card titled **"Titration session to run
next"**, directly under "What to test at the next visit" and above the closed-loop card. Two
columns, Left and Right. **Nothing here writes to the device**: it is a sheet a clinician reads at
the visit.

**Where it lives.** `BRAVO/modules/StimOptimizer/titration_plan.py` (the arithmetic, pure
functions, no Django), `bravo_service.titration_plan_block` (gathers the inputs and reads two
stored tables once), the response key `titration_plan`, one new function
`margin_becomes_available` in `ClosedLoopDeployment/post_ramp.py`, and the card
`Client/src/views/Reports/StimOptimizer/TitrationSessionCard.js`. **The switch
`USE_POST_RAMP_MARGIN` is NOT flipped**; it is still OFF.

---

## 1. What the card says for RCS08 today (every number, read live through the bridge)

Both sides share the same design because both sides are on the same rate today and have the same
stated ceiling. The differences are the pulse width, the sensing contact, and what the record
already holds on that contact.

| | Left | Right |
|---|---|---|
| **rate to hold** | **55 Hz** — the rate in force on this side, not lifted | **55 Hz** — the rate in force on this side, not lifted |
| **pulse width to hold** | **100 µs** — in force on the Left | **150 µs** — in force on the Right (its own column, not the Left's) |
| **ceiling** | **5.0 mA** — stated by the PI | **5.0 mA** — stated by the PI |
| **current ladder** | 0 → 0.5 → 1.0 → 1.5 → 2.0 → 2.5 → 3.0 → 3.5 → 4.0 → 4.5 → 5.0 → 4.5 → 4.0 → 3.5 → 3.0 → 2.5 → 2.0 → 1.5 → 1.0 → 0.5 → 0 mA: **21 steps, 11 distinct currents**, the top step held once | the same |
| **hold per step** | **60 s** = 30 s settled window + 20 s post-ramp margin + 10 s slack; leaves **13 usable 3 s pieces** after the margin, against the **10** a settled setting needs | the same |
| **record from** | **L 0⁻2⁺** (ZERO_TWO_LEFT): **12 of 18 bands respond at 55 Hz**, ipsilateral, passed the screen — the readiness screen's best deployable cell for Left stimulation at the session's rate, the same pick the two-stage gate makes per side | **L 0⁻3⁺** (ZERO_THREE_LEFT): **15 of 18 bands respond at 55 Hz**, but it is a contact on the **OTHER side** (Left); the device needs a contralateral sensing configuration for it (decision 143, S3). The best contact on the Right itself, **R 1⁻3⁺**, has 12 of 18 bands responding but did not pass the screen (only 1 of 18 bands has a significant negative era-blocked slope) |
| **band centres to analyse** | **12 clear**: 8.5, 9.5, 10.5, 16.5, 17.5, 18.5, 19.5, 20.5, 21.5, 22.5, 23.5, 24.5 Hz. **10 struck**: 11.5, 12.5, 13.5, 14.5, 15.5 Hz (within 2.5 Hz of 13.75 Hz, a quarter of the rate) and 25.5, 26.5, 27.5, 28.5, 29.5 Hz (within 2.5 Hz of 27.5 Hz, half the rate). The stimulator shows up at 195, 27.5, 13.75 and 41.25 Hz | the same (same rate) |
| **during the session** | streaming on throughout (so the voltage trace exists for every step); an off-stimulation baseline before the first step and after the last; an impedance test before and after at a FIXED measurement current, not the device's automatic low-current mode, which reads spuriously high (decision 133); every step held 60 s or longer, the wall-clock time of each current change on the clinic sheet | the same |
| **what the record holds today on that contact** | **5 settled points across 1 run** of rising current (the most at any centre in the pooled table: 22 of 22 centres hold that many); **at most 5 settled currents in any one run** (1 run on this contact) | the pooled current-to-power table has **no row** for L 0⁻3⁺ and the per-run points table has **no run** on it |
| **what the session buys** | **21 settled points, 11 distinct currents on the way up** | the same |

**The margin sentence, derived from the stored per-run points table (11 runs, 3,017 rows), not
typed:** *"No run in the record holds the 8 settled settings the 20 s post-ramp margin needs (the
most in any one run is 6, the run of 2026-08-18 12:51, left stimulator turned up, other side at
zero, on ONE_THREE_LEFT); the margin stays off until this session is recorded, and its rising leg
alone gives 11."* So on RCS08 today: no such run exists, the switch is off, and the session's
rising leg alone (11) clears the floor of 8.

Two things a reader should carry:

- **The Left sensing contact is the committed band's contact.** L 0⁻2⁺ is where the PI's committed
  band (24.5 Hz) sits, and 24.5 Hz is one of the 12 clear centres at 55 Hz. The record on that
  contact is one run of 5 settled currents (decision 139 measured the same: "5 usable points at 5
  distinct currents pooled across 1 visit"), which is why the pooled slope on the committed band is
  "not assessed" today and why this session matters there most.
- **The Right side's best evidence at 55 Hz is on a Left contact.** That is decision 143's S3 case
  and the card says so in amber rather than hiding it; it also names the best contact on the Right
  itself and why it did not pass. Which contact to record from on the Right is the PI's call at the
  visit; the card does not make it.

---

## 2. Where each number came from (the `sources` block, printed under "Why this design" on the card)

| Field | Source |
|---|---|
| rate | "the setting in force on the {side} side, from the full epoch table (newest device setting, rated or not), since 2026-09-03T20:07:11+00:00"; when lifted, "lifted to the adaptive minimum (55 Hz, percept_adaptive.MIN_ADAPTIVE_RATE_HZ, decision 138)" |
| pulse width | the same setting in force, each side's own column |
| ceiling | "stated by PI (2026-09-02 hard limit, objective.AMP_HARD_LIMIT_MA; confirmed as the safety ceiling 2026-09-12)" — `safety_ceiling.ceiling_for` |
| sensing contact | "the readiness screen's best deployable cell for this side at the session's rate, 55 Hz (lfp_evidence.best_deployable, the gate's own per-side pick)"; falls back to any rate (named), then to the most-responding cell on the side (named as not passed) |
| ladder | "0 mA to the stated ceiling in 0.5 mA steps, up then down (research synthesis §1; open item 30)" |
| hold | "within_visit.PRE_CHANGE_WINDOW_S (30 s) + within_visit.RAMP_EXCLUDE_S (20 s, decisions 141 and 144) + 10 s slack; pieces of within_visit.CHUNK_S (3 s), within_visit.MIN_CHUNKS_PRE_CHANGE (10) required" — all read from the constants, none typed again |
| band centres | "the 22 calibrated-grid centres, 8.5-29.5 Hz (decision 32); harmonics \|250 − rate\|, rate/2, rate/4, 3·rate/4 (research synthesis §1); ±2.5 Hz" |
| record today | "the stored pooled current-to-power table (within_visit_pooled_shape) and the stored per-run points table (three_source_run_points), both written by the Closed-Loop page, read as stim_optimizer" — the pooled table read: 294 rows, written 2026-09-12T21:53:24 UTC; the per-run table: 3,017 rows, written 2026-09-12T21:53:25 UTC |
| the margin | "ClosedLoopDeployment.post_ramp.margin_becomes_available over the stored per-run points table; the floor is amplitude_effect.MIN_POINTS_CURVATURE" (8, decision 55) |
| conditions | research synthesis §1; decision 133 (impedance) |

A "settled setting" for the margin count is a distinct current carrying a settled band-power
value on the voltage-trace route, counted per (run, sensing contact). A rate below 55 Hz would be
lifted to 55 Hz with the reason on the card; on RCS08 both sides are already at 55 Hz.

---

## 3. Tests (30 new, `StimOptimizer/tests/test_titration_plan.py`; two existing key-list tests updated)

- the ladder never exceeds the stated ceiling, for 5.0, 4.8, 3.0, 0.5, 2.25 and 6.0 mA; goes up
  then down; 2 × distinct − 1 steps; 5.0 mA gives exactly the 21 steps listed above; 4.8 mA rounds
  DOWN to 4.5 and says so; no ceiling gives no ladder and a reason;
- a rate below 55 Hz (40 Hz) is lifted to 55 with the reason naming decision 138; 55, 110 and
  145 Hz are held as they are; no rate on record gives the minimum and says so;
- the harmonic avoidance pinned on the values: **55 Hz** avoids 11.5, 12.5, 13.5, 14.5, 15.5,
  25.5, 26.5, 27.5, 28.5, 29.5 (12 clear); **110 Hz** avoids 25.5, 26.5, 27.5, 28.5, 29.5
  (harmonics 140, 55, 27.5, 82.5 Hz; 17 clear); **145 Hz** avoids nothing (105, 72.5, 36.25,
  108.75 Hz; 22 clear); a candidate centre is judged the same way (24.5 Hz clear at 55 Hz, 27.5
  Hz not);
- the hold is 60 s = 30 + 20 + 10, from the `within_visit` constants, leaving 13 ≥ 10 usable
  pieces;
- `margin_becomes_available`: a 6-setting run → False (most 6, the run named); adding an
  8-setting run → True with that run listed; only the voltage-trace route counts and a current
  with no settled value does not; the same current at three centres is one setting; no table →
  "not stored", not zero;
- the record-today reader picks the best-covered centre inside 8-30 Hz for that contact (13
  points, 4 runs at 20.5 Hz, ignoring a 72.5 Hz row) and the largest settled-current count in
  one run; no tables → said, not zero;
- the yield arithmetic: 21 points, 11 on the way up, clears the floor of 8, and the sentence;
- a lifted rate changes the band list and its source names the minimum; a contralateral contact
  is named as on the other side; no contact gives a note;
- every source non-empty;
- through the service with the platform stubbed: `titration_plan` for both sides, each side's OWN
  pulse width (100 / 150 µs), the fallback ceiling named as the module hard limit, the screen's
  per-side pick at the session's rate, a cell that passed only at 165 Hz named with that rate,
  the block survives a readiness failure, and no numpy scalars anywhere in it.

The two tests that pin the exact list of top-level response keys
(`test_two_stage_wiring.py`, `test_two_stage_adaptive_envelope.py`) now list `titration_plan`.
That was the whole of the first suite run's two failures.

---

## 4. Proofs on RCS08 (through the bridge, a fresh build into the scratch store override)

**Field count and difference count, never a tolerance.** The committed module (`git archive
HEAD`, run through the probe's `old` mode) against the working tree, the page's own request
(both sides, both sites, plotly backend):

- **before 21,771 fields, after 22,106; 21,771 in common; 0 only-before; 335 only-after, every
  one under `titration_plan`; 2 differing, of which 1 non-timing: `store.response_key` (the key
  hashes the module's source, so it changes by design) and `cache_status.last_built_utc`.**

No speed claim is made: the "before" run was made in the probe's `old` mode, which also leaves the
BLAS thread pool uncapped, so its 30.03 s against the after run's 9.76 s measures decision 140's
cap and not this change. The two stored-table reads this block adds cost 0.01-0.03 s each in the
per-stage table.

**Suites, one bridge job each, both runners (`run_both_suites.sh`), verbatim:**

- first run, before the two key-list tests were updated:
  `host:      1066 passed, 2 skipped, 2 failed, 0 errors  [parallel: 2 failed, 1065 passed, 2 skipped in 10.40s | store, serial: 1 passed, 1069 deselected in 0.45s]`
  `container: PASS=630 FAIL=0 LIVE_SKIPPED=6`
- after, job `20260912-193022-2d710c8b`:
  `host:      1068 passed, 2 skipped, 0 failed, 0 errors  [parallel: 1067 passed, 2 skipped in 10.03s | store, serial: 1 passed, 1069 deselected in 0.40s]`
  `container: PASS=630 FAIL=0 LIVE_SKIPPED=6`

Baseline was host 1038 / 2 / 0 and container 630 / 0; the host gained exactly the 30 new tests.

**Frontend.** Rebuilt clean (`Compiled with warnings`: 209 warnings repository-wide, the same 209
as before this change; none in any file under `Client/src/views/Reports/StimOptimizer/`). The
strings this card owns — "Titration session to run next", "Why this design", "The best contact
on this side itself" — are each in **`Client/build/static/js/328.599edcdf.chunk.js`** and in no
other chunk. **Not watched in a browser** this session (not signed in); the card's values are the
ones printed in §1, read from the same response the page receives.

**Workers and the stored response.** The four gunicorn workers were reloaded (`kill -HUP 1`; four
fresh worker processes, ages 1-8 s, under the same master). The page's own two requests were then
made against the production store: the plain request built in 9.46 s and wrote
`stim_optimizer_response/…/32895e7c…`; the TwoStage request built in 10.15 s and wrote
`…/8899775638…`; a repeat of the plain request in a fresh process was **served in 1.67 s**
(`served_from_store=True`, `cache_status.last_built_utc` 2026-09-13T02:31:38 UTC).

---

## 5. Two things found on the way, not fixed here

1. **The page's own two requests evict each other's stored response.** `stim_optimizer_response`
   is not in `CacheStore.store.KEEP_NEWEST_BY_KIND`, so it keeps ONE entry per participant. The
   page fetches the plain response, then the same request with `TwoStage: true` under a different
   key; the second write removes the first. Watched live: plain (built), TwoStage (built), plain
   again in the same process — **not served**, rebuilt in 9.00 s. The next page load therefore
   rebuilds the plain response every time (about 9-10 s) rather than reading it. Pre-existing,
   the decision-107 class, and one line in `KEEP_NEWEST_BY_KIND` (2 for this kind) would close
   it; the store is outside this builder's files, so it is reported rather than changed.
2. **The readiness screen's best deployable cell at ANY rate is at 165 Hz on both sides** (L 1⁻3⁺
   and R 0⁻3⁺, 18 of 18 bands each), a rate the session does not run at. The card therefore picks
   at the session's rate first (L 0⁻2⁺ and, contralaterally, L 0⁻3⁺ at 55 Hz), and would name the
   165 Hz cell only if nothing passed at 55 Hz. This is the same rule the gate applies per side; it
   is stated here so nobody reads the card's contact as "the best contact on the record".
