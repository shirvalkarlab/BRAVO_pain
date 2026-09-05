"""Amplitude-response evidence built from WITHIN-VISIT clinic steps, not chronic exposure epochs.

WHY THIS EXISTS ALONGSIDE ``lfp_evidence.build_all``. That builder reads exposure epochs whose
amplitude is entangled with calendar time, so era blocking is the only defence against the
confound. On RCS08 that defence fails in both directions and for opposite reasons:

  * the FULL-RECORD window fails on capture DIRECTION in all 18 bands, because the two capture arms
    straddle two programming regimes and power therefore RISES across them; and
  * the FIVE-ERA window fails on capture SEPARATION in 14 of 18, because restricting to recent eras
    removes the low amplitudes and the contrast collapses from 2.9 mA to 1.0.

Inside one clinic visit the rate, pulse width and contacts are fixed and the whole amplitude ladder
happens within hours, so there is no time confound to adjust for. The measured within-visit span on
RCS08 reaches 3.5 mA, and the resulting capture separation runs 0.53 to 0.89 per cell rather than
0.41 to 0.93 — which is why separation stops being the binding constraint.

The output is deliberately the SAME shape ``lfp_evidence.build_all`` returns, a
``{(channel, hemisphere, rate): LfpEvidence}`` mapping plus an audit frame, so ``screen_cells`` and
the whole gate downstream of it run unchanged. Only the evidence source is swapped.

DEPENDENCY NOTE. Nothing here imports Biomarkers. The harmonic-landing flag that accompanies the
per-band scores needs ``Biomarkers.routines.analytics.harmonic_landings_hz`` and therefore lives in
``ClosedLoopDeployment.clinic_steps``, which already depends on both. Keeping the flag out of this
file is what lets StimOptimizer stay free of that import.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import stage_gate as GATE
from .lfp_evidence import EvidenceAudit

#: Seconds after a step's onset that are discarded as ramp transient.
#:
#: The clinic sheets themselves warn that the amplitude ramps rather than stepping, and the ramp
#: analysis measured the stimulation-frequency artefact still RISING at 150 s -- far beyond the
#: 30-45 s the sheets suggest. 45 s is therefore the sheets' own figure and not a safe one; it is
#: used because a longer exclusion leaves almost no settled signal (the median step is 60 s), and
#: the residual risk is recorded rather than removed.
RAMP_EXCLUDE_S = 45.0

#: Amplitude bin width for forming capture arms, in mA.
#:
#: A JUDGEMENT. The programmer steps finely while a capture arm needs rows: one RCS08 visit carried
#: 29 distinct amplitude levels across 36 steps, so grouping on the raw level leaves roughly one
#: step per level and no arm reaches ``lfp_response.MIN_ROWS_PER_ARM``. 0.5 mA is the coarsest
#: grouping that still separates clinically distinct settings.
AMP_ARM_BIN_MA = 0.5

#: Minimum settled tiles a step must contribute before its median is used. Two is the arithmetic
#: minimum for a median to mean anything, and it is deliberately low because the median RCS08 step
#: yields only about five settled tiles. The thinness is reported per step, not hidden.
MIN_SETTLED_TILES = 2


def amplitude_arm_bins(amp_mA, bin_mA=AMP_ARM_BIN_MA):
    """Amplitudes rounded to the declared arm bin. See :data:`AMP_ARM_BIN_MA` for why."""
    a = np.asarray(amp_mA, dtype=float)
    if not np.isfinite(bin_mA) or bin_mA <= 0:
        raise ValueError(f"bin_mA must be positive and finite, got {bin_mA}")
    return np.round(a / float(bin_mA)) * float(bin_mA)


def step_settled_medians(step_t0, step_window_s, tile_t, tile_power, *,
                         ramp_s=RAMP_EXCLUDE_S, min_tiles=MIN_SETTLED_TILES):
    """One power vector per step: the median across that step's SETTLED tiles.

    THE UNIT IS THE STEP, NOT THE TILE. A device capture is a short recording summarised to one
    number, so the step median is its analogue, and a median rather than a mean because a capture
    window can contain a transient.

    WHAT THE CHOICE PROTECTS, measured rather than assumed. It does NOT protect the standardised
    separation: on a construction with a large between-step spread and a small within-step one,
    separation came out 2.54 at step level and 2.64 at tile level, a ratio of 1.04, with the slope
    identical to four decimals. A Cohen-style d divides by the pooled within-ARM spread, and an arm
    contains many different steps whichever unit is used, so between-step variation dominates the
    denominator either way. What tiles inflate is the INFERENCE: on that same construction the
    slope p-value went from 4.7e-54 to 1.7e-63 -- ten orders of magnitude -- on an n inflated
    twentyfold from 24 to 480 with the cluster count unchanged. Cluster-robust standard errors do
    not rescue it, because the clusters stay fixed while the rows inside each one multiply.

    ``tile_t`` must be sorted ascending. Returns ``(medians, n_tiles, kept)``.
    """
    t0 = np.asarray(step_t0, dtype=float)
    win = np.asarray(step_window_s, dtype=float)
    tt = np.asarray(tile_t, dtype=float)
    tp = np.asarray(tile_power, dtype=float)
    if t0.shape != win.shape:
        raise ValueError(f"step_t0 {t0.shape} and step_window_s {win.shape} must match")
    if tp.ndim != 2 or tp.shape[0] != tt.size:
        raise ValueError(f"tile_power must be (n_tiles, n_centres) aligned to tile_t "
                         f"({tt.size}); got {tp.shape}")
    if tt.size and np.any(np.diff(tt) < 0):
        raise ValueError("tile_t must be sorted ascending")

    meds, counts, kept = [], [], []
    for i, (a, w) in enumerate(zip(t0, win)):
        if not np.isfinite(a) or not np.isfinite(w) or w <= ramp_s:
            continue
        i0 = int(np.searchsorted(tt, a + ramp_s))
        i1 = int(np.searchsorted(tt, a + w))
        if i1 - i0 < int(min_tiles):
            continue
        meds.append(np.nanmedian(tp[i0:i1, :], axis=0))
        counts.append(i1 - i0)
        kept.append(i)
    if not meds:
        n_cen = tp.shape[1] if tp.ndim == 2 else 0
        return (np.empty((0, n_cen)), np.empty(0, dtype=int), np.empty(0, dtype=int))
    return np.vstack(meds), np.asarray(counts, dtype=int), np.asarray(kept, dtype=int)


def build_within_visit_evidence(steps, *, channel, hemisphere, rate_hz, centers_hz,
                                tile_t, tile_power, band_width_hz=5.0,
                                amp_col=None, visit_col="visit", ramp_s=RAMP_EXCLUDE_S,
                                bin_mA=AMP_ARM_BIN_MA, min_tiles=MIN_SETTLED_TILES,
                                mode_requires=None):
    """One :class:`stage_gate.LfpEvidence` from clinic steps, plus its audit.

    ``steps`` needs ``t0`` (epoch seconds), ``window_s``, a per-hemisphere amplitude column and a
    visit label. The VISIT supplies both the era and the cluster, which is the whole point of the
    design: amplitude varies WITHIN a visit, so blocking on visit removes calendar time without
    absorbing the amplitude contrast. On the chronic epochs the opposite held -- each old era
    carried a single amplitude, so its dummy absorbed the era entirely and contributed nothing.
    """
    aud = EvidenceAudit(channel=str(channel), hemisphere=str(hemisphere), rate_hz=float(rate_hz))
    S = pd.DataFrame(steps)
    aud.n_psd_rows = int(np.asarray(tile_t).size)
    if amp_col is None:
        amp_col = f"amp_mA_{hemisphere}"
    for need in ("t0", "window_s", visit_col, amp_col):
        if need not in S.columns:
            aud.reason_unusable = f"steps frame has no {need!r} column"
            return None, aud
    aud.amp_col, aud.era_col = amp_col, visit_col
    aud.era_source = f"clinic visit ({visit_col!r}); amplitude varies WITHIN each visit"

    rate_num = pd.to_numeric(S.get("rate_hz"), errors="coerce")
    n0 = len(S)
    S = S[np.isclose(rate_num, float(rate_hz))] if rate_num is not None else S
    aud.n_dropped_other_rate = n0 - len(S)
    n0 = len(S)
    S = S[pd.to_numeric(S[amp_col], errors="coerce") > 0]
    aud.n_dropped_stim_off = n0 - len(S)
    S = S.dropna(subset=["t0", "window_s", amp_col])
    if not len(S):
        aud.reason_unusable = (f"no step at {rate_hz:g} Hz with stimulation on and a usable "
                               f"{amp_col}")
        return None, aud

    med, cnt, kept = step_settled_medians(S["t0"].to_numpy(float),
                                          S["window_s"].to_numpy(float),
                                          tile_t, tile_power,
                                          ramp_s=ramp_s, min_tiles=min_tiles)
    aud.n_joined = int(len(kept))
    aud.n_dropped_no_epoch = int(len(S) - len(kept))
    aud.n_final = int(len(kept))
    if not len(kept):
        aud.reason_unusable = (f"no step had at least {min_tiles} tiles in its settled window "
                               f"(ramp exclusion {ramp_s:g} s)")
        return None, aud

    K = S.iloc[kept]
    amp = amplitude_arm_bins(pd.to_numeric(K[amp_col], errors="coerce").to_numpy(float), bin_mA)
    era = K[visit_col].astype(str).to_numpy()
    aud.amplitudes = tuple(sorted(np.unique(np.round(amp, 2)).tolist()))
    aud.n_eras = int(pd.Series(era).nunique())
    if len(aud.amplitudes) < 2:
        aud.reason_unusable = (f"only one binned amplitude ({aud.amplitudes}) — a capture needs "
                               f"two therapeutic amplitudes to contrast")
        return None, aud

    cen = np.asarray(centers_hz, dtype=float)
    if med.shape[1] != cen.size:
        raise ValueError(f"centers_hz has {cen.size} entries but the tile power has "
                         f"{med.shape[1]} columns")
    bp = {(round(float(c), 6), round(float(band_width_hz), 6)): med[:, j]
          for j, c in enumerate(cen)}
    kw = {} if mode_requires is None else {"mode_requires": mode_requires}
    ev = GATE.LfpEvidence(amplitude_mA=amp, band_power=bp, era=era, cluster=era,
                          hemisphere=str(hemisphere), **kw)
    return ev, aud


def build_all_within_visit(steps, *, centers_hz, tiles_by_channel,
                           hemispheres=("Left", "Right"), rates=None, channels=None, **kw):
    """Within-visit evidence for every (channel, hemisphere, rate) cell.

    ``tiles_by_channel`` maps a channel name to ``(tile_t, tile_power)``. Returns
    ``(dict, audit_frame)`` in the same shape as :func:`lfp_evidence.build_all`, so
    ``lfp_evidence.screen_cells`` consumes it without modification -- the majority-of-bands rule,
    the era-significance condition and the amplitude ceiling all apply identically.
    """
    S = pd.DataFrame(steps)
    chans = list(channels) if channels is not None else sorted(tiles_by_channel)
    if rates is None:
        rates = sorted(pd.to_numeric(S.get("rate_hz"), errors="coerce").dropna().unique().tolist())
    out, rows = {}, []
    for ch in chans:
        tt, tp = tiles_by_channel.get(ch, (np.empty(0), np.empty((0, len(centers_hz)))))
        for h in hemispheres:
            for r in rates:
                ev, aud = build_within_visit_evidence(
                    S, channel=ch, hemisphere=h, rate_hz=r, centers_hz=centers_hz,
                    tile_t=tt, tile_power=tp, **kw)
                rows.append({**aud.__dict__, "usable": ev is not None})
                if ev is not None:
                    out[(ch, h, float(r))] = ev
    return out, pd.DataFrame(rows)
