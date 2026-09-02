# Session handoff — 2026-09-02: closed-loop wiring completed

Commits `5d07a9f` -> `969534d` on `PS_closedloop_deployment`, pushed. StimOptimizer suite
**359 passed / 41 skipped**; container Biomarkers **320/320**. Deployment verified on all three
axes (git in sync, container checksums match the host for all seven touched modules, workers
restarted and the freshly built bundle is the one nginx serves).

## What was built

The chain that lets Stage 2 be evaluated against real recordings instead of against `None`:

    adapter.evidence_inputs(participant)        -> (psd_frame, epochs)
    lfp_evidence.build_all(...)                 -> {(channel, hemi, rate): LfpEvidence}, audit
    lfp_evidence.screen_cells(..., response_fn) -> screen frame, selected key
    pipeline.live_evidence(participant, ...)    -> LiveEvidence (selected + screen + audit)
    bravo_service.closed_loop_readiness(...)    -> JSON payload
    Client/src/views/Reports/StimOptimizer      -> "Closed-loop readiness" panel

`lfp_evidence.select_for()` picks the cell matching a frozen configuration and refuses two things:
evidence from a DIFFERENT rate (artifact scales with rate, so a response at one rate says nothing
about another) and an unnamed choice among several sensing channels.

## The result on RCS08

84 (channel, hemisphere, rate) cells evaluated -> 50 usable -> 10 with any responding band ->
**1 deployable: `ZERO_TWO_LEFT` / Left / 55 Hz**, 18 of 18 adaptive-window bands responding, all 18
with significant era-blocked slopes, amplitude 1.4-4.5 mA against a 4.90 mA energy cap, median
separation 1.17. The screened selection and an explicit request for that cell agree.

Nine responders failed, and the reason counts (from `rcs08_closedloop_screen.csv`) are 5 on energy,
5 on band minority, 2 on era blocking (some fail more than one):

1. **The energy gate applies to the EVIDENCE, not only to proposed settings.** FIVE cells:
   `ONE_THREE_LEFT` Left @165 Hz contrasts 1.6 -> 4.8 mA against a 3.35 mA cap, and FOUR cells at
   110 Hz reach 4.0 mA against 3.18 mA (`ZERO_THREE_LEFT`, `ZERO_THREE_RIGHT`, `ZERO_TWO_LEFT`,
   `ZERO_TWO_RIGHT`, all Left). Energy is the SOLE blocker for three of the five. Same argument that
   disqualified the 165 Hz lead — if the high arm delivers more energy than we will program, a
   response measured only across it was never deployable evidence. Without this condition a clean
   dose-response curve recorded outside the safe envelope silently licenses a policy inside it.
2. **A majority of scanned bands must respond.** The 18 bands are 5 Hz wide on a 1 Hz grid, so they
   overlap and move together; one or two responding bands is the maximum of a correlated family.
3. **The slope must survive era blocking.** ONE cell — `ZERO_THREE_RIGHT` Right @110 Hz — has 18 of
   18 bands responding and ZERO with a significant era-blocked slope. Amplitude rose over time, so
   unblocked that slope is time, not dose. A second cell with no era-significant band
   (`ZERO_THREE_LEFT` Right @110 Hz) responds on only 1 of 18 and fails band-majority too, so it is
   not an example of a strong cell defeated by the confound.

## Two bugs found by running it, not by tests

Both the same failure — fixtures written with invented names instead of production's, so the whole
suite passed while the first live call broke.

- **Column names.** `lfp_evidence` hardcoded `rate` / `amp_Left` / `visit`; production
  `adapter.exposure_epochs` emits `freq_hz` / `amp_mA_Left` and no visit column. First live call
  raised `KeyError: 'rate'`. Now resolved against `RATE_COLS` / `AMP_COL_TEMPLATES` with the
  PRODUCTION names first, and the audit records which columns were read.
- **Era fallback.** With no era column it fell back to the per-epoch index: one observation per
  stratum, i.e. blocking with no blocking power, while reporting a large era count that hid it.
  Eras are now calendar months of `t_start` and `aud.era_source` names the source.

Also fixed earlier in the day and worth repeating here: the platform stores `10*log10(power)`
(decibels), so linearising with `10 ** logX` is wrong by a factor of ten in the exponent and returns
finite, plausible numbers. `band_power_linear` takes an explicit `log_scale` and refuses an unknown
value.

## Still open

- `run_two_stage` accepts `lfp=` but no single call passes `live_evidence(...).selected` into it.
  The pieces are connected and individually verified; joining them is small. On present data the
  gate refuses on the resolution condition regardless, so this changes no verdict today.
- **Out-of-sample calibration is not assessed anywhere** — not the severity model, not either
  surrogate backend, not per stratum.
- **The frequency length scale is not identified** by this data under any prior tested, and its
  profile is bimodal. That sits upstream of every posterior the module reports.
- The rotation-versus-block permutation design question is the PI's call, since changing it moves
  published p-values.

## Operational note, now four for four

The server runs with `--reload` and it has NEVER picked up a change in this project. Workers were
96 minutes old against modules edited minutes earlier. **Always sync the container from the
committed host tree, `kill -HUP 1`, and verify worker ages afterwards.** The app listens on
**port 27286** (nginx on 80) — not 8000 or 3001, which is what two of my probes wrongly assumed.
And route introspection by callback name gives a FALSE NEGATIVE for class-based views; resolve the
URL path instead.
