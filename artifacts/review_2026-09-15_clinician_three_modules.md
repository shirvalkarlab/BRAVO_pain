# Review, 2026-09-15: the three modules read as a clinician about to program a Percept RC

**Verdict: Needs Work.** Nothing found is a wrong number. Every serious finding is the same kind of thing:
a number the platform computes correctly, stores, and tests, and then does not put in front of the person
who has to type settings into the device. Four reviewers read the modules in parallel (one per module and
one across all three on time dynamics and thin data); every Critical and High claim they made was re-checked
by me against the code or a live number before it was kept. Two were softened, one was corrected, none was
dropped. The four raw reports and the check-by-check table are in
`.planning/2026-09-15-clinician-adversarial-review-of-the-thre/`.


> **Addendum, same day (decision 168).** The three Criticals (S1, C1, B1) and the two findings on the same lines (S2, B4) are fixed, test-first, and pushed. The averaging-range check the PI asked for changed B4's wording: the 0-30 s range is a 2020 sensing-era tip-card figure, RCS08's device has never run longer, and the device's Dual onset (0-6 min) holds a level rather than averaging it -- so the grid tiers its rows rather than calling anything above 30 s impossible.

**Who this is written for.** A clinician who has RCS08's record on screen, is planning Wednesday's
(2026-09-16) titration session, and will afterwards type a closed-loop configuration into the tablet by hand.
Every finding says which module, which page and panel, and whether the thing is on screen today.

**Live state today (RCS08, the committed band L 0-2+ at 24.5 Hz), read through the pages' own requests:**

- Closed-Loop Deployment page: verdict **"supported (point signs only; 2 of 3 intervals span zero)"**,
  licensed, 51 device rules eligible (30 advisory). The current-to-power link (E1) is −4.45 device units per
  mA, p = 0.54, 59 setting blocks — and its own note begins "SCREENING STATISTIC ONLY".
- Stim Optimizer page: no current can be recommended on either side from either data stream (0 of 4
  REDCap-fitted combinations and 0 of 19 clinic-sheet combinations pass the three checks); closed loop
  "MUST NOT START: 2 of 4 conditions block".
- Biomarkers page: the strongest band is L 1-3+ at 12.5 Hz, r = −0.53 (interval −0.66 to −0.40, 117
  ratings, corrected q = 0.0022), found at **5 minutes** of averaged signal.

---

## 1. Biomarkers module — does it tell a clinician which band to trust?

**What the page shows.** Biomarkers page: a data-availability timeline, the matching and split controls, then
the two heat maps ("How well each band tracks pain": correlation on the left, area under the curve on the
right; 22 band centres across, 10 lengths of signal down, one contact pair at a time), then the older
full-range scan. A circled cell clears the correction for having tested 22 bands. Hover shows one number;
click pins a scatter with a plain, uncorrected r and p.

**The statistics are careful.** The p-value behind a circle corrects for having tried ten lengths and kept
the best, using a block shuffle sized to the ratings' own day-to-day similarity; a second correction runs
across the 22 centres, separately per grid and per contact; single 3-second pieces are screened against a
historical 99.5th-percentile ceiling before averaging; cells answered from the device's own FFT snapshot are
counted and captioned. This is better than most published biomarker dashboards.

**Findings.**

**B1 — Critical. The numbers that decide whether a band is trustworthy are never shown.** For every column
the backend computes, for the one winning cell, the rating count, the bootstrap interval, the
selection-corrected p and the 22-band q (`Biomarkers/routines/analytics.py` `_best_rows_correlation`,
about lines 6513-6611). The page reads those rows only to decide where to draw the circle
(`Client/src/views/Reports/Biomarkers/BiomarkerHeatmapGrids.js:263-306`); the hover template at line 299
prints `r = %{z:.3f}` and nothing else; the click panel prints a *different*, uncorrected r and p computed
from raw points, which the code's own comment (line 142) says must not be confused with the grid's number.
The only component that ever printed n, interval and q (`BandTimeSweepPanel.js`) is imported nowhere
(`index.js:23` names it in a comment). Live: the 12.5 Hz cell's n = 117, interval −0.66 to −0.40, q = 0.0022
exist in the response and a clinician cannot see any of them.
*Fix (frontend):* on hover and on the pinned panel, print the winning row's n, interval and q beside the
plain statistic, labelled as two different things. *Test:* a jest render of the grid against the RCS08
fixture asserting the string "117 ratings" appears for that column.

