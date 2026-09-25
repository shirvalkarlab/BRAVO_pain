"""A confirmations-and-separation design rule: how far apart the two thresholds must sit, and how
many confirmations the onset must demand, before this participant's own signal noise alone stops
flipping the controller's decision.

WHAT THIS PORTS AND FROM WHERE. The method-contest entry `kalman_est` (decision 150,
`artifacts/contest_2026-09-13_kalman_est.md`) treated one band's power as a slow, real level
watched through fast, meaningless wobble, fitted that split by maximum likelihood on this
participant's own recordings, and then asked a noise-only question of the fitted model: hold the
true level fixed at the midpoint between the two thresholds, simulate nothing but the fitted
wobble, and find the smallest threshold separation that keeps the wobble alone from producing more
than one false crossing an hour, for every averaging-and-onset pair the device offers. This file
is that same computation, built as production code (T3, `artifacts/contest_2026-09-13_SYNTHESIS.md`
section 4), read from the scratch scripts at
`BRAVO/_agent_bridge/_probe_tl/_contest/kalman_est/kf.py`, `k1_models.py`, `k2_derive.py` and
`k0b_ctrlsys.py` (gitignored, not in this repository) and ported here -- not re-derived.

THE TWO MODELS FITTED, and why only these two of the contest's thirteen. The contest compared
thirteen variants and found the nonlinear ones win the training likelihood by a wide margin and
then predict worse than doing nothing at all out of sample (their own section 2.2) -- the reading
they carried forward for the device's timing and thresholds was the plain **two-component** model,
a slow level plus a faster, quickly-decaying component, on top of measurement wobble ("L4, two
components"). This file fits exactly that model, and falls back to the plain **one-component**
local level ("L1") when the two-component fit does not converge to an identified two-component
answer -- which happened for real on the contest's own second band, where the fast component's own
variance fitted to zero and its carry-over number floated freely with nothing to anchor it. No
nonlinear variant is fitted here: none of them survived the contest's own out-of-sample test, and
carrying one forward here would be re-deriving a result the contest already rejected.

WHERE THE STEADY-STATE WEIGHT COMES FROM, and the one correction worth repeating. The weight the
fitted filter settles on for its newest reading is the fixed point of the discrete Riccati
equation, computed here two ways: the module's own numerical iteration (`riccati_steady_state`,
which always runs and is what every number below is actually built from), and, only where the
`ctrlsys` package can be imported -- the live server container, not this project's ordinary host
test environment -- an independent cross-check against `ctrlsys.sb02md`
(`ctrlsys_cross_check`). The contest's own note about that call is repeated here because it cost a
sign error to find: `sb02md`'s `hinv` argument must be `'I'`, not `'D'` -- with `'D'` it returns
the OTHER root of the equation. `ctrlsys_cross_check` uses `'I'`.

WHAT THE NOISE SIMULATION ACTUALLY COUNTS. `false_crossing_rate` holds the true level fixed at a
stated value, draws the fitted model's own measurement wobble (and, for the two-component model,
its fast-decaying component, drawn with `scipy.signal.lfilter` exactly as the contest drew it),
averages the simulated readings onto the device's own non-overlapping averaging windows, and counts
a *confirmed crossing* as a run of `onset / averaging` consecutive windows on the wrong side of a
threshold -- one count per such run, not one per reading, because that is what the controller
itself does: it changes state once per confirmed excursion, not once per sample that happens to lie
past the line. `min_separation_for_rate` sweeps a grid of separations at one averaging-and-onset
pair and returns the smallest one that holds the simulated rate at or below the target;
`separation_table` runs that sweep over the device's whole averaging x onset grid.

WHAT IS DELIBERATELY NOT PORTED. The nonlinear variance models (N1-N9), the local-linear-trend
family (L2, L3) and the current-dependence terms all belonged to the contest's thirteen-model
comparison and none of them is the model the contest's own judgement carried forward for the
device's timing and thresholds -- porting them here would be re-deriving work the contest already
did and set aside. The amplitude the device was delivering is threaded through
`design_rule_for_series`'s caller (`adapter.simulation_inputs_for_participant` already reads it)
but is not used by either fitted model in this file; it is kept in the function's inputs only so a
future gain-dependent model (T7, once a titration session exists) has it in hand without a second
change to the calling code.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
from scipy.optimize import minimize

_log = logging.getLogger(__name__)

try:
    from modules.DecodeCommon import device_ranges as _DR
except ImportError:                                              # pragma: no cover
    from DecodeCommon import device_ranges as _DR

KIND = "closed_loop_design_rule"
#: Bumped whenever a change here would change an already-stored table's numbers.
RULE_VERSION = "v2_onset_grid_capped_at_the_tablets_30s"

LOG2PI = float(np.log(2.0 * np.pi))

#: The device's own averaging x onset grid this rule is evaluated on. The averaging grid is the
#: contest's (`k2_derive.py`), spanning the documented 0-30 s. The ONSET grid was the contest's
#: 30, 60, 120 and 180 s until 2026-09-15, when the PI read the clinician tablet: the onset accepts
#: 0.00 ms to 30.00 s on both Dual timers (`DecodeCommon.device_ranges.ONSET_RANGE_DUAL_MS`), so
#: three of those four columns could never be typed in. His instruction: "limit the search grid to
#: evaluate onsets only up to a maximum of 30 seconds." The grid now mirrors the averaging grid, so
#: the table keeps two dimensions and every pair is enterable. The contest's finding "at 30 s
#: averaging no onset under 120 s reaches one false crossing an hour" therefore reads: at 30 s
#: averaging no enterable onset does.
AVERAGING_GRID_S: Tuple[float, ...] = (3.0, 6.0, 15.0, 30.0)
ONSET_GRID_S: Tuple[float, ...] = tuple(
    o for o in (3.0, 6.0, 15.0, 30.0) if o <= _DR.ONSET_RANGE_DUAL_MS[1] / 1000.0)
#: The separations the sweep tries at each averaging x onset pair, in the recorded series' own
#: units (device LSB). "never" (``None``) is reported when none of these holds the target.
SEPARATION_GRID: Tuple[float, ...] = (5.0, 10.0, 15.0, 20.0, 25.0, 30.0, 40.0, 60.0, 80.0, 120.0,
                                      160.0, 200.0, 300.0)
TARGET_CROSSINGS_PER_HOUR = 1.0
#: Hours of synthetic noise simulated per separation tried. The contest used 200 h; this uses 100 h
#: by default to keep the whole averaging x onset x separation sweep (4 x 4 x 13 = 208 simulations)
#: inside a request the page already accepts costs like this for (`write_simulation`, decision 41,
#: accepted a 50 s cold build). Each simulated hour is cheap (1,200 numpy draws at 3 s averaging),
#: so this is a request-time cost decision, not an accuracy one -- doubling it changes the answer by
#: less than one grid step in every check run while building this (see the decision's live proof).
DEFAULT_SIM_HOURS = 100.0
RNG_SEED = 20260913
#: The Nelder-Mead evaluation budget and restart count for each fit. The contest used 1200
#: evaluations and 2 restarts for the two-component model; this uses fewer by default to keep one
#: report's cost bounded, and states the reduction rather than hiding it -- the acceptance test for
#: this file is "how closely the design table lands to the contest's own", not a bit-exact
#: reproduction, since the contest's grid, hours and restart count were also its own choices.
DEFAULT_MAXFEV_L1 = 400
DEFAULT_MAXFEV_L4 = 900
DEFAULT_RESTARTS = 1
#: A two-component fit below this many training readings has too little to identify a fast
#: component from a slow one; the L1 fallback is used instead and the reason says so.
MIN_READINGS_FOR_TWO_COMPONENT = 200


# ---------------------------------------------------------------------------------------------
# The fitted model
# ---------------------------------------------------------------------------------------------
@dataclass
class FittedModel:
    """A fitted local-level model: ``kind`` is ``"1state"`` (L1, a plain local level) or
    ``"2comp"`` (L4, a slow level plus a faster, decaying component), both plus measurement
    wobble. Only the fields the model's own ``kind`` uses are set; the rest stay ``None``."""

    kind: str
    m: float
    r0: float
    nll: float
    k: int
    n: int
    phi: Optional[float] = None
    q: Optional[float] = None
    phi_s: Optional[float] = None
    phi_f: Optional[float] = None
    q_s: Optional[float] = None
    q_f: Optional[float] = None

    @property
    def aic(self) -> float:
        return 2.0 * self.nll + 2.0 * self.k

    def as_dict(self) -> Dict[str, Any]:
        return {"kind": self.kind, "m": self.m, "r0": self.r0, "nll": self.nll, "k": self.k,
                "n": self.n, "aic": self.aic, "phi": self.phi, "q": self.q, "phi_s": self.phi_s,
                "phi_f": self.phi_f, "q_s": self.q_s, "q_f": self.q_f}


