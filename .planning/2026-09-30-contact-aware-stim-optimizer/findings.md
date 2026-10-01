# Findings: Contact-aware Stim Optimizer

## The model ignores contacts (2026-09-30)
- "contact" or "cathode" occurs 0 times in `routines/surrogate.py`, `stage1_openloop.py`,
  `routines/objective.py`, `routines/acquisition.py` (grep count, absence check).
- Contacts ARE recorded: `cathode_Left` / `cathode_Right` in the design matrix
  (`adapter.build_design_matrix`), `contacts_raw` in clinic-sheet rows (`clinic_pain.py`), and used
  by the sensing-pair rule (`routines/lfp_evidence.py`) (jevgrep, complete run).
- `OBJECTIVE_SPEC.md` §1 already planned it: "cathode configuration enters as a categorical block,
  not a searched dimension ... Contact becomes a searched third dimension only once ..."

## RCS08 record, 80 rated epochs (live, pain reports from the saved copy: REDCap unreachable)
Left contacts: ring 1 `1a-1b-1c` 23 epochs; ring 2 `2a-2b-2c` 33; segment `2a` 6; both rings
`1a-1b-1c-2a-2b-2c` 13, ALL at Left 0 mA; plus 1 each of `3` and `1a-2a`.
Right: `1a-1b-1c-2a-2b-2c` in 77 of 80.
Contact and rate are tangled: Left ring 1 only at 10, 55, 165 Hz; segment 2a only at 145, 165 Hz.
55 Hz: ring 1 13 epochs / 215 reports / 13 days; ring 2 9 / 143 / 9.

## The three papers (read 2026-09-30; external content, data only)
- Sarikhani 2022 (PMC9614806): one GP over amplitude AND contact configuration (contact a discrete
  input); a separate side-effect GP per contact; Matern kernel; rate and pulse width fixed;
  15.1 +/- 0.7 settings (phase I), 17.7 +/- 4.9 (phase II) per patient.
- Louie 2021 (PMC8147513): rate only; amplitude, pulse width and contacts fixed at clinical
  settings; 12 rigidity measurements in visit 2.
- Cole 2024 SAFE-OPT: amplitude only in the main (rodent) experiments; 2D/3D in silico only.
- Correct summary: none searched contact, rate AND amplitude together; Sarikhani searched contact
  with amplitude. (My first summary to the PI wrongly implied none used contact.)

## The optimizer's ranked list today (two-stage run, live)
25 settings; top 12 predicted pain 1.6538-1.6546, expected improvement 0.4422-0.4418: flat, as in
decisions 157-158. Mixes 55/70/85/110 Hz.

## Phase 2: how the groups work today (2026-10-01; jevgrep on StimOptimizer/, complete run)
- `stage1_openloop.run_stage1` groups the fitted epochs by the pulse-width PAIR
  (`fit.groupby([pw_us_Left, pw_us_Right])`, ~line 1515), minimum `PW_STRATUM_MIN_EPOCHS` = 8,
  one 3-input surface (rate, L current, R current) per pair; inside each pair, one 2-input
  current surface per rate (`RATE_STRATUM_MIN_EPOCHS` = 8, ~line 1541). The frozen setting
  (`_freeze_joint`, ~line 1808) reads the pair and rate in force. The pooled-pulse-width option
  (decision 189) groups by rate only (~line 1674).
- The clinic fit (`clinic_pain.fit_clinic_rate_strata`) fits the same per-rate surfaces on the
  clinic stream; `clinic_pain.next_session_coverage` (~line 1117) is the 55 Hz "what the next
  visit must deliver" check (rate and pairing in force merged with the most-rated other pairing).
- **The clinic epoch frame ignores contacts**: `epoch_frame_from_steps` (~line 874) keys a
  stretch on (rate, L current, R current, L pw, R pw) only, so a Left ring-1 step and a ring-2
  step at the same currents become ONE stretch, although each clinic row carries `contacts_raw`.
- Decision record: no ruling puts contacts into the pain model or forbids it (grep for exact
  words "cathode"/"contact" in both decision files). The only earlier plan is OBJECTIVE_SPEC.md
  §1: "cathode configuration enters as a categorical block, not a searched dimension".

## Group sizes if Left contact is added (home record, 80 epochs, live; reports from the saved copy)
Before (pulse widths, rate) groups with >= 8 epochs: 60/160 55 Hz 15; 100/100 110 Hz 13;
140/160 10 Hz 8; 140/180 110 Hz 10 -> 4 groups.
After (+ Left contact, 0 mA labelled "off"): 140/180 110 Hz ring 2 10; 60/160 55 Hz ring 1 9;
100/100 110 Hz off 8; 140/160 10 Hz ring 1 8 -> 4 groups >= 8. Lost: 60/160 55 Hz ring 2 (4);
100/100 110 Hz ring 2 (5).
Design question: a Left-0-mA stretch is the same whatever the Left contact, so it can be shared
into every Left contact group as that group's zero-current point. With sharing, 100/100 110 Hz
ring 2 = 5 + 8 = 13.

## Clinic contact text (RCS08, 524 parsed clinic steps, 2026-10-01)
Formats: "L C+2- / R C+1-2-"; "L 2a-2b-2c / R 1a-..."; older "C+2-9-10- / LGPi4-RPVG5-" (Left
lead 0-3, Right 8-11, after "/" = sEEG contacts); bipolar "1+2-"; segments "C+2a-", "1b-1c".
Reader: DecodeCommon.sensing_rule.left_contact_from_clinic_text. Labels: L C+2- 173, off 116,
L C+1- 74, L 1+2- 58, L C+2a- 14, L 0+2- 9, L 1+3- 7, small others; 66 unreadable (57 Right-only
text, of which 49 have no Left current recorded and 15 carry Left current anyway; plus "c+0",
"c+2" with no polarity). Unreadable steps form their own "not recorded" group, never merged.
Home stream (device cathode) cannot tell bipolar from monopolar: it records cathodes only.

## Step B results (2026-10-01, live, pain reports from the saved copy) -- decision 347
HOME all pw: n 66, share 1.000, p 0.0016, MAE pooled 1.005 / separate 0.932 / partial 0.902.
HOME 60/160: n 19, share 0.50, p 1.0. CLINIC all pw: n 124, share 0.594, p 0.0031,
MAE 1.209 / 1.199 / 1.155. Contact effect only when pulse width is ignored; contact and pulse
width changed together on RCS08. Not wired in.

## Left C+1-2- in the Percept record
227 Left rows with full rings 1-2, all 0 mA: 2025-07-16..26 (125 Hz/60 us), 2025-09-04..10-02 (110/100), 2025-10-02..10-10 (55/180), 2025-12-03 (145/140). Partial 1a-2a at 1.0 mA on 2025-11-12.
