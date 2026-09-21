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

import enum
import re
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from . import lfp_response as LFP
from . import percept_adaptive as PA
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


# UNTIL 2026-09-19 a table here (``LOG_SCALES``) named how the assembled matrix's decibels were to be
# undone, because getting the exponent wrong by a factor of ten returned plausible-looking numbers.
# The matrix now holds raw power (``X``, decision 204, on the PI's rule that log power enters no
# calculation), so there is nothing to undo and the table is gone.

# =================================================================================================
# PUTTING THIS MODULE'S BAND POWER ONTO THE DEVICE'S OWN NUMBER SCALE
# =================================================================================================
# THE PROBLEM, found 2026-09-06 because the PI said the closed-loop page's numbers looked wrong.
# He was right. He said they "shouldn't span values of one to nine, they should be in the hundreds
# minimum and often probably in the thousands", and as shipped they spanned about 0.04 to 27.
#
# ``band_power_linear`` below integrates the stored power density across the band (until decision
# 204 it undid a stored logarithm first). Its own docstring says that gives the device's quantity
# "up to a fixed scale factor" -- and
# THAT FACTOR WAS NEVER APPLIED ANYWHERE. There was a constant for it,
# ``ClosedLoopDeployment.constraints.LFP_POWER_LSB_TO_UV2 = 0.01``, but the only thing in the whole
# repository that touched it was one test asserting its value; no production code multiplied by it.
# So every band power this module produced was the device's quantity divided by roughly two hundred,
# and it was labelled as being in the device's units.
#
# WHY A CONSTANT IS THE RIGHT SHAPE OF FIX, AND WHY IT CHANGES NO CONCLUSION. The lab's own
# calibration note (Biomarkers/routines/analytics.py, above LSB_PER_UV2_TRANSFORM) sets this out:
# the scale factor is multiplicative on the whole feature column, so within a single-source feature
# it CANCELS inside a correlation or an area under the curve, and it cancels inside any standardised
# effect size. It matters for exactly two things -- the absolute values displayed, and any comparison
# against a threshold programmed in the device's units. Both of those are what the PI is asking
# about. So applying it corrects the displayed scale and the threshold arithmetic while leaving every
# slope sign, p-value and verdict in this module untouched.
#
# WHY NOT THE LAB'S EXISTING CONSTANTS. ``LSB_PER_UV2_TRANSFORM`` (the transform constant in effect) is calibrated for a
# DIFFERENT signal-processing recipe -- its note names it precisely: "RC+S-Hann / 256-pt zero-padded
# FFT / peak-amplitude / mean-magnitude band power", reproduced bit-for-bit. This module does
# something else: it exponentiates a dB10 power DENSITY and integrates it over the band. A different
# reduction has a different constant, and nobody had ever measured this one.
# ``LFP_POWER_LSB_TO_UV2 = 0.01`` (i.e. 100) descends from ``LSB_RULE_OF_THUMB``, whose own comment
# calls it "carried here only as the schema default".
#
# HOW THIS NUMBER WAS MEASURED, on RCS08's own record, on 2026-09-06.
# Two independent references, on rows matched by electrode, band centre AND moment (within 2 s):
#
#   (a) against the band power derived from the raw samples -- the scale the platform's exploration
#       pages display -- 4,555 paired rows: median factor 216.6, and stable across band centres
#       (215.2, 214.2, 216.1, 215.5, 221.7 for 12.5/17.5/22.5/24.5/27.5 Hz) and across all six
#       electrodes (207.1 to 219.6).
#
#   (b) against the DEVICE'S OWN reported LFP Power -- 6,835 paired rows. Four of the six electrodes
#       agree tightly with (a): ZERO_THREE_LEFT 218, ZERO_TWO_RIGHT 215-223, ONE_THREE_RIGHT 202-213,
#       ZERO_TWO_LEFT 204-212, with a 10th-to-90th spread as narrow as 1.23x on two of them, which is
#       comparable to the 1.19x fold error the lab's own transform calibration reports.
#
# Two independent references converging on about 215 is the reason for the value below.
#
# THE HONEST LIMITATION, recorded here because it is not resolved and must not be forgotten.
# The other TWO electrodes in reference (b) disagree, and they disagree in a structured way rather
# than noisily: ONE_THREE_LEFT gives 85, 70, 57, 54, 51 and ZERO_THREE_RIGHT gives 62, 46, 36, 33,
# 29 across those same five band centres -- both FALLING with frequency, with 10th-to-90th spreads
# up to 14.8x. Those two are precisely the electrodes with the most device-reported windows (797 and
# 384, against 251-294 for the rest), which is a hint rather than an explanation: the device reports
# LFP Power for the ONE band it was configured to sense, and reading its value at other band centres
# is not the same thing as the device having measured them. Until that is understood, a value from
# this module carries a genuine uncertainty of roughly a factor of two on those two electrodes, and
# should not be compared against a programmed threshold there without checking it against the
# device's own reading for that specific band. This does not affect any sign, slope or verdict, for
# the cancellation reason above.
#
# WHY THERE IS NO NEW CONSTANT HERE, AND WHY MY FIRST ATTEMPT AT ONE WAS WRONG.
#
# I initially set a constant of 215 here, measured tonight by matching rows between two
# representations of this participant's signal. The PI asked why the lab's existing calibration was
# not being used instead. Reading HANDOFF_TD_LSB_calibration_2026-06-27.md settled it against me,
# and the reasons are worth keeping because they are easy to walk back into.
#
# FIRST, A WRITTEN DECISION FORBIDS IT. That handoff records, as an architecture decision of the PI
# dated 2026-06-27 and marked "no open option": the deployable source of truth for band power in the
# device's units is the TD transform route with the constant in effect, and it is "the PRIMARY way LSB is
# computed for both the exploratory panels and the deployment fallback -- NOT a second DSP to
# maintain". It names both consumers explicitly, and one of them is this module. The whole purpose
# of that decision was to REMOVE a split in which one path silently used a different recipe and a
# different constant from the lab's headline model. Adding a fifth recipe with a fifth constant
# would rebuild exactly the split the decision exists to eliminate.
#
# SECOND, THAT HANDOFF ALREADY CATALOGUES MY MISTAKE BY NAME. Its "ERROR 3 -- Conflating the two
# scale constants" records that each signal-processing recipe has its OWN constant: the transform
# route gives 352.62, welch256 gives 270.22, welch250 gives 265.17, and a per-window variant gives
# 326. So a new number for a new recipe is not automatically a discovery; it is the predictable
# consequence of using a recipe nobody calibrated.
#
# THIRD, AND DECISIVELY, MY MEASUREMENT WAS NOT GOOD ENOUGH TO STAND ON. The lab's transform
# calibration reports r = 0.9927, RMSE 60.6 device units, and a median fold error of 1.092 with 93.9%
# of blocks inside 1.5x. My paired ratio gave a median fold error of 2.70x with one constant, and
# even with a separate constant per electrode and band the 90th percentile was 4.14x and the worst
# case 13.9x. That handoff's "ERROR 1" states the diagnostic plainly: if a pairing does not
# reproduce k = 352.6 with r = 0.9927 then the pairing itself is wrong, because non-coincident or
# wrong-product pairing drops the correlation to about 0.13. Mine did not reproduce it, so the honest
# reading is that 215 measured my pairing error, not a property of the device.
#
# WHAT THE ACTUAL FIX IS. Band power in this module must come from the calibrated route rather than
# from integrating a stored decibel power density, which is what ``band_power_linear`` below does and
# which no calibration covers. The calibrated helper already exists and its own docstring describes
# it as "One helper, one constant, used by both the Biomarker exploration panels and the deployment
# modeled fallback": ``Biomarkers.routines.analytics.td_to_lsb``, which applies the transform recipe
# (mean-detrend, rcs-Hann taper, zero-pad to 256, real FFT, peak scale, sum of squared magnitude over
# the band) and multiplies by the transform constant in effect. The 3-second tiles held in the Biomarkers raw cache are that
# same quantity already computed, which is why the platform's own pages read in the hundreds to
# thousands while this module read in single digits.
#
# Until this module is switched onto that route, its band power is proportional to the device's
# quantity but NOT on the device's scale, and the docstring of ``band_power_linear`` says so. Nothing
# should compare a value from here against a threshold programmed in device units.


