# Audit, 2026-09-15: the Google Drive clinic sheets, the side-effect penalty, and the pain scale

**Scope.** Three questions the PI asked on 2026-09-15, answered with proof rather than assertion:

1. What data was imported from the Google Drive clinic and at-home testing sheets, and is it intact?
2. How do side-effect scores shape the penalty inside the Bayesian optimizer (the Stim Optimizer module)?
3. How are the verbal pain scores from the sheets, and the REDCap pain items, put on one scale? The PI's stated understanding was "scaled to 0-100, multiply by 10 if they are 0-10 scores".

**Method.** Every line of the objective, the ingest and the safety model was read (file and line numbers below). Then a read-only probe was run inside the server container on RCS08's real data through the agent bridge (`BRAVO/_agent_bridge/_audit_scale_se.py`, job 20260915-093710-adf061b3), plus a second job for a synthetic check and the three test files that pin these rules (job 20260915-093843-38c4f0bb; 64 tests, 64 passed). No code was changed.

---

## The short answers

| Question | Answer | Proof |
|---|---|---|
| Is the Drive data intact? | **Yes.** 29 workbooks + 1 template on disk, every file's sha256 equals the Drive download manifest. | §1 |
| Are the sheets' verbal pain scores 0-10? | **Yes, and they are used as written.** 1,411 scores across seven body sites; the largest is 10.0 (head), nothing above 10. Multiplier applied: 1.0. | §3 |
| Are the REDCap pain items rescaled? | **Yes, by dividing by 10, not multiplying.** `left_leg_vas` runs 20.5-84.5 in the raw data and 2.05-8.45 after the rescale. | §3 |
| So is "0-100, NRS x10" right? | **No -- it is the other way round.** The common scale is **0-10**. The 0-100 items are divided by 10. The result is the same ordering of settings, but the penalty is calibrated on the 0-10 scale, so the direction matters and the code is internally consistent. | §3 |
| How does a side-effect score become a penalty? | A four-step ladder in NRS points: none = 0, mild = 1.0, moderate = infinite, severe = infinite. Infinite means the setting can never be chosen, whatever its pain benefit. No report at all = 0, but flagged as "not observed". | §2 |
| Which side-effect data reaches the optimizer today? | **Almost none.** REDCap has no side-effect field (penalty 0 on all 92 epochs). Of the 29 sheets, only the 2026-09-02 sheet has a numeric side-effect column: 15 rows, ten scored 0 and five scored 1. One fitted epoch carries a mild penalty of exactly 1.0. | §2, §4 |
| Does the safety model use reported side effects? | **No.** It is seeded only from (a) the PI's stated 4.5 mA ceiling per side and (b) every setting held long enough, treated as tolerated. | §2 |
| Anything wrong? | **One latent defect, proven synthetically, zero live instances today:** a setting scored moderate or severe on a sheet would be barred from the pain fit but would still be fed to the safety model as "tolerated, severity 0". Plus two documentation weaknesses (§5). | §5 |

---

## 1. What came in from Google Drive, and is it intact

