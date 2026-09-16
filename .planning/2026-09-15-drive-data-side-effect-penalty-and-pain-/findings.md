# Findings: Drive data, side-effect penalty and pain scaling audit

## Context carried in from the landed plan (2026-09-11-make-closed-loop-work)
- HEAD 55dd551b on PS_closedloop_deployment, clean tree, suites green (host 1260 pass, container PASS=631).
- Clinic-sheet stream ingested from `BRAVO/_pro_dump/clinic_sheets/RCS08/` (gitignored). Live counts on
  2026-09-15 01:25: n_steps 816, n_with_pain 472, n_unparsed_prose 7, n_skipped_no_setting 16.
- Module hard cap `objective.AMP_HARD_LIMIT_MA` = 5.0; PI safe ceiling 4.5/4.5 (safety_ceiling.ceilings_by_hemisphere).
- Open non-code items: decision 139 threshold re-centring; titration session Wed 2026-09-16; Google
  service-account key; whether 5.0 hard cap should drop to 4.5.

## Early signals from grep (to verify in Phases 2-3)
- **Common scale is 0-10 NRS, not 0-100.** `tests/test_core.py:272` asserts `OBJ.scale_factor("left_leg_vas") == 0.1`;
  `test_core.py:255-267` says a 0-100 VAS primary item is rescaled so J_pain is in NRS points (|J_pain| <= 10).
  This is the INVERSE of the PI's premise ("0-100, NRS x10") -- equivalent normalisation, opposite direction. Must confirm.
- `test_core.py:71`: `side_effect_penalty("mild") == 1.0` ("cancels exactly 1.0 NRS point"); `None -> 0.0`; unknown label raises.
  `test_core.py:81`: some level maps to +inf ("a finite penalty would be beaten by a large enough pain benefit").
- `test_core.py:76`: `se_observed` -- "absence of a report is not absence of a side effect".
- `adapter.py:492`: "Nothing is rescaled on the way through here" (REDCap adapter passes raw item scales through; objective does the rescale).
- `clinic_pain.py:714`: sheet-stream items are laid out so `objective.build_objective`'s item resolution "finds them with no rescaling" -- need to check whether the verbal /10 scores are therefore treated as 0-10 already.
- `clinic_pain.py:95-97`: only ONE workbook layout has a numeric severity column ("SIDE EFFECT"/"SCORE" two-row header); label map {0:none,1:mild,2:mild,3:moderate,4:severe}. Other workbooks' "Side Effect?" is free text, NOT parsed as a number.
- `routines/stage_gate.py:69`: amplitude does NOT predict side-effect severity in this record (Spearman rho=-0.013, p=0.79).
- `stage2_closedloop.py:213`: only 5 of 417 non-procedural rows with stim on sit above some severity threshold.

## Phase 1: Drive-imported data inventory (clinic_pain.py, read 2026-09-15)
- Folder `BRAVO/_pro_dump/clinic_sheets/RCS08/`: 30 workbooks + 1 `_Template_` + `manifest.json`
  (manifest = Drive download record: title, file, drive_id, bytes, sha256 per file; 30 entries; NOT parse counts).
  Docstring says "29 workbooks" -- the folder has 30 (the 2026_Sep2 file was added after; counts as the one with the numeric SE column).
  Visits span Jul 2025 .. Sep 2026: 20 In-Clinic, 9 At-Home, 1 fMRI-DBS visit (06_22_26).
