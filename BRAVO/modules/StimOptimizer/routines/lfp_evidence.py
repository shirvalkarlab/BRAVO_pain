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
    # Which columns were actually read, and where the era labels came from. Recorded because this
    # module accepts more than one epoch-frame naming convention and derives eras when none are
    # supplied, so "which frame was this" is not answerable from the numbers alone.
    amp_col: str | None = None
    rate_col: str | None = None
    era_source: str | None = None
    # The recent-era restriction, when one was applied. Recorded because a slope fitted on five
    # eras and one fitted on forty are not the same estimate, and nothing else in the payload
    # distinguishes them.
    n_dropped_old_eras: int = 0
    recent_eras_requested: int | None = None
    recent_eras_kept: tuple = ()
    era_order_source: str | None = None
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


#: Column-name candidates, most-canonical first. The production caller is
#: ``adapter.exposure_epochs``, which emits ``freq_hz`` / ``amp_mA_Left`` / ``pw_us_Left``; earlier
#: hand-built frames in this project used ``rate`` / ``amp_Left``. Both are accepted because the
#: first draft of this module hardcoded the SECOND set — it was written against a synthetic fixture
#: with invented names, so every test passed while the real adapter output raised KeyError on the
#: first live run. Resolving against a candidate list, with the production names first, is the fix.
RATE_COLS = ("freq_hz", "rate", "rate_hz")
AMP_COL_TEMPLATES = ("amp_mA_{h}", "amp_{h}", "amp_mA{h}")


def _resolve_col(frame, candidates, what):
    for c in candidates:
        if c in frame.columns:
            return c
    raise KeyError(f"epochs has no {what} column; tried {list(candidates)}, "
                   f"frame has {sorted(frame.columns)}")


#: HOW MANY OF THE MOST RECENT ERAS THE RESPONSE TEST MAY USE, or None for all of them.
#:
#: PI direction, 2026-09-05: restrict the era calculations to the four or five most recent eras.
#: The motivation is the same one that drives the burn-in exclusion on the biomarker side — the
#: early record describes a different physiological and programming state, and blocking on eras
#: that span the whole implant history asks the model to hold constant something that changed in
#: kind rather than in degree.
#:
#: THE CONFLICT THIS CREATES, which is why the value is not simply set to 5 here. In this module the
#: era variable is used TWICE: as the blocking factor (``C(era)`` in the slope model) and as the
#: CLUSTER for the robust standard errors — ``LfpEvidence(era=..., cluster=...)`` is passed the same
#: array. Restricting to five eras therefore leaves five clusters against a model carrying four era
#: dummies plus an intercept plus amplitude, which is six parameters. A cluster-robust sandwich with
#: fewer clusters than parameters is rank-deficient, and this project has already established what
#: that looks like: zero-width confidence intervals reported at p values near 1e-14. So the
#: restriction cannot be applied without either dropping the blocking, changing the cluster unit, or
#: switching to small-sample inference — and which of those is right is an empirical question, not a
#: default, so it was measured before being set.
#:
#: MEASURED, 2026-09-05, on RCS08 at 55 Hz. Three findings decided the value.
#:
#: 1. The era-blocked SLOPE does not move at all. It is -0.1222 log per mA on ONE_THREE_LEFT/Left at
#:    10.5 Hz with all 8 eras, with 5, and with 4 — identical to four decimals while n falls from
#:    361 to 331 to 328. That is not a coincidence and not a bug: the dropped eras each carried a
#:    SINGLE amplitude level, so their era dummy absorbs them entirely and they contribute nothing
#:    to a within-era amplitude slope. The restriction the PI asked for was therefore already
#:    implicit in the estimator for the slope.
#: 2. What it does change is the CAPTURE CONTRAST, and materially. Dropping the older eras removes
#:    the low amplitude levels from the record, so the low capture arm moves from 1.6 mA to 3.5 mA
#:    and the contrast is measured over 1.0 mA instead of 2.9 mA. On that cell ``direction_ok``
#:    flips from False to True in 15 of 18 bands: with the full record power RISES from 3.222 to
#:    4.894 across the arms, and on the recent eras it FALLS from 5.020 to 4.894. The full-record
#:    capture was inverted because it spanned two programming regimes.
#: 3. The predicted rank deficiency did NOT materialise — interval widths stay at 0.23 to 0.26 with
#:    4 and 5 clusters — but the cluster count lands in the anti-conservative regime. A wild cluster
#:    bootstrap resolves no finer than 1/2**G, which is 0.031 at five clusters and 0.062 at four, so
#:    at FOUR eras the reported p of 0.0564 sits BELOW its own resolution floor and cannot be
#:    resolved at all. Five is therefore the smallest defensible window of the two the PI named.
#:
#: The verdict is unchanged at 5 and at 4: 2 of 50 cells deployable, 0 of 12 at 55 Hz, and the same
#: cell selected. So this is a change of reasoning rather than of outcome, which is the honest thing
#: to record — the binding constraint on that cell moved from capture DIRECTION to capture
#: SEPARATION, which now sits at 0.41 to 0.52 against a 0.5 floor because the amplitude range
#: collapsed. Bands with a significant slope fail separation and bands clearing separation have p
#: between 0.07 and 0.35, an anti-correlation forced by the 1 mA contrast.
RECENT_ERAS_FOR_RESPONSE = 5


