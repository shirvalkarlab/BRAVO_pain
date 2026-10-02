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
    """Regression (audit 2026-10-02): per-column medians were untried combinations."""
    tr = _transitions()
    extra = tr.iloc[:6].copy()                    # same cell as the good setting, other combinations
    for i, (f, al, pl) in enumerate([(100, 2.6, 60), (115, 3.4, 110), (90, 2.8, 70),
                                     (110, 3.0, 100), (120, 3.2, 90), (95, 2.7, 80)]):
        extra.iloc[i, extra.columns.get_loc("act_freq_hz")] = f
        extra.iloc[i, extra.columns.get_loc("act_amp_mA_Left")] = al
        extra.iloc[i, extra.columns.get_loc("act_pw_us_Left")] = pl
    tr = pd.concat([tr, extra], ignore_index=True)
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
    over = tr.iloc[:2].copy()
    over["act_amp_mA_Left"] = 4.8                              # an unsafe delivered setting
    tr = pd.concat([tr, over], ignore_index=True)
    gp = T.GPBandit().fit(tr)
    assert len(gp.candidates) == 2                             # 3 delivered, 1 past the ceiling
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
                         "pain_composite": pain, "prev_pain_composite": 6.0, "left_contact": "L C+2-"})


def test_a_policy_pointing_at_the_least_painful_setting_scores_positive_and_significant():
    val = _val()
    best = D.normalize_action([55, 0.0, 2.0, 100, 150]).astype(np.float32)
    r = V.evaluate_policy("oracle", lambda o: np.repeat(best[None], len(o), 0), val, n_perm=500)
    assert r["rho_dist_change"] > 0.9 and r["p_dist_change_shift"] <= 1 / 30 + 1e-9
    assert r["near_minus_far_change"] < -2 and r["rho_dist"] > 0.9


def test_a_policy_pointing_at_the_most_painful_setting_scores_negative():
    val = _val()
    worst = D.normalize_action([55, 4.0, 2.0, 100, 150]).astype(np.float32)
    r = V.evaluate_policy("anti", lambda o: np.repeat(worst[None], len(o), 0), val, n_perm=200)
    assert r["rho_dist_change"] < -0.9 and r["p_dist_change_shift"] > 0.9


def test_a_critic_that_predicts_which_switches_help_scores_positive_rho_adv():
    val = _val()
    q = lambda o, a: -D.denormalize_action(a)[:, 1]          # less current is better, as in the data
    r = V.evaluate_policy("critic", V.stay_policy, val, q=q, n_perm=200)
    assert r["rho_adv"] > 0.9 and r["rho_q"] > 0.9


def test_a_critic_that_ignores_the_setting_scores_nothing_on_rho_adv():
    """Audit 2026-10-02: a critic echoing the previous pain scored rho_q 0.548 on real data."""
    val = _val()
    q = lambda o, a: -np.asarray(o)[:, 7]
    r = V.evaluate_policy("echo", V.stay_policy, val, q=q, n_perm=50)
    assert not np.isfinite(r["rho_adv"])                    # zero predicted gain everywhere


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
    val["prev_pain_composite"] = 0.0
    rec = D.normalize_action([55, 0.0, 2.0, 100, 150]).astype(np.float32)
    amps = [0, 0, 0, 0, 2, 2, 4, 4, 4]                 # four periods tie at the smallest distance
    for perm in ([0, 1, 2, 3, 4, 5, 6, 7, 8], [3, 2, 1, 0, 5, 4, 8, 7, 6]):
        v = val.iloc[perm].reset_index(drop=True)
        v["amp_mA_Left"] = [amps[i] for i in perm]
        r = V.evaluate_policy("x", lambda o: np.repeat(rec[None], len(o), 0), v, n_perm=20)
        assert r["near_minus_far"] == pytest.approx(np.mean([1, 2, 3, 4]) - np.mean([7, 8, 9]))
        assert r["near_minus_far_change"] == r["near_minus_far"]


def _clinic_transitions(n_visits=10, per=8, seed=0):
    """Held-out-test data: 110 Hz at 3 mA relieves 2 points, 55 Hz at 0.5 mA relieves nothing."""
    rng = np.random.default_rng(seed)
    rows = []
    for v in range(n_visits):
        cur_set = (55, 0.5, 2.0, 100, 150)
        for i in range(per):
            good = rng.random() < 0.5
            act = (110, 3.0, 2.0, 100, 150) if good else (55, 0.5, 2.0, 100, 150)
            comp = rng.uniform(5, 8)
            drop = (2.0 if good else 0.0) + rng.normal(0, 0.3)
            rows.append({"visit": f"v{v}", "obs": _obs(comp, setting=cur_set), "next_obs": _obs(comp - drop, setting=act),
                         "reward": drop, "symptom": drop, "terminal": False,
                         **{f"cur_{k}": x for k, x in zip(C.ACTION_NAMES, cur_set)},
                         **{f"act_{k}": x for k, x in zip(C.ACTION_NAMES, act)}})
            cur_set = act
    return pd.DataFrame(rows)


def test_heldout_switch_gain_is_positive_for_a_model_that_knows_the_better_setting():
    tr = _clinic_transitions()
    r = V.heldout_visit_value_rank(lambda d: T.TabularActorCritic(gamma=0.0).fit(d).q, tr, n_perm=200)
    assert r["heldout_rho_switch_gain"] > 0.5 and r["heldout_p_switch_gain"] < 0.01


def test_a_setting_blind_model_earns_no_switch_gain_score():
    tr = _clinic_transitions()
    r = V.heldout_visit_value_rank(lambda d: T.StateOnlyGP().fit(d).q, tr, n_perm=50)
    assert not np.isfinite(r["heldout_rho_switch_gain"])


def test_switch_gain_decomposition_supports_a_model_whose_destination_values_carry_the_effect():
    tr = _clinic_transitions(n_visits=12, per=10)
    r = V.switch_gain_decomposition(lambda d: T.TabularActorCritic(gamma=0.0).fit(d).q, tr, n_perm=200)
    assert r["a_partial"] > 0.3 and r["p_a_partial"] < 0.05


def test_switch_gain_decomposition_never_supports_a_setting_blind_model():
    tr = _clinic_transitions(n_visits=12, per=10)
    r = V.switch_gain_decomposition(lambda d: T.StateOnlyGP().fit(d).q, tr, n_perm=50)
    assert r["supports_recommendations"] is False


def test_small_models_never_recommend_zero_left_current_for_an_active_contact():
    """Regression (2026-10-02): the explore reading recommended 10 Hz at 0 mA for L C+2-."""
    tr = _transitions()
    off = tr.iloc[:6].copy()
    for k, v in zip(C.ACTION_NAMES, (10, 0.0, 0.0, 60, 160)):
        off[f"act_{k}"] = v
    off["reward"] = 6.0                                      # tempting: an "off" step with relief
    tr = pd.concat([tr, off], ignore_index=True)
    for m in (T.TabularActorCritic(beta=3.0).fit(tr), T.GPBandit().fit(tr)):
        for mode in ("exploit", "explore"):
            rec = D.denormalize_action(m.policy(_obs(6.5, contact="L C+2-"), mode))[0]
            assert rec[1] > 0.0
            rec = D.denormalize_action(m.policy(_obs(6.5, contact="off (Left 0 mA)"), mode))[0]
            assert rec[1] == pytest.approx(0.0, abs=1e-6)
