# Progress

## 2026-09-20 (the PI: two sub-agents, audit calibration usage and LSB storage / timeline matching)
- Plan created with /pwf. Two read-only audit agents launched in the background (A: calibration usage; B: storage, the timeline's matching step, an acquisition-timeline design). Waiting on their reports.
- Both audits back (A: 275k tokens, 62 tool uses; B: 279k, 50). Findings filed in findings.md; A's finding 1 and B's A1/A6 re-read in the code and confirmed. Nothing changed yet.
- The PI: the 9/16 titration session was run in full. Re-read from the device's current record: streaming restarted twice; only a rise counted. 0a (join recordings under 20 s with the current held; `prev_current_mA`) and 0b (both legs, `leg` tag) built test-first: RED 9/11, GREEN 11; suites 1392 / 2 / 0 and 702 / 0; jest 47 + 2 known. Live: left 9/16 ladder 1+4 -> 8 in one run; 4 of 15 runs >= 8; run points 4,845 -> 8,353; E1 L 1-3+ n 18 -> 33, p 0.21 -> 0.72; verdicts unchanged. Rebuilt; reloaded. Decision 213.
- Item 1 (214): `empirical_lsb_ratio` on unscaled microvolts with the transform, compared with the constant in effect. RED 3/4, GREEN 4; jest pin written after the edit (not watched red). Suites 1392 / 2 / 0 and 704 / 0. Live: 193 fields, 8 differing (all lsb_ratio); ratio 8.1e-5 -> 0.00283 = 1/352.7, 0.98× the constant, confidence low -> high. Rebuilt; reloaded.
