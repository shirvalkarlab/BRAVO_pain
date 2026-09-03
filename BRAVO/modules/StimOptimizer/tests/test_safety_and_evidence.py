"""The energy-matched safety gate, and building LfpEvidence from real-shaped data.

Every test here pins a failure mode that would otherwise be silent: a budget that licences an
exposure that never happened, an amplitude gate that passes a setting delivering three times the
tolerated energy, a timestamp unit that empties a join without raising, or a band power computed by
summing logarithms.
"""
import numpy as np
import pandas as pd
import pytest

from StimOptimizer.routines import objective as OBJ
from StimOptimizer.routines import schedule as SCHED
from StimOptimizer.routines import lfp_evidence as EV


# --- the flat amplitude hard limit (replaces the retracted energy-matched cap) ----------------
#: Delivered amplitude envelope for the filter fixtures. Defined here rather than inside the
#: excised energy block it used to share, which is why five tests briefly referenced an undefined
#: name after the retraction.
ENV = {"Left": (0.0, 5.0), "Right": (0.0, 5.0)}

def test_the_amplitude_limit_is_flat_and_lives_in_one_place():
    """PI-declared 5.0 mA per hemisphere, established by testing at 165 Hz.

    RETRACTION 2026-09-02: this file previously tested an energy-matched ceiling that scaled the
    cap as sqrt(55/f) from a TEED budget. The PI rejected the premise that tolerable amplitude at a
    frequency is governed by delivered energy. The machinery was removed rather than switched off,
    and these tests assert it is GONE, because a dormant energy cap is what a later reader
    reinstates by accident.
    """
    from StimOptimizer.routines import stage_gate as GATE
    from StimOptimizer import stage1_openloop as S1
    from StimOptimizer.routines import plots as PLT
    assert OBJ.AMP_HARD_LIMIT_MA == 5.0
    # one source of truth, not four literals that can drift apart
    assert GATE.AMP_CEILING_MA == OBJ.AMP_HARD_LIMIT_MA
    assert S1.AMP_CEILING_MA == OBJ.AMP_HARD_LIMIT_MA
    # and the SEARCH GRID must reach the limit, or the highest permitted amplitudes sit outside
    # the search space where the surrogate can neither score nor propose them
    assert PLT.AMP_GRID.max() == OBJ.AMP_HARD_LIMIT_MA


def test_every_teed_symbol_is_gone_from_the_objective():
    for name in ("ENERGY_REF", "energy_reference", "energy_penalty",
                 "energy_reference_from_record", "energy_matched_ceiling"):
        assert not hasattr(OBJ, name), f"{name} survived the retraction"
    assert "w_energy" not in OBJ.DEFAULTS


def test_the_composite_objective_no_longer_carries_an_energy_term():
    """It was J_pain + J_SE + w_energy*J_energy with w_energy = 0.0, so removing it changes
    no published value. This test pins that the column is gone AND that J still equals the sum
    of the two surviving terms, so a future energy-like term cannot be added silently."""
    ep = pd.DataFrame({
        "epoch": [1, 2], "freq_hz": [55.0, 55.0], "amp_mA_Left": [1.6, 3.5],
        "pw_us_Left": [60.0, 60.0], "n": [6, 6], "t0": pd.to_datetime(["2026-01-01", "2026-02-01"], utc=True),
        "dur_h": [200.0, 200.0], "left_leg_vas": [70.0, 40.0], "left_leg_vas_sd": [8.0, 8.0]})
    d = OBJ.build_objective(ep, incumbent_epoch=1)
    assert "J_energy" not in d.columns
    assert np.allclose(d["J"], d["J_pain"] + d["J_SE"])


def test_safety_filter_refuses_an_energy_budget_argument():
    """A caller still passing one is working from the retracted model and must see that."""
    c = pd.DataFrame([dict(id="x", rate=55.0, ampL=1.4, ampR=3.0, pwL=60.0, pwR=150.0)])
    with pytest.raises(TypeError):
        SCHED.safety_filter(c, delivered_envelope=ENV, energy_budget={"Left": 1.0})


