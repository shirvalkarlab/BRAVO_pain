"""The aperiodic (1/f) fit is gone (decision 206).

`remove_aperiodic` fitted the 1/f slope of each spectrum on a log-log axis and returned what was
left; the only caller was the pain correlation's `transform="fooof"`, which no page and no request
could select -- only the command-line runner could, and nothing runs it. On the PI's rule of
2026-09-19 (decision 202: log power enters no calculation) he had it deleted rather than kept as a
named exception. The device thresholds raw band power, so a band chosen on "power above the 1/f
background" could not have been programmed as chosen in any case.
"""
import ast
import pathlib
import sys

import numpy as np

_BRAVO_ROOT = pathlib.Path(__file__).resolve().parents[3]
if str(_BRAVO_ROOT) not in sys.path:
    sys.path.insert(0, str(_BRAVO_ROOT))

from modules.Biomarkers.routines import streaming_psd
from modules.Biomarkers import pipeline

_SRC = pathlib.Path(streaming_psd.__file__)


def test_the_aperiodic_fit_no_longer_exists():
    assert not hasattr(streaming_psd, "remove_aperiodic")
    tree = ast.parse(_SRC.read_text())
    names = sorted(n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)
                   and "aperiodic" in n.name.lower())
    assert names == [], names
    src = _SRC.read_text()
    assert "specparam" not in src and 'transform == "fooof"' not in src   # history may name it


def test_the_pain_correlation_refuses_the_fooof_transform():
    from modules.Biomarkers import adapter
    fs = 250.0
    recs = []
    for k in range(5):
        rng = np.random.default_rng(k)
        n = int(8 * fs)
        t = np.arange(n) / fs
        data = np.column_stack([np.sin(2 * np.pi * 20 * t) + 0.3 * rng.standard_normal(n),
                                np.sin(2 * np.pi * 30 * t) + 0.3 * rng.standard_normal(n)])
        recs.append({"SamplingRate": fs, "ChannelNames": ["ZERO_TWO_LEFT", "ZERO_TWO_RIGHT"],
                     "Data": data, "Missing": np.zeros_like(data),
                     "StartTime": 1_700_000_000.0 + 600.0 * k, "Duration": n / fs})
    streams = adapter.bravo_timedomain_recordings_to_streams(recs)
    try:
        streaming_psd.compute_psd_pain_correlation(
            streams, np.array([2.0, 4.0, 6.0, 8.0, 9.0]), ["ZERO_TWO_LEFT", "ZERO_TWO_RIGHT"],
            transform="fooof")
    except ValueError:
        return
    raise AssertionError("transform='fooof' was accepted")


def test_the_command_line_runner_offers_no_fooof_choice():
    src = pathlib.Path(pipeline.__file__).read_text()
    assert "fooof" not in src.lower(), "pipeline.py still names the fooof transform"
