"""Host tests for the offline RL data pipeline. All of them run with the study's venv on the Mac:

    cd BRAVO/modules && ~/.venvs/bravo-stim-rl/bin/python -m pytest StimRL/tests -q

The routine run in the server container has no SQLAlchemy: there the tests that read the snapshot
database are skipped by name (`needs_sqlalchemy`) and the rest run.
"""
import json
import os
import re

import numpy as np
import pandas as pd
import pytest

from StimRL import config as C
from StimRL import data_pipeline as D

HERE = os.path.dirname(__file__)
needs_sqlalchemy = pytest.mark.skipif(__import__("importlib").util.find_spec("sqlalchemy") is None,
                                      reason="reads the snapshot database: needs SQLAlchemy (the study's venv on the Mac)")
MODULES = os.path.abspath(os.path.join(HERE, "..", ".."))


def _sym(composite, worst=None, se=None):
    sites = {s: composite for s in C.PAIN_SITES}
    if worst is not None:
        sites["back"] = worst
    return {"sites": sites, "real": set(C.PAIN_SITES), "composite": composite,
            "worst": composite if worst is None else worst, "side_effect": se}


SAFE = (55.0, 2.0, 2.0, 100.0, 150.0)


# ---- reward ------------------------------------------------------------------------------------
def test_delta_reward_is_the_drop_in_composite_pain():
    r, term, parts = D.RewardFunction("delta")(_sym(7.0), _sym(5.5), SAFE, _sym(8.0))
    assert (r, term) == (1.5, False) and parts["symptom"] == 1.5


def test_level_reward_is_the_drop_below_the_visit_baseline():
    r, _, _ = D.RewardFunction("level")(_sym(7.0), _sym(5.5), SAFE, _sym(8.0))
    assert r == pytest.approx(2.5)


def test_worst_site_reward_halves_composite_and_worst_site_gains():
    base, nxt = _sym(8.0, worst=9.0), _sym(5.0, worst=8.0)
    mean_drop = np.mean(list(base["sites"].values())) - np.mean(list(nxt["sites"].values()))
    r, _, _ = D.RewardFunction("worst_site")(_sym(7.0), nxt, SAFE, base)
    assert r == pytest.approx(0.5 * mean_drop + 0.5 * 1.0)


@pytest.mark.parametrize("se,cost", [(0, 0.0), (1, 1.0), (2, 2.0)])
def test_side_effect_costs_follow_the_stim_optimizer_ladder(se, cost):
    r, term, _ = D.RewardFunction("delta")(_sym(6.0), _sym(6.0, se=se), SAFE, _sym(6.0))
    assert (r, term) == (-cost, False)


def test_moderate_side_effect_ends_the_episode_with_the_terminal_penalty():
    r, term, _ = D.RewardFunction("delta")(_sym(6.0), _sym(4.0, se=3), SAFE, _sym(6.0))
    assert term and r == pytest.approx(2.0 + C.TERMINAL_PENALTY)


def test_current_past_the_ceiling_ends_the_episode_with_the_terminal_penalty():
    r, term, parts = D.RewardFunction("delta")(_sym(6.0), _sym(6.0), (55, 4.6, 2.0, 100, 150), _sym(6.0))
    assert term and r == C.TERMINAL_PENALTY and parts["safety_penalty"] == C.TERMINAL_PENALTY


@pytest.mark.parametrize("amp,pen", [(3.9, 0.0), (4.0, 0.0), (4.25, -1.0), (4.5, -2.0)])
def test_proximity_penalty_rises_linearly_from_4_to_the_ceiling(amp, pen):
    r, term, _ = D.RewardFunction("delta")(_sym(6.0), _sym(6.0), (55, 1.0, amp, 100, 150), _sym(6.0))
    assert not term and r == pytest.approx(pen)


def test_rate_outside_the_device_envelope_is_a_violation():
    assert D.SafetyModel().violates((260.0, 1.0, 1.0, 100.0, 100.0))
    assert not D.SafetyModel().violates((250.0, 1.0, 1.0, 100.0, 100.0))


def test_action_scaling_round_trips():
    raw = np.array([110.0, 3.25, 0.0, 60.0, 290.0])
    assert np.allclose(D.denormalize_action(D.normalize_action(raw)), raw)


