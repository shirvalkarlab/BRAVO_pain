"""The clinic-sheet ratings in the deployment summary, behind the Closed-Loop page's button (the
PI, 2026-09-24: "a toggle or an option to include the clinic sheets in the summary or not").

The summary, the deployment ROC and the stability grid share one setup (`_band_validation_setup`),
which read the REDCap ratings only: the switch that adds the sheet ratings to the heat-map grid
(decision 186) and to its drill-down (228) never reached it. With the switch on, the setup now
merges the sheet ratings that carry the chosen score, exactly as the grid does, through ONE helper
the grid, the drill-down and the setup all call; with it off, nothing changes. The setup says how
many it merged, so the page can print it.

Runs in the container (Django): python3 Biomarkers/tests/test_sheet_ratings_in_summary.py
"""
import os
import sys

import numpy as np
import pandas as pd

_BRAVO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, _BRAVO_ROOT)
sys.path.insert(0, os.path.join(_BRAVO_ROOT, "modules"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "BRAVO.settings")
try:
    import django  # noqa: E402
    django.setup()
except Exception:
    pass
from Biomarkers import bravo_service as bs  # noqa: E402


def _sheet_steps():
    t0 = pd.Timestamp("2026-03-01 18:00", tz="UTC")
    return pd.DataFrame([
        dict(t_utc=t0 + pd.Timedelta(hours=i), left_leg=float(4 + i), overall=np.nan, back=np.nan,
             setting="clinic") for i in range(3)] + [
        dict(t_utc=t0 + pd.Timedelta(hours=9), left_leg=np.nan, overall=6.0, back=np.nan, setting="clinic")])


def _with(patches, fn):
    old = {k: getattr(bs, k) for k in patches}
    try:
        for k, v in patches.items():
            setattr(bs, k, v)
        return fn()
    finally:
        for k, v in old.items():
            setattr(bs, k, v)


def test_the_helper_merges_only_the_steps_carrying_the_score_and_only_when_switched_on():
    t = np.array([1.0e9, 1.1e9]); v = np.array([50.0, 60.0])
    patches = {"load_clinic_sheet_steps": lambda uid: (_sheet_steps(), None)}
    off = _with(patches, lambda: bs._merge_clinic_sheet_ratings("u", "left_leg_vas", "Left Leg VAS", t, v, {}))
    on = _with(patches, lambda: bs._merge_clinic_sheet_ratings(
        "u", "left_leg_vas", "Left Leg VAS", t, v, {"IncludeClinicSheetRatings": "1"}))
    assert off[0].size == 2 and not off[2].any() and off[3]["included"] is False
    assert on[0].size == 5, "three steps carry a Left Leg score; the NRS-only step is not one"
    assert int(on[2].sum()) == 3 and on[3]["n_added"] == 3 and on[3]["included"] is True
    assert sorted(on[1][on[2]]) == [40.0, 50.0, 60.0], "sheet 0-10 put on the page's 0-100 scale"


def test_the_shared_setup_hands_the_merged_ratings_to_the_matcher_when_switched_on():
    seen = []
    from Biomarkers.routines import streaming_psd as sp

    class _P:
        uid = "u"

    def _pooled(mat, times, values, **kw):
        seen.append(np.asarray(times).size)
        return {"psd": np.zeros((1, 1))}
    t = np.array([1.0e9, 1.1e9]); v = np.array([50.0, 60.0])
    patches = {
        "load_clinic_sheet_steps": lambda uid: (_sheet_steps(), None),
        "_load_pros": lambda rd, P: pd.DataFrame({"x": [1, 2]}),
        "_resolve_biomarker_metric": lambda rd, df: (df, "left_leg_vas", None),
        "_pro_match_arrays": lambda df, m: (t, v),
        "_cached_psd_matrix": lambda uid, **k: {"t": np.array([1.0]), "X": np.ones((1, 1))},
        "_all_pro_times": lambda df: t,
        "_chronic_list_for": lambda uid: [],
    }
    old_find, old_pool = bs.models.Participant.find, sp.build_pooled_detail_from_matrix
    bs.models.Participant.find = staticmethod(lambda uid: _P())
    sp.build_pooled_detail_from_matrix = _pooled
    try:
        off = _with(patches, lambda: bs._band_validation_setup({"ParticipantId": "u"}))
        on = _with(patches, lambda: bs._band_validation_setup({"ParticipantId": "u", "IncludeClinicSheetRatings": "1"}))
    finally:
        bs.models.Participant.find, sp.build_pooled_detail_from_matrix = old_find, old_pool
    assert seen == [2, 5], seen
    assert off["clinic_sheet_ratings"]["included"] is False
    assert on["clinic_sheet_ratings"]["n_added"] == 3


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); print("PASS", name)
            except Exception as exc:                          # noqa: BLE001
                fails += 1; print("FAIL", name, repr(exc)[:300])
    sys.exit(1 if fails else 0)