def _sig(u):
    return 1.0 / (1.0 + np.exp(-np.clip(u, -40.0, 40.0)))


def _logit(p):
    return float(np.log(p / (1.0 - p)))


# ---------------------------------------------------------------------------------------------
# The panel, and the two filters (ported from kf.py, with the amplitude- and level-dependent
# variance terms dropped: neither fitted model here uses them, see the module docstring)
# ---------------------------------------------------------------------------------------------
def build_panel(stretches: Sequence[Tuple[np.ndarray, np.ndarray, np.ndarray]],
                min_len: int = 3) -> np.ndarray:
    """A padded ``(S, L)`` array of band power from ``simulation.regrid_stretches``'s stretches.

    Leading missing readings of a stretch are dropped so column 0 is always a real reading, exactly
    as the contest's own panel builder does. A stretch with fewer than ``min_len`` finite readings
    is left out entirely. Raises ``ValueError`` when nothing is left, which the caller turns into a
    refusal rather than a fit on no data.
    """
    rows = []
    for _t, p, _a in stretches:
        p = np.asarray(p, dtype=float)
        ok = np.isfinite(p)
        if int(ok.sum()) < min_len:
            continue
        first = int(np.argmax(ok))
        rows.append(p[first:])
    if not rows:
        raise ValueError("no stretch has enough finite readings to fit a design-rule model on "
                         f"(min_len={min_len})")
    s = len(rows)
    l = max(r.size for r in rows)
    y = np.full((s, l), np.nan)
    for k, r in enumerate(rows):
        y[k, :r.size] = r
    return y