def test_the_flat_limit_binds_identically_at_every_rate():
    """The point of the retraction: 4.5 mA is now equally acceptable at 55 and at 165 Hz, where
    the energy model would have refused it at the higher rate."""
    rows = [dict(id=f"r{f:.0f}", rate=f, ampL=4.5, ampR=4.5, pwL=100.0, pwR=150.0)
            for f in (55.0, 110.0, 165.0)]
    kept, rej = SCHED.safety_filter(pd.DataFrame(rows), delivered_envelope=ENV)
    assert len(kept) == 3 and rej.empty


def test_above_the_flat_limit_is_refused_at_every_rate():
    rows = [dict(id=f"r{f:.0f}", rate=f, ampL=5.1, ampR=1.0, pwL=100.0, pwR=150.0)
            for f in (55.0, 165.0)]
    kept, rej = SCHED.safety_filter(pd.DataFrame(rows), delivered_envelope={"Left": (0.0, 9.0),
                                                                            "Right": (0.0, 9.0)})
    assert kept.empty and len(rej) == 2
    assert rej.reject_reason.str.contains("hard limit").all()


# --- LfpEvidence from real-shaped data ---------------------------------------------------------
FREQS = np.arange(1.0, 41.0, 1.0)


def _psd(n=40, t0=1_760_000_000):
    rng = np.random.default_rng(0)
    log_psd = rng.normal(-1.0, 0.15, size=(n, FREQS.size))
    return pd.DataFrame({"t": np.arange(n) * 600 + t0, "channel": ["ZERO_TWO_LEFT"] * n,
                         "log_psd": list(log_psd), "freqs": [FREQS] * n})


def _epochs(t0=1_760_000_000):
    s = pd.to_datetime(t0, unit="s", utc=True)
    return pd.DataFrame([
        dict(t_start=s, t_end=s + pd.Timedelta(hours=2), amp_Left=1.6, amp_Right=2.0,
             rate=165.0, visit=1),
        dict(t_start=s + pd.Timedelta(hours=2), t_end=s + pd.Timedelta(hours=4), amp_Left=2.4,
             amp_Right=2.0, rate=165.0, visit=2),
        dict(t_start=s + pd.Timedelta(hours=4), t_end=s + pd.Timedelta(hours=6), amp_Left=0.0,
             amp_Right=2.0, rate=165.0, visit=3),
        dict(t_start=s + pd.Timedelta(hours=6), t_end=s + pd.Timedelta(hours=8), amp_Left=3.0,
             amp_Right=2.0, rate=55.0, visit=4),
    ])


def test_band_power_exponentiates_before_summing():
    """Summing logs is a PRODUCT of powers, not the linear sum the device thresholds.

    This fixture is built as a PLAIN base-10 log, so it must say so. It originally relied on the
    default, and when the default became "db10" — the platform's real convention — the test failed
    on its own stale premise rather than on a code defect. Naming the convention at the call site
    is exactly the discipline the log_scale parameter exists to force.
    """
    log = np.array([[np.log10(2.0), np.log10(8.0)]])
    f = np.array([10.0, 11.0])
    got = EV.band_power_linear(log, f, 10.5, 2.0, log_scale="log10")
    assert got[0] == pytest.approx((2.0 + 8.0) * 1.0)      # 10, not log10(2)+log10(8)=1.204
    assert got[0] != pytest.approx(np.log10(2.0) + np.log10(8.0))


def test_band_outside_the_frequency_axis_returns_none_rather_than_nearest_bins():
    assert EV.band_power_linear(np.zeros((2, FREQS.size)), FREQS, 200.0, 5.0) is None


