"""The band labeller runs on the device's own bins up to 125 Hz (decision 505's open item, fixed
2026-10-27).

Until then the table both copies of `snap_freq` read stopped at 26.4 Hz, so the device's 27.34 Hz
(RCS08's left lead, L 0-3, from 2026-10-07) and 28.32 Hz (right lead, R 0-3, 2025-11-20 to
2025-12-17) sensing frequencies were labelled 26.4 Hz, and the chronic log's readings at those
frequencies were merged with the real 26.37 Hz readings in every home-record answer at 26.5 Hz.

Held here, on values:
  * the chronic log's readings at 26.37, 27.34 and 28.32 Hz are filed at 26.4, 27.3 and 28.3 Hz,
    and the chronic answer gives each its own band (26.5, 27.5, 28.5 Hz), with only its own
    readings: a band whose power follows pain is not mixed with one whose power runs against it;
  * the two formula copies (`pipeline._snap_freq`, `adapter._snap_freq_local`) give the table's
    label for every device bin centre, exact or as the device spells it to two decimals.

Run inside the container: python3 _agent_bridge/_snr6_run.py Biomarkers/tests/test_band_labeller_to_125hz.py
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from modules.Biomarkers.routines import chronic_band_choice as CBC      # noqa: E402
from modules.Biomarkers.routines import availability as av              # noqa: E402
from modules.DecodeCommon import representation as R                     # noqa: E402

T0 = 1_760_000_000.0
CENTRES = [8.5 + k for k in range(22)]          # the heat map's centres, 8.5 to 29.5 Hz
FREQS = (26.37, 27.34, 28.32)                   # the device's sensing frequencies on RCS08
N_EACH = 14


def _three_frequency_log():
    """One left chronic recording on L 0-3 whose sensing frequency moves 26.37 -> 27.34 -> 28.32 Hz,
    a reading one minute before each report. Power follows pain at 26.37 and 28.32 Hz and runs
    against it at 27.34 Hz."""
    rng = np.random.default_rng(3)
    n = N_EACH * len(FREQS)
    rt = T0 + 3600.0 * np.arange(n) + 30.0
    pain = rng.normal(5.0, 2.0, n)
    t = rt - 60.0
    seg = np.repeat(np.arange(len(FREQS)), N_EACH)
    lfp = np.where(seg == 1, 500.0 - 30.0 * pain, 100.0 + 10.0 * pain)
    sched = [[float(t[i * N_EACH]) - 1.0, f] for i, f in enumerate(FREQS)]
    rec = {"ChannelNames": ["LeftHemisphere LFP", "LeftHemisphere Amplitude"],
           "Data": np.column_stack([lfp, np.ones(n)]), "Time": t, "SamplingRate": -1,
           "RecordingType": "MedtronicChronicBrainSense", "FreqScheduleHz": sched,
           "ContactSchedule": [[float(t[0]) - 1.0, "0-3"]]}
    merged, _ = R.merge_chronic_repeats([rec])
    return merged, rt, pain, seg


def test_the_chronic_readings_at_each_frequency_are_filed_at_its_own_label():
    recs, rt, pain, seg = _three_frequency_log()
    s = CBC.chronic_samples_by_pair(recs)["ZERO_THREE_LEFT"]
    got = [(round(float(t) - T0), float(f)) for t, f in zip(s["t"], s["freq_hz"])]
    want = [(round(float(t) - T0), (26.4, 27.3, 28.3)[k]) for t, k in zip(rt - 60.0, seg)]
    assert got == want


def test_the_chronic_answer_no_longer_pools_26_37_and_27_34_hz():
    recs, rt, pain, seg = _three_frequency_log()
    blk = CBC.chronic_band_choice(CBC.chronic_samples_by_pair(recs), {}, rt, pain, centres=CENTRES,
                                  tol_s=900.0, n_boot=200)["ZERO_THREE_LEFT"]
    by = blk["by_centre"]
    assert sorted(by) == [26.5, 27.5, 28.5], sorted(by)
    assert [by[c]["freq_hz"] for c in (26.5, 27.5, 28.5)] == [26.4, 27.3, 28.3]
    for c in (26.5, 27.5, 28.5):
        assert by[c]["n_reports"] == N_EACH and by[c]["covered"] is True, (c, by[c]["n_reports"])
    # each band's answer is its own readings' only: power follows pain at 26.37 and 28.32 Hz and
    # runs against it at 27.34 Hz; pooled at one label (the old table) the r would be neither
    assert by[26.5]["pearson_r"] > 0.99 and by[28.5]["pearson_r"] > 0.99
    assert by[27.5]["pearson_r"] < -0.99
    # the 26.5 Hz answer is exactly the answer on the 26.37 Hz readings alone, field for field
    only = seg == 0
    alone_recs, _ = R.merge_chronic_repeats([{
        **recs[0], "Data": np.asarray(recs[0]["Data"])[only], "Time": np.asarray(recs[0]["Time"])[only],
        "FreqScheduleHz": [recs[0]["FreqScheduleHz"][0]]}])
    alone = CBC.chronic_band_choice(CBC.chronic_samples_by_pair(alone_recs), {}, rt[only], pain[only],
                                    centres=CENTRES, tol_s=900.0, n_boot=200)["ZERO_THREE_LEFT"]
    ea, eb = by[26.5], alone["by_centre"][26.5]
    for k in ea:                                    # no tolerance
        va, vb = ea[k], eb[k]
        assert (va == vb) or (va != va and vb != vb), (k, va, vb)


def test_the_formula_copies_give_the_tables_label_on_every_device_frequency():
    from modules.Biomarkers import pipeline as PL, adapter as AD
    for k in range(4, 129):
        for v in (k * 250.0 / 256.0, round(k * 250.0 / 256.0, 2), int(k * 250.0 / 256.0 * 100) / 100):
            want = av.snap_freq(v)
            assert want == R.snap_freq(v) == PL._snap_freq(v) == AD._snap_freq_local(v), (k, v)
