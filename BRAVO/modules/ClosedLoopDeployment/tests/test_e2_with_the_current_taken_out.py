"""E2 read again with the stimulation current in force taken out of the band power.

WHY. E2 is the edge that says the band tells this patient's high pain from their low pain. On the
left lead of the live participant every band that rises with pain also rests on the current the
stimulator was delivering at the time (decision 232, and decision 234 measured it on the grid:
+0.08 to +0.20 plainly, +0.01 to +0.12 once the current is taken out). The Closed-Loop page today
prints E2 with no term for the current at all and only warns about it in words (decision 235). This
is the measurement behind that warning.

WHAT IS PINNED HERE, and every case is pinned on the value it produces:

  * a constructed record where the current drives BOTH the band power and the pain: the plain
    reading is far above coin flipping and the adjusted one collapses onto it;
  * a constructed record where the band carries a real pain relationship of its own and the current
    moves independently: the adjusted reading stays away from coin flipping;
  * the default is OFF, and a call that does not ask for the adjustment returns exactly what it
    returned before, to the last bit;
  * the two refusals are stated rather than computed around: a band that moves almost exactly with
    the current gets no adjusted number (that is itself the finding), and a current that never
    moves has nothing to take out;
  * the exported-table route says plainly that it cannot make the adjustment, because the exported
    table carries one row per band and no per-sample current.
"""
import numpy as np
import pandas as pd

try:
    from modules.ClosedLoopDeployment import edges as E
    from modules.Biomarkers.routines import analytics as AN
except ImportError:                                              # pragma: no cover - host spelling
    from ClosedLoopDeployment import edges as E
    from Biomarkers.routines import analytics as AN


CH = "ONE_THREE_LEFT"
FC = 24.5
AMP = "amp_mA_Left"


def _table(power, pain, reports, current, *, channel=CH, center_hz=FC):
    """The per-sample table this module builds: one row per spectral sample."""
    return pd.DataFrame({
        "channel": [channel] * len(power),
        "center_hz": [float(center_hz)] * len(power),
        "power_linear": np.asarray(power, dtype=float),
        "nrs": np.asarray(pain, dtype=float),
        "report_id": list(reports),
        AMP: np.asarray(current, dtype=float),
    })


def _current_drives_both(n_reports=40, samples_per_report=6, seed=3):
    """Pain and band power are both read off the current; the band says nothing of its own.

    The current walks over the range the record actually holds (0 to 4 mA). Pain rises with it and
    so does the band's power, so the band separates high pain from low pain very well while
    carrying no information the current does not already carry.
    """
    rng = np.random.default_rng(seed)
    cur = np.linspace(0.0, 4.0, n_reports)
    power, pain, reports, current = [], [], [], []
    for i, c in enumerate(cur):
        pain_i = 2.0 * c + rng.normal(0, 0.15)
        for _ in range(samples_per_report):
            # The band's own scatter is deliberately large enough that the band is not simply the
            # current relabelled: 86% of its movement is the current, below the 98% at which this
            # code refuses to adjust at all (the next test pins that refusal).
            power.append(3.0 * c + rng.normal(0, 1.5))
            pain.append(pain_i)
            reports.append(f"r{i}")
            current.append(c)
    return _table(power, pain, reports, current)


def _band_carries_pain_current_independent(n_reports=40, samples_per_report=6, seed=5):
    """The band tracks pain; the current moves on its own and touches neither."""
    rng = np.random.default_rng(seed)
    power, pain, reports, current = [], [], [], []
    for i in range(n_reports):
        pain_i = float(rng.integers(0, 11))
        c = float(rng.choice([0.0, 1.0, 2.0, 3.0, 4.0]))
        for _ in range(samples_per_report):
            power.append(0.6 * pain_i + rng.normal(0, 2.0))
            pain.append(pain_i)
            reports.append(f"r{i}")
            current.append(c)
    return _table(power, pain, reports, current)


# --- the measurement -------------------------------------------------------------------------
def test_a_current_that_drives_both_collapses_the_adjusted_reading_onto_coin_flipping():
    T = _current_drives_both()
    out = AN.band_pain_auc_from_table(T, channel=CH, center_hz=FC, covariate_column=AMP,
                                      n_boot=200, seed=0)
    adj = out["covariate_adjusted"]
    assert out["auc"] > 0.9, out["auc"]
    assert adj["available"] is True, adj
    assert abs(adj["auc"] - 0.5) < 0.15, adj["auc"]
    assert abs(adj["partial_r"]) < 0.2, adj["partial_r"]


def test_a_band_with_its_own_pain_relationship_survives_the_adjustment():
    T = _band_carries_pain_current_independent()
    out = AN.band_pain_auc_from_table(T, channel=CH, center_hz=FC, covariate_column=AMP,
                                      n_boot=200, seed=0)
    adj = out["covariate_adjusted"]
    assert out["auc"] > 0.7, out["auc"]
    assert adj["auc"] > 0.7, adj["auc"]
    assert adj["partial_r"] > 0.3, adj["partial_r"]