def test_nanosecond_timestamps_raise_instead_of_silently_emptying_the_join():
    """Read as ns, every window lands in 1970 and the join returns nothing with no error."""
    with pytest.raises(ValueError, match="epoch SECONDS"):
        EV.build_evidence(_psd(), _epochs(), channel="ZERO_TWO_LEFT", hemisphere="Left",
                          rate_hz=165.0, time_unit="ns")


def test_zero_amplitude_windows_are_dropped_because_stim_off_has_no_artifact():
    ev, aud = EV.build_evidence(_psd(), _epochs(), channel="ZERO_TWO_LEFT", hemisphere="Left",
                                rate_hz=165.0, bands=[(20.0, 5.0)])
    assert ev is not None
    assert aud.n_dropped_stim_off > 0
    assert 0.0 not in aud.amplitudes
    assert aud.amplitudes == (1.6, 2.4)


def test_rates_are_never_pooled_because_artifact_scales_with_rate():
    ev, aud = EV.build_evidence(_psd(), _epochs(), channel="ZERO_TWO_LEFT", hemisphere="Left",
                                rate_hz=165.0, bands=[(20.0, 5.0)])
    assert aud.n_dropped_other_rate > 0          # the 55 Hz epoch is excluded
    assert aud.rate_hz == 165.0


def test_a_single_amplitude_yields_no_evidence_and_says_why():
    """A gate that reports 'no response' for absent data is indistinguishable from a real negative."""
    ev, aud = EV.build_evidence(_psd(), _epochs(), channel="ZERO_TWO_LEFT", hemisphere="Left",
                                rate_hz=55.0, bands=[(20.0, 5.0)])
    assert ev is None
    assert "only one amplitude" in aud.reason_unusable
    assert "UNUSABLE" in aud.describe()


def test_evidence_carries_band_power_not_magnitude():
    """Populating `magnitude` with log power would be wrong twice over and still look plausible."""
    ev, _ = EV.build_evidence(_psd(), _epochs(), channel="ZERO_TWO_LEFT", hemisphere="Left",
                              rate_hz=165.0, bands=[(20.0, 5.0)])
    assert ev.magnitude is None and ev.freqs is None
    assert ev.band_power and ev.power_for(20.0, 5.0) is not None
    assert len(ev.power_for(20.0, 5.0)) == len(ev.amplitude_mA)


def test_era_and_cluster_are_populated_because_amplitude_is_confounded_with_time():
    ev, aud = EV.build_evidence(_psd(), _epochs(), channel="ZERO_TWO_LEFT", hemisphere="Left",
                                rate_hz=165.0, bands=[(20.0, 5.0)])
    assert ev.era is not None and ev.cluster is not None
    assert aud.n_eras >= 2
    assert ev.hemisphere == "Left"


def test_unknown_channel_is_reported_not_silently_empty():
    ev, aud = EV.build_evidence(_psd(), _epochs(), channel="NOPE", hemisphere="Left",
                                rate_hz=165.0, bands=[(20.0, 5.0)])
    assert ev is None and "no PSD rows" in aud.reason_unusable


def test_build_all_keys_on_channel_hemisphere_rate_and_audits_unusable_cells():
    got, audit = EV.build_all(_psd(), _epochs(), rates=[165.0, 55.0], bands=[(20.0, 5.0)])
    assert ("ZERO_TWO_LEFT", "Left", 165.0) in got
    assert not audit.empty and "usable" in audit.columns
    assert (~audit.usable).any()                 # the 55 Hz cell is unusable and still listed
    assert audit.loc[~audit.usable, "reason_unusable"].notna().all()


def test_hemisphere_must_be_named_explicitly():
    with pytest.raises(ValueError, match="hemisphere"):
        EV.build_evidence(_psd(), _epochs(), channel="ZERO_TWO_LEFT", hemisphere="both",
                          rate_hz=165.0)