def _derive_era(ep, era_col, aud):
    """Era labels for temporal blocking, and an honest record of where they came from.

    Amplitude is confounded with time in this record, so the response test blocks on era. If the
    frame carries an era/visit column it is used. Otherwise eras are derived as CALENDAR MONTHS of
    ``t_start`` — not per-epoch indices. That distinction is the whole point: giving every epoch its
    own era leaves the blocked model with one observation per stratum, which removes all blocking
    power while still reporting a large era count, so the degradation would be invisible. The
    resolved source is written into the audit.
    """
    if era_col and era_col in ep.columns:
        aud.era_source = f"column {era_col!r}"
        return ep[era_col].to_numpy()
    if "t_start" in ep.columns:
        aud.era_source = "calendar month of t_start (no era column present)"
        return pd.to_datetime(ep["t_start"], utc=True).dt.strftime("%Y-%m").to_numpy()
    aud.era_source = "UNAVAILABLE — no era column and no t_start; blocking is impossible"
    return np.zeros(len(ep), dtype=int)


def build_evidence(psd, epochs, *, channel, hemisphere, rate_hz, bands=None,
                   require_stim_on=True, amp_col=None, era_col="visit", rate_col=None,
                   time_unit="s", mode_requires=None, log_scale=DEFAULT_LOG_SCALE,
                   recent_eras=RECENT_ERAS_FOR_RESPONSE):
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
    if amp_col is None:
        amp_col = _resolve_col(epochs, [t.format(h=hemisphere) for t in AMP_COL_TEMPLATES],
                               f"{hemisphere}-hemisphere amplitude")
    elif amp_col not in epochs.columns:
        raise KeyError(f"epochs missing {amp_col!r}; has {sorted(epochs.columns)}")
    rate_col = rate_col or _resolve_col(epochs, RATE_COLS, "stimulation rate")
    aud.amp_col = amp_col
    aud.rate_col = rate_col

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
                 rate=pd.to_numeric(meta[rate_col], errors="coerce").to_numpy(),
                 era=_derive_era(meta, era_col, aud))

    n_before = len(p)
    p = p[np.isclose(p["rate"], float(rate_hz))]
    aud.n_dropped_other_rate = n_before - len(p)
    if require_stim_on:
        n_before = len(p)
        p = p[p["amp"] > 0]
        aud.n_dropped_stim_off = n_before - len(p)
    p = p.dropna(subset=["amp"])

    # RESTRICT TO THE MOST RECENT ERAS, if asked. Applied here rather than earlier so that "most
    # recent" is measured over the rows that survive the rate and stimulation-on filters — an era
    # that contributes nothing at this rate is not one of this cell's recent eras, and counting it
    # would silently shorten the window.
    #
    # Ordered by each era's LATEST timestamp, not by its label. Calendar-month labels happen to sort
    # chronologically but a visit column need not, and ordering by label would quietly select the
    # alphabetically-last eras on any record whose visit identifiers are not date-like.
    if recent_eras is not None and int(recent_eras) > 0 and len(p):
        if "t" in p.columns:
            order = p.groupby("era")["t"].max().sort_values()
            aud.era_order_source = "each era's latest timestamp"
        else:
            order = pd.Series(sorted(pd.Series(p["era"]).unique()),
                              index=sorted(pd.Series(p["era"]).unique()))
            aud.era_order_source = ("era LABEL order — no time column present, so this is only "
                                    "chronological if the labels are date-like")
        keep = list(order.index[-int(recent_eras):])
        n_before = len(p)
        p = p[p["era"].isin(keep)]
        aud.n_dropped_old_eras = n_before - len(p)
        aud.recent_eras_kept = tuple(str(k) for k in keep)
        aud.recent_eras_requested = int(recent_eras)

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