def filter_1state(Y: np.ndarray, *, phi: float, m: float, q: float, r0: float) -> Dict[str, Any]:
    """The plain local level: ``level_t = m + phi*(level_{t-1} - m) + w`` (w ~ N(0, q)),
    ``y_t = level_t + e`` (e ~ N(0, r0)). Started at the first reading of every row; the
    log-likelihood is summed from the second reading of every row onward, matching the contest's
    own convention so no arbitrary starting guess enters the comparison."""
    s, l = Y.shape
    x = Y[:, 0].copy()
    p = np.full(s, float(r0))
    m_ok = np.isfinite(Y)
    ll = 0.0
    n_used = 0
    for t in range(1, l):
        xp = m + phi * (x - m)
        pp = phi * phi * p + q
        f = pp + r0
        mt = m_ok[:, t]
        v = np.where(mt, Y[:, t] - xp, 0.0)
        ll += float(np.sum(np.where(mt, -0.5 * (LOG2PI + np.log(f) + v * v / f), 0.0)))
        n_used += int(mt.sum())
        k = np.where(mt, pp / f, 0.0)
        x = xp + k * v
        p = np.where(mt, (1.0 - k) * pp, pp)
    return {"loglik": ll, "n": n_used}


def filter_2comp(Y: np.ndarray, *, phi_s: float, phi_f: float, q_s: float, q_f: float, m: float,
                 r0: float) -> Dict[str, Any]:
    """The two-component filter (see `_filter_2comp_numpy`), run as a compiled loop when numba is
    installed and as the numpy loop otherwise, with the same answer either way (decision 269)."""
    if COMPILED_FILTER:
        Yc = np.ascontiguousarray(Y, dtype=float)
        vs = q_s / max(1e-12, 1.0 - phi_s * phi_s)
        vf = q_f / max(1e-12, 1.0 - phi_f * phi_f)
        ll, n_used = _filter_2comp_kernel(Yc, np.isfinite(Yc), float(phi_s), float(phi_f), float(q_s),
                                          float(q_f), float(m), float(r0), float(vs), float(vf), LOG2PI)
        return {"loglik": float(ll), "n": int(n_used)}
    return _filter_2comp_numpy(Y, phi_s=phi_s, phi_f=phi_f, q_s=q_s, q_f=q_f, m=m, r0=r0)


# SPEED-UP ITEM 3 (the PI, 2026-09-25: "add numba and do option 1"). The numpy loop below does about
# 30 small array operations per time step; on RCS08 (349 stretches x 1,499 steps) a call took 29 ms,
# nearly all of it numpy's per-call overhead, and a fit makes about 1,600 calls. The compiled loop
# performs the SAME operations on each stretch in the SAME order, so every number is the same:
#   * add, subtract, multiply and divide are exactly rounded, whichever code runs them;
#   * the log is the same library function numpy calls here (checked on 2,000 arrays, 0 differing);
#   * each step's terms are summed in numpy's own order -- pairwise over the whole row, 8 running sums
#     for a block of up to 128, halves split at a multiple of 8 above that (checked against np.sum
#     on 3,000 arrays, 0 differing); a plain left-to-right sum would NOT match.
# `tests/test_design_rule_compiled_filter.py` holds the two loops equal. COMPILED_FILTER False forces
# the numpy loop (the proof compares the two). NO ON-DISK CACHE: the summation calls itself, and a
# cached recursive function crashed the process when loaded under the server's libraries (measured
# 2026-09-25: segmentation fault from the cache, none when compiled in the process); each worker
# compiles once on its first fit, about a second.
try:
    import math as _math
    from numba import njit as _njit
    # numba logs its own type checking at DEBUG, and the server logs at DEBUG: the first fit in each
    # worker wrote 38,760 lines of it (measured 2026-09-25). Its warnings and errors still show.
    logging.getLogger("numba").setLevel(logging.WARNING)

    @_njit(cache=False)
    def _pairwise_sum(a, lo, n):                      # numpy's DOUBLE_pairwise_sum, stride 1
        if n < 8:
            res = 0.0
            for i in range(n):
                res += a[lo + i]
            return res
        elif n <= 128:
            r0 = a[lo]; r1 = a[lo + 1]; r2 = a[lo + 2]; r3 = a[lo + 3]
            r4 = a[lo + 4]; r5 = a[lo + 5]; r6 = a[lo + 6]; r7 = a[lo + 7]
            i = 8
            while i < n - (n % 8):
                r0 += a[lo + i]; r1 += a[lo + i + 1]; r2 += a[lo + i + 2]; r3 += a[lo + i + 3]
                r4 += a[lo + i + 4]; r5 += a[lo + i + 5]; r6 += a[lo + i + 6]; r7 += a[lo + i + 7]
                i += 8
            res = ((r0 + r1) + (r2 + r3)) + ((r4 + r5) + (r6 + r7))
            while i < n:
                res += a[lo + i]
                i += 1
            return res
        else:
            n2 = n // 2
            n2 -= n2 % 8
            return _pairwise_sum(a, lo, n2) + _pairwise_sum(a, lo + n2, n - n2)

    @_njit(cache=False)
    def _filter_2comp_kernel(Y, ok, phi_s, phi_f, q_s, q_f, m, r0, vs, vf, log2pi):
        s, l = Y.shape
        xs = np.zeros(s); xf = np.zeros(s)
        p11 = np.empty(s); p22 = np.empty(s); p12 = np.zeros(s)
        for i in range(s):
            p11[i] = vs
            p22[i] = vf
        for i in range(s):                               # step 0, unmasked, as the numpy loop
            f0 = p11[i] + 2.0 * p12[i] + p22[i] + r0
            v0 = Y[i, 0] - m
            k1 = (p11[i] + p12[i]) / f0
            k2 = (p12[i] + p22[i]) / f0
            xs[i] = xs[i] + k1 * v0
            xf[i] = xf[i] + k2 * v0
            a1 = p11[i] + p12[i]
            a2 = p12[i] + p22[i]
            p11[i] = p11[i] - k1 * a1
            p12[i] = p12[i] - k1 * a2
            p22[i] = p22[i] - k2 * a2
        ps2 = phi_s * phi_s
        psf = phi_s * phi_f
        pf2 = phi_f * phi_f
        term = np.empty(s)
        ll = 0.0
        n_used = 0
        for t in range(1, l):
            for i in range(s):
                xsp = phi_s * xs[i]
                xfp = phi_f * xf[i]
                p11p = ps2 * p11[i] + q_s
                p12p = psf * p12[i]
                p22p = pf2 * p22[i] + q_f
                xp = m + xsp + xfp
                f = p11p + 2.0 * p12p + p22p + r0
                mt = ok[i, t]
                v = (Y[i, t] - xp) if mt else 0.0
                term[i] = (-0.5 * (log2pi + _math.log(f) + v * v / f)) if mt else 0.0
                if mt:
                    n_used += 1
                a1 = p11p + p12p
                a2 = p12p + p22p
                k1 = (a1 / f) if mt else 0.0
                k2 = (a2 / f) if mt else 0.0
                xs[i] = xsp + k1 * v
                xf[i] = xfp + k2 * v
                p11[i] = p11p - k1 * a1
                p12[i] = p12p - k1 * a2
                p22[i] = p22p - k2 * a2
            ll += _pairwise_sum(term, 0, s)
        return ll, n_used

    COMPILED_FILTER = True
