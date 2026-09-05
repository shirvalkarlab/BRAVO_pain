"""The within-visit evidence builder, and the claim that the existing screen consumes it unchanged."""
import numpy as np
import pandas as pd
import pytest

from StimOptimizer.routines import within_visit as WV
from StimOptimizer.routines import lfp_evidence as EV
from StimOptimizer.routines import lfp_response as LR

CEN = np.arange(10.5, 27.6, 1.0)


def _steps(n_visits=6, per_visit=8, rate=55.0, amps=(1.0, 3.5), tile_dt=3.0, win=120.0):
    """Clinic steps: each visit walks the amplitude ladder, which is the design's whole premise."""
    rows = []
    t = 1_700_000_000.0
    for v in range(n_visits):
        for k in range(per_visit):
            rows.append(dict(t0=t, window_s=win, rate_hz=rate,
                             amp_mA_Left=amps[k % len(amps)],
                             amp_mA_Right=amps[k % len(amps)],
                             visit=f"2026-0{v + 1}-01"))
            t += win + 60.0
        t += 86400.0
    return pd.DataFrame(rows)


def _tiles(steps, *, slope_per_mA=-0.2, seed=0, tile_dt=3.0, ramp_s=WV.RAMP_EXCLUDE_S):
    """Tiles spanning each step, carrying a real amplitude effect plus a per-visit offset."""
    rng = np.random.default_rng(seed)
    ts, ps = [], []
    voff = {v: rng.normal(0, 0.4) for v in steps.visit.unique()}
    for _, r in steps.iterrows():
        n = int(r.window_s // tile_dt)
        for j in range(n):
            ts.append(r.t0 + j * tile_dt)
            base = 5.0 + slope_per_mA * r.amp_mA_Left + voff[r.visit]
            ps.append(base + rng.normal(0, 0.05, CEN.size))
    o = np.argsort(np.asarray(ts))
    return np.asarray(ts)[o], np.vstack(ps)[o]


def test_within_visit_import_does_not_pull_in_biomarkers():
    """The dependency direction is load-bearing: ClosedLoopDeployment imports StimOptimizer, never
    the reverse, so a builder here cannot reach into ClosedLoopDeployment.clinic_steps. The
    harmonic-landing flag needs Biomarkers and therefore stays on that side; this asserts the split
    actually holds rather than being described in a comment.
    """
    import subprocess, sys, os
    code = ("import sys;"
            "from StimOptimizer.routines import within_visit;"
            "print([m for m in sys.modules if m.startswith('Biomarkers')])")
    env = dict(os.environ, PYTHONPATH=os.path.dirname(os.path.dirname(
        os.path.dirname(os.path.abspath(WV.__file__)))))
    r = subprocess.run([sys.executable, "-B", "-c", code], capture_output=True, text=True, env=env)
    assert r.returncode == 0, r.stderr[-400:]
    assert r.stdout.strip().endswith("[]"), r.stdout


def test_builder_returns_the_same_shape_build_all_does_and_screen_cells_eats_it():
    """The load-bearing interoperability claim. If the mapping shape drifts, the whole gate
    downstream -- the majority-of-bands rule, the era-significance condition, the amplitude
    ceiling -- silently stops applying to within-visit evidence.
    """
    S = _steps()
    tt, tp = _tiles(S)
    ev, audit = WV.build_all_within_visit(
        S, centers_hz=CEN, tiles_by_channel={"ZERO_TWO_LEFT": (tt, tp)},
        hemispheres=("Left",), rates=(55.0,))
    assert isinstance(ev, dict) and isinstance(audit, pd.DataFrame)
    assert list(ev) == [("ZERO_TWO_LEFT", "Left", 55.0)]
    e = ev[("ZERO_TWO_LEFT", "Left", 55.0)]
    assert e.amplitude_mA.size == e.era.size == e.cluster.size
    assert len(e.band_power) == CEN.size

    # screen_cells returns (frame, selected_key) -- the selection is part of its contract, so a
    # test that unpacked only the frame would not notice the key going missing.
    scr, selected = EV.screen_cells(ev, response_fn=LR.assess_response)
    assert isinstance(scr, pd.DataFrame) and len(scr) == 1
    for col in ("channel", "hemisphere", "rate_hz", "n_bands", "n_responding",
                "deployable", "blocking_reasons"):
        assert col in scr.columns, (col, list(scr.columns))
    assert int(scr.n_bands.iloc[0]) == CEN.size

    # and the GATE really applies: a clean within-visit design with a genuine negative slope
    # reaches deployable, which is what proves the downstream rules were not bypassed.
    assert bool(scr.deployable.iloc[0]) is True, scr.blocking_reasons.iloc[0]
    assert selected == ("ZERO_TWO_LEFT", "Left", 55.0), selected


def test_the_visit_supplies_era_and_cluster_and_amplitude_varies_inside_it():
    """The property the chronic epochs lacked. There, each era carried ONE amplitude, so its dummy
    absorbed the era entirely and contributed no within-era contrast -- which is why restricting to
    five recent eras left the blocked slope identical to four decimals. Here every visit contains
    both arms, so blocking removes calendar time WITHOUT absorbing the effect.
    """
    S = _steps()
    tt, tp = _tiles(S)
    e, aud = WV.build_within_visit_evidence(
        S, channel="ZERO_TWO_LEFT", hemisphere="Left", rate_hz=55.0,
        centers_hz=CEN, tile_t=tt, tile_power=tp)
    assert e is not None, aud.reason_unusable
    assert np.array_equal(e.era, e.cluster)
    df = pd.DataFrame({"era": e.era, "amp": e.amplitude_mA})
    per_era = df.groupby("era").amp.nunique()
    assert (per_era >= 2).all(), per_era.to_dict()
    assert aud.n_eras >= 2 and len(aud.amplitudes) >= 2


def test_a_real_negative_slope_survives_the_builder():
    S = _steps()
    tt, tp = _tiles(S, slope_per_mA=-0.30)
    e, _ = WV.build_within_visit_evidence(
        S, channel="ZERO_TWO_LEFT", hemisphere="Left", rate_hz=55.0,
        centers_hz=CEN, tile_t=tt, tile_power=tp)
    r = LR.assess_response(e.power_for(20.5, 5.0), e.amplitude_mA, era=e.era, cluster=e.cluster)
    assert r.slope_log_per_mA < 0, r.slope_log_per_mA
    assert r.direction_ok is True
    assert r.slope_p < 0.05


def test_unusable_cells_are_audited_with_a_reason_never_silently_absent():
    S = _steps(amps=(2.0,))                      # one amplitude only -> no capture contrast
    tt, tp = _tiles(S)
    e, aud = WV.build_within_visit_evidence(
        S, channel="ZERO_TWO_LEFT", hemisphere="Left", rate_hz=55.0,
        centers_hz=CEN, tile_t=tt, tile_power=tp)
    assert e is None and "one binned amplitude" in (aud.reason_unusable or "")

    # a rate with no steps at all
    e2, aud2 = WV.build_within_visit_evidence(
        _steps(), channel="ZERO_TWO_LEFT", hemisphere="Left", rate_hz=999.0,
        centers_hz=CEN, tile_t=tt, tile_power=tp)
    assert e2 is None and aud2.reason_unusable
    assert aud2.n_dropped_other_rate > 0

    # tiles that do not overlap the steps
    e3, aud3 = WV.build_within_visit_evidence(
        _steps(), channel="ZERO_TWO_LEFT", hemisphere="Left", rate_hz=55.0,
        centers_hz=CEN, tile_t=tt + 5e6, tile_power=tp)
    assert e3 is None and "settled window" in (aud3.reason_unusable or "")


def test_centre_count_mismatch_raises_rather_than_mislabelling_bands():
    """Silent misalignment here would attribute one band's power to another's centre, which is the
    single worst failure available in this module -- it would be invisible and wrong.
    """
    S = _steps()
    tt, tp = _tiles(S)
    with pytest.raises(ValueError, match="centers_hz"):
        WV.build_within_visit_evidence(S, channel="ZERO_TWO_LEFT", hemisphere="Left",
                                       rate_hz=55.0, centers_hz=CEN[:-3],
                                       tile_t=tt, tile_power=tp)