- Ingest key facts (`clinic_pain.py`):
  - Columns matched BY NAME (`_canon_header`, L108-160), scribe suffix "(Name)" stripped; typo tolerance ("Timastamp", "PW (ms)").
  - PAIN_FIELDS = overall, head, back, left_leg, left_foot, right_leg, right_foot (L91). "Verbal" and "Current verbal pain score" -> `overall` (L149).
  - `_parse_pain_value` (L204-241): plain number -> float AS WRITTEN; "N/10" -> N (numerator); Excel-date trap (day==10, month 1..10) -> month.
    **No rescaling of any kind.** `_PLAIN_NUM` accepts up to 3 digits, so a stray "80" would pass through as 80.0 (check live max).
  - Side-effect: ONLY the bare header "side effect" (the SCORE sub-column, 2026_Sep2 workbook only) -> `side_effect_score`, parsed by the
    same `_parse_pain_value` (0-4). "Side Effect? ..." headers -> `side_effect_text` (free text, never a number; only used for the prose-hint counter).
  - `SIDE_EFFECT_SEVERITY_LABEL = {0:"none",1:"mild",2:"mild",3:"moderate",4:"severe"}` (L97). Sheet's printed ladder is 0=none,1=mild,
    2=mild persistent,3=moderate,4=avoid. So 2 collapses into "mild" and 4 ("avoid") becomes "severe".
  - `epoch_frame_from_steps` (L706-778): groups distinct (rate, ampL, ampR, pwL, pwR) rounded to 2 dp -> one epoch; `pain_<Site>` = mean of
    that site's scores, `_sd` = std (n>=2); `se_severity` = label of the WORST (max) side_effect_score in the group, else None.
    Rows with no rate are dropped (all of July 2025 -- rate/pw not recovered there). Docstring L713-714: "each on its native 0-10 scale, so
    objective.build_objective's own item resolution finds them with no rescaling."
  - Counters: n_steps (amp cell set), n_with_pain, n_unparsed_prose (regex hint on notes / side_effect_text), n_skipped_no_setting.
- So for the clinic stream, the ONLY numeric side-effect evidence is from the single 2026-09-02 workbook; every other epoch has se_severity=None.

## Phase 2/3 core: routines/objective.py (read in full 2026-09-15)
### Scale (answers premise C)
- L64-77: `TARGET_SCALE = 10.0`; `NATIVE_SCALE` = {nrs:10, pain_*:10, *_vas:100, vas:100, relief:100, mpq_sum:45}.
  `scale_factor(col) = 10 / NATIVE_SCALE[col]` -> VAS x0.1, NRS x1.0, unknown col -> 1.0 (assumed already 0-10).
- Comment L57-63: "Everything is therefore rescaled to a common 0-10 reference before J_pain is formed" and WHY: the SE ladder
  is calibrated in NRS points (1 mild = 1.0) and "would be ten times too weak against a 0-100 objective".
- `build_objective` L341-352: `sf = scale_factor(item)`; item and `<item>_sd` multiplied IN PLACE; frame records
  `primary_item` and `primary_scale_factor` so a later reader cannot rescale twice. `J_pain = item*sf - ref(incumbent)`.
- `composite_z` L246-249: non-standardised metrics also multiply by `scale_factor(col)`; z-scored (legacy_composite) do not (SD units).
- **VERDICT on premise C: the PI's statement "scaled to 0-100, multiply NRS by 10" is INVERTED relative to the code. The code
  scales to 0-10 (VAS / 10). Same normalisation, opposite direction; internally consistent with the NRS-point ladder.**

### Side-effect penalty (answers premise B)
- L21-26: `SE_LADDER = {"none":0.0, "mild":1.0, "moderate":inf, "severe":inf}`. Rationale L17-24: J_pain is bounded below by
  -incumbent (~-7.28), so any finite penalty could be outbid; +inf is the only way "always rejected" is true (Sarikhani et al. contrast).
- L30-33: `SE_HARD_REJECT = {moderate, severe}`, `SE_SEVERITY_RANK` none0/mild1/moderate2/severe3, `SE_THRESHOLD = 3.0` (safety GP boundary).
- `side_effect_penalty` L199-208: None/NaN -> 0.0; label lowercased and looked up; unknown label RAISES ValueError.
- `build_objective` L361-372: if `se_severity` column exists -> `se_observed = notna`, `J_SE = map(side_effect_penalty)`;
  else `se_observed=False`, `J_SE=0.0` with comment "absence of a report is not absence of a side effect".
  L376: `J = J_pain + J_SE`; L379: `feasible = isfinite(J)` -> moderate/severe epochs are INFEASIBLE, excluded from the argmin but
  (comment L28-31) still inform the safety GP.
