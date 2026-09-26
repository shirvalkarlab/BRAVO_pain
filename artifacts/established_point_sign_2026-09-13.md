# "Established means the mean only": the point sign decides, the interval is a caveat

**2026-09-13, branch `PS_closedloop_deployment`.** Everything below is on the **Closed-Loop
Deployment page**, in the Closed-Loop Deployment module (`BRAVO/modules/ClosedLoopDeployment/`).

## 1. The rule

The Closed-Loop page judges a band on three measured relationships, drawn as a triangle: how band
power moves with stimulation current (E1), how band power moves with pain (E2), and how pain moves
with current (E3). Each relationship has a point estimate (the number itself), a 95% interval
around it, and a p-value. Until today a relationship counted as "resolved" only when its interval
excluded zero; if the interval spanned zero the page treated the relationship as having no
direction at all, the sign-agreement test could not run, and the verdict at the top of the page
read "unsupported".

The PI's rule, 2026-09-13, his words: **"Established means mean only for flexibility."** Three
readings were put to him and he chose **"point sign decides, but flag as provisional"**:

- a relationship has a direction when the sign of its point estimate is + or −;
- the interval and the p-value stay on the page as caveats and block nothing;
- when any of the three intervals spans zero, the verdict is flagged provisional and says so:
  `supported (point signs only; N of 3 intervals span zero)`.

He was told, and accepted, that on RCS08 this turns the verdict from "unsupported" to a
provisional "supported".

What still blocks, unchanged (decision 9, "absence of evidence is not permission"): a relationship
with **no** estimate at all (nothing could be computed), or one of exactly zero, has no sign and
still blocks; a sign pointing the wrong way for the control law still blocks. Only the interval
stopped gating.

## 2. What changed, file by file

**Backend, `BRAVO/modules/ClosedLoopDeployment/`**

- `types.py` — `EdgeEstimate.resolved` now means "the point estimate is finite and not zero" (the
  sign is + or −). The old rule, "the interval excludes zero", is kept as a new field,
  `EdgeEstimate.statistically_established`, which every page and ledger row prints beside the sign
  and which no gate reads. `EdgeEstimate.sign` now returns "no sign" for a NaN estimate (it used
  to read a NaN as −1, which mattered nowhere while the interval gated and would have mattered
  everywhere once the sign alone did). `DeploymentReport` gains `n_edges_unestablished` (how many of
  the three intervals span zero or are absent) and `provisional` (True when that count is above
  zero AND the report is licensed). `is_licensed` is unchanged in code; its docstring records the
  rule, the date, his words and the reading chosen.
- `consistency.py` — the sign-agreement test reads the point sign; the note it writes now carries a
  PROVISIONAL sentence naming each relationship whose interval spans zero with its interval and p.
- `pipeline.py` — the "sign established" flags the D19 device-rule row prints beside each sign read
  `statistically_established` by name (the same value they carried before).
- `authority.py`, `d26_capture_verdicts` — the two D26 capture checks ("inverted capture",
  "thresholds too close") are judged on the sign of the pooled titration slope; an interval
  spanning zero is now a CAVEAT sentence on both, with the interval and p, and no longer raises the
  predicted RECAPTURE THRESHOLDS alert. They still warn and never block (decision 139).
- `adapter.py`, `report_to_dict` — the verdict string carries the flag when licensed and
  provisional; `verdict_detail` gains `provisional`, `n_edges_unestablished`, `n_edges`,
  `unestablished_edges`, `all_edges_statistically_established`; each edge gains
  `statistically_established`.

**Page, `Client/src/views/Reports/ClosedLoopSim/`**

- `ProvisionalNote.js` (new) — the one provisional line, drawn in three places and never inside a
  fold: the count, then each relationship whose interval spans zero as numbers ("E1 sign −: −3.788
  [−12.505, +4.929] p = 0.42").
- `DeploymentDecisionHeader.js` — the sticky verdict card at the top of the page. When the verdict
  is provisional the headline reads "…the evidence supports it on point signs alone (provisional:
  N of 3 intervals span zero)" in the warn colour, and the provisional line sits under BOTH the
  "DOES THE EVIDENCE SUPPORT THIS CONFIGURATION?" track (lit SUPPORTED) and the "IS THERE ANYTHING
  TO TRANSCRIBE TODAY?" track.
