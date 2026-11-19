"""Step C of the contact-aware Stim Optimizer: which (Left contact, rate) block to test at the
next clinic visit (the PI's go-ahead and rulings of 2026-10-01; plan
`.planning/2026-09-30-contact-aware-stim-optimizer/`).

THE TWO LEVELS. Between visits the model picks the BLOCK: one Left contact at one rate, at the
pulse-width pairing in force (ruling 5 of decision 233: the next session runs at that pairing).
Within the visit the block is run as the fixed ladder -- 0 mA up to the Left maximum in 0.5 mA
steps, back down in 1.0 mA drops (`titration_plan.ladder`) -- because a ladder is what gives the
change in band power per milliamp and a pain rating at every current. In-clinic ratings choose;
home ratings confirm and are never merged with them (the PI, 2026-09-30).

THE CANDIDATES (his choice): every Left contact that has carried current in either stream, plus
L C+1-2- -- the only Left configuration that allows sensing on L 0-3 (decision 217's rule) -- at
every rate offered, except rates below the closed-loop minimum (`percept_adaptive`).

THE RANKING (his choice: most promising first). For a block with a fitted clinic surface (step A's
per-rate surface for that pairing, Left contact and rate), the score is the largest PLAUSIBLE
improvement in pain over the setting in force -- the predicted improvement plus 2 SD -- at a current
pair that is inside the surface's safe set and under both sides' maxima; the pair is reported. A
block with no fitted surface has no prediction of its own, so it gets the same bound from the
stream's own spread of J, prior mean "no change": 2 x prior_sd. A tie goes to the block with
fewer stretches. Units: NRS points (J is pain against the setting in force; lower J is better).

WHAT THIS IS NOT. It is not a claim that the top block will help: with surfaces this thin the
bound is mostly uncertainty, which the `basis` field says block by block.
"""
from __future__ import annotations

import numpy as np
from scipy import optimize

from . import percept_adaptive as PA
from .contact_pooling import _matern32, RATE_LENGTH_SCALE_OCTAVES

C12 = "L C+1-2-"
PRIOR_BASIS = "no surface: the stream's own spread"
FITTED_BASIS = "fitted surface"
BORROWED_BASIS = ("borrowed across rates and pulse widths: this contact's own clinic stretches, "
                  "read at the pulse widths in force; limited by the maxima only")
K_SD = 2.0
#: The same minimum the Stage 1 groups use (`stage1_openloop.PW_STRATUM_MIN_EPOCHS`).
BORROW_MIN_STRETCHES = 8
AMP_GRID_MA = tuple(round(0.25 * k, 2) for k in range(21))     # 0-5 mA, the live grid's step


class BorrowedSurfaceGP:
    """BORROWING ACROSS RATES AND PULSE WIDTHS (the PI, 2026-10-01: "extend it to borrow across
    pulse widths"). One exact GP per Left contact over its own clinic stretches (and the shared
    Left-0-mA ones), inputs (log2 rate, L mA, R mA, log2 L pulse width, log2 R pulse width):
    Matern 3/2; rate PINNED at one octave as in the live fit; the two currents' length scales and
    ONE pulse-width length scale (octaves) fitted; each stretch's obs_var on the diagonal; J
    standardised. It is read at the block's rate and the pulse widths in force, so a contact tried
    only at other pulse widths still gets a prediction there -- an extrapolation in pulse width,
    which the block's basis says."""

    BOUNDS = [(1e-3, 1e2), (0.3, 20.0), (0.3, 20.0), (0.25, 8.0), (1e-6, 1.0)]

    @staticmethod
    def _X(d):
        return np.column_stack([np.log2(d["freq_hz"].to_numpy(float)),
                                d["amp_mA_Left"].to_numpy(float), d["amp_mA_Right"].to_numpy(float),
                                np.log2(d["pw_us_Left"].to_numpy(float)),
                                np.log2(d["pw_us_Right"].to_numpy(float))])

    def _K(self, th, A, B=None):
        s2, lL, lR, lpw, _ = np.exp(th)
        ls = [RATE_LENGTH_SCALE_OCTAVES, lL, lR, lpw, lpw]
        return s2 * _matern32(A, A if B is None else B, ls)

    def fit(self, d):
        X = self._X(d)
        y = d["J"].to_numpy(float)
        self._loc, self._scale = float(y.mean()), float(max(y.std(ddof=0), 1e-9))
        yz = (y - self._loc) / self._scale
        alpha = d["obs_var"].to_numpy(float) / self._scale ** 2
        lb, ub = np.log([b[0] for b in self.BOUNDS]), np.log([b[1] for b in self.BOUNDS])

        def nlml(th):
            K = self._K(th, X)
            K[np.diag_indices_from(K)] += alpha + np.exp(th[4])
            try:
                L = np.linalg.cholesky(K)
            except np.linalg.LinAlgError:
                return 1e10
            a = np.linalg.solve(L.T, np.linalg.solve(L, yz))
            return float(0.5 * yz @ a + np.log(np.diag(L)).sum())

        rng = np.random.default_rng(0)
        starts = [np.log([1.0, 2.0, 2.0, 1.0, 1e-2])] + [rng.uniform(lb, ub) for _ in range(4)]
        best = min((optimize.minimize(nlml, t, method="L-BFGS-B", bounds=list(zip(lb, ub)))
                    for t in starts), key=lambda r: r.fun)
        self.theta_ = best.x
        K = self._K(self.theta_, X)
        K[np.diag_indices_from(K)] += alpha + np.exp(self.theta_[4])
        self.L_ = np.linalg.cholesky(K)
        self.a_ = np.linalg.solve(self.L_.T, np.linalg.solve(self.L_, yz))
        self.X_ = X
        return self

    def surface(self, rate_hz, pw_left, pw_right, amps=AMP_GRID_MA):
        """{amps_mA, mu, sd, safe} on the current grid at one rate and one pulse-width pair; `safe`
        is all True -- only the maxima limit a borrowed surface."""
        amps = np.asarray(amps, float)
        gl, gr = np.meshgrid(amps, amps, indexing="ij")
        n = gl.size
        Xs = np.column_stack([np.full(n, np.log2(rate_hz)), gl.ravel(), gr.ravel(),
                              np.full(n, np.log2(pw_left)), np.full(n, np.log2(pw_right))])
        Ks = self._K(self.theta_, Xs, self.X_)
        mu = Ks @ self.a_
        v = np.linalg.solve(self.L_, Ks.T)
        var = np.maximum(np.exp(self.theta_[0]) - (v ** 2).sum(0), 1e-12)
        shape = (amps.size, amps.size)
        return {"amps_mA": list(amps), "mu": (mu * self._scale + self._loc).reshape(shape),
                "sd": (np.sqrt(var) * self._scale).reshape(shape),
                "safe": np.ones(shape, bool)}