**B2 — Critical. Nothing on this page is out-of-sample, and the page does not say so.** Forward-chaining
validation (decision 12) and this patient's own reliable-change amount (decision 111) both run — only on the
Closed-Loop Deployment page, after a band is committed (`ClosedLoopSim/DeploySignoffCard.js`,
`ReliableChangePanel.js`; no file under `Reports/Biomarkers/` mentions either). A clinician who stops at the
exploration page sees an in-sample correlation with no caption.
*Fix (frontend, one line):* under the grids, "These are in-sample results; whether a band holds up on new
data is checked after you commit it, on the Closed-Loop Deployment page."

**B3 — Critical. "Does this band still track pain under a different stimulation setting?" is computed for
this exact grid and hidden from this page.** The cross-setting stability answer (stable / setting-dependent /
cannot tell) is built in the background for every stored grid (decisions 96-98) and drawn on the Closed-Loop
page's "Choose a band" card. `Biomarkers/bravo_service.py:5552` says the flag is "deliberately absent" from
the Biomarkers request, and `BiomarkerHeatmapGrids.js` contains no stability string. For a new indication
with no published biomarker, this is the single most important honesty check on a promising cell.
*Fix (backend + frontend):* carry the stored stability answer into the Biomarkers grid response (it is
already keyed on the same entry) and mark each winning cell with the same three-way symbol the Closed-Loop
card uses.

**B4 — High. The best evidence sits at a length of signal the device cannot average.** Both strongest
correlations (12.5 Hz on L 1-3+, 15.5 Hz on R 0-3+) resolve at 300 s. The device's documented averaging range
for closed loop is 0-30 s (`StimOptimizer/routines/percept_adaptive.py:178`, from the tip card; decision
148). Some cells clear at device-usable lengths (13.5 Hz AUC at 15 s, q = 0.029), but nothing distinguishes
"best evidence, wrong length for the device" from "best evidence at a length the device can run".
*Fix (frontend):* shade the rows above 30 s, and show the best device-usable row beside the unconstrained
best. *Fix (backend, small):* the grid reads `DOCUMENTED_RANGES["averaging duration"]` rather than a typed
30.

**B5 — High. In-clinic sessions are invisible here.** Every number on the page comes from at-home REDCap
ratings matched within a symmetric window (default 60 min, `sweep_settings.py:48`). The clinic-and-home
testing sheets (816 steps, 472 with a score, decision 161) are read by Stim Optimizer only; no file under
`BRAVO/modules/Biomarkers/` or `Reports/Biomarkers/` references them. The clinic sessions are the only
place current is stepped on purpose, which is what separates "band tracks pain" from "band tracks
stimulation, and pain does too".
*Fix (doc now, backend later):* a caption stating the page pools at-home ratings only; then a count of how
many matched ratings fell inside a clinic visit.

**B6 — High (two reviewers found it independently). The interval and the p-value for the same cell rest on
opposite assumptions.** The p-value uses a circular block shuffle sized to the ratings' autocorrelation
(`analytics.py:6247-6248`); the interval resamples individual rating rows as if independent
(`analytics.py:6552`, `rng.integers(0, idx.size, ...)`). Decision 111 measured that two ratings an hour
apart differ by 0.37 points: they are close to one observation, not two. The interval is narrower than the
evidence supports, in exactly the direction that made decision 19 add a block bootstrap to the older
routine. It does not change today's page (the interval is not shown, B1) but will the day B1 is fixed.
*Fix (backend):* resample whole blocks with the same `block_length_for` machinery; pin with a test that the
interval widens on a constructed series with strong lag-1 autocorrelation; report the field count and how
many intervals changed on RCS08.