#: A cell must respond on at least this fraction of scanned bands. One band of eighteen is what a
#: null looks like when eighteen OVERLAPPING bands are tested; a majority is the weakest claim that
#: is not simply the maximum of a correlated family.
MIN_RESPONDING_BAND_FRACTION = 0.5


def _sensing_side(channel) -> str:
    """Which hemisphere a sensing channel sits on, read from its name.

    Percept channel labels end in _LEFT or _RIGHT (e.g. ZERO_TWO_LEFT). This matters because a
    cell pairs a SENSING channel with a STIMULATING hemisphere and the two need not match: the
    A610 manual states that in Dual Threshold Mode stimulation is driven by sensing from the SAME
    hemisphere unless a contralateral sensing configuration has been explicitly set up. A
    contralateral cell is therefore not unusable, but it requires a configuration step that an
    ipsilateral cell does not, so it must never be selected silently.
    """
    c = str(channel).upper()
    if c.endswith("_LEFT"):
        return "Left"
    if c.endswith("_RIGHT"):
        return "Right"
    return "unknown"


def _laterality(channel, hemisphere) -> str:
    """``ipsilateral`` / ``contralateral`` / ``unknown``.

    An unparseable channel name returns "unknown" rather than defaulting to either value. Calling
    it contralateral would assert a fact about the electrode geometry that the name does not
    support, and calling it ipsilateral would let an unverified pairing be selected as though the
    configuration question had been settled.
    """
    side = _sensing_side(channel)
    if side == "unknown":
        return "unknown"
    return "ipsilateral" if side == str(hemisphere) else "contralateral"


