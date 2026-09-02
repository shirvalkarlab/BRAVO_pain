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


# --- the energy budget -------------------------------------------------------------------------
def _census():
    """SYNTHETIC. Left reaches 4.5 mA and 180 us at 55 Hz but NEVER TOGETHER — the whole point.

    These numbers are invented to make the max-of-product rule bite cleanly; they are NOT RCS08's.
    Do not quote the 180 us or the resulting 1.8x ratio as facts about the patient — that mistake
    was made once, in a clinic planning document. On RCS08's chronic census the maximum amplitude
    and maximum pulse width at 55 Hz occur in the SAME epoch, so the real ratio there is 1.00x; on
    the acute step log pulse width reaches 290 us and the ratio is 2.90x.
    """
    return pd.DataFrame([
        dict(hemi="Left",  amp=4.5, pw=100.0, rate=55.0),
        dict(hemi="Left",  amp=2.0, pw=180.0, rate=55.0),
        dict(hemi="Left",  amp=4.8, pw=100.0, rate=165.0),   # different rate, must not be used
        dict(hemi="Right", amp=4.5, pw=160.0, rate=55.0),
        dict(hemi="Right", amp=0.0, pw=160.0, rate=55.0),    # off; must be excluded
    ])


def test_budget_is_max_of_the_product_not_the_product_of_maxima():
    """max(amp)**2 * max(pw) would invent an exposure the patient never received."""
    ref = OBJ.energy_reference_from_record(_census())
    assert ref["Left"]["amp_mA"] == 4.5 and ref["Left"]["pw_us"] == 100.0
    assert ref["Left"]["teed"] == pytest.approx(4.5 ** 2 * 100.0 * 55.0)
    naive = 4.5 ** 2 * 180.0 * 55.0          # what separate maxima would give
    assert ref["Left"]["teed"] < naive
    assert naive / ref["Left"]["teed"] == pytest.approx(1.8)


def test_budget_uses_only_the_reference_rate_and_ignores_stim_off():
    ref = OBJ.energy_reference_from_record(_census(), rate_hz=55.0)
    assert ref["Left"]["rate_hz"] == 55.0
    # the 4.8 mA / 165 Hz row is more energetic but is at the wrong rate
    assert ref["Left"]["amp_mA"] != 4.8
    assert ref["Right"]["amp_mA"] == 4.5           # not the 0.0 mA row


def test_hemisphere_absent_at_the_reference_rate_is_omitted_not_substituted():
    c = pd.DataFrame([dict(hemi="Left", amp=1.0, pw=60.0, rate=110.0)])
    assert OBJ.energy_reference_from_record(c) == {}


# --- the ceiling -------------------------------------------------------------------------------
def test_ceiling_scales_as_the_square_root_of_the_rate_ratio():
    budget = 4.5 ** 2 * 100.0 * 55.0
    at55 = OBJ.energy_matched_ceiling(55.0, 100.0, budget)
    assert at55 == pytest.approx(4.5)
    assert OBJ.energy_matched_ceiling(110.0, 100.0, budget) == pytest.approx(4.5 * np.sqrt(0.5))
    assert OBJ.energy_matched_ceiling(165.0, 100.0, budget) == pytest.approx(4.5 / np.sqrt(3.0))
    # and the delivered energy at the cap equals the budget, which is the definition
    cap = OBJ.energy_matched_ceiling(165.0, 100.0, budget)
    assert cap ** 2 * 100.0 * 165.0 == pytest.approx(budget)


def test_shorter_pulse_width_buys_amplitude_at_the_same_energy():
    budget = 4.5 ** 2 * 100.0 * 55.0
    assert (OBJ.energy_matched_ceiling(165.0, 60.0, budget)
            > OBJ.energy_matched_ceiling(165.0, 100.0, budget))


def test_ceiling_must_be_clamped_because_low_rates_are_permissive():
    """At 10 Hz the energy-matched value is ~10.5 mA. Unclamped, an energy-only gate is unsafe."""
    budget = 4.5 ** 2 * 100.0 * 55.0
    assert OBJ.energy_matched_ceiling(10.0, 100.0, budget) > 10.0
    assert OBJ.energy_matched_ceiling(10.0, 100.0, budget, amp_ceiling=4.9) == pytest.approx(4.9)


def test_ceiling_refuses_nonsense_inputs():
    for bad in ((0.0, 100.0, 1.0), (55.0, 0.0, 1.0)):
        with pytest.raises(ValueError):
            OBJ.energy_matched_ceiling(*bad)
    with pytest.raises(ValueError):
        OBJ.energy_matched_ceiling(55.0, 100.0, 0.0)


# --- the filter --------------------------------------------------------------------------------
ENV = {"Left": (0.0, 4.9), "Right": (0.0, 4.9)}
BUDGET = {"Left": 4.5 ** 2 * 100.0 * 55.0, "Right": 4.5 ** 2 * 160.0 * 55.0}


