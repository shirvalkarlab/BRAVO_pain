# Findings: PI rulings 2026-09-21

## The rulings (the PI, verbatim gist)
- Keep the clinic implication of the sensing-pair rule (217): L 0-3+ is only available when the left stimulates on C+1-2-. Critical; record, no code.
- Delete the frozen June log-log model.
- Pool across pulse widths: build option A behind the toggle (decision 189's plan).
- Harmonic rule: a warning on the readiness screen, not blocking.
- Pain-report cap in the matcher: do not remove; make it a warning.
- Chronic-detector routines with zero callers: delete.
- New pain reports rebuild the full-spectrum matrix: yes, the data will be different (no change).
- Audit code leftovers: afterwards.

## Survey (2026-09-21)
- Frozen model: only tests referenced it after 212; `analytics._freq_extrapolated` keeps its own validated range [7.8, 28.3] Hz.
- Chronic detector: the four routines were called only by tests; `_all_data_window` was `sliding_window_analytics`'s only helper. `_cv_logistic_auc` and `_cluster_robust_logit_p` (analytics.py) have no caller either, before and after; not in the ruling, left in place.
- Harmonic mark today: `bravo_service._closed_loop_readiness` adds `qualifying_near_stim_harmonic_hz`, `qualifying_clear_of_stim_harmonics_hz`, `stim_harmonic_notes` per row; the page shows an amber "on a stimulator harmonic" tooltip in `SensingEvidenceTable.js`. Nothing on the row says the cell qualifies ONLY through harmonic bands; the screen's ranking ignores it.
- Matcher cap: `Biomarkers/adapter.align_pros(target="session")` calls the shared matcher with `max_per_rating=None`; its output feeds `pipeline.run_timedomain_branch`, whose `summary` lands on the module response as `summary.timedomain`; the page draws the "Biomarker computed against" block from `data.*` after Compute (index.js ~1012) and the legacy timeline reads `summary.timedomain.band`. The correlation's p is cluster-robust on the report identity (`rating_group_from_identity`).