def screen_cells(evidence, *, response_fn,
                 min_responding_fraction=MIN_RESPONDING_BAND_FRACTION,
                 require_era_significance=True, amp_ceiling=None):
    """Which cells carry evidence that could actually license a closed-loop deployment.

    Responding is necessary and not sufficient. Two further conditions apply:

    1. **A majority of scanned bands must respond**, because the bands overlap and move together,
       so the best band of eighteen is the maximum of a correlated family rather than a finding.
    2. **The slope must survive era blocking.** Amplitude rose over time in this record, so an
       unblocked slope can be time rather than dose.

    ``amp_ceiling`` optionally refuses a cell whose contrast reaches above the declared hard limit
    (:data:`objective.AMP_HARD_LIMIT_MA`). Left as ``None`` no amplitude condition is applied.

    RETRACTION, 2026-09-02: a third condition used to refuse any cell whose high amplitude arm
    exceeded an ENERGY-MATCHED ceiling scaling as sqrt(55/f). The PI has rejected the premise that
    tolerable amplitude at a frequency is governed by delivered energy, so ``energy_budget`` and
    ``pw_lookup`` are gone and passing them raises TypeError. This materially loosens the screen:
    five of the ten responding cells on RCS08 were refused on energy alone or in part, and under a
    flat 5 mA limit none of them breaches, so cells previously excluded now qualify. The argument
    that a response measured outside the programmable envelope is not deployable evidence still
    holds in principle — it is simply that the envelope is a flat amplitude limit, not an energy
    budget, so almost nothing on this record falls outside it.

    ``response_fn(power, amplitude, era=, cluster=)`` is injected rather than imported, so this
    module does not depend on the response implementation and a caller can screen against an
    alternative test.

    Returns ``(screen_frame, selected_key)``. Cells are ranked by responding fraction then median
    separation, but ONLY among survivors — a cell that fails a condition is never selected on the
    strength of a large separation.
    """
    rows = []
    for (ch, hemi, rate), ev in (evidence or {}).items():
        band_keys = list(ev.band_power.keys())
        res = [response_fn(ev.power_for(c, w), ev.amplitude_mA, era=ev.era, cluster=ev.cluster)
               for (c, w) in band_keys]
        n = len(res) or 1
        n_resp = sum(1 for r in res if r.responds is True)
        # SIGNIFICANT *AND* POINTING THE RIGHT WAY. This counted significance alone until
        # 2026-09-02, which inverted the purpose of the era-blocking condition instead of serving
        # it. `direction_ok` compares the raw arm means and is therefore confoundable with time;
        # the era-blocked slope is the confound-ADJUSTED quantity. Requiring only that the adjusted
        # slope be significant admitted cells whose arm means fall while the adjusted relationship
        # RISES — i.e. exactly the cells where the apparent response is a time artifact. On RCS08
        # the cell the screen SELECTED as best (ZERO_TWO_LEFT/Left/55 Hz) had all 18 bands with a
        # significantly POSITIVE era-blocked slope, median +0.4387 log units per mA.
        #
        # Adaptive Therapy needs band power to FALL as amplitude rises, so the adjusted slope must
        # be negative. Both counts are reported: n_era_significant for continuity, and
        # n_era_negative_significant, which is the one the gate uses.
        n_sig = sum(1 for r in res if np.isfinite(r.slope_p) and r.slope_p < 0.05)
        n_sig_neg = sum(1 for r in res if np.isfinite(r.slope_p) and r.slope_p < 0.05
                        and np.isfinite(r.slope_log_per_mA) and r.slope_log_per_mA < 0)
        seps = [r.separation_d for r in res if np.isfinite(r.separation_d)]
        amps = tuple(sorted(set(np.round(np.asarray(ev.amplitude_mA, float), 3))))
        amp_hi = max(amps) if amps else float("nan")

        cap = float(amp_ceiling) if amp_ceiling is not None else float("inf")
        within_limit = bool(np.isfinite(amp_hi) and amp_hi <= cap + 1e-9)

        fails = []
        if n_resp / n < min_responding_fraction:
            fails.append(f"only {n_resp} of {n} bands respond (need "
                         f"{min_responding_fraction:.0%}; overlapping bands make the single best "
                         f"band the maximum of a correlated family)")
        if not within_limit:
            fails.append(f"high arm {amp_hi:.1f} mA exceeds the {cap:.1f} mA hard limit, so the "
                         f"response was measured outside the programmable envelope")
        # A MAJORITY of bands must carry the negative adjusted slope, not merely one. This is the
        # same argument already applied to the responding fraction: the 18 bands are 5 Hz wide on a
        # 1 Hz grid, so they overlap heavily and move together, and a single qualifying band is the
        # maximum of a correlated family rather than a finding. Applying the rule to the responding
        # fraction but not to the adjusted sign was an inconsistency: on RCS08 it let
        # ZERO_TWO_RIGHT/Left/110 Hz through on 3 of 18 negative bands with a POSITIVE median slope
        # of +0.0409.
        if require_era_significance and n_sig_neg / n < min_responding_fraction:
            if n_sig == 0:
                fails.append("no band has a significant era-blocked slope, so the contrast is not "
                             "separable from the amplitude-versus-time confound")
            else:
                fails.append(
                    f"only {n_sig_neg} of {n} bands have a significant NEGATIVE era-blocked slope "
                    f"(need {min_responding_fraction:.0%}; {n_sig} are significant in either "
                    "direction). Once the amplitude-versus-time confound is removed the response "
                    "does not fall with amplitude in a majority of bands, which is what Adaptive "
                    "Therapy needs; falling arm means without a falling adjusted slope are a time "
                    "artifact")

        rows.append(dict(channel=ch, hemisphere=hemi, rate_hz=float(rate), n_bands=n,
                         n_responding=n_resp, responding_fraction=round(n_resp / n, 3),
                         n_era_significant=n_sig,
                         n_era_negative_significant=n_sig_neg,
                         median_separation_d=(round(float(np.median(seps)), 3) if seps
                                              else float("nan")),
                         amp_low_mA=(min(amps) if amps else float("nan")), amp_high_mA=amp_hi,
                         sensing_side=_sensing_side(ch),
                         laterality=_laterality(ch, hemi),
                         amp_limit_mA=(round(cap, 2) if np.isfinite(cap) else None),
                         within_amp_limit=within_limit,
                         deployable=(not fails), blocking_reasons="; ".join(fails)))
    screen = pd.DataFrame(rows)
    if screen.empty:
        return screen, None
    ok = screen[screen.deployable]
    if ok.empty:
        return screen, None
    # Rank IPSILATERAL cells ahead of contralateral ones before considering strength of evidence.
    # A contralateral pairing (sensing on one side driving stimulation on the other) is supported by
    # the device but only once a contralateral sensing configuration has been set up, so preferring
    # it on the strength of a slightly better separation would hand back a configuration that needs
    # an extra clinical step without saying so. Contralateral cells remain in the screen and remain
    # selectable by naming them explicitly through select_for.
    ok = ok.assign(_ipsi=(ok["laterality"] == "ipsilateral").astype(int))
    best = ok.sort_values(["_ipsi", "responding_fraction", "median_separation_d"],
                          ascending=False).iloc[0]
    return screen, (best.channel, best.hemisphere, float(best.rate_hz))


