Good, confirmed gitignored/disposable. Now the write-up.

## Adjacent-duplicate audit — Biomarkers, Stim Optimizer, Closed-Loop Deployment

Method: read the three page directories, then confirmed the data-dependent items against RCS08's live response through three read-only bridge probes (`_agent_bridge/_referent_dup_biomarkers.py`, `_referent_dup_closedloop.py`, `_referent_dup_closedloop2.py` — disposable, already gitignored). Every item below is checked against either the served component source or the actual response text, not assumed from a comment.

### 1. Biomarkers — "How well each band tracks pain" card — the snapshot-served sentence, printed in the always-visible orange caption AND again in the folded "how to read this" drawer

**On screen:** Biomarkers page, the calibrated heat-map card, directly under the "Correlation with pain" heading (always visible) and again inside the closed-by-default "How to read this" drawer at the bottom of the same card.

- Always-visible copy: `DeviceSpectrumCaption` in `Client/src/views/Reports/Biomarkers/BiomarkerHeatmapGrids.js:597-599`, drawing `deviceSpectrumBullets(sw)` (`Client/src/views/Reports/Biomarkers/gridReadouts.js:124-135`). Confirmed live for R 0⁻3⁺: "358 of 451 matched reports (79%) had no voltage trace in the match window and were read from the device's 30 s FFT snapshots: a row of N s uses the nearest ceil(N/30) snapshots, or nothing."
- Drawer copy: one of the response's own `notes` (field `band_time_sweep.<channel>.notes`, generated in `BRAVO/modules/Biomarkers/routines/analytics.py:6141-6146`), pulled into the drawer by `bulletsFor()`'s `...notes.slice(3)` at `BiomarkerHeatmapGrids.js:128`. Confirmed live, same channel: "358 of this contact pair's matched pain reports were answered from the device's own FFT snapshots rather than the voltage trace, and the most affected cell drew 79% of its reports that way. A pain report with no voltage trace within the match window is answered from the device's own FFT snapshots instead. Each snapshot covers 30 s, so a row of N seconds takes the nearest ceil(N / 30) snapshots within the window..."

Same three numbers (358, 79%, the ceil(N/30) rule) in near-identical wording, in the one card. The comment at `BiomarkerHeatmapGrids.js:117-120` claims this was already fixed ("the snapshot bullet is gone from here because the orange caption above the grid already carries it") — that is true only of the frontend's own static bullet, which was removed. It is false for this sentence, because the sentence is generated server-side and unconditionally appended to `notes` whenever `n_dev_reports` is truthy, so it still flows through `notes.slice(3)` into the drawer regardless of what the frontend intends. This is the exact class the task names as caught twice by eye on 2026-09-15.

**Keep:** the always-visible caption (`DeviceSpectrumCaption`) — it sits next to the numbers it explains and is computed independently from the same grid fields the reader is already looking at.
**Fix:** backend. Stop appending the device-spectrum sentence to `analytics.py`'s `notes` list at lines 6141-6146 (the frontend caption already covers it from `n_pain_reports_from_device_spectrum` / `device_spectrum_total_grid`, which stay on the response for anyone reading it programmatically). A frontend-only fix (filtering the string out of `notes.slice(3)`) would work but is fragile against reworded backend text.

### 2. Closed-Loop Deployment — sticky verdict header — the "provisional: N of 3 intervals span zero" count, printed in the headline sentence and then again in full, twice, side by side

**On screen:** Closed-Loop Deployment page, the sticky verdict card at the very top — the first thing a clinician reads, on every scroll position.

- Headline: `DeploymentDecisionHeader.js:113-116` — `` `...the evidence supports it on point signs alone (provisional: ${provisional.n} of ${provisional.total} intervals span zero)` ``. Confirmed live for the ZERO_TWO_LEFT/24.5 Hz candidate: `provisional.n = 2`, `provisional.total = 3` (from `verdict_detail.n_edges_unestablished` / the edge count, `bravo_service.run_for_participant`).
- Two full detail boxes immediately below, one under the "evidence" cell and one under the "transcription" cell, both built from the same `ProvisionalNote` component (`ProvisionalNote.js:72-93`) called at `DeploymentDecisionHeader.js:157-158` with the identical `data={rep}`. Each renders: "PROVISIONAL — POINT SIGNS ONLY; 2 OF 3 INTERVALS SPAN ZERO" plus the E1/E2/E3 lines.

So within one glance at the top card, the count "2 of 3 intervals span zero" is stated three times (headline, evidence-cell box, transcription-cell box), and the two boxes are byte-for-byte identical to each other.

