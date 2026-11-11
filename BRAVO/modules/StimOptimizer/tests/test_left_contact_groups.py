"""Stage 1 groups stretches of unchanged settings by Left contact as well as by pulse widths (step A
of the contact-aware plan, the PI's go-ahead of 2026-09-30; his rulings of 2026-10-01: the contact
is part of every group label, and a stretch with Left at 0 mA belongs to every Left contact group,
because with no current the contact makes no difference).

Until this change the model never read the contacts: "contact" and "cathode" occurred 0 times in
the surrogate, the objective, the acquisition and Stage 1, so ring 1 and ring 2 on the Left were
fitted as one surface (.planning/2026-09-30-contact-aware-stim-optimizer/findings.md).

Values, not shapes: the group keys, each group's stretch count (its own contact's stretches plus
the shared 0 mA ones), the count of distinct stretches fitted, the per-contact table, the contact
on every summary row, the configuration in force as the reference, and a record without contacts
grouped exactly as before.

Merged here 2026-10-05: test_fit_contact_group.py, test_contact_pooling.py, test_block_chooser.py (each under its own heading below).
"""
import numpy as np
import pandas as pd
import pytest

from StimOptimizer import stage1_openloop as S1

from StimOptimizer.routines import contact_pooling as CPL

from StimOptimizer.routines import block_chooser as BC


# ---------------------------------------------------------------------------------------------
# borrowing across rates AND pulse widths (the PI, 2026-10-01: "extend it to borrow across
# pulse widths"): a contact with clinic stretches at other rates and pulse widths gets a surface
# read at the block's rate and the pulse widths in force
# ---------------------------------------------------------------------------------------------
import pandas as pd

RING1 = "1a-1b-1c"
RING2 = "2a-2b-2c"


def _record(n_ring1=10, n_ring2=10, n_off=4, pw=(60.0, 160.0), rates=(55.0, 110.0), seed=0,
            ring2_better=0.0, last=RING1):
    """One pulse-width pair; Left ring 1, Left ring 2 and Left-off stretches; rates alternate.
    The newest stretch (the setting in force) is on `last`."""
    rng = np.random.default_rng(seed)
    rows = []
    kinds = [RING2] * n_ring2 + ["off"] * n_off + [RING1] * n_ring1
    if last == RING2:
        kinds = [RING1] * n_ring1 + ["off"] * n_off + [RING2] * n_ring2
    for i, kind in enumerate(kinds):
        amp_left = 0.0 if kind == "off" else 1.0 + 0.25 * (i % 6)
        rows.append(dict(
            epoch=float(i + 1), freq_hz=float(rates[i % len(rates)]),
            pw_us_Left=pw[0], pw_us_Right=pw[1],
            amp_mA_Left=amp_left, amp_mA_Right=1.5 + 0.25 * (i % 4),
            cathode_Left=(RING2 if kind == "off" else kind), cathode_Right="1a-1b-1c-2a-2b-2c",
            n=6.0, dur_h=150.0, n_rating_days=2.0,
            left_leg_vas=float(50.0 - 10.0 * ring2_better * (kind == RING2) + 3.0 * rng.standard_normal()),
            left_leg_vas_sd=8.0))
    d = pd.DataFrame(rows)
    d["t0"] = pd.date_range("2025-07-01", periods=len(d), freq="3D", tz="UTC")
    return d


# Stage 1 runs here without its calibration check (`calibration_check=False`, 2026-10-02): a
# warning that changes no recommendation (decision 233, ruling 6), read by no test in this file,
# and held by `test_stratum_calibration.py`; its leave-one-out refits were most of each fit's time.
@pytest.fixture(scope="module")
def two_contacts():
    return S1.run_stage1(_record(), data_horizon="test", washin_min=1.0, calibration_check=False)


# ---------------------------------------------------------------------------------------------
# the label
# ---------------------------------------------------------------------------------------------
def test_the_left_contact_label_is_the_clinic_sheets_own_and_0_mA_is_off():
    assert S1.left_contact_label("1a-1b-1c-2a-2b-2c", 2.0) == "L C+1-2-"
    assert S1.left_contact_label("2a-2b-2c", 1.5) == "L C+2-"
    assert S1.left_contact_label("2a", 4.8) == "L C+2a-"
    assert S1.left_contact_label("2a-2b-2c", 0.0) == S1.LEFT_OFF
    # the clinic sheet's own text, read for its Left part
    assert S1.left_contact_label("L C+2- / R C+1-2-", 1.0) == "L C+2-"
    assert S1.left_contact_label(None, 1.0) is None
    assert S1.left_contact_label("", 1.0) is None


