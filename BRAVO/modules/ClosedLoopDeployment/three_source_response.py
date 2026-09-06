"""How stimulation current moves band power, measured three separate ways and put side by side.

WHAT THIS FILE IS FOR. The closed-loop deployment page needs to show the person reading it how the
band power it wants to place a threshold on actually behaved when the stimulation current was
turned up. There are three different ways to get a band power out of this device, they come from
three different recordings, and this file computes all three over the same stimulation settings so
they can be read next to each other. It answers "when the current went up, did the band power go up
or down, and do the three ways of measuring it agree", and it answers nothing else. In particular it
does NOT decide whether a band is fit to deploy, it does not pass or fail anything, and no verdict
anywhere in the deployment report is allowed to depend on it. It is there to be informative.

THE THREE WAYS OF GETTING A BAND POWER, and they really are three different recordings:

  1. FROM THE 250-SAMPLES-A-SECOND VOLTAGE TRACE. The device can stream the raw voltage of a sensing
     contact in microvolts. We cut that trace into three second pieces, run the lab's validated
     recipe over each piece, and multiply by the constant that puts the answer into the device's own
     units. The trace carries the whole spectrum, so this route can report every candidate band. The
     pieces are read out of the tile cache that the biomarker exploration page already builds
     (Biomarkers.routines.availability.raw_lsb_spectrum_cache); nothing here recomputes them.

  2. FROM THE DEVICE'S OWN SPECTRUM. The device can also run its own spectrum calculation on board
     and hand back the result, either as a snapshot when the patient presses the button or as a
     survey of the contacts. We add up the squared magnitude inside the band and multiply by the
     constant for that route. This also carries the whole spectrum. Same tile cache, different
     family inside it.

  3. FROM THE DEVICE'S OWN BAND POWER, WITH NO CONVERSION AT ALL. While the device streams, it also
     reports the band power it computed on board for the one band it was programmed to sense, about
     twice a second, with the stimulation current of each side written next to it on the same clock.
     Nothing is converted, so nothing can be mis-converted. This is the reference wherever it exists,
     and it exists for one band only, which is a fact about the device and not a gap in our data.

FIVE THINGS THAT ARE TRUE OF THIS MEASUREMENT AND STAY TRUE IN THE CODE. The PI read these on
2026-09-06 and accepted all five, so they are stated once here rather than argued on the figures.

  (a) The device's own band power exists for the single band it was programmed to sense, and for no
      other band. Route 3 therefore covers one band while routes 1 and 2 cover the whole spectrum.
      The code reports which band that was and how many samples it has, and the layout treats the
      one-band shape as the structure of the measurement rather than as missing data.
  (b) The three routes are not three independent measurements. The device computes its own band
      power on board from the very voltage trace that route 1 reads, so routes 1 and 3 are the same
      recording seen two ways. The contact surveys carry their own voltage trace and are where the
      spectrum-to-device-units constant was fitted in the first place, so route 2 can never be
      treated as an independent user of that constant. Agreement between the three panels is a check
      that the conversion is behaving, NOT three confirmations that stimulation moved the brain.
  (c) The conversion into device units was checked only between about 8 and 28 Hz, against nine
      sensing centres from 7.8 to 28.3 Hz. Inside 9 to 28 Hz the constant runs from 258 to 317 units
      per squared microvolt, and 26.4 Hz sits at 317, about 18 per cent above the pooled value.
      Outside 8 to 28 Hz routes 1 and 2 are extrapolating, and every row this file emits says whether
      its band is inside the checked range. Route 3 converts nothing and so needs no checked range.
  (d) WORDING NOTE, and it is a scientific point rather than a style one. A band is marked here when
      it CONTAINS a frequency at which a whole multiple of the stimulation rate reappears after the
      device's sampling folds anything above half the sampling rate back down. That is arithmetic and
      is safe to assert. It is NOT safe to assert that such a band is therefore measuring the
      stimulator rather than the brain, and this module used to say exactly that until the PI
      corrected it on 2026-09-06. His argument: a stimulation artefact grows with current and keeps
      growing -- on RCS08's 2026-08-18 visit the bands containing 55 Hz itself rise monotonically to
      18.2 times their starting value -- whereas the marked bands in the 22-30 Hz range rise and then
      FALL, peaking near 1.8 mA. Something that comes back down is not that artefact. A separate
      claim of mine, that the affected bands split cleanly along the landing frequencies, was also
      wrong: the curvature p-values run smoothly across frequency, so the apparent split was only
      where a 0.05 cutoff crossed a continuous gradient. So the mark means "a folded landing lies
      inside this band, treat its amplitude response with care", and nothing stronger.

  (e) Some bands carry a folded multiple of the stimulation rate. The stimulator puts out energy
      at its own rate and at whole multiples of it, and anything above half the sampling rate folds
      back down into the recorded spectrum. Those bands are marked on every panel and in every row.
      The marking is a data label, not an opinion: before it was there, the largest apparent effect
      on a heat map of this record was the stimulation artifact, reaching 45506 device units and
      18.2 times its starting value, and it looked exactly like a spectacular biomarker. The landings
      come from Biomarkers.routines.analytics.harmonic_landings_hz through
      ClosedLoopDeployment.clinic_steps.amplitude_response_band_mask; the folding is not
      reimplemented here.
  (e) Band power is not a straight line in current, and a measurement taken while the current is
      moving is measuring the move. The settled level is the quantity of interest. Every number this
      file emits is an average over settled recording only, taken from the thirty seconds
      immediately before the next increase in current, and only along a run of increases. When the
      current falls, and especially when it falls to zero, that run has ended and the window is not
      carried across the break. Routes 1 and 2 get this from
      StimOptimizer.routines.within_visit.mean_power_before_next_change, which is the PI's rule
      already written down. Route 3 can do better because it carries the current itself, so it also
      requires the device's own record to show the current standing still across the whole window.

WHY THERE IS NO LOGARITHM ANYWHERE IN HERE. The device forms a band power by adding up squared
magnitude across the band and compares it against a threshold typed in those same units. It never
takes a logarithm, so neither do we: every number that leaves this file is in the device's own
units, and a reader can compare it against a threshold without doing arithmetic in their head.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

import numpy as np
import pandas as pd

from Biomarkers.routines import analytics
from . import clinic_steps
from StimOptimizer.routines import within_visit


# -------------------------------------------------------------------------------------------------
# Names the three routes are known by, everywhere. One spelling, used by the payload, the CSV, the
# figures and the tests, so a panel and a table can never disagree about which route they are showing.
# -------------------------------------------------------------------------------------------------
SOURCE_TIME_DOMAIN = "time domain voltage trace"
SOURCE_DEVICE_SPECTRUM = "device's own spectrum"
SOURCE_DEVICE_BAND_POWER = "device's own band power"

SOURCE_ORDER = (SOURCE_TIME_DOMAIN, SOURCE_DEVICE_SPECTRUM, SOURCE_DEVICE_BAND_POWER)

#: What each route had to be multiplied by to reach the device's own units, for the record. Route 3
#: is not converted at all, which is why it is None rather than 1.0 -- a 1.0 would suggest someone
#: chose a scale factor and happened to pick one, and nobody did.
SOURCE_CONVERSION = {
    SOURCE_TIME_DOMAIN: analytics.LSB_PER_UV2_TRANSFORM,
    SOURCE_DEVICE_SPECTRUM: analytics.LSB_PER_DEVICE_PSD,
    SOURCE_DEVICE_BAND_POWER: None,
}

#: Whether a route covers the whole spectrum or only the one band the device was programmed to sense.
SOURCE_COVERS_WHOLE_SPECTRUM = {
    SOURCE_TIME_DOMAIN: True,
    SOURCE_DEVICE_SPECTRUM: True,
    SOURCE_DEVICE_BAND_POWER: False,
}

#: Half-width of a band, in hertz. Taken from clinic_steps rather than written again here, because a
#: second copy of this number is how the two files would come to disagree about what a band is.
BAND_HALF_HZ = clinic_steps.BAND_HALF_HZ

#: The range over which the conversion into device units was actually checked, in hertz: 7.8 to 28.3,
#: the lowest and highest centre the device happened to sense during the paired recordings the
#: conversion was fitted on. Read from analytics so this file cannot drift from the constants it is
#: describing, and deliberately NOT the 30 hertz figure that also appears there -- 30 is the highest
#: place the firmware will let an adaptive sensing band sit, which is a fact about the device, while
#: 28.3 is the highest place we have data to check the conversion at, which is a fact about our
#: recordings. Using the device limit here would claim a check we never ran.
CHECKED_LO_HZ = float(analytics.LSB_VALIDATED_HZ_LO)
CHECKED_HI_HZ = float(analytics.LSB_VALIDATED_HZ_HI)

#: How long to wait, after the device's own record shows the current has stopped moving, before
#: believing the band power. Five seconds, and it is measured rather than assumed. On the RCS08
#: record of 2026-08-18, averaging the device's own band power in five second slices after the last
#: current change and dividing by the level it eventually settled at gave, on the right side at
#: 7.81 Hz, 1.32 in the first five seconds and 1.03 or below from five seconds on, across nine holds
#: of at least forty seconds; on the left side at 23.44 Hz the first five seconds gave 1.01 across
#: fourteen holds, so no excursion was resolvable there at all. Twenty four holds on one visit is
#: thin, and the honest reading is that the excursion is short rather than that it is exactly five
#: seconds long. It matters little in practice: the settings on that visit were held about sixty
#: seconds, so the thirty second window before the next change already sits well clear of it.
DEVICE_SETTLE_AFTER_CURRENT_STOPS_S = 5.0

#: What fraction of the samples a thirty second window could hold must actually be there before the
#: device's own band power is averaged. Two thirds. At about two samples a second a thirty second
#: window holds about sixty, so this asks for about forty. It is the same intent as the ten-pieces-
#: out-of-ten rule the other two routes use, written for a stream that samples fifteen times faster.
DEVICE_MIN_SAMPLE_FRACTION = 2.0 / 3.0


# -------------------------------------------------------------------------------------------------
# Reading the device's own band power (route 3) out of the stored streaming recordings
# -------------------------------------------------------------------------------------------------
def read_device_band_power(power_domain_recordings) -> Dict[str, Dict[str, Any]]:
    """Pull the device's own band power, and the current beside it, out of the streaming records.

    These are the ``MedtronicBrainSensePowerDomain`` recordings, which is where the platform stores
    ``BrainSenseLfp.LfpData``. Each recording holds a column of band power and a column of
    stimulation current per hemisphere, sampled together at about two samples a second, so the
    current and the power it produced share one clock and there is no matching to get wrong.

    Returns one entry per sensing contact, keyed by the contact name the rest of the platform uses::

        {"ONE_THREE_LEFT": {"t": [epoch seconds], "power": [device units], "mA": [milliamps],
                            "centre_hz": float, "rate_hz": float, "averaging_s": float,
                            "n_samples": int, "n_recordings": int}}

    The band power is exactly what the device reported. Nothing is scaled, nothing is converted and
    no logarithm is taken, which is the whole reason this route is worth having.
    """
    out: Dict[str, Dict[str, Any]] = {}
    for rec in (power_domain_recordings or []):
        if not isinstance(rec, dict):
            continue
        names = list(rec.get("ChannelNames") or [])
        data = np.asarray(rec.get("Data"), dtype=float)
        if data.ndim != 2 or not names:
            continue
        if data.shape[0] == len(names) and data.shape[1] != len(names):
            data = data.T
        try:
            t0 = float(rec.get("StartTime"))
            fs = float(rec.get("SamplingRate") or 0.0)
        except (TypeError, ValueError):
            continue
        if not np.isfinite(t0) or not np.isfinite(fs) or fs <= 0:
            continue
        t = t0 + np.arange(data.shape[0], dtype=float) / fs
        therapy = (rec.get("Descriptor") or {}).get("Therapy") or {}

        # The columns are named "<CONTACT> Power" and "<CONTACT> Stimulation". Pair them by contact
        # rather than by position, because a recording that carries only one hemisphere would put the
        # columns somewhere else and a positional read would silently take the wrong one.
        power_cols = {n[: -len(" Power")]: i for i, n in enumerate(names) if n.endswith(" Power")}
        stim_cols = {n[: -len(" Stimulation")]: i for i, n in enumerate(names)
                     if n.endswith(" Stimulation")}
        for contact, ip in power_cols.items():
            if contact not in stim_cols or ip >= data.shape[1]:
                continue
            ia = stim_cols[contact]
            if ia >= data.shape[1]:
                continue
            side = "Left" if contact.endswith("LEFT") else ("Right" if contact.endswith("RIGHT")
                                                            else None)
            hemi = therapy.get(side) or {} if side else {}
            entry = out.setdefault(contact, {"t": [], "power": [], "mA": [], "centre_hz": [],
                                             "rate_hz": [], "averaging_s": [],
                                             "hemisphere": side, "n_recordings": 0})
            entry["t"].append(t)
            entry["power"].append(data[:, ip])
            entry["mA"].append(data[:, ia])
            entry["n_recordings"] += 1
            # The band the device was sensing, the rate it was stimulating at and how long it
            # averaged over are recorded PER SAMPLE rather than once per contact. They are settings
            # a clinician can change between one streaming session and the next, and this record
            # shows them doing exactly that: the right 0-3 contact was sensed at 10.74 hertz in some
            # sessions and 7.81 hertz in others. Keeping one value per contact would report whichever
            # session happened to be read first and quietly mislabel every other one.
            n_here = data.shape[0]
            for key, src, scale in (("centre_hz", "FrequencyInHertz", 1.0),
                                    ("rate_hz", "RateInHertz", 1.0),
                                    ("averaging_s", "AveragingDurationInMilliSeconds", 1e-3)):
                v = hemi.get(src)
                try:
                    v = float(v) * scale if v is not None else np.nan
                except (TypeError, ValueError):
                    v = np.nan
                entry[key].append(np.full(n_here, v, dtype=float))

    # Sort each contact's samples into time order and glue the recordings together. Sorting matters:
    # the recordings come back from the store in whatever order the files were ingested, and a
    # window search over an unsorted clock finds the wrong samples without complaining.
    for contact, entry in out.items():
        cat = {k: (np.concatenate(entry[k]) if entry[k] else np.empty(0))
               for k in ("t", "power", "mA", "centre_hz", "rate_hz", "averaging_s")}
        order = np.argsort(cat["t"], kind="stable")
        for k, v in cat.items():
            entry[k] = v[order]
        entry["n_samples"] = int(cat["t"].size)
    return out


def device_band_power_in_window(entry, t_lo, t_hi):
    """Cut one contact's device band power down to a stretch of time, and say what it was sensing.

    Everything a panel says about this route has to describe the stretch of rising current being
    shown, not the whole recording history. Reporting a whole-history sample count beside one run's
    numbers would tell a reader the route is well covered here when it may have almost nothing here.

    Returns None when the stretch holds no samples, and raises when the band the device was sensing
    CHANGED inside the stretch, because two different bands averaged together would be reported as
    one band, and that is a quieter and worse failure than an empty panel.
    """
    if not entry or int(entry.get("n_samples") or 0) == 0:
        return None
    t = np.asarray(entry["t"], dtype=float)
    m = (t >= float(t_lo)) & (t < float(t_hi))
    if not m.any():
        return None
    out = {k: np.asarray(entry[k], dtype=float)[m] for k in ("t", "power", "mA")}
    for k in ("centre_hz", "rate_hz", "averaging_s"):
        v = np.asarray(entry[k], dtype=float)[m]
        v = v[np.isfinite(v)]
        u = np.unique(np.round(v, 6))
        if k == "centre_hz" and u.size > 1:
            raise ValueError(
                f"the device was sensing more than one band during this stretch "
                f"({', '.join(f'{x:g}' for x in u)} hertz), so its band power cannot be reported "
                f"as one band's")
        out[k] = float(u[0]) if u.size else None
    out["hemisphere"] = entry.get("hemisphere")
    out["n_samples"] = int(m.sum())
    out["n_samples_whole_record"] = int(t.size)
    return out


def settled_device_band_power(step_t0, step_end_t, current_mA, sample_t, sample_power, sample_mA, *,
                              window_s=within_visit.PRE_CHANGE_WINDOW_S,
                              settle_s=DEVICE_SETTLE_AFTER_CURRENT_STOPS_S,
                              min_fraction=DEVICE_MIN_SAMPLE_FRACTION,
                              block=None, require_rise_into_setting=True):
    """The settled level of the device's own band power, one number per stimulation setting.

    This is the same rule the other two routes follow -- average the last ``window_s`` seconds before
    the next increase in current, and only along a run of increases -- with one extra requirement
    that only this route can check. Because the device writes the current next to the power on the
    same clock, we can insist that the device's OWN record shows the current standing still across
    the whole window, and that it stopped moving at least ``settle_s`` seconds before the window
    opened. A setting whose window fails either test gets no number and a plain reason.

    ``sample_power`` is the device's band power for one sensing contact and ``sample_mA`` the current
    of the side being ramped, both sampled on the same clock as ``sample_t``. Nothing is converted
    and no logarithm is taken; the numbers come out in the units the device reported.

    Returns ``(power, table)``. ``power`` is one value per setting, missing where the setting was
    refused. ``table`` carries the current, the window used, the sample count, whether the setting
    was accepted and, when it was not, why not.
    """
    t0 = np.asarray(step_t0, dtype=float)
    amp = np.asarray(current_mA, dtype=float)
    st = np.asarray(sample_t, dtype=float)
    sp = np.asarray(sample_power, dtype=float)
    sa = np.asarray(sample_mA, dtype=float)
    n = t0.size
    if amp.size != n:
        raise ValueError(f"step_t0 has {n} entries but current_mA has {amp.size}")
    if not (st.size == sp.size == sa.size):
        raise ValueError(f"the device's time, power and current arrays must be the same length; "
                         f"got {st.size}, {sp.size}, {sa.size}")
    if st.size and np.any(np.diff(st) < 0):
        raise ValueError("sample_t must be sorted ascending")

    up_from_previous, _ = within_visit.rising_current_settings(amp, block)
    t_end = np.asarray(step_end_t, dtype=float)
    if t_end.size != n:
        raise ValueError("step_end_t must have one entry per setting")

    # The moment the current last moved, per sample, from the device's own record. A sample whose
    # current differs from the one before it marks a move; carrying that time forward tells us, for
    # any instant, how long the current has been standing still.
    if st.size:
        moved = np.zeros(st.size, dtype=bool)
        moved[0] = True
        moved[1:] = sa[1:] != sa[:-1]
        last_move_t = np.maximum.accumulate(np.where(moved, st, -np.inf))
    else:
        last_move_t = np.empty(0)

    want = float(window_s)
    power = np.full(n, np.nan)
    rows = []
    for i in range(n):
        lo = max(t_end[i] - want, t0[i]) if np.isfinite(t_end[i]) else np.nan
        sel = ((st >= lo) & (st < t_end[i])) if np.isfinite(lo) else np.zeros(st.size, dtype=bool)
        n_found = int(sel.sum())
        n_wanted = int(round(want * _sample_rate(st))) if st.size > 1 else 0
        need = max(1, int(np.ceil(float(min_fraction) * n_wanted))) if n_wanted else 1

        reason = ""
        if require_rise_into_setting and not up_from_previous[i]:
            reason = ("the current did not go up to reach this setting, so the thirty seconds "
                      "would mix this setting with the higher or equal current before it")
        elif not np.isfinite(t_end[i]):
            reason = ("the moment the current was next changed is not known, so there is no "
                      "thirty second window that is certain to sit inside this setting")
        elif n_found < need:
            reason = (f"the device reported only {n_found} samples of its own band power in the "
                      f"{want:g} seconds before the next current change, and {need} are required")
        else:
            held = sa[sel]
            if np.unique(held).size > 1:
                reason = ("the device's own record shows the current moving during the thirty "
                          "seconds, so those seconds do not describe one current")
            elif float(st[sel].min() - last_move_t[sel][0]) < float(settle_s):
                reason = (f"the device's own record shows the current stopped moving less than "
                          f"{float(settle_s):g} seconds before the window opened, so the band "
                          f"power may still be settling")
            else:
                power[i] = float(np.nanmean(sp[sel]))

        rows.append({"current_mA": float(amp[i]) if np.isfinite(amp[i]) else None,
                     "window_start_epoch_s": float(lo) if np.isfinite(lo) else None,
                     "window_end_epoch_s": float(t_end[i]) if np.isfinite(t_end[i]) else None,
                     "n_pieces_averaged": n_found,
                     "current_went_up_into_this_setting": bool(up_from_previous[i]),
                     "accepted": bool(np.isfinite(power[i])),
                     "why_not_used": reason})
    return power, pd.DataFrame(rows)


def _sample_rate(t):
    """Samples a second, from the spacing the recording actually has rather than from a constant."""
    t = np.asarray(t, dtype=float)
    if t.size < 2:
        return 0.0
    dt = np.median(np.diff(t))
    return float(1.0 / dt) if np.isfinite(dt) and dt > 0 else 0.0


# -------------------------------------------------------------------------------------------------
# The comparison itself
# -------------------------------------------------------------------------------------------------
@dataclass
class SourcePanel:
    """Everything one of the three panels needs, or the plain reason it has nothing to show."""

    source: str
    covers_whole_spectrum: bool
    conversion_into_device_units: Optional[float]
    #: Settings that produced a number, in the order the current went up.
    current_mA: List[float] = field(default_factory=list)
    #: The settled band power at the band being compared, in the device's own units.
    settled_power: List[Optional[float]] = field(default_factory=list)
    #: How many pieces of recording each of those averages rests on.
    n_pieces: List[int] = field(default_factory=list)
    #: The band the comparison is made at, and how far it sits from the band the device was sensing.
    band_centre_hz: Optional[float] = None
    band_lo_hz: Optional[float] = None
    band_hi_hz: Optional[float] = None
    offset_from_programmed_centre_hz: Optional[float] = None
    band_is_measuring_the_stimulator: Optional[bool] = None
    band_inside_checked_conversion_range: Optional[bool] = None
    #: The whole spectrum, for the routes that have one: settings down the rows, bands across.
    spectrum_centres_hz: List[float] = field(default_factory=list)
    spectrum_power: List[List[Optional[float]]] = field(default_factory=list)
    spectrum_band_is_measuring_the_stimulator: List[bool] = field(default_factory=list)
    #: How much recording this route had before any of the settling rules were applied. All three
    #: counts describe THIS run of rising current, never the whole recording history.
    n_pieces_available_in_visit: int = 0
    n_pieces_in_run_before_quality_checks: int = 0
    n_pieces_dropped_for_quality: int = 0
    n_settings_offered: int = 0
    n_settings_used: int = 0
    #: Every stimulation setting this route was offered, whether or not it produced a number, each
    #: with the plain reason it was refused. A route that simply omitted its refusals would let a
    #: reader believe the settings it shows are all the settings there were.
    settings: List[Dict[str, Any]] = field(default_factory=list)
    #: How long one averaged piece of recording is, in seconds, and what a piece is for this route.
    #: The two converted routes average three second pieces of the voltage trace; the device's own
    #: band power arrives about twice a second, each sample already an average over three seconds of
    #: signal, so a count of 60 there and a count of 10 in the first panel describe the same
    #: thirty seconds and must not be read as one route having six times the evidence.
    piece_length_s: Optional[float] = None
    piece_description: Optional[str] = None
    #: Set when the route has nothing to show, and it says WHY rather than leaving a blank panel.
    absent_reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source,
            "covers_whole_spectrum": self.covers_whole_spectrum,
            "conversion_into_device_units": self.conversion_into_device_units,
            "current_mA": self.current_mA,
            "settled_power": self.settled_power,
            "n_pieces": self.n_pieces,
            "band_centre_hz": self.band_centre_hz,
            "band_lo_hz": self.band_lo_hz,
            "band_hi_hz": self.band_hi_hz,
            "offset_from_programmed_centre_hz": self.offset_from_programmed_centre_hz,
            "band_is_measuring_the_stimulator": self.band_is_measuring_the_stimulator,
            "band_inside_checked_conversion_range": self.band_inside_checked_conversion_range,
            "spectrum_centres_hz": self.spectrum_centres_hz,
            "spectrum_power": self.spectrum_power,
            "spectrum_band_is_measuring_the_stimulator":
                self.spectrum_band_is_measuring_the_stimulator,
            "n_pieces_available_in_visit": self.n_pieces_available_in_visit,
            "n_pieces_in_run_before_quality_checks": self.n_pieces_in_run_before_quality_checks,
            "n_pieces_dropped_for_quality": self.n_pieces_dropped_for_quality,
            "settings": self.settings,
            "piece_length_s": self.piece_length_s,
            "piece_description": self.piece_description,
            "n_settings_offered": self.n_settings_offered,
            "n_settings_used": self.n_settings_used,
            "absent_reason": self.absent_reason,
        }


@dataclass
class ThreeSourceComparison:
    """The three panels for one run of rising current on one side, plus what a reader needs to know."""

    label: str
    ramped_side: str
    sensing_contact: str
    programmed_centre_hz: Optional[float]
    stimulation_rate_hz: Optional[float]
    visit_date: str
    window_start_local: str
    window_end_local: str
    current_from_mA: Optional[float]
    current_to_mA: Optional[float]
    n_settings: int
    settled_window_s: float
    panels: List[SourcePanel] = field(default_factory=list)
    bands_measuring_the_stimulator_hz: List[float] = field(default_factory=list)
    stimulator_landings_hz: List[float] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "label": self.label,
            "ramped_side": self.ramped_side,
            "sensing_contact": self.sensing_contact,
            "programmed_centre_hz": self.programmed_centre_hz,
            "stimulation_rate_hz": self.stimulation_rate_hz,
            "visit_date": self.visit_date,
            "window_start_local": self.window_start_local,
            "window_end_local": self.window_end_local,
            "current_from_mA": self.current_from_mA,
            "current_to_mA": self.current_to_mA,
            "n_settings": self.n_settings,
            "settled_window_s": self.settled_window_s,
            "panels": [p.to_dict() for p in self.panels],
            "bands_measuring_the_stimulator_hz": self.bands_measuring_the_stimulator_hz,
            "stimulator_landings_hz": self.stimulator_landings_hz,
            "notes": self.notes,
        }


#: How long a pause in current changes has to be before the device is taken to have ARRIVED at a
#: setting rather than to be still on its way there. Twenty seconds, and it comes from the record:
#: the device does not jump to a programmed current, it walks there in 0.1 mA increments, so a
#: clinician's single "2.0 mA" step appears in the device's own log as five or ten changes a second
#: or two apart. Reading each of those as a setting of its own would produce settings that were held
#: for a second and were never held at all. The RCS08 clinic ladders hold each setting for about
#: sixty seconds, so twenty seconds separates "still moving" from "arrived" with room to spare on
#: both sides.
DEVICE_MOVE_GAP_S = 20.0


def read_device_current(power_domain_recordings):
    """The stimulation current of both sides, as the device itself recorded it, twice a second.

    This is the cleanest record of what current was running in this whole study, and it is the one
    the device wrote down while it was measuring. The clinic testing sheets record what the clinician
    MEANT to set and when they wrote it down; this records what the device delivered, on the same
    clock as the band power it reported. Where the two disagree, this is the one to believe about
    timing.

    Returns ``{"blocks": [{"t": [...], "mA": {contact: [...]}}], "contacts": [...]}`` -- one block
    per streaming recording, because the clock is continuous inside a recording and not across the
    gap between two of them, and a run of rising current must never be assembled across such a gap.
    """
    blocks = []
    contacts = set()
    for rec in (power_domain_recordings or []):
        if not isinstance(rec, dict):
            continue
        names = list(rec.get("ChannelNames") or [])
        data = np.asarray(rec.get("Data"), dtype=float)
        if data.ndim != 2 or not names:
            continue
        if data.shape[0] == len(names) and data.shape[1] != len(names):
            data = data.T
        try:
            t0, fs = float(rec.get("StartTime")), float(rec.get("SamplingRate") or 0.0)
        except (TypeError, ValueError):
            continue
        if not np.isfinite(t0) or fs <= 0:
            continue
        cols = {n[: -len(" Stimulation")]: i for i, n in enumerate(names)
                if n.endswith(" Stimulation") and i < data.shape[1]}
        if not cols:
            continue
        contacts |= set(cols)
        blocks.append({"t": t0 + np.arange(data.shape[0], dtype=float) / fs,
                       "mA": {c: data[:, i] for c, i in cols.items()}})
    blocks.sort(key=lambda b: float(b["t"][0]) if len(b["t"]) else np.inf)
    return {"blocks": blocks, "contacts": sorted(contacts)}


def find_single_side_runs_from_device(current_record, *, min_settings=3,
                                      move_gap_s=DEVICE_MOVE_GAP_S):
    """Find the runs of rising current on ONE side, from the device's own current record.

    Same question as :func:`find_single_side_runs` and the same answer shape, asked of the device's
    own log instead of the clinic testing sheet. This is the version the server uses, because the
    sheets are a spreadsheet a human keeps and the server has no copy of them, while the device's log
    is in the database already.

    A SETTING is the stretch between the moment the device stopped moving the current and the moment
    it started moving it again. The current it settled at is the current at the end of that move.
    Because the device walks to a new current in small increments, the moves themselves are grouped:
    changes less than ``move_gap_s`` apart are one move, not several settings.

    A RUN is a sequence of settings, inside one recording, on which one side's current rises step by
    step while the other side stays at zero throughout. Those are the only stretches in which a
    change in band power can be attributed to one side. When both sides carry current, the run ends,
    and when the current falls the run ends, so no window is ever carried across a break.
    """
    runs = []
    for block in (current_record or {}).get("blocks", []):
        t = np.asarray(block["t"], dtype=float)
        if t.size < 3:
            continue
        by = {c: np.asarray(v, dtype=float) for c, v in block["mA"].items()}
        left = [c for c in by if c.endswith("LEFT")]
        right = [c for c in by if c.endswith("RIGHT")]
        if not left or not right:
            continue
        aL, aR = by[left[0]], by[right[0]]

        # Every instant at which either side's current changed, grouped into moves.
        changed = np.where((np.diff(aL) != 0) | (np.diff(aR) != 0))[0] + 1
        if changed.size == 0:
            continue
        move_end_idx = [c for k, c in enumerate(changed)
                        if k == len(changed) - 1 or (t[changed[k + 1]] - t[c]) > float(move_gap_s)]
        # A setting starts when a move ends and ends when the next move starts.
        move_start_of = {}
        for k, c in enumerate(changed):
            if k == 0 or (t[c] - t[changed[k - 1]]) > float(move_gap_s):
                move_start_of[c] = True
        starts = [c for c in changed if move_start_of.get(c)]

        settings = []
        for e in move_end_idx:
            later = [s for s in starts if t[s] > t[e] + 1e-9]
            # When there is no later move, the setting ran to the end of the recording. Its settled
            # window is then the last stretch of constant current before the device stopped
            # streaming, which is the same quantity as the stretch before a next increase: the
            # current was standing still throughout either way. Leaving it empty instead would throw
            # away the highest current of every run that ended with the recording, which on this
            # record is most of them.
            t_end = float(t[later[0]]) if later else float(t[-1])
            settings.append({"t0": float(t[e]), "t_end": t_end,
                             "left_mA": float(aL[e]), "right_mA": float(aR[e])})
        if not settings:
            continue

        def side_of(st):
            if st["left_mA"] > 0 and st["right_mA"] == 0:
                return "Left"
            if st["right_mA"] > 0 and st["left_mA"] == 0:
                return "Right"
            if st["left_mA"] == 0 and st["right_mA"] == 0:
                return "both at zero"
            return None

        i = 0
        while i < len(settings):
            side = side_of(settings[i])
            if side in (None, "both at zero"):
                i += 1
                continue
            j = i
            while j + 1 < len(settings) and side_of(settings[j + 1]) == side:
                j += 1
            lo = i - 1 if (i > 0 and side_of(settings[i - 1]) == "both at zero") else i
            chunk = settings[lo:j + 1]
            amp = np.array([(st["left_mA"] if side == "Left" else st["right_mA"])
                            for st in chunk], dtype=float)
            if int((amp > 0).sum()) >= int(min_settings):
                label = f"{side} run {len(runs) + 1}"
                runs.append({
                    "side": side,
                    "steps": pd.DataFrame({
                        "t0": [st["t0"] for st in chunk],
                        "t_end": [st["t_end"] for st in chunk],
                        "current_mA": amp,
                        "block": [label] * len(chunk)}),
                    "n_settings": int((amp > 0).sum()),
                    "current_from_mA": _lowest_positive(amp),
                    "current_to_mA": float(np.nanmax(amp)),
                    "source_of_the_ladder": "the device's own per-sample current record",
                })
            i = j + 1
    return runs


def find_single_side_runs(steps, *, rate_hz=None, min_settings=3):
    """Find the stretches where ONE stimulator was turned up while the other sat at zero.

    This is the only kind of stretch in which a change in band power can be put down to one side.
    When both stimulators are running, a change could have come from either, and no arrangement of
    the arithmetic afterwards can separate them, so those stretches are reported and then left out.

    ``steps`` is the parsed clinic testing sheet: one row per stimulation setting, in time order,
    with ``t_local`` the wall-clock moment the setting started, ``amp_mA_Left`` and ``amp_mA_Right``
    the currents, and ``rate_hz`` the stimulation rate. Rows with no current recorded end a stretch,
    because we do not know what was running during them.

    Returns a list of runs. Each run carries a ``steps`` table ready for :func:`build_comparison`,
    with ``t0`` the moment each setting started, ``t_end`` the moment the next one started,
    ``current_mA`` the current of the side that was being turned up, and ``block`` a label that the
    rise test must not look across. The row that ends the run is kept in the table so the last real
    setting has a known end; it carries no current of its own and is refused on that basis.
    """
    df = steps.copy()
    if rate_hz is not None:
        df = df[df["rate_hz"] == float(rate_hz)]
    df = df.sort_values("t_local").reset_index(drop=True)
    if df.empty:
        return []
    t0 = pd.to_datetime(df["t_local"]).dt.tz_localize("America/Los_Angeles")
    df["t0"] = t0.astype("int64").to_numpy() / 1e9
    L = pd.to_numeric(df["amp_mA_Left"], errors="coerce").to_numpy(dtype=float)
    R = pd.to_numeric(df["amp_mA_Right"], errors="coerce").to_numpy(dtype=float)

    def side_of(i):
        """Which side, if either, is the only one delivering current in this setting."""
        if not np.isfinite(L[i]) or not np.isfinite(R[i]):
            return None
        if L[i] > 0 and R[i] == 0:
            return "Left"
        if R[i] > 0 and L[i] == 0:
            return "Right"
        if L[i] == 0 and R[i] == 0:
            return "both at zero"
        return None

    runs = []
    i = 0
    while i < len(df):
        side = side_of(i)
        if side in (None, "both at zero"):
            i += 1
            continue
        j = i
        while j + 1 < len(df) and side_of(j + 1) == side:
            j += 1
        # Reach one setting back to pick up a zero-current row, so the first rise of the run is a
        # rise the record actually shows rather than one we assumed happened.
        start = i - 1 if (i > 0 and side_of(i - 1) == "both at zero") else i
        # Reach one setting forward so the last real setting has a known end.
        stop = min(j + 1, len(df) - 1)
        block = df.loc[start:stop]
        amp = (L if side == "Left" else R)[start:stop + 1].copy()
        tt = df["t0"].to_numpy()[start:stop + 1]
        t_end = np.append(tt[1:], np.nan)
        if int(np.isfinite(amp).sum()) >= int(min_settings):
            runs.append({
                "side": side,
                "steps": pd.DataFrame({"t0": tt, "t_end": t_end, "current_mA": amp,
                                       "block": [f"{side} run {len(runs) + 1}"] * len(tt)}),
                "n_settings": int(np.isfinite(amp).sum()),
                "current_from_mA": float(np.nanmin(amp[np.isfinite(amp) & (amp > 0)]))
                if np.any(np.isfinite(amp) & (amp > 0)) else None,
                "current_to_mA": float(np.nanmax(amp[np.isfinite(amp)])),
                "rate_hz": float(df["rate_hz"].to_numpy()[i]) if "rate_hz" in df else None,
                "start_local": str(df["t_local"].to_numpy()[start]),
                "end_local": str(df["t_local"].to_numpy()[stop]),
            })
        i = j + 1
    return runs


def _lowest_positive(values):
    """The smallest current above zero, or None when every row is zero or missing."""
    v = np.asarray(values, dtype=float)
    v = v[np.isfinite(v) & (v > 0)]
    return float(v.min()) if v.size else None


def _nearest_centre(centres, target):
    """The band centre on the cache's grid that sits closest to the band the device was sensing.

    The tile cache lays its bands out one hertz apart on half-integer centres, while the device puts
    its sensing centre on its own spectrum grid, so the two rarely coincide exactly. We take the
    single closest band and report how far off it is. We NEVER add or average two neighbouring bands
    to manufacture a centre in between: neighbouring bands are five hertz wide on one hertz spacing,
    so they overlap heavily and adding them counts the same signal several times over.
    """
    c = np.asarray(centres, dtype=float)
    if c.size == 0 or target is None or not np.isfinite(float(target)):
        return None, None
    j = int(np.argmin(np.abs(c - float(target))))
    return j, float(c[j] - float(target))


def _tile_panel(source, tile_t, tile_power, ok_mask, centres, steps, *, band_index,
                programmed_centre_hz, usable_band_mask, window_s, min_pieces,
                absent_when_empty, run_window):
    """One panel from three second pieces of recording, for either of the two converted routes.

    ``run_window`` is the stretch of time the run occupies, and every piece outside it is dropped
    before anything is counted. The count a panel prints has to describe the run it is drawn beside;
    a whole-history count would tell a reader this route is well covered here when it may have
    nothing at all here, which is exactly the mistake an honest empty panel exists to prevent.
    """
    centres = np.asarray(centres, dtype=float)
    panel = SourcePanel(source=source,
                        covers_whole_spectrum=SOURCE_COVERS_WHOLE_SPECTRUM[source],
                        conversion_into_device_units=SOURCE_CONVERSION[source],
                        n_settings_offered=int(len(steps)))
    t = np.asarray(tile_t, dtype=float)
    P = np.asarray(tile_power, dtype=float)
    if P.ndim != 2 or P.shape[0] != t.size:
        P = np.full((t.size, centres.size), np.nan)
    inside = (t >= float(run_window[0])) & (t < float(run_window[1]))
    panel.n_pieces_in_run_before_quality_checks = int(inside.sum())
    keep = np.asarray(ok_mask, dtype=bool) if ok_mask is not None else np.ones(t.size, dtype=bool)
    panel.n_pieces_dropped_for_quality = int((inside & ~keep).sum())
    keep = keep & inside
    t, P = t[keep], P[keep, :]
    order = np.argsort(t, kind="stable")
    t, P = t[order], P[order, :]
    panel.n_pieces_available_in_visit = int(t.size)

    if t.size == 0:
        panel.absent_reason = absent_when_empty
        return panel

    power, table = within_visit.mean_power_before_next_change(
        steps["t0"].to_numpy(dtype=float), steps["current_mA"].to_numpy(dtype=float),
        t, P, block=steps["block"].to_numpy(), step_end_t=steps["t_end"].to_numpy(dtype=float),
        window_s=window_s, min_chunks=min_pieces)

    used = np.isfinite(power).any(axis=1) if power.ndim == 2 else np.isfinite(power)
    panel.n_settings_used = int(used.sum())
    if panel.n_settings_used == 0:
        panel.absent_reason = (
            f"this route had {t.size} usable three second pieces of recording inside this run of "
            f"rising current, but none of the {len(steps)} stimulation settings had the "
            f"{int(min_pieces)} pieces the settled rule requires in the {window_s:g} seconds "
            f"before the next current increase")
        return panel

    j = band_index
    panel.band_centre_hz = float(centres[j])
    panel.band_lo_hz = float(centres[j]) - BAND_HALF_HZ
    panel.band_hi_hz = float(centres[j]) + BAND_HALF_HZ
    _, off = _nearest_centre(centres, programmed_centre_hz)
    panel.offset_from_programmed_centre_hz = off
    panel.band_is_measuring_the_stimulator = bool(not usable_band_mask[j])
    panel.band_inside_checked_conversion_range = bool(
        CHECKED_LO_HZ - 1e-9 <= centres[j] <= CHECKED_HI_HZ + 1e-9)

    panel.piece_length_s = float(within_visit.CHUNK_S)
    panel.piece_description = (f"one {within_visit.CHUNK_S:g} second piece of the recording, "
                               f"reduced to a single band power")
    amps = steps["current_mA"].to_numpy(dtype=float)
    counts = table["n_chunks_found"].to_numpy()
    why = table["refusal_reason"].tolist()
    for i in range(len(steps)):
        v = power[i, j] if used[i] else np.nan
        row = {"current_mA": float(amps[i]) if np.isfinite(amps[i]) else None,
               "settled_power": float(v) if np.isfinite(v) else None,
               "n_pieces": int(counts[i]),
               "accepted": bool(np.isfinite(v)),
               "why_not_used": (why[i] if not np.isfinite(v) else "")}
        panel.settings.append(row)
        if not np.isfinite(v):
            continue
        panel.current_mA.append(row["current_mA"])
        panel.settled_power.append(row["settled_power"])
        panel.n_pieces.append(row["n_pieces"])
        panel.spectrum_power.append([float(x) if np.isfinite(x) else None for x in power[i, :]])
    panel.spectrum_centres_hz = [float(x) for x in centres]
    panel.spectrum_band_is_measuring_the_stimulator = [bool(not u) for u in usable_band_mask]
    return panel


def build_comparison(*, label, ramped_side, sensing_contact, steps, visit_date,
                     window_start_local, window_end_local,
                     tiles, device_band_power, stimulation_rate_hz,
                     window_s=within_visit.PRE_CHANGE_WINDOW_S,
                     min_pieces=within_visit.MIN_CHUNKS_PRE_CHANGE):
    """Compute all three panels for one run of rising current on one side.

    ``steps`` is a table of the stimulation settings in time order, with ``t0`` the moment each
    setting started, ``t_end`` the moment the next one started, ``current_mA`` the current of the
    side being ramped, and ``block`` a label that must not be crossed when asking whether the current
    went up. ``tiles`` is one channel's entry from the tile cache. ``device_band_power`` is one
    contact's entry from :func:`read_device_band_power`, or None when the device reported none.

    Each of the three panels is computed from its own recording. Nothing is copied from one panel to
    another, and when a route has no usable recording its panel says so in plain words instead of
    borrowing a neighbour's numbers to look complete.
    """
    centres = np.asarray(tiles["centres_hz"] if "centres_hz" in tiles else tiles["centers_hz"],
                         dtype=float)
    half = float(tiles.get("band_half_hz", BAND_HALF_HZ))
    if abs(half - BAND_HALF_HZ) > 1e-9:
        raise ValueError(f"the tile cache says its bands are {half} hertz either side of centre, "
                         f"but this comparison is written for {BAND_HALF_HZ}; stopping rather than "
                         f"quietly comparing bands of two different widths")

    usable = clinic_steps.amplitude_response_band_mask(stimulation_rate_hz, centres)
    landings = [d["lands_at_hz"] for d in analytics.harmonic_landings_hz(
        stimulation_rate_hz, float(centres.min()) - half, float(centres.max()) + half)]

    # The stretch of time this run occupies. Everything the three panels count and average is cut
    # down to it first, so each panel's coverage number describes the run the reader is looking at.
    t_starts = steps["t0"].to_numpy(dtype=float)
    t_ends = steps["t_end"].to_numpy(dtype=float)
    run_window = (float(np.nanmin(t_starts)),
                  float(np.nanmax(np.where(np.isfinite(t_ends), t_ends, t_starts))))

    # The band the device was sensing DURING THIS RUN, read from the device's own record rather than
    # from anywhere else, and refused outright if it moved mid-run.
    device_here = None
    device_absent_reason = None
    if device_band_power:
        try:
            device_here = device_band_power_in_window(device_band_power, *run_window)
        except ValueError as exc:
            device_absent_reason = str(exc)
    programmed = (device_here or {}).get("centre_hz")

    # Which band the two converted routes are read at. It is the ONE band on the tile cache's grid
    # that sits closest to the band the device was sensing, so all three panels describe the same
    # part of the spectrum and the comparison means something. The cache lays its bands one hertz
    # apart on half-integer centres while the device puts its centre on its own spectrum grid, so
    # the two rarely land on the same number and the gap between them is reported rather than
    # smoothed over. Neighbouring bands are NEVER added or averaged to manufacture a centre in
    # between; they are five hertz wide on one hertz spacing, so they overlap heavily and combining
    # them counts the same signal several times over and inflates every value.
    j, off = _nearest_centre(centres, programmed)
    if j is None:
        # The device reported no sensing centre for this run, so there is no band it and the two
        # converted routes have in common. Rather than pick one and imply a comparison that cannot
        # be made, fall back to the middle of the range the conversion was checked over and say so.
        j = int(np.argmin(np.abs(centres - 0.5 * (CHECKED_LO_HZ + CHECKED_HI_HZ))))
        off = None

    out = ThreeSourceComparison(
        label=label, ramped_side=ramped_side, sensing_contact=sensing_contact,
        programmed_centre_hz=(float(programmed) if programmed is not None else None),
        stimulation_rate_hz=(float(stimulation_rate_hz)
                             if stimulation_rate_hz is not None else None),
        visit_date=str(visit_date), window_start_local=str(window_start_local),
        window_end_local=str(window_end_local),
        # The lowest and highest current the LADDER reached. The zero-current rows that bracket a
        # run are there only to mark where it began and ended, and reporting one of them as the
        # bottom of the range would say the ladder started at zero when the first setting the
        # clinician stepped to was the lowest positive current.
        current_from_mA=_lowest_positive(steps["current_mA"]),
        current_to_mA=(float(np.nanmax(steps["current_mA"].to_numpy(dtype=float)))
                       if len(steps) else None),
        n_settings=int(len(steps)), settled_window_s=float(window_s),
        bands_measuring_the_stimulator_hz=[float(c) for c in centres[~usable]],
        stimulator_landings_hz=[float(x) for x in landings])

    # ---- route 1: the voltage trace, cut into three second pieces ----
    td = tiles.get("td") or {}
    ok = None
    if td.get("ok") is not None:
        ok = np.asarray(td["ok"], dtype=bool)
        if td.get("saturated") is not None:
            ok = ok & ~np.asarray(td["saturated"], dtype=bool)
    out.panels.append(_tile_panel(
        SOURCE_TIME_DOMAIN, td.get("t", []), td.get("lsb", np.empty((0, centres.size))), ok,
        centres, steps, band_index=j, programmed_centre_hz=programmed, usable_band_mask=usable,
        window_s=window_s, min_pieces=min_pieces, run_window=run_window,
        absent_when_empty=("the device streamed no voltage trace on this contact during this run of "
                           "rising current, so there is nothing to compute a band power from")))

    # ---- route 2: the device's own spectrum ----
    psd = tiles.get("psd") or {}
    out.panels.append(_tile_panel(
        SOURCE_DEVICE_SPECTRUM, psd.get("t", []), psd.get("lsb", np.empty((0, centres.size))), None,
        centres, steps, band_index=j, programmed_centre_hz=programmed, usable_band_mask=usable,
        window_s=window_s, min_pieces=min_pieces, run_window=run_window,
        absent_when_empty=("the device produced none of its own spectra during this run of rising "
                           "current. It computes one only when the patient presses the button or "
                           "when a contact survey is run with the stimulation off, and neither "
                           "happened here")))

    # ---- route 3: the device's own band power, unconverted ----
    panel = SourcePanel(source=SOURCE_DEVICE_BAND_POWER,
                        covers_whole_spectrum=False,
                        conversion_into_device_units=None,
                        n_settings_offered=int(len(steps)))
    if device_absent_reason:
        panel.absent_reason = device_absent_reason
    elif not device_here or int(device_here.get("n_samples") or 0) == 0:
        whole = int((device_band_power or {}).get("n_samples") or 0)
        panel.absent_reason = ("the device reported none of its own band power on this contact "
                               "during this run of rising current, so this route has nothing to "
                               "show. It exists only while the device is streaming"
                               + (f", and it did stream {whole} samples on this contact at other "
                                  f"times in the record" if whole else ""))
    else:
        device_band_power = device_here
        panel.n_pieces_available_in_visit = int(device_here["n_samples"])
        panel.n_pieces_in_run_before_quality_checks = int(device_here["n_samples"])
        panel.band_centre_hz = (float(programmed) if programmed is not None else None)
        if programmed is not None:
            panel.band_lo_hz = float(programmed) - half
            panel.band_hi_hz = float(programmed) + half
            panel.offset_from_programmed_centre_hz = 0.0
            panel.band_is_measuring_the_stimulator = bool(
                not clinic_steps.amplitude_response_band_mask(
                    stimulation_rate_hz, np.array([float(programmed)]))[0])
            panel.band_inside_checked_conversion_range = None  # nothing was converted
        power, table = settled_device_band_power(
            steps["t0"].to_numpy(dtype=float), steps["t_end"].to_numpy(dtype=float),
            steps["current_mA"].to_numpy(dtype=float),
            device_band_power["t"], device_band_power["power"], device_band_power["mA"],
            block=steps["block"].to_numpy(), window_s=window_s)
        used = np.isfinite(power)
        panel.n_settings_used = int(used.sum())
        if panel.n_settings_used == 0:
            reasons = [r for r in table["why_not_used"].tolist() if r]
            panel.absent_reason = (
                f"the device reported {panel.n_pieces_available_in_visit} samples of its own band "
                f"power during the visit, but none of the {len(steps)} stimulation settings had a "
                f"settled window that met the rule. The first reason given was: "
                f"{reasons[0] if reasons else 'unknown'}")
        else:
            rate = _sample_rate(device_here["t"])
            panel.piece_length_s = float(1.0 / rate) if rate else None
            avg = device_here.get("averaging_s")
            panel.piece_description = (
                f"one sample of the device's own band power, arriving about "
                f"{rate:.1f} times a second"
                + (f", each already an average over {avg:g} seconds of signal" if avg else ""))
            amps = steps["current_mA"].to_numpy(dtype=float)
            counts = table["n_pieces_averaged"].to_numpy()
            why = table["why_not_used"].tolist()
            for i in range(len(steps)):
                v = power[i]
                row = {"current_mA": float(amps[i]) if np.isfinite(amps[i]) else None,
                       "settled_power": float(v) if np.isfinite(v) else None,
                       "n_pieces": int(counts[i]),
                       "accepted": bool(np.isfinite(v)),
                       "why_not_used": (why[i] if not np.isfinite(v) else "")}
                panel.settings.append(row)
                if not np.isfinite(v):
                    continue
                panel.current_mA.append(row["current_mA"])
                panel.settled_power.append(row["settled_power"])
                panel.n_pieces.append(row["n_pieces"])
    out.panels.append(panel)

    out.notes = [
        "The three panels come from three different recordings, but they are not three independent "
        "measurements: the device computes its own band power on board from the very voltage trace "
        "the first panel reads, and the contact surveys behind the second panel are where the "
        "conversion into device units was fitted. Agreement here means the conversion is behaving, "
        "not that stimulation moved the brain three times over.",
        f"Every number is an average over settled recording only: the {float(window_s):g} seconds "
        f"before the next increase in current, along a run of increases. Where the current fell, the "
        f"run ended and no window was carried across the break.",
        f"Bands where a multiple of the {stimulation_rate_hz:g} hertz stimulation lands after "
        f"sampling are marked; those carry a folded multiple of the stimulation rate.",
        f"The conversion into device units was checked only between {CHECKED_LO_HZ:g} and "
        f"{CHECKED_HI_HZ:g} hertz. The third panel converts nothing and needs no checked range.",
    ]
    return out


def comparison_rows(comparison: ThreeSourceComparison) -> List[Dict[str, Any]]:
    """One flat row per source, band and stimulation setting: the numbers behind every panel.

    A setting that produced no number still gets a row, with an empty band power and the plain
    reason it was refused. A route that had nothing at all for this run still gets rows too, for the
    same reason: a table that quietly leaves out what it could not measure reads as though the
    measurement was never attempted, and the whole point of this comparison is that a reader can see
    which of the three routes covered which settings.
    """
    rows: List[Dict[str, Any]] = []

    def base(panel):
        return {
            "source": panel.source,
            "run": comparison.label,
            "visit_date": comparison.visit_date,
            "ramped_side": comparison.ramped_side,
            "sensing_contact": comparison.sensing_contact,
            "stimulation_rate_hz": comparison.stimulation_rate_hz,
            "conversion_into_device_units": panel.conversion_into_device_units,
            "piece_length_s": panel.piece_length_s,
            "route_absent_reason": panel.absent_reason or "",
        }

    for panel in comparison.panels:
        if not panel.settings:
            rows.append({**base(panel), "band_centre_hz": panel.band_centre_hz,
                         "band_lower_edge_hz": panel.band_lo_hz,
                         "band_upper_edge_hz": panel.band_hi_hz, "current_mA": None,
                         "settled_band_power_device_units": None, "n_pieces_averaged": 0,
                         "band_is_measuring_the_stimulator": panel.band_is_measuring_the_stimulator,
                         "band_inside_checked_conversion_range":
                             panel.band_inside_checked_conversion_range,
                         "why_not_used": panel.absent_reason or ""})
            continue

        for k, st in enumerate(panel.settings):
            rows.append({**base(panel),
                         "band_centre_hz": panel.band_centre_hz,
                         "band_lower_edge_hz": panel.band_lo_hz,
                         "band_upper_edge_hz": panel.band_hi_hz,
                         "current_mA": st["current_mA"],
                         "settled_band_power_device_units": st["settled_power"],
                         "n_pieces_averaged": st["n_pieces"],
                         "band_is_measuring_the_stimulator":
                             panel.band_is_measuring_the_stimulator,
                         "band_inside_checked_conversion_range":
                             panel.band_inside_checked_conversion_range,
                         "why_not_used": st["why_not_used"]})

        # The routes that cover the whole spectrum also contribute every other band, so the table
        # holds the numbers the whole-spectrum panels are drawn from and not only the one band the
        # three routes are compared at.
        if not (panel.spectrum_power and panel.spectrum_centres_hz):
            continue
        accepted = [k for k, st in enumerate(panel.settings) if st["accepted"]]
        for k_acc, k in enumerate(accepted):
            st = panel.settings[k]
            for jj, centre in enumerate(panel.spectrum_centres_hz):
                if centre == panel.band_centre_hz:
                    continue
                rows.append({**base(panel),
                             "band_centre_hz": centre,
                             "band_lower_edge_hz": centre - BAND_HALF_HZ,
                             "band_upper_edge_hz": centre + BAND_HALF_HZ,
                             "current_mA": st["current_mA"],
                             "settled_band_power_device_units": panel.spectrum_power[k_acc][jj],
                             "n_pieces_averaged": st["n_pieces"],
                             "band_is_measuring_the_stimulator":
                                 panel.spectrum_band_is_measuring_the_stimulator[jj],
                             "band_inside_checked_conversion_range":
                                 bool(CHECKED_LO_HZ - 1e-9 <= centre <= CHECKED_HI_HZ + 1e-9),
                             "why_not_used": ""})
    return rows


# -------------------------------------------------------------------------------------------------
# The one call the server makes
# -------------------------------------------------------------------------------------------------
def build_for_participant(uid, *, max_runs=4, min_settings=3):
    """Build every three-source comparison this participant's record supports, for the report.

    WHERE THE LADDER OF CURRENTS COMES FROM, and why it is not the clinic testing sheet. The sheets
    are a spreadsheet a person keeps during the visit, they live in the analysis folder, and the
    server has no copy of them. The device's own log of the current it delivered is in the database
    already, and -- the reason it is the one to use -- it is written on the SAME CLOCK as the band
    power it reported, so a setting and the power measured during it cannot be misaligned by however
    far the two clocks have drifted apart. It also records what the device delivered rather than what
    was intended.

    HOW FAR THE TWO DISAGREE, measured rather than assumed. On the RCS08 visit of 2026-08-18 the
    sheet and the device agree on every setting and on their order, across the eleven settings of the
    two single-side runs. The moment each setting began differs by between 4 seconds early and 22
    seconds late on the device's clock, with a median of 6 seconds late. Both directions occur, so
    this is not a fixed offset that could be corrected for; it is the ordinary spread between a
    clinician writing down a time and the device finishing its ramp. That spread is small against
    the roughly sixty seconds each setting was held and against the thirty second settled window
    taken from the END of each setting, so it does not move any number reported here. It is the
    reason the ladder is read from the device rather than the reason to trust the device: a
    twenty-two second error in where a setting starts would matter to a window measured forwards
    from the start, and none of these are.

    ONE CONSEQUENCE OF USING THE DEVICE'S LOG, stated because it shortens a run rather than
    lengthening it. The log stops when the streaming session stops. On that same visit the clinician
    kept stepping the right side up to 3.0 mA but the device stopped streaming after 2.0 mA, so the
    run reported here ends at 2.0 mA. This is not a loss: the voltage trace behind the first panel
    comes from the same streaming session, so it stopped at the same moment. A run is never joined
    across such a gap, because on the far side of it there is no record that the current rose.

    Returns a payload dictionary, and NEVER raises for want of data. When the record supports no
    comparison at all, the payload says which of the required pieces was missing.
    """
    from Biomarkers import bravo_service as bs
    from Biomarkers.routines import availability as _avail

    payload: Dict[str, Any] = {"comparisons": [], "gates_nothing": True,
                               "ladder_from": "the device's own per-sample current record"}

    power = bs._load_recordings(uid, bs.POWERDOMAIN_TYPES)
    if not power:
        payload["absent_reason"] = (
            "the device has no streaming recordings stored for this participant, so there is no "
            "record of the current it delivered and no run of rising current to measure against")
        return payload

    current = read_device_current(power)
    runs = find_single_side_runs_from_device(current, min_settings=min_settings)
    payload["n_runs_found"] = len(runs)
    if not runs:
        payload["absent_reason"] = (
            f"the device streamed {len(current['blocks'])} recordings, but none of them contains a "
            f"stretch of at least {int(min_settings)} rising currents on one side with the other "
            f"side at zero. Only such a stretch lets a change in band power be attributed to one "
            f"side, so there is nothing here that can be compared three ways")
        return payload

    device = read_device_band_power(power)
    td = bs._load_recordings(uid, bs.TIMEDOMAIN_TYPES)
    psd = bs._load_recordings(uid, bs.AVAILABILITY_PSD_TYPES)
    chans = list(dict.fromkeys(_avail._canon_channel(c) for c in bs._derive_chan_order(td)))
    cache = bs._raw_lsb_cache_cached(
        uid, chans, list(td) + list(psd),
        bs._event_psd_lsb_blocks(uid, sensing_index=bs._build_sensing_config_index(list(td))),
        montage_psd_blocks=bs._montage_psd_lsb_blocks(uid, montage_recordings=psd))

    # Newest runs first: a reader of the deployment page is deciding about the present settings.
    runs.sort(key=lambda r: float(r["steps"]["t0"].max()), reverse=True)
    for run in runs[:int(max_runs)]:
        lo = float(run["steps"]["t0"].min())
        hi = float(np.nanmax(np.where(np.isfinite(run["steps"]["t_end"].to_numpy(dtype=float)),
                                      run["steps"]["t_end"].to_numpy(dtype=float),
                                      run["steps"]["t0"].to_numpy(dtype=float))))

        # The sensing contact is the one on the side that was ramped that actually carries device
        # band power inside this run. It is read from the device's record rather than chosen, so a
        # run can never be labelled with a contact that was not sensing during it.
        picked, picked_entry = None, None
        for contact, entry in device.items():
            if not str(contact).upper().endswith(run["side"].upper()):
                continue
            try:
                here = device_band_power_in_window(entry, lo, hi)
            except ValueError:
                continue
            if here and here["n_samples"] > int((picked_entry or {}).get("n_samples", 0)):
                picked, picked_entry = contact, here
        if picked is None or picked not in cache:
            continue

        rate = (picked_entry or {}).get("rate_hz")
        stamp = pd.to_datetime(lo, unit="s", utc=True).tz_convert("America/Los_Angeles")
        stamp_end = pd.to_datetime(hi, unit="s", utc=True).tz_convert("America/Los_Angeles")
        try:
            comp = build_comparison(
                label=(f"{stamp:%Y-%m-%d %H:%M}, {run['side'].lower()} stimulator turned up, "
                       f"other side at zero"),
                ramped_side=run["side"], sensing_contact=picked, steps=run["steps"],
                visit_date=f"{stamp:%Y-%m-%d}", window_start_local=f"{stamp:%Y-%m-%d %H:%M:%S}",
                window_end_local=f"{stamp_end:%Y-%m-%d %H:%M:%S}",
                tiles=cache[picked], device_band_power=device.get(picked),
                stimulation_rate_hz=rate)
        except Exception as exc:                        # one bad run must not lose the others
            payload.setdefault("runs_that_failed", []).append(
                {"side": run["side"], "starting_at": f"{stamp:%Y-%m-%d %H:%M:%S}",
                 "reason": f"{exc!r}"})
            continue
        payload["comparisons"].append(comp)

    if not payload["comparisons"]:
        payload["absent_reason"] = (
            f"the device's current record holds {len(runs)} runs of rising current on one side, but "
            f"none of them could be matched to a sensing contact that was reporting band power at "
            f"the time, so there is no band on which the three routes can be compared")
    return payload