- No energy term (L373-375, w_energy was 0.0; removed). `AMP_HARD_LIMIT_MA = 5.0` (L211-227), flat, PI-declared at 165 Hz.
- Open question to trace: REDCap stream -- does adapter.py ever populate `se_severity`? Clinic stream -- only the 2026_Sep2 workbook.
  Where does the SafetyGP get its severity (surrogate.SafetyGP.seed_from_history "tolerated anchor / limit anchor")?

## Phase 2: where side-effect evidence actually enters the optimizer (traced 2026-09-15)
### Three separate side-effect channels exist; only one is live in the safety model
1. **REDCap stream (adapter.py)**: grep for `se_severity`/`severity` in adapter.py -> NO hits. The PRO battery has no
   structured severity field (surrogate.py L418-419 says so). So on the REDCap stream `build_objective` takes the
   `else` branch (objective.py L367-372): `J_SE = 0.0`, `se_observed = False` for EVERY epoch. J == J_pain there.
2. **Clinic-sheet stream (clinic_pain.py)**: `se_severity` populated ONLY from the 2026_Sep2 workbook's numeric 0-4 column
   (worst score per setting -> label). Every other clinic epoch -> None -> penalty 0.0, se_observed False.
   Need to confirm live how many clinic epochs carry a non-null se_severity.
3. **SafetyGP (surrogate.py L389-530 + safety_ceiling.py)**: fitted on PSEUDO-observations only:
   - severity-3 (`SE_THRESHOLD`) anchors = the PI-stated ceiling (4.5 mA both sides for RCS08, `PI_STATED_CEILING_MA`,
     safety_ceiling.py L47-51), one per rate on the grid (`ceiling_anchors`), var 1.5;
   - severity-0 anchors = every (rate, current) with amp>0 held >= min_tolerated_h (72 h REDCap; 0.001 h clinic,
     `CLINIC_MIN_TOLERATED_H`), var 0.5 (`tolerated_anchors`, `safety_seed`).
   - Safe set = mu + beta*sigma < 3.0 (beta=2). `expansion_capped_mask` keyed to worst_severity (none 0.4 / mild 0.2 / mod,sev 0).
   - **No reported side-effect score of any kind enters the SafetyGP today.** surrogate.py L436-438: "Never mix these with real
     severity reports without keeping an se_observed flag alongside, and drop the seeds once prospective reports exist."
   - Previously (until 2026-09-12, decision 143/145) the severity-3 anchors came from device `UpperLimitInMilliAmps`;
     replaced because a programmed limit is not a side-effect statement (safety_ceiling.py docstring; Left ceiling fell 5.0->0.1 mA).

### The "amplitude does NOT predict side-effect severity (Spearman rho=-0.013, p=0.79, n=417)" claim
- Appears in routines/stage_gate.py L69-72, stage2_closedloop.py L211-215, TWO_STAGE_DESIGN.md L185. NOT computed anywhere in
  current code; it is a hard-coded number from the 2026-09-02 ordinal-safety analysis (BOTORCH_REFACTOR.md L60-105).
- That analysis's data: `rcs08_acute_steps_coded.csv` (artifact b4886a4f...), 774 coded acute steps -> 417 fitted
  (375 none / 23 mild / 18 moderate / 1 severe). **BOTORCH_REFACTOR.md L84-97: 402 of the 696 "none" labels were rows never
  presented to a coder -- absence of a note, not an observation of no side effect.** Explicit-coded-only refit (153 rows):
  moderate-or-worse rate 12.4% vs 4.56%; 0 safe cells vs 14. "absolute risk level ... uncertain by roughly a factor of three."
- The ordinal model itself (`routines/safety_ordinal.py`, 917 lines, + its 413-line test) was DELETED in decision 145
  (commit b945fd67) as unreached. The `_ordinal_analysis_driver.py` is gone too. So the rho=-0.013 number now has no
  reproducible path in the repo and its input labels were 96% (402/417) uncoded absence.
- What that claim GATES: stage2 `_amp_windows` bounds adaptive limits to the DELIVERED envelope (conservative direction --
  it refuses to go above what was delivered). So the label problem makes the justification text weaker, not the gate unsafe.