#: The contact text as the clinic sheets type it (read from RCS08's 524 parsed clinic steps,
#: 2026-10-01), and the Left contact each one means. Left lead contacts are 0-3, Right 8-11;
#: text after "/" is the sEEG contacts, not the stimulator; "1+2-" is bipolar.
CLINIC_TEXT = [
    ("L C+2- / R C+1-2-", "L C+2-"),
    ("L 2a-2b-2c / R 1a-1b-1c-2a-2b-2c", "L C+2-"),
    ("C+2-9-10- / LGPi4-RPVG5-", "L C+2-"),
    ("C+1-9-10- / SHAM", "L C+1-"),
    ("1+2- / LGPi4+LGPi5-", "L 1+2-"),
    ("1+2-9+10- / LGPi4-RPVG5-", "L 1+2-"),
    ("1+2- 9-10- / LGPi4+LGPi5- RPVG5-", "L 1+2-"),
    ("0+2-9-10- / LGPi4-RPVG5-", "L 0+2-"),
    ("1+3- / LGPi4+LGPi6-", "L 1+3-"),
    ("C+2a- / LGPi5-", "L C+2a-"),
    ("C+1a-2a- / LGPi4-LGPi5-", "L C+1a-2a-"),
    ("c+ 1-", "L C+1-"),
    ("C+9-10- / RPVG5-", None),        # Right only: no Left contact
    ("9+10- / RPVG5+RPVG5-", None),
    ("10+9- / RPVG5+RPVG5-", None),
    ("c+0", None),                     # no polarity on 0: not readable
    ("LGPi5- RPVG5-", None),           # sEEG contacts only: no Left stimulator contact
    ("c+ 1b-1c- (1.5mA from both b and c)", "L C+1b-1c-"),
]


@pytest.mark.parametrize("text,label", CLINIC_TEXT)
def test_the_clinic_sheets_contact_text_is_read_for_its_left_contact(text, label):
    assert S1.left_contact_label(text, 1.0) == label


# ---------------------------------------------------------------------------------------------
# the groups
# ---------------------------------------------------------------------------------------------
def test_each_left_contact_gets_its_own_group_and_0_mA_stretches_join_both(two_contacts):
    res = two_contacts
    assert sorted(res.slices) == [(60.0, 160.0, "L C+1-"), (60.0, 160.0, "L C+2-")]
    # 10 of its own and the 4 with Left at 0 mA
    assert res.slices[(60.0, 160.0, "L C+1-")].n_epochs == 14
    assert res.slices[(60.0, 160.0, "L C+2-")].n_epochs == 14
    assert res.slices[(60.0, 160.0, "L C+1-")].left_contact == "L C+1-"


def test_the_shared_0_mA_stretches_are_counted_once_in_the_total(two_contacts):
    assert two_contacts.frozen.audit["n_epochs_in_fitted_strata"] == 24


def test_the_page_is_told_the_stretches_reports_and_days_per_left_contact(two_contacts):
    table = {r["left_contact"]: r for r in two_contacts.frozen.audit["left_contacts"]}
    assert set(table) == {"L C+1-", "L C+2-", S1.LEFT_OFF}
    assert table["L C+1-"]["n_epochs"] == 10 and table["L C+2-"]["n_epochs"] == 10
    assert table[S1.LEFT_OFF]["n_epochs"] == 4
    assert table["L C+1-"]["n_reports"] == 60.0
    assert table[S1.LEFT_OFF]["shared_into_every_contact"] is True


def test_every_summary_and_per_rate_row_names_its_left_contact(two_contacts):
    assert set(two_contacts.summary["left_contact"]) == {"L C+1-", "L C+2-"}
    assert set(two_contacts.rate_summary["left_contact"]) == {"L C+1-", "L C+2-"}
    keys = set(two_contacts.summary["joint_stratum_key"])
    assert keys == {"60_160_L C+1-", "60_160_L C+2-"}


def test_a_contact_below_the_minimum_is_skipped_with_its_reason_never_pooled():
    res = S1.run_stage1(_record(n_ring2=3, n_off=2), data_horizon="test", washin_min=1.0,
                        calibration_check=False)
    assert sorted(res.slices) == [(60.0, 160.0, "L C+1-")]
    reason = res.skipped["pwL60_pwR160_L C+2-"]
    assert "5 fitted stretches" in reason and "L C+2-" in reason


# ---------------------------------------------------------------------------------------------
# the setting in force is the reference
# ---------------------------------------------------------------------------------------------
def test_the_reference_is_the_group_with_the_pulse_widths_and_left_contact_in_force(two_contacts):
    fz = two_contacts.frozen
    assert fz.incumbent_left_contact == "L C+1-"
    for s in fz.settings:
        assert s.detail["left_contact"] in ("L C+1-", "L C+2-")
        assert s.detail["incumbent_left_contact"] == "L C+1-"


def test_a_clearly_better_contact_is_chosen_and_the_reasons_name_both_contacts():
    # ring 2 is 30 VAS points better than ring 1 against a noise SD of 3; ring 1 is in force
    res = S1.run_stage1(_record(ring2_better=3.0, seed=3), data_horizon="test", washin_min=1.0,
                        calibration_check=False)
    s = res.frozen.setting("Left")
    assert s.detail["left_contact"] == "L C+2-"
    assert any("L C+1-" in r and "L C+2-" in r for r in s.reasons)