def band_power_linear(psd, freqs, center_hz, width_hz):
    """Device-style band power from a raw power spectrum: integrate the density over the band.

    The device thresholds a linear sum of squared magnitude over the band, and power is proportional
    to squared magnitude, so integrating raw power density gives the device's quantity up to a
    fixed scale factor. ``psd`` is one raw spectrum per row (the assembled matrix's ``X``); until
    decision 204 (2026-09-19) it was decibels and this function undid them first, with a named
    convention because the wrong exponent returned plausible numbers. Nothing is undone now.

    Returns one value per row, or ``None`` when the band lies outside the frequency axis, rather
    than integrating over whichever bins happen to be nearest.
    """
    f = np.asarray(freqs, float)
    lo, hi = float(center_hz) - float(width_hz) / 2.0, float(center_hz) + float(width_hz) / 2.0
    sel = (f >= lo) & (f <= hi)
    if not sel.any():
        return None
    lin = np.asarray(psd, float)[:, sel]
    df = float(np.median(np.diff(f))) if f.size > 1 else 1.0
    return np.nansum(lin, axis=1) * df


def frame_from_matrix(mat, *, sources=None):
    """The BRAVO assembled PSD matrix -> the row frame :func:`build_evidence` consumes.

    ``mat`` is what ``Biomarkers.bravo_service._cached_psd_matrix`` returns:
    ``{"X": (N,F) raw power, "t": (N,), "channel": (N,), "source": (N,), "f_set": (F,)}``. Note ``f_set`` is
    ONE shared frequency axis for every row, not a per-row array, so it is attached to each row here
    rather than being re-derived.

    ``sources`` optionally restricts which recording sources contribute (e.g. streaming time-domain
    only, excluding montage sweeps). Left as ``None`` every source is kept, which is right for a
    response test — the question is whether the band moves with amplitude, and a montage sweep
    observes that as validly as a streaming segment.
    """
    # ``X`` is raw power (decision 204). A matrix that still carries ``logX`` is an entry assembled
    # under the old decibel rule and is refused here rather than read as raw power.
    need = {"X", "t", "channel", "f_set"}
    missing = need - set(mat or {})
    if missing:
        raise KeyError(f"assembled matrix missing {sorted(missing)}; has {sorted((mat or {}))}")
    X = np.asarray(mat["X"], float)
    f_set = np.asarray(mat["f_set"], float)
    if X.shape[1] != f_set.size:
        raise ValueError(f"X has {X.shape[1]} frequency columns but f_set has {f_set.size}")
    src = np.asarray(mat.get("source", np.full(X.shape[0], "?")), dtype=object)
    keep = np.ones(X.shape[0], bool) if sources is None else np.isin(src, list(sources))
    return pd.DataFrame({"t": np.asarray(mat["t"], float)[keep],
                         "channel": np.asarray(mat["channel"], dtype=object)[keep],
                         "source": src[keep],
                         "psd": list(X[keep]),
                         "freqs": [f_set] * int(keep.sum())})


# =================================================================================================
# READING BAND POWER THAT IS ALREADY ON THE DEVICE'S NUMBER SCALE
# =================================================================================================
# WHAT CHANGED, 2026-09-06. Everything above this line builds band power by integrating a stored
# power density across the band (a stored logarithm, undone first, until decision 204). Nobody ever calibrated that
# recipe, so the numbers it produced were proportional to the quantity the device works in but not
# on the device's scale, and the long note above ``band_power_linear`` explains why inventing a
# constant to bridge the gap was the wrong fix and was withdrawn.
#
# The right fix needs no constant at all, because the lab already computes band power on the
# device's scale and stores it. ``Biomarkers.routines.availability.raw_lsb_spectrum_cache`` cuts
# every recording into three-second tiles and, for each tile and each band centre, computes band
# power two ways:
#
#   * FROM THE RAW SAMPLES, using the recipe the lab validated bit for bit (mean-detrend, the
#     device's own Hann taper, zero-pad to 256 points, real Fourier transform, peak scaling, sum of
#     squared magnitude across the band) and then multiplying by the lab's own calibration number
#     for that recipe. That multiplication happens inside the Biomarkers module. It does not happen
#     here and there is no number for it in this file.
#
#   * FROM THE DEVICE'S OWN ONBOARD SPECTRUM, when the device reported one for that moment, using
#     the lab's separate calibration number for that route. Again the multiplication happens inside
#     the Biomarkers module.
#
# The lab's own comment on that cache records that the two routes were compared on the same
# recordings and agree to a ratio of about 0.99 between 8 and 30 Hz, which is why values from the
# two can sit in the same column of a table.
#
# THE ONE MISTAKE THAT WOULD BE EASY TO MAKE HERE, WRITTEN DOWN SO IT IS NOT MADE. The cache holds
# band centres one hertz apart, from 2.5 Hz to 99.5 Hz, and each stored value is the band power over
# a band 5 Hz wide centred on that centre, because the cache is built with a half width of 2.5 Hz.
# So neighbouring stored values OVERLAP each other by four fifths of their width. One stored value
# IS a complete five-hertz band on its own. Adding two neighbours together, or averaging them, would
# count almost the same signal twice and would inflate every number it touched while still returning
# something finite and plausible. The code below therefore never combines neighbouring values: it
# looks up the ONE column whose centre matches the band being asked for, and if no column matches
# that band exactly it reports the band as unavailable rather than assembling it from neighbours.
# The band width being asked for is checked against the cache's own half width for the same reason.

#: Column-name prefix carrying band power on the device's own scale, one column per band centre. The
#: centre is written into the name (``band_lsb_10.5`` is the five-hertz band centred on 10.5 Hz), so
#: asking for a band is a column lookup by name and there is no index arithmetic that could slide by
#: one and read the neighbouring band.
CAL_LSB_PREFIX = "band_lsb_"

#: Column-name prefix for the flag saying the DEVICE'S OWN onboard spectrum supplied that band on
#: that row, and that the lab marks the value as calibrated. One column per band centre, matching
#: the value columns above.
CAL_NATIVE_PREFIX = "band_native_"

_CAL_CENTER_RE = re.compile(r"^" + CAL_LSB_PREFIX + r"(-?\d+(?:\.\d+)?)$")

#: How close in time a device reading has to be to a three-second tile before the two are treated as
#: describing THE SAME MOMENT. Left as None it is read from the tile length the frame carries, as
#: half a tile, which is the largest gap two descriptions of one tile can have.
DEFAULT_NATIVE_TOLERANCE_FRACTION_OF_TILE = 0.5


class BandPowerTier(enum.IntEnum):
    """Where a single band power value came from. Recorded per row and per band, not per cell.

    A reader has to be able to tell which of the two routes produced any particular number, because
    the two are different measurements of the same thing: one is computed from the raw samples by
    the lab's validated recipe, the other is the device's own onboard spectrum. They agree closely
    on this record but they are not the same measurement and a table that mixed them silently would
    not be auditable.
    """

    NO_VALUE = 0
    TIME_DOMAIN_TRANSFORM = 1
    DEVICE_ONBOARD_SPECTRUM = 2


#: Plain sentences for the tiers above, for anything that has to show a reader where a number came
#: from without assuming they know the vocabulary.
TIER_LABELS = {
    BandPowerTier.NO_VALUE: "no value for this band on this row",
    BandPowerTier.TIME_DOMAIN_TRANSFORM:
        "computed from the raw samples by the lab's validated recipe and put on the device's scale "
        "inside the Biomarkers module",
    BandPowerTier.DEVICE_ONBOARD_SPECTRUM:
        "the device's own onboard spectrum for that moment, put on the device's scale inside the "
        "Biomarkers module",
}

#: The two families of row a calibrated frame carries, named the way the cache names its two tiers.
FAMILY_TIME_DOMAIN = "td_transform"
FAMILY_DEVICE_SPECTRUM = "device_psd"

