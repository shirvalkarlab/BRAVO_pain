# Archive — what was here, and which document carries it now

**Archived 2026-09-07 at commit `705bdb0`, at the PI's instruction.** His words: *"There are too
many Handoffs going on now."* The repository root held 53 markdown files, 51 of them handoffs,
audits, validation reports, plans or superseded correction summaries.

**Nothing was deleted.** Every file was moved with `git mv` where it was tracked, so history
follows it; three untracked files were moved in place.

**The five documents that replace all of this now live at the repository root:**

| Replacement | What it owns |
|---|---|
| `DEVICE_percept_rc.md` | every Medtronic Percept RC fact — the three threshold modes and their timing, the recording products and their exact JSON keys, the two different quantities both written LSB, and every calibration constant stated as what it converts from and to and whether it was measured on simultaneous recordings or composed by chaining |
| `ARCHITECTURE_modules_and_store.md` | the three modules, the store, the formats, Redis and MySQL, where a request spends its time, the three spectrum builders, and the named routines and response keys |
| `METHODS_measurement_and_findings.md` | the measurement rules, the two multiple-comparison corrections, the live results on RCS08 with the limit on each, and every retraction |
| `OPERATIONS_runbook.md` | the container, the two test runners, the frontend rebuild, and every trap already paid for |
| `DECISIONS_and_open_items.md` | the numbered decision log, the single list of open items, and the commit lineage |

**The resolution record is `.planning/2026-09-06-cache-store-and-record-consolidation/findings.md`
§1** — 30 contradictions found across the source documents, each resolved to the newer result, with
the losing claim named so it cannot re-enter by being re-read here.

---

## READ THIS BEFORE TREATING ANYTHING IN THIS FOLDER AS CURRENT

**Every file here is superseded.** They are kept for audit, for provenance, and because four of the
mistakes in them are the lesson. Three specific hazards:

1. **Every code line number in every file here has moved.** All of them. The current locations are
   in `findings.md` §2.
2. **Every test-suite count here is stale**, and they were stale within the sessions that wrote
   them. One reached a pushed commit message that cannot be edited. **No count appears in any
   replacement document** — the two runner commands are given instead.
3. **`README_BIOMARKERS_AND_DEPLOYMENT.md` describes machinery that does not exist**: a device-writing
   endpoint and two credentials for it, and a firmware version and a value range for the threshold.
   All were confirmed absent from every Python and JavaScript file in the repository. **The platform
   produces a configuration for a clinician to program by hand. There is no interface that writes to
   the device.**

---

## What replaced what

### The consolidated record

| Archived | Replaced by |
|---|---|
| `MEGA_HANDOFF.md` | **all five.** Its reference sections §1 to §9 were ported in full. **Its §0, about 4,000 lines of session-by-session narrative, was NOT ported line by line** — its durable content is what §1 to §9 existed to hold, and the two most recent sessions are covered by the handoffs listed below. That narrative remains here as the historical record. |
| `HANDOFF.md` | all five |
| `README_BIOMARKERS_AND_DEPLOYMENT.md` | all five, with the three corrections its own reconciliation demanded incorporated, and the two nonexistent sections dropped |
| `README_CORRECTIONS_RECONCILED_2026-09-06.md` | `findings.md` §1 — its six re-checked corrections are rows in the supersession register |
| `README_CORRECTIONS_SUMMARY.md` | superseded twice: first by the reconciled version above, now by `findings.md` §1 |
| `PLAN_cache_store_phase2_2026-09-07.md` | `.planning/2026-09-06-cache-store-and-record-consolidation/task_plan.md`, and the approved plan artifact. **Its 30 step titles are preserved verbatim** so progress reports against them still line up. |

### Device and calibration

| Archived | Replaced by |
|---|---|
| `HANDOFF_TD_LSB_calibration_2026-06-27.md` | `DEVICE_percept_rc.md` §6 to §8 — the constants, the transform recipe, the calibration quality, the pairing rules, and the diagnostic. **Note: its §3.2 specifies a Welch-256 backup at 269 that was deleted from the code on 2026-06-28 and no longer exists.** |
| `CS3_FFTBinData_units_recon_2026-06-27.md` | `DEVICE_percept_rc.md` §6 — the 4.789 ratio and that the device's spectrum is linear microvolt magnitude |
| `INGEST_BrainSenseLfp_pairing_audit_2026-06-27.md` | `DEVICE_percept_rc.md` §7 — which streams are simultaneous, and the pairing rules |
| `METHODS_lsb_estimation.md` | `DEVICE_percept_rc.md` §6 and §10. **The served copy at `Client/public/static/docs/METHODS_lsb_estimation.html` is untouched by this move.** Its tier ordering is superseded by decision 21. |
| `ANALYSIS_percept_spectral_repro_comparison.md` | `DEVICE_percept_rc.md` §7 — the exact reproduction of the reference implementation as the anchor result |