## LIVE PROOF on RCS08 (container, bridge job 20260915-093710-adf061b3, probe `_agent_bridge/_audit_scale_se.py`)
### REDCap stream (adapter.build_design_matrix, washin 1 min): 92 epochs
- Raw item ranges BEFORE build_objective: left_leg_vas 20.5..84.5 (n=75), back_vas 37..100, nrs 4.5..9.0 (n=92), vas 11..91.25,
  mpq_sum 4.67..37.9, relief 7.6..66.5.  => left_leg_vas IS a 0-100 VAS in the frame; nrs IS 0-10.
- `se_severity` column present: **False**. build_objective: primary_item=left_leg_vas, primary_scale_factor=0.1 (== scale_factor()),
  item after rescale 2.05..8.45, `D[item] == es[item]*0.1` exactly (allclose True), incumbent (epoch 123) ref = 4.644 NRS,
  J_pain -2.594..+3.806 (NRS points), J_SE == 0.0 on all 92, se_observed_true = 0, J == J_pain everywhere.
- feasible 75 / infeasible 17: the 17 are epochs with NO left_leg_vas rating (J_pain NaN -> isfinite False), NOT side-effect rejects.
  => `feasible` conflates "no rating" with "side-effect rejected" on this stream (cosmetic/label issue, behaviour is right: unrated
  epochs cannot be fitted).
- Safety seed per side: Left 26 tolerated (sev 0) + 12 ceiling anchors (sev 3.0 at 4.5 mA, one per grid rate); Right 30 + 12.
  min_tolerated_h = 72 h. Provenance "stated by PI, 2026-09-14". NO reported severity in the seed.

### Clinic-sheet stream (clinic_pain.load_clinic_steps, consumer stim_optimizer): 472 rows with pain, 29 files
- manifest counts: n_steps 816, n_with_pain 472, n_unparsed_prose 7, n_skipped_no_setting 16 (matches the 2026-09-15 01:25 log).
- Folder: 29 workbooks + template + manifest.json = 31 files (docstring's "29" is right; my earlier "30" counted the template).
- Raw site ranges: overall 2..9 (n=449), head 5..10 (42), back 3..9 (228), left_leg 1..8 (216), left_foot 0..8 (175),
  right_leg 1..9 (154), right_foot 1..8.5 (147). **values_above_10: [] -- nothing outside 0-10 anywhere.** So the sheets ARE 0-10
  NRS and are consumed with factor 1.0 -- no x10, no /10.
- side_effect_score non-null: 15 rows, values {0: 10, 1: 5}, ALL from `2026_Sep2 ... 09_02_2026.xlsx`. No 2/3/4 anywhere.
- July 2025 (07_30_25): 7 rows, rate_known 0 -> all dropped from the epoch frame (documented; no rate/pw recovered).
- Aug 21 2025: only overall+back (no leg columns). Sep 04 / Sep 18 2025: head/back/left_leg/left_foot only (no right side).
- epoch_frame_from_steps: 240 distinct settings; pain_Left_Leg on 118 (1..8), pain_Overall on 230 (2..9); se_severity {None:234,
  none:3, mild:3}; dur_h 0.0028..2.91 h (mean 0.06 h = 3.6 min).
- build_objective on clinic frame: primary_item=pain_Left_Leg, **primary_scale_factor=1.0**, pooled var 2.676 (clinic_own),
  reference epoch 114, J_pain -1..+6 NRS, J_SE {0.0:117, 1.0:1} (one mild epoch penalised exactly 1.0), se_observed 1, infeasible 0.
- Safety seed on clinic frame: Left 80 tolerated + 12 ceiling; Right 75 + 12 (CLINIC_MIN_TOLERATED_H = 0.001 h).
- **Latent defect check**: infeasible (moderate/severe) epochs that would ALSO qualify as severity-0 tolerated anchors: 0 today
  (no moderate/severe on record). The code path has no severity filter (`safety_ceiling.tolerated_anchors` L118-124 keeps
  amp>0 & dur>=min only), so the first sheet row scored 3 or 4 would be BOTH excluded from the pain fit AND fed to the SafetyGP
  as "tolerated, severity 0". Needs a synthetic proof + a fix decision from the PI.
