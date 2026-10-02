"""Host tests for the Q-table actor-critic, the GP bandit and the shared scoring."""
import numpy as np
import pandas as pd
import pytest

from StimRL import config as C
from StimRL import data_pipeline as D
from StimRL import tabular as T
from StimRL import validation as V


def _obs(composite, contact="L C+2-", setting=(55, 2, 2, 100, 150)):
    sym = {"sites": {s: composite for s in C.PAIN_SITES}, "composite": composite, "worst": composite,
           "side_effect": 0}
    return D.encode_state(sym, np.asarray(setting, float), contact, False)


def _transitions(n=60, seed=0):
    """Synthetic data where 110 Hz at 3 mA Left always helps and 55 Hz at 1 mA never does."""
    rng = np.random.default_rng(seed)
    rows = []
    for i in range(n):
        good = i % 2 == 0
        act = (110, 3.0, 2.0, 100, 150) if good else (55, 0.5, 2.0, 100, 150)
        comp = rng.uniform(5, 8)
        nxt = comp - (2.0 if good else 0.0) + rng.normal(0, 0.1)
        rows.append({"obs": _obs(comp), "next_obs": _obs(nxt, setting=act), "reward": comp - nxt,
                     "terminal": False, **{f"act_{k}": v for k, v in zip(C.ACTION_NAMES, act)}})
    return pd.DataFrame(rows)


def test_action_cells_cover_every_band_once():
    cells = {T.action_cell((f, a, b, p, p)) for f in (20, 55, 110, 150) for a in (0.5, 2, 4)
             for b in (0.5, 2, 4) for p in (60, 200)}
    assert cells == set(range(T.N_ACTIONS))


def test_q_table_actor_critic_learns_the_better_setting():
    ac = T.TabularActorCritic(gamma=0.5).fit(_transitions())
    rec = D.denormalize_action(ac.policy(_obs(6.5)))[0]
    assert rec[0] == pytest.approx(110) and rec[1] == pytest.approx(3.0)
    good = D.normalize_action([110, 3.0, 2.0, 100, 150])[None]
    bad = D.normalize_action([55, 0.5, 2.0, 100, 150])[None]
    assert ac.q(_obs(6.5)[None], good)[0] > ac.q(_obs(6.5)[None], bad)[0] + 1.0


def test_q_table_only_recommends_settings_that_were_delivered():
    tr = _transitions()
    ac = T.TabularActorCritic().fit(tr)
    delivered = {tuple(np.round(r, 3)) for r in tr[[f"act_{k}" for k in C.ACTION_NAMES]].to_numpy(float)}
    for mode in ("exploit", "explore"):
        for comp in (2.0, 6.0, 9.5):
            rec = tuple(np.round(D.denormalize_action(ac.policy(_obs(comp), mode))[0], 3))
            assert rec in delivered


def test_explore_reading_never_picks_a_cell_past_the_ceiling():
    tr = _transitions()
    over = tr.iloc[:4].copy()
    for k, v in zip(C.ACTION_NAMES, (150, 4.8, 4.8, 200, 200)):
        over[f"act_{k}"] = v
    over["reward"] = 5.0                                    # tempting, and rarely tried
    ac = T.TabularActorCritic(beta=5.0).fit(pd.concat([tr, over], ignore_index=True))
    rec = D.denormalize_action(ac.policy(_obs(6.5), "explore"))[0]
    assert max(rec[1], rec[2]) <= C.AMP_CEILING_MA


def test_gp_bandit_prefers_the_better_setting_and_skips_unsafe_candidates():
    tr = _transitions()
    gp = T.GPBandit().fit(tr)
    rec = D.denormalize_action(gp.policy(_obs(6.5)))[0]
    assert rec[0] == pytest.approx(110, abs=1e-3)
    assert all(not D.SafetyModel().violates(D.denormalize_action(c)) for c in gp.candidates)


# ---- scoring ----------------------------------------------------------------------------------
def _val(n=30, seed=0):
    rng = np.random.default_rng(seed)
    amps = rng.uniform(0, 4, n)
    pain = 4 + amps + rng.normal(0, 0.2, n)                 # more current, more pain
    return pd.DataFrame({"obs": [_obs(6.0) for _ in range(n)], "freq_hz": 55.0, "amp_mA_Left": amps,
                         "amp_mA_Right": 2.0, "pw_us_Left": 100.0, "pw_us_Right": 150.0,
                         "pain_composite": pain})