# --- joint prior exposure: the failure that produced a wrong clinic document -------------------
def _prior():
    """1.4 mA seen only at 60 us; 100 us seen only at 3.5 mA. Neither pairing is 1.4 @ 100."""
    return pd.DataFrame([
        dict(hemi="Left",  amp=1.4, pw=60.0,  rate=55.0),
        dict(hemi="Left",  amp=3.5, pw=100.0, rate=55.0),
        dict(hemi="Right", amp=3.0, pw=150.0, rate=55.0),
    ])


def test_marginal_familiarity_does_not_imply_the_pair_was_ever_delivered():
    """The exact bug: a plan built from individually-familiar numbers, novel as a combination.

    1.4 mA appears at 55 Hz. 100 us appears at 55 Hz. The PAIR 1.4 mA @ 100 us never happened,
    and an amplitude-only check cannot see that.
    """
    c = pd.DataFrame([dict(id="novel_pair", rate=55.0, ampL=1.4, ampR=3.0,
                           pwL=100.0, pwR=150.0)])
    kept, rej = SCHED.safety_filter(c, delivered_envelope=ENV, amp_ceiling=4.9,
                                    prior_triples=_prior())
    assert kept.empty, "a novel combination must not pass"
    assert "NEVER been delivered" in rej.iloc[0]["reject_reason"]
    assert rej.iloc[0]["prior_joint_L"] == 0
    # and it would have PASSED without the joint check, which is why the check exists
    kept2, _ = SCHED.safety_filter(c, delivered_envelope=ENV, amp_ceiling=4.9,
                                   prior_triples=None)
    assert len(kept2) == 1


def test_a_genuinely_delivered_triple_passes_and_reports_its_record_count():
    c = pd.DataFrame([dict(id="real", rate=55.0, ampL=1.4, ampR=3.0, pwL=60.0, pwR=150.0)])
    kept, rej = SCHED.safety_filter(c, delivered_envelope=ENV, amp_ceiling=4.9,
                                    prior_triples=_prior())
    assert len(kept) == 1 and rej.empty
    assert kept.iloc[0]["prior_joint_L"] == 1 and kept.iloc[0]["prior_joint_R"] == 1


def test_joint_check_is_opt_in_and_validates_its_own_input():
    c = pd.DataFrame([dict(id="x", rate=55.0, ampL=1.4, ampR=3.0, pwL=60.0, pwR=150.0)])
    with pytest.raises(KeyError, match="prior_triples missing"):
        SCHED.safety_filter(c, delivered_envelope=ENV,
                            prior_triples=_prior().rename(columns={"pw": "pulse_width"}))


# --- the dB convention, and the assembled-matrix adapter (2026-09-02) --------------------------
def test_the_platform_stores_decibels_and_undoing_it_wrongly_is_silent():
    """streaming_psd.psd_rows_to_matrix stores 10*log10(power). Using 10**logX is wrong by a
    factor of ten IN THE EXPONENT and still returns finite, plausible numbers — no exception,
    just band powers inflated by orders of magnitude. Hence the explicit log_scale.
    """
    power = np.array([[4.0, 16.0]])
    db = 10.0 * np.log10(power)                      # what the platform actually stores
    f = np.array([10.0, 11.0])
    got = EV.band_power_linear(db, f, 10.5, 2.0, log_scale="db10")
    assert got[0] == pytest.approx(4.0 + 16.0)
    wrong = EV.band_power_linear(db, f, 10.5, 2.0, log_scale="log10")
    assert wrong[0] > 100 * got[0], "the two conventions must differ enough to matter"
    assert np.isfinite(wrong[0]), "and the wrong one is finite, which is why it is dangerous"


def test_db10_is_the_default_because_that_is_what_the_platform_stores():
    assert EV.DEFAULT_LOG_SCALE == "db10"
    power = np.array([[4.0, 16.0]])
    db = 10.0 * np.log10(power)
    f = np.array([10.0, 11.0])
    assert EV.band_power_linear(db, f, 10.5, 2.0)[0] == pytest.approx(20.0)