def _f(v):
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if np.isfinite(x) else None


def _best_cell(surface, ceilings):
    """(optimistic, predicted, amp_left, amp_right) at the safe cell under both maxima with the
    largest -mu + K_SD * sd; None when no cell qualifies."""
    amps = np.asarray(surface.get("amps_mA") or [], float)
    mu = np.asarray(surface.get("mu"), float)
    sd = np.asarray(surface.get("sd"), float)
    safe = np.asarray(surface.get("safe"), bool)
    if amps.size == 0 or mu.shape != (amps.size, amps.size):
        return None
    cl, cr = _f((ceilings or {}).get("Left")), _f((ceilings or {}).get("Right"))
    ok = safe.copy()
    if cl is not None:
        ok &= (amps[:, None] <= cl + 1e-9)
    if cr is not None:
        ok &= (amps[None, :] <= cr + 1e-9)
    ok &= np.isfinite(mu) & np.isfinite(sd)
    # A Left contact is tested only where Left carries current: at 0 mA the contact makes no
    # difference (the PI's ruling of 2026-10-01), so a 0 mA cell would score the contact for a
    # setting that does not use it (found live: every L C+1- block's best cell was Left 0 mA).
    ok &= (amps[:, None] > 0.0)
    if not ok.any():
        return None
    score = np.where(ok, -mu + K_SD * sd, -np.inf)
    i, j = np.unravel_index(int(np.argmax(score)), score.shape)
    return float(score[i, j]), float(-mu[i, j]), float(amps[i]), float(amps[j])