# ---------------------------------------------------------------------------------------------
# a record without contacts is grouped exactly as before
# ---------------------------------------------------------------------------------------------
def test_a_record_without_contacts_is_grouped_by_pulse_widths_alone():
    d = _record().drop(columns=["cathode_Left", "cathode_Right"])
    res = S1.run_stage1(d, data_horizon="test", washin_min=1.0, calibration_check=False)
    assert sorted(res.slices) == [(60.0, 160.0, None)]
    assert res.slices[(60.0, 160.0, None)].n_epochs == 24
    assert res.frozen.audit["left_contacts"] == []
    assert set(res.summary["joint_stratum_key"]) == {"60_160"}


# ---------------------------------------------------------------------------------------------
# the fit pooled over pulse widths keeps contacts apart: the contact in force plus the 0 mA ones
# ---------------------------------------------------------------------------------------------
def test_the_pulse_width_pooled_fit_reads_the_contact_in_force_and_the_shared_0_mA_stretches():
    d = pd.concat([_record(), _record(pw=(100.0, 150.0)).assign(epoch=lambda x: x["epoch"] + 100)],
                  ignore_index=True)
    d["t0"] = pd.date_range("2025-07-01", periods=len(d), freq="3D", tz="UTC")
    res = S1.run_stage1(d, data_horizon="test", washin_min=1.0, pool_pulse_widths=True,
                        calibration_check=False)
    rows = res.pooled_rate_summary
    assert set(rows["left_contact"]) == {"L C+1-"}
    # per rate: half of (2 pairings x (10 ring 1 + 4 off)) = 14
    assert sorted(rows["n_epochs"]) == [14, 14]


# ---------------------------------------------------------------------------------------------
# the clinic stream: a stretch is one setting AND one Left contact
# ---------------------------------------------------------------------------------------------
def _clinic_step(i, contacts, amp_left, score=5.0):
    return dict(visit_date="v1", setting="clinic", file="f", sha256="x", t_local=None,
                t_utc=pd.Timestamp("2026-01-01", tz="UTC") + pd.Timedelta(minutes=i),
                amp_mA_Left=amp_left, amp_mA_Right=2.5, freq_hz=55.0, pw_us_Left=60.0,
                pw_us_Right=160.0, contacts_raw=contacts, duration_s=60.0,
                side_effect_score=np.nan, overall=np.nan, head=np.nan, back=np.nan,
                left_leg=score, left_foot=np.nan, right_leg=np.nan, right_foot=np.nan,
                notes=None, row_index=i)


def test_the_clinic_frame_keeps_two_left_contacts_at_the_same_currents_apart():
    from StimOptimizer import clinic_pain as CP
    steps = pd.DataFrame([_clinic_step(0, "C+1-9-10- / SHAM", 2.0, 4.0),
                          _clinic_step(1, "C+2-9-10- / SHAM", 2.0, 7.0),
                          _clinic_step(2, "C+2-9-10- / SHAM", 2.0, 6.0)])
    ep = CP.epoch_frame_from_steps(steps)
    assert len(ep) == 2
    by = {r["cathode_Left"]: r for _, r in ep.iterrows()}
    assert set(by) == {"L C+1-", "L C+2-"}
    assert by["L C+2-"]["n"] == 2 and by["L C+1-"]["n"] == 1


def test_the_clinic_frame_merges_left_0_mA_steps_whatever_their_contact_text():
    from StimOptimizer import clinic_pain as CP
    steps = pd.DataFrame([_clinic_step(0, "C+1-9-10- / SHAM", 0.0),
                          _clinic_step(1, "L C+2- / R C+1-2-", 0.0)])
    ep = CP.epoch_frame_from_steps(steps)
    assert len(ep) == 1 and ep.iloc[0]["n"] == 2


def test_the_next_visit_check_counts_only_the_left_contact_in_force_and_the_0_mA_stretches():
    from StimOptimizer import clinic_pain as CP
    steps = [_clinic_step(i, "C+1-9-10- / SHAM", 1.0 + 0.5 * i) for i in range(4)]
    steps += [_clinic_step(10 + i, "C+2-9-10- / SHAM", 1.0 + 0.5 * i) for i in range(5)]
    steps += [_clinic_step(20, "C+2-9-10- / SHAM", 0.0)]
    ep = CP.epoch_frame_from_steps(pd.DataFrame(steps))
    in_force = {"Left": {"rate_hz": 55.0, "pulse_width_us": 60.0, "amplitude_mA": 2.0,
                         "contacts_short": "L C+2-"},
                "Right": {"rate_hz": 55.0, "pulse_width_us": 160.0, "amplitude_mA": 2.5}}
    nsc = CP.next_session_coverage(ep, in_force)
    assert nsc["available"] is True
    assert nsc["n_epochs"] == 6                 # 5 on L C+2- and the 1 with Left at 0 mA
    assert nsc["left_contact"] == "L C+2-"
    assert "L C+2-" in nsc["sentence"]


