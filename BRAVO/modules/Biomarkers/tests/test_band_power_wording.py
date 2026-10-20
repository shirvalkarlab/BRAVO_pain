"""The Biomarkers server's refusal sentences say "TD and PSD band power", never "spectra" or
"spectral" (the PI's wording ruling of 2026-09-26).

The samples these sentences describe mix the two sources the page names: TD, band power worked
out from a time-domain recording, and PSD, the device's own 30 s snapshot. Each sentence below
reaches the page as the reason a band or a contact pair could not be assessed, so each is produced
here through the function that writes it and read back, not found by searching the source (the
one exception is the heat-map cell's message, which needs the database to reach).

Run inside the container:
    docker exec -w /usr/src/BRAVO bravo_pain-bravo-server-1 python3 -W ignore \
        modules/Biomarkers/tests/test_band_power_wording.py
"""
import os
import re
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from Biomarkers.routines import analytics as A          # noqa: E402

WORDS = "TD and PSD band power"
OLD = re.compile(r"spectr(?:um|a|al)", re.I)


def _says_it(why):
    assert WORDS in why, why
    assert not OLD.search(why), why


def test_the_auc_refusals_say_td_and_psd_band_power():
    x = np.asarray([1.0, 2.0, 3.0, 4.0, 5.0, 6.0])
    lab = np.asarray([1.0, 2.0, 3.0, 7.0, 8.0, 9.0])
    no_groups = A.band_pain_auc(x, lab, None)
    assert no_groups["answer"] == A.BAND_PAIN_NOT_ASSESSED
    _says_it(no_groups["why"])
    none_usable = A.band_pain_auc(np.full(6, np.nan), lab, np.arange(6))
    assert none_usable["answer"] == A.BAND_PAIN_NOT_ASSESSED
    _says_it(none_usable["why"])
    print("OK the area-under-the-curve refusals say TD and PSD band power")


def test_the_correlation_refusals_say_td_and_psd_band_power():
    x = np.asarray([1.0, 2.0, 3.0, 4.0])
    lab = np.asarray([1.0, 2.0, 3.0, 4.0])
    no_groups = A.band_pain_correlation(x, lab, None)
    assert no_groups["answer"] == A.BAND_PAIN_NOT_ASSESSED
    _says_it(no_groups["why"])
    too_few = A.band_pain_correlation(np.asarray([1.0, 2.0, np.nan, np.nan]), lab, np.arange(4))
    assert too_few["answer"] == A.BAND_PAIN_NOT_ASSESSED
    _says_it(too_few["why"])
    assert "only 2 samples of TD and PSD band power" in too_few["why"], too_few["why"]
    print("OK the correlation refusals say TD and PSD band power")


def test_the_table_refusal_says_td_and_psd_band_power():
    t = pd.DataFrame({"channel": ["A"] * 4, "center_hz": [20.0] * 4,
                      "power_linear": [1.0, 2.0, 3.0, 4.0], "nrs": [1.0, 2.0, 7.0, 8.0]})
    out = A.band_pain_auc_from_table(t, channel="A", center_hz=20.0)
    assert out["answer"] == A.BAND_PAIN_NOT_ASSESSED
    _says_it(out["why"])
    print("OK the closed-loop table refusal says TD and PSD band power")


def test_the_older_scans_absent_pair_says_td_and_psd_band_power():
    f = np.arange(1.0, 41.0)
    detail = {"f_set": f, "psd": np.ones((4, 1, f.size)), "labels": np.asarray([1.0, 2.0, 7.0, 8.0]),
              "chan_order": ["ZERO_THREE_LEFT"], "rating_group": np.arange(4),
              "times": np.arange(4.0)}
    for export in (A.band_pain_auc_export, A.band_pain_correlation_export):
        tab = export(detail, channels=["ONE_THREE_RIGHT"], centers=[20.0], n_boot=10)
        assert len(tab) == 1
        why = str(tab["why"].iloc[0])
        _says_it(why)
        assert why.endswith("is not present in the pooled TD and PSD band power handed in"), why
    print("OK the older scan's absent-pair reason says TD and PSD band power, twice")


def test_the_grid_with_no_band_centre_says_td_and_psd_band_power():
    out = A.band_time_sweep_from_power({1.0: np.zeros((3, 0))}, np.asarray([1.0, 2.0, 3.0]),
                                       center_freqs_hz=np.asarray([]))
    assert out["answer"] == A.BAND_PAIN_NOT_ASSESSED
    _says_it(out["why"])
    assert "nothing to sweep" in out["why"]
    print("OK the grid's no-band-centre reason says TD and PSD band power")


def test_the_heat_map_cell_message_says_td_and_psd_band_power():
    # Reached only through the database, so read from the one line that writes it.
    src = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "bravo_service.py"), encoding="utf-8").read()
    assert 'f"No cached TD and PSD band power for sensing contact pair {channel}."' in src
    assert "No cached spectra for sensing contact pair" not in src
    print("OK the heat-map cell message says TD and PSD band power")


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