def test_a_policy_pointing_at_the_least_painful_setting_scores_positive_and_significant():
    val = _val()
    best = D.normalize_action([55, 0.0, 2.0, 100, 150]).astype(np.float32)
    r = V.evaluate_policy("oracle", lambda o: np.repeat(best[None], len(o), 0), val, n_perm=500)
    assert r["rho_dist"] > 0.9 and r["p_dist_shuffle"] < 0.01 and r["near_minus_far"] < -2


def test_a_policy_pointing_at_the_most_painful_setting_scores_negative():
    val = _val()
    worst = D.normalize_action([55, 4.0, 2.0, 100, 150]).astype(np.float32)
    r = V.evaluate_policy("anti", lambda o: np.repeat(worst[None], len(o), 0), val, n_perm=200)
    assert r["rho_dist"] < -0.9 and r["p_dist_shuffle"] > 0.9


def test_value_ranking_uses_minus_pain_so_a_correct_critic_is_positive():
    val = _val()
    q = lambda o, a: -D.denormalize_action(a)[:, 1]          # less current is better, as in the data
    r = V.evaluate_policy("critic", V.stay_policy, val, q=q, n_perm=200)
    assert r["rho_q"] > 0.9


def test_risk_counts_recommendations_past_and_near_the_ceiling():
    val = _val(n=10)
    over = D.normalize_action([55, 4.8, 2.0, 100, 150]).astype(np.float32)
    near = D.normalize_action([55, 4.25, 2.0, 100, 150]).astype(np.float32)
    r = V.evaluate_policy("over", lambda o: np.repeat(over[None], len(o), 0), val, n_perm=50)
    assert r["share_past_limit"] == 1.0 and r["share_at_or_above_4mA"] == 1.0 and r["risk_mean"] > 1
    r = V.evaluate_policy("near", lambda o: np.repeat(near[None], len(o), 0), val, n_perm=50)
    assert r["share_past_limit"] == 0.0 and r["risk_mean"] == pytest.approx(0.5)


def test_stay_policy_returns_the_setting_in_force():
    o = _obs(6.0, setting=(110, 3.0, 1.0, 60, 290))
    assert np.allclose(D.denormalize_action(V.stay_policy(o[None]))[0], [110, 3.0, 1.0, 60, 290], atol=1e-4)


def test_equal_settings_give_exactly_tied_distances_despite_float32_states():
    """Regression (2026-10-02): float32 states split ties and moved rank correlations."""
    s = (110.0, 3.3, 1.7, 60.0, 130.0)
    o = _obs(6.0, setting=s).astype(np.float32)
    d = V.action_distance(V.stay_policy(np.stack([o, o])), D.normalize_action(np.array([s, s])))
    assert d[0] == d[1] == 0.0
    d2 = V.action_distance(V.stay_policy(o[None]).astype(np.float32), D.normalize_action([[55, 3.3, 1.7, 60, 130]]))
    d3 = V.action_distance(V.stay_policy(o[None]), D.normalize_action([[55, 3.3, 1.7, 60, 130]]))
    assert d2[0] == d3[0]


def test_near_minus_far_puts_tied_distances_in_the_same_third_whatever_their_order():
    val = _val(n=9)
    val["pain_composite"] = [1, 2, 3, 4, 5, 6, 7, 8, 9]
    rec = D.normalize_action([55, 0.0, 2.0, 100, 150]).astype(np.float32)
    amps = [0, 0, 0, 0, 2, 2, 4, 4, 4]                 # four periods tie at the smallest distance
    for perm in ([0, 1, 2, 3, 4, 5, 6, 7, 8], [3, 2, 1, 0, 5, 4, 8, 7, 6]):
        v = val.iloc[perm].reset_index(drop=True)
        v["amp_mA_Left"] = [amps[i] for i in perm]
        r = V.evaluate_policy("x", lambda o: np.repeat(rec[None], len(o), 0), v, n_perm=20)
        assert r["near_minus_far"] == pytest.approx(np.mean([1, 2, 3, 4]) - np.mean([7, 8, 9]))