# ================================================================================================
# From test_fit_contact_group.py (merged here 2026-10-05).
# Stage 1 fits each (Left pulse width, Right pulse width, Left contact) group through one function,
# `_fit_contact_group` (speed-up item B1, step one, 2026-10-01: a refactor with no change in any
# number; step two runs the groups in parallel processes, which needs the fit as a function of its
# own arguments only).
#
# Values, not shapes: the function is called once per group large enough to fit, its answers are the
# groups run_stage1 reports, and a group whose surface cannot be fitted is reported as skipped with
# the exception's own text, exactly as the loop did.
# ================================================================================================


def test_each_fitted_group_comes_from_one_call_of_the_group_function(monkeypatch):
    calls = []
    real = S1._fit_contact_group

    def spy(pwl, pwr, contact, sub, **kw):
        out = real(pwl, pwr, contact, sub, **kw)
        calls.append(((pwl, pwr, contact), len(sub), out))
        return out

    monkeypatch.setattr(S1, "_fit_contact_group", spy)
    res = S1.run_stage1(_record(), data_horizon="test", washin_min=1.0)
    assert len(res.slices) == 2
    assert [k for k, _n, _o in calls] == list(res.slices)
    for key, n, (sl, reason) in calls:
        assert reason is None
        assert res.slices[key] is sl
        assert sl.left_contact == key[2]
        assert sl.n_epochs == n
        assert sl.rate_strata and all(rs.left_contact == key[2] for rs in sl.rate_strata.values())


def test_a_group_that_cannot_be_fitted_is_skipped_with_the_exceptions_text(monkeypatch):
    def refuse(*a, **k):
        raise RuntimeError("no surface here")

    monkeypatch.setattr(S1, "_fit_joint_stratum", refuse)
    sl, reason = S1._fit_contact_group(60.0, 160.0, "L C+1-", _record().iloc[:8], grid=None,
                                       sgp_left=None, sgp_right=None, incumbent_xyz=None,
                                       fixed_length_scale=None, kappa=1.0, q=4, eta=1.0, beta=1.0,
                                       constraint=None, ceiling_mA=None, amp_grid=None,
                                       calibration_check=False, resolution_k=2.0)
    assert sl is None and reason == "RuntimeError: no surface here"
    res = S1.run_stage1(_record(), data_horizon="test", washin_min=1.0)
    assert res.slices == {}
    assert sorted(res.skipped.values()) == ["RuntimeError: no surface here"] * 2


# ================================================================================================
# From test_contact_pooling.py (merged here 2026-10-05).
# Step B of the contact-aware Stim Optimizer (the PI's go-ahead, 2026-10-01): one fit with a
# shared pain surface over (rate, Left current, Right current) plus a deviation per Left contact
# whose size the data estimate (`routines.contact_pooling`). Stretches with Left at 0 mA carry no
# deviation: with no current the contact makes no difference (his ruling of 2026-10-01).
#
# Values, not shapes, on constructed records where the answer is known: when ring 2 is truly
# better, the contact share is large, the no-contact-effect test rejects, and the partial-pooling
# fit predicts held-out days better than the old pooled fit; when the contacts are identical, the
# share is near zero and the test does not reject.
# ================================================================================================


def _pooling_record(effect, n_per=14, seed=0):
    """Two Left contacts and some Left-off stretches, one stretch a day, pain J in NRS points.
    `effect` = how much better (lower J) ring 2 is at the same currents."""
    rng = np.random.default_rng(seed)
    rows = []
    day = 0
    for contact in ("L C+1-", "L C+2-"):
        for k in range(n_per):
            day += 1
            aL = 0.5 + 0.25 * (k % 9)
            aR = 1.0 + 0.5 * (k % 4)
            j = -0.3 * aL + 0.1 * aR - (effect if contact == "L C+2-" else 0.0)
            rows.append(dict(freq_hz=55.0, amp_mA_Left=aL, amp_mA_Right=aR, left_contact=contact,
                             J=j + 0.3 * rng.standard_normal(), obs_var=0.09,
                             t0=pd.Timestamp("2025-01-01", tz="UTC") + pd.Timedelta(days=day)))
    for k in range(6):
        day += 1
        aR = 1.0 + 0.5 * (k % 4)
        rows.append(dict(freq_hz=55.0, amp_mA_Left=0.0, amp_mA_Right=aR, left_contact=CPL.LEFT_OFF,
                         J=0.1 * aR + 0.3 * rng.standard_normal(), obs_var=0.09,
                         t0=pd.Timestamp("2025-01-01", tz="UTC") + pd.Timedelta(days=day)))
    return pd.DataFrame(rows)


@pytest.fixture(scope="module")
def differ():
    return CPL.compare(_pooling_record(effect=1.5, seed=1))


@pytest.fixture(scope="module")
def same():
    return CPL.compare(_pooling_record(effect=0.0, seed=2))


def test_when_ring_2_is_truly_better_most_of_the_variation_is_the_contact(differ):
    assert differ["contact_share"] > 0.5
    assert differ["no_contact_effect_p"] < 0.01


