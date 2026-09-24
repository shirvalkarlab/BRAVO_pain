"""No log power on the pooled full-spectrum path or in the pain correlation (decision 204).

The PI's rule of 2026-09-19 (decision 202): log power enters no calculation anywhere. Decision 202
cleared the E1 path; this file pins the two sites he asked for next, in his order.

1. THE STABILITY TEST. Its input is the pooled full-spectrum detail, and until now that detail was
   built from an assembled matrix that held every spectrum as decibels (``10 * log10(power)`` under
   the field ``logX``), standardised those decibels within channel and source, and averaged them
   over the band. The stability test, the mixed-model inference, the per-era ROC and the drill-down
   band feature all read that average. Now the matrix holds raw power under ``X`` (a stale reader
   that still asks for ``logX`` fails with a KeyError instead of reading raw power as decibels), the
   detail standardises raw power, and the ``prelog`` flag with its three ``10 * log10`` fallbacks is
   gone.

2. THE PAIN CORRELATION. ``compute_psd_pain_correlation`` correlated ``10 * log10`` of the spectrum
   with the pain score by default; that is what the Biomarkers page's one-line band summary and the
   sliding correlation heat map were built on. It now correlates the raw spectrum; the three
   logarithmic transforms are refused rather than silently mapped to raw.

The source guards read the syntax tree rather than importing, so they run on both runners.
"""
import ast
import pathlib
import sys

import numpy as np

_BRAVO_ROOT = pathlib.Path(__file__).resolve().parents[3]
if str(_BRAVO_ROOT) not in sys.path:
    sys.path.insert(0, str(_BRAVO_ROOT))

from modules.Biomarkers.routines import analytics
from modules.Biomarkers.routines import streaming_psd

_ROUTINES = pathlib.Path(__file__).resolve().parents[1] / "routines"
_SERVICE = pathlib.Path(__file__).resolve().parents[1] / "bravo_service.py"


# --- 1. the assembled matrix and the pooled detail -------------------------------------------------

F5 = np.array([10.0, 20.0, 30.0, 40.0, 50.0])


def _rows():
    """Three spectra on one channel; each bin doubles from row to row (1, 2, 4 at 10 Hz)."""
    base = np.array([1.0, 10.0, 100.0, 1000.0, 10000.0])
    return [
        {"channel": "ZERO_TWO_LEFT", "source": "TD streaming", "t": 1000.0 * (k + 1), "freq": F5,
         "power": base * (2.0 ** k), "dur": 30.0} for k in range(3)
    ]


def test_the_assembled_matrix_holds_raw_power_under_X_and_no_logX():
    mat = streaming_psd.psd_rows_to_matrix(_rows(), f_set=F5)
    assert mat is not None
    assert "logX" not in mat, sorted(mat)
    assert "X" in mat, sorted(mat)
    expect = np.vstack([r["power"] for r in _rows()])
    assert np.array_equal(mat["X"], expect), mat["X"]


def test_the_pooled_detail_standardises_raw_power_and_carries_no_prelog_flag():
    mat = streaming_psd.psd_rows_to_matrix(_rows(), f_set=F5)
    assert mat is not None
    det = streaming_psd.build_pooled_detail_from_matrix(
        mat, np.array([1000.0, 2000.0, 3000.0]), np.array([2.0, 5.0, 8.0]),
        tolerance_min=1.0, aggregate="all", max_per_rating=3, refractory_min=0.0,
        match_direction="nearest")
    assert "prelog" not in det, sorted(det)
    assert "log" not in str(det["transform"]), det["transform"]
    # standardised RAW power: per frequency, (x - mean) / sd (population sd, as the builder
    # has always used), on 1, 2, 4 at 10 Hz
    x = np.array([1.0, 2.0, 4.0])
    z = (x - x.mean()) / x.std()
    got = np.asarray(det["psd"])[:, 0, 0]
    assert np.allclose(got, z, rtol=0, atol=1e-12), (got, z)
    # and NOT the standardised decibels, which would order the same but space differently
    zdb = (10 * np.log10(x) - np.mean(10 * np.log10(x))) / np.std(10 * np.log10(x))
    assert not np.allclose(got, zdb, rtol=0, atol=1e-6), "the detail still standardises decibels"


