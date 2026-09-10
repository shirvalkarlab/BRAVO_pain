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