#: What kind of band power a frame carries. Written into the audit so that a table of results says
#: which recipe produced it rather than leaving that to be inferred from the size of the numbers.
BAND_POWER_FROM_CALIBRATED_CACHE = "calibrated three-second tiles, already on the device's scale"
BAND_POWER_FROM_INTEGRATED_DENSITY = ("a stored decibel power density, linearised and integrated "
                                      "across the band; NOT on the device's scale")


def _cal_center_columns(frame):
    """``[(centre_hz, value_column, native_flag_column)]`` for a calibrated frame, by centre.

    Returns an empty list for a frame that does not carry calibrated band power, which is how
    :func:`build_evidence` tells the two kinds of frame apart. The centre is parsed back out of the
    column name rather than being taken from anywhere else, so the name and the number can never
    disagree.
    """
    out = []
    for col in getattr(frame, "columns", []):
        m = _CAL_CENTER_RE.match(str(col))
        if m:
            out.append((float(m.group(1)), str(col), CAL_NATIVE_PREFIX + m.group(1)))
    return sorted(out, key=lambda r: r[0])


def _cal_column_name(center_hz):
    """The one column name that holds the band centred on ``center_hz``.

    ``%g`` formatting is used in both directions so that 10.5 written into a name and 10.5 looked up
    later produce the same string. Nothing here rounds a requested centre onto the grid: a centre
    that does not match a column is reported as unavailable by the caller.
    """
    return f"{CAL_LSB_PREFIX}{float(center_hz):g}"


def frame_from_lsb_cache(cache, *, centers_hz=None, sources=None, channels=None):
    """The Biomarkers calibrated tile cache -> the row frame :func:`build_evidence` consumes.

    ``cache`` is ``{channel: raw_lsb_spectrum_cache(...) output}``, which is what
    ``Biomarkers.bravo_service._raw_lsb_cache_cached`` returns. Each entry holds two families of
    measurement for one sensing contact, on ONE shared axis of band centres:

    * ``entry["td"]`` — three-second tiles computed from the raw samples, with ``t`` the tile centre
      in unix seconds, ``lsb`` the band power on the device's scale, and two quality flags,
      ``ok`` and ``saturated``, one per tile.
    * ``entry["psd"]`` — the device's own onboard spectrum readings, with ``t`` in unix seconds,
      ``lsb`` the band power on the device's scale, and ``calibrated`` a flag PER READING AND PER
      BAND (a two-dimensional mask, not one flag per reading).

    Both families become rows of one frame, tagged in a ``family`` column, so that
    :func:`build_evidence` can apply the rule that the device's own reading wins wherever it exists.
    Nothing is dropped here — the quality flags travel as columns and the dropping happens in
    :func:`build_evidence`, where it can be counted into the audit.

    ``centers_hz`` restricts which band centres are carried. Left as None every centre in the cache
    is carried, which is 98 of them from 2.5 to 99.5 Hz. The production caller passes the range in
    which band power on the device's scale is deployable at all, because a band the device cannot
    place a sensing window on is not evidence for a deployment however it behaves. That range is
    read from the lab's own constants by the caller rather than being restated here.

    ``sources`` restricts which recording sources contribute, matched against the cache's OWN source
    labels — which are not the same vocabulary as the assembled-spectra frame's labels, so a caller
    that hands over labels from that other frame would otherwise silently filter everything away.
    A ``sources`` value that matches nothing therefore raises and names the labels that are present.

    ``channels`` restricts which sensing contacts contribute; left as None every contact in the
    cache is carried.
    """
    wanted = None if channels is None else {str(c) for c in channels}
    entries = {str(ch): e for ch, e in (cache or {}).items()
               if isinstance(e, dict) and (wanted is None or str(ch) in wanted)}
    if not entries:
        return pd.DataFrame()

    # ONE FRAME CARRIES ONE GRID. The band centres and the band half width are properties of the
    # cache, and a frame whose rows came from two different grids could not be read by a single
    # column lookup. Disagreement is therefore refused rather than reconciled.
    grids = {tuple(np.round(np.asarray(e["centers_hz"], float), 6)) for e in entries.values()}
    halves = {round(float(e["band_half_hz"]), 6) for e in entries.values()}
    windows = {round(float(e.get("window_s", np.nan)), 6) for e in entries.values()}
    if len(grids) != 1 or len(halves) != 1:
        raise ValueError("the cached contacts do not share one grid of band centres and one band "
                         f"half width ({len(grids)} distinct grids, half widths {sorted(halves)}); "
                         "one frame cannot carry two grids")
    all_centers = np.asarray(sorted(grids.pop()), float)
    half_hz = halves.pop()
    window_s = float(sorted(windows)[0])

    if centers_hz is None:
        keep_c = np.ones(all_centers.size, bool)
    else:
        want = np.asarray([float(c) for c in np.atleast_1d(centers_hz)], float)
        keep_c = np.array([bool(np.any(np.isclose(c, want, atol=1e-6))) for c in all_centers])
        missing = [float(w) for w in want
                   if not np.any(np.isclose(w, all_centers, atol=1e-6))]
        if missing:
            raise ValueError(f"band centres {missing} are not on the cache's grid "
                             f"({all_centers.min():g} to {all_centers.max():g} Hz, one hertz "
                             "apart); a centre that is not stored cannot be assembled from its "
                             "neighbours because neighbouring bands overlap by four fifths of "
                             "their width")
    centers = all_centers[keep_c]
    if not centers.size:
        raise ValueError("no band centre survived the requested restriction")

    def _matrix(rows, n_cols):
        """The cache's spectra -> a float matrix, whether they arrive as lists or as one array.

        TWO SHAPES REACH HERE AND BOTH ARE LEGITIMATE. A family built fresh by
        ``Biomarkers.routines.availability.raw_lsb_spectrum_cache`` holds its spectra as a list of
        lists with ``None`` for a missing value. A family restored from the shared tile-cache file
        holds them as ONE float array with ``nan`` for a missing value, because that file stores the
        spectra as an array -- its read is eleven times faster than rebuilding 29 million separate
        Python numbers.

        ``if not rows`` stood here and broke on 2026-09-06 the moment that file began serving
        arrays: asking a two-dimensional array whether it is truthy raises
        ``ValueError("The truth value of an array with more than one element is ambiguous")``. The
        effect was that this whole function raised for any participant whose tiles came back from
        the file rather than from a fresh build -- which is now the ordinary case -- so the
        calibrated band-power route failed while the endpoint still returned arms from the other
        route, i.e. it failed QUIETLY and produced a thinner answer rather than an error.

        No test caught it because every fixture in this suite builds its families as lists. The
        array case is now covered explicitly.
        """
        if rows is None:
            return np.zeros((0, n_cols), float)
        if isinstance(rows, np.ndarray):
            # Already numeric, already nan for missing. Only the emptiness test differs, and a
            # zero-row array must still come back with the requested width so the column
            # restriction below can be applied to it.
            if rows.size == 0:
                return np.zeros((0, n_cols), float)
            return np.asarray(rows, float)
        if len(rows) == 0:
            return np.zeros((0, n_cols), float)
        return np.asarray([[np.nan if v is None else float(v) for v in row] for row in rows],
                          float)

    blocks = []
    for ch, e in entries.items():
        td, psd = e.get("td") or {}, e.get("psd") or {}
        n_td, n_psd = len(td.get("t") or []), len(psd.get("t") or [])

        # TAKE THE VALUE AND REPLACE ONLY A MISSING ONE. `td.get("lsb") or []` stood here and broke
        # on 2026-09-06 the moment the Biomarkers tile cache began storing each window family's
        # spectra as one float array instead of a list of lists: asking a two-dimensional array
        # whether it is truthy raises ValueError("The truth value of an array with more than one
        # element is ambiguous") rather than answering. That made this function raise for any
        # participant whose tiles came back from the shared file rather than from a fresh build --
        # which is now the common case, and it is why the calibrated band-power route failed while
        # the endpoint still returned arms from the other route.
        #
        # `_RAW_LSB_MATRICES = ("lsb",)` in Biomarkers.bravo_service is the list of keys that become
        # arrays, and `lsb` is the only one, so the sibling `t`, `ok`, `saturated` and `source`
        # lookups below are still lists and are left exactly as they were. If that tuple ever grows,
        # every `or []` on the new key has to be changed the same way.
        rows_td = td.get("lsb")
        rows_psd = psd.get("lsb")
        v_td = _matrix([] if rows_td is None else rows_td, all_centers.size)[:, keep_c]
        v_psd = _matrix([] if rows_psd is None else rows_psd, all_centers.size)[:, keep_c]
        # The device family's calibrated mask is indexed by BOTH reading and band centre. A value
        # the lab does not mark calibrated is not used to set a number, so the mask is carried
        # through rather than being collapsed to one flag per reading.
        cal_psd = (np.asarray([[bool(x) for x in row] for row in psd["calibrated"]], bool)[:, keep_c]
                   if n_psd else np.zeros((0, centers.size), bool))
        cal_psd = cal_psd & np.isfinite(v_psd)

        for family, n, t, vals, native, src, ok, sat in (
                (FAMILY_TIME_DOMAIN, n_td, td.get("t") or [], v_td,
                 np.zeros((n_td, centers.size), bool), td.get("source") or [],
                 td.get("ok") or [], td.get("saturated") or []),
                (FAMILY_DEVICE_SPECTRUM, n_psd, psd.get("t") or [], v_psd, cal_psd,
                 psd.get("source") or [], [True] * n_psd, [False] * n_psd)):
            if not n:
                continue
            cols = {"t": np.asarray(t, float),
                    "channel": np.asarray([str(ch)] * n, dtype=object),
                    "source": np.asarray([str(s) for s in src], dtype=object),
                    "family": np.asarray([family] * n, dtype=object),
                    # The device family has no per-reading quality flags of its own, so its rows are
                    # marked good and not saturated. That is not an assumption about the device: the
                    # quality gate those flags implement is a gate on the raw sample tiles, and a
                    # reading the device itself reported has no raw samples here to gate.
                    "tile_ok": np.asarray([bool(x) for x in ok], bool),
                    "tile_saturated": np.asarray([bool(x) for x in sat], bool),
                    # Provenance that has to travel with the numbers rather than be looked up later.
                    "band_half_hz": np.full(n, half_hz, float),
                    "tile_window_s": np.full(n, window_s, float)}
            for j, c in enumerate(centers):
                cols[_cal_column_name(c)] = vals[:, j]
                cols[CAL_NATIVE_PREFIX + f"{c:g}"] = native[:, j]
            blocks.append(pd.DataFrame(cols))

    if not blocks:
        return pd.DataFrame()
    out = pd.concat(blocks, ignore_index=True)

    if sources is not None:
        want_src = {str(s) for s in sources}
        present = sorted({str(s) for s in out["source"].unique()})
        keep = out["source"].astype(str).isin(want_src)
        if not keep.any():
            raise ValueError(f"none of the requested sources {sorted(want_src)} appear in this "
                             f"cache, which holds {present}; the calibrated cache labels its "
                             "recordings differently from the assembled-spectra frame, so labels "
                             "from that frame will not match here")
        out = out[keep].reset_index(drop=True)
    return out.sort_values(["channel", "t"]).reset_index(drop=True)