def rank_blocks(rate_rows, *, in_force, contacts_used, rates, ceilings, prior_sd,
                min_rate_hz=PA.MIN_ADAPTIVE_RATE_HZ, contact_frames=None,
                borrow_min_stretches=BORROW_MIN_STRETCHES) -> dict:
    """Every candidate block, ranked; plus the top block's ladder. `rate_rows` are step A's
    per-rate clinic rows (`rate_strata_clinic`), each with its own Left contact and, when fitted,
    a `surface` (amps_mA, mu, sd, safe)."""
    from .. import titration_plan as TP

    f = dict(in_force or {})
    pwl = _f((f.get("Left") or {}).get("pulse_width_us"))
    pwr = _f((f.get("Right") or {}).get("pulse_width_us"))
    contacts = []
    for c in list(contacts_used or []) + [C12]:
        if c and c not in contacts:
            contacts.append(str(c))
    offered = sorted({float(r) for r in (rates or []) if _f(r) is not None})
    kept = [r for r in offered if r >= float(min_rate_hz) - 1e-9]
    left_out = [r for r in offered if r < float(min_rate_hz) - 1e-9]

    def _row_for(c, rate):
        for r in rate_rows or []:
            if (r.get("left_contact") == c and _f(r.get("rate_hz")) is not None
                    and abs(float(r["rate_hz"]) - rate) < 1e-6
                    and pwl is not None and pwr is not None
                    and abs(float(r.get("pw_us_left", -1)) - pwl) < 1e-6
                    and abs(float(r.get("pw_us_right", -1)) - pwr) < 1e-6):
                return r
        return None

    prior = float(K_SD * float(prior_sd))
    # One borrowed fit per contact with enough of its own clinic stretches (any rate, any pulse
    # widths); `n_own` counts the contact's stretches with current, not the shared 0 mA ones.
    borrowed = {}
    for c, fr in (contact_frames or {}).items():
        n_own = int((fr["amp_mA_Left"].astype(float) > 0).sum()) if len(fr) else 0
        if n_own >= int(borrow_min_stretches) and pwl is not None and pwr is not None:
            try:
                borrowed[c] = (BorrowedSurfaceGP().fit(fr), n_own)
            except (ValueError, np.linalg.LinAlgError):
                pass
    # PER RATE (the PI, 2026-10-02): the count a block shows is its own clinic stretches at its
    # rate with the Left current on, read from the contact's frame; the borrowed fit's total, which
    # the table used to print on every rate row (L C+1-: 31 at 85, 125 and 145 Hz alike), travels as
    # `n_stretches_borrowed_fit`. The ranking still sorts on the count it always used (`_n_sort`).
    def _per_rate(c, rate):
        fr = (contact_frames or {}).get(c)
        if fr is None or not len(fr) or "freq_hz" not in fr or "amp_mA_Left" not in fr:
            return None
        on = fr["amp_mA_Left"].astype(float).to_numpy() > 0
        at = np.abs(fr["freq_hz"].astype(float).to_numpy() - float(rate)) < 1e-6
        return int((on & at).sum())

    blocks = []
    for c in contacts:
        for rate in kept:
            r = _row_for(c, rate)
            n = int((r or {}).get("n_epochs") or 0)
            cell = _best_cell(r["surface"], ceilings) if (r and r.get("fitted") and r.get("surface")) else None
            if cell is not None:
                opt, pred, aL, aR = cell
                blocks.append(dict(left_contact=c, rate_hz=rate, n_stretches=n, basis=FITTED_BASIS,
                                   optimistic_improvement=opt, predicted_improvement=pred,
                                   amp_mA_left=aL, amp_mA_right=aR))
                continue
            bcell = (_best_cell(borrowed[c][0].surface(rate, pwl, pwr), ceilings)
                     if c in borrowed else None)
            if bcell is not None:
                opt, pred, aL, aR = bcell
                blocks.append(dict(left_contact=c, rate_hz=rate, n_stretches=borrowed[c][1],
                                   basis=BORROWED_BASIS, optimistic_improvement=opt,
                                   predicted_improvement=pred, amp_mA_left=aL, amp_mA_right=aR))
            else:
                blocks.append(dict(left_contact=c, rate_hz=rate, n_stretches=n, basis=PRIOR_BASIS,
                                   optimistic_improvement=prior, predicted_improvement=0.0,
                                   amp_mA_left=None, amp_mA_right=None))
    for b in blocks:
        b["_n_sort"] = b["n_stretches"]
        pr = _per_rate(b["left_contact"], b["rate_hz"])
        if b["basis"] == BORROWED_BASIS:
            b["n_stretches_borrowed_fit"] = b["n_stretches"]
        if pr is not None:
            b["n_stretches"] = pr
    blocks.sort(key=lambda b: (-round(b["optimistic_improvement"], 9), b["_n_sort"],
                               b["left_contact"], b["rate_hz"]))
    for b in blocks:
        b.pop("_n_sort", None)
    for k, b in enumerate(blocks, start=1):
        b["rank"] = k

    # A TIE AT THE TOP IS SAID, NEVER BROKEN SILENTLY (2026-10-01, found live on RCS08: 46 of 48
    # blocks shared the prior bound and the "top" one won on alphabetical order). The ordering
    # inside a tie is kept for display, but no single block is offered as the model's pick.
    top = blocks[0] if blocks else None
    n_tied = (sum(1 for b in blocks if abs(b["optimistic_improvement"] - top["optimistic_improvement"]) < 1e-9)
              if top is not None else 0)
    next_block, note = None, None
    if top is not None and n_tied == 1:
        next_block = dict(top, ladder=TP.ladder((ceilings or {}).get("Left")),
                          right_held_mA=_f((f.get("Right") or {}).get("amplitude_mA")))
    elif top is not None:
        # the tied blocks are the untested ones (no surface, so they all carry the prior bound);
        # the bound is what could still be plausible, never a measured gain (decision 386)
        note = (f"{n_tied} untested blocks tie at the top at the prior bound of "
                f"{top['optimistic_improvement']:.2f} NRS points (not a prediction); measured blocks "
                f"rank below; the model cannot rank the tied ones, so it offers no single next block")
    return {"available": bool(blocks), "blocks": blocks, "next_block": next_block,
            "n_tied_at_top": int(n_tied), "ranking_note": note,
            "pulse_widths_us": {"Left": pwl, "Right": pwr}, "rates_left_out": left_out,
            "min_rate_hz": float(min_rate_hz), "prior_sd": float(prior_sd), "k_sd": K_SD,
            "unit": "NRS points of improvement over the setting in force (higher is better)"}
