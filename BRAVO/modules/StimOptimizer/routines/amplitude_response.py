"""How band power responds to stimulation current: one fitted curve, evaluated anywhere.

WHY THIS FILE EXISTS, 2026-09-11 (redesign plan decision 21). The closed-loop simulation needs to
know what band power WOULD have been at an amplitude the controller commands, given what it WAS at
the amplitude the device was actually delivering. That is a difference of the same curve at two
currents, `g(a_sim) - g(a_obs)`, and the per-run baseline the pooled fit assigns to each visit
cancels in that difference -- so the curve needs no intercept, only its amplitude-dependent part.

Two shapes today, chosen by the evidence in the stored pooled row (`within_visit.
amplitude_response_shape_pooled`, decision 55): a straight line when no bend is established, and
the fitted quadratic -- with decision 55's second straight line past the peak -- once one is. The
same object can be built from any other fit that reports a slope, a quadratic, or a peak, which is
why it sits here as pure numpy with no import from any other module: the Biomarkers module may need
it once a bend in the stimulation-amplitude response has to be modelled there too (the PI's
standing expectation, decision 11 of the redesign plan), and Biomarkers is imported by everything
else, so a curve that lived anywhere else could not be imported from it without a cycle.

Units: currents in mA; power in whatever units the fit was made in (the pooled fit is in the
device's own linear units, so `g` and `offset` are in device units).
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, Optional

import numpy as np

NONE, LINEAR, QUADRATIC = "none", "linear", "quadratic"


def _f(v, default=float("nan")) -> float:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return default
    return x if np.isfinite(x) else default


@dataclass(frozen=True)
class ResponseCurve:
    """The amplitude-dependent part of the band-power response, `g(mA)`.

    ``kind`` is one of NONE (power does not respond: g == 0), LINEAR (g = slope * mA) or
    QUADRATIC (g = quad * mA^2 + lin * mA up to the peak, then the post-peak line, continued from
    g(peak) so the curve is unbroken). Every coefficient is stated in the fit's own units.
    ``fitted_lo_mA``/``fitted_hi_mA`` record the range of currents the fit rests on: outside it
    the curve is an extrapolation, and `extrapolates` says so for a given pair of limits.
    """
    kind: str = NONE
    slope_per_mA: float = 0.0
    slope_stderr: float = float("nan")
    slope_p: float = float("nan")
    quad_per_mA2: float = float("nan")
    quad_lin_per_mA: float = float("nan")
    quad_stderr: float = float("nan")
    p_curvature: float = float("nan")
    peak_mA: float = float("nan")
    post_peak_slope_per_mA: float = float("nan")
    fitted_lo_mA: float = float("nan")
    fitted_hi_mA: float = float("nan")
    n_points: int = 0
    n_runs: int = 0
    source: str = ""
    note: str = ""

    # ---- construction ----------------------------------------------------------------------
    @classmethod
    def zero(cls, note="no response: power follows the recording whatever the amplitude does"):
        return cls(kind=NONE, slope_per_mA=0.0, source="none", note=note)

    @classmethod
    def linear(cls, slope_per_mA, *, stderr=float("nan"), p=float("nan"), lo=float("nan"),
               hi=float("nan"), n_points=0, n_runs=0, source="linear", note=""):
        return cls(kind=LINEAR, slope_per_mA=float(slope_per_mA), slope_stderr=_f(stderr),
                   slope_p=_f(p), fitted_lo_mA=_f(lo), fitted_hi_mA=_f(hi),
                   n_points=int(n_points or 0), n_runs=int(n_runs or 0), source=source, note=note)

    @classmethod
    def from_pooled_row(cls, row: Optional[Dict[str, Any]], *, use_bend: bool = True,
                        lo_mA=float("nan"), hi_mA=float("nan")) -> "ResponseCurve":
        """The curve the stored pooled row (decision 103, `amplitude_effect.POOLED_FIELDS`)
        supports: the quadratic when a bend is established (`curves`) and its coefficients are
        stored, else the pooled straight line, else the zero curve with the row's own reason.

        ``use_bend=False`` forces the straight line even when a bend is established -- the
        control the simulation runs beside the peaked model so the two can be compared.
        """
        if not row:
            return cls.zero(note="no pooled row is stored for this contact and band yet")
        n = int(_f(row.get("n"), 0) or 0)
        n_runs = int(_f(row.get("n_visits"), 0) or 0)
        slope = _f(row.get("pooled_slope_per_mA"))
        curves = bool(row.get("curves"))
        a = _f(row.get("quad_coef_per_mA2"))
        b = _f(row.get("quad_lin_coef_per_mA"))
        if use_bend and curves and np.isfinite(a) and np.isfinite(b):
            peak = _f(row.get("peak_mA"))
            post = _f(row.get("post_peak_slope_per_mA"))
            return cls(kind=QUADRATIC, slope_per_mA=slope, slope_stderr=_f(row.get("pooled_slope_stderr")),
                       slope_p=_f(row.get("pooled_slope_p")), quad_per_mA2=a, quad_lin_per_mA=b,
                       quad_stderr=_f(row.get("quad_coef_stderr")),
                       p_curvature=_f(row.get("p_curvature")),
                       peak_mA=peak if bool(row.get("peaks_inside")) else float("nan"),
                       post_peak_slope_per_mA=post, fitted_lo_mA=_f(lo_mA), fitted_hi_mA=_f(hi_mA),
                       n_points=n, n_runs=n_runs, source="stored pooled row, quadratic",
                       note=str(row.get("verdict") or ""))
        if np.isfinite(slope):
            return cls.linear(slope, stderr=row.get("pooled_slope_stderr"), p=row.get("pooled_slope_p"),
                              lo=lo_mA, hi=hi_mA, n_points=n, n_runs=n_runs,
                              source="stored pooled row, straight line",
                              note=str(row.get("verdict") or ""))
        return cls.zero(note=str(row.get("verdict") or "the pooled slope is not assessed"))

    # ---- evaluation --------------------------------------------------------------------------
    def g(self, amp_mA):
        """The amplitude-dependent part of power at ``amp_mA`` (scalar or array)."""
        x = np.asarray(amp_mA, dtype=float)
        if self.kind == NONE:
            return np.zeros_like(x)
        if self.kind == LINEAR:
            return self.slope_per_mA * x
        a, b = self.quad_per_mA2, self.quad_lin_per_mA
        quad = a * x * x + b * x
        if np.isfinite(self.peak_mA) and np.isfinite(self.post_peak_slope_per_mA):
            gp = a * self.peak_mA ** 2 + b * self.peak_mA
            return np.where(x <= self.peak_mA, quad, gp + self.post_peak_slope_per_mA * (x - self.peak_mA))
        return quad

    def offset(self, amp_sim, amp_obs):
        """What power would differ by, at the commanded current against the recorded one."""
        return self.g(amp_sim) - self.g(amp_obs)

    def derivative(self, amp_mA):
        """dg/dmA -- positive where raising the current RAISES the band's power."""
        x = np.asarray(amp_mA, dtype=float)
        if self.kind == NONE:
            return np.zeros_like(x)
        if self.kind == LINEAR:
            return np.full_like(x, self.slope_per_mA)
        d = 2.0 * self.quad_per_mA2 * x + self.quad_lin_per_mA
        if np.isfinite(self.peak_mA) and np.isfinite(self.post_peak_slope_per_mA):
            return np.where(x <= self.peak_mA, d, self.post_peak_slope_per_mA)
        return d

    def positive_feedback_range(self, lo_mA, hi_mA, n=201):
        """The stretch of [lo, hi] where power rises with current -- the WRONG side of the peak
        for the device's Dual Threshold law, which raises current to suppress power. Returns
        (lo, hi) of that stretch or None. Sampled on a grid, which is exact for a line and for a
        quadratic with one vertex."""
        lo, hi = float(lo_mA), float(hi_mA)
        if not (np.isfinite(lo) and np.isfinite(hi) and hi > lo):
            return None
        xs = np.linspace(lo, hi, int(n))
        up = self.derivative(xs) > 0
        if not up.any():
            return None
        return (float(xs[up].min()), float(xs[up].max()))

    def extrapolates(self, lo_mA, hi_mA) -> bool:
        if not (np.isfinite(self.fitted_lo_mA) and np.isfinite(self.fitted_hi_mA)):
            return False
        return bool(float(lo_mA) < self.fitted_lo_mA - 1e-9 or float(hi_mA) > self.fitted_hi_mA + 1e-9)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        return {k: (None if isinstance(v, float) and not np.isfinite(v) else v) for k, v in d.items()}
