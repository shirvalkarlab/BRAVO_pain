"""The onset worked out per band (the PI, 2026-10-04, decision 417: "yes. per band"; rule chosen:
"fewest switches, none undone").

Until now one onset (30 s, decision 150) was typed for the participant and shown for every band.
Now, for the chosen band, at 3 s averaging, each onset the tablet allows (3 to 30 s in 3 s steps)
is tried: the band's thresholds are placed from its own record (its median averaged reading +- the
separation its fitted noise model requires at that onset), the band's own recorded power is
replayed through the controller (blanking equal to the onset, the card's 30 s ramps, the plan's
current limits), and among the onsets with no switch undone within one onset, the one with the
fewest switches an hour is taken (the shorter on a tie). An onset
whose noise model reaches no separation gets no pair and is not a candidate. When no onset reaches
zero undone, the one with the fewest is taken and that is said.

Pinned on values: the pick against a direct replay of every row; the skipped onsets; the
fall-back; the grid; and the card's timing built from the pick (onset, blanking = onset, the
averaging, and the fields the record cannot decide kept and labelled as the same for every band).
"""
import numpy as np

try:
    from modules.ClosedLoopDeployment import band_timing as BT, robustness as RB, simulation as SIM
    from modules.ClosedLoopDeployment import timing_recommendation as TR
except ImportError:                                              # pragma: no cover - host spelling
    from ClosedLoopDeployment import band_timing as BT, robustness as RB, simulation as SIM
    from ClosedLoopDeployment import timing_recommendation as TR

UID = "2e3c75c00d7f4f37b53a048d195f11da"


def _series(seed=0, hours=3.0, level=200.0, wobble=25.0, swing=150.0):
    """3 s pieces in four stretches with gaps: a slow 20-minute swing (so the controller reaches
    both current limits), a slow drift and fast wobble."""
    rng = np.random.default_rng(seed)
    t, p = [], []
    t0 = 1_750_000_000.0
    n = int(hours * 3600 / 3 / 4)
    for s in range(4):
        base = t0 + s * 20_000.0
        slow = np.cumsum(rng.normal(0, 0.6, n))
        t.extend(base + 3.0 * np.arange(n))
        tt = 3.0 * np.arange(n)
        p.extend(level + swing * np.sin(2 * np.pi * tt / 1200.0) + slow + rng.normal(0, wobble, n))
    t = np.asarray(t)
    return t, np.asarray(p), np.full(t.size, 2.0)


def _rows(seps):
    return [{"averaging_s": 3.0, "onset_s": float(o), "min_separation": s} for o, s in seps.items()]


def test_the_grid_is_the_tablets_onsets_at_three_second_averaging():
    assert BT.AVERAGING_S == 3.0
    assert BT.ONSET_GRID_S == tuple(float(x) for x in range(3, 31, 3))


def test_the_pick_is_the_fewest_switches_among_onsets_with_none_undone():
    t, p, a = _series()
    stretches = BT.stretches_for(t, p, a)
    rows = _rows({o: 30.0 + 120.0 / o for o in BT.ONSET_GRID_S})
    out = BT.choose_onset(stretches, rows, median=200.0, amp_low=1.0, amp_high=3.0)
    assert out["available"] is True
    by = {r["onset_s"]: r for r in out["rows"]}
    for o in BT.ONSET_GRID_S:                      # each row is a direct replay of its own pair
        half = 30.0 + 120.0 / o
        ms = o * 1000.0
        res = RB.run_many(stretches, 3000.0, np.array([200.0 + half]), np.array([200.0 - half]),
                          np.array([ms]), np.array([ms]), np.array([BT.RAMP_MS]),
                          np.array([BT.RAMP_MS]), 1.0, 3.0)
        assert by[o]["undone"] == int(res["reversals_within_one_onset"][0])
        assert by[o]["upper"] == 200.0 + half and by[o]["lower"] == 200.0 - half
    zero = [o for o in BT.ONSET_GRID_S if by[o]["undone"] == 0 and by[o]["controls"]]
    assert zero, "this series reaches zero undone somewhere on the grid"
    want = min(zero, key=lambda o: (by[o]["transitions_per_hour"], o))
    assert out["onset_s"] == want and out["zero_undone_reached"] is True


