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
