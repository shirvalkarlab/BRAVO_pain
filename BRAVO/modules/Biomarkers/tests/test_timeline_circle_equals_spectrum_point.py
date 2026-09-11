"""The timeline circle for a pain rating equals the per-rating spectrum at the same band centre.

WHAT IS ON A PAGE AND WHAT IS NOT (CLAUDE.md rule 13). The timeline circle IS on a page: the
Biomarkers page's data-availability timeline draws one circle per pain rating per sensing contact,
its value chosen by `availability.per_pro_lsb` at that contact's configured sensing centre --
the device's own sensed sample if one exists (native tier), else the voltage trace through the
validated transform (TD tier), else the device's own spectrum through the bridge (PSD-bridge tier).
The per-rating SPECTRUM (`availability.per_pro_lsb_spectrum`, the same rule evaluated at many
centres) is reached by NO page today: the live per-rating spectrum was retired on 2026-06-28 when
matching against the 3 s tile cache replaced it, and its only remaining callers are tests. So
this file pins an identity between a number a reader sees and a function nothing reads, which is
worth pinning for exactly one reason: the two share `_per_pro_lsb_*_indexed`'s rule, and anyone
who revives the spectrum, or changes the timeline's rule, must keep them equal or know they broke.

WHY THE NATIVE TIER IS LEFT OUT. The spectrum has no native tier -- a sensed sample exists at one
centre only, and a spectrum is by definition many centres -- so for a rating the timeline serves
natively the two are DIFFERENT by design, and the second test pins that difference deliberately
rather than letting it read as a failure of the identity.

Measured on RCS08 on 2026-09-10 before this file was written: 240 of 240 circles served from the
TD or bridge tier equal the spectrum at the same centre, bit for bit, across all 12 sensing
contacts (open item 13 of DECISIONS_and_open_items.md).
"""
import os
import sys
import pathlib
import numpy as np

