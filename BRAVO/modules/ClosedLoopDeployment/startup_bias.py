"""The start-of-stretch bias in band power: are the first few readings after a gap in recording
low compared with the rest of that stretch, and for how long -- the measurement the adaptive
startup delay is set from (T6, 2026-09-13; contest decision 150, ``artifacts/contest_2026-09-13_
SYNTHESIS.md`` section 4, task 7 "The startup dip, measured in the module").

WHAT THIS PORTS, AND FROM WHERE, AND WHY TWO METHODS. Two of the contest's six entries each
measured this independently and reported different numbers on the identical participant and band
(ONE_THREE_LEFT at 24.5 Hz): contestant D (``dwell_markov``) found a real, significant dip at the
very first reading of a training stretch (0.104 of this participant's own scatter low, t = -2.49,
82 stretches); contestant E (``nonlin_dyn``) found nothing (0.03, 0.01, 0.00 of the scatter for the
first three readings, none more than 1.5 standard errors from zero). The contest's own synthesis
took the disagreement at face value rather than picking a winner ("this disagrees with the Phase 10
finding ... the two use different baselines and I cannot say which is right", contestant E's own
report). BOTH are ported here exactly as each contestant coded them, from the read-only scratch
copies (gitignored, not in this repository): ``BRAVO/_agent_bridge/_probe_tl/_contest/dwell_markov/
d1_explore.py`` (search "startup check") and ``BRAVO/_agent_bridge/_probe_tl/_contest/nonlin_dyn/
s3_returnmap.py`` (section "(D) start-of-stretch transient"). Neither is corrected, reconciled or
picked as more right than the other -- see the module's own returned ``note`` field, and the
docstrings on the two functions below, for what actually differs between them and why that is
enough on its own to explain two different answers on the same data.

BOTH BASELINES ARE "THE STRETCH'S OWN MEDIAN" IN WORDS, AND THAT IS WHERE THE SIMILARITY ENDS.
Read closely, D's baseline is ``np.median(f)`` where ``f`` is a stretch's FINITE readings only,
compacted so gaps inside the stretch are squeezed out; E's baseline is ``np.nanmedian(p)`` over the
stretch's full regridded array ``p``, which ignores NaNs the same way -- so the two baselines
compute the identical NUMBER for a given stretch. What differs is which reading each contestant
calls "the k-th reading":

- **D compacts the stretch first, then indexes.** ``f = pp[np.isfinite(pp)]``; reading ``k`` is the
  k-th value that was actually MEASURED, wherever it falls on the clock, and any missing cell in
  between is invisible to the index. A stretch qualifies at all only when it has more than 20
  finite readings (``f.size > 20``) -- so D's numbers come from the longer, steadier stretches only.
- **E indexes the regridded grid directly, no compaction.** Reading ``j`` is the value at device-
  clock position ``j`` (elapsed time ``j * device_clock_s``); if that exact cell is missing the
  stretch simply does not contribute to that reading index (it is not shifted to the next real
  value the way D's index effectively is). E requires only that the stretch's grid reaches position
  ``j`` -- no minimum-length floor at all, so short, choppy stretches contribute too.

Both differences push the same way on reading 0 specifically: D's ``f[0]`` and E's ``p[0]`` are the
identical value for every stretch (the first cell of a regridded stretch is always the one the
first real sample fell into, by construction of ``simulation.regrid_stretches``), so any
disagreement at reading 0 traces to WHICH STRETCHES are included, not to a different reading being
measured -- D's 20-reading floor keeps only the longer, likely-steadier recordings, while E counts
every stretch including brief ones a recording box only sampled for a few cells before the next
gap. The standard deviation each side divides by also differs in scope: D's ``sd`` pools every
FINITE reading in the whole 70% training split (long and short stretches alike); E's ``sd_all``
pools only the readings of stretches that reached the module's own minimum grid length (E's script
uses 3 cells) before the split was drawn.

THE TRAIN/TEST SPLIT is what both contestants used and is ported once, faithfully, for both
methods: stretches ordered by their own start time, the first ``train_frac`` (70% by default,
rounded) by COUNT is training, exactly the fraction the contest brief specified for every entry
(``artifacts/contest_2026-09-13_SYNTHESIS.md``, "the brief's split"). D drew its split from every
stretch `regrid_stretches` returned; E first dropped stretches shorter than 3 grid cells and THEN
split -- so the two methods' own training sets are not even the same collection of stretches, which
is carried through here rather than smoothed into one shared split, because that difference is
itself part of the honest answer to why the two contestants disagree.

NOTHING HERE IS FITTED OR SIMULATED. Unlike ``design_rule.py`` (T3) this needs no optimiser and no
noise simulation -- it is arithmetic over the same 3 s tiles `design_rule.py` and `occupancy.py`
already read, so, like ``occupancy.py`` (T4), it is computed fresh on every deployment report
rather than stored in the cache (`CacheStore`); there is nothing here expensive enough to be worth
the store's own bookkeeping.
"""
from __future__ import annotations