### Statistics, methods and findings

| Archived | Replaced by |
|---|---|
| `VALIDATION_report_RCS08.md`, `VALIDATION_report_RCS08_v2.md` | `METHODS_measurement_and_findings.md` §5 |
| `PARITY_audit_validation_vs_backend.md` | `METHODS_measurement_and_findings.md` §3 and §5 |
| `AUDIT_concat_vs_PRO_matching_RCS08.md` | decision 3 — the concatenation repair is robust to matching, 67 against 67, zero changes |
| `AUDIT_streaming_concatenation_RCS08.md` | decision 4 — windows over 10 percent missing are dropped entirely |
| `AUDIT_stream_exclusions_RCS08.md` | `METHODS_measurement_and_findings.md` §2 |
| `HANDOFF_taskB_spectral_exploration.md` | `METHODS_measurement_and_findings.md` §3 and §5 |
| `AUDIT_TRIAGE_medium_low.md`, `AUDIT_TRIAGE_v2_decisions.md`, `AUDIT_TRIAGE_v3_decisions.md` | `DECISIONS_and_open_items.md` open item 15. **The audit of record is the artifact `closedloop_audit_report.md`, version `e3a12136-e0e1-4fff-b95f-baa42d0a0a46`**, and these three are its decision sheets. |
| `FIXHANDOUT_MASTER_biomarker_fixes.md` | the decision log |

### Platform and modules

| Archived | Replaced by |
|---|---|
| `BIOMARKERS_STIMOPT_CONSISTENCY_REPORT.md` | `ARCHITECTURE_modules_and_store.md` §1 and §6 |
| `CLD_REBUILD_REPORT.md` | `ARCHITECTURE_modules_and_store.md` §8 |
| `HANDOFF_session_psd-cache_ui-fixes.md` | `ARCHITECTURE_modules_and_store.md` §2 and §8 |

### Session narrative — durable content ported, the blow-by-blow kept here

The 22 `SESSION_HANDOFF_*` files and the four `HANDOFF_biomarker_2026-06-23*` files. Their durable
content is in the five replacements; **their value now is the reasoning behind a change, which the
five documents summarise rather than reproduce.** The four that a future reader is most likely to
want:

| Archived | Why it might still be worth opening |
|---|---|
| `SESSION_HANDOFF_2026-09-07_cache_store_takeover.md` | the cache design as approved, the format measurements, the ten parallel lanes |
| `SESSION_HANDOFF_2026-09-06_sweep_ramp_and_matcher.md` | the sweep, the measured ramp, the 21.4x matcher, and the proof that the mount claim was wrong |
| `SESSION_HANDOFF_2026-09-05_clinic_steps_and_ramp.md` | the clinic sheet against the device's own record |
| `SESSION_HANDOFF_2026-09-02_two_stage_and_ordinal_safety.md` | the two-stage screen and the safety gate |

---

## The port was machine-checked, not asserted

Every number, code identifier, JSON key, file path and commit hash was extracted from all 51
archived files and from the five replacements plus the three planning files, and the difference was
read item by item. **Of the names mentioned three or more times in the archive and initially
absent, the check drove them down by roughly a fifth to a half depending on category, and every
remaining item was then classified rather than left unexplained.**

**Thirty-five identifiers the check flagged were confirmed live in the current source and have been
ported.** Seven named script files were confirmed to be session-only scratch and are named as such
in `ARCHITECTURE_modules_and_store.md` §11 so a reader who meets one here knows it is not module
code.

**The checker's two known limitations, stated so nobody reads its output as a clean bill:**

1. **It treats the same file cited with a different path prefix as two different items**, so
   `Biomarkers/routines/analytics.py` and `BRAVO/modules/Biomarkers/routines/analytics.py` both
   appear as gaps when only one spelling was carried. A meaningful part of the residual path gap is
   this.
2. **It cannot tell a superseded number from a dropped one.** Most of the residual numeric gap is
   exactly what the PI asked to be dropped — stale line numbers, stale suite counts, timings from
   sessions whose code has since changed, and the losing side of the 30 resolved contradictions.

The full item-by-item gap list is `port_gap_report.json`, saved as an artifact alongside this
index.