# ---- trajectories -------------------------------------------------------------------------------
def _steps(rows, file="v1", setting="clinic"):
    base = {"file": file, "setting": setting, "rating_source": "stim_tab", "left_contact": "L C+2-",
            "freq_hz": 55.0, "pw_us_Left": 100.0, "pw_us_Right": 150.0, "amp_mA_Right": 2.0,
            **{s: np.nan for s in C.PAIN_SITES}, "side_effect_score": np.nan}
    return pd.DataFrame([{**base, "row_index": i, **r} for i, r in enumerate(rows)])


@needs_sqlalchemy
def test_four_rated_steps_make_three_transitions_and_one_timeout():
    st = _steps([{"amp_mA_Left": a, "overall": p} for a, p in [(1, 7), (2, 6), (3, 5), (2.5, 6)]])
    tr = D.TrajectoryBuilder(D.RewardFunction("delta")).build(st)
    assert len(tr.transitions) == 3
    assert tr.timeouts.tolist() == [0, 0, 0, 1] and tr.terminals.sum() == 0
    assert tr.rewards[:3].tolist() == pytest.approx([1.0, 1.0, -1.0])
    ds = tr.mdp_dataset()
    assert ds.transition_count == 3


@needs_sqlalchemy
def test_a_terminal_step_splits_the_visit_into_two_episodes():
    st = _steps([{"amp_mA_Left": a, "overall": p} for a, p in [(1, 7), (4.8, 6), (2, 5), (2.5, 6)]])
    tr = D.TrajectoryBuilder(D.RewardFunction("delta")).build(st)
    assert tr.terminals.tolist() == [1, 0, 0, 0] and tr.timeouts.tolist() == [0, 0, 0, 1]
    assert tr.episode_visit == ["v1", "v1"]
    assert tr.mdp_dataset().transition_count == 3


def test_a_step_missing_rate_after_the_visit_fill_is_dropped():
    st = _steps([{"amp_mA_Left": 1, "overall": 7}, {"amp_mA_Left": 2, "overall": 6}])
    st["freq_hz"] = np.nan
    assert len(D._clean_settings(st)) == 0


@needs_sqlalchemy
def test_cross_validation_subset_keeps_only_the_named_visits():
    a = _steps([{"amp_mA_Left": x, "overall": 7 - x} for x in (1, 2, 3)], file="a")
    b = _steps([{"amp_mA_Left": x, "overall": 7 - x} for x in (1, 2)], file="b", setting="home")
    tr = D.TrajectoryBuilder(D.RewardFunction("delta")).build(pd.concat([a, b]))
    assert tr.mdp_dataset(["a"]).transition_count == 2
    assert tr.mdp_dataset(["b"]).transition_count == 1
    assert tr.transitions.at_home.tolist() == [False, False, True]


# ---- database ----------------------------------------------------------------------------------
@pytest.fixture
def tiny_snapshot(tmp_path):
    st = _steps([{"amp_mA_Left": 1, "overall": 7}, {"amp_mA_Left": 2, "overall": 6},
                 {"amp_mA_Left": 3, "overall": np.nan}])
    st.loc[2, "rating_source"] = None                       # an unrated step: exposure, not pain
    st["visit_date_ts"] = "2026-01-05T18:00:00Z"
    st.to_csv(tmp_path / "visit_steps.csv", index=False)
    ep = pd.DataFrame({"epoch": [1, 2], "t_start": ["2026-01-01T00:00:00Z", "2026-01-04T00:00:00Z"],
                       "t_end": ["2026-01-04T00:00:00Z", "2026-01-08T00:00:00Z"], "dur_h": [72, 96],
                       "freq_hz": [55, 110], "amp_mA_Left": [1.0, 2.0], "amp_mA_Right": [1.0, 2.0],
                       "pw_us_Left": [100, 100], "pw_us_Right": [150, 150], "left_contact": ["L C+2-"] * 2})
    ep.to_csv(tmp_path / "chronic_epochs.csv", index=False)
    t = (["2026-01-01T12:00:00Z", "2026-01-02T12:00:00Z", "2026-01-03T12:00:00Z"]
         + ["2026-01-04T00:00:30Z"]                          # inside the 1-minute wash-in
         + ["2026-01-05T20:00:00Z"]                          # on the visit day (California)
         + ["2026-01-06T12:00:00Z", "2026-01-06T13:00:00Z", "2026-01-07T12:00:00Z"])
    rep = pd.DataFrame({"nrs": [8, 8, 8, 0, 0, 5, 5, 5], "vas": [80] * 3 + [0, 0] + [50] * 3, "t_utc": t})
    rep.to_csv(tmp_path / "redcap_reports.csv", index=False)
    json.dump({"visit_steps": {"rows": 3}, "chronic_epochs": {"rows": 2}, "redcap_reports": {"rows": 8}},
              open(tmp_path / "manifest.json", "w"))
    return tmp_path