def _merge_device_over_time_domain(p, center_cols, *, tol_s):
    """Combine the two families into one set of rows, with the device's own reading winning.

    ``p`` is one sensing contact's rows from a calibrated frame, indexed 0..n-1. Returns
    ``(values, tiers, keep_mask, counts)`` where ``values`` and ``tiers`` are ``(kept rows x band
    centres)`` and ``keep_mask`` says which of ``p``'s rows are kept.

    THE RULE, which comes from the lab's own architecture decision (see section 3.3 of
    ``HANDOFF_TD_LSB_calibration_2026-06-27.md``): a value modelled from the raw samples never sets
    the number where the device's own reading exists. So for every device reading that describes the
    same moment as a three-second tile, the device's value replaces the tile's value in the bands
    where the lab marks it calibrated, and the tile keeps its own value everywhere else.

    A device reading that describes no tile is NOT thrown away — it is kept as a row of its own, with
    a value only in the bands it is calibrated for. Throwing it away would discard the very
    measurements the rule above says are preferred.

    "The same moment" means within ``tol_s`` of the tile's centre. Readings are matched in order of
    increasing time gap, and one tile can absorb at most one reading, so the closest description of
    a tile wins and the outcome does not depend on the order the rows happen to sit in.
    """
    lsb_cols = [c for _, c, _ in center_cols]
    nat_cols = [c for _, _, c in center_cols]
    # A copy, deliberately. Pandas hands back a read-only view of its own storage, and the merge
    # below writes the device's readings into this matrix.
    values = np.array(p[lsb_cols].to_numpy(float), dtype=float, copy=True)
    native = p[nat_cols].to_numpy(bool) & np.isfinite(values)
    family = p["family"].astype(str).to_numpy()
    times = p["t"].to_numpy(float)

    is_td = family == FAMILY_TIME_DOMAIN
    is_dev = family == FAMILY_DEVICE_SPECTRUM

    # A device reading is only usable in the bands the lab marks calibrated. Outside those the lab
    # calls the value exploratory, so it must not set a number here.
    values[is_dev] = np.where(native[is_dev], values[is_dev], np.nan)

    tiers = np.where(np.isfinite(values),
                     np.where(is_dev[:, None], int(BandPowerTier.DEVICE_ONBOARD_SPECTRUM),
                              int(BandPowerTier.TIME_DOMAIN_TRANSFORM)),
                     int(BandPowerTier.NO_VALUE)).astype(np.int8)

    keep = np.ones(len(p), bool)
    counts = {"n_device_rows": int(is_dev.sum()),
              "n_device_rows_merged_into_a_tile": 0,
              "n_device_rows_standing_alone": int(is_dev.sum()),
              "n_values_from_device": 0}

    td_pos = np.flatnonzero(is_td)
    dev_pos = np.flatnonzero(is_dev)
    if td_pos.size and dev_pos.size:
        td_t = times[td_pos]
        order_td = np.argsort(td_t, kind="stable")
        td_sorted, td_pos_sorted = td_t[order_td], td_pos[order_td]
        # Nearest tile to each device reading, and the gap to it.
        ins = np.clip(np.searchsorted(td_sorted, times[dev_pos]), 1, td_sorted.size - 1) \
            if td_sorted.size > 1 else np.zeros(dev_pos.size, int)
        if td_sorted.size > 1:
            left, right = ins - 1, ins
            pick = np.where(np.abs(times[dev_pos] - td_sorted[left])
                            <= np.abs(times[dev_pos] - td_sorted[right]), left, right)
        else:
            pick = np.zeros(dev_pos.size, int)
        gap = np.abs(times[dev_pos] - td_sorted[pick])
        eligible = gap <= float(tol_s)
        taken = set()
        for k in np.argsort(gap, kind="stable"):
            if not eligible[k]:
                continue
            target = int(td_pos_sorted[pick[k]])
            if target in taken:
                continue
            taken.add(target)
            donor = int(dev_pos[k])
            m = native[donor]
            values[target] = np.where(m, values[donor], values[target])
            tiers[target] = np.where(m, int(BandPowerTier.DEVICE_ONBOARD_SPECTRUM), tiers[target])
            keep[donor] = False
            counts["n_device_rows_merged_into_a_tile"] += 1
        counts["n_device_rows_standing_alone"] = (
            counts["n_device_rows"] - counts["n_device_rows_merged_into_a_tile"])

    counts["n_values_from_device"] = int(
        (tiers[keep] == int(BandPowerTier.DEVICE_ONBOARD_SPECTRUM)).sum())
    counts["n_values_from_time_domain"] = int(
        (tiers[keep] == int(BandPowerTier.TIME_DOMAIN_TRANSFORM)).sum())
    return values[keep], tiers[keep], keep, counts


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
    # WHICH RECIPE PRODUCED THE BAND POWER, and where each value came from. Recorded because the two
    # recipes this module can read are on different number scales -- one is on the device's own
    # scale and the other is not -- so a table of results that did not say which it used could not
    # be compared against a threshold, or against another table.
    band_power_source: str | None = None
    band_half_hz: float | None = None
    #: Band centres that were asked for and are not stored in the cache. Named rather than silently
    #: rounded onto the grid, because neighbouring stored bands overlap by four fifths of their
    #: width and combining them would inflate the answer.
    band_centres_unavailable: tuple = ()
    #: Three-second tiles refused on the cache's own quality flags. A tile flagged saturated or not
    #: usable is dropped, not used, because its value is not a measurement of the brain.
    n_dropped_saturated_tile: int = 0
    n_dropped_unusable_tile: int = 0
    #: How the device's own readings were used: how many there were, how many described the same
    #: moment as a tile and so replaced that tile's values, and how many stood alone.
    n_device_rows: int = 0
    n_device_rows_merged_into_a_tile: int = 0
    n_device_rows_standing_alone: int = 0
    #: Counts over the final table of (row x band), by where each value came from.
    values_by_tier: dict = field(default_factory=dict)
    reason_unusable: str | None = None

    def describe(self) -> str:
        if self.reason_unusable:
            return (f"{self.channel} {self.hemisphere} @{self.rate_hz:g} Hz: UNUSABLE — "
                    f"{self.reason_unusable}")
        tiers = ", ".join(f"{n} values {where}" for where, n in (self.values_by_tier or {}).items()
                          if n)
        return (f"{self.channel} {self.hemisphere} @{self.rate_hz:g} Hz: {self.n_final} windows "
                f"over {len(self.amplitudes)} amplitudes {self.amplitudes}, {self.n_eras} eras "
                f"(joined {self.n_joined} of {self.n_psd_rows}; dropped "
                f"{self.n_dropped_no_epoch} unmatched, {self.n_dropped_stim_off} stim-off, "
                f"{self.n_dropped_other_rate} other-rate"
                + (f", {self.n_dropped_saturated_tile} tiles at the converter's rail, "
                   f"{self.n_dropped_unusable_tile} tiles the cache could not score"
                   if self.n_dropped_saturated_tile or self.n_dropped_unusable_tile else "")
                + f"). Band power came from {self.band_power_source}"
                + (f". Where the numbers came from: {tiers}" if tiers else ""))


