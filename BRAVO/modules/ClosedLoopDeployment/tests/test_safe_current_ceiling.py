"""Synthetic current-limit integration: observed captures remain distinct from bounded plans."""
import json
import pytest
import numpy as np
import pandas as pd

try:
    from modules.ClosedLoopDeployment import (pipeline as PL, adapter as AD, prescription as PR,
                                              types as TY, simulation as SIM, replay as RP)
    from modules.StimOptimizer import safety_ceiling as SC
    from modules.StimOptimizer.routines import amplitude_response as AR
except ImportError:                                              # pragma: no cover
    from ClosedLoopDeployment import (pipeline as PL, adapter as AD, prescription as PR,
                                      types as TY, simulation as SIM, replay as RP)
    from StimOptimizer import safety_ceiling as SC
    from StimOptimizer.routines import amplitude_response as AR


SUBJECT = "synthetic-safe-current"


@pytest.fixture(autouse=True)
def clinical_evidence(monkeypatch, tmp_path):
    from DecodeCommon.tests.synthetic_clinical_config import install
    path = tmp_path / "clinical.json"
    install(monkeypatch, path, (SUBJECT,))
    document = json.loads(path.read_text())
    document["participants"][SUBJECT]["safety_ceiling"]["values_mA"] = {"Left": 3.25, "Right": 3.25}
    path.write_text(json.dumps(document))


def _safe_current():
    try:
        from modules.ClosedLoopDeployment import safe_current as SCUR
    except ImportError:                                          # pragma: no cover
        from ClosedLoopDeployment import safe_current as SCUR
    return SCUR


# ------------------------------------------------------------------------------------------------
# the joined table: the right stimulator stepped from 1.0 to 4.85 mA, above SUBJECT's 3.25 mA ceiling
# ------------------------------------------------------------------------------------------------
def _table(channel="ZERO_THREE_RIGHT", n_epochs=8, per_epoch=6, seed=0, step=0.55):
    rng = np.random.default_rng(seed)
    rows = []
    for k in range(n_epochs):
        amp_r = round(1.0 + k * step, 4)                 # 1.0, 1.55, ..., 4.85 mA
        for _ in range(per_epoch):
            rows.append({"t": float(k * 100), "channel": channel, "setting_epoch": k,
                         "center_hz": 23.25, "amp_mA_Left": 2.0, "amp_mA_Right": amp_r,
                         "power_linear": 600.0 - 40.0 * amp_r + rng.normal(0, 3.0),
                         "nrs": 8.0 - 0.6 * amp_r + rng.normal(0, 0.1), "report_id": f"r{k}"})
    return pd.DataFrame(rows)


_CAND = {"channel": "ZERO_THREE_RIGHT", "center_hz": 23.25, "sensing_hemisphere": "Right",
         "actuated_hemisphere": "Right"}


def _run(monkeypatch, uid, *, allow=(), table=None):
    T = table if table is not None else _table()
    monkeypatch.setattr(AD, "joined_table_cached", lambda *a, **k: T)
    real = PL._optional
    monkeypatch.setattr(PL, "_optional", lambda name: real(name) if name in allow else None)
    return PL.run(uid, psd_frame=pd.DataFrame({"x": [1]}), epochs=pd.DataFrame({"x": [1]}),
                  candidates=[dict(_CAND)], hemisphere="Right", n_boot=50)


def _plan(hi=4.8, lo=1.4):
    return TY.ThresholdPlan(upper=0.4, lower=0.2, capture_amp_low=lo, capture_amp_high=hi)


def _rows(plan, candidate=None):
    out = PR.prescribe_all_modes(threshold_plan=plan, candidate=candidate or {
        "channel": "ONE_THREE_LEFT", "center_hz": 23.25, "band_width_hz": 5.0})
    rows = {m: {r["parameter"]: r for r in p.as_rows()} for m, p in out["modes"].items() if p.fields}
    if plan.safety_participant_uid is not None:
        assert rows, "a configured synthetic plan must produce actual rows"
    return rows


# ------------------------------------------------------------------------------------------------
# the pipeline: the measured capture currents stay as measured; the limits are capped
# ------------------------------------------------------------------------------------------------
def test_the_pipeline_caps_the_limits_at_the_participants_own_ceiling(monkeypatch):
    rep = _run(monkeypatch, SUBJECT)
    tp = rep.threshold
    assert tp is not None
    # the thresholds were read at the measured currents, so those are kept as measured
    assert (tp.capture_amp_low, tp.capture_amp_high) == (1.0, 4.85)
    # the ceiling is read from its one home, for the actuated side
    assert tp.safety_ceiling_mA == SC.ceiling_for(SUBJECT, "Right")[0] == 3.25
    assert tp.amplitude_limits() == (1.0, 3.25)
    assert "3.25 mA" in tp.amp_limit_high_note and "4.85 mA" in tp.amp_limit_high_note
    assert tp.amp_limit_low_note is None


def test_a_participant_with_no_stated_ceiling_is_explicitly_unavailable(monkeypatch):
    rep = _run(monkeypatch, "not-a-participant")
    assert rep.threshold is None and rep.protocol is None
    assert any("clinical configuration unavailable" in reason for reason in rep.blockers)


def test_the_titration_ladder_ends_are_the_capped_limits(monkeypatch):
    rep = _run(monkeypatch, SUBJECT, allow=("protocol",))
    assert rep.protocol is not None and rep.protocol.steps
    amps = [float(v) for s in rep.protocol.steps for k, v in s.items()
            if "amp" in k and isinstance(v, (int, float)) and not isinstance(v, bool)]
    assert amps and max(amps) == 3.25, sorted(set(amps))
    assert not any("4.85" in str(s.get("label", "")) for s in rep.protocol.steps)


