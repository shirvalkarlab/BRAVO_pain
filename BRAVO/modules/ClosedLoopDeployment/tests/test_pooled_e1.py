"""E1, the current-to-power edge, from the stored pooled titration slope (redesign decision 9,
decision 124 in the log, the PI's choice on 2026-09-11).

Two rules held here: the pipeline swaps E1 for the pooled slope ONLY when a slope is stored, and
keeps the historical setting-epoch estimate on the report beside it; and the curvature answer
travels in the edge's note as a caveat, never as a second number the sign test could read.
"""
import numpy as np
import pandas as pd

try:
    from modules.ClosedLoopDeployment import pipeline as PL, edges as E, adapter as AD
except ImportError:                                              # pragma: no cover
    from ClosedLoopDeployment import pipeline as PL, edges as E, adapter as AD


def _row(**over):
    r = {"pooled_direction": "band power falls as current rises", "pooled_slope_per_mA": -3.6,
         "pooled_slope_stderr": 1.2, "pooled_slope_p": 0.01, "n": 13, "n_visits": 4,
         "verdict": "ok", "curves": False, "peaks_inside": False, "peak_mA": float("nan"),
         "p_curvature": 0.41, "r2_linear": 0.6, "r2_quadratic": 0.61}
    r.update(over)
    return r


def test_the_pooled_edge_carries_the_slope_its_interval_and_the_run_count():
    e = E.pooled_actuation_edge(_row(), scale="power_linear")
    assert e.name == "E1" and e.estimate == -3.6 and e.p == 0.01
    assert e.ci == (-3.6 - 1.96 * 1.2, -3.6 + 1.96 * 1.2)
    assert e.n == 13 and e.n_clusters == 4 and "run of rising current" in e.cluster_unit
    assert e.sign == -1 and e.resolved is True
    assert "POOLED ACROSS 4 RUNS" in e.note and "No bend was detected" in e.note
    assert e.confounded_by == []


def test_a_detected_bend_is_a_caveat_in_the_note_and_a_named_confounder_never_a_number():
    e = E.pooled_actuation_edge(_row(curves=True, p_curvature=0.004, peaks_inside=True, peak_mA=2.6))
    assert "bend across the tested currents was detected (p = 0.004)" in e.note
    assert "peak near 2.6 mA" in e.note
    assert "curvature" in e.confounded_by
    assert e.estimate == -3.6, "the slope itself is untouched; the bend qualifies it in words"


def test_no_stored_slope_gives_an_unresolved_edge_that_says_why():
    e = E.pooled_actuation_edge(_row(pooled_slope_per_mA=float("nan"), pooled_slope_p=float("nan"),
                                     verdict="not assessed: 5 usable points"))
    assert e.estimate is None and e.resolved is False
    assert "not assessed: 5 usable points" in e.note


def test_few_runs_are_named_as_a_confounder():
    e = E.pooled_actuation_edge(_row(n_visits=2))
    assert "few runs" in e.confounded_by


def _toy_table(n_epochs=6, per_epoch=5, slope=-2.0, seed=0):
    rng = np.random.default_rng(seed)
    rows = []
    for k in range(n_epochs):
        amp = 1.0 + k * 0.5
        for _ in range(per_epoch):
            lin = 10.0 + slope * amp + rng.normal(0, 0.2)
            rows.append({"t": float(k), "channel": "CH", "setting_epoch": k, "center_hz": 20.5,
                         "amp_mA_Left": amp, "power_linear": lin,
                         # the manifest's scale check reads both scales; the pipeline is the
                         # thing under test, so the table carries what the real one carries
                         "power_mean_of_log": float(np.log10(max(lin, 1e-6))),
                         "nrs": 5.0 + 0.5 * amp + rng.normal(0, 0.2), "report_id": f"r{k}"})
    return pd.DataFrame(rows)


def _run_pipeline(monkeypatch, pooled_e1):
    T = _toy_table()
    monkeypatch.setattr(AD, "joined_table_cached", lambda *a, **k: T)
    monkeypatch.setattr(PL, "_optional", lambda name: None)      # no device rules, no replay
    return PL.run("p", psd_frame=pd.DataFrame({"x": [1]}), epochs=pd.DataFrame({"x": [1]}),
                  design_matrix=None, candidates=[{"channel": "CH", "center_hz": 20.5}],
                  pooled_e1=pooled_e1)


def test_the_pipeline_uses_the_pooled_slope_and_keeps_the_historical_edge(monkeypatch):
    rep = _run_pipeline(monkeypatch, _row())
    assert rep.edges["E1"].estimate == -3.6
    assert "run of rising current" in rep.edges["E1"].cluster_unit
    hist = rep.edges_historical["E1"]
    assert hist.cluster_unit == "setting epoch", "the setting-epoch estimate must be kept"
    assert hist.estimate is not None and hist.estimate != -3.6


def test_without_a_stored_slope_the_pipeline_keeps_the_setting_epoch_edge(monkeypatch):
    for pooled in (None, {}, _row(pooled_slope_per_mA=float("nan"))):
        rep = _run_pipeline(monkeypatch, pooled)
        assert rep.edges["E1"].cluster_unit == "setting epoch"
        assert rep.edges_historical == {}
