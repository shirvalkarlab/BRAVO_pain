"""The deployment summary's area under the curve read again with the stimulation current taken out
(the PI, 2026-09-25, answer 6 of the revised plan: "build the same number with the current taken out
beside it").

The routine (`routines/deployment_current.py`) is checked on constructed records whose answer is
known: a band whose power and pain both follow the current reads well plainly and near coin flipping
adjusted; a band with its own pain relationship keeps it; a band read "more power, less pain" is
given in that same direction; and each refusal (no dated settings, a current that never moves, a
band that is the current) says why instead of printing a number. The summary endpoint is checked
to carry it without moving a single plain number, gate or verdict (descriptive only, decision 233
answer 2).

The routine tests need no Django; the endpoint tests need it and are skipped without it.
Runs in the container: python3 Biomarkers/tests/test_summary_auc_current_taken_out.py
"""
import os
import sys

import numpy as np
import pandas as pd

_BRAVO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, _BRAVO_ROOT)
sys.path.insert(0, os.path.join(_BRAVO_ROOT, "modules"))

from Biomarkers.routines import analytics  # noqa: E402
from Biomarkers.routines import deployment_current as dc  # noqa: E402

CH = "ONE_THREE_LEFT"
T0 = pd.Timestamp("2026-01-05 12:00", tz="UTC")
N_REPORTS = 48
PER_REPORT = 6