- `stateTracks.js` — the SUPPORTED / NOT ESTABLISHED wording: NOT ESTABLISHED now means "at least
  one edge has no point estimate".
- `PrescriptionPanel.js` — the "Full parameter recommendation" card prints the provisional line
  above the values it shows.
- `DeploySignoffCard.js` — the "Deploy-to-Percept review" sheet's VALUES TO TRANSCRIBE block prints
  the module's verdict string and the provisional line, so the printed record carries the caveat.
- `EvidenceTrianglePanel.js` — each edge's label reads numbers, not adjectives: "SIGN −
  (INTERVAL SPANS ZERO)" or "SIGN − (INTERVAL EXCLUDES ZERO)" or "NO POINT ESTIMATE"; the point
  marker is filled when the interval excludes zero and hollow when it spans zero; in the triangle
  drawing an edge with a sign now carries its arrowhead and the small text under it reads
  "sign − (interval spans zero)".
- `WhatWouldChangeThis.js` — a provisional verdict lists one item: which intervals span zero and
  that only a titration session moves them off zero.

## 3. Tests (host suite, pytest)

New file `ClosedLoopDeployment/tests/test_established_means_point_sign.py`, 15 tests: a non-zero
estimate with an interval spanning zero is resolved and not established; None and NaN estimates
are unresolved (and NaN has no sign); an estimate of exactly zero is unresolved; no interval means
not established; three right signs all spanning zero is licensed AND provisional with
`n_edges_unestablished == 3`; all established is licensed and not provisional; two of three counts
two; a wrong-way sign is not licensed whatever the intervals; a missing estimate still blocks; a
device refusal reads "blocked", never provisional; the serialised verdict reads exactly
`supported (point signs only; 3 of 3 intervals span zero)`; the established case reads plain
`supported`; D19's flags read the interval rule by name; the D26 verdicts follow the sign and
carry the caveat.

Nine existing tests pinned the old rule and were rewritten to pin the new one with the reason in
their docstrings (none deleted; two were split so the part that still holds is its own test):
`test_core.py` (4, one split into two), `test_bootstrap.py` (1), `test_d19_point_signs_and_d30_active_group.py`
(1), `test_d26_reads_pooled_slope.py` (1, split into two), `test_review_2026_09_12_sides_and_ledger.py` (1).

## 4. Before and after on RCS08, through the bridge, the page's own request shape

Two bands at 24.5 Hz, 5 Hz wide, Left side, Dual Threshold. Captured before any edit, then after.
Every field compared exactly; never a tolerance.