except Exception:                                        # noqa: BLE001 -- no numba: the numpy loop
    COMPILED_FILTER = False


def _filter_2comp_numpy(Y: np.ndarray, *, phi_s: float, phi_f: float, q_s: float, q_f: float, m: float,
                        r0: float) -> Dict[str, Any]:
    """A slow component plus a faster, decaying component plus measurement wobble:
    ``y_t = m + slow_t + fast_t + e_t``. Covariance carried as three scalars, vectorised over
    stretches -- the contest's own `filter_2comp`, with the amplitude- and level-dependent
    variance terms (unused by the model this file fits) removed."""
    s, l = Y.shape
    vs = q_s / max(1e-12, 1.0 - phi_s * phi_s)
    vf = q_f / max(1e-12, 1.0 - phi_f * phi_f)
    xs = np.zeros(s)
    xf = np.zeros(s)
    p11 = np.full(s, vs)
    p22 = np.full(s, vf)
    p12 = np.zeros(s)
    m_ok = np.isfinite(Y)
    y0 = Y[:, 0]
    f0 = p11 + 2.0 * p12 + p22 + r0
    v0 = y0 - m
    k1 = (p11 + p12) / f0
    k2 = (p12 + p22) / f0
    xs = xs + k1 * v0
    xf = xf + k2 * v0
    a1 = p11 + p12
    a2 = p12 + p22
    p11 = p11 - k1 * a1
    p12 = p12 - k1 * a2
    p22 = p22 - k2 * a2
    ll = 0.0
    n_used = 0
    for t in range(1, l):
        xsp = phi_s * xs
        xfp = phi_f * xf
        p11p = phi_s * phi_s * p11 + q_s
        p12p = phi_s * phi_f * p12
        p22p = phi_f * phi_f * p22 + q_f
        xp = m + xsp + xfp
        f = p11p + 2.0 * p12p + p22p + r0
        mt = m_ok[:, t]
        v = np.where(mt, Y[:, t] - xp, 0.0)
        ll += float(np.sum(np.where(mt, -0.5 * (LOG2PI + np.log(f) + v * v / f), 0.0)))
        n_used += int(mt.sum())
        a1 = p11p + p12p
        a2 = p12p + p22p
        k1 = np.where(mt, a1 / f, 0.0)
        k2 = np.where(mt, a2 / f, 0.0)
        xs = xsp + k1 * v
        xf = xfp + k2 * v
        p11 = p11p - k1 * a1
        p12 = p12p - k1 * a2
        p22 = p22p - k2 * a2
    return {"loglik": ll, "n": n_used}


# ---------------------------------------------------------------------------------------------
# Fitting: maximum likelihood by Nelder-Mead, ported from k1_models.py / kf.py's nll_of
# ---------------------------------------------------------------------------------------------
def _scales(Y: np.ndarray) -> Dict[str, float]:
    v = Y[np.isfinite(Y)]
    mbar = float(np.median(v))
    mad = float(np.median(np.abs(v - mbar))) * 1.4826
    return {"mbar": mbar, "var_rob": float(mad * mad) if mad > 0 else 1.0, "n": int(v.size)}