def test_unknown_log_scale_raises_rather_than_guessing():
    with pytest.raises(ValueError, match="log_scale"):
        EV.band_power_linear(np.zeros((1, 2)), np.array([1.0, 2.0]), 1.5, 2.0, log_scale="ln")


def _matrix(n=6):
    f_set = np.arange(1.0, 41.0, 1.0)
    return {"logX": np.full((n, f_set.size), -1.0), "t": np.arange(n) * 600.0 + 1_760_000_000,
            "channel": np.array(["ZERO_TWO_LEFT"] * n, dtype=object),
            "source": np.array(["td"] * (n - 2) + ["montage"] * 2, dtype=object),
            "f_set": f_set}


def test_frame_from_matrix_attaches_the_shared_frequency_axis_to_every_row():
    """f_set is ONE axis for all rows, not per-row; the frame builder must not re-derive it."""
    fr = EV.frame_from_matrix(_matrix())
    assert list(fr.columns) == ["t", "channel", "source", "log_psd", "freqs"]
    assert len(fr) == 6
    assert all(len(x) == 40 for x in fr.freqs)
    assert np.array_equal(fr.freqs.iloc[0], fr.freqs.iloc[-1])


def test_frame_from_matrix_can_restrict_sources_but_keeps_all_by_default():
    assert len(EV.frame_from_matrix(_matrix())) == 6
    assert len(EV.frame_from_matrix(_matrix(), sources=["td"])) == 4


def test_frame_from_matrix_refuses_a_shape_mismatch():
    m = _matrix(); m["f_set"] = np.arange(1.0, 10.0)
    with pytest.raises(ValueError, match="frequency columns"):
        EV.frame_from_matrix(m)
    with pytest.raises(KeyError, match="missing"):
        EV.frame_from_matrix({"logX": np.zeros((2, 2))})


def test_matrix_to_evidence_round_trip_uses_the_db_convention():
    """End to end: assembled matrix -> frame -> evidence, with band power on the linear scale."""
    m = _matrix(n=40)
    m["t"] = np.arange(40) * 600.0 + 1_760_000_000
    fr = EV.frame_from_matrix(m)
    ev, aud = EV.build_evidence(fr, _epochs(), channel="ZERO_TWO_LEFT", hemisphere="Left",
                                rate_hz=165.0, bands=[(20.0, 5.0)])
    assert ev is not None and aud.n_final > 0
    bp = ev.power_for(20.0, 5.0)
    # logX is a flat -1 dB, so linear power density is 10**(-0.1) per bin over 5 bins at 1 Hz
    assert bp[0] == pytest.approx(5 * 10 ** (-0.1), rel=1e-6)


# --- production column names (2026-09-02) ------------------------------------------------------
def _epochs_production():
    """EXACTLY the columns adapter.exposure_epochs emits, verified against a live run.

    The first draft of lfp_evidence hardcoded 'rate' / 'amp_Left' / 'visit'. Every test passed
    because the fixtures used those invented names; the first live call raised KeyError: 'rate'.
    This fixture exists so the module is tested against what production actually hands it.
    """
    s = pd.to_datetime(1_760_000_000, unit="s", utc=True)
    return pd.DataFrame([
        dict(epoch=1, t_start=s, t_end=s + pd.Timedelta(hours=2), freq_hz=165.0,
             amp_mA_Left=1.6, amp_mA_Right=2.0, pw_us_Left=100.0, pw_us_Right=150.0,
             cathode_Left="2a-2b-2c", cathode_Right="1a", dur_h=2.0, open_ended=False),
        dict(epoch=2, t_start=s + pd.Timedelta(days=40), t_end=s + pd.Timedelta(days=40, hours=2),
             freq_hz=165.0, amp_mA_Left=2.4, amp_mA_Right=2.0, pw_us_Left=100.0, pw_us_Right=150.0,
             cathode_Left="2a-2b-2c", cathode_Right="1a", dur_h=2.0, open_ended=False),
    ])


