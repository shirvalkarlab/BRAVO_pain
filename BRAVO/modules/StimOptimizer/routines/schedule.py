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

from . import objective as OBJ


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


def safety_filter(candidates, *, delivered_envelope, amp_ceiling, energy_budget=None,
                  prior_triples=None, amp_tol=0.06, pw_tol=1.0,
                  triple_hemi_col="hemi", triple_amp_col="amp", triple_pw_col="pw",
                  triple_rate_col="rate",
                  left_col="ampL", right_col="ampR", rate_col="rate",
                  pw_left_col="pwL", pw_right_col="pwR"):
    """Keep only candidates inside EVERY safety constraint. Three now bind, not two.

    ``delivered_envelope`` is ``{"Left": (lo, hi), "Right": (lo, hi)}`` taken from the patient's own
    record, and ``amp_ceiling`` is the clinician-declared absolute maximum.

    ``energy_budget`` is ``{"Left": teed, "Right": teed}``, normally from
    :func:`objective.energy_reference_from_record`. WHY IT EXISTS: the tolerated amplitude ceilings
    were established at one rate (55 Hz here), and the energy the tissue receives per unit time
    rises with rate, so an amplitude that is safe at 55 Hz can deliver several times that energy at
    a higher rate. Total electrical energy delivered goes as amplitude squared times pulse width
    times rate, so at 165 Hz the same amplitude delivers 3x the energy. Passing ``None`` skips the
    energy gate and restores the old two-constraint behaviour, which is wrong for any candidate set
    spanning more than one rate — it is the default only so existing single-rate callers do not
    change behaviour silently.

    A CASE THIS CATCHES AND EYEBALLING DOES NOT: a hemisphere held at a CONSTANT amplitude across a
    rate change is not held at constant energy. On this record the right side held at 3.0 mA while
    the rate moved 55 -> 165 Hz goes from 44% to 133% of its own budget, so the side nobody was
    varying is the side that breaches.

    Returns ``(kept, rejected)``; rejected rows carry ``reject_reason`` so a dropped candidate is
    always visible rather than silently absent.

    Note on the safety GP: this filter binds on the delivered record rather than on the module's
    safety surrogate. The surrogate is fitted from coded severity (see ``routines.safety_ordinal``),
    but on this record 402 of 774 rows were never examined by a coder and default to "none" at
    systematically lower amplitudes, so its absolute probabilities are provisional and it reports
    the top of the amplitude range as unevidenced rather than safe. What the patient has actually
    received is the firmer constraint.
    """
    cand = pd.DataFrame(candidates).copy()
    lo_l, hi_l = delivered_envelope["Left"]
    lo_r, hi_r = delivered_envelope["Right"]
    in_env = cand[left_col].between(lo_l, hi_l) & cand[right_col].between(lo_r, hi_r)
    under_ceil = (cand[left_col] <= amp_ceiling) & (cand[right_col] <= amp_ceiling)

    if energy_budget is None:
        in_energy = pd.Series(True, index=cand.index)
        over_l = over_r = pd.Series(False, index=cand.index)
    else:
        missing = [c for c in (rate_col, pw_left_col, pw_right_col) if c not in cand.columns]
        if missing:
            raise KeyError(
                f"the energy gate needs {missing} on every candidate. Amplitude alone cannot be "
                "checked against an energy budget: the same amplitude is a different energy at a "
                "different rate or pulse width. Supply them, or pass energy_budget=None to skip "
                "the gate deliberately.")
        capL = OBJ.energy_matched_ceiling(cand[rate_col], cand[pw_left_col],
                                          energy_budget["Left"], amp_ceiling=amp_ceiling)
        capR = OBJ.energy_matched_ceiling(cand[rate_col], cand[pw_right_col],
                                          energy_budget["Right"], amp_ceiling=amp_ceiling)
        cand["energy_cap_L_mA"] = np.round(capL, 3)
        cand["energy_cap_R_mA"] = np.round(capR, 3)
        cand["teed_pct_L"] = np.round(
            100 * cand[left_col] ** 2 * cand[pw_left_col] * cand[rate_col]
            / energy_budget["Left"]).astype(int)
        cand["teed_pct_R"] = np.round(
            100 * cand[right_col] ** 2 * cand[pw_right_col] * cand[rate_col]
            / energy_budget["Right"]).astype(int)
        over_l = cand[left_col] > capL + 1e-9
        over_r = cand[right_col] > capR + 1e-9
        in_energy = ~(over_l | over_r)

    if prior_triples is None:
        novel_l = novel_r = pd.Series(False, index=cand.index)
    else:
        # JOINT prior exposure, not marginal. An amplitude seen at this rate and a pulse width seen
        # at this rate do NOT imply the PAIR was ever delivered: a plan can be assembled entirely
        # from individually-familiar numbers and still program a combination the patient has never
        # received. That happened in this project — a clinic plan claimed every setting had been
        # delivered before while 7 of 14 hemisphere-settings were novel as triples, because the
        # check was on amplitude alone and pulse width was assigned from an unrelated epoch.
        pt = pd.DataFrame(prior_triples)
        for c in (triple_hemi_col, triple_amp_col, triple_pw_col, triple_rate_col):
            if c not in pt.columns:
                raise KeyError(f"prior_triples missing {c!r}; has {sorted(pt.columns)}")
        pt = pt.assign(**{c: pd.to_numeric(pt[c], errors="coerce")
                          for c in (triple_amp_col, triple_pw_col, triple_rate_col)})

        def _n_prior(hemi, rate, amp, pw):
            s = pt[(pt[triple_hemi_col] == hemi)
                   & np.isclose(pt[triple_rate_col], float(rate))
                   & (np.abs(pt[triple_amp_col] - float(amp)) <= amp_tol)
                   & (np.abs(pt[triple_pw_col] - float(pw)) <= pw_tol)]
            return int(len(s))

        nl = [_n_prior("Left", r[rate_col], r[left_col], r[pw_left_col])
              for _, r in cand.iterrows()]
        nr = [_n_prior("Right", r[rate_col], r[right_col], r[pw_right_col])
              for _, r in cand.iterrows()]
        cand["prior_joint_L"] = nl
        cand["prior_joint_R"] = nr
        novel_l = pd.Series(nl, index=cand.index) == 0
        novel_r = pd.Series(nr, index=cand.index) == 0

    ok = in_env & under_ceil & in_energy & ~(novel_l | novel_r)
    reason = np.where(
        ~under_ceil, f"above the {amp_ceiling} mA declared ceiling",
        np.where(~in_env, "outside the amplitude range ever delivered to this patient",
                 np.where(over_l & over_r, "energy budget exceeded on BOTH hemispheres",
                          np.where(over_l, "LEFT exceeds its energy-matched ceiling at this rate",
                                   np.where(over_r,
                                            "RIGHT exceeds its energy-matched ceiling at this rate "
                                            "(a constant amplitude is not a constant energy)",
                                            np.where(
                                                novel_l | novel_r,
                                                "this exact (rate, amplitude, pulse width) "
                                                "combination has NEVER been delivered to this "
                                                "patient, even though the amplitude and the pulse "
                                                "width each appear individually",
                                                ""))))))
    cand["reject_reason"] = np.where(ok, "", reason)
    return cand[ok].drop(columns=["reject_reason"]).reset_index(drop=True), \
        cand[~ok].reset_index(drop=True)
