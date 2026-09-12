# Findings: Closed-Loop module minimally functional

## §1 — What the audit found, and how far behind the module actually was

Compared against Biomarkers and StimOptimizer, file for file. Full detail in decisions 100 and 101;
the three that mattered:

| | ClosedLoopDeployment | Biomarkers | StimOptimizer | CacheStore |
|---|---|---|---|---|
| Logger method calls | **0** | 43 | 13 | 17 |
| `bravo_service.py` entry point | **absent** | yes | yes | n/a |
| Source files / test files | 23 / 16 | 15 / 29 | 25 / 20 | 5 / 6 |

**The zero is the one that matters.** The module declared a logger at `adapter.py:37` and never
called it, so a failure inside the report was visible only to somebody already looking at the one
payload field carrying it. One failure was visible nowhere at all: a failed store read set both
cached entries to `None`, both were rebuilt, and the page looked entirely normal while redoing that
work on every request.

## §2 — The seven functions nothing calls, and what each one is

| function | what it computes | named in a decision? |
|---|---|---|
| `direction_consistency.for_band` | the entry point for the check below | 74 |
| `direction_consistency.implied_control_direction` | combines two already-computed links into current → pain | 74 |
| `direction_consistency.correlation_row_for_band` | looks one row out of the calibrated grid | — |
| `amplitude_effect.pooled_shape_for_band` | the within-visit current → power link, pooled across visits | 74 |
| `reliable_change.reliable_change_verdict` | whether one participant's pain change exceeds measurement noise | 75 |
| `reliable_change.pooled_same_condition_sd` | that noise, estimated from RCS08's own unchanged-setting ratings | 75 |
| `clinic_steps.within_visit_band_scores` | not yet read | **none** |

## §3 — Why the consistency check was the cheapest of the seven to wire

`for_band` needs exactly two things, and `report_for_participant` **already computes both, at the
same point in the same function**: `_3build`, the three-source comparison, and `_grid_export`, the
calibrated grid read once at the top. So wiring it fits no new model, opens no file, and issues no
query — it reads two results that already exist and reports the sign combination.

That is what makes it a caveat rather than a cost. The check's own docstring is explicit that it is
not a pass/fail gate and that the honest default on missing or non-significant evidence is "not
assessed", which is decision 9's three-state discipline applied to a new question.

**The question it answers is the one actuation actually depends on.** A band can correlate with
pain across visits and still be one whose power current cannot move, or moves the wrong way for
that correlation to translate into anything the device can act on. Multiplying the two signs is
what separates those cases, and until now nothing combined them.

## §8. The reliable-change floor: what "short gap" should mean (2026-09-10)

**Context.** The side chat found a wrong sentence in decision 104 (an SD of 0.93 was compared to
Farrar's 2.0 threshold; the derived threshold is 0.93 × √2 × 1.96 ≈ 2.6, ABOVE Farrar's bar) and
raised the concern that long epochs let weeks of real pain movement into a number meant to be
short-gap measurement noise. The PI asked for epochs over 12 h to be thrown out, then asked for
the analysis first. Measured on RCS08, NRS, 764 ratings, 92 epochs with ratings, 78 with ≥2.

**Epoch lengths (78 qualifying):** median 49 h, quartiles 27–159 h, longest 1,030 h (43 days).
Under 12 h: 3.8%. Under 24 h: 12.8%. Under 48 h: 48.7%. Under a week: 77%.

**Ratings per epoch:** median 4, upper quartile 8, max 105.

**Gap between consecutive ratings inside an epoch (671 pairs):** median 9.7 h, quartiles 4–18 h,
**90% under 24 h.** The patient rates a few times a day; consecutive ratings are rarely far apart
even inside a 43-day epoch.

**THE CONCERN DOES NOT HOLD ON THIS RECORD.** Within-epoch spread does not grow with epoch length:
Spearman ρ = −0.013, p = 0.91. Epochs under 24 h have a HIGHER median SD (1.41) than epochs over a
week (0.91). The size of a consecutive difference barely grows with the gap between the two
ratings: ρ = 0.07, p = 0.07.

**Sweep A — filter on epoch length (the current code, parameterised):**
| cutoff | epochs | df | pooled SD | threshold (points) |
|---|---|---|---|---|
| 6 h | 2 | 4 | not assessed | — |
| 12 h | 3 | 5 | 1.52 | 4.2 |
| 24 h | 10 | 12 | 1.80 | 5.0 |
| 48 h | 38 | 76 | 1.12 | 3.1 |
| 72 h | 43 | 90 | 1.06 | 2.9 |
| 1 week | 60 | 214 | 0.94 | 2.6 |
| none | 78 | 671 | 0.93 | 2.6 |
Short cutoffs give a HIGHER, noisier estimate from a tiny sample. It settles from 72 h on.

**Sweep B — pairwise: consecutive same-epoch ratings no more than T apart, SD = √(mean(d²)/2):**
| max gap | pairs | pooled SD | threshold |
|---|---|---|---|
| 1 h | 23 | 0.30 | 0.8 (suspicious: likely duplicate submissions) |
| 2 h | 36 | 1.27 | 3.5 (small sample) |
| 6 h | 267 | 0.79 | 2.18 |
| 12 h | 341 | 0.78 | 2.16 |
| 24 h | 605 | 0.76 | 2.10 |
| 48 h | 662 | 0.77 | 2.14 |
| none | 671 | 0.78 | 2.15 |
**Stable at 0.76–0.79 from 6 h to no limit.** The gap does not matter on this record.

**Reading.** The pairwise estimator is what Jacobson & Truax's short-gap noise actually means
(the same state measured twice), it uses 605 pairs instead of 3 epochs, and it is insensitive to
the cutoff. It gives a threshold of about 2.1 points, essentially Farrar's 2.0. The epoch-length
filter is the wrong unit: it throws out 96% of the data at 12 h to fix a problem the data do not
show, and returns a worse estimate.

**State of the code at this point: UNCOMMITTED.** `reliable_change.py` carries a parameterised
`max_epoch_hours` (default 12) and `adapter.py` reports it. Nothing committed; the PI is choosing.

### §8d. Are the one-hour pairs really under unchanged settings? Measured 2026-09-10, independently of the stretch labels
Probe `_agent_bridge/_probe_rc/probe_verify_pairs.py` (disposable) looked up, for BOTH ratings of every
pair the floor uses, the settings in force straight from the device's programmed history (carried forward
from the last change) and compared rate, left/right current, left/right pulse width, left/right contact.
Result on RCS08: **83 of 83 pairs across all six scores identical on every one of those at both ends, 0
changed between** (NRS 15/15, VAS 15/15, MPQ 14/14, left-leg 12/12, back 12/12, relief 15/15).
**Caveat found by the same probe:** "unchanged" is not "on". Of the 15 NRS pairs, **5 have both stimulators
at 0 mA and 2 have one side at 0 mA**; only 8 have both sides delivering current. Those off-stim pairs
(2025-07-23, 2025-07-29, 2026-04-27 both-off; 2025-10-07 right-off) are all 9->9 or 8->8. Whether a
stim-off pair counts as "stable therapy" is the PI's call; the code today counts it, because the rule is
"every setting unchanged", which stim-off satisfies. Not visible on the page: the panel prints the pair and
stretch counts but nothing about whether stimulation was on during them.