def _psd_production(epochs):
    f = np.arange(1.0, 41.0, 1.0)
    ts = []
    for r in epochs.itertuples():
        base = r.t_start.timestamp()
        ts += [base + 600, base + 1200, base + 1800]
    n = len(ts)
    return pd.DataFrame({"t": np.array(ts, float), "channel": ["ZERO_TWO_LEFT"] * n,
                         "source": ["TD streaming"] * n,
                         "log_psd": list(np.full((n, f.size), -1.0)), "freqs": [f] * n})


def test_build_evidence_accepts_the_adapters_real_column_names():
    ep = _epochs_production()
    ev, aud = EV.build_evidence(_psd_production(ep), ep, channel="ZERO_TWO_LEFT",
                                hemisphere="Left", rate_hz=165.0, bands=[(20.0, 5.0)])
    assert ev is not None, aud.reason_unusable
    assert aud.rate_col == "freq_hz" and aud.amp_col == "amp_mA_Left"
    assert aud.amplitudes == (1.6, 2.4)


def test_right_hemisphere_resolves_to_its_own_amplitude_column():
    ep = _epochs_production()
    ep.loc[1, "amp_mA_Right"] = 3.0            # give the right side two levels
    _, aud = EV.build_evidence(_psd_production(ep), ep, channel="ZERO_TWO_LEFT",
                               hemisphere="Right", rate_hz=165.0, bands=[(20.0, 5.0)])
    assert aud.amp_col == "amp_mA_Right"


def test_missing_rate_column_names_what_it_tried():
    ep = _epochs_production().drop(columns=["freq_hz"])
    with pytest.raises(KeyError, match="stimulation rate"):
        EV.build_evidence(_psd_production(_epochs_production()), ep, channel="ZERO_TWO_LEFT",
                          hemisphere="Left", rate_hz=165.0, bands=[(20.0, 5.0)])


def test_era_falls_back_to_calendar_month_not_one_era_per_epoch():
    """Per-epoch eras would leave one observation per stratum: blocking with no blocking power,
    and a large era count in the audit hiding it. Calendar months group real exposures."""
    ep = _epochs_production()                   # two epochs 40 days apart, no visit column
    ev, aud = EV.build_evidence(_psd_production(ep), ep, channel="ZERO_TWO_LEFT",
                                hemisphere="Left", rate_hz=165.0, bands=[(20.0, 5.0)])
    assert "calendar month" in aud.era_source
    assert aud.n_eras == 2                      # two distinct months, not six windows
    assert len(set(ev.era)) == 2


def test_an_explicit_era_column_wins_and_is_recorded():
    ep = _epochs_production().assign(visit=[7, 7])
    ev, aud = EV.build_evidence(_psd_production(ep), ep, channel="ZERO_TWO_LEFT",
                                hemisphere="Left", rate_hz=165.0, bands=[(20.0, 5.0)])
    assert aud.era_source == "column 'visit'" and aud.n_eras == 1


# --- deployability screening and cell selection (2026-09-02) -----------------------------------
class _Res:
    """Minimal stand-in for lfp_response.ResponseResult, so screening is tested in isolation.

    `slope` defaults NEGATIVE because that is the direction Adaptive Therapy needs (band power
    falling as amplitude rises). The stub originally carried no slope at all, which is why the
    screen could require era significance without ever checking the sign — the fixture could not
    have caught it.
    """
    def __init__(self, responds, slope_p, sep_d, slope=-0.2):
        self.responds, self.slope_p, self.separation_d = responds, slope_p, sep_d
        self.slope_log_per_mA = slope