@needs_sqlalchemy
def test_database_rows_match_the_manifest_and_unrated_steps_are_never_returned(tiny_snapshot):
    db = D.RetrospectiveDB(str(tiny_snapshot))
    assert db.build_from_snapshot() == {"visit_steps": 3, "chronic_epochs": 2, "redcap_reports": 8}
    assert len(db.rated_steps()) == 2 and len(db.all_steps()) == 3


@needs_sqlalchemy
def test_database_refuses_a_snapshot_whose_row_count_disagrees(tiny_snapshot):
    json.dump({"visit_steps": {"rows": 4}, "chronic_epochs": {"rows": 2}, "redcap_reports": {"rows": 8}},
              open(tiny_snapshot / "manifest.json", "w"))
    with pytest.raises(ValueError, match="visit_steps"):
        D.RetrospectiveDB(str(tiny_snapshot)).build_from_snapshot()


@needs_sqlalchemy
def test_validation_skips_wash_in_and_visit_day_reports_and_needs_a_previous_period(tiny_snapshot):
    db = D.RetrospectiveDB(str(tiny_snapshot))
    db.build_from_snapshot()
    val = D.chronic_validation_set(db)
    assert len(val) == 1                                    # period 1 has no period before it
    row = val.iloc[0]
    assert row.n_reports == 3 and row.pain_nrs == 5.0 and row.pain_composite == 5.0
    assert row.prev_pain_composite == 8.0                   # period 1's three reports
    assert row.obs[0] == pytest.approx(0.8)                 # overall = mean(nrs 8, vas 80/10)
    assert row.obs[10:15] == pytest.approx((D.normalize_action([55, 1, 1, 100, 150]) + 1) / 2)


@needs_sqlalchemy
def test_latest_state_uses_the_newest_periods_own_reports_and_setting(tiny_snapshot):
    """Regression (audit 2026-10-02): it used the reports of the period BEFORE the newest."""
    db = D.RetrospectiveDB(str(tiny_snapshot))
    db.ensure_built()
    obs = D.latest_state(db, "L C+1-")
    assert obs[0] == pytest.approx(0.5)                     # newest period: nrs 5, vas 50
    assert obs[10:15] == pytest.approx((D.normalize_action([110, 2, 2, 100, 150]) + 1) / 2)
    assert obs[15 + C.CONTACT_LEVELS.index("L C+1-")] == 1.0


@needs_sqlalchemy
def test_a_setting_written_on_an_unrated_row_carries_to_the_next_rated_row(tiny_snapshot):
    """Regression (audit 2026-10-02): the fill skipped unrated rows and used an older setting."""
    st = pd.read_csv(tiny_snapshot / "visit_steps.csv")
    st["freq_hz"] = [55.0, np.nan, 130.0]
    st.loc[1, "freq_hz"] = np.nan
    st = pd.concat([st, st.iloc[[1]].assign(row_index=3, rating_source="stim_tab", overall=5.0)], ignore_index=True)
    st.to_csv(tiny_snapshot / "visit_steps.csv", index=False)
    m = json.load(open(tiny_snapshot / "manifest.json")); m["visit_steps"]["rows"] = 4
    json.dump(m, open(tiny_snapshot / "manifest.json", "w"))
    db = D.RetrospectiveDB(str(tiny_snapshot))
    db.build_from_snapshot()
    r = db.rated_steps()
    assert r.sort_values("row_index")["freq_hz"].tolist() == [55.0, 55.0, 130.0]


