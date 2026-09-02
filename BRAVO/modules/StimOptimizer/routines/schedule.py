"""In-clinic testing schedules: randomised complete block designs over candidate settings.

WHY A BLOCK DESIGN AND NOT A RANDOM ORDER
-----------------------------------------
This project has measured that pain ratings decline over the course of a visit. In a fixed running
order, "later setting" and "better setting" are the same variable and no amount of modelling
separates them. A plain random order de-confounds them only in expectation, and with a handful of
settings in one session the realised imbalance is routinely large enough to matter.

A randomised complete block design fixes it by construction: each setting appears exactly once per
block, so each is sampled once in every 1/B of the session and the drift is *orthogonal* to setting
rather than merely uncorrelated on average. The analysis then carries block as a factor and the
drift is removed instead of assumed absent.

Two further constraints are enforced:

* **No setting on adjacent steps.** An immediate repeat wastes a wash-in and lets carry-over between
  identical settings accumulate into what looks like a within-setting effect.
* **A repeated anchor.** The incumbent appears in every block, which is what makes within-session
  noise estimable *separately* from between-setting effect. Without a repeated setting the two are
  not identified and every contrast is measured against an unknown.

The design degrades safely: whole blocks may be dropped if a session runs short (even ONE complete
block is analysable), but a *partial* block re-introduces exactly the imbalance the design exists to
remove. That is why :func:`randomized_block_schedule` reports block boundaries explicitly.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd


@dataclass
class ScheduleSpec:
    """Everything that must be recorded for a schedule to be reproducible and auditable."""

    seed: int
    n_settings: int
    n_blocks: int
    washin_s: float
    min_per_step: float
    n_steps: int = 0
    balance: dict = field(default_factory=dict)

    def describe(self) -> str:
        return (f"{self.n_settings} settings x {self.n_blocks} blocks = {self.n_steps} steps, "
                f"~{self.n_steps * self.min_per_step:.0f} min at {self.min_per_step:g} min/step, "
                f"wash-in {self.washin_s:g} s, seed {self.seed}")


# Blank columns the clinic fills in. Actual clock times are recorded rather than assumed, because
# the analysis re-derives each step's TRUE wash-in from them instead of trusting the protocol.
_FILL_IN = ("actual_time_programmed", "actual_time_rated", "nrs_left_leg", "nrs_left_foot",
            "nrs_back", "nrs_overall", "side_effect_none_mild_mod_severe", "notes")


def randomized_block_schedule(candidates, *, seed, n_blocks=3, washin_s=60.0, min_per_step=3.0,
                              id_col="id", max_tries=500):
    """Randomised complete block schedule over ``candidates`` (one row per setting).

    Returns ``(schedule_df, spec)``. ``schedule_df`` carries one row per step plus the blank
    fill-in columns; ``spec`` is a :class:`ScheduleSpec` recording the seed and the realised
    balance, so a schedule handed to a clinic can always be regenerated exactly.

    Raises rather than silently degrading if the adjacency constraint cannot be met, which happens
    only for a single candidate (where a block design is meaningless anyway).
    """
    cand = pd.DataFrame(candidates).reset_index(drop=True)
    if id_col not in cand.columns:
        raise KeyError(f"candidates must carry an {id_col!r} column; got {list(cand.columns)}")
    ids = list(cand[id_col])
    if len(set(ids)) != len(ids):
        raise ValueError(f"candidate ids must be unique; got {ids}")
    if len(ids) < 2:
        raise ValueError("a block design needs at least 2 settings; with one setting there is "
                         "nothing to randomise and no contrast to protect")
    if int(n_blocks) < 1:
        raise ValueError("n_blocks must be >= 1")

    rng = np.random.default_rng(int(seed))
    blocks = []
    for _ in range(int(n_blocks)):
        order = None
        for _ in range(int(max_tries)):
            trial = list(rng.permutation(ids))
            if not blocks or trial[0] != blocks[-1][-1]:
                order = trial
                break
        if order is None:
            raise RuntimeError("could not satisfy the no-adjacent-repeat constraint; this should be "
                               "unreachable for >= 2 settings")
        blocks.append(order)

    seq = [s for blk in blocks for s in blk]
    # Invariants, asserted rather than trusted: a silently broken design still produces a tidy sheet.
    assert all(sorted(b) == sorted(ids) for b in blocks), "a block is not complete"
    assert all(seq[i] != seq[i + 1] for i in range(len(seq) - 1)), "adjacent repeat"

    meta = cand.set_index(id_col)
    rows = []
    for k, sid in enumerate(seq):
        r = meta.loc[sid]
        row = {"step": k + 1, "block": (k // len(ids)) + 1,
               "t_plan_min": round(k * float(min_per_step), 1),
               "setting": sid, "washin_s": float(washin_s)}
        for c in meta.columns:
            row[c] = r[c]
        for c in _FILL_IN:
            row[c] = ""
        rows.append(row)
    sched = pd.DataFrame(rows)

    spec = ScheduleSpec(seed=int(seed), n_settings=len(ids), n_blocks=int(n_blocks),
                        washin_s=float(washin_s), min_per_step=float(min_per_step),
                        n_steps=len(sched))
    # Realised balance: the mean step index per setting. All values near (n_steps+1)/2 means no
    # setting systematically sits early or late in the session.
    spec.balance = {"mean_step_index": sched.groupby("setting").step.mean().round(3).to_dict(),
                    "target": (len(sched) + 1) / 2.0,
                    "appearances": sched.setting.value_counts().sort_index().to_dict()}
    return sched, spec


def safety_filter(candidates, *, delivered_envelope, amp_ceiling,
                  left_col="ampL", right_col="ampR"):
    """Keep only candidates inside BOTH the declared ceiling and what has actually been delivered.

    ``delivered_envelope`` is ``{"Left": (lo, hi), "Right": (lo, hi)}`` taken from the patient's own
    record. This is deliberately the binding constraint rather than the module's safety GP: that GP
    runs on a two-anchor seed because no structured side-effect severity item has ever been
    collected, so it is over-conservative and would refuse amplitudes the patient has already
    tolerated. Returns ``(kept, rejected)`` so a dropped candidate is visible, never silent.
    """
    cand = pd.DataFrame(candidates).copy()
    lo_l, hi_l = delivered_envelope["Left"]
    lo_r, hi_r = delivered_envelope["Right"]
    ok = (cand[left_col].between(lo_l, hi_l) & cand[right_col].between(lo_r, hi_r)
          & (cand[left_col] <= amp_ceiling) & (cand[right_col] <= amp_ceiling))
    cand["reject_reason"] = np.where(
        ok, "",
        np.where((cand[left_col] > amp_ceiling) | (cand[right_col] > amp_ceiling),
                 f"above the {amp_ceiling} mA ceiling",
                 "outside the amplitude range ever delivered to this patient"))
    return cand[ok].drop(columns=["reject_reason"]).reset_index(drop=True), \
        cand[~ok].reset_index(drop=True)