| | L 1⁻3⁺ (the band in the PI's browser) | L 0⁻2⁺ (the committed band) |
|---|---|---|
| verdict | `unsupported` → `supported (point signs only; 2 of 3 intervals span zero)` | same change |
| licensed | False → True | False → True |
| provisional / n unestablished | (absent) → True / 2 | (absent) → True / 2 |
| E1 estimate, interval, p, sign | −3.788, [−12.505, +4.929], p 0.419, sign −1 (unchanged) | −4.445, [−18.616, +9.726], p 0.539, sign −1 (unchanged) |
| E1 resolved / established | False → True / False | False → True / False |
| E2 estimate, interval, p, sign | +0.058, [−0.083, +0.197], p 0.46, sign +1 (unchanged) | +0.088, [−0.023, +0.195], p 0.12, sign +1 (unchanged) |
| E2 resolved / established | False → True / False | False → True / False |
| E3 estimate, interval, p, sign | −0.154, [−0.269, −0.039], p 0.0086, sign −1 (unchanged) | same numbers (unchanged) |
| E3 resolved / established | True → True / True | True → True / True |
| sign agreement (coherent) | None → True | None → True |
| D19 row | satisfied, recorded, both times; observed line names both unestablished signs with interval and p | same |
| D26 row | before: advisory failed (alert predicted because the interval spanned zero); after: passes and leaves no row (the alert follows the sign) | not assessed both times (no pooled slope is stored for this band) |
| D26 capture verdicts | inverted: not indicated both times; too close: "not established" → "not indicated" with the caveat; predicted alert True → False | not assessed both times |
| thresholds upper / lower | 210.579 / 161.903, unchanged | 196.129 / 190.890, unchanged |
| capture currents | 1.4 / 4.8 mA, unchanged | 1.4 / 4.8 mA, unchanged |
| parameters block present | True before and after | True before and after |

**Why 2 of 3 and not 3 of 3.** The brief expected "3 of 3"; the data say 2 of 3 on both bands: E3
(pain on current) has an interval of −0.269 to −0.039 that excludes zero, so it was established
before and after. The count is read from the data.

**Why the parameters block is present both times.** The "Full parameter recommendation" card
withholds its values on the DEVICE answer (whether the 51 device rules permit the configuration),
not on the evidence verdict, and the device has permitted both bands since decision 135. What
changes today is the caveat printed on that card, and the verdict above it.

**Field counts.** L 1⁻3⁺: 49,341 fields before, 49,343 after, 49,333 in common, 104 differing,
0 of them timing fields. Of the 104: the verdict, `licensed`, the two `resolved` flags, the
sign-agreement result and note, the four D26 sentences (caveat wording), `too_close.status`,
`predicted_recapture_alert`, and the eligibility summary count (30 → 29 advisory rows) account for
19; the other 85 are the advisory list shifting by one slot after the D26 row left it. **Keyed by
rule id, the ledger has 120 fields compared on the 30 rows present both times, 0 differing**, and
one row (D26) present only before. 8 fields only before (that D26 row), 10 only after (the new
flags). L 0⁻2⁺: 49,326 before, 49,334 after, 49,324 in common, 10 differing: the verdict,
`licensed`, the two `resolved` flags, the sign-agreement result and note, and three from the CL-DBS
simulation card's own bookkeeping (`n_pieces` 46,118 → 0, `already_stored`, `active_model`):
the first run built and stored the simulation and the second read it back, which is the store
doing its job and nothing this change touched. **Ledger keyed by rule id: 124 fields on 31 rows,
0 differing.** On both bands: **every edge number, 21 compared, 0 differing; thresholds, 8
compared, 0 differing; prescription fields, 48 compared, 0 differing.**

## 5. Suites, build, workers

- host: `1086 passed, 2 skipped, 0 failed, 0 errors  [parallel: 1085 passed, 2 skipped in 10.23s | store, serial: 1 passed, 1087 deselected in 0.39s]` (baseline 1069 / 2 / 0; +17 = 15 new + 2 splits)
- container: `PASS=631 FAIL=0 LIVE_SKIPPED=6` (unchanged)
- frontend: `Compiled with warnings.`; none of the seven touched files appears in the warnings;
  "point signs only", "INTERVAL SPANS ZERO" and "no point estimate" are in
  `Client/build/static/js/576.08f0ab97.chunk.js`; "DIRECTION NOT ESTABLISHED" is absent from every
  chunk. The page's own jest tests: 30 passed, 2 failed — the same 2 fail on the committed tree
  before this change (they look for "NOT COHERENT" and "1 of them can be resolved at the
  programmer", wording renamed on 2026-09-11 and earlier), so they are not from this work and are
  left for the orchestrator.
- workers reloaded (`kill -HUP 1`; 5 gunicorn processes after).

## 6. Not watched

The page was not watched in a browser this session (no login; typing a credential is a hard
limit). The chunk check above is the proof the panel reached the served bundle.

## Correction, 2026-09-26 (decision 290)

The E2 rows of the table in section 4 (+0.058, interval -0.083 to +0.197, p 0.46 on L 1-3+; +0.088,
-0.023 to +0.195, p 0.12 on L 0-2+) were computed on the pain ratings of the settings period BEFORE
each 3 s piece's own: the Closed-Loop joined table matched the period's position (counted from 0)
against the ratings' period number (counted from 1), from the module's first build on 2026-09-03 until
2026-09-25. The before/after comparison in this document stands, because both captures used the same
join; the E2 values do not. Re-measured on 2026-09-26 on the full saved tiles with the join fixed:
L 1-3+ at 24.5 Hz under NRS reads an area under the curve of 0.564 (0.438 to 0.678), p 0.29, 43 pain
reports, that is +0.064 on this table's scale. Its interval still spans 0.5, so the "2 of 3 intervals
span zero" in this document is unchanged. L 0-2+ was not re-measured: it is not a sensing pair the
device allows with today's contacts (decision 217). Full numbers: decision 290 in
`DECISIONS_and_open_items.md` and `docs/decision_log_full_2026-09-19.md`.