def test_when_the_contacts_are_identical_the_contact_share_is_small_and_not_significant(same):
    assert same["contact_share"] < 0.2
    assert same["no_contact_effect_p"] > 0.05


def test_partial_pooling_predicts_held_out_days_better_than_ignoring_the_contact(differ):
    cv = differ["held_out"]
    assert cv["n_folds"] == 34                         # one stretch a day: 28 + 6 days
    assert cv["mae"]["partial"] < cv["mae"]["pooled"]
    # the difference and its interval: partial minus pooled, below zero means partial is better
    lo, hi = cv["mae_difference_ci"]["partial_minus_pooled"]
    assert hi < 0


def test_every_model_is_scored_on_the_same_held_out_stretches(differ):
    cv = differ["held_out"]
    assert set(cv["mae"]) == {"pooled", "separate", "partial"}
    assert len(cv["per_fold"]) == cv["n_folds"]
    assert all(set(f["error"]) == {"pooled", "separate", "partial"} for f in cv["per_fold"])


def test_left_off_stretches_carry_no_contact_deviation():
    d = _pooling_record(effect=1.5, seed=3)
    m = CPL.PartialPoolingGP().fit(d)
    off = d[d["left_contact"] == CPL.LEFT_OFF].iloc[[0]]
    # predicting a Left-off stretch under either contact label gives the same answer
    a = m.predict(off.assign(left_contact="L C+1-").assign(amp_mA_Left=0.0))
    b = m.predict(off.assign(left_contact="L C+2-").assign(amp_mA_Left=0.0))
    assert a[0] == pytest.approx(b[0], abs=1e-9)


def test_one_contact_only_says_so_and_fits_nothing():
    d = _pooling_record(effect=0.0)
    d = d[d["left_contact"] != "L C+2-"]
    out = CPL.compare(d)
    assert out["available"] is False
    assert "one Left contact" in out["reason"]


# ================================================================================================
# From test_block_chooser.py (merged here 2026-10-05).
# Step C of the contact-aware Stim Optimizer (`routines.block_chooser`; the PI's go-ahead and
# rulings of 2026-10-01): which (Left contact, rate) block to test at the next clinic visit.
#
# His choices: the candidates are every Left contact that has carried current in either stream,
# plus L C+1-2- (the only one that allows sensing on L 0-3); the blocks are ranked MOST PROMISING
# FIRST, by the largest plausible improvement in pain over the setting in force (predicted
# improvement + 2 SD) at a safe current pair under both sides' maxima. A block with no fitted
# surface gets the same bound from the stream's own spread of J (prior mean: no change). Rates
# below the closed-loop minimum are not offered. The session runs at the pulse-width pairing in
# force (ruling 5 of decision 233).
# ================================================================================================

AMPS = [0.0, 1.0, 2.0, 3.0, 4.0, 5.0]


def _surface(mu, sd, safe=None):
    n = len(AMPS)
    return {"amps_mA": AMPS, "mu": [[mu(i, j) for j in range(n)] for i in range(n)],
            "sd": [[sd(i, j) for j in range(n)] for i in range(n)],
            "safe": [[True if safe is None else safe(i, j) for j in range(n)] for i in range(n)]}


def _row(contact, rate, *, fitted, surface=None, n=10, pw=(100.0, 150.0)):
    return {"pw_us_left": pw[0], "pw_us_right": pw[1], "left_contact": contact, "rate_hz": rate,
            "fitted": fitted, "n_epochs": n, "surface": surface}


def _block(out, contact, rate=55.0):
    """The one block for this Left contact and rate (L C+1-2- is always a candidate too, so the
    block wanted is never assumed to be first)."""
    (b,) = [b for b in out["blocks"] if b["left_contact"] == contact and b["rate_hz"] == rate]
    return b


IN_FORCE = {"Left": {"contacts_short": "L C+2-", "pulse_width_us": 100.0, "rate_hz": 55.0},
            "Right": {"pulse_width_us": 150.0}}


def test_a_fitted_block_is_scored_by_its_best_plausible_improvement_at_a_safe_cell_under_the_maxima():
    # improvement = -mu; best plausible = -mu + 2 sd; the best cell is at (4, 4) mA but the Left
    # maximum is 3 mA, so the chooser must stop at Left 3 mA
    surf = _surface(mu=lambda i, j: -0.2 * i - 0.1 * j, sd=lambda i, j: 0.1)
    out = BC.rank_blocks([_row("L C+2-", 55.0, fitted=True, surface=surf)], in_force=IN_FORCE,
                         contacts_used=["L C+2-"], rates=[55.0], ceilings={"Left": 3.0, "Right": 4.0},
                         prior_sd=1.0)
    b = _block(out, "L C+2-")
    assert b["basis"] == "fitted surface"
    assert (b["amp_mA_left"], b["amp_mA_right"]) == (3.0, 4.0)
    assert b["optimistic_improvement"] == pytest.approx(0.2 * 3 + 0.1 * 4 + 2 * 0.1)
    assert b["predicted_improvement"] == pytest.approx(1.0)


