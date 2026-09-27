"""Regression tests for the pipeline-level statistics helpers added in the rigor review.

Run inside the container:
    docker exec -w /usr/src/BRAVO bravo_pain-bravo-server-1 python3 -W ignore \
        modules/Biomarkers/tests/test_pipeline_stats.py
"""
import os
import sys
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from Biomarkers import pipeline  # noqa: E402


def test_select_biomarker_band_enforces_50hz_cap():
    """The 50 Hz biomarker cap: even when the globally strongest |R| sits at/above 50 Hz, the
    selector must NEVER pick it — it returns the strongest band strictly below 50 Hz. A grid whose
    only finite cells are >=50 Hz returns None (nothing selectable)."""
    rng = np.random.default_rng(0)
    N = 60
    f_set = np.array([10.0, 20.0, 40.0, 55.0, 60.0])
    labels = np.linspace(0, 10, N) + rng.normal(0, 0.3, N)
    feat = rng.normal(0, 1, (N, 1, f_set.size))
    feat[:, 0, 4] = labels * 2 + rng.normal(0, 0.05, N)   # 60 Hz: near-perfect, strongest GLOBALLY
    feat[:, 0, 1] = labels + rng.normal(0, 0.6, N)         # 20 Hz: strong but weaker, < 50
    corr = np.array([[np.corrcoef(feat[:, 0, j], labels)[0, 1] for j in range(f_set.size)]])
    result = {"corr": corr, "f_set": f_set, "feature": feat, "labels": labels,
              "pval": np.full((1, f_set.size), 0.001)}
    # The global argmax |R| is the 60 Hz cell -- the cap must override it.
    assert f_set[int(np.argmax(np.abs(corr[0])))] >= 50.0
    sel = pipeline.select_biomarker_band(result, q_threshold=0.05)
    assert sel is not None
    assert sel[4] < pipeline.MAX_BIOMARKER_FREQ_HZ, f"selected band {sel[4]} Hz violates the 50 Hz cap"
    assert sel[4] == 20.0
    # When every finite cell is >= 50 Hz, NOTHING is selectable.
    res_all_high = dict(result, f_set=np.array([50.0, 55.0, 60.0, 70.0, 80.0]))
    assert pipeline.select_biomarker_band(res_all_high) is None


def test_available_frequencies_counts_and_split():
    """_available_frequencies reports per-band sample/day/label counts pooling chronic+streaming,
    and never mixes bands."""
    import pandas as pd
    base = pd.Timestamp("2025-09-01")
    rows = []
    # 7.8 Hz band: 3 days, mixed labels (chronic + streaming pooled — source is irrelevant here).
    for d in range(3):
        for k in range(4):
            rows.append({"timestamp": base + pd.Timedelta(days=d, hours=k), "frequency_hz": 7.8,
                         "pain_level": float(d % 2)})              # day0=0, day1=1, day2=0
    # 22.5 Hz band: 2 days, one fully unlabeled (pain_level NaN) -> counts as samples/days but not labeled.
    for d in range(2):
        for k in range(3):
            rows.append({"timestamp": base + pd.Timedelta(days=10 + d, hours=k), "frequency_hz": 22.5,
                         "pain_level": (1.0 if d == 0 else np.nan)})
    cv = pd.DataFrame(rows)
    av = pipeline._available_frequencies(cv)
    by = {round(a["frequency_hz"], 1): a for a in av}
    assert set(by) == {7.8, 22.5}
    assert by[7.8]["n_samples"] == 12 and by[7.8]["n_days"] == 3
    assert by[7.8]["n_labeled"] == 12 and by[7.8]["n_pos"] == 4 and by[7.8]["n_neg"] == 8
    assert by[22.5]["n_samples"] == 6 and by[22.5]["n_days"] == 2
    assert by[22.5]["n_labeled"] == 3 and by[22.5]["n_days_labeled"] == 1
    # No frequency column -> empty (legacy data).
    assert pipeline._available_frequencies(cv.drop(columns=["frequency_hz"])) == []


def test_decode_by_frequency_never_pools_bands():
    """_decode_by_frequency slices the frame per sensing band and computes ROC/Otsu/binarization on
    that band ALONE — a contact's 7.8 Hz and 22.5 Hz samples never mix, and a band with too few
    labeled samples reports counts but no AUC."""
    import pandas as pd
    base = pd.Timestamp("2025-09-01")
    rows = []
    # 7.8 Hz: 12 labeled days, power separates the classes (decodable).
    for d in range(12):
        hi = (d % 2 == 0)
        for k in range(5):
            rows.append({"timestamp": base + pd.Timedelta(days=d, hours=k),
                         "frequency_hz": 7.8, "LFP_smoothed": (150.0 if hi else 110.0),
                         "pain_level": (1.0 if hi else 0.0), "nrs": (8.0 if hi else 2.0)})
    # 22.5 Hz: a single day, one class -> too little to fit a detector.
    for k in range(4):
        rows.append({"timestamp": base + pd.Timedelta(days=40, hours=k),
                     "frequency_hz": 22.5, "LFP_smoothed": 130.0, "pain_level": 1.0, "nrs": 7.0})
    cv = pd.DataFrame(rows)
    fd = pipeline._decode_by_frequency(cv, "nrs")
    assert set(fd) == {"7.8", "22.5"}
    # 7.8 band: decodable, perfectly separable -> AUC == 1.0, Otsu between the two power levels.
    assert fd["7.8"]["n_samples"] == 60 and fd["7.8"]["n_days"] == 12
    assert fd["7.8"]["roc"]["auc"] == 1.0
    assert 110.0 < fd["7.8"]["distribution"]["otsu"] < 150.0
    assert fd["7.8"]["binarization"]["n_pos_days"] == 6 and fd["7.8"]["binarization"]["n_neg_days"] == 6
    assert len(fd["7.8"]["binarization"]["daily"]) == 12
    # 22.5 band: insufficient -> no AUC, but counts still reported.
    assert fd["22.5"]["roc"]["auc"] is None and fd["22.5"]["n_samples"] == 4
    # No frequency column -> empty.
    assert pipeline._decode_by_frequency(cv.drop(columns=["frequency_hz"]), "nrs") == {}


if __name__ == "__main__":
    test_select_biomarker_band_enforces_50hz_cap()
    print("All pipeline_stats tests passed.")
