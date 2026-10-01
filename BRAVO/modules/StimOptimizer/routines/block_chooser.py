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

from . import percept_adaptive as PA

C12 = "L C+1-2-"
PRIOR_BASIS = "no surface: the stream's own spread"
FITTED_BASIS = "fitted surface"
K_SD = 2.0


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
    if not ok.any():
        return None
    score = np.where(ok, -mu + K_SD * sd, -np.inf)
    i, j = np.unravel_index(int(np.argmax(score)), score.shape)
    return float(score[i, j]), float(-mu[i, j]), float(amps[i]), float(amps[j])


def rank_blocks(rate_rows, *, in_force, contacts_used, rates, ceilings, prior_sd,
                min_rate_hz=PA.MIN_ADAPTIVE_RATE_HZ) -> dict:
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
            else:
                blocks.append(dict(left_contact=c, rate_hz=rate, n_stretches=n, basis=PRIOR_BASIS,
                                   optimistic_improvement=prior, predicted_improvement=0.0,
                                   amp_mA_left=None, amp_mA_right=None))
    blocks.sort(key=lambda b: (-round(b["optimistic_improvement"], 9), b["n_stretches"],
                               b["left_contact"], b["rate_hz"]))
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
        note = (f"{n_tied} blocks tie at the top with the same plausible improvement "
                f"({top['optimistic_improvement']:.2f} NRS points); the model cannot rank them, "
                f"so it offers no single next block")
    return {"available": bool(blocks), "blocks": blocks, "next_block": next_block,
            "n_tied_at_top": int(n_tied), "ranking_note": note,
            "pulse_widths_us": {"Left": pwl, "Right": pwr}, "rates_left_out": left_out,
            "min_rate_hz": float(min_rate_hz), "prior_sd": float(prior_sd), "k_sd": K_SD,
            "unit": "NRS points of improvement over the setting in force (higher is better)"}