def test_the_serialised_threshold_block_names_the_limits_and_the_ceiling(monkeypatch):
    rep = _run(monkeypatch, SUBJECT)
    th = AD.report_to_dict(rep)["threshold"]
    assert th["capture_amp_high"] == 4.85
    assert th["amp_limit_high"] == 3.25 and th["amp_limit_low"] == 1.0
    assert th["safety_ceiling_mA"] == 3.25
    assert th["safety_ceiling_provenance"] == SC.ceiling_for(SUBJECT, "Right")[1]


# ------------------------------------------------------------------------------------------------
# the table's rows
# ------------------------------------------------------------------------------------------------
def test_the_upper_limit_row_is_capped_and_says_so_in_one_sentence():
    plan = _safe_current().apply_to_plan(_plan(), SUBJECT, "Left")
    for mode, rows in _rows(plan).items():
        up, lo = rows["Adaptive amplitude limit, upper"], rows["Adaptive amplitude limit, lower"]
        assert up["value"] == 3.25, mode
        assert up["ceiling_note"] == ("Capped at the 3.25 mA safe ceiling; the highest current "
                                      "measured was 4.8 mA."), mode
        assert lo["value"] == 1.4 and lo["ceiling_note"] is None, mode


def test_a_limit_at_the_ceiling_is_not_called_capped():
    plan = _safe_current().apply_to_plan(_plan(hi=3.25), SUBJECT, "Right")
    for mode, rows in _rows(plan).items():
        assert rows["Adaptive amplitude limit, upper"]["value"] == 3.25
        assert rows["Adaptive amplitude limit, upper"]["ceiling_note"] is None


def test_every_current_row_is_at_or_below_the_ceiling_the_paused_amplitude_included():
    plan = _safe_current().apply_to_plan(_plan(hi=5.2, lo=4.6), SUBJECT, "Left")
    rows = _rows(plan, candidate={"channel": "ONE_THREE_LEFT", "center_hz": 23.25,
                                  "band_width_hz": 5.0, "paused_amplitude_mA": 5.0})
    assert rows
    for mode, by_name in rows.items():
        cur = {n: r for n, r in by_name.items() if r["units"] == "mA" and r["value"] is not None}
        assert set(cur) == {"Adaptive amplitude limit, lower", "Adaptive amplitude limit, upper",
                            "Paused amplitude"}, mode
        assert all(r["value"] <= 3.25 for r in cur.values()), {n: r["value"] for n, r in cur.items()}
        assert cur["Paused amplitude"]["ceiling_note"] == (
            "Capped at the 3.25 mA safe ceiling; the stated paused amplitude was 5 mA.")


def test_a_plan_without_participant_binding_cannot_offer_current_rows():
    assert _rows(_plan(hi=5.6)) == {}


# ------------------------------------------------------------------------------------------------
# the controller: the replay, the simulation and the simulation's stored key
# ------------------------------------------------------------------------------------------------
def _series(n=900, dt=1.2):
    t = np.arange(n) * dt
    p = 0.29 + 0.15 * np.sin(np.linspace(0, 6 * np.pi, n))
    return t, p, np.full(n, 2.0)


def test_the_replay_runs_between_the_capped_limits():
    plan = _safe_current().apply_to_plan(_plan(), SUBJECT, "Left")
    t, p, _ = _series()
    res = RP.dual_threshold({"t_s": t, "power": p}, plan)
    amp = np.asarray(res.amplitude_mA, float)
    assert float(np.nanmax(amp)) == 3.25


def test_the_simulation_runs_between_the_capped_limits():
    plan = _safe_current().apply_to_plan(_plan(), SUBJECT, "Left")
    t, p, a = _series()
    res = SIM.simulate_series(t, p, a, plan, [AR.ResponseCurve.zero()], tau_s=30.0)
    assert res["params"]["amp_high_mA"] == 3.25 and res["params"]["amp_low_mA"] == 1.4
    assert float(np.max(res["amp"])) == 3.25
    # the card's sentence travels with the run, so the simulation card can say the range was capped
    assert res["params"]["amp_limit_note"] == ("Capped at the 3.25 mA safe ceiling; the highest "
                                               "current measured was 4.8 mA.")
    uncapped = SIM.simulate_series(t, p, a, _safe_current().apply_to_plan(_plan(hi=3.25), SUBJECT, "Left"),
                                   [AR.ResponseCurve.zero()], tau_s=30.0)
    assert uncapped["params"]["amp_limit_note"] is None


def test_the_simulation_key_carries_the_limits_the_controller_runs_with(monkeypatch):
    monkeypatch.setattr(AD, "recording_set_signature", lambda p: "rs")
    kw = dict(tiles_key="k", contact="ONE_THREE_LEFT", centre_hz=23.25, hemisphere="Left",
              power_scale="power_linear", n_resample=10, seed=0)
    capped = AD.simulation_signature("p", plan=_safe_current().apply_to_plan(_plan(), SUBJECT, "Left"), **kw)
    at_ceiling = AD.simulation_signature("p", plan=_safe_current().apply_to_plan(_plan(hi=3.25), SUBJECT, "Left"), **kw)
    # the key names 3.25 mA, the limit the controller runs with, and not the measured 4.8
    assert capped == at_ceiling
    assert 4.8 not in capped[-3]