from typing import Any, Dict, List, Sequence, Tuple

import numpy as np

#: The fraction of stretches, by count and in time order, that both contestants used for training.
TRAIN_FRAC = 0.70

#: D's own floor: a stretch needs MORE than this many finite readings to contribute at all.
D_MIN_FINITE_READINGS = 20
#: D's own range: reading indices 0 through 5 (six readings), `range(0, 6)` in the source script.
D_MAX_INDEX = 6

#: E's own floor: a stretch needs to reach this many regridded cells before the split is drawn.
E_MIN_GRID_LEN = 3
#: E's own range: reading indices 0 through 7 (eight readings), `range(8)` in the source script.
E_MAX_INDEX = 8

StretchTuple = Tuple[np.ndarray, np.ndarray, np.ndarray]


# ---------------------------------------------------------------------------------------------
# The one train/test split both contestants used (ported once; see the module docstring for why
# it is applied to a DIFFERENT starting collection for each method, faithfully, not harmonised)
# ---------------------------------------------------------------------------------------------
def split_stretches_by_time(stretches: Sequence[StretchTuple],
                            frac: float = TRAIN_FRAC
                            ) -> Tuple[List[StretchTuple], List[StretchTuple]]:
    """Order ``stretches`` (each ``(t_grid, power, amp)``, `simulation.regrid_stretches`'s own
    shape) by their own start time and split the first ``frac`` of them, by COUNT, into training;
    the rest is test. Contestant E's own ``split_stretches`` (``s3_returnmap.py``): an explicit
    sort by ``s[0][0]``, the stretch's first grid timestamp. Contestant D's version relied on its
    input already being time-ordered (which `regrid_stretches` always returns) rather than sorting
    explicitly; the two are the same split on already-ordered input, so one function serves both.
    """
    if not stretches:
        return [], []
    order = np.argsort([float(s[0][0]) if len(s[0]) else np.inf for s in stretches], kind="stable")
    ordered = [stretches[int(i)] for i in order]
    n_train = int(round(float(frac) * len(ordered)))
    return ordered[:n_train], ordered[n_train:]