**This one is largely deliberate** — see the "deliberate repeats" section below; `ProvisionalNote.js:13-17`'s own docstring explains why it is drawn in more than one place. It is listed here, ranked high, because it is the highest-traffic block on the whole platform and because the *headline's own inline count* is a fourth, unplanned echo of the same number, beyond the two documented placements.
**Keep:** the two boxes under the Evidence and Transcription cells (documented, intentional — a reader who looks at only one cell must still see the caveat).
**Fix:** frontend, narrow. Drop the parenthetical count from the headline sentence itself (`DeploymentDecisionHeader.js:114-115`) and let it read "...supports it on point signs alone (see below)" — the two boxes two lines down already carry the number and the detail; the headline repeating it adds a third copy of the same fact with no added information.

### 3. Closed-Loop Deployment — Upper/Lower LFP threshold row — the design-rule note and the occupancy note both open by restating the averaging duration in force

**On screen:** Closed-Loop Deployment page, "Full parameter recommendation" card, directly under the Upper LFP threshold value (and again under Lower LFP threshold) — always visible, never folded.

- `design_rule_note` (`BRAVO/modules/ClosedLoopDeployment/prescription.py:847-851`), rendered at `PrescriptionPanel.js:247-252`. Confirmed live: "Noise-only design rule (fitted on this participant's own recordings, L4 two components): the stored pair is ±2.6 from its midpoint; the rule needs ±5 **at this timing (3 s averaging / 30 s onset)**..."
- `occupancy_note` (`BRAVO/modules/ClosedLoopDeployment/occupancy.py:136-140`), rendered directly beneath it at `PrescriptionPanel.js:257-262`. Confirmed live: "**At the 3 s averaging duration in force**, 32608 averaged readings: 43.9% above the upper threshold..."

Both sentences open by naming the same fact — the averaging duration currently in force, 3 s — independently computed and independently worded, stacked as the first two lines under the same field. Each note does go on to say something the other doesn't (the design rule's required separation; the occupancy fractions), so this is not pure restatement, but the shared opening clause is the same number stated twice in a row.

**Keep:** `occupancy_note` — the averaging duration is load-bearing to its own percentages ("at the 3 s averaging duration, 43.9% above..."), so it cannot drop the number without becoming unreadable.
**Fix:** backend, small. In `design_rule_note` (`prescription.py:847-851`), drop the parenthetical restating the timing when `occupancy_note` is about to be attached to the same field (or simply say "at the timing shown above" once both notes are known to co-occur, which they always are — both are attached by `attach_design_rule`/`attach_occupancy` to the identical Upper/Lower LFP threshold fields). Low risk since both functions already take the same `averaging_ms`/`onset_ms` inputs.

### 4. Closed-Loop Deployment — Upper/Lower onset duration row — the block-bootstrap onset interval, stated by `robustness_note` and restated (with a different, stale number) inside the folded "Why this value" text

**On screen:** same "Full parameter recommendation" card, Upper/Lower onset duration rows — `robustness_note` is always visible; the conflicting restatement is one click away behind "Why this value."

- `robustness_note` (`BRAVO/modules/ClosedLoopDeployment/prescription.py:1003-1009`), always visible: confirmed live, "...the onset duration a designer replaying the real Dual Threshold controller against this record would pick ranges from **27 to 30 s**..."
- The field's own `why` text, a fixed template in `BRAVO/modules/ClosedLoopDeployment/timing_recommendation.py:64`, behind the "Why this value" fold: "...A block bootstrap over the recordings puts **36-90 s** in the same recommendation."

Both sentences describe the identical quantity (the block-bootstrap onset interval, "one recommendation, not a single number") for the same field on the same candidate, and they disagree (27–30 s vs. 36–90 s) because `timing_recommendation.py`'s `why` text is a fixed, generic string written once for the reference contact used in decision 155, while `robustness_note` is computed live per candidate. This is the failure mode duplication invites: the two copies drifted.

**Keep:** `robustness_note` — computed fresh for the candidate actually on screen.
**Fix:** backend. Remove the specific "36-90 s" sentence from the static `why` text in `timing_recommendation.py:64` (the general point about the recommendation being a range, not a point, can stay in prose; the number belongs only to `robustness_note`, which already carries it correctly per candidate).

### 5. Stim Optimizer — "may it start on the frozen setting?" card, condition "Rate at or above the adaptive minimum" — the always-open Numbers panel and the folded Sentence restate the identical rates

