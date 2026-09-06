"""Production plotting contract: real figure JSON, no browser or private data.

Plotly is a required runtime dependency. This module intentionally uses a normal import rather
than importorskip, so the portable deployment gate fails if the dependency is missing.
"""
import json
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
import plotly
import plotly.graph_objects as go
import pytest

from StimOptimizer import bravo_service, pipeline
from StimOptimizer.routines import plots

EXPECTED = {"posterior_surface", "acquisition", "trajectory", "dual_model", "coverage"}


@pytest.fixture(scope="module")
def fitted_report():
    n = 14
    rng = np.random.default_rng(417)
    frame = pd.DataFrame({
        "epoch": np.arange(1, n + 1, dtype=float),
        "t0": pd.date_range("2026-01-01", periods=n, freq="7D", tz="UTC"),
        "freq_hz": np.tile([10., 55., 110., 165.], 4)[:n],
        "amp_mA_Left": np.round(np.linspace(1., 2.5, n), 1),
        "amp_mA_Right": np.round(np.linspace(.8, 2., n), 1),
        "pw_us_Left": np.full(n, 60.), "n": np.full(n, 6.), "dur_h": np.full(n, 120.),
        "left_leg_vas": np.round(50 + 10 * rng.standard_normal(n), 1),
        "left_leg_vas_sd": np.full(n, 12.),
    })
    return pipeline.run(frame, sites=("left_leg", "back"), hemispheres=("Left",),
                        outdir=None, render_figures=False, data_horizon="synthetic plotting regression",
                        washin_min=1., n_batches=1, q=2)


def test_runtime_dependency_is_declared_and_plain_array_compatible():
    requirements = Path(__file__).resolve().parents[3] / "requirements.txt"
    assert "plotly==5.24.1" in requirements.read_text().splitlines()
    assert plotly.__version__ == "5.24.1"


def test_all_fitted_arms_emit_five_real_plain_array_figures(fitted_report):
    assert set(fitted_report.arms) == {"left_leg__Left"}
    assert "back__Left" in fitted_report.manifest["skipped"]  # absent metric remains a normal skip
    for arm in fitted_report.arms.values():
        result = bravo_service._plotly_figures(arm.ctx)
        assert set(result["figures"]) == EXPECTED
        assert result["figure_errors"] == {}
        for figure in result["figures"].values():
            assert figure["data"]
            assert figure["layout"]
            json.dumps(figure, allow_nan=False)
            for trace in figure["data"]:
                for axis in ("x", "y", "z"):
                    if axis in trace:
                        assert isinstance(trace[axis], list), "Frontend Plotly 2.x requires plain arrays"


@pytest.mark.parametrize("failure", ["missing", "exception", "empty"])
def test_one_broken_figure_reports_its_reason_and_keeps_other_figures(failure):
    valid = lambda ctx: go.Figure(go.Scatter(x=[1], y=[2]))
    replacements = {name: valid for name in ["fig1_posterior_surface", "fig2_acquisition_decomposition",
                    "fig3_search_trajectory", "fig4_dual_model", "fig5_coverage_map"]}
    if failure == "missing":
        replacements["fig3_search_trajectory"] = None
    elif failure == "exception":
        def broken(ctx):
            raise ValueError("private participant input /private/source/record.csv")
        replacements["fig3_search_trajectory"] = broken
    else:
        replacements["fig3_search_trajectory"] = lambda ctx: go.Figure()
    with patch.multiple(plots, **replacements):
        result = bravo_service._plotly_figures(object())
    assert set(result["figures"]) == EXPECTED - {"trajectory"}
    assert set(result["figure_errors"]) == {"trajectory"}
    error = result["figure_errors"]["trajectory"]
    assert error["builder"] == "fig3_search_trajectory"
    assert error["error_type"] == ("MissingBuilder" if failure == "missing" else "ValueError")
    assert error["message"]
    assert "private participant" not in error["message"]
    assert "/private/" not in error["message"]