# ---------------------------------------------------------------------------------------------
# Contestant D's method (dwell_markov, d1_explore.py, "startup check")
# ---------------------------------------------------------------------------------------------
def startup_bias_d_method(train_stretches: Sequence[StretchTuple], *,
                          min_finite: int = D_MIN_FINITE_READINGS,
                          max_index: int = D_MAX_INDEX) -> Dict[str, Any]:
    """D's own computation, ported line for line. For every training stretch with more than
    ``min_finite`` finite readings, compact it to its finite readings alone (``f``) and take
    ``f[k]`` for each reading index ``k``; the baseline is that stretch's own ``np.median(f)``.
    The standard deviation divided into the bias is pooled over every finite reading of every
    TRAINING stretch (not only the qualifying ones) -- D's own ``sd`` line, recomputed here once
    rather than once per ``k`` as the source script did, since it does not depend on ``k``.
    """
    all_finite = [np.asarray(p, dtype=float)[np.isfinite(np.asarray(p, dtype=float))]
                 for (_t, p, _a) in train_stretches]
    pooled = np.concatenate(all_finite) if all_finite else np.empty(0)
    if pooled.size < 2:
        return {"available": False,
               "reason": "fewer than 2 finite readings across the training stretches"}
    sd = float(np.std(pooled))                            # population sd, D's own `np.std`

    qualifying = [f for f in all_finite if f.size > min_finite]
    if not qualifying:
        return {"available": False,
               "reason": f"no training stretch has more than {min_finite} finite readings",
               "sd_of_series": sd, "n_train_stretches": len(train_stretches)}

    rows: List[Dict[str, Any]] = []
    for k in range(max_index):
        vals = np.array([f[k] for f in qualifying], dtype=float)
        base = np.array([float(np.median(f)) for f in qualifying], dtype=float)
        d = vals - base
        n = int(d.size)
        bias_in_sd = float(d.mean() / sd) if sd > 0 else float("nan")
        if n > 1:
            sd_d = float(d.std(ddof=1))
            se = sd_d / np.sqrt(n) if sd_d > 0 else 0.0
        else:
            se = float("nan")
        t_stat = float(d.mean() / se) if se and np.isfinite(se) and se > 0 else float("nan")
        rows.append({"reading_index": k, "n_stretches": n, "mean_value": float(vals.mean()),
                    "mean_stretch_median": float(base.mean()), "bias_in_sd": bias_in_sd,
                    "t_stat": t_stat})
    return {"available": True, "min_finite_readings": min_finite, "sd_of_series": sd,
           "n_train_stretches": len(train_stretches), "n_qualifying_stretches": len(qualifying),
           "rows": rows}


# ---------------------------------------------------------------------------------------------
# Contestant E's method (nonlin_dyn, s3_returnmap.py, "(D) start-of-stretch transient")
# ---------------------------------------------------------------------------------------------
def startup_bias_e_method(train_stretches: Sequence[StretchTuple], *, dt_s: float,
                          max_index: int = E_MAX_INDEX) -> Dict[str, Any]:
    """E's own computation, ported line for line. ``raw_tr`` is every training stretch's full
    regridded power array (NaNs and all, no compaction); ``allv`` pools every finite reading
    across those stretches into ``sd_all``. For each reading index ``j``, a stretch contributes
    only when its grid reaches position ``j`` AND that exact cell is finite -- no minimum-length
    floor on the stretch itself, unlike D. The baseline is that stretch's own ``np.nanmedian(p)``
    over its WHOLE regridded array, recomputed for each ``j`` over exactly the stretches that
    reading index included, matching the source script's own per-``j`` recomputation.
    """
    raw = [np.asarray(p, dtype=float) for (_t, p, _a) in train_stretches]
    finite_parts = [p[np.isfinite(p)] for p in raw]
    allv = np.concatenate(finite_parts) if finite_parts else np.empty(0)
    if allv.size < 2:
        return {"available": False,
               "reason": "fewer than 2 finite readings across the training stretches"}
    sd_all = float(np.std(allv))                           # E's own `np.nanstd`, already finite

    rows: List[Dict[str, Any]] = []
    for j in range(max_index):
        vals, base = [], []
        for p in raw:
            if p.size > j and np.isfinite(p[j]):
                vals.append(float(p[j]))
                base.append(float(np.nanmedian(p)))
        n = len(vals)
        if n < 2:
            rows.append({"reading_index": j, "time_s": float(j) * float(dt_s), "n_stretches": n,
                        "bias_in_sd": None, "stderr_in_sd": None, "z": None})
            continue
        vals_a = np.array(vals, dtype=float)
        base_a = np.array(base, dtype=float)
        d = (vals_a - base_a) / sd_all
        se = float(d.std(ddof=1) / np.sqrt(n))
        bias = float(d.mean())
        z = float(bias / se) if se and np.isfinite(se) and se > 0 else float("nan")
        rows.append({"reading_index": j, "time_s": float(j) * float(dt_s), "n_stretches": n,
                    "bias_in_sd": bias, "stderr_in_sd": se, "z": z})
    return {"available": True, "sd_of_series": sd_all, "n_train_stretches": len(train_stretches),
           "rows": rows}