def test_unsafe_cells_are_never_chosen():
    surf = _surface(mu=lambda i, j: -0.2 * i, sd=lambda i, j: 0.1, safe=lambda i, j: i <= 2)
    out = BC.rank_blocks([_row("L C+2-", 55.0, fitted=True, surface=surf)], in_force=IN_FORCE,
                         contacts_used=["L C+2-"], rates=[55.0], ceilings={"Left": 5.0, "Right": 5.0},
                         prior_sd=1.0)
    assert _block(out, "L C+2-")["amp_mA_left"] == 2.0


def test_a_block_with_no_surface_gets_the_prior_bound_and_says_so():
    out = BC.rank_blocks([], in_force=IN_FORCE, contacts_used=["L C+2-"], rates=[55.0],
                         ceilings={"Left": 4.5, "Right": 4.5}, prior_sd=0.8)
    b = _block(out, "L C+2-")
    assert b["basis"] == "no surface: the stream's own spread"
    assert b["optimistic_improvement"] == pytest.approx(1.6)
    assert b["predicted_improvement"] == 0.0


def test_c12_is_always_a_candidate_and_rates_below_the_closed_loop_minimum_are_not():
    out = BC.rank_blocks([], in_force=IN_FORCE, contacts_used=["L C+2-", "L C+1-"],
                         rates=[10.0, 55.0, 110.0], ceilings={"Left": 4.5, "Right": 4.5}, prior_sd=1.0)
    keys = {(b["left_contact"], b["rate_hz"]) for b in out["blocks"]}
    assert ("L C+1-2-", 55.0) in keys and ("L C+1-2-", 110.0) in keys
    assert all(r >= 55.0 for _, r in keys)
    assert len(keys) == 3 * 2
    assert out["rates_left_out"] == [10.0]


def test_blocks_are_ranked_most_promising_first():
    good = _surface(mu=lambda i, j: -1.0, sd=lambda i, j: 0.75)    # bound 1 + 1.5 = 2.5
    poor = _surface(mu=lambda i, j: 0.5, sd=lambda i, j: 0.2)      # bound -0.5 + 0.4 = -0.1
    rows = [_row("L C+2-", 55.0, fitted=True, surface=poor, n=12),
            _row("L C+1-", 55.0, fitted=True, surface=good, n=9)]
    out = BC.rank_blocks(rows, in_force=IN_FORCE, contacts_used=["L C+2-", "L C+1-"], rates=[55.0],
                         ceilings={"Left": 4.5, "Right": 4.5}, prior_sd=1.0)
    order = [(b["left_contact"], b["optimistic_improvement"]) for b in out["blocks"]]
    assert order[0] == ("L C+1-", pytest.approx(2.5))
    assert order[1][0] == "L C+1-2-"                # no surface: the prior bound, 2 x 1.0 = 2.0
    assert order[-1][0] == "L C+2-"
    assert [b["rank"] for b in out["blocks"]] == [1, 2, 3]


def test_only_the_pairing_in_force_is_read():
    other = _surface(mu=lambda i, j: -5.0, sd=lambda i, j: 0.1)
    rows = [_row("L C+2-", 55.0, fitted=True, surface=other, pw=(60.0, 160.0))]
    out = BC.rank_blocks(rows, in_force=IN_FORCE, contacts_used=["L C+2-"], rates=[55.0],
                         ceilings={"Left": 4.5, "Right": 4.5}, prior_sd=1.0)
    assert _block(out, "L C+2-")["basis"] == "no surface: the stream's own spread"
    assert out["pulse_widths_us"] == {"Left": 100.0, "Right": 150.0}


def test_the_top_block_comes_with_its_ladder_up_to_the_left_maximum():
    good = _surface(mu=lambda i, j: -2.0, sd=lambda i, j: 0.5)
    out = BC.rank_blocks([_row("L C+2-", 55.0, fitted=True, surface=good)], in_force=IN_FORCE,
                         contacts_used=["L C+2-"], rates=[55.0],
                         ceilings={"Left": 2.5, "Right": 3.0}, prior_sd=1.0)
    lad = out["next_block"]["ladder"]
    assert lad["steps_mA"][0] == 0.0 and lad["top_mA"] == 2.5 and lad["steps_mA"][-1] == 0.0


def test_a_tie_goes_to_the_block_with_fewer_stretches():
    tied = _surface(mu=lambda i, j: 0.0, sd=lambda i, j: 1.0)       # bound 2.0, as the prior's
    rows = [_row("L C+2-", 55.0, fitted=True, surface=tied, n=12)]
    out = BC.rank_blocks(rows, in_force=IN_FORCE, contacts_used=["L C+2-"], rates=[55.0],
                         ceilings={"Left": 4.5, "Right": 4.5}, prior_sd=1.0)
    assert [b["left_contact"] for b in out["blocks"]] == ["L C+1-2-", "L C+2-"]