class _Ev:
    def __init__(self, amps, n_bands=18):
        self.amplitude_mA = np.array(amps, float)
        self.era = np.array(["a", "b"] * (len(amps) // 2 + 1))[:len(amps)]
        self.cluster = np.arange(len(amps))
        self.band_power = {(float(c), 5.0): np.ones(len(amps)) for c in range(10, 10 + n_bands)}

    def power_for(self, c, w):
        return self.band_power[(float(c), float(w))]


def _fn(responds, slope_p, sep_d=1.2, slope=-0.2):
    """`slope` defaults negative, the direction Adaptive Therapy needs. Pass a positive value to
    exercise the case where the confound-adjusted relationship runs the wrong way."""
    return lambda power, amp, era=None, cluster=None: _Res(responds, slope_p, sep_d, slope)


LIMIT = 5.0


def test_a_response_measured_above_the_hard_limit_is_not_deployable_evidence():
    """The principle survives the retraction; only the envelope changed. A response measured
    entirely above the programmable amplitude is not evidence for a policy below it. Under the
    flat 5 mA limit this now takes a 5.4 mA arm, where the energy model refused 4.8 mA at 165 Hz.
    """
    ev = {("ch", "Left", 165.0): _Ev([2.4, 5.4])}
    screen, best = EV.screen_cells(ev, response_fn=_fn(True, 0.001), amp_ceiling=LIMIT)
    assert best is None
    row = screen.iloc[0]
    assert row.n_responding == 18 and not row.deployable
    assert not row.within_amp_limit
    assert "hard limit" in row.blocking_reasons


def test_the_previously_energy_refused_cells_now_qualify():
    """The concrete consequence on RCS08: 4.8 mA at 165 Hz and 4.0 mA at 110 Hz were refused by
    the energy cap (3.35 and 3.18 mA). Under a flat 5 mA limit neither breaches."""
    ev = {("a", "Left", 165.0): _Ev([1.6, 4.8]), ("b", "Left", 110.0): _Ev([1.0, 4.0])}
    screen, best = EV.screen_cells(ev, response_fn=_fn(True, 0.001), amp_ceiling=LIMIT)
    assert screen.within_amp_limit.all() and screen.deployable.all()
    assert best is not None


def test_screen_cells_refuses_the_retracted_parameters():
    ev = {("ch", "Left", 55.0): _Ev([1.6, 4.0])}
    with pytest.raises(TypeError):
        EV.screen_cells(ev, response_fn=_fn(True, 0.001), energy_budget={"Left": 1.0})


def test_an_in_budget_responding_cell_is_deployable_and_selected():
    ev = {("ch", "Left", 55.0): _Ev([1.6, 4.0])}
    screen, best = EV.screen_cells(ev, response_fn=_fn(True, 0.001), amp_ceiling=LIMIT)
    assert best == ("ch", "Left", 55.0)
    assert screen.iloc[0].deployable and screen.iloc[0].within_amp_limit


def test_a_cell_whose_slope_dies_under_era_blocking_is_refused():
    ev = {("ch", "Left", 55.0): _Ev([1.6, 4.0])}
    screen, best = EV.screen_cells(ev, response_fn=_fn(True, 0.40), amp_ceiling=LIMIT)
    assert best is None
    assert "era-blocked slope" in screen.iloc[0].blocking_reasons


def test_one_lucky_band_of_eighteen_is_not_a_finding():
    """Overlapping bands move together, so the best of a correlated family is not evidence."""
    ev = {("ch", "Left", 55.0): _Ev([1.6, 4.0])}
    calls = {"n": 0}

    def one_only(power, amp, era=None, cluster=None):
        calls["n"] += 1
        return _Res(calls["n"] == 1, 0.001, 1.2)

    screen, best = EV.screen_cells(ev, response_fn=one_only, amp_ceiling=LIMIT)
    assert best is None
    assert screen.iloc[0].n_responding == 1
    assert "correlated family" in screen.iloc[0].blocking_reasons


def test_a_failing_cell_is_never_selected_on_the_strength_of_its_separation():
    ev = {("ch", "Left", 165.0): _Ev([2.4, 5.4]),          # huge separation, over the limit
          ("ch", "Left", 55.0): _Ev([1.6, 4.0])}           # modest, within the limit
    def by_rate(power, amp, era=None, cluster=None):
        return _Res(True, 0.001, 9.9 if len(amp) and max(amp) > 5.0 else 0.6)
    screen, best = EV.screen_cells(ev, response_fn=by_rate, amp_ceiling=LIMIT)
    assert best == ("ch", "Left", 55.0)


def test_select_for_refuses_evidence_from_a_different_rate():
    """Artifact scales with rate, so a response at one rate says nothing about another."""
    ev = {("ch", "Left", 55.0): _Ev([1.6, 4.0])}
    got, why = EV.select_for(ev, rate_hz=165.0, hemisphere="Left")
    assert got is None and "no evidence for Left at 165 Hz" in why
    got2, why2 = EV.select_for(ev, rate_hz=55.0, hemisphere="Left")
    assert got2 is not None and "@55 Hz" in why2


def test_select_for_refuses_to_pick_a_channel_silently():
    ev = {("a", "Left", 55.0): _Ev([1.6, 4.0]), ("b", "Left", 55.0): _Ev([1.6, 4.0])}
    got, why = EV.select_for(ev, rate_hz=55.0, hemisphere="Left")
    assert got is None and "ambiguous" in why
    got2, _ = EV.select_for(ev, rate_hz=55.0, hemisphere="Left", channel="b")
    assert got2 is not None


def test_empty_evidence_screens_to_nothing_without_raising():
    screen, best = EV.screen_cells({}, response_fn=_fn(True, 0.001))
    assert screen.empty and best is None


# --- the era-blocked slope must point the RIGHT WAY, not merely be significant (2026-09-02) ------
def test_a_significant_but_POSITIVE_adjusted_slope_is_refused():
    """REGRESSION, and it changed a live verdict. screen_cells counted bands whose era-blocked
    slope was significant and never checked its sign, which inverted the purpose of the condition:
    a cell passed when its raw arm means fell while the confound-ADJUSTED relationship rose, i.e.
    exactly when the apparent response was a time artifact. On RCS08 the cell the screen SELECTED
    as best (ZERO_TWO_LEFT/Left/55 Hz) had all 18 bands significantly POSITIVE, median +0.4387.
    """
    ev = {("ch", "Left", 55.0): _Ev([1.6, 4.0])}
    screen, best = EV.screen_cells(
        ev, response_fn=_fn(True, 0.001, slope=+0.44), amp_ceiling=LIMIT)
    row = screen.iloc[0]
    assert row.n_responding == 18 and row.n_era_significant == 18
    assert row.n_era_negative_significant == 0
    assert not row.deployable and best is None
    assert "NEGATIVE era-blocked slope" in row.blocking_reasons
    assert "time artifact" in row.blocking_reasons


def test_a_negative_adjusted_slope_in_a_majority_is_required_not_one_lucky_band():
    """The correlated-family argument applies to the SIGN as well as to the responding fraction.
    Applying it to one and not the other let a cell through on 3 of 18 negative bands with a
    positive median slope."""
    def mostly_positive(power, amp, era=None, cluster=None):
        mostly_positive.i += 1
        neg = mostly_positive.i <= 3            # only 3 of 18 bands negative
        return _Res(True, 0.001, 0.9, slope=(-0.2 if neg else +0.2))
    mostly_positive.i = 0
    ev = {("ch", "Left", 110.0): _Ev([2.5, 4.0])}
    screen, best = EV.screen_cells(ev, response_fn=mostly_positive, amp_ceiling=LIMIT)
    row = screen.iloc[0]
    assert row.n_era_negative_significant == 3 and row.n_bands == 18
    assert not row.deployable and best is None