# ---------------------------------------------------------------------------------------------
# The one entry point a caller needs: build the stretches, run both methods, report both plainly
# ---------------------------------------------------------------------------------------------
def startup_bias_for_series(t, power, amp_obs, *, train_frac: float = TRAIN_FRAC,
                            min_finite_for_d: int = D_MIN_FINITE_READINGS,
                            d_max_index: int = D_MAX_INDEX,
                            e_min_grid_len: int = E_MIN_GRID_LEN,
                            e_max_index: int = E_MAX_INDEX) -> Dict[str, Any]:
    """Build this participant's own stretches from ``t``/``power``/``amp_obs`` (the same shape
    `simulation.regrid_stretches` accepts, `adapter.simulation_inputs_for_participant`'s own
    output) exactly as `design_rule.design_rule_for_series` does, then run both contestants'
    methods on the training split. THE TWO METHODS ARE APPLIED TO TWO DIFFERENT TRAINING SETS,
    each drawn the way its own contestant drew it (see the module docstring) -- D's split is over
    every stretch; E's is over stretches that first passed its own minimum-length filter. Neither
    result is corrected toward the other.
    """
    from . import simulation as _sim

    t = np.asarray(t, dtype=float)
    p = np.asarray(power, dtype=float)
    a = np.asarray(amp_obs, dtype=float)
    if a.size != t.size:
        a = np.full(t.size, np.nan)
    ok = np.isfinite(t) & np.isfinite(p)
    t, p, a = t[ok], p[ok], a[ok]
    if t.size < 3:
        return {"refused": True, "reason": f"only {t.size} distinct samples with a finite power "
                                          "reading, too few to split into stretches"}
    order = np.argsort(t, kind="stable")
    t, p, a = t[order], p[order], a[order]
    if np.any(np.diff(t) == 0):
        uniq, idx = np.unique(t, return_inverse=True)

        def _mean_by(v):
            s_ = np.zeros(uniq.size)
            c = np.zeros(uniq.size)
            fin = np.isfinite(v)
            np.add.at(s_, idx[fin], v[fin])
            np.add.at(c, idx[fin], 1.0)
            return np.where(c > 0, s_ / np.maximum(c, 1.0), np.nan)
        p, a, t = _mean_by(p), _mean_by(a), uniq
    gaps = np.diff(t)
    pos = gaps[gaps > 0]
    if pos.size == 0:
        return {"refused": True, "reason": "the time base has no positive interval"}
    dt_s = float(np.median(pos))
    stretches, n_empty, n_merged, _bounds = _sim.regrid_stretches(t, p, a, dt_s)
    if not stretches:
        return {"refused": True, "reason": "no stretches could be built from this series"}

    d_train, d_test = split_stretches_by_time(stretches, train_frac)
    d_result = startup_bias_d_method(d_train, min_finite=min_finite_for_d, max_index=d_max_index)

    e_candidates = [s for s in stretches if s[1].size >= e_min_grid_len]
    e_train, e_test = split_stretches_by_time(e_candidates, train_frac)
    e_result = startup_bias_e_method(e_train, dt_s=dt_s, max_index=e_max_index)

    return {
        "refused": False, "device_clock_s": dt_s, "train_frac": float(train_frac),
        "n_stretches_total": len(stretches),
        "n_stretches_train_d": len(d_train), "n_stretches_test_d": len(d_test),
        "n_stretches_train_e": len(e_train), "n_stretches_test_e": len(e_test),
        "d_method": d_result, "e_method": e_result,
        "note": ("Both methods call their baseline \"the stretch's own median\" and compute the "
                "identical number for it; they disagree because D compacts each stretch to its "
                "finite readings before indexing (so reading k is the k-th value actually "
                "measured, from stretches with more than 20 finite readings only) while E indexes "
                "the raw device-clock position directly (so reading j is the value at elapsed "
                "time j times the device clock, from every stretch that reached that position, no "
                "minimum length). Neither is corrected toward the other here."),
    }
