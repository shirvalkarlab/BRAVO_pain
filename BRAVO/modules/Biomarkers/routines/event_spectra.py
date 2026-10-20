"""Observed support of Percept event FFT magnitudes (µVp), not waveform PSDs.

Medtronic UC202012929dEN, JSON schema for LfpFrequencySnapshotEvents:
negative FFTBinData values are censored to avoid artifacts. Keep those bins
missing; neither zero-filling nor extending nearby observations recovers them.
"""
import numpy as np

EVENT_SPECTRUM_SOURCE = "Patient event"


def _observed_runs(frequency, magnitude):
    """Return ordered, contiguous observed runs; invalid axes have no support."""
    try:
        f = np.asarray(frequency, dtype=float)
        m = np.asarray(magnitude, dtype=float)
    except (TypeError, ValueError):
        return []
    if f.ndim != 1 or m.ndim != 1 or f.size != m.size or not f.size:
        return []
    if np.any(np.diff(f[np.isfinite(f)]) <= 0):
        return []
    observed = np.flatnonzero(np.isfinite(f) & (f >= 0) & np.isfinite(m) & (m >= 0))
    runs = np.split(observed, np.flatnonzero(np.diff(observed) > 1) + 1)
    return [(f[run], m[run]) for run in runs if run.size]


def interpolate_observed_event_spectrum(frequency, magnitude, grid):
    """Interpolate within observed runs only; retain zeros and missing intervals."""
    grid = np.asarray(grid, dtype=float)
    out = np.full(grid.shape, np.nan, dtype=float)
    for f, m in _observed_runs(frequency, magnitude):
        inside = (grid >= f[0]) & (grid <= f[-1])
        out[inside] = np.interp(grid[inside], f, m)
    return out


def event_band_supported(frequency, magnitude, center_hz, half_hz=2.5):
    """Whether the entire requested band lies in one contiguous observed run.

    This gates the existing calibrated calculation without modifying it. A
    censored interval or incomplete band must not become a smaller finite sum.
    """
    try:
        center, half = float(center_hz), float(half_hz)
    except (TypeError, ValueError):
        return False
    if not np.isfinite(center) or not np.isfinite(half) or half <= 0:
        return False
    lo, hi = center - half, center + half
    return any(f[0] <= lo and f[-1] >= hi for f, _ in _observed_runs(frequency, magnitude))