def _fit_nm(nll, x0, maxfev, restarts):
    x = np.asarray(x0, dtype=float)
    best = None
    for _ in range(max(1, int(restarts))):
        best = minimize(nll, x, method="Nelder-Mead",
                        options={"maxfev": int(maxfev), "xatol": 1e-4, "fatol": 1e-3,
                                 "adaptive": True})
        x = best.x
    return best


def fit_local_level(Y: np.ndarray, *, maxfev: int = DEFAULT_MAXFEV_L1,
                    restarts: int = DEFAULT_RESTARTS) -> FittedModel:
    """Maximum-likelihood fit of the plain local level (L1): ``phi=1`` (a random walk), free ``q``
    and ``r0``. The contest's own starting point: ``q0 = 0.05`` of the robust variance, ``r0`` the
    robust variance itself."""
    sc = _scales(Y)
    mbar, var_rob = sc["mbar"], sc["var_rob"]

    def nll(u):
        q = float(np.exp(u[0]))
        r0 = float(np.exp(u[1]))
        if not (np.isfinite(q) and np.isfinite(r0)) or q <= 0.0 or r0 <= 0.0:
            return 1e12
        try:
            v = -filter_1state(Y, phi=1.0, m=mbar, q=q, r0=r0)["loglik"]
        except Exception:                              # noqa: BLE001
            return 1e12
        return v if np.isfinite(v) else 1e12

    x0 = [np.log(var_rob * 0.05), np.log(var_rob)]
    res = _fit_nm(nll, x0, maxfev, restarts)
    q = float(np.exp(res.x[0]))
    r0 = float(np.exp(res.x[1]))
    return FittedModel(kind="1state", phi=1.0, q=q, r0=r0, m=mbar, nll=float(res.fun), k=2,
                       n=sc["n"])


def fit_two_component(Y: np.ndarray, *, maxfev: int = DEFAULT_MAXFEV_L4,
                      restarts: int = DEFAULT_RESTARTS) -> FittedModel:
    """Maximum-likelihood fit of the two-component model (L4): a slow, damped level (``phi_s``,
    ``q_s``) plus a faster, more-damped component (``phi_f``, ``q_f``, with ``phi_f < phi_s``
    enforced so the two components stay identified as slow-and-fast rather than swapping), plus
    measurement wobble ``r0``. The contest's own starting point (`k1_models.py`, ``L4_two_component``)."""
    sc = _scales(Y)
    mbar, var_rob = sc["mbar"], sc["var_rob"]

    def unpack(u):
        return (_sig(u[0]), _sig(u[1]), float(np.exp(u[2])), float(np.exp(u[3])),
                float(np.exp(u[4])), float(u[5]) * 100.0)

    def nll(u):
        phi_s, phi_f, q_s, q_f, r0, m = unpack(u)
        if not all(np.isfinite(v) for v in (phi_s, phi_f, q_s, q_f, r0, m)):
            return 1e12
        if q_s <= 0.0 or q_f <= 0.0 or r0 <= 0.0:
            return 1e12
        if phi_f >= phi_s:                             # keeps "slow" and "fast" from swapping
            return 1e12
        try:
            v = -filter_2comp(Y, phi_s=phi_s, phi_f=phi_f, q_s=q_s, q_f=q_f, m=m, r0=r0)["loglik"]
        except Exception:                              # noqa: BLE001
            return 1e12
        return v if np.isfinite(v) else 1e12

    x0 = [_logit(0.99), _logit(0.25), np.log(var_rob * 0.01), np.log(var_rob * 0.3),
          np.log(var_rob * 0.6), mbar / 100.0]
    res = _fit_nm(nll, x0, maxfev, restarts)
    phi_s, phi_f, q_s, q_f, r0, m = unpack(res.x)
    return FittedModel(kind="2comp", phi_s=phi_s, phi_f=phi_f, q_s=q_s, q_f=q_f, r0=r0, m=m,
                       nll=float(res.fun), k=6, n=sc["n"])


def fit_design_model(stretches, *, prefer: str = "2comp", maxfev_l1: int = DEFAULT_MAXFEV_L1,
                     maxfev_l4: int = DEFAULT_MAXFEV_L4,
                     restarts: int = DEFAULT_RESTARTS) -> Tuple[FittedModel, str]:
    """Fit the two-component model (L4) and fall back to the plain local level (L1) when the
    two-component fit does not converge to an identified two-component answer. Returns
    ``(model, chosen)`` where ``chosen`` names which model is returned and, on a fallback, why.

    THE FALLBACK CRITERIA, stated because they decide which model a reader is shown. The
    two-component fit is rejected, and L1 used instead, when: the panel has fewer than
    ``MIN_READINGS_FOR_TWO_COMPONENT`` finite readings (too little to identify a fast component
    from a slow one); the optimiser could not escape the constraint penalty (``nll >= 1e11``, the
    same sentinel the objective returns for an infeasible point); or the returned fit is not
    finite. This is the same situation the contest met on its own second band, where the
    two-component fit's fast-component variance landed at zero and its carry-over floated freely
    with nothing left to identify -- the contest kept that fit and said so in words; this function
    states it as an explicit, testable rule instead and falls back to the model that IS identified.
    """
    y = build_panel(stretches)
    l1 = fit_local_level(y, maxfev=maxfev_l1, restarts=restarts)
    if prefer != "2comp":
        return l1, "L1 local level (requested)"
    n_finite = int(np.isfinite(y).sum())
    if n_finite < MIN_READINGS_FOR_TWO_COMPONENT:
        return l1, (f"L1 local level (fallback: only {n_finite} finite readings, fewer than the "
                    f"{MIN_READINGS_FOR_TWO_COMPONENT} a two-component fit needs to identify a "
                    "fast component separately from the slow one)")
    try:
        l4 = fit_two_component(y, maxfev=maxfev_l4, restarts=restarts)
    except Exception as ex:                            # noqa: BLE001
        _log.warning("closed-loop design rule: the two-component fit raised", exc_info=True)
        return l1, f"L1 local level (fallback: the two-component fit raised {ex!r})"
    if not np.isfinite(l4.nll) or l4.nll >= 1e11:
        return l1, ("L1 local level (fallback: the two-component fit did not converge to an "
                    "identified two-component answer)")
    return l4, "L4 two components"