**What a clinician could be misled by here:** a circled cell read as "ready to program" (the drawer text
saying otherwise is closed by default); 117 "reports" read as 117 independent trials; a 5-minute cell read
as programmable.

---

## 2. Stim Optimizer — does it collect the data that answers the closed-loop questions?

**What the page shows.** Stim Optimizer page: "What the joint search prefers, per side"; the band-response
table; the evidence counts; "Titration session to run next"; "Where the two currents have been tried" (the
current maps, REDCap and clinic streams one above the other); the home schedule; the two-stage plan with
its four closed-loop checks at the bottom.

**What is done well.** The joint left-and-right current model (decision 157) fixed a real confound. The
honest-current rule (decision 158: not flat, beats today by more than the scatter, enough distinct
combinations) is doing its job — it says "no" everywhere on RCS08 today rather than printing a number. The
pooled rise-then-fall test across visits (decisions 55/56) is the right design. The titration card is
genuinely actionable: a ladder, a hold time with its arithmetic, a sensing contact, and the bands to avoid
because they sit on the stimulator's own harmonics.

**Findings.**

**S1 — Critical. The safety-envelope check fails for a reason a clinician will misread.** Live: the
closed-loop gate's "Closed-loop current limits inside the delivered range and under the ceiling" reads
**FAIL — "Left: upper limit 4.8 mA exceeds the declared ceiling of 4.5 mA"**. That 4.8 mA is not a proposed
setting. No candidate limits are supplied, so `StimOptimizer/routines/stage_gate.py:867-873` substitutes the
highest current ever delivered on that side (`defaulted.append(...)`), and the PI lowered the ceiling from
5.0 to 4.5 mA on 2026-09-14 (decision 160). The check can never pass on the left until a real candidate
limit is checked instead of history. On screen it reads as "the plan wants an unsafe current", which is
backwards.
*Fix (backend):* when limits were defaulted, return "not assessed" with the sentence "the highest current the
device has delivered (4.8 mA) is above today's ceiling (4.5 mA); no limit was proposed", instead of FAIL.
*Fix (frontend):* `Client/src/views/Reports/StimOptimizer/ClosedLoopChecks.js:214-240` already prints
"limits defaulted to the delivered range"; add "— this is history, not a proposal" next to the failing
figure. *Test:* a gate test with `amp_limits=None` and an envelope above the ceiling expects `None`, not
`False`.