def _record(kind, seed=1, constant_current=None, other_pair_reports=0):
    """A pooled detail of the shape `_band_validation_setup` builds, one band at 24.5 Hz, and the
    settings stream in force. The current steps 0 -> 1 -> 2 -> 3 mA over the record (a new setting
    every 12 reports), so the current is confounded with time as on RCS08.

    kind: "confounded"  -- power and pain both follow the current, nothing else links them;
          "own"         -- pain moves the power, the current is set independently of both;
          "inverse"     -- as "own" but more power goes with LESS pain;
          "is_current"  -- the power is the current itself, to within a whisper.
    """
    rng = np.random.default_rng(seed)
    rep_t = [T0 + pd.Timedelta(hours=6 * i) for i in range(N_REPORTS)]
    if constant_current is not None:
        cur_rep = np.full(N_REPORTS, float(constant_current))
    elif kind == "confounded":
        cur_rep = np.repeat([0.0, 1.0, 2.0, 3.0], N_REPORTS // 4)
    else:
        cur_rep = rng.choice([0.0, 1.0, 2.0, 3.0], N_REPORTS)
    if kind == "confounded":
        pain_rep = 3.0 + 1.5 * cur_rep + rng.normal(0, 0.6, N_REPORTS)
    else:
        pain_rep = rng.uniform(0, 10, N_REPORTS)
    f = np.arange(20.0, 30.0, 1.0)
    rows_p, rows_lab, rows_g, rows_t = [], [], [], []
    for i in range(N_REPORTS):
        for k in range(PER_REPORT):
            noise = rng.normal(0, 1.0)
            if kind == "confounded":
                power = 2.0 * cur_rep[i] + noise
            elif kind == "own":
                power = 0.6 * pain_rep[i] + noise
            elif kind == "inverse":
                power = -0.6 * pain_rep[i] + noise
            else:                                    # "is_current"
                power = cur_rep[i] + 1e-4 * noise
            rows_p.append(np.full(f.size, power))
            rows_lab.append(pain_rep[i])
            rows_g.append(i)
            rows_t.append(str((rep_t[i] - pd.Timedelta(minutes=5 * k)).tz_convert(None)))
    # pain reports matched only to ANOTHER contact pair: no power on this one, but their scores
    # count where the plain curve draws its thirds (as in the pooled detail on RCS08)
    for j in range(other_pair_reports):
        rows_p.append(np.full(f.size, np.nan))
        rows_lab.append(9.5 + 0.01 * j)
        rows_g.append(N_REPORTS + j)
        rows_t.append(str((rep_t[-1] + pd.Timedelta(hours=1 + j)).tz_convert(None)))
    psd = np.asarray(rows_p)[:, None, :]
    detail = {"f_set": f, "psd": psd, "labels": np.asarray(rows_lab), "chan_order": [CH],
              "rating_group": np.asarray(rows_g), "times": rows_t}
    # the settings: one row per change on the left, the first a day before the record starts
    change_idx = [0] + [i for i in range(1, N_REPORTS) if cur_rep[i] != cur_rep[i - 1]]
    t_s = [(rep_t[0] - pd.Timedelta(days=1)).timestamp()] + [
        (rep_t[i] - pd.Timedelta(hours=1)).timestamp() for i in change_idx[1:]]
    stream = {"t_s": np.asarray(t_s, float), "hemi": np.asarray(["Left"] * len(t_s), object),
              "amp_mA": np.asarray([cur_rep[i] for i in change_idx], float),
              "store_key": "stream-key", "n_rows": len(t_s)}
    return detail, stream


def _read(detail, stream, **kw):
    roc = analytics.deployment_roc(detail, CH, 24.5, band_width_hz=5.0, n_boot=200)
    out = dc.auc_with_current_taken_out(detail, CH, 24.5, band_width_hz=5.0, strategy="tertile",
                                        low_pct=33.3333, high_pct=66.6667, settings_stream=stream,
                                        plain_roc=roc, n_boot=200, **kw)
    return roc, out


def test_a_band_that_only_follows_the_current_reads_near_coin_flipping_once_it_is_out():
    detail, stream = _record("confounded")
    roc, out = _read(detail, stream)
    assert roc["auc"] > 0.8, roc["auc"]
    assert out["available"] is True, out["why"]
    assert out["auc_low"] < 0.5 < out["auc_high"], (out["auc"], out["auc_low"], out["auc_high"])
    assert out["shape"] == "line" and out["flexibility_spent"] == 1
    assert out["n_distinct_currents"] == 4 and out["n_samples_without_current"] == 0
    # the same estimator's plain reading on the same samples is the plain curve's own number
    assert abs(out["plain_on_same_samples"]["auc"] - roc["auc"]) < 1e-12


def test_a_band_with_its_own_pain_relationship_keeps_it():
    detail, stream = _record("own")
    roc, out = _read(detail, stream)
    assert out["available"] is True, out["why"]
    assert out["auc_low"] > 0.5, (out["auc"], out["auc_low"])
    assert abs(out["auc"] - roc["auc"]) < 0.05, (out["auc"], roc["auc"])
    assert out["partial_r"] > 0.3


def test_a_band_read_more_power_less_pain_is_given_in_the_plain_readings_own_direction():
    detail, stream = _record("inverse")
    roc, out = _read(detail, stream)
    assert roc["flip"] is True and roc["auc"] > 0.7
    assert out["auc"] > 0.7, "the adjusted reading must be given in the plain number's direction"
    assert out["auc_more_power_more_pain"] < 0.3
    assert abs(out["auc"] - (1.0 - out["auc_more_power_more_pain"])) < 1e-12
    assert out["auc_low"] <= out["auc"] <= out["auc_high"]
    assert out["plain_direction"] == "more power goes with less pain"


def test_no_dated_settings_is_a_stated_refusal_not_a_number():
    detail, _stream = _record("own")
    _roc, out = _read(detail, None)
    assert out["available"] is False and out["auc"] is None
    assert "no current per sample" in out["why"]


def test_a_current_that_never_moves_is_a_stated_refusal():
    detail, stream = _record("own", constant_current=2.0)
    _roc, out = _read(detail, stream)
    assert out["available"] is False and out["auc"] is None
    assert "constant" in out["why"], out["why"]


def test_a_band_that_is_the_current_is_a_stated_refusal_under_the_shared_rule():
    detail, stream = _record("is_current")
    _roc, out = _read(detail, stream)
    assert out["available"] is False and out["auc"] is None
    assert out["nearly_the_current"] is True
    assert out["r_power_vs_current"] ** 2 >= analytics_rule(), out["r_power_vs_current"]


def analytics_rule():
    from Biomarkers.routines.stats_utils import NEARLY_THE_COVARIATE_R2
    return NEARLY_THE_COVARIATE_R2


def test_samples_before_the_first_setting_are_counted_out_and_the_plain_reading_follows_them():
    detail, stream = _record("own")
    # the settings filed before the thirteenth report are dropped: the samples before the first
    # setting left have no current, which is unknown, not zero
    cutoff = (T0 + pd.Timedelta(hours=6 * 12 - 1)).timestamp()
    keep = np.asarray(stream["t_s"], float) >= cutoff
    late = dict(stream, t_s=np.asarray(stream["t_s"], float)[keep],
                hemi=np.asarray(stream["hemi"], object)[keep],
                amp_mA=np.asarray(stream["amp_mA"], float)[keep])
    roc, out = _read(detail, late)
    assert out["available"] is True, out["why"]
    # counted among the samples the plain curve uses (the high and low thirds)
    y = analytics._binarize_labels(detail["labels"], rating_group=detail["rating_group"])
    early = dc.epoch_seconds(detail["times"]) < float(late["t_s"].min())
    assert out["n_samples_total"] == int(np.isfinite(y).sum())
    assert out["n_samples_without_current"] == int((early & np.isfinite(y)).sum()) > 0
    # the like-for-like plain reading is on exactly the adjusted reading's samples and reports
    assert out["plain_on_same_samples"]["n_spectral_samples"] == out["n_spectral_samples"]
    assert out["plain_on_same_samples"]["n_pain_reports"] == out["n_pain_reports"] < roc["n_clusters"]


def test_the_split_is_the_plain_curves_own_even_when_other_pairs_reports_set_the_thirds():
    """Found on the live record: the pooled detail carries samples of every contact pair, and the
    plain curve draws its thirds over all of their pain reports. Re-drawing them on this band's own
    rows moved which reports counted as high or low (0.608 against the printed 0.617). The plain
    reading made the adjusted reading's way, on the same samples, must equal the printed number."""
    detail, stream = _record("own", other_pair_reports=20)
    roc, out = _read(detail, stream)
    assert out["available"] is True, out["why"]
    assert out["n_samples_without_current"] == 0
    # two implementations of one weighted sum (the estimator's and scikit-learn's) differ in the last
    # digits only; the old re-drawn split was 0.009 away on RCS08
    assert abs(out["plain_on_same_samples"]["auc"] - roc["auc"]) < 1e-12
    assert out["plain_on_same_samples"]["n_pain_reports"] == roc["n_clusters"]


def test_no_plain_reading_means_nothing_to_read_again():
    detail, stream = _record("own")
    out = dc.auc_with_current_taken_out(detail, CH, 24.5, band_width_hz=5.0, strategy="tertile",
                                        low_pct=33.3333, high_pct=66.6667, settings_stream=stream,
                                        plain_roc={"available": False}, n_boot=200)
    assert out["available"] is False and "plain reading could not be formed" in out["why"]


# ---------------------------------------------------------------------------------------------
# The endpoint: carried on the summary's evidence, moving nothing else (needs Django)
# ---------------------------------------------------------------------------------------------

def _summary_with(stream):
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "BRAVO.settings")
    import django
    django.setup()
    from Biomarkers import bravo_service as bs
    from Biomarkers.routines import stim_current as sc
    detail, _ = _record("confounded")
    core = {"available": True, "participant_uid": "u", "Participant": None, "channel": CH,
            "center_hz": 24.5, "band_width_hz": 5.0, "pooled": detail, "stim_series": None,
            "glmer": {}, "stim": {}, "verdict": None, "label_metric": "nrs",
            "composite_parts": None, "label_strategy": "tertile", "low_pct": 33.3333,
            "high_pct": 66.6667, "match_direction": "prior", "clinic_sheet_ratings": None}
    saved = {k: getattr(bs, k) for k in ("_validate_band_core", "_sign_off_recordings",
                                         "_calibration_scatter")}
    saved_sc = sc.settings_stream_for
    saved_lsb = (bs.availability.lsb_series, bs.availability.modeled_lsb_at_center)
    try:
        bs._validate_band_core = lambda rd: dict(core)
        bs._sign_off_recordings = lambda uid: ([], [], [], [])
        bs._calibration_scatter = lambda uid: None
        bs.availability.lsb_series = lambda *a, **k: {}
        bs.availability.modeled_lsb_at_center = lambda *a, **k: np.zeros(0)
        sc.settings_stream_for = lambda uid: stream
        return bs.deployment_summary({"ParticipantId": "u", "Channel": CH, "CenterHz": 24.5,
                                      "NBoot": 200})
    finally:
        for k, v in saved.items():
            setattr(bs, k, v)
        sc.settings_stream_for = saved_sc
        bs.availability.lsb_series, bs.availability.modeled_lsb_at_center = saved_lsb