def test_a_sites_first_rating_mid_visit_is_not_read_as_a_change():
    """Regression (audit 2026-10-02): the composite jumped when a site was first rated."""
    st = _steps([{"amp_mA_Left": 1, "overall": 6}, {"amp_mA_Left": 2, "overall": 6, "left_leg": 9}])
    tr = D.TrajectoryBuilder(D.RewardFunction("delta")).build(st)
    assert tr.rewards[0] == pytest.approx(0.0)


@needs_sqlalchemy
def test_every_transition_matches_d3rlpys_own_transition_picker():
    st = pd.concat([_steps([{"amp_mA_Left": a, "overall": p} for a, p in [(1, 7), (2, 6), (3, 5)]], file="a"),
                    _steps([{"amp_mA_Left": a, "overall": p} for a, p in [(1, 4), (2, 3)]], file="b")])
    tr = D.TrajectoryBuilder(D.RewardFunction("delta")).build(st)
    ds = tr.mdp_dataset()
    picked = [ds.transition_picker(e, i) for e in ds.episodes for i in range(e.transition_count)]
    assert len(picked) == len(tr.transitions) == 3
    for p, (_, row) in zip(picked, tr.transitions.iterrows()):
        assert np.allclose(p.observation, row.obs) and np.allclose(p.next_observation, row.next_obs)
        assert p.reward[0] == pytest.approx(row.reward)


# ---- constants agree with the modules that own them ----------------------------------------------
def _read(rel):
    return open(os.path.join(MODULES, rel)).read()


def test_ceiling_matches_the_pi_stated_ceiling():
    src = _read("StimOptimizer/safety_ceiling.py")
    assert re.search(r'"2e3c75c00d7f4f37b53a048d195f11da": \{"Left": 4\.5, "Right": 4\.5\}', src)
    assert C.AMP_CEILING_MA == 4.5


def test_action_top_matches_the_stim_optimizer_hard_limit():
    assert re.search(r"^AMP_HARD_LIMIT_MA = 5\.0$", _read("StimOptimizer/routines/objective.py"), re.M)
    assert C.AMP_ACTION_MAX_MA == 5.0


def test_side_effect_ladder_matches_the_objective():
    src = _read("StimOptimizer/routines/objective.py")
    assert 'SE_LADDER = {"none": 0.0, "mild": 1.0, "mild_persistent": 2.0, "moderate": np.inf' in src
    assert re.search(r"^SE_THRESHOLD = 3\.0", src, re.M)
    assert C.SIDE_EFFECT_COST == {0: 0.0, 1: 1.0, 2: 2.0} and C.SIDE_EFFECT_TERMINAL_AT == 3


def test_device_envelope_matches_closed_loop_constraints():
    src = _read("ClosedLoopDeployment/constraints.py")
    assert '"pulse_width_us": (20.0, 450.0)' in src and '"rate_hz": (2.0, 250.0)' in src
    assert C.DEVICE_PW_US == (20.0, 450.0) and C.DEVICE_RATE_HZ == (2.0, 250.0)


def _load_in_child(path):
    from StimRL import data_pipeline as DD
    db = DD.RetrospectiveDB(path)
    db.ensure_built()
    return len(db.rated_steps())


@needs_sqlalchemy
def test_many_processes_loading_at_once_all_read_the_full_table(tiny_snapshot):
    """Regression (2026-10-02): three tournament processes rebuilt one SQLite file at once and two
    died with 'no such table'. Now the file is built once under a lock and swapped in whole."""
    import multiprocessing as mp
    with mp.get_context("spawn").Pool(6) as pool:
        got = pool.map(_load_in_child, [str(tiny_snapshot)] * 12)
    assert got == [2] * 12


@needs_sqlalchemy
def test_an_up_to_date_database_is_not_rebuilt(tiny_snapshot):
    db = D.RetrospectiveDB(str(tiny_snapshot))
    db.ensure_built()
    path = tiny_snapshot / "stim_rl.sqlite"
    first = os.stat(path).st_mtime_ns
    db.ensure_built()
    assert os.stat(path).st_mtime_ns == first