**On screen:** Stim Optimizer page, "Closed loop: may it start on the frozen setting?" card, first condition row — the rate numbers are always visible; the restatement is one click away behind "Sentence."

- Always-visible: `Numbers()` case `"rate_at_or_above_adaptive_minimum"`, `ClosedLoopChecks.js:101-111` — prints `L {rate} Hz · R {rate} Hz` and `minimum {min} Hz` straight from `evidence.rates`/`evidence.min_rate_hz`.
- Folded "Sentence" (`c.detail`, `ClosedLoopChecks.js:295-299`): backend text from `BRAVO/modules/StimOptimizer/routines/stage_gate.py:387-391` — "every frozen rate is at or above the adaptive minimum of {min} Hz (Left {rate} Hz, Right {rate} Hz)" — the same two rates and the same minimum, in prose.

**Keep:** the open Numbers line — a clinician scanning the four-check strip reads the numbers there, not in a fold.
**Fix:** backend, optional. `check_rate_at_or_above_minimum`'s passing-case `detail` (`stage_gate.py:387-391`) could drop the parenthetical rate list and just say "every frozen rate is at or above the adaptive minimum of {min} Hz" — the per-side rates are already in `evidence.rates`, which the frontend already renders. Low priority: it is folded, and the fold's whole job in this file's own design ("symbols and numbers in the open, sentences folded") is to let a reader who wants the full reasoning re-read the numbers restated in prose, so this is closer to acceptable than items 1–4.

### 6. Stim Optimizer — sensing-evidence table — the current-limit value, stated in the always-visible sub-caption and again inside the folded footnote

**On screen:** Stim Optimizer page, the sensing-evidence table's sub-caption directly under its headline (always visible) and its "What 'usable' requires..." fold at the bottom of the same card.

- Always visible (`SensingEvidenceTable.js:87-91`): "...evidence above the {cap} module cap is excluded" (or "Current limit {cap}." when no per-side ceiling exists).
- Folded (`SensingEvidenceTable.js:190-192`): "...the currents tested sit at or below the flat {cap} limit. That limit is PI-declared and was established by testing at 165 Hz..."

**Keep:** the always-visible sub-caption, since it sits with the count that depends on it.
**Fix:** frontend, low priority. The fold adds real information (provenance, the withdrawn energy-matched model) that the caption does not, so this is closer to elaboration than pure duplication; if trimmed, drop the bare restatement of the number from the fold's first clause and start straight from "That limit is PI-declared...".

---

### Repeats that are deliberate — do not remove

- **Closed-Loop `ProvisionalNote` under the Evidence and Transcription cells** (`DeploymentDecisionHeader.js:157-158`, `ProvisionalNote.js:13-17`). The component's own docstring states the reason: the same caveat has to appear wherever a reader's eye might land — under "does the evidence support it," under "is there anything to transcribe," and again on the parameter table itself (`ProvisionalNote` inside `PrescriptionPanel.js:640`). Only the headline's own extra inline count (item 2 above) should go; the three placed boxes are load-bearing by design.
- **`PrescriptionPanel.js`'s two-mode view vs. the selected-mode view.** The mode banner, coupling banners, and field notes are drawn once per active threshold mode (Dual/Single/Single Inverse); switching modes remounts the row subtree on purpose (`PrescriptionPanel.js:678-681`) so a value from one mode is never mistaken for another's. This looks like repetition across a session but is never two modes on screen at once.
- **`design_rule_note` / `occupancy_note` / `startup_bias_note` / `robustness_note` all being attached to their own field rows independently** (`prescription.py:861-1034`). Each is its own named check (design rule, occupancy, start-of-recording bias, block-bootstrap robustness) with its own docstring explaining it is placed "for the same reason the [other] note is — a fact about this configuration on this record, not only a justification behind the fold." Having four notes on the threshold rows is intentional layering of four different checks, not one fact stated four times; only the specific overlap in item 3 (both restating the timing) should be trimmed, not the pattern itself.
- **`Client/src/views/Reports/StimOptimizer/DecisionStrip.js`'s "search prefers" setting vs. `TwoStagePlanCard.js`'s folded "fit for each pulse width and side" table.** `TwoStagePlanCard.js`'s own comment (lines 6-9) records that the frozen setting was deliberately moved out of this card and into `DecisionStrip` "so they are not printed twice." The folded strata table still lists the frozen stratum's own rate/current alongside every *other* fitted stratum for comparison — that is supplementary context (seeing the winner next to its rivals), not the same fact restated, and it is behind a fold by design.