"""Decisions 194 and 196 (the PI, 2026-09-17). The noise model's age penalty (0.25 x years²) was a
placeholder that a hold-out fit showed to be inert (decision 193); it is gone. A fitted time input
was built in its place the same day and removed on his ruling: this participant has had the
disease for more than three years, so any drift in the rating is an effect of the stimulation and
not a confound -- time is modelled nowhere. What remains pinned here is that observation age has
no weight at all.
"""
import numpy as np
import pandas as pd

from StimOptimizer.routines import objective as OBJ


def _two_epochs_a_year_apart():
    return pd.DataFrame({
        "epoch": [1, 2], "freq_hz": [55.0, 55.0], "amp_mA_Left": [1.6, 1.6], "amp_mA_Right": [1.2, 1.2],
        "pw_us_Left": [60.0, 60.0], "pw_us_Right": [160.0, 160.0], "n": [20, 20],
        "t0": pd.to_datetime(["2026-06-01", "2025-06-01"], utc=True), "dur_h": [200.0, 200.0],
        "left_leg_vas": [60.0, 60.0], "left_leg_vas_sd": [10.0, 10.0]})


def test_the_age_penalty_is_gone_two_identical_epochs_a_year_apart_weigh_the_same():
    d = OBJ.build_objective(_two_epochs_a_year_apart(), incumbent_epoch=1).set_index("epoch")
    assert d.loc[1, "obs_var"] == d.loc[2, "obs_var"]
    assert "c_age" not in OBJ.DEFAULTS
