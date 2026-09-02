"""Build a real :class:`~StimOptimizer.routines.stage_gate.LfpEvidence` from platform data.

WHAT THIS EXISTS FOR
--------------------
Stage 2 cannot propose a closed-loop policy without knowing whether the sensed band actually
responds to stimulation amplitude — that is the device's own requirement, because Adaptive Therapy's
only lever IS amplitude. ``stage_gate.LfpEvidence`` is the interface that carries that measurement,
and until this module existed it was constructed ONLY in tests. Every Stage 2 figure therefore came
from fabricated spectra. This module is the missing join:

    Biomarkers assembled PSD matrix   (what the brain was doing, and when)
                  x
    StimOptimizer exposure epochs     (what stimulation was being delivered, and when)

Neither module owns both halves, which is why the join lives here in StimOptimizer rather than in
Biomarkers: the epoch reconstruction, the wash-in convention and the era blocking are all
StimOptimizer's definitions, and duplicating them on the Biomarkers side would create a second
answer to "what setting was in force at this moment".

FIVE TRAPS, EVERY ONE OF WHICH HAS ALREADY BITTEN THIS PROJECT ONCE
-------------------------------------------------------------------
1. **Timestamp units.** The assembled matrix stores epoch SECONDS. Read as nanoseconds (the pandas
   default for large integers) every window lands in 1970 and the join returns zero rows while
   raising nothing at all. :func:`_to_utc` pins the unit and asserts the result is plausible.

2. **The stored values are LOG POWER DENSITY, not magnitude.** ``LfpEvidence`` accepts a
   ``magnitude`` matrix and reduces it with the DEVICE's band-power definition (a linear sum of
   squared magnitude, manual p. 39). Handing it log power would be wrong twice over — once for the
   log, once for power-versus-magnitude — and would still produce plausible-looking numbers. This
   module therefore exponentiates to linear power density and populates ``band_power`` directly,
   integrating over the band itself, and never fills ``magnitude``.

3. **Zero-amplitude rows are not the bottom of a dose axis.** With stimulation off there is no
   stimulation artifact at all, so a 0-versus-4.8 mA contrast is artifact-versus-no-artifact and
   says nothing about response within the therapeutic range. Dropped by default; see
   ``require_stim_on``.

4. **Artifact magnitude depends on RATE.** Pooling rates makes a rate contrast masquerade as an
   amplitude contrast. This module refuses to build evidence spanning multiple rates unless asked,
   because the honest unit is one rate at a time.

5. **Amplitude is confounded with time on this record**, since amplitude rose over the programme.
   ``era`` must block it, and is populated from the epoch's own visit index rather than invented.

WHAT THIS MODULE DELIBERATELY DOES NOT DO
-----------------------------------------
It does not decide whether the band responds — :func:`lfp_response.assess_response` does, and
Stage 2 calls it. It does not select a band. It does not average over channels: a channel is a
distinct sensing configuration and pooling them would mix electrodes. One evidence object per
(channel, hemisphere, rate).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import lfp_response as LFP
from . import stage_gate as GATE

#: Assembled-matrix timestamps are epoch seconds. Anything outside this window means the unit was
#: misread rather than that the study ran for decades.
_PLAUSIBLE_UTC = (pd.Timestamp("2015-01-01", tz="UTC"), pd.Timestamp("2035-01-01", tz="UTC"))


def _to_utc(values, *, unit="s"):
    """Epoch values -> tz-aware UTC, with the unit pinned and the result sanity-checked."""
    t = pd.to_datetime(pd.to_numeric(pd.Series(values), errors="coerce"), unit=unit, utc=True)
    good = t.dropna()
    if len(good):
        lo, hi = good.min(), good.max()
        if lo < _PLAUSIBLE_UTC[0] or hi > _PLAUSIBLE_UTC[1]:
            raise ValueError(
                f"PSD timestamps land at {lo} .. {hi}, outside {_PLAUSIBLE_UTC[0].date()} .. "
                f"{_PLAUSIBLE_UTC[1].date()}. The assembled matrix stores epoch SECONDS; this is "
                "the symptom of reading them as another unit, which silently empties the join.")
    return t


#: How a stored log spectrum maps back to linear power. The BRAVO platform's assembled matrix holds
#: ``logX = 10 * log10(power)`` — DECIBELS — set in ``streaming_psd.psd_rows_to_matrix``. Undoing it
#: with ``10 ** logX`` instead of ``10 ** (logX / 10)`` is wrong by a factor of ten IN THE EXPONENT,
#: which for a spectrum around -1 dB inflates band power by orders of magnitude while still
#: returning finite, plausible-looking numbers. The convention is therefore named explicitly at every
#: call site rather than assumed.
LOG_SCALES = {"db10": 10.0, "log10": 1.0}
DEFAULT_LOG_SCALE = "db10"


def band_power_linear(log_psd, freqs, center_hz, width_hz, *, log_scale=DEFAULT_LOG_SCALE):
    """Device-style band power from a LOG power spectrum: linearise, then integrate over the band.

    The device thresholds a linear sum of squared magnitude over the band, and power is proportional
    to squared magnitude, so integrating linear power density gives the device's quantity up to a
    fixed scale factor. The log must be undone BEFORE summing — summing logs is a product of powers,
    not a sum.

    ``log_scale`` names the stored convention: ``"db10"`` for ``10*log10(power)`` (what the BRAVO
    assembled matrix stores) or ``"log10"`` for a plain base-10 log. Getting this wrong does not
    raise; it silently rescales every band power, so it is a required piece of provenance rather
    than a detail.

    Returns one value per row, or ``None`` when the band lies outside the frequency axis, rather
    than integrating over whichever bins happen to be nearest.
    """
    if log_scale not in LOG_SCALES:
        raise ValueError(f"log_scale must be one of {sorted(LOG_SCALES)}, got {log_scale!r}")
    f = np.asarray(freqs, float)
    lo, hi = float(center_hz) - float(width_hz) / 2.0, float(center_hz) + float(width_hz) / 2.0
    sel = (f >= lo) & (f <= hi)
    if not sel.any():
        return None
    lin = np.power(10.0, np.asarray(log_psd, float)[:, sel] / LOG_SCALES[log_scale])
    df = float(np.median(np.diff(f))) if f.size > 1 else 1.0
    return np.nansum(lin, axis=1) * df


def frame_from_matrix(mat, *, sources=None):
    """The BRAVO assembled PSD matrix -> the row frame :func:`build_evidence` consumes.

    ``mat`` is what ``Biomarkers.bravo_service._cached_psd_matrix`` returns:
    ``{"logX": (N,F), "t": (N,), "channel": (N,), "source": (N,), "f_set": (F,)}``. Note ``f_set`` is
    ONE shared frequency axis for every row, not a per-row array, so it is attached to each row here
    rather than being re-derived.

    ``sources`` optionally restricts which recording sources contribute (e.g. streaming time-domain
    only, excluding montage sweeps). Left as ``None`` every source is kept, which is right for a
    response test — the question is whether the band moves with amplitude, and a montage sweep
    observes that as validly as a streaming segment.
    """
    need = {"logX", "t", "channel", "f_set"}
    missing = need - set(mat or {})
    if missing:
        raise KeyError(f"assembled matrix missing {sorted(missing)}; has {sorted((mat or {}))}")
    logX = np.asarray(mat["logX"], float)
    f_set = np.asarray(mat["f_set"], float)
    if logX.shape[1] != f_set.size:
        raise ValueError(f"logX has {logX.shape[1]} frequency columns but f_set has {f_set.size}")
    src = np.asarray(mat.get("source", np.full(logX.shape[0], "?")), dtype=object)
    keep = np.ones(logX.shape[0], bool) if sources is None else np.isin(src, list(sources))
    return pd.DataFrame({"t": np.asarray(mat["t"], float)[keep],
                         "channel": np.asarray(mat["channel"], dtype=object)[keep],
                         "source": src[keep],
                         "log_psd": list(logX[keep]),
                         "freqs": [f_set] * int(keep.sum())})


@dataclass
class EvidenceAudit:
    """Why rows were kept or dropped. Coverage that cannot be inspected cannot be trusted."""

    channel: str
    hemisphere: str
    rate_hz: float
    n_psd_rows: int = 0
    n_joined: int = 0
    n_dropped_no_epoch: int = 0
    n_dropped_stim_off: int = 0
    n_dropped_other_rate: int = 0
    n_final: int = 0
    amplitudes: tuple = ()
    n_eras: int = 0
    reason_unusable: str | None = None

    def describe(self) -> str:
        if self.reason_unusable:
            return (f"{self.channel} {self.hemisphere} @{self.rate_hz:g} Hz: UNUSABLE — "
                    f"{self.reason_unusable}")
        return (f"{self.channel} {self.hemisphere} @{self.rate_hz:g} Hz: {self.n_final} windows "
                f"over {len(self.amplitudes)} amplitudes {self.amplitudes}, {self.n_eras} eras "
                f"(joined {self.n_joined} of {self.n_psd_rows}; dropped "
                f"{self.n_dropped_no_epoch} unmatched, {self.n_dropped_stim_off} stim-off, "
                f"{self.n_dropped_other_rate} other-rate)")


def _epoch_for_times(times, epochs, *, t_start="t_start", t_end="t_end"):
    """Index of the exposure epoch containing each timestamp, or -1. Half-open [start, end)."""
    ep = epochs.reset_index(drop=True)
    starts = pd.to_datetime(ep[t_start], utc=True).to_numpy()
    ends = pd.to_datetime(ep[t_end], utc=True).to_numpy()
    tv = pd.to_datetime(pd.Series(times), utc=True).to_numpy()
    idx = np.searchsorted(starts, tv, side="right") - 1
    ok = (idx >= 0) & (idx < len(ep))
    within = np.zeros(len(tv), bool)
    within[ok] = tv[ok] < ends[np.clip(idx[ok], 0, len(ep) - 1)]
    return np.where(within, idx, -1)


def build_evidence(psd, epochs, *, channel, hemisphere, rate_hz, bands=None,
                   require_stim_on=True, amp_col=None, era_col="visit",
                   time_unit="s", mode_requires=None, log_scale=DEFAULT_LOG_SCALE):
    """One :class:`LfpEvidence` for a single (channel, hemisphere, rate), plus its audit.

    Parameters
    ----------
    psd
        Frame with ``t`` (epoch seconds), ``channel``, and either a ``log_psd`` matrix column or
        columns named by ``freqs``. Simplest accepted form: ``{"t", "channel", "log_psd", "freqs"}``
        where ``log_psd`` is a 2-D array aligned to ``psd`` rows and ``freqs`` its frequency axis.
    epochs
        StimOptimizer exposure epochs: ``t_start``, ``t_end``, per-hemisphere amplitude and ``rate``.
    bands
        Iterable of ``(center_hz, width_hz)``. Defaults to the adaptive-capable grid, because a band
        outside 8-30 Hz cannot drive therapy however well it predicts pain.

    Returns ``(evidence, audit)``. ``evidence`` is ``None`` when the data cannot support the test —
    fewer than two distinct amplitudes, or only one era — and the audit says which, because a gate
    that silently returns "does not respond" for missing data is indistinguishable from one
    reporting a real negative.
    """
    aud = EvidenceAudit(channel=str(channel), hemisphere=str(hemisphere), rate_hz=float(rate_hz))
    if hemisphere not in ("Left", "Right"):
        raise ValueError(f"hemisphere must be 'Left' or 'Right', got {hemisphere!r}")
    amp_col = amp_col or f"amp_{hemisphere}"
    if amp_col not in epochs.columns:
        raise KeyError(f"epochs missing {amp_col!r}; has {sorted(epochs.columns)}")

    p = pd.DataFrame(psd)
    p = p[p["channel"].astype(str) == str(channel)].copy()
    aud.n_psd_rows = len(p)
    if not len(p):
        aud.reason_unusable = f"no PSD rows for channel {channel!r}"
        return None, aud
    p["t_utc"] = _to_utc(p["t"], unit=time_unit)

    ep = pd.DataFrame(epochs).reset_index(drop=True)
    j = _epoch_for_times(p["t_utc"], ep)
    aud.n_dropped_no_epoch = int((j < 0).sum())
    p = p.assign(_ep=j)
    p = p[p._ep >= 0]
    aud.n_joined = len(p)
    if not len(p):
        aud.reason_unusable = "no PSD window falls inside any exposure epoch"
        return None, aud

    meta = ep.loc[p._ep.to_numpy()]
    p = p.assign(amp=pd.to_numeric(meta[amp_col], errors="coerce").to_numpy(),
                 rate=pd.to_numeric(meta["rate"], errors="coerce").to_numpy(),
                 era=(meta[era_col].to_numpy() if era_col in ep.columns else p._ep.to_numpy()))

    n_before = len(p)
    p = p[np.isclose(p["rate"], float(rate_hz))]
    aud.n_dropped_other_rate = n_before - len(p)
    if require_stim_on:
        n_before = len(p)
        p = p[p["amp"] > 0]
        aud.n_dropped_stim_off = n_before - len(p)
    p = p.dropna(subset=["amp"])
    aud.n_final = len(p)
    if not len(p):
        aud.reason_unusable = f"nothing left after restricting to {rate_hz:g} Hz with stimulation on"
        return None, aud

    aud.amplitudes = tuple(sorted(np.unique(np.round(p["amp"].to_numpy(float), 2)).tolist()))
    aud.n_eras = int(pd.Series(p["era"]).nunique())
    if len(aud.amplitudes) < 2:
        aud.reason_unusable = (f"only one amplitude ({aud.amplitudes}) at this rate — a capture "
                               "needs two therapeutic amplitudes to contrast")
        return None, aud

    freqs = np.asarray(p["freqs"].iloc[0] if "freqs" in p.columns else p.attrs.get("freqs"), float)
    logm = np.vstack(p["log_psd"].to_numpy()) if p["log_psd"].dtype == object \
        else np.asarray(p["log_psd"].tolist(), float)

    if bands is None:
        lo, hi = GATE.ADAPTIVE_BAND_HZ if hasattr(GATE, "ADAPTIVE_BAND_HZ") else (8.0, 30.0)
        centers = np.arange(np.ceil(lo + 2.5), np.floor(hi - 2.5) + 1e-9, 1.0)
        bands = [(float(c), 5.0) for c in centers]

    bp = {}
    for c, w in bands:
        v = band_power_linear(logm, freqs, c, w, log_scale=log_scale)
        if v is not None:
            bp[(round(float(c), 6), round(float(w), 6))] = v
    if not bp:
        aud.reason_unusable = "no requested band lies inside the PSD frequency axis"
        return None, aud

    kw = {} if mode_requires is None else {"mode_requires": mode_requires}
    ev = GATE.LfpEvidence(amplitude_mA=p["amp"].to_numpy(float), band_power=bp,
                          era=np.asarray(p["era"]), cluster=np.asarray(p["era"]),
                          hemisphere=str(hemisphere), **kw)
    return ev, aud


def build_all(psd, epochs, *, hemispheres=("Left", "Right"), rates=None, channels=None, **kw):
    """Evidence for every (channel, hemisphere, rate) cell. Returns ``(dict, audit_frame)``.

    The cell is the unit because pooling channels mixes sensing configurations and pooling rates
    lets a rate effect masquerade as an amplitude effect. Unusable cells appear in the audit with
    their reason rather than being dropped.
    """
    p = pd.DataFrame(psd)
    ep = pd.DataFrame(epochs)
    chans = list(channels) if channels is not None else sorted(p["channel"].astype(str).unique())
    rs = list(rates) if rates is not None else sorted(
        pd.to_numeric(ep["rate"], errors="coerce").dropna().unique().tolist())
    out, rows = {}, []
    for ch in chans:
        for h in hemispheres:
            for r in rs:
                ev, aud = build_evidence(p, ep, channel=ch, hemisphere=h, rate_hz=r, **kw)
                rows.append({**aud.__dict__, "usable": ev is not None,
                             "n_amplitudes": len(aud.amplitudes)})
                if ev is not None:
                    out[(ch, h, float(r))] = ev
    return out, pd.DataFrame(rows)