def select_for(evidence, *, rate_hz, hemisphere, channel=None):
    """The evidence cell matching a frozen configuration, or ``None`` with the reason.

    Evidence must come from the SAME rate as the configuration being gated. Stimulation artifact
    scales with rate, so a response established at one rate says nothing about another, and the gate
    would otherwise be satisfied by evidence from a regime that is not the one being deployed.
    Hemisphere must match for the same reason amplitude is per-hemisphere.

    ``channel=None`` with several sensing channels available is AMBIGUOUS and returns ``None``: the
    caller must name the channel, because picking one silently hides that a choice was made.
    """
    hits = {k: v for k, v in (evidence or {}).items()
            if np.isclose(float(k[2]), float(rate_hz)) and k[1] == hemisphere
            and (channel is None or k[0] == channel)}
    if not hits:
        return None, (f"no evidence for {hemisphere} at {float(rate_hz):g} Hz"
                      + (f" on {channel}" if channel else ""))
    if len(hits) > 1:
        return None, ("ambiguous: evidence exists on " + ", ".join(sorted(k[0] for k in hits))
                      + " — name the sensing channel rather than letting one be picked silently")
    (k, v), = hits.items()
    return v, f"{k[0]} {k[1]} @{k[2]:g} Hz"


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
        pd.to_numeric(ep[_resolve_col(ep, RATE_COLS, "stimulation rate")],
                      errors="coerce").dropna().unique().tolist())
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