def _utc_ns(values):
    """Timestamps as int64 nanoseconds since the epoch, in UTC; a missing value is the minimum int.

    The comparisons below used to run on arrays of Timestamp OBJECTS -- ``to_numpy()`` on a
    timezone-aware series hands back one Python object per row -- so each of the four to five
    million comparisons a request makes went through Python. The integer form compares the same
    instants (two timezone-aware timestamps compare by instant, which is what the integer is) and
    gives the same answer for a missing value: pandas' NaT sorts first in the integer form and
    compares as "not less than" and "not greater than" anything in the object form, and both make
    ``searchsorted`` place it before every epoch and every ``<`` against it false.
    """
    t = pd.to_datetime(pd.Series(values), utc=True)
    return t.to_numpy(dtype="datetime64[ns]").astype("int64")


def _epoch_for_times(times, epochs, *, t_start="t_start", t_end="t_end"):
    """Index of the exposure epoch containing each timestamp, or -1. Half-open [start, end)."""
    ep = epochs.reset_index(drop=True)
    starts = _utc_ns(ep[t_start])
    ends = _utc_ns(ep[t_end])
    tv = _utc_ns(times)
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
#:    flips from False to True in 15 of 18 bands. VERIFIED ACROSS ALL 18 BANDS in both windows on
#:    2026-09-05 after a reviewer caught that the claim had originally been generalised from the
#:    10.5 Hz band alone: the full-record baseline is False in **all 18** bands, the five-era window
#:    is True in 15, and the three that stay False are 25.5, 26.5 and 27.5 Hz. At 10.5 Hz power
#:    RISES from 3.222 to 4.894 across the full-record arms and FALLS from 5.020 to 4.894 on the
#:    recent ones. The full-record capture was inverted because it spanned two programming regimes.
#:
#:    The same table shows the trade in the other direction, which is the part that decides
#:    anything: full-record separation is 1.01 to 4.88 across the bands, comfortably clearing any
#:    plausible floor, while the five-era separation is 0.41 to 0.93. So the two windows fail for
#:    opposite reasons — the long one on direction, the short one on separation — and neither yields
#:    a deployable cell.
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


class _PreparedChannel:
    """One sensing channel's rows, filtered, merged and joined to the epochs; see `build_evidence`."""
    __slots__ = ("p", "ep", "center_cols", "cal_values", "cal_tiers", "audit", "reason")

    def __init__(self):
        self.p = self.ep = None
        self.center_cols = []
        self.cal_values = self.cal_tiers = None
        self.audit = {}
        self.reason = None


def _prepare_channel(psd, epochs, *, channel, time_unit="s", native_tol_s=None):
    """The channel-only half of `build_evidence`, verbatim, returning what the cell half needs.

    `audit` holds the audit fields this half used to set on the cell's audit directly, in the
    order it set them; `reason` is the early-exit reason, when the channel cannot be used at all.
    """
    out = _PreparedChannel()
    aud = out.audit
    p = pd.DataFrame(psd)
    p = p[p["channel"].astype(str) == str(channel)].copy()
    aud["n_psd_rows"] = len(p)
    if not len(p):
        out.reason = f"no rows of sensed signal for channel {channel!r}"
        return out
    p["t_utc"] = _to_utc(p["t"], unit=time_unit)

    # ---- band power already on the device's scale, when the frame carries it ---------------------
    # Two things happen here and nowhere else, because this is the only point where both families of
    # measurement and their quality flags are all present: bad tiles are dropped, and the device's
    # own reading is allowed to win over the value modelled from the raw samples for the same moment
    # and the same band. Everything after this point treats the result as one table of rows.
    center_cols = _cal_center_columns(p)
    cal_values = cal_tiers = None
    if center_cols:
        aud["band_power_source"] = BAND_POWER_FROM_CALIBRATED_CACHE
        # A frame carrying band power on the device's scale must also carry the things that make it
        # readable: which family each row belongs to, the two quality flags, and the band half width
        # and tile length that say what one stored value covers. A hand-built frame with the value
        # columns and none of the rest would otherwise fail somewhere further down with a message
        # about whichever column happened to be reached first.
        companions = ["family", "tile_ok", "tile_saturated", "band_half_hz", "tile_window_s"]
        absent = [c for c in companions if c not in p.columns]
        if absent:
            raise KeyError(f"this frame carries band power on the device's scale but is missing "
                           f"{absent}; build it with frame_from_lsb_cache rather than by hand, so "
                           "that the quality flags and the band width travel with the numbers")
        aud["band_half_hz"] = float(p["band_half_hz"].iloc[0])

        # QUALITY FIRST. The cache flags a tile whose raw samples hit the converter's rail, and a
        # tile it could not score at all. Either way the stored value is not a measurement of the
        # brain, so the tile is dropped rather than used. Dropping happens before the merge so that
        # a bad tile cannot absorb a device reading and hide it.
        fam = p["family"].astype(str).to_numpy()
        is_td = fam == FAMILY_TIME_DOMAIN
        sat = p["tile_saturated"].to_numpy(bool) & is_td
        bad = (~p["tile_ok"].to_numpy(bool)) & is_td & ~sat
        aud["n_dropped_saturated_tile"] = int(sat.sum())
        aud["n_dropped_unusable_tile"] = int(bad.sum())
        p = p[~(sat | bad)].reset_index(drop=True)
        if not len(p):
            out.reason = (f"every tile for channel {channel!r} was refused on the cache's "
                          f"quality flags ({aud['n_dropped_saturated_tile']} saturated, "
                          f"{aud['n_dropped_unusable_tile']} otherwise unusable)")
            return out

        tol = (float(native_tol_s) if native_tol_s is not None
               else float(p["tile_window_s"].iloc[0]) * DEFAULT_NATIVE_TOLERANCE_FRACTION_OF_TILE)
        cal_values, cal_tiers, keep, counts = _merge_device_over_time_domain(
            p, center_cols, tol_s=tol)
        p = p[keep].reset_index(drop=True)
        # A stable position into the two matrices above, so that every filter after this point can
        # subset the rows without the values and the rows drifting out of alignment.
        p["_cal_row"] = np.arange(len(p))
        aud["n_device_rows"] = counts["n_device_rows"]
        aud["n_device_rows_merged_into_a_tile"] = counts["n_device_rows_merged_into_a_tile"]
        aud["n_device_rows_standing_alone"] = counts["n_device_rows_standing_alone"]
    else:
        aud["band_power_source"] = BAND_POWER_FROM_INTEGRATED_DENSITY

    ep = pd.DataFrame(epochs).reset_index(drop=True)
    j = _epoch_for_times(p["t_utc"], ep)
    aud["n_dropped_no_epoch"] = int((j < 0).sum())
    p = p.assign(_ep=j)
    p = p[p._ep >= 0]
    aud["n_joined"] = len(p)
    if not len(p):
        out.reason = "no PSD window falls inside any exposure epoch"
        return out
    out.p, out.ep = p, ep
    out.center_cols, out.cal_values, out.cal_tiers = center_cols, cal_values, cal_tiers
    return out