# ---------------------------------------------------------------------------------------------
# The steady-state weight (the Riccati fixed point), and its optional ctrlsys cross-check
# ---------------------------------------------------------------------------------------------
def state_space_matrices(model: FittedModel):
    """``(A, C, Q, R)`` of the fitted model, in the shape both `riccati_steady_state` and
    `ctrlsys_cross_check` expect."""
    if model.kind == "1state":
        a = np.array([[model.phi]])
        c = np.array([[1.0]])
        q = np.array([[model.q]])
    else:
        a = np.diag([model.phi_s, model.phi_f])
        c = np.array([[1.0, 1.0]])
        q = np.diag([model.q_s, model.q_f])
    return a, c, q, float(model.r0)


def riccati_steady_state(a: np.ndarray, c: np.ndarray, q: np.ndarray, r: float,
                         iters: int = 20000, tol: float = 1e-13) -> Dict[str, Any]:
    """Iterate the discrete Riccati equation to its fixed point. This is the PRIMARY computation
    -- it needs nothing but numpy and runs identically on the host test environment and the
    server container. See `ctrlsys_cross_check` for the independent check the contest ran against
    it, which only the container can run."""
    n = a.shape[0]
    p = np.eye(n) * r
    i = 0
    for i in range(iters):
        pp = a @ p @ a.T + q
        f = float((c @ pp @ c.T).reshape(-1)[0]) + r
        k = (pp @ c.T) / f
        pn = pp - k @ (c @ pp)
        if np.max(np.abs(pn - p)) < tol * max(1.0, np.max(np.abs(p))):
            p = pn
            break
        p = pn
    pp = a @ p @ a.T + q
    f = float((c @ pp @ c.T).reshape(-1)[0]) + r
    k = (pp @ c.T) / f
    return {"P_filt": p, "P_pred": pp, "K": k, "innov_var": f, "iters": i + 1}


def ctrlsys_cross_check(a: np.ndarray, c: np.ndarray, q: np.ndarray, r: float) -> Dict[str, Any]:
    """The independent check the contest ran on this same Riccati equation, through
    ``ctrlsys.sb02md``. ``ctrlsys`` is a container-only dependency -- not installed in this
    project's ordinary host test environment -- so this returns ``{"available": False}`` there,
    and `riccati_steady_state`'s own iteration remains the number everything else in this file is
    built from either way. ``hinv='I'``, not ``'D'``: with ``'D'`` the routine returns the OTHER
    root of the equation, found by the contest against a scalar case whose answer was already
    known by iteration."""
    try:
        import ctrlsys
    except ImportError:
        return {"available": False}
    n = a.shape[0]
    g = np.asfortranarray((c.T @ c) / r)
    try:
        out = ctrlsys.sb02md('D', 'I', 'U', 'N', 'S', n, np.asfortranarray(a.T.copy()), g.copy(),
                             np.asfortranarray(q.copy()))
        x, info = out[0], out[-1]
        mine = riccati_steady_state(a, c, q, r)["P_pred"]
        theirs = np.asarray(x)
        dd = float(np.max(np.abs(theirs - mine)))
        rel = dd / max(1e-12, float(np.max(np.abs(mine))))
        return {"available": True, "ok": bool(info == 0), "info": int(info),
                "max_abs_difference": dd, "relative_difference": rel}
    except Exception as ex:                            # noqa: BLE001
        return {"available": True, "ok": False, "error": f"{type(ex).__name__}: {ex}"}