_BRAVO_ROOT = pathlib.Path(__file__).resolve().parents[3]
if str(_BRAVO_ROOT) not in sys.path:
    sys.path.insert(0, str(_BRAVO_ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "BRAVO.settings")
try:
    import django
    django.setup()
except Exception:
    pass

from modules.Biomarkers.routines import availability as av

_FS = 250.0
_T0 = 1_700_000_000.0


def _td_rec(channel, start, secs=40.0, freq_hz=20.0, amp=2.0, seed=0):
    n = int(secs * _FS)
    tt = np.arange(n) / _FS
    sig = amp * np.sin(2 * np.pi * freq_hz * tt) + 0.1 * np.random.default_rng(seed).standard_normal(n)
    return {"ChannelNames": [channel], "Data": sig.reshape(-1, 1), "SamplingRate": _FS, "StartTime": start}


def _event_block(channel, t, center=20.0):
    f = np.linspace(0.0, 96.68, 100)
    mag = np.zeros(100); mag[(f >= center - 2.5) & (f <= center + 2.5)] = 2.0
    return {"channel": channel, "t": t, "freq": list(f), "power": list(mag), "center_hz": center}


def _spectrum_value_at(spec_record, center):
    """The spectrum's value at one centre, read the way a consumer would."""
    centres = spec_record.get("center_hz") or []
    vals = spec_record.get("lsb") or []
    for c, v in zip(centres, vals):
        if float(c) == float(center):
            return v
    return None


def test_a_rating_served_from_the_voltage_trace_or_the_bridge_reads_the_same_on_both():
    """Constructed: one rating the voltage trace serves, one only the bridge serves. Each equals the
    spectrum at the same centre EXACTLY -- `==`, never a tolerance (CLAUDE.md §10 rule 11)."""
    ch = "ZERO_THREE_LEFT"; center = 20.0
    td = _td_rec(ch, _T0, secs=40.0)                     # covers _T0 .. _T0+40
    ev_far = _event_block(ch, _T0 + 500.0)               # only the bridge can serve this rating
    pro = [_T0 + 20.0, _T0 + 500.0]
    circles = av.per_pro_lsb(pro, None, ch, center, td_recordings=[td], event_psd_recordings=[ev_far])
    spectra = av.per_pro_lsb_spectrum(pro, ch, [center], td_recordings=[td], event_psd_recordings=[ev_far])
    assert circles[0]["tier"] == av.PRO_LSB_TIER_TD
    assert circles[1]["tier"] == av.PRO_LSB_TIER_BRIDGE
    for i in range(2):
        c = circles[i]["lsb"]; s = _spectrum_value_at(spectra[i], center)
        assert c is not None and s is not None
        assert float(c) == float(s), (i, circles[i]["tier"], c, s)
        assert spectra[i]["tier"] == circles[i]["tier"], (spectra[i]["tier"], circles[i]["tier"])


def test_a_rating_served_natively_is_where_the_two_legitimately_differ():
    """The spectrum has no native tier, so a rating the timeline serves from the device's own
    sensed sample is NOT expected to equal the spectrum. Pinned so the exclusion in the live test
    below is a stated rule and not a convenience."""
    ch = "ZERO_THREE_LEFT"; center = 20.0
    td = _td_rec(ch, _T0, secs=40.0)
    native = {"t": [_T0 + 20.0], "y": [321.0], "center_hz": [20.0], "modeled": [False], "source": ["streaming"]}
    pro = [_T0 + 20.0]
    circle = av.per_pro_lsb(pro, native, ch, center, td_recordings=[td], event_psd_recordings=[])[0]
    spec = av.per_pro_lsb_spectrum(pro, ch, [center], td_recordings=[td], event_psd_recordings=[])[0]
    assert circle["tier"] == av.PRO_LSB_TIER_NATIVE and circle["lsb"] == 321.0
    assert spec["tier"] == av.PRO_LSB_TIER_TD
    assert float(circle["lsb"]) != float(_spectrum_value_at(spec, center))


def test_live_every_timeline_circle_on_rcs08_equals_the_spectrum_at_its_own_centre():
    """LIVE, on the real participant, the thing open item 13 asked for. Skips cleanly when RCS08 is
    not in this database (the same skip shape `test_analytics.py` uses). The circles are read from
    the availability payload -- the exact thing the page draws -- not recomputed; only the spectrum
    side is computed here, from the same recordings the page's own builder uses. Compared with
    `==` per value and counted, so a failure names how many moved.
    """
    try:
        from Server import models
        from modules.Biomarkers import bravo_service as bs
    except Exception:
        return                                           # no Django here -> nothing live to check
    uid = "2e3c75c00d7f4f37b53a048d195f11da"
    try:
        if models.Participant.find(uid=uid) is None:
            return
    except Exception:
        return

    avail = bs.availability_for_participant({"ParticipantId": uid})["availability"]
    pro_lsb = avail.get("pro_lsb") or {}
    pain_t = np.asarray(avail["pain"]["t"], dtype=float)
    if pain_t.size == 0 or not pro_lsb:
        return

    td = bs._load_recordings(uid, bs.TIMEDOMAIN_TYPES)
    psd_list = bs._load_recordings(uid, bs.AVAILABILITY_PSD_TYPES)
    pd_list = bs._load_recordings(uid, bs.POWERDOMAIN_TYPES)
    sensing_hz = av.analytics.power_center_freqs(pd_list)
    event_blocks = bs._event_psd_lsb_blocks(uid, sensing_hz_by_channel=sensing_hz,
                                            sensing_index=bs._build_sensing_config_index(list(td or [])))
    index = av.channel_index(list(td or []) + list(psd_list or []), event_blocks)

    compared = equal = 0
    moved = []
    for raw_ch, recs in pro_lsb.items():
        centres = sorted({float(r["center_hz"]) for r in recs if r.get("center_hz") is not None})
        if not centres:
            continue
        for c in centres:
            spec = av.per_pro_lsb_spectrum(pain_t, av._canon_channel(raw_ch), [c], index=index)
            for i, r in enumerate(recs):
                if r.get("tier") not in (av.PRO_LSB_TIER_TD, av.PRO_LSB_TIER_BRIDGE):
                    continue
                if float(r["center_hz"]) != c or r.get("lsb") is None:
                    continue
                s = _spectrum_value_at(spec[i], c)
                compared += 1
                if s is not None and float(r["lsb"]) == float(s):
                    equal += 1
                else:
                    moved.append((raw_ch, i, r.get("tier"), r["lsb"], s))
    assert compared > 0, "RCS08 has no timeline circle served from the voltage trace or the bridge"
    assert equal == compared, f"{compared - equal} of {compared} circles differ from the spectrum: {moved[:5]}"