def test_among_onsets_with_none_undone_the_fewest_switches_wins_not_the_shortest():
    """Fixed counts: 12 s and 27 s both undo nothing; 27 s switches less, so 27 s is the onset."""
    t, p, a = _series()
    undone = {o: (0 if o in (12.0, 27.0) else 3) for o in BT.ONSET_GRID_S}
    tph = {o: (8.0 if o == 12.0 else 2.5 if o == 27.0 else 1.0) for o in BT.ONSET_GRID_S}
    real = RB.run_many

    def fixed(stretches, averaging_ms, upper, lower, onset_ms, *rest):
        k = len(upper)
        return {"reversals_within_one_onset": np.array([undone[o / 1000.0] for o in onset_ms]),
                "transitions_per_hour": np.array([tph[o / 1000.0] for o in onset_ms]),
                "frac_time_at_upper_limit": np.full(k, 0.3), "frac_time_at_lower_limit": np.full(k, 0.3),
                "hours": 1.0}
    RB.run_many = fixed
    try:
        out = BT.choose_onset(BT.stretches_for(t, p, a), _rows({o: 10.0 for o in BT.ONSET_GRID_S}),
                              median=200.0, amp_low=1.0, amp_high=3.0)
    finally:
        RB.run_many = real
    assert out["onset_s"] == 27.0 and out["zero_undone_reached"] is True


def test_an_onset_with_no_separation_is_not_a_candidate():
    t, p, a = _series()
    seps = {o: (None if o < 15 else 40.0) for o in BT.ONSET_GRID_S}
    out = BT.choose_onset(BT.stretches_for(t, p, a), _rows(seps), median=200.0, amp_low=1.0,
                          amp_high=3.0)
    skipped = [r for r in out["rows"] if r["upper"] is None]
    assert sorted(r["onset_s"] for r in skipped) == [3.0, 6.0, 9.0, 12.0]
    assert all(r["undone"] is None for r in skipped)
    assert out["onset_s"] >= 15.0


def test_when_no_onset_reaches_zero_the_fewest_is_taken_and_said():
    """The replay's undone counts are fixed here (none zero, a tie at the fewest) so the fall-back
    rule itself is what is pinned."""
    t, p, a = _series()
    undone = {3.0: 9, 6.0: 7, 9.0: 4, 12.0: 2, 15.0: 3, 18.0: 2, 21.0: 5, 24.0: 6, 27.0: 8, 30.0: 9}
    real = RB.run_many

    def fixed(stretches, averaging_ms, upper, lower, onset_ms, *rest):
        k = len(upper)
        return {"reversals_within_one_onset": np.array([undone[o / 1000.0] for o in onset_ms]),
                "transitions_per_hour": np.ones(k), "frac_time_at_upper_limit": np.full(k, 0.3),
                "frac_time_at_lower_limit": np.full(k, 0.3), "hours": 1.0}
    RB.run_many = fixed
    try:
        out = BT.choose_onset(BT.stretches_for(t, p, a), _rows({o: 10.0 for o in BT.ONSET_GRID_S}),
                              median=200.0, amp_low=1.0, amp_high=3.0)
    finally:
        RB.run_many = real
    assert out["available"] is True and out["zero_undone_reached"] is False
    assert out["onset_s"] == 12.0 and out["pick"]["undone"] == 2       # fewest, shorter of the tie


def test_no_separation_anywhere_is_a_refusal():
    t, p, a = _series()
    out = BT.choose_onset(BT.stretches_for(t, p, a), _rows({o: None for o in BT.ONSET_GRID_S}),
                          median=200.0, amp_low=1.0, amp_high=3.0)
    assert out["available"] is False and "separation" in out["reason"]


def test_the_cards_timing_takes_the_bands_onset_and_keeps_the_rest_labelled():
    band = {"available": True, "onset_s": 21.0, "zero_undone_reached": True,
            "rows": [{"onset_s": 21.0, "undone": 0, "transitions_per_hour": 2.4}],
            "candidate": {"channel": "ZERO_THREE_LEFT", "center_hz": 26.5}}
    got = TR.for_band(UID, band)
    assert got["onset_upper_ms"]["value_ms"] == 21000.0
    assert got["onset_lower_ms"]["value_ms"] == 21000.0
    assert got["detection_blanking_ms"]["value_ms"] == 21000.0
    assert got["averaging_ms"]["value_ms"] == 3000.0
    assert "ZERO_THREE_LEFT" in got["onset_upper_ms"]["provenance"]
    for k in ("transition_up_ms", "transition_down_ms", "adaptive_startup_delay_ms"):
        assert got[k]["value_ms"] == TR.RECORD_DERIVED_TIMING_MS[UID][k]
        assert "same for every band" in got[k]["why"]


def test_without_a_band_answer_the_participant_table_stands():
    assert TR.for_band(UID, None) == TR.for_participant(UID)
    assert TR.for_band(UID, {"available": False, "reason": "x"}) == TR.for_participant(UID)


# --- the band's onset reaches the record pair, the card and the simulation (wiring) -------------
from types import SimpleNamespace

try:
    from modules.ClosedLoopDeployment import adapter as AD, pipeline as PL
    from modules.ClosedLoopDeployment.types import ThresholdPlan