# ---------------------------------------------------------------------------------------------
# The noise-only crossing simulation, ported from k2_derive.false_crossing_rate
# ---------------------------------------------------------------------------------------------
def false_crossing_rate(model: FittedModel, *, averaging_s: float, onset_s: float,
                        separation: float, hours: float, level: float,
                        rng: np.random.Generator, dt_s: float) -> Dict[str, Any]:
    """Hold the true level FIXED at ``level`` and simulate nothing but the fitted model's own
    measurement wobble (plus, for a two-component model, its faster, decaying component), average
    onto the device's own non-overlapping ``averaging_s`` windows, and count a *confirmed
    crossing* as a run of ``ceil(onset_s / averaging_s)`` consecutive windows on the wrong side of
    a threshold -- one count per run, matching the controller's own behaviour of changing state
    once per confirmed excursion rather than once per sample."""
    r = float(model.r0)
    n_steps = int(round(hours * 3600.0 / dt_s))
    if n_steps <= 0:
        return {"above": 0.0, "below": 0.0, "total_per_hour": 0.0, "window_s": averaging_s,
                "windows_in_onset": 1}
    e = rng.normal(0.0, np.sqrt(max(r, 0.0)), n_steps)
    fast = np.zeros(n_steps)
    if model.kind == "2comp":
        from scipy.signal import lfilter
        w = rng.normal(0.0, np.sqrt(max(model.q_f, 0.0)), n_steps)
        fast = lfilter([1.0], [1.0, -model.phi_f], w)
    y = level + fast + e
    n_per = max(1, int(round(averaging_s / dt_s)))
    n_win = y.size // n_per
    if n_win == 0:
        return {"above": 0.0, "below": 0.0, "total_per_hour": 0.0, "window_s": n_per * dt_s,
                "windows_in_onset": 1}
    z = y[:n_win * n_per].reshape(n_win, n_per).mean(axis=1)
    n_on = max(1, int(np.ceil(onset_s / (n_per * dt_s))))
    out: Dict[str, Any] = {}
    for side, thr in (("above", level + separation), ("below", level - separation)):
        b = (z > thr) if side == "above" else (z < thr)
        d = np.diff(np.concatenate(([0], b.astype(np.int8), [0])))
        starts = np.flatnonzero(d == 1)
        ends = np.flatnonzero(d == -1)
        out[side] = float(np.sum((ends - starts) >= n_on)) / hours
    out["total_per_hour"] = out["above"] + out["below"]
    out["window_s"] = n_per * dt_s
    out["windows_in_onset"] = n_on
    return out


def min_separation_for_rate(model: FittedModel, *, averaging_s: float, onset_s: float,
                            level: float, rng: np.random.Generator, dt_s: float,
                            target_per_hour: float = TARGET_CROSSINGS_PER_HOUR,
                            hours: float = DEFAULT_SIM_HOURS,
                            separations: Sequence[float] = SEPARATION_GRID
                            ) -> Tuple[Optional[float], List[Dict[str, float]]]:
    """The smallest separation in ``separations`` that holds the simulated noise-only crossing
    rate at or below ``target_per_hour``, and the whole sweep it was chosen from. ``None`` means
    none of the tried separations was enough -- "never", in the contest's own words."""
    sweep = []
    for sep in separations:
        r = false_crossing_rate(model, averaging_s=averaging_s, onset_s=onset_s,
                                separation=float(sep), hours=hours, level=level, rng=rng,
                                dt_s=dt_s)
        sweep.append({"separation": float(sep), "total_per_hour": float(r["total_per_hour"])})
    ok = [row["separation"] for row in sweep if row["total_per_hour"] <= target_per_hour]
    return (min(ok) if ok else None), sweep


def separation_table(model: FittedModel, *, level: float,
                     averaging_grid: Sequence[float] = AVERAGING_GRID_S,
                     onset_grid: Sequence[float] = ONSET_GRID_S,
                     separations: Sequence[float] = SEPARATION_GRID,
                     hours: float = DEFAULT_SIM_HOURS,
                     target_per_hour: float = TARGET_CROSSINGS_PER_HOUR,
                     seed: int = RNG_SEED, dt_s: float = 3.0) -> List[Dict[str, Any]]:
    """The whole averaging x onset grid: one row per pair, each carrying the minimum separation
    (or ``None`` for "never") and the sweep it came from. One random generator is used across the
    whole grid (continuing its stream from pair to pair, as the contest's own script did) rather
    than a fresh one per pair, so the table is one coherent simulation rather than sixteen
    independent, differently-seeded ones."""
    rng = np.random.default_rng(seed)
    rows = []
    for avg in averaging_grid:
        # 2026-09-15: the device counts the onset in whole averaging windows (D14, decision 150),
        # so two onsets that round to the same window count are ONE configuration. With the onset
        # grid capped at the tablet's 30 s, that happens at 30 s averaging for every onset on the
        # grid; simulated separately they printed two different requirements (200 and 300 device
        # units) for the same setting. The first onset of each window count is simulated and the
        # others copy it, and each row says which onset it shares its answer with.
        n_per = max(1, int(round(float(avg) / float(dt_s))))
        by_windows: Dict[int, Dict[str, Any]] = {}
        for onset in onset_grid:
            n_on = max(1, int(np.ceil(float(onset) / (n_per * float(dt_s)))))
            first = by_windows.get(n_on)
            if first is None:
                need, sweep = min_separation_for_rate(model, averaging_s=avg, onset_s=onset,
                                                       level=level, rng=rng, dt_s=dt_s,
                                                       target_per_hour=target_per_hour,
                                                       hours=hours, separations=separations)
                row = {"averaging_s": float(avg), "onset_s": float(onset),
                       "min_separation": need, "sweep": sweep, "windows_in_onset": int(n_on),
                       "same_configuration_as_onset_s": None}
                by_windows[n_on] = row
            else:
                row = {"averaging_s": float(avg), "onset_s": float(onset),
                       "min_separation": first["min_separation"], "sweep": first["sweep"],
                       "windows_in_onset": int(n_on),
                       "same_configuration_as_onset_s": float(first["onset_s"])}
            rows.append(row)
    return rows