def test_the_service_offers_contacts_from_both_streams_and_takes_the_prior_from_the_clinic_spread():
    import types
    import pandas as pd
    from StimOptimizer import bravo_service as BS
    s1c = types.SimpleNamespace(
        D=pd.DataFrame({"J": [0.0, 1.0, 2.0, 3.0], "feasible": [True, True, True, False]}),
        audit={"left_contacts": [{"left_contact": "L 1+2-", "n_epochs": 5},
                                 {"left_contact": "off (Left 0 mA)", "n_epochs": 2}]})
    rows = [_row("L 1+2-", 110.0, fitted=False, n=5)]
    out = BS._next_blocks_block(rows, s1c, in_force=IN_FORCE,
                                ceilings={"Left": (4.5, "PI"), "Right": (4.5, "PI")},
                                home_left_contacts=[{"left_contact": "L C+1-", "n_epochs": 19}])
    contacts = {b["left_contact"] for b in out["blocks"]}
    assert contacts == {"L 1+2-", "L C+1-", "L C+2-", "L C+1-2-"}   # clinic, home, in force, C+1-2-
    assert {b["rate_hz"] for b in out["blocks"]} == {55.0, 110.0}     # the rows' rates and the rate in force
    assert out["prior_sd"] == pytest.approx(float(np.std([0.0, 1.0, 2.0])))   # feasible J only


def test_a_tie_at_the_top_is_said_and_no_single_block_is_offered_as_the_models_pick():
    # no surfaces at all: every block has the same prior bound, so the model cannot rank them
    out = BC.rank_blocks([], in_force=IN_FORCE, contacts_used=["L C+2-", "L C+1-"],
                         rates=[55.0, 110.0], ceilings={"Left": 4.5, "Right": 4.5}, prior_sd=1.0)
    assert out["n_tied_at_top"] == 6
    assert out["next_block"] is None
    assert "cannot rank" in out["ranking_note"] and "6" in out["ranking_note"]


def test_the_tie_note_says_the_tied_blocks_are_untested_and_the_number_is_a_bound_not_a_prediction():
    # the live page said "30 blocks tie ... 3.09 NRS points" above a table whose every row was
    # WORSE than today: the 3.09 is the prior bound of the untested blocks, not an improvement
    # anyone measured (decision 386)
    out = BC.rank_blocks([], in_force=IN_FORCE, contacts_used=["L C+2-"], rates=[55.0, 110.0],
                         ceilings={"Left": 4.5, "Right": 4.5}, prior_sd=1.0)
    note = out["ranking_note"]
    assert "untested" in note and "not a prediction" in note and "measured blocks rank below" in note


def test_a_clear_winner_is_offered_with_its_ladder_and_no_tie_note():
    good = _surface(mu=lambda i, j: -2.0, sd=lambda i, j: 0.5)      # bound 3.0 > prior 2.0
    out = BC.rank_blocks([_row("L C+2-", 55.0, fitted=True, surface=good)], in_force=IN_FORCE,
                         contacts_used=["L C+2-"], rates=[55.0], ceilings={"Left": 4.5, "Right": 4.5},
                         prior_sd=1.0)
    assert out["n_tied_at_top"] == 1
    assert out["next_block"]["left_contact"] == "L C+2-"
    assert out["ranking_note"] is None


def _contact_frame(better, n=12, pw=(60.0, 160.0), rates=(55.0, 110.0), seed=0):
    rng = np.random.default_rng(seed)
    rows = []
    for k in range(n):
        aL = 0.5 + 0.5 * (k % 6)
        rows.append(dict(freq_hz=rates[k % len(rates)], amp_mA_Left=aL, amp_mA_Right=2.5,
                         pw_us_Left=pw[0], pw_us_Right=pw[1],
                         J=-better * aL / 3.0 + 0.1 * rng.standard_normal(), obs_var=0.04))
    return pd.DataFrame(rows)


def test_a_contact_tried_only_at_other_pulse_widths_gets_a_borrowed_surface():
    frames = {"L C+1-": _contact_frame(better=2.0)}
    out = BC.rank_blocks([], in_force=IN_FORCE, contacts_used=["L C+1-"], rates=[55.0],
                         ceilings={"Left": 4.5, "Right": 4.5}, prior_sd=1.0, contact_frames=frames)
    b = _block(out, "L C+1-")
    assert b["basis"] == BC.BORROWED_BASIS
    assert b["n_stretches_borrowed_fit"] == 12
    assert np.isfinite(b["optimistic_improvement"]) and b["amp_mA_left"] is not None