except ImportError:                                              # pragma: no cover
    from ClosedLoopDeployment import adapter as AD, pipeline as PL
    from ClosedLoopDeployment.types import ThresholdPlan

BAND = {"available": True, "onset_s": 21.0, "zero_undone_reached": True, "median": 200.0,
        "pick": {"onset_s": 21.0, "undone": 0, "transitions_per_hour": 2.0},
        "design_rows": [{"averaging_s": 3.0, "onset_s": float(o), "min_separation": 50.0 - o}
                        for o in range(3, 31, 3)],
        "candidate": {"channel": "ZERO_THREE_LEFT", "center_hz": 26.5}}


def test_the_record_pair_is_placed_at_the_bands_onset_from_its_own_separations():
    t, p, a = _series()
    saved = {k: getattr(AD, k) for k in ("simulation_inputs_for_participant", "write_band_timing",
                                         "write_design_rule", "design_rule_if_stored")}
    AD.simulation_inputs_for_participant = lambda *x, **k: {"t": t, "power": p, "amp_obs": a}
    AD.write_band_timing = lambda *x, **k: dict(BAND)
    AD.write_design_rule = lambda *x, **k: {"store_key": None}
    AD.design_rule_if_stored = lambda *x, **k: {"table": [{"averaging_s": 3.0, "onset_s": 30.0,
                                                           "min_separation": 999.0}]}
    try:
        plan = ThresholdPlan(upper=260.0, lower=150.0, capture_amp_low=1.0, capture_amp_high=3.0)
        rep = SimpleNamespace(threshold=plan)
        new, placement = AD._place_thresholds_from_record(
            UID, rep, [{"channel": "ZERO_THREE_LEFT", "center_hz": 26.5}], hemisphere="Left")
    finally:
        for k, v in saved.items():
            setattr(AD, k, v)
    assert placement["available"] is True and placement["onset_s"] == 21.0
    assert placement["half_separation"] == 50.0 - 21.0                 # the band's own row
    assert abs(placement["centre"] - placement["upper"] + 29.0) < 1e-9
    assert rep.band_timing["onset_s"] == 21.0


def test_the_simulations_recommended_regime_runs_at_the_bands_onset():
    runs = AD._timing_runs_for_simulation(UID, "Left", {}, band_timing=BAND)
    params = runs["recommended"]["params"]
    assert params.get("onset_ms") == 21000.0 and params.get("averaging_ms") == 3000.0
    assert params.get("blanking_ms", params.get("detection_blanking_ms")) == 21000.0


def test_the_card_reads_the_bands_timing():
    import inspect
    src = inspect.getsource(PL.run)
    assert 'for_band(participant_uid, getattr(rep, "band_timing", None))' in src


def test_a_pair_the_controller_never_reaches_is_not_a_candidate():
    """RCS08's committed band, 31.2 h, as the report saw it: 24 s at +-300 never switches (0 at each
    limit), 27 s at +-120 barely reaches the lower limit (0.1%), 30 s at +-20 controls (24% / 27%).
    Fewest switches alone would take 24 s; only 30 s controls, so 30 s is the onset."""
    t, p, a = _series()
    sep = {o: None for o in BT.ONSET_GRID_S}
    sep.update({24.0: 300.0, 27.0: 120.0, 30.0: 20.0})
    stats = {24.0: (0.0, 0.0, 0.0), 27.0: (0.51, 0.067, 0.001), 30.0: (1.93, 0.244, 0.271)}
    real = RB.run_many

    def fixed(stretches, averaging_ms, upper, lower, onset_ms, *rest):
        os_ = [o / 1000.0 for o in onset_ms]
        return {"reversals_within_one_onset": np.zeros(len(os_), dtype=int),
                "transitions_per_hour": np.array([stats[o][0] for o in os_]),
                "frac_time_at_upper_limit": np.array([stats[o][1] for o in os_]),
                "frac_time_at_lower_limit": np.array([stats[o][2] for o in os_]), "hours": 31.2}
    RB.run_many = fixed
    try:
        out = BT.choose_onset(BT.stretches_for(t, p, a), _rows(sep), median=218.3, amp_low=0.2,
                              amp_high=4.5)
        none = BT.choose_onset(BT.stretches_for(t, p, a), _rows({24.0: 300.0}), median=218.3,
                               amp_low=0.2, amp_high=4.5)
    finally:
        RB.run_many = real
    assert out["onset_s"] == 30.0 and out["pick"]["lower"] == 218.3 - 20.0
    by = {r["onset_s"]: r for r in out["rows"]}
    assert by[24.0]["controls"] is False and by[27.0]["controls"] is False and by[30.0]["controls"] is True
    assert none["available"] is False and "each current limit" in none["reason"]