def build_evidence(psd, epochs, *, channel, hemisphere, rate_hz, bands=None,
                   require_stim_on=True, amp_col=None, era_col="visit", rate_col=None,
                   time_unit="s", mode_requires=None,
                   recent_eras=RECENT_ERAS_FOR_RESPONSE, native_tol_s=None, _prepared=None):
    """One :class:`LfpEvidence` for a single (channel, hemisphere, rate), plus its audit.

    Parameters
    ----------
    psd
        A frame of sensed signal, in either of two shapes, and which one it is decides where band
        power comes from.

        THE ONE TO USE. A frame from :func:`frame_from_lsb_cache`, carrying band power ALREADY ON
        THE DEVICE'S OWN NUMBER SCALE, one column per band centre. Band power is then READ from the
        column whose centre matches the band asked for. Nothing is integrated, nothing is
        exponentiated, and no scale factor is applied anywhere in this module. The device's own
        onboard reading wins over the value modelled from the raw samples wherever it exists for the
        same moment and the same band, and a tile the cache flags as saturated or unusable is
        dropped rather than used.

        THE OLDER ONE, still accepted. A frame with ``t`` (epoch seconds), ``channel``, and either a
        ``psd`` matrix column (raw power, decision 204) or columns named by ``freqs``; band power is
        then built by integrating the density across the band. That quantity is
        proportional to the one the device works in but is NOT on the device's scale, so a value
        from it must never be compared against a threshold programmed in the device's units.

        Which one was used is written into ``band_power_source`` on the audit and on the returned
        evidence, so a table of results always says which recipe produced it.
    native_tol_s
        How close in time the device's own reading has to be to a three-second tile before the two
        are treated as describing the same moment. Left as None it is half a tile, read from the
        tile length the frame carries. Only used with a calibrated frame.
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

    # EVERYTHING THAT DEPENDS ONLY ON THE CHANNEL AND THE EPOCHS is done once per channel and
    # shared across the cells built from the same frame (2026-09-12): the channel filter, the
    # timestamp conversion, the quality filter, the device-over-tile merge and the epoch join.
    # `build_all` hands in a per-call dictionary so the sixteen cells of one channel (two
    # hemispheres, eight rates on RCS08) prepare it once; a direct caller hands nothing and gets
    # exactly the old one-cell path. Nothing after this point writes into the shared frame or the
    # shared matrices: every later step filters into a new frame or reads by index.
    prepared = None if _prepared is None else _prepared.get(str(channel))
    if prepared is None:
        prepared = _prepare_channel(psd, epochs, channel=channel, time_unit=time_unit,
                                    native_tol_s=native_tol_s)
        if _prepared is not None:
            _prepared[str(channel)] = prepared
    for name, value in prepared.audit.items():
        setattr(aud, name, value)
    if prepared.reason is not None:
        aud.reason_unusable = prepared.reason
        return None, aud
    p, ep = prepared.p, prepared.ep
    center_cols, cal_values, cal_tiers = prepared.center_cols, prepared.cal_values, prepared.cal_tiers

    # ONE VALUE PER EPOCH, THEN ONE LOOKUP PER TILE. The amplitude, the rate and the era label are
    # properties of the epoch a tile fell in, so they are read off the epoch table once (about a
    # hundred rows) and spread over the tiles by index. This used to be done the other way round --
    # the epoch rows were first repeated once per tile and the era's month string was then formatted
    # for every one of those tens of thousands of rows, in every one of the ninety-odd cells; that
    # formatting alone was 8.5 s of a 73 s request on RCS08 (2026-09-12). Same strings, same
    # numbers: `ep` carries a fresh 0..n-1 index, so indexing its columns by position is the same
    # lookup `ep.loc[...]` made.
    j = p._ep.to_numpy()
    p = p.assign(amp=pd.to_numeric(ep[amp_col], errors="coerce").to_numpy()[j],
                 rate=pd.to_numeric(ep[rate_col], errors="coerce").to_numpy()[j],
                 era=_derive_era(ep, era_col, aud)[j])

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

    # ONE definition of the adaptive range (review S13, 2026-09-12): `percept_adaptive
    # .ADAPTIVE_LFP_BAND_HZ`, which the gate and Stage 2 read. This line used to look for a
    # `GATE.ADAPTIVE_BAND_HZ` that no module defines and fall through to a literal (8.0, 30.0).
    lo_hz, hi_hz = PA.ADAPTIVE_LFP_BAND_HZ

    bp, tier_of = {}, {}
    if center_cols:
        # READ the stored value for the band. Do not integrate anything, do not add anything up.
        # One stored column IS the whole five-hertz band, so the whole operation is a lookup.
        half = float(aud.band_half_hz)
        stored = np.asarray([c for c, _, _ in center_cols], float)
        rows = p["_cal_row"].to_numpy(int)

        if bands is None:
            # Every stored band that fits ENTIRELY inside the range the device can place a sensing
            # window on. Taking the cache's own centres rather than a grid of our own is what keeps
            # the lookup exact: a centre we invented would fall between two stored bands, and the
            # only ways to serve it would be to round it onto the grid or to combine neighbours,
            # and combining neighbours would count nearly the same signal twice.
            bands = [(float(c), 2.0 * half) for c in stored
                     if c - half >= lo_hz - 1e-9 and c + half <= hi_hz + 1e-9]

        unavailable = []
        for c, w in bands:
            if not np.isclose(float(w), 2.0 * half, atol=1e-6):
                raise ValueError(
                    f"a band {float(w):g} Hz wide was asked for, but the cached bands are "
                    f"{2.0 * half:g} Hz wide ({half:g} Hz either side of the centre). This module "
                    "will not serve a different width from stored values: the stored bands sit one "
                    "hertz apart and so overlap by four fifths of their width, and adding or "
                    "averaging neighbouring bands to make a wider one would count nearly the same "
                    "signal several times over and inflate the result")
            hit = np.flatnonzero(np.isclose(stored, float(c), atol=1e-6))
            if hit.size != 1:
                unavailable.append(float(c))
                continue
            j = int(hit[0])
            bp[(round(float(c), 6), round(float(w), 6))] = cal_values[rows, j]
            tier_of[(round(float(c), 6), round(float(w), 6))] = cal_tiers[rows, j]
        # Named, not rounded onto the grid and not built out of overlapping neighbours.
        aud.band_centres_unavailable = tuple(unavailable)
        if bp:
            used = np.concatenate([t for t in tier_of.values()])
            finite = np.concatenate([np.isfinite(v) for v in bp.values()])
            aud.values_by_tier = {
                TIER_LABELS[BandPowerTier.DEVICE_ONBOARD_SPECTRUM]:
                    int((used == int(BandPowerTier.DEVICE_ONBOARD_SPECTRUM)).sum()),
                TIER_LABELS[BandPowerTier.TIME_DOMAIN_TRANSFORM]:
                    int((used == int(BandPowerTier.TIME_DOMAIN_TRANSFORM)).sum()),
                TIER_LABELS[BandPowerTier.NO_VALUE]: int((~finite).sum())}
        if not bp:
            aud.reason_unusable = (f"none of the requested bands is stored in the cache; asked for "
                                   f"{[float(c) for c, _ in bands]}, stored centres run "
                                   f"{stored.min():g} to {stored.max():g} Hz")
            return None, aud
    else:
        freqs = np.asarray(p["freqs"].iloc[0] if "freqs" in p.columns
                           else p.attrs.get("freqs"), float)
        pm = np.vstack(p["psd"].to_numpy()) if p["psd"].dtype == object \
            else np.asarray(p["psd"].tolist(), float)

        if bands is None:
            centers = np.arange(np.ceil(lo_hz + 2.5), np.floor(hi_hz - 2.5) + 1e-9, 1.0)
            bands = [(float(c), 5.0) for c in centers]

        for c, w in bands:
            v = band_power_linear(pm, freqs, c, w)
            if v is not None:
                bp[(round(float(c), 6), round(float(w), 6))] = v
        if not bp:
            aud.reason_unusable = "no requested band lies inside the PSD frequency axis"
            return None, aud

    kw = {} if mode_requires is None else {"mode_requires": mode_requires}
    ev = GATE.LfpEvidence(amplitude_mA=p["amp"].to_numpy(float), band_power=bp,
                          era=np.asarray(p["era"]), cluster=np.asarray(p["era"]),
                          hemisphere=str(hemisphere), **kw)
    # WHERE EVERY NUMBER CAME FROM, carried on the evidence object itself so that a reader holding
    # only the evidence can tell. These are set as plain attributes rather than as fields of
    # ``LfpEvidence`` because that class lives in ``stage_gate.py``, which this change does not
    # touch; anything reading them should use ``getattr`` with a default.
    ev.band_power_source = aud.band_power_source
    ev.band_power_tier = tier_of
    ev.band_power_tier_labels = dict(TIER_LABELS)
    # The sensing contact this cell was read on (2026-09-12), so the gate's per-side block can
    # name it; same plain-attribute convention as the three above.
    ev.channel = str(channel)
    ev.rate_hz = float(rate_hz)
    ev.laterality = _laterality(channel, hemisphere)
    return ev, aud


def band_era_negative_significant(r) -> bool:
    """Does one band's era-blocked slope fall with amplitude AND clear p < 0.05?

    The confound-ADJUSTED half of "this band responds" (see :func:`screen_cells`): the raw
    capture contrast can fall because time passed rather than because current rose, so the
    slope that has era removed must be negative and significant on its own.
    """
    return bool(np.isfinite(r.slope_p) and r.slope_p < 0.05
                and np.isfinite(r.slope_per_mA) and r.slope_per_mA < 0)


def _centre_key(c) -> float:
    """One spelling of a band centre for set membership: 24.5 and 24.500000001 are one band."""
    return round(float(c), 3)


def _hz_list(centres) -> str:
    return ", ".join(f"{c:g} Hz" for c in sorted(centres))


def cell_response_verdict(results, *, pain_positive_centers) -> dict:
    """THE ONE RULE for "this cell's sensed signal can drive Adaptive Therapy" (decision 199,
    2026-09-17), shared by the readiness screen and the two-stage gate so they cannot disagree.

    A cell is responsive when AT LEAST ONE band both
      (a) FALLS with stimulation current -- a significant NEGATIVE era-blocked slope
          (:func:`band_era_negative_significant`) -- and
      (b) RISES with pain -- its centre is in ``pain_positive_centers``, the band centres whose
          correlation with the pain score on the stored Biomarkers grid is positive and
          established (``routines.pain_relationship``).
    The two signs together are the device's fixed control polarity: more current, less power,
    less pain. The PI's ruling, verbatim: "We literally only need one actual band that meets the
    criteria. What we need is for the band to have a positive relationship with the biomarker and
    a negative relationship with stimulation." The two MAJORITY rules of decision 143 (half the
    bands responding on capture, half carrying the negative slope) are gone; the capture count
    stays on the row as information.

    ``results`` maps each band centre (Hz) to its ``lfp_response.ResponseResult``.
    ``pain_positive_centers`` is the contact's set of centres, EMPTY when the grid has the contact
    and none qualifies, ``None`` when the grid does not know the contact at all -- in which case
    the verdict is NOT ASSESSED (``responds`` None), never a pass: a gate that goes green on
    absence of evidence is unsafe (decision 9).

    Returns the counts (``n_bands``, ``n_responding`` on capture, ``n_era_significant``,
    ``n_era_negative_significant``, ``n_pain_positive`` or None, ``n_qualifying``,
    ``qualifying_centers_hz``), ``responds`` (True / False / None) and ``blocking_reasons``.
    """
    res = dict(results or {})
    n = len(res)
    known = pain_positive_centers is not None
    pain = {_centre_key(c) for c in (pain_positive_centers or ())}
    base = dict(n_bands=n, n_responding=0, n_era_significant=0, n_era_negative_significant=0,
                n_pain_positive=(len(pain) if known else None), n_qualifying=0,
                qualifying_centers_hz=[])
    if n == 0:
        return dict(base, responds=None, blocking_reasons=["no band could be tested"])
    n_resp = sum(1 for r in res.values() if r.responds is True)
    n_sig = sum(1 for r in res.values() if np.isfinite(r.slope_p) and r.slope_p < 0.05)
    falling = sorted(_centre_key(c) for c, r in res.items() if band_era_negative_significant(r))
    scanned = {_centre_key(c) for c in res}
    pain_here = sorted(pain & scanned)
    qualifying = sorted(set(falling) & pain)
    base.update(n_responding=n_resp, n_era_significant=n_sig,
                n_era_negative_significant=len(falling),
                n_pain_positive=(len(pain_here) if known else None),
                n_qualifying=len(qualifying), qualifying_centers_hz=qualifying)
    if not known:
        return dict(base, responds=None, blocking_reasons=[
            "the pain relationship of this contact's bands is not known (no stored Biomarkers "
            "grid carries this contact), so no band can be shown to rise with pain"])
    fails = []
    if not falling:
        fails.append("no band falls with current once the time confound is removed (no "
                     "significant negative era-blocked slope)"
                     + (f"; {n_sig} of {n} are significant in the WRONG direction" if n_sig
                        else ""))
    if not pain_here:
        fails.append("no band on this contact has a supported positive relationship with "
                     "pain on the Biomarkers grid (power rising with pain), which the device's "
                     "control polarity needs")
    if falling and pain_here and not qualifying:
        fails.append("no band both falls with current and rises with pain: falling with "
                     f"current at {_hz_list(falling)}; rising with pain at {_hz_list(pain_here)}")
    return dict(base, responds=(not fails), blocking_reasons=fails)


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


_RING_WORDS = {"ZERO": 0, "ONE": 1, "TWO": 2, "THREE": 3}


def sensing_pair_rings(channel):
    """The two ring numbers of a bipolar sensing channel name (``ZERO_TWO_LEFT`` -> (0, 2)), or
    None when the name does not carry two ring words."""
    words = [w for w in str(channel or "").upper().split("_") if w in _RING_WORDS]
    if len(words) != 2:
        return None
    a, b = _RING_WORDS[words[0]], _RING_WORDS[words[1]]
    return (min(a, b), max(a, b))


def flanking_pair(stim_rings):
    """The one sensing pair the device allows for a set of stimulating rings on a lead: the two
    contacts immediately flanking them -- (1, 3) for contact 2, (0, 2) for contact 1, (0, 3) for
    contacts 1 and 2 together; None for contact 0 or 3 (nothing flanks them), an empty set, or a
    non-contiguous set (decision 217; the three configurations per lead of the BrainSense tip
    card p. 7-8 and the white paper p. 8)."""
    rings = sorted({int(r) for r in (stim_rings or set())})
    if not rings or rings != list(range(rings[0], rings[-1] + 1)):
        return None
    lo, hi = rings[0] - 1, rings[-1] + 1
    return (lo, hi) if 0 <= lo and hi <= 3 else None


def pair_flanks_stimulation(channel, stim_rings):
    """Is this sensing pair the one the device allows with these stimulating rings on its lead?
    None when the pair cannot be read or no stimulating ring is given."""
    pair = sensing_pair_rings(channel)
    if pair is None or not stim_rings:
        return None
    return pair == flanking_pair(stim_rings)


def screen_cells(evidence, *, response_fn, pain_positive_by_channel=None, amp_ceiling=None,
                 stim_rings_by_side=None):
    """Which cells carry evidence that could actually license a closed-loop deployment.

    The rule is :func:`cell_response_verdict` (decision 199): at least one band that falls with
    current once the time confound is removed AND rises with pain on the stored Biomarkers grid.
    ``pain_positive_by_channel`` maps each sensing channel to that set of band centres
    (``routines.pain_relationship.pain_positive_centers_by_channel``); a channel it does not
    carry, or ``None``, leaves every cell of that channel NOT ASSESSED.

    ``amp_ceiling`` optionally refuses a cell whose contrast reaches above the declared hard limit
    (:data:`objective.AMP_HARD_LIMIT_MA`). Left as ``None`` no amplitude condition is applied.

    ``stim_rings_by_side`` maps each lead ("Left", "Right") to the set of ring numbers it
    stimulates on today (from the cathode in force). A cell whose sensing pair is not the pair
    immediately FLANKING its own lead's stimulating contact is refused (decision 217: the device
    offers three configurations per lead -- stimulate on 1 and sense 0-2, on 2 and sense 1-3, on
    1 and 2 and sense 0-3); a lead with no ring given applies no rule and the row says so.

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

    Returns ``(screen_frame, selected_key)``. Cells are ranked by the number of qualifying bands
    then median separation, but ONLY among survivors — a cell that fails a condition is never
    selected on the strength of a large separation.
    """
    rows = []
    for (ch, hemi, rate), ev in (evidence or {}).items():
        band_keys = list(ev.band_power.keys())
        res = {float(c): response_fn(ev.power_for(c, w), ev.amplitude_mA, era=ev.era,
                                     cluster=ev.cluster)
               for (c, w) in band_keys}
        n = len(res) or 1
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
        #
        # THE RULE ITSELF is `cell_response_verdict` (decision 199), shared with the gate so the
        # two cannot disagree; the amplitude-limit condition below is the screen's own, because
        # the gate checks amplitude limits as a separate condition.
        pain = (pain_positive_by_channel or {}).get(str(ch)) if pain_positive_by_channel else None
        v = cell_response_verdict(res, pain_positive_centers=pain)
        n_resp, n_sig, n_sig_neg = v["n_responding"], v["n_era_significant"], \
            v["n_era_negative_significant"]
        seps = [r.separation_d for r in res.values() if np.isfinite(r.separation_d)]
        amps = tuple(sorted(set(np.round(np.asarray(ev.amplitude_mA, float), 3))))
        amp_hi = max(amps) if amps else float("nan")

        cap = float(amp_ceiling) if amp_ceiling is not None else float("inf")
        within_limit = bool(np.isfinite(amp_hi) and amp_hi <= cap + 1e-9)

        fails = list(v["blocking_reasons"])
        sensing_side = _sensing_side(ch)
        rings = (stim_rings_by_side or {}).get(sensing_side) if stim_rings_by_side else None
        flanks = pair_flanks_stimulation(ch, rings) if rings else None
        if flanks is False:
            pair = sensing_pair_rings(ch)
            allowed = flanking_pair(rings)
            stim_txt = " and ".join(str(r) for r in sorted(rings))
            if allowed is None:
                fails.insert(0, f"the {sensing_side.lower()} lead is stimulating on contact {stim_txt}, "
                                f"and no sensing pair flanks that contact; the device offers no sensing "
                                f"configuration on this lead (contralateral sensing is the alternative)")
            else:
                fails.insert(0, f"the {sensing_side.lower()} lead is stimulating on contact {stim_txt}, so "
                                f"the only sensing pair the device allows is {allowed[0]}-{allowed[1]} "
                                f"(the contacts immediately above and below it); this pair is "
                                f"{pair[0]}-{pair[1]}")
        if not within_limit:
            fails.insert(0, f"high arm {amp_hi:.1f} mA exceeds the {cap:.1f} mA hard limit, "
                            "so the response was measured outside the programmable envelope")

        rows.append(dict(channel=ch, hemisphere=hemi, rate_hz=float(rate), n_bands=n,
                         n_responding=n_resp, responding_fraction=round(n_resp / n, 3),
                         n_era_significant=n_sig,
                         n_era_negative_significant=n_sig_neg,
                         n_pain_positive=v["n_pain_positive"],
                         n_qualifying=int(v["n_qualifying"]),
                         qualifying_centers_hz=list(v["qualifying_centers_hz"]),
                         pain_relationship_known=(v["n_pain_positive"] is not None),
                         median_separation_d=(round(float(np.median(seps)), 3) if seps
                                              else float("nan")),
                         amp_low_mA=(min(amps) if amps else float("nan")), amp_high_mA=amp_hi,
                         sensing_side=_sensing_side(ch),
                         laterality=_laterality(ch, hemi),
                         amp_limit_mA=(round(cap, 2) if np.isfinite(cap) else None),
                         within_amp_limit=within_limit,
                         sensing_pair_flanks_stimulation=flanks,
                         deployable=(v["responds"] is True and not fails),
                         blocking_reasons="; ".join(fails)))
    screen = pd.DataFrame(rows)
    if screen.empty:
        return screen, None
    return screen, best_deployable(screen)


def best_deployable(screen, *, hemisphere=None, rate_hz=None, channel=None):
    """The best deployable cell of a screen frame as ``(channel, hemisphere, rate_hz)``, or
    ``None``; optionally restricted to one stimulating side, one rate, one sensing channel.

    The ranking is the screen's and lives here so the gate's per-side selection (review S3,
    2026-09-12) and the screen's own selection cannot differ: IPSILATERAL cells ahead of
    contralateral ones before considering strength of evidence, then the number of qualifying
    bands (falling with current AND rising with pain, decision 199), then median separation. A contralateral pairing (sensing on one side driving stimulation on the
    other) is supported by the device but only once a contralateral sensing configuration has
    been set up, so preferring it on the strength of a slightly better separation would hand back
    a configuration that needs an extra clinical step without saying so. Contralateral cells
    remain in the screen and remain selectable by naming them explicitly through select_for.
    """
    if screen is None or len(screen) == 0 or "deployable" not in screen.columns:
        return None
    ok = screen[screen.deployable.astype(bool)]
    if hemisphere is not None and "hemisphere" in ok.columns:
        ok = ok[ok["hemisphere"].astype(str) == str(hemisphere)]
    if rate_hz is not None and "rate_hz" in ok.columns:
        ok = ok[np.isclose(pd.to_numeric(ok["rate_hz"], errors="coerce"), float(rate_hz))]
    if channel is not None and "channel" in ok.columns:
        ok = ok[ok["channel"].astype(str) == str(channel)]
    if ok.empty:
        return None
    ok = ok.assign(_ipsi=(ok["laterality"] == "ipsilateral").astype(int))
    strength = "n_qualifying" if "n_qualifying" in ok.columns else "responding_fraction"
    best = ok.sort_values(["_ipsi", strength, "median_separation_d"], ascending=False).iloc[0]
    return (best.channel, best.hemisphere, float(best.rate_hz))


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
    prepared = {}          # one prepared frame per channel, shared by that channel's cells
    for ch in chans:
        for h in hemispheres:
            for r in rs:
                ev, aud = build_evidence(p, ep, channel=ch, hemisphere=h, rate_hz=r,
                                         _prepared=prepared, **kw)
                rows.append({**aud.__dict__, "usable": ev is not None,
                             "n_amplitudes": len(aud.amplitudes)})
                if ev is not None:
                    out[(ch, h, float(r))] = ev
    return out, pd.DataFrame(rows)