**S2 — High. The side-effect-versus-current statistic rests on 15 rows and is shown nowhere at a glance.**
Since this morning (decision 166) the gate recomputes it live: Spearman rho = −0.04, p = 0.895, **n = 15
scored steps, 0 above 4 mA**, out of 816 clinic steps. The number sits in the response twice
(`two_stage.stage1.clinic_stream.side_effect_vs_current` and the gate's evidence) and `ClosedLoopChecks.js`'s
number line for that check reads none of it — the sentence surfaces only inside the refusal paragraph, only
when the check fails on the "above the delivered maximum" branch.
*Fix (frontend):* always print `side_effect_vs_current.sentence` as a caption under that check, pass or fail.
*For the clinic:* the numeric "SIDE EFFECT / SCORE" column exists on 1 of 29 workbooks; the statistic stays
at n = 15 until it is filled in at every visit, starting Wednesday.

**S3 — High. "Tolerated" means "not reported moderate or severe", not "reported fine".** After this
morning's fix (decision 164) a clinic step seeds the safety model as tolerated when its current was above
zero, it was held at least 3.6 s, and nobody wrote a 3 or 4 (`safety_ceiling.py` `tolerated_anchors`,
`_intolerable_mask`). 801 of 816 steps carry no score at all, and an unscored step is treated the same as a
step scored "none". The 3.6 s minimum is defensible as "delivered under supervision"; it is not "a clinician
confirmed no problem", and the safety picture cannot tell the two apart.
*Fix (backend):* a second anchor tier — scored-none versus delivered-unscored — reported in the seed's meta
(`n_tolerated_scored_none`, `n_tolerated_unscored`) so the safety card can say how much of "tolerated" is
observed absence of harm and how much is absence of a note.

**S4 — High (cross-cutting reviewer). The coverage check counts ratings, not occasions.**
`stage1_openloop.py:486-517` `current_coverage` groups by (left mA, right mA), sums the report count, and
requires 5 per pair; there is no time term. Five ratings filed in one afternoon at one home setting satisfy
it exactly as five ratings on five days would — and decision 111 shows same-hour ratings are nearly one
observation. A "yes" from this check can be built from near-duplicates.
*Fix (backend):* require the qualifying reports for a pair to span at least two calendar days (or N hours)
as well as the count; `current_map_schedule.py` already knows the hold-days per step and can plan for it.

**S5 — Medium.** The REDCap and clinic streams are fitted at different pulse-width pairs today (REDCap:
60/160 and 140/180 µs; clinic: 60/160 and 100/100 µs) and the current-map card does not say so; a reader can
take "no current, both streams" as two measurements of one configuration. *Fix (frontend):* one sentence in
`CurrentMapCard.js`'s clinic section naming which pairs the two streams share.

**S6 — Medium.** The noise model's duration term (`routines/objective.py:286-302`, reference one week) gives
every clinic step, 60 s or 10 min, the same near-maximal penalty; "held longer" never counts more there.
*Fix (doc or backend):* say so, or give the clinic stream a reference in minutes.

**S7 — Medium.** The 20 s post-ramp margin the titration card budgets for is switched off in the Closed-Loop
analysis (decision 144) until a titration session exists; nothing on this card says the margin it is
designed to unlock is not yet applied. *Fix (frontend, one line on the titration card).*

**S8 — Low (doc).** `OBJECTIVE_SPEC.md` and much of `TWO_STAGE_DESIGN.md` describe per-side fits and a
two-dimensional grid that predate decisions 157-166; neither is marked superseded. *Fix:* a "superseded by"
note at the top of each pointing at `stage1_openloop.py`'s docstring.

**What a clinician could be misled by here:** a failing "amplitude limits" check read as an unsafe proposal
(S1); "side effects do not move with current" read as established (S2, n = 15); "no current, both streams"
read as agreement (S5).

---

## 3. Closed-Loop Deployment — is the recommendation complete and honest about thin data?

**What the page shows.** Closed-Loop Deployment page, top to bottom: the verdict header; "Device rules · 51
checked"; the evidence triangle (current → power, power → pain, current → pain); band stability; the
reliable-change panel; "Full parameter recommendation" (every field to type, with the documented range, the
record-derived value with its confidence, and what the device runs today); the sign-off card; the CL-DBS
simulations.

**What is done well.** This page does most of what an adversarial reviewer would ask for by name. Every
timing field prints its documented range and source, the record-derived value with a confidence grade, and
what is programmed today (averaging 3,000 vs 30,000 ms; startup delay 15,000 vs 0; transitions 30,000 vs
4,000; limits 1.4-4.8 vs 2.0-3.0 mA). The threshold rows carry four independent checks, all rendered: the
noise-only design rule (needs ±5 at this timing; the stored pair is ±2.6), occupancy (2.0 % of 32,608
readings between the two thresholds; the pair's centre 12.4 units above this patient's median, against a
half-width of 2.6), the block-bootstrap robustness interval, and the start-of-stretch dip. The simulation
replays the device's own controller under both the programmed and the recommended timing. The three-state
discipline (a number, an interval, or "not assessable") holds everywhere I looked.

**Findings.**

**C1 — Critical. The current-to-power arrow is drawn as a measured edge when it is the screening
statistic.** On the committed band, through the page's own request: E1 = −4.45 device units per mA, p = 0.54,
32,466 samples in 59 setting blocks, `resolved: true`, and its note begins **"SCREENING STATISTIC ONLY.
Amplitude is confounded with time in the historical record, so this cannot be read as the causal effect of
amplitude on power."** (`ClosedLoopDeployment/edges.py:111`). The clean pooled titration slope that decision
126 swaps in was not stored for this band (5 settled points, 1 visit, below the 8-point minimum), so
`edges_historical` is empty and the confounded estimate is E1 itself. `EvidenceTrianglePanel.js:138-146`
draws any edge with a point sign as a solid line with an arrowhead; the hollow marker (its line 29) says
"interval spans zero", and nothing says "screening". The edge's payload has no `source` field (keys checked:
`ci, cluster_unit, confounded_by, estimate, inference, n, n_clusters, name, note, p, resolved, scale, sign,
statistically_established`). The caveat is in a closed fold.
*Fix (backend):* `edges.E1.source = "screening_historical" | "pooled_titration"`, set where the swap is
decided in `pipeline.run`. *Fix (frontend):* a distinct stroke and the word "screening" beside E1 when the
source is historical. *Test:* a pipeline test with no stored pooled row asserts `source == "screening_
historical"`; the triangle's jest render asserts the label.