def lookup_min_separation(rows: Sequence[Dict[str, Any]], *, averaging_ms: float,
                          onset_ms: float, tol_s: float = 0.5) -> Optional[Dict[str, Any]]:
    """The design table's row nearest an arbitrary averaging/onset pair (in ms, matching how the
    parameter card carries timing values), and whether that row is an exact grid match within
    ``tol_s`` seconds of both. ``None`` when ``rows`` is empty."""
    if not rows:
        return None
    avg_s = float(averaging_ms) / 1000.0
    ons_s = float(onset_ms) / 1000.0
    best = min(rows, key=lambda row: abs(row["averaging_s"] - avg_s) + abs(row["onset_s"] - ons_s))
    exact = (abs(best["averaging_s"] - avg_s) <= tol_s and abs(best["onset_s"] - ons_s) <= tol_s)
    return dict(best, exact_match=exact)


# ---------------------------------------------------------------------------------------------
# The analytic check for a single, unaveraged, unconfirmed reading (the white-noise acceptance
# test's own reference answer -- see tests/test_design_rule.py)
# ---------------------------------------------------------------------------------------------
def analytic_min_separation(sigma: float, readings_per_hour: float,
                            target_per_hour: float = TARGET_CROSSINGS_PER_HOUR) -> float:
    """The minimum separation for i.i.d. Gaussian(0, sigma^2) readings, one independent reading
    per decision (no averaging, one reading confirms), at ``readings_per_hour`` readings an hour,
    to keep at most ``target_per_hour`` false crossings an hour.

    TWO-SIDED ACCOUNTING, stated because it is the one place this is easy to get wrong. Each
    reading is tested against BOTH thresholds independently (a reading can be a false "above"
    crossing or a false "below" crossing, never both), so the total false-crossing rate is
    ``readings_per_hour * 2 * (1 - Phi(sep/sigma))`` and the minimum separation solves
    ``readings_per_hour * 2 * (1 - Phi(sep/sigma)) = target_per_hour``, i.e.
    ``sep = sigma * Phi^-1(1 - target_per_hour / (2 * readings_per_hour))``.
    """
    from scipy.stats import norm
    p_two_sided = float(target_per_hour) / (2.0 * float(readings_per_hour))
    return float(sigma) * float(norm.ppf(1.0 - p_two_sided))


# ---------------------------------------------------------------------------------------------
# The one entry point a caller needs: fit on a participant's own series, build the table
# ---------------------------------------------------------------------------------------------
def design_rule_for_series(t, power, amp_obs, *, upper: float, lower: float,
                           prefer: str = "2comp", maxfev_l1: int = DEFAULT_MAXFEV_L1,
                           maxfev_l4: int = DEFAULT_MAXFEV_L4, restarts: int = DEFAULT_RESTARTS,
                           hours: float = DEFAULT_SIM_HOURS, seed: int = RNG_SEED,
                           averaging_grid: Sequence[float] = AVERAGING_GRID_S,
                           onset_grid: Sequence[float] = ONSET_GRID_S,
                           separations: Sequence[float] = SEPARATION_GRID) -> Dict[str, Any]:
    """Fit the design-rule model on one participant's own 3 s power series and build the
    separation table, holding the noise simulation's level at the midpoint of ``upper``/``lower``
    -- the same convention the contest used (`k2_derive.py`, ``mid``).

    ``t``, ``power``, ``amp_obs`` are the same series `simulation.regrid_stretches` accepts
    (`adapter.simulation_inputs_for_participant`'s own output); the device clock (the averaging
    unit the table's rows are quoted in seconds of) is read from the series' own median interval,
    not hardcoded, so a change to how often the tiles are built is honoured automatically.
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
    try:
        model, chosen = fit_design_model(stretches, prefer=prefer, maxfev_l1=maxfev_l1,
                                         maxfev_l4=maxfev_l4, restarts=restarts)
    except ValueError as ex:
        return {"refused": True, "reason": str(ex)}
    level = 0.5 * (float(upper) + float(lower))
    a_m, c_m, q_m, r_m = state_space_matrices(model)
    ss = riccati_steady_state(a_m, c_m, q_m, r_m)
    cross = ctrlsys_cross_check(a_m, c_m, q_m, r_m)
    table = separation_table(model, level=level, averaging_grid=averaging_grid,
                             onset_grid=onset_grid, separations=separations, hours=hours,
                             seed=seed, dt_s=dt_s)
    return {
        "refused": False, "model": chosen, "fitted": model.as_dict(),
        "level_midpoint": level, "upper": float(upper), "lower": float(lower),
        "device_clock_s": dt_s, "n_train_stretches": len(stretches),
        "n_train_readings": int(model.n), "n_cells_empty": int(n_empty),
        "n_cells_merged": int(n_merged), "hours_simulated_per_cell": float(hours),
        "target_crossings_per_hour": float(TARGET_CROSSINGS_PER_HOUR),
        "riccati": {"gain": np.asarray(ss["K"]).ravel().tolist(),
                   "innovation_sd": float(np.sqrt(ss["innov_var"]))},
        "ctrlsys_cross_check": cross,
        "table": table,
    }