def _django_available():
    try:
        os.environ.setdefault("DJANGO_SETTINGS_MODULE", "BRAVO.settings")
        import django
        django.setup()
        from Biomarkers import bravo_service  # noqa: F401
        return True
    except Exception:                                                   # noqa: BLE001
        return False


def test_the_summary_carries_the_adjusted_reading_beside_the_plain_one_and_moves_nothing_else():
    if not _django_available():
        import pytest
        pytest.skip("the summary endpoint needs Django (runs in the container)")
    _, stream = _record("confounded")
    with_ = _summary_with(stream)
    without = _summary_with(None)
    adj = with_["evidence"]["auc_current_removed"]
    assert adj["available"] is True, adj["why"]
    assert adj["label"] == "with the stimulation current taken out"
    assert adj["auc_low"] < 0.5 < adj["auc_high"]
    assert without["evidence"]["auc_current_removed"]["available"] is False
    # descriptive only: every plain number, gate and the verdict are the same either way
    for k in ("auc", "auc_lo", "auc_hi", "n_clusters"):
        assert with_["evidence"][k] == without["evidence"][k], k
    assert with_["gates"] == without["gates"] and with_["verdict"] == without["verdict"]
    assert with_["caveats"] == without["caveats"]


def _roc_with(stream):
    """The Closed-Loop deployment ROC panel's own endpoint (`band_deployment_roc`) on the same
    constructed record, with the band core and the settings stream stood in for."""
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "BRAVO.settings")
    import django
    django.setup()
    from Biomarkers import bravo_service as bs
    from Biomarkers.routines import stim_current as sc
    detail, _ = _record("confounded")
    core = {"available": True, "participant_uid": "u", "channel": CH, "center_hz": 24.5,
            "band_width_hz": 5.0, "pooled": detail, "label_metric": "nrs",
            "label_strategy": "tertile", "low_pct": 33.3333, "high_pct": 66.6667,
            "match_direction": "prior", "refractory_min": 30.0}
    saved_core, saved_sc = bs._validate_band_core, sc.settings_stream_for
    try:
        bs._validate_band_core = lambda rd: dict(core)
        sc.settings_stream_for = lambda uid: stream
        return bs.band_deployment_roc({"ParticipantId": "u", "Channel": CH, "CenterHz": 24.5,
                                       "NBoot": 200})
    finally:
        bs._validate_band_core, sc.settings_stream_for = saved_core, saved_sc


def test_the_deployment_roc_panel_carries_the_adjusted_reading_and_moves_nothing_else():
    """2026-09-26: the Closed-Loop page's deployment ROC panel has its own endpoint and printed the
    plain area alone; it now carries the same current-removed reading the summary carries (decision
    293), from the same routine, descriptive only."""
    if not _django_available():
        import pytest
        pytest.skip("the ROC endpoint needs Django (runs in the container)")
    _, stream = _record("confounded")
    with_ = _roc_with(stream)
    without = _roc_with(None)
    adj = with_["auc_current_removed"]
    assert adj["available"] is True, adj["why"]
    assert adj["label"] == "with the stimulation current taken out"
    assert adj["auc_low"] < 0.5 < adj["auc_high"]
    assert without["auc_current_removed"]["available"] is False
    # descriptive only: the plain curve and the forward check are the same either way
    assert with_["roc"] == without["roc"] and with_["forward"] == without["forward"]
    assert set(with_) == set(without)

if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); print("PASS", name)
            except Exception as exc:                          # noqa: BLE001
                fails += 1; print("FAIL", name, repr(exc)[:300])
    sys.exit(1 if fails else 0)