def test_each_block_counts_its_own_stretches_at_its_rate_not_the_contacts_total():
    """Page review 2026-10-02 (the PI: "per rate"): the ranked table printed L C+1-'s 31 in-clinic
    stretches on every rate row, 85, 125 and 145 Hz included, though in the clinic it was tested at
    55 Hz 24 times, 110 Hz 9, 165 Hz 3. A block's count is now its own stretches at its rate with
    the Left current on; the borrowed fit's total travels beside it; the ranking is unchanged."""
    frames = {"L C+1-": _contact_frame(better=2.0, n=12)}          # 6 at 55 Hz, 6 at 110 Hz
    out = BC.rank_blocks([], in_force=IN_FORCE, contacts_used=["L C+1-"], rates=[55.0, 85.0, 110.0],
                         ceilings={"Left": 4.5, "Right": 4.5}, prior_sd=1.0, contact_frames=frames)
    assert [_block(out, "L C+1-", r)["n_stretches"] for r in (55.0, 85.0, 110.0)] == [6, 0, 6]
    assert all(_block(out, "L C+1-", r)["n_stretches_borrowed_fit"] == 12 for r in (55.0, 85.0, 110.0))


def test_a_contact_with_too_few_stretches_keeps_the_prior_bound():
    frames = {"L C+1-": _contact_frame(better=2.0, n=5)}
    out = BC.rank_blocks([], in_force=IN_FORCE, contacts_used=["L C+1-"], rates=[55.0],
                         ceilings={"Left": 4.5, "Right": 4.5}, prior_sd=1.0, contact_frames=frames)
    assert _block(out, "L C+1-")["basis"] == BC.PRIOR_BASIS


def test_the_borrowed_prediction_separates_a_better_contact_from_a_worse_one():
    frames = {"L C+1-": _contact_frame(better=3.0, seed=1), "L 1+2-": _contact_frame(better=-1.0, seed=2)}
    out = BC.rank_blocks([], in_force=IN_FORCE, contacts_used=["L C+1-", "L 1+2-"], rates=[55.0],
                         ceilings={"Left": 4.5, "Right": 4.5}, prior_sd=1.0, contact_frames=frames)
    good, bad = _block(out, "L C+1-"), _block(out, "L 1+2-")
    assert good["predicted_improvement"] > bad["predicted_improvement"] + 0.5


def test_a_surface_at_the_pulse_widths_in_force_is_used_before_a_borrowed_one():
    surf = _surface(mu=lambda i, j: -0.2 * i, sd=lambda i, j: 0.1)
    frames = {"L C+2-": _contact_frame(better=2.0)}
    out = BC.rank_blocks([_row("L C+2-", 55.0, fitted=True, surface=surf)], in_force=IN_FORCE,
                         contacts_used=["L C+2-"], rates=[55.0], ceilings={"Left": 4.5, "Right": 4.5},
                         prior_sd=1.0, contact_frames=frames)
    assert _block(out, "L C+2-")["basis"] == BC.FITTED_BASIS


def test_the_service_hands_each_contact_its_own_clinic_stretches_for_borrowing():
    import types
    from StimOptimizer import bravo_service as BS
    fr = _contact_frame(better=2.0, n=12)
    fr["cathode_Left"] = "L C+1-"
    off = fr.iloc[:2].copy(); off["amp_mA_Left"] = 0.0; off["cathode_Left"] = "L C+2-"
    D = pd.concat([fr, off], ignore_index=True); D["feasible"] = True
    s1c = types.SimpleNamespace(D=D, audit={"left_contacts": [{"left_contact": "L C+1-"}]})
    out = BS._next_blocks_block([], s1c, in_force=IN_FORCE,
                                ceilings={"Left": (4.5, "PI"), "Right": (4.5, "PI")})
    b = _block(out, "L C+1-")
    assert b["basis"] == BC.BORROWED_BASIS and b["n_stretches_borrowed_fit"] == 12
    assert _block(out, "L C+1-2-")["basis"] == BC.PRIOR_BASIS


def test_a_contact_block_is_scored_only_where_the_left_side_carries_current():
    # the best cell is Left 0 mA, where the contact makes no difference: it must not be chosen
    surf = _surface(mu=lambda i, j: 0.3 * i, sd=lambda i, j: 0.1)
    out = BC.rank_blocks([_row("L C+2-", 55.0, fitted=True, surface=surf)], in_force=IN_FORCE,
                         contacts_used=["L C+2-"], rates=[55.0], ceilings={"Left": 4.5, "Right": 4.5},
                         prior_sd=1.0)
    assert _block(out, "L C+2-")["amp_mA_left"] == 1.0          # the lowest current above 0 on this grid


def test_each_contacts_clinic_exposure_rides_with_the_ranking():
    import types
    from StimOptimizer import bravo_service as BS
    s1c = types.SimpleNamespace(D=pd.DataFrame({"J": [0.0, 1.0], "feasible": [True, True]}), audit={})
    exposure = [{"left_contact": "L C+1-2-", "n_steps": 6, "n_rated": 1, "amp_min_mA": 0.5,
                 "amp_max_mA": 1.6, "n_visits": 3}]
    out = BS._next_blocks_block([], s1c, in_force=IN_FORCE,
                                ceilings={"Left": (4.5, "PI"), "Right": (4.5, "PI")}, exposure=exposure)
    assert out["exposure"]["L C+1-2-"]["amp_max_mA"] == 1.6
    assert out["exposure"]["L C+1-2-"]["n_rated"] == 1
