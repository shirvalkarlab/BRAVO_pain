"""Does a candidate LFP band RESPOND TO STIMULATION AMPLITUDE?

WHY THIS IS A SEPARATE QUESTION FROM "DOES IT TRACK PAIN"
--------------------------------------------------------
The A610 manual (M066414C001 Rev B, p. 35) states: "Adaptive Therapy relies on LFP signals that
respond to stimulation amplitude changes. If a patient's LFP signal does not respond in this way,
Adaptive Therapy may not be optimal."

A band can correlate perfectly with reported pain and still be useless as a closed-loop control
signal, because the controller does not act on pain — it acts on the band, and it can only act by
moving amplitude. If amplitude does not move the band, the loop has no authority. In Parkinson's
this requirement is met by the well-characterised alpha-beta suppression with increasing stimulation
amplitude; for a pain biomarker it is not established, and the biomarker module currently tests only
the pain correlation. This module supplies the missing test.

THE TEST MIRRORS THE DEVICE'S OWN CAPTURE PROCEDURE
--------------------------------------------------
Rather than a generic regression, the primary readout reproduces what the device will actually do
(manual p. 39, white paper p. 15):

  * capture LFP power at the LOWER amplitude of therapeutic benefit  -> L
  * capture LFP power at the UPPER amplitude of therapeutic benefit  -> U
  * derive threshold = 0.75 * (U - L) + L
  * REFUSE if the two captures are "too close together or are inverted"

So the question is not merely "is the slope significantly non-zero" but "would the device accept the
captures this band produces, in the direction the mode requires, with enough separation to place a
threshold". A statistically significant but tiny response fails that test just as surely as a null
one, which is why both a contrast and a separation measure are reported.

Power is computed in the DEVICE's units for the capture contrast — the linear sum of squared
magnitude over the band (manual p. 39), not log and not mean — because the threshold has to be
expressed in those units. Inference is additionally run on the log scale, where a multiplicative
quantity spanning orders of magnitude is better behaved.

THE TIME CONFOUND IS NOT OPTIONAL HERE
--------------------------------------
In this record stimulation amplitude rose over time, so a naive amplitude effect is partly a time
effect. Every model below carries ``era`` as a blocking factor and uses cluster-robust standard
errors on the repeat unit, and the unadjusted estimate is reported beside the adjusted one so the
size of the confound is visible rather than asserted away.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd


#: Minimum standardised separation between the two captures for a threshold to be placeable.
#: Expressed as a Cohen-style d on the log scale. This is a JUDGEMENT, not a device figure: the
#: labelling says the device refuses captures that are "too close together" without publishing the
#: tolerance, so we require the two capture distributions to be separated by at least this much for
#: the derived threshold to sit somewhere the signal actually spends time on both sides of. Recorded
#: as a named constant so it can be argued with rather than buried.
MIN_CAPTURE_SEPARATION_D = 0.5

#: Minimum rows per capture arm before an estimate is reported at all.
MIN_ROWS_PER_ARM = 8


@dataclass
class ResponseResult:
    """Verdict on whether one band responds to stimulation amplitude."""

    responds: bool | None                 # None == not assessed
    reason: str
    direction_ok: bool | None = None
    n_low: int = 0
    n_high: int = 0
    amp_low_mA: float = float("nan")
    amp_high_mA: float = float("nan")
    power_low: float = float("nan")       # device units, linear sum of squares
    power_high: float = float("nan")
    derived_threshold: float = float("nan")
    captures_inverted: bool | None = None
    separation_d: float = float("nan")
    slope_log_per_mA: float = float("nan")
    slope_ci: tuple = (float("nan"), float("nan"))
    slope_p: float = float("nan")
    slope_unadjusted: float = float("nan")
    n_eras: int = 0
    notes: list = field(default_factory=list)

    def describe(self) -> str:
        if self.responds is None:
            return f"NOT ASSESSED: {self.reason}"
        verdict = "RESPONDS" if self.responds else "DOES NOT RESPOND"
        return (f"{verdict} — {self.reason} | captures {self.power_low:.4g} -> {self.power_high:.4g} "
                f"device units at {self.amp_low_mA:.1f} -> {self.amp_high_mA:.1f} mA, "
                f"separation d={self.separation_d:.2f}, era-adjusted log slope "
                f"{self.slope_log_per_mA:+.4f}/mA (p={self.slope_p:.4g})")


def device_band_power(psd_magnitude, freqs, center_hz, band_width_hz):
    """Band power in the DEVICE's definition: sum of squared magnitude over the band.

    Manual p. 39: "Captured LFP power ... calculated as the sum of the squared LFP magnitude at each
    frequency within the selected band, similar to the Area Under the Curve."

    ``psd_magnitude`` is (n_rows, n_freqs) of MAGNITUDE (not power). Returns (n_rows,). A mean or a
    log would be a different quantity and would not be the number the device thresholds; the sum
    also scales with the number of bins in the band, which is why the band width must be fixed when
    comparing values.
    """
    mag = np.asarray(psd_magnitude, dtype=float)
    f = np.asarray(freqs, dtype=float)
    if mag.ndim != 2:
        raise ValueError(f"psd_magnitude must be 2-D (rows x freqs), got shape {mag.shape}")
    if mag.shape[1] != f.size:
        raise ValueError(f"freqs has {f.size} entries but psd_magnitude has {mag.shape[1]} columns")
    lo = float(center_hz) - float(band_width_hz) / 2.0
    hi = float(center_hz) + float(band_width_hz) / 2.0
    sel = (f >= lo) & (f <= hi)
    if not sel.any():
        raise ValueError(f"no frequency bins inside {lo:.3f}-{hi:.3f} Hz "
                         f"(available {f.min():.3f}-{f.max():.3f} Hz)")
    return np.nansum(mag[:, sel] ** 2, axis=1)


def assess_response(power, amplitude_mA, *, era=None, cluster=None, mode_requires="suppression",
                    low_amp=None, high_amp=None, min_sep_d=MIN_CAPTURE_SEPARATION_D):
    """Does ``power`` respond to ``amplitude_mA`` in the direction a control mode needs?

    ``power`` is in device units (linear sum of squares). ``mode_requires`` is ``"suppression"`` for
    Dual and Single Threshold modes (higher amplitude must LOWER the band) or ``"elevation"`` for the
    inverse relationship. ``era`` blocks the time confound; ``cluster`` is the repeat unit for
    cluster-robust standard errors (epoch or rating id). ``low_amp``/``high_amp`` pin the two capture
    arms; by default the lowest and highest observed amplitude levels with enough rows are used.

    Returns a :class:`ResponseResult`. A verdict of ``None`` means NOT ASSESSED — the data cannot
    answer the question — which is reported as such and never as "does not respond".
    """
    p = np.asarray(power, dtype=float)
    a = np.asarray(amplitude_mA, dtype=float)
    if p.shape != a.shape:
        raise ValueError(f"power {p.shape} and amplitude {a.shape} must have the same shape")
    if mode_requires not in ("suppression", "elevation"):
        raise ValueError("mode_requires must be 'suppression' or 'elevation'")

    ok = np.isfinite(p) & np.isfinite(a) & (p > 0)
    notes = []
    if (~np.isfinite(p)).any() or (p <= 0).any():
        notes.append(f"{int((~ok).sum())} rows dropped: non-finite or non-positive power "
                     "(log-scale inference needs strictly positive power)")
    if ok.sum() < 2 * MIN_ROWS_PER_ARM:
        return ResponseResult(None, f"only {int(ok.sum())} usable rows; need at least "
                                    f"{2 * MIN_ROWS_PER_ARM}", notes=notes)
    p, a = p[ok], a[ok]
    era_v = (np.asarray(era)[ok] if era is not None else None)
    clus = (np.asarray(cluster)[ok] if cluster is not None else None)

    levels = np.unique(a)
    if levels.size < 2:
        return ResponseResult(None, f"stimulation amplitude never varied (single level "
                                    f"{levels[0]:.2f} mA); the response is unidentifiable",
                              notes=notes)

    # --- capture arms, mirroring the device's two-amplitude procedure -------------------------
    counts = {float(v): int((a == v).sum()) for v in levels}
    usable = sorted([v for v, n in counts.items() if n >= MIN_ROWS_PER_ARM])
    if len(usable) < 2:
        return ResponseResult(None, f"no two amplitude levels have >= {MIN_ROWS_PER_ARM} rows "
                                    f"(counts {counts})", notes=notes)
    lo_a = float(usable[0] if low_amp is None else low_amp)
    hi_a = float(usable[-1] if high_amp is None else high_amp)
    if hi_a <= lo_a:
        return ResponseResult(None, f"high capture amplitude {hi_a} is not above the low one {lo_a}",
                              notes=notes)
    m_lo, m_hi = (a == lo_a), (a == hi_a)
    if m_lo.sum() < MIN_ROWS_PER_ARM or m_hi.sum() < MIN_ROWS_PER_ARM:
        return ResponseResult(None, f"capture arms too small (low n={int(m_lo.sum())}, "
                                    f"high n={int(m_hi.sum())})", notes=notes)

    # Medians in device units: the capture is a summary of a short recording, and a median is less
    # sensitive to a transient artefact than a mean would be.
    P_lo, P_hi = float(np.median(p[m_lo])), float(np.median(p[m_hi]))
    # The device derives its threshold from the two captures, ordered lower-amplitude first.
    thr = 0.75 * (P_hi - P_lo) + P_lo

    lg = np.log(p)
    s_lo, s_hi = lg[m_lo], lg[m_hi]
    pooled = np.sqrt(((s_lo.size - 1) * s_lo.var(ddof=1) + (s_hi.size - 1) * s_hi.var(ddof=1))
                     / max(1, s_lo.size + s_hi.size - 2))
    sep_d = float(abs(s_lo.mean() - s_hi.mean()) / pooled) if pooled > 0 else float("inf")

    expected_lower_at_high = (mode_requires == "suppression")
    observed_lower_at_high = P_hi < P_lo
    direction_ok = bool(observed_lower_at_high == expected_lower_at_high)
    # "Inverted" in the device's sense: the capture pair runs the wrong way for the chosen mode, so
    # the derived threshold would sit outside the range the signal moves through.
    inverted = not direction_ok

    # --- era-blocked, cluster-robust slope on the log scale -----------------------------------
    slope = ci = pval = np.nan
    slope_unadj = np.nan
    n_eras = 0
    try:
        import statsmodels.formula.api as smf
        df = pd.DataFrame({"logp": lg, "amp": a})
        slope_unadj = float(smf.ols("logp ~ amp", data=df).fit().params["amp"])
        formula = "logp ~ amp"
        if era_v is not None and pd.Series(era_v).nunique() > 1:
            df["era"] = pd.Series(era_v).astype(str).values
            n_eras = int(df["era"].nunique())
            formula += " + C(era)"
        fit_kw = {}
        if clus is not None and pd.Series(clus).nunique() > 1:
            df["clus"] = pd.Series(clus).values
            fit_kw = dict(cov_type="cluster", cov_kwds={"groups": df["clus"]})
        res = smf.ols(formula, data=df).fit(**fit_kw)
        slope = float(res.params["amp"])
        lo_ci, hi_ci = res.conf_int().loc["amp"]
        ci = (float(lo_ci), float(hi_ci))
        pval = float(res.pvalues["amp"])
        if not fit_kw:
            notes.append("standard errors are NOT cluster-robust (no usable cluster variable), so "
                         "the p-value is anti-conservative under repeated sampling within a unit")
        if n_eras == 0:
            notes.append("era NOT blocked (no usable era variable); the amplitude effect is "
                         "confounded with time in this record and this estimate does not separate "
                         "them")
    except Exception as exc:                                   # pragma: no cover - defensive
        notes.append(f"slope model failed ({type(exc).__name__}: {exc}); verdict rests on the "
                     "capture contrast alone")
        ci = (float("nan"), float("nan"))

    # --- verdict ------------------------------------------------------------------------------
    sep_ok = sep_d >= float(min_sep_d)
    responds = bool(direction_ok and sep_ok)
    if not direction_ok:
        reason = (f"captures run the WRONG WAY for a mode requiring {mode_requires}: power "
                  f"{'falls' if observed_lower_at_high else 'rises'} from {P_lo:.4g} to {P_hi:.4g} "
                  f"as amplitude goes {lo_a:.1f} -> {hi_a:.1f} mA. The device refuses inverted "
                  "captures.")
    elif not sep_ok:
        reason = (f"direction is right but the captures are TOO CLOSE: separation d={sep_d:.2f} "
                  f"below the required {float(min_sep_d):.2f}, so a threshold placed between them "
                  "would not have the signal reliably on both sides.")
    else:
        reason = (f"direction correct for {mode_requires} and captures separated by d={sep_d:.2f}")

    return ResponseResult(responds=responds, reason=reason, direction_ok=direction_ok,
                          n_low=int(m_lo.sum()), n_high=int(m_hi.sum()),
                          amp_low_mA=lo_a, amp_high_mA=hi_a,
                          power_low=P_lo, power_high=P_hi, derived_threshold=float(thr),
                          captures_inverted=inverted, separation_d=sep_d,
                          slope_log_per_mA=slope, slope_ci=ci, slope_p=pval,
                          slope_unadjusted=slope_unadj, n_eras=n_eras, notes=notes)