**Folder:** `BRAVO/_pro_dump/clinic_sheets/RCS08/` (kept out of git because the notes columns carry the patient's own words). Contents: 29 testing workbooks, 1 template, and `manifest.json` -- the Drive download record with each file's Drive id, byte count and sha256.

**Integrity check (run on the host, 2026-09-15):** 30 manifest entries, 30 `.xlsx` files on disk, none missing either way, **zero sha256 mismatches**. What is on disk is byte-for-byte what was downloaded from Drive.

**Visits covered:** July 2025 to September 2026 -- 20 in-clinic visits (one of them the fMRI-DBS visit of 2026-06-22) and 9 at-home testing sheets.

**What the ingest reads** (`StimOptimizer/clinic_pain.py`):

- Columns are matched **by name, never by position** (`_canon_header`, lines 104-160), because the column layout differs between workbooks. A scribe's name in brackets after a header ("Timestamp (Donna)") is stripped first. Known typos are tolerated ("Timastamp", "PW (ms)" holding microseconds).
- Seven pain sites: overall, head, back, left leg, left foot, right leg, right foot. The older sheets' "Verbal" column and July 2025's "Current verbal pain score" are treated as "overall" (line 149).
- A pain cell is read as a number **exactly as written** (`_parse_pain_value`, lines 206-241): a plain number stays as it is; "9/10" becomes 9; and an Excel cell that Excel itself silently turned into a date (typing "8/10" becomes the date 8-October) is read back as 8 when the day is 10 and the month is 1-10. Anything else is left unparsed. **There is no multiplication or division anywhere in the ingest.**
- Prose in the notes such as "left leg 8 -> 0" is **never** turned into a number; it is counted (7 such rows) and left out.

**Live counts stored for RCS08** (from the ingest's own record): 816 stimulation steps, 472 steps with at least one pain score, 7 prose rows not parsed, 16 pain scores skipped because no stimulation setting had been recorded yet on that sheet.

**Known gaps, all disclosed in the code, none silent:**

| Workbook | Gap | Effect |
|---|---|---|
| July 2025 (07_30_25) | Scores live in the Notes tab; rate and pulse width are not recorded there | 7 rows read, all 7 dropped from the per-rate fit (no rate) -- they count in the file totals only |
| August 21 2025 | Only "overall" and "back" columns | No leg scores; cannot feed the left-leg objective |
| Sep 04 and Sep 18 2025 | Head/back/left leg/left foot only | No right-side scores |
| 28 of 29 workbooks | "Side Effect?" column is free text | **Not parsed as a number.** Only the 2026-09-02 sheet has the numeric "SIDE EFFECT / SCORE" column |

---

## 2. How side-effect scores become the optimizer's penalty

### 2a. The ladder (`StimOptimizer/routines/objective.py`, lines 21-33 and 199-208)

The optimizer minimises one number per setting, **J**, in NRS points (0-10 pain scale points). J = (pain at that setting minus pain at the setting in force) + side-effect penalty. Lower is better; 0 means "same as today".

| Reported severity | Penalty added to J | Meaning |
|---|---|---|
| none | 0.0 | no cost |
| mild | **1.0 NRS point** | one mild side effect cancels exactly one point of pain relief |
| moderate | **infinite** | the setting can never be chosen |
| severe | **infinite** | the setting can never be chosen |
| no report | 0.0, and `se_observed = False` | "absence of a report is not absence of a side effect" (line 76 of the test file) |
| any other word | the code raises an error | an unrecognised label is refused, not guessed at |

**Why infinite rather than a big number** (comment at lines 17-24): the pain term is bounded below by the pain at the setting in force (about -7.3 points on RCS08), so any finite penalty -- even 4.0 -- could be outbid by a large enough apparent pain improvement. Infinite is the only value that makes "always rejected" actually true.

**What infinite does** (lines 376-379): `J = J_pain + J_SE`, then `feasible = isfinite(J)`. A setting with an infinite J is excluded from the pain surface fit (`stage1_openloop.py` line 885: `fit = D.loc[D["feasible"]]`), so an intolerable setting says nothing about where the pain optimum is.

**Where the clinic sheet's 0-4 score maps onto that ladder** (`clinic_pain.py` line 97): sheet 0 -> none, 1 -> mild, 2 -> mild, 3 -> moderate, 4 -> severe. The sheet's own printed scale is 0 = none, 1 = mild, 2 = mild persistent, 3 = moderate, 4 = avoid. Note that **2 ("mild persistent") is folded into "mild" and costs 1.0 point, not more**, and **3 ("moderate") is already a hard reject**. When one setting was tested more than once, the **worst** score across those tests is used (line 760).

### 2b. What actually reaches the penalty today (live, RCS08)

- **REDCap stream:** the design matrix has **no side-effect column at all** (`adapter.py` never creates one; the probe confirms `has_se_severity_column = False`). So on all 92 REDCap epochs the penalty is 0 and `se_observed` is False. J equals the pain term exactly on every epoch (checked: `J == J_pain` everywhere).
- **Clinic-sheet stream:** 15 rows carry a numeric side-effect score, all from the 2026-09-02 sheet: ten scored 0, five scored 1, none scored 2, 3 or 4. After grouping into distinct settings: 3 settings labelled "none", 3 labelled "mild", 234 with no score. Of the 118 settings that have a left-leg score (and so enter the fit), **one** carries the mild penalty of exactly 1.0; the other 117 carry 0. Zero settings are infeasible.

### 2c. The safety model is a separate thing, and it uses no reported side effect

The safety model (`routines/surrogate.py` `SafetyGP`, lines 389-530) is a Gaussian process over severity whose "safe set" is every grid point where the upper confidence bound of predicted severity stays below 3.0 (`SE_THRESHOLD`). It decides the reachable ceiling, the queue's "safe" column and the batches.

It is fitted on **pseudo-observations only** (`StimOptimizer/safety_ceiling.py`):

1. **Severity 3 anchors** = the PI's stated ceiling, 4.5 mA on each side for RCS08 (stated 2026-09-14, table at lines 47-51), placed at every one of the 12 stimulation rates on the grid.
2. **Severity 0 ("tolerated") anchors** = every (rate, current) with current above 0 that was held at least a minimum time: 72 hours on the REDCap stream, 3.6 seconds (0.001 h) on the clinic stream.

Live seed on RCS08: Left 26 tolerated + 12 ceiling anchors (REDCap), 80 + 12 (clinic); Right 30 + 12 and 75 + 12.

No reported severity score enters this model. The code says so itself (`surrogate.py` lines 436-438): "Never mix these with real severity reports without keeping an `se_observed` flag alongside, and drop the seeds once prospective reports exist." That instruction has not yet been acted on because, until the 2026-09-02 sheet, there were no numeric reports to act on.

---

## 3. The pain scale: what the code does, with numbers

### 3a. The rule (`routines/objective.py`, lines 57-82)

> `TARGET_SCALE = 10.0` -- "Everything is therefore rescaled to a common **0-10** reference before J_pain is formed."

Each column has a declared native scale, and the multiplier is 10 divided by that:

| Column | Native scale | Multiplier | Source |
|---|---|---|---|
| `nrs`, `pain_Overall`, `pain_Left_Leg`, `pain_Back`, ... (the sheet items and REDCap NRS) | 0-10 | **1.0** | used as written |
| `left_leg_vas`, `back_vas`, `vas`, `relief` (REDCap visual analogue items) | 0-100 | **0.1** | divided by 10 |
| `mpq_sum` (McGill sum) | 0-45 | 0.222 | only used in the legacy composite, which z-scores anyway |
| an unknown column | assumed 0-10 | 1.0 | "the safe default for a hand-built frame" |

The rescale happens **once**, inside `build_objective` (lines 341-352), before anything is differenced or weighted; the standard deviation is multiplied by the same factor; and the output frame records `primary_item` and `primary_scale_factor` so nothing downstream can rescale a second time. I searched the service layer, the plotting module and the React page for any further multiply-by-10 or divide-by-10 of a pain value: **none exists**. J is in 0-10 points from the objective to the screen (`plots.py` line 104: "Composite objective J (NRS points; 0 = incumbent)").

### 3b. The reason the direction is 0-10 and not 0-100

The comment at lines 57-63 states it: the side-effect ladder is calibrated so that **one mild side effect cancels 1.0 NRS point**. Against a 0-100 objective that same 1.0 would be ten times too weak. Scaling everything to 0-10 keeps the ladder's meaning. Test `test_build_objective_rescales_a_0_100_primary_item` (`tests/test_core.py` line 255) pins exactly this: a 0-100 primary item and its 0-10 twin must give identical J, and |J_pain| must stay at or below 10.

### 3c. Live proof on RCS08

**REDCap stream (92 epochs):**

| Quantity | Value |
|---|---|
| raw `left_leg_vas` range in the design matrix | 20.5 to 84.5 (n = 75) -- unmistakably a 0-100 scale |
| raw `nrs` range | 4.5 to 9.0 (n = 92) -- a 0-10 scale |
| `primary_item` chosen | `left_leg_vas` |
| `primary_scale_factor` recorded on the frame | **0.1** (equals `scale_factor("left_leg_vas")`) |
| `left_leg_vas` after rescale | 2.05 to 8.45 |
| rescaled column equals raw x 0.1, element by element | **True** |
| pain at the setting in force (epoch 123), on 0-10 | 4.644 |
| J_pain range | -2.594 to +3.806 NRS points |

**Clinic-sheet stream (472 rows, 240 distinct settings, 118 with a left-leg score):**

| Quantity | Value |
|---|---|
| raw per-site ranges | overall 2-9 (n 449), head 5-10 (42), back 3-9 (228), left leg 1-8 (216), left foot 0-8 (175), right leg 1-9 (154), right foot 1-8.5 (147) |
| any value above 10 anywhere | **none** |
| `primary_item` | `pain_Left_Leg` |
| `primary_scale_factor` | **1.0** |
| `pain_Left_Leg` after "rescale" | 1.0 to 8.0 (unchanged) |
| J_pain range | -1.0 to +6.0 NRS points, against the reference setting (epoch 114) |

**Conclusion for question 3.** The PI's premise "0-100, multiply NRS by 10" describes the opposite direction from what runs. The code puts everything on **0-10**: REDCap visual-analogue items are divided by 10, sheet scores and REDCap NRS are used as written. The ordering of settings is identical either way; the penalty calibration (1 mild = 1.0 point) is only correct on the 0-10 scale, and that is the scale in force. **No correction to the code is needed.** The PI's mental model should be updated to "0-10".

---

## 4. The synthetic check that the ladder does what the comments say

Job 20260915-093843-38c4f0bb built a four-epoch frame at 55 Hz, currents 1, 2, 3, 4 mA, left-leg pain 5, 4, 3, 2, severities none / mild / moderate / severe, setting in force = the 1 mA epoch:

```
J_SE      : [0.0, 1.0, inf, inf]
feasible  : [True, True, False, False]
J         : [0.0, 0.0, inf, inf]
```

Read across: the mild epoch had 1.0 point less pain than the setting in force (4 vs 5) and the mild penalty of 1.0 cancels it exactly, so J = 0.0 -- the calibration statement is literally true. The moderate and severe epochs are infinite and infeasible even though their pain is 2 and 3 points better.

---

## 5. What was found that needs the PI's decision

### 5a. Latent defect: a moderate or severe sheet score would seed the safety model as "tolerated"

`safety_ceiling.tolerated_anchors` (lines 118-124) keeps every epoch with current above 0 held at least the minimum time. It does **not** look at `se_severity` or `feasible`. `stage1_openloop.py` line 874 hands it the whole frame, including infeasible epochs. Same synthetic frame, minimum time 0.001 h:

```
tolerated anchors handed to SafetyGP as severity 0: [[55,1.0],[55,2.0],[55,3.0],[55,4.0]]
LEAK: moderate (3.0 mA) / severe (4.0 mA) epochs seeded as tolerated: [3.0, 4.0]
safety_seed n_tolerated: 4   (2 if severity were respected)
```

So the first time a clinic sheet scores a setting 3 or 4, that setting is correctly barred from the pain fit **and** simultaneously tells the safety model "this current was tolerated with no side effect" -- the exact opposite of what the sheet said. On the clinic stream the "held long enough" bar is 3.6 seconds, so every scored step qualifies.

**Live exposure today: zero.** The only numeric scores on record are ten 0s and five 1s (2026-09-02 sheet). Nothing on RCS08's record is currently mis-seeded. But the Wednesday titration session and every session after it will use the new sheet with the numeric column, so this becomes live the first time a 3 or 4 is written.

**Fixed the same day (decision 164), at the PI's instruction "apply the fix now, with a test, before Wednesday".** `tolerated_anchors` now excludes any epoch whose reported severity is moderate or severe and the seed reports `n_intolerable_excluded`; two tests written first and watched to fail. Live anchor counts on RCS08 are unchanged (REDCap L 26 / R 30, clinic L 80 / R 75, 0 excluded), because nothing on record is scored 3 or 4 yet. The original suggestion, kept for the record: in `tolerated_anchors`, also require `feasible` to be True (or `se_severity` not in {moderate, severe}) when the column exists. A better fix, already described in `surrogate.py` lines 436-438, is to feed the real scored severities into the safety model with their `se_observed` flag and drop the pseudo-anchors where real reports exist -- but that is a design change, not a patch.

### 5b. The "amplitude does not predict side-effect severity" sentence rests on labels the analysis itself distrusted

`routines/stage_gate.py` lines 69-72, `stage2_closedloop.py` lines 211-215 and `TWO_STAGE_DESIGN.md` line 185 all state: "amplitude does NOT predict side-effect severity (Spearman rho = -0.013, p = 0.79, n = 417 non-procedural steps with stimulation on)". This number is **not computed anywhere in the current code**. It comes from the 2026-09-02 ordinal-safety analysis (`BOTORCH_REFACTOR.md` lines 60-105), whose model (`routines/safety_ordinal.py`, 917 lines) was deleted as unreached in decision 145.

That analysis says of its own labels (lines 84-97): of the 417 fitted steps, 375 were "none" -- and **402 of the file's 696 "none" labels were rows never shown to a coder**, i.e. absence of a note, not an observation of no side effect. Refitting on the 153 explicitly coded rows raised the moderate-or-worse rate from 4.56% to 12.42% and shrank the safe set from 14 cells to 0. The document's own words: "the absolute risk level for this participant is uncertain by roughly a factor of three."

What that sentence gates in today's code is **conservative**: it justifies bounding the adaptive amplitude limits to the range actually delivered (`_amp_windows`), which refuses to go above what was tested. So the weak label does not make anything unsafe. But the sentence is quoted as an established fact in three places, with no path back to the data, and it should either be recomputed on the new numeric side-effect column once enough rows exist, or reworded to say "under the 2026-09-02 coding, which counted uncoded rows as none".

### 5c. Two small labelling points, no behaviour change

- On the REDCap stream, 17 of 92 epochs read `feasible = False`. None of them is a side-effect reject; they simply have no left-leg VAS rating (the pain term is NaN, so J is not finite). The word "infeasible" therefore covers both "intolerable" and "unrated" on this stream. Correct behaviour, misleading label.
- The clinic ingest folds sheet score 2 ("mild persistent") into "mild" (penalty 1.0). If the PI intends "mild persistent" to cost more than "mild", the map at `clinic_pain.py` line 97 is the one place to change.

---

## 6. Where every number above came from

| Item | Path |
|---|---|
| Probe script (read-only, RCS08 live) | `BRAVO/_agent_bridge/_audit_scale_se.py`, bridge job 20260915-093710-adf061b3 |
| Synthetic ladder + leak proof | `BRAVO/_agent_bridge/_audit_leak_proof.py`, bridge job 20260915-093843-38c4f0bb |
| Tests run in the same job | `tests/test_core.py`, `tests/test_clinic_pain.py`, `tests/test_safety_ceiling.py` -- 64 passed, 0 failed |
| Manifest reconciliation | run on the host against `BRAVO/_pro_dump/clinic_sheets/RCS08/manifest.json` |
| Objective and ladder | `BRAVO/modules/StimOptimizer/routines/objective.py` |
| Sheet ingest | `BRAVO/modules/StimOptimizer/clinic_pain.py` |
| Safety seeding | `BRAVO/modules/StimOptimizer/safety_ceiling.py`, `routines/surrogate.py` |
| Stage 1 wiring | `BRAVO/modules/StimOptimizer/stage1_openloop.py` lines 870-885 |
| Planning files for this audit | `.planning/2026-09-15-drive-data-side-effect-penalty-and-pain-/` |

The audit itself changed no code. The fix in §5a was applied afterwards as decision 164 (`safety_ceiling.py`, `tests/test_safety_ceiling.py`); the package digest change makes every stored Stim Optimizer answer rebuild once.