def _cands():
    return pd.DataFrame([
        dict(id="ok55",   rate=55.0,  ampL=4.5, ampR=3.0, pwL=100.0, pwR=160.0),
        dict(id="hot165", rate=165.0, ampL=4.5, ampR=3.0, pwL=100.0, pwR=160.0),
        dict(id="heldR",  rate=165.0, ampL=2.4, ampR=3.0, pwL=100.0, pwR=160.0),
        dict(id="fine165", rate=165.0, ampL=2.4, ampR=2.0, pwL=100.0, pwR=160.0),
    ])


def test_the_gate_catches_a_constant_amplitude_that_is_not_a_constant_energy():
    """`heldR` varies only the LEFT amplitude; the right sits untouched at 3.0 mA and breaches."""
    kept, rej = SCHED.safety_filter(_cands(), delivered_envelope=ENV, amp_ceiling=4.9,
                                    energy_budget=BUDGET)
    assert set(kept.id) == {"ok55", "fine165"}
    r = rej.set_index("id")
    assert "RIGHT exceeds" in r.loc["heldR", "reject_reason"]
    assert "constant amplitude is not a constant energy" in r.loc["heldR", "reject_reason"]
    # the right side is over budget even though nobody varied it
    assert r.loc["heldR", "teed_pct_R"] > 100
    assert r.loc["heldR", "teed_pct_L"] <= 100


def test_the_gate_reports_the_energy_fraction_so_a_reader_can_audit_it():
    kept, rej = SCHED.safety_filter(_cands(), delivered_envelope=ENV, amp_ceiling=4.9,
                                    energy_budget=BUDGET)
    assert kept.set_index("id").loc["ok55", "teed_pct_L"] == 100      # the reference cell itself
    hot = rej.set_index("id").loc["hot165"]
    assert hot["teed_pct_L"] == pytest.approx(300, abs=1)             # 3x at 3x the rate
    assert "energy" in hot["reject_reason"].lower()


def test_amplitude_alone_cannot_be_energy_checked_so_the_gate_refuses_to_guess():
    bare = _cands().drop(columns=["pwL"])
    with pytest.raises(KeyError, match="energy gate needs"):
        SCHED.safety_filter(bare, delivered_envelope=ENV, amp_ceiling=4.9, energy_budget=BUDGET)


def test_energy_gate_is_opt_in_so_existing_single_rate_callers_are_unchanged():
    kept, rej = SCHED.safety_filter(_cands(), delivered_envelope=ENV, amp_ceiling=4.9,
                                    energy_budget=None)
    assert len(kept) == 4 and rej.empty
    assert "teed_pct_L" not in kept.columns


def test_declared_ceiling_still_binds_independently_of_energy():
    """A low rate makes the energy cap permissive; the declared ceiling must still refuse."""
    c = pd.DataFrame([dict(id="low", rate=10.0, ampL=6.0, ampR=1.0, pwL=100.0, pwR=160.0)])
    kept, rej = SCHED.safety_filter(c, delivered_envelope={"Left": (0, 9), "Right": (0, 9)},
                                    amp_ceiling=4.9, energy_budget=BUDGET)
    assert kept.empty
    assert "ceiling" in rej.iloc[0]["reject_reason"]


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
                                    energy_budget=BUDGET, prior_triples=_prior())
    assert kept.empty, "a novel combination must not pass"
    assert "NEVER been delivered" in rej.iloc[0]["reject_reason"]
    assert rej.iloc[0]["prior_joint_L"] == 0
    # and it would have PASSED without the joint check, which is why the check exists
    kept2, _ = SCHED.safety_filter(c, delivered_envelope=ENV, amp_ceiling=4.9,
                                   energy_budget=BUDGET, prior_triples=None)
    assert len(kept2) == 1


def test_a_genuinely_delivered_triple_passes_and_reports_its_record_count():
    c = pd.DataFrame([dict(id="real", rate=55.0, ampL=1.4, ampR=3.0, pwL=60.0, pwR=150.0)])
    kept, rej = SCHED.safety_filter(c, delivered_envelope=ENV, amp_ceiling=4.9,
                                    energy_budget=BUDGET, prior_triples=_prior())
    assert len(kept) == 1 and rej.empty
    assert kept.iloc[0]["prior_joint_L"] == 1 and kept.iloc[0]["prior_joint_R"] == 1


def test_joint_check_is_opt_in_and_validates_its_own_input():
    c = pd.DataFrame([dict(id="x", rate=55.0, ampL=1.4, ampR=3.0, pwL=60.0, pwR=150.0)])
    with pytest.raises(KeyError, match="prior_triples missing"):
        SCHED.safety_filter(c, delivered_envelope=ENV, amp_ceiling=4.9,
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