def test_both_readings_carry_an_interval_resampled_on_whole_pain_reports():
    T = _band_carries_pain_current_independent()
    out = AN.band_pain_auc_from_table(T, channel=CH, center_hz=FC, covariate_column=AMP,
                                      n_boot=200, seed=0)
    adj = out["covariate_adjusted"]
    assert adj["auc_low"] < adj["auc"] < adj["auc_high"]
    assert adj["partial_r_low"] < adj["partial_r"] < adj["partial_r_high"]
    assert adj["resampling_unit"] == "one pain report"


# --- default off -----------------------------------------------------------------------------
def test_the_adjustment_is_off_by_default_and_the_plain_answer_does_not_move():
    T = _band_carries_pain_current_independent()
    plain = AN.band_pain_auc_from_table(T, channel=CH, center_hz=FC, n_boot=200, seed=0)
    asked = AN.band_pain_auc_from_table(T, channel=CH, center_hz=FC, covariate_column=AMP,
                                        n_boot=200, seed=0)
    assert "covariate_adjusted" not in plain
    for k, v in plain.items():
        if isinstance(v, float):
            assert asked[k] == v, k
        else:
            assert asked[k] == v, k


# --- the two refusals ------------------------------------------------------------------------
def test_a_band_that_is_almost_exactly_the_current_gets_no_adjusted_number():
    """Decision 237's rule, in its second home: when taking the current out leaves noise, say that
    the band IS the current rather than printing a number made of what is left."""
    rng = np.random.default_rng(11)
    cur = np.repeat(np.linspace(0.0, 4.0, 30), 5)
    power = 3.0 * cur + rng.normal(0, 0.002, cur.size)
    pain = np.repeat(rng.integers(0, 11, 30).astype(float), 5)
    reports = np.repeat([f"r{i}" for i in range(30)], 5)
    out = AN.band_pain_auc_from_table(_table(power, pain, reports, cur), channel=CH, center_hz=FC,
                                      covariate_column=AMP, n_boot=200, seed=0)
    adj = out["covariate_adjusted"]
    assert adj["available"] is False
    assert adj["auc"] is None and adj["partial_r"] is None
    assert adj["nearly_the_covariate"] is True
    assert "almost exactly" in adj["why"]


def test_a_current_that_never_moves_has_nothing_to_take_out():
    T = _band_carries_pain_current_independent()
    T[AMP] = 2.0
    out = AN.band_pain_auc_from_table(T, channel=CH, center_hz=FC, covariate_column=AMP,
                                      n_boot=200, seed=0)
    adj = out["covariate_adjusted"]
    assert adj["available"] is False
    assert adj["auc"] is None
    assert "constant" in adj["why"]


def test_a_column_that_is_not_on_the_table_is_named_in_the_refusal():
    T = _band_carries_pain_current_independent()
    out = AN.band_pain_auc_from_table(T, channel=CH, center_hz=FC,
                                      covariate_column="amp_mA_Right", n_boot=200, seed=0)
    adj = out["covariate_adjusted"]
    assert adj["available"] is False
    assert "amp_mA_Right" in adj["why"]


# --- the edge itself -------------------------------------------------------------------------
def test_state_edge_carries_the_adjusted_reading_when_it_is_asked_for():
    T = _current_drives_both()
    e = E.state_edge(T, channel=CH, center_hz=FC, n_boot=200, adjust_for_column=AMP)
    assert e.adjusted is not None
    assert e.adjusted["available"] is True
    assert abs(e.adjusted["estimate"] - 0.0) < 0.15, e.adjusted["estimate"]
    # The estimate is shifted by 0.5 exactly as E2's own is, so "excludes zero" keeps meaning
    # "beats coin flipping" on both numbers.
    assert abs(e.adjusted["estimate"] - (e.adjusted["auc"] - 0.5)) < 1e-12
    assert AMP in e.adjusted["adjusted_for"]
    assert "taken out" in e.note


def test_state_edge_is_unchanged_when_the_adjustment_is_not_asked_for():
    T = _current_drives_both()
    plain = E.state_edge(T, channel=CH, center_hz=FC, n_boot=200)
    asked = E.state_edge(T, channel=CH, center_hz=FC, n_boot=200, adjust_for_column=AMP)
    assert plain.adjusted is None
    assert plain.estimate == asked.estimate
    assert plain.ci == asked.ci
    assert plain.p == asked.p


def test_the_exported_table_route_says_it_cannot_make_the_adjustment():
    """The table the biomarker page exports has one row per band and no per-sample current, so the
    adjustment cannot be made from it. Saying so is not the same as reporting no effect."""
    exported = pd.DataFrame([{
        "channel": CH, "band_center_hz": FC, "auc": 0.62, "auc_low": 0.55, "auc_high": 0.70,
        "answer": AN.BAND_PAIN_ESTABLISHED, "p_two_sided": 0.02, "n_spectral_samples": 900,
        "n_pain_reports": 40, "why": "", "pain_split_rule": "thirds",
    }])
    e = E.state_edge(exported, channel=CH, center_hz=FC, adjust_for_column=AMP)
    assert e.adjusted is not None
    assert e.adjusted["available"] is False
    assert "exported" in e.adjusted["why"]