def test_the_band_feature_is_the_raw_band_mean_not_its_decibel_expression():
    """A detail without any flag is read as raw power: constant 4.0 across the band comes back as
    4.0, not 10*log10(4) = 6.02."""
    f = np.linspace(1.0, 40.0, 40)
    psd = np.full((6, 1, f.size), 4.0)
    det = {"f_set": f, "psd": psd, "labels": np.arange(6.0),
           "chan_order": ["ZERO_TWO_LEFT"], "times": [f"2026-01-0{i + 1} 10:00:00" for i in range(6)]}
    bp, _labels, _rg, _t = analytics._band_feature_from_detail(det, "ZERO_TWO_LEFT", 20.0, 5.0)
    assert np.array_equal(bp, np.full(6, 4.0)), bp


def test_the_feature_name_written_on_every_exported_row_says_raw_power():
    det = {"f_set": np.array([1.0]), "psd": np.zeros((1, 1, 1)), "labels": np.array([1.0]),
           "chan_order": ["ZERO_TWO_LEFT"]}
    name = analytics._pooled_power_feature_name(det)
    assert "logarithm of" not in name.lower() and "decibel" not in name.lower(), name
    assert "raw power" in name.lower(), name


def _function_nodes(path, names):
    tree = ast.parse(path.read_text())
    return {n.name: n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name in names}


def _calls_log(fn_node):
    """Every attribute call named log10 / log2 / log inside one function, by line."""
    found = []
    for n in ast.walk(fn_node):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) \
                and n.func.attr in ("log10", "log2", "log"):
            found.append(n.lineno)
        if isinstance(n, ast.Constant) and n.value == "prelog":
            found.append(n.lineno)
    return found


def test_no_reader_of_the_pooled_detail_takes_a_logarithm_or_reads_prelog():
    names = {"_band_feature_from_detail", "band_mixedmodel_inference", "band_stim_stability",
             "deployment_roc_by_era", "_pooled_power_feature_name"}
    fns = _function_nodes(_ROUTINES / "analytics.py", names)
    assert set(fns) == names, f"missing: {names - set(fns)}"
    bad = {k: _calls_log(v) for k, v in fns.items() if _calls_log(v)}
    assert bad == {}, f"logarithm or prelog still read at: {bad}"


def test_neither_matrix_builder_nor_pooled_detail_builder_takes_a_logarithm():
    names = {"psd_rows_to_matrix", "build_pooled_detail_from_matrix", "compute_psd_pain_correlation"}
    fns = _function_nodes(_ROUTINES / "streaming_psd.py", names)
    assert set(fns) == names, f"missing: {names - set(fns)}"
    bad = {k: _calls_log(v) for k, v in fns.items() if _calls_log(v)}
    assert bad == {}, f"logarithm or prelog still present at: {bad}"


def test_the_matrix_store_key_names_the_power_scale_so_no_decibel_entry_is_served():
    """An entry assembled under the old decibel rule must never be served as raw power: the key
    carries a scale token, and the version names raw power."""
    from modules.Biomarkers import bravo_service as bs
    assert getattr(bs, "_MATRIX_POWER_SCALE_VERSION", None) == "v2_raw_power", \
        getattr(bs, "_MATRIX_POWER_SCALE_VERSION", None)
    fn = _function_nodes(_SERVICE, {"_psd_matrix_signature_orm"})["_psd_matrix_signature_orm"]
    used = any(isinstance(n, ast.Name) and n.id == "_MATRIX_POWER_SCALE_VERSION" for n in ast.walk(fn))
    assert used, "the matrix signature does not fold the power-scale version in"
    # every version from raw power on (v3); v4 (2026-09-24) added the clinic-sheet switch to the
    # shared setup and is raw power too -- what must never come back is the decibel rule before v3
    assert bs.STABILITY_GRID_RULE_VERSION in ("v3_raw_power_feature", "v4_sheet_ratings_in_setup"), \
        bs.STABILITY_GRID_RULE_VERSION