**C2 — High. "Supported" is what the header says today, on two intervals that span zero.** The reviewer
believed the live verdict was "blocked" because its probe omitted the two hemisphere fields the page sends;
through the page's own request it is **"supported (point signs only; 2 of 3 intervals span zero)"** and
licensed. That is decision 147, the PI's rule, applied correctly. It is also a sign-only verdict resting on
E1 (the screening statistic, C1) and E2 (an AUC of 0.588, interval 0.477 to 0.695, 27 clusters — below the
module's own 40-cluster comfort line). The word "supported" comes first and is the colour a clinician
reads.
*Fix (frontend):* make the provisional state its own badge colour and put "provisional" first; keep the
sentence. *Not a rule change* — the rule is his.

**C3 — Medium. The simulation's headline sentence uses two timing values the record cannot decide, and
carries no qualifier.** Transitions and detection blanking are graded "Low" on the parameter card ("the
record cannot decide this"); `ClosedLoopSimulationPanel.js:58-80` `headline()` prints the switching numbers
from the same run with no mention. *Fix (frontend):* prepend "using two timing values the record cannot
determine" when any input carries Low confidence.

**C4 — Medium. The reliable-change pairs have no date range on the card.** Items carry
`n_pairs, n_epochs, pooled_sd, df` and no dates; 12-15 pairs clustered in one week are not the same guarantee
as 12-15 spread over the record. *Fix (backend + frontend):* `earliest_pair`, `latest_pair` on each item,
printed beside the count.

**C5 — Low (softened from the reviewer's High). Occupancy is already amber.** `PrescriptionPanel.js:257-260`
draws `occupancy_note` in the warning colour; the reviewer's "grey prose" was wrong. What is true: all four
threshold-row notes are amber whether their own `warning` flag is true or false, so amber carries no
information. *Fix (frontend):* colour by the flag.

**C6 — Low. No standing off-label line.** D01/D02 are deferred advisories by decision 148; the phrase "not an
approved indication" appears in a test fixture and a code comment and on no rendered card
(`WhatWouldChangeThis.js:178-182` excludes them on purpose). The printed sign-off sheet carries it nowhere.
*Fix (frontend, one line on `DeploySignoffCard.js`):* "Chronic pain is not an approved indication for this
device; Adaptive Therapy is labelled for Parkinson's disease." His call, since he ruled D01/D02 out of the
"what would change this" panel.

**C7 — Low.** Paused amplitude (D34) is left blank with no range at all, where every other current field
prints 0-25.5 mA. *Fix (backend):* attach the general envelope.

**What a clinician could be misled by here:** the E1 arrow (C1); the green "supported" (C2); a simulation
headline built on two undecidable timing values (C3).

---

## 4. Across all three: time, thin data, and Wednesday

**T1 — High. Four different rules decide which pain rating belongs to which brain reading, and no page says
they can disagree.** The chronic detector joins by California calendar day
(`Biomarkers/routines/local_time.py:33`, decision 142); the calibrated grid matches within a minutes-wide
window with a direction rule (`availability.py:1946`); Stim Optimizer assigns a rating to whichever
multi-day device-setting block was in force, after a 1-minute wash-in (`StimOptimizer/adapter.py:437-469`);
the clinic stream is matched by the step itself. Decision 118 measured that one report is claimed by up to 24
recording sessions at a 60-minute window. The Biomarkers grid and the Stim Optimizer map can therefore
disagree about the same handful of daily ratings for reasons that are matching, not biology.
*Fix (doc first):* one paragraph in `ARCHITECTURE_modules_and_store.md` naming the four rules and why each
exists. *Then (backend):* each page reports how many of its ratings the other pages also used.

**T2 — Medium. Pooled statistics carry a visit count and no per-visit spread.** E1, the pooled shape and the
robustness interval report `n_visits`/`n_clusters` (`amplitude_effect.py:267`); none reports the per-visit
estimate or a drift flag, though decision 16 found a months-long settling transient and decision 99 watched
one point move from p = 0.29 to 0.03 as the record grew. *Fix (backend):* per-visit slopes beside the pooled
one in `pooled_table_from_build`; one line beside E1.

**T3 — Medium. The device's clock and the analysis clock.** Occupancy, the design rule and robustness all run
at the card's 3 s averaging and say so; decision 153 measured the occupancy fraction and the off-centre
warning both flip between 3 s and 30 s on the same band. Nothing on the card says the answer would differ at
the device's native 30 s. *Fix (backend + frontend):* compute occupancy at both and print both.

**T4 — Medium (raised from the reviewer's Low, because it decides whether Wednesday's scores reach the
page).** The clinic-sheet ingest is a manual command. `~/dev/bravo_daily_ingest.sh` runs
`ingest_percept_folder` only (lines 148, 168); `manage.py ingest_clinic_sheets` is scheduled by nothing.
After Wednesday the recording half of the chain updates itself at noon; the clinic-score half stays at
Tuesday's state until someone runs the command, and every page will keep saying "no current can be
recommended" with no hint why.
*Fix (ops):* add the command to the daily job, or a one-line step in `OPERATIONS_runbook.md`: after every
clinic visit, run `python3 manage.py ingest_clinic_sheets --participant <uid>`.

### What Wednesday's session has to produce for the chain to resolve

1. Streaming on throughout, at one rate — the recording side then rebuilds itself after the noon ingest.
2. At least 8 settled currents per side — decision 160's ladder gives 10 up plus the 1.0 mA down leg.
3. A pain score **and the numeric side-effect score** written on the sheet at every step — this is what feeds
   the coverage check (S4), the safety anchors (S3) and the severity statistic (S2, n = 15 today). REDCap
   cannot supply it at 2 minutes a step.
4. Someone running the clinic ingest afterwards (T4).

If all four happen, no code change is needed for the platform to compute the whole chain; findings B1-C7
change how much to trust what it then prints, not whether it prints.

---

## 5. Root cause, and the one fix that would stop this recurring

Fifteen of the nineteen kept findings are one pattern: **computed, stored, tested, and not on the page** (B1,
B2, B3, S2, C1's missing source flag, T2, C4, and the rest by degree). Rule 13 in `CLAUDE.md` was written
because of this and it has recurred in every module.

Five Whys. (1) Each page prints what its first design asked for; later backend additions were proved by
field counts on the response and declared done. (2) The project's proof standard — field count and
difference count on the JSON — stops at the JSON; nothing asserts a field becomes a rendered element. (3)
"Reached the screen" is checked by string-searching the built chunk, which proves the code shipped, not that
it renders for this payload. (4) Browser checks need a login most sessions lack: decisions 60, 66, 67, 95,
106, 159, 162 and 163 each end "not watched in a browser". (5) There is no fixture-driven render test —
`ClosedLoopSim/__fixtures__/rcs08_deployment_payload.json` exists and asserts nothing about what a clinician
sees; two pre-existing jest failures are noted in decision 147 and left.

**Systemic fix:** one jest test per card that renders it against the committed RCS08 fixture and asserts the
exact strings a clinician must be able to read — "117 ratings", "screening", "history, not a proposal",
"n = 15 scored steps" — run in the same step as the frontend build. It needs no login, no container, and it
would have caught every Critical in this review.

Two smaller patterns: **minimums written as counts on a record whose independence is in time** (S4, S3, T1,
C4 — fix: one shared "distinct occasions" helper in DecodeCommon), and **the analysis grain is not the device
grain** (B4, T3 — fix: the Biomarkers grid reads `percept_adaptive.DOCUMENTED_RANGES`).

---

## 6. Ranked fix list

| Rank | Id | Where | Kind | One-line change |
|---|---|---|---|---|
| 1 | S1 | `stage_gate.py:867-873`, `ClosedLoopChecks.js:214` | backend + frontend | defaulted limits → "not assessed" with the history-not-proposal sentence |
| 2 | C1 | `edges.py`, `pipeline.run`, `EvidenceTrianglePanel.js:138` | backend + frontend | `E1.source` flag; distinct stroke and the word "screening" |
| 3 | B1 | `BiomarkerHeatmapGrids.js:299, 600-660` | frontend | print n, interval, q beside the plain statistic |
| 4 | B3 | `Biomarkers/bravo_service.py:5552`, grid component | backend + frontend | carry the stored stability answer onto the Biomarkers grid |
| 5 | B6 | `analytics.py:6552` | backend | block-resample the interval; test it widens under autocorrelation |
| 6 | S2 | `ClosedLoopChecks.js:214` | frontend | always print the severity sentence with its n |
| 7 | T4 | `~/dev/bravo_daily_ingest.sh`, `OPERATIONS_runbook.md` | ops/doc | schedule or document the clinic ingest |
| 8 | S4 | `stage1_openloop.py:486` | backend | coverage needs a time span per pair, not only a count |
| 9 | B4 | grid component + `percept_adaptive.DOCUMENTED_RANGES` | frontend + backend | mark rows above the device's 30 s averaging |
| 10 | C2 | verdict header | frontend | provisional gets its own colour and comes first |
| 11 | B2 | grids caption | frontend | "in-sample; checked after commit on the Closed-Loop page" |
| 12 | S3 | `safety_ceiling.py` seed meta | backend | scored-none vs delivered-unscored anchor tiers |
| 13 | T1 | `ARCHITECTURE_modules_and_store.md` | doc | name the four matching rules |
| 14 | B5 | grids caption | doc → backend | "at-home ratings only"; later a clinic-visit count |
| 15 | §5 | `Client/src/.../__tests__` | test | fixture render tests per card |
| 16-23 | C3, C4, T2, T3, S5, S6, S7, C5-C7, S8 | as listed | mixed | the Medium and Low items above |

Nothing above changes a stored number except B6 (the interval) and, if built, T2 and T3 (additive fields).
Each of those needs the field-count and difference-count proof on RCS08 before it ships, as this project
requires. None of it is authorised by this review: rule 8 — plan approval is not execution authority.

---

*Reviewers: four worker-reviewer agents (Biomarkers, Stim Optimizer, Closed-Loop Deployment, cross-cutting),
read-only, 2026-09-15 14:46-14:57. Orchestrator verification 15:05-15:40, probe
`BRAVO/_agent_bridge/_review_cl_service_path.py` (outbox 20260915-145626-cf29c405). No production file was
changed by this review.*