# --- 2. the pain correlation ---------------------------------------------------------------------

def _streams(n_epochs=5):
    """Five synthetic two-channel recordings through the adapter's own reshape (the same fixture
    `test_adapter.py` uses), so the Welch step sees exactly the shape the page feeds it."""
    from modules.Biomarkers import adapter
    fs = 250.0
    recs = []
    for k in range(n_epochs):
        rng = np.random.default_rng(k)
        n = int(8 * fs)
        t = np.arange(n) / fs
        data = np.column_stack([np.sin(2 * np.pi * 20 * t) + 0.3 * rng.standard_normal(n),
                                np.sin(2 * np.pi * 30 * t) + 0.3 * rng.standard_normal(n)])
        recs.append({"SamplingRate": fs, "ChannelNames": ["ZERO_TWO_LEFT", "ZERO_TWO_RIGHT"],
                     "Data": data, "Missing": np.zeros_like(data),
                     "StartTime": 1_700_000_000.0 + 600.0 * k, "Duration": n / fs})
    return adapter.bravo_timedomain_recordings_to_streams(recs)


def test_the_pain_correlation_correlates_the_raw_spectrum_by_default():
    labels = np.array([2.0, 4.0, 6.0, 8.0, 9.0])
    out = streaming_psd.compute_psd_pain_correlation(
        _streams(), labels, ["ZERO_TWO_LEFT", "ZERO_TWO_RIGHT"])
    assert out["transform"] == "raw", out["transform"]
    feat, psd = np.asarray(out["feature"]), np.asarray(out["psd"])
    m = np.isfinite(psd)
    assert m.any()
    assert np.array_equal(feat[m], psd[m]), "the correlated feature is not the raw spectrum"


def test_the_pain_correlation_refuses_a_logarithmic_transform():
    labels = np.array([2.0, 4.0, 6.0, 8.0, 9.0])
    for bad in ("log", "log_zscore", "relative_power_log"):
        try:
            streaming_psd.compute_psd_pain_correlation(
                _streams(), labels, ["ZERO_TWO_LEFT", "ZERO_TWO_RIGHT"], transform=bad)
        except ValueError:
            continue
        raise AssertionError(f"transform={bad!r} was accepted")


def test_the_pipeline_defaults_carry_no_log_transform():
    """The live caller is ``pipeline.run_biomarker`` -> ``run_timedomain_branch``; their defaults
    are what the page gets."""
    from modules.Biomarkers import pipeline
    import inspect
    for fn in (pipeline.run_biomarker, pipeline.run_timedomain_branch, pipeline.run_streaming_biomarker):
        d = inspect.signature(fn).parameters["transform"].default
        assert d == "raw", (fn.__name__, d)


def test_no_runtime_string_in_analytics_calls_the_band_feature_log_or_decibel():
    """Sentences the page could print (``feature_units``, outlier ``rule`` strings) must not
    describe the feature as log or dB now that it is raw power. Docstrings are left out."""
    tree = ast.parse((_ROUTINES / "analytics.py").read_text())
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Module)):
            body = getattr(node, "body", [])
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
                    and isinstance(body[0].value.value, str):
                docstrings.add(id(body[0].value))
    bad = sorted({n.value for n in ast.walk(tree)
                  if isinstance(n, ast.Constant) and isinstance(n.value, str)
                  and id(n) not in docstrings
                  and ("log/dB" in n.value or "log10 band power" in n.value
                       or "logarithm of power" in n.value)})
    assert bad == [], f"runtime strings still call the feature log or dB: {bad}"
