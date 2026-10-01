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
"""
import numpy as np
import pandas as pd
import pytest

from StimOptimizer import stage1_openloop as S1

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


@pytest.fixture(scope="module")
def two_contacts():
    return S1.run_stage1(_record(), data_horizon="test", washin_min=1.0)


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
    res = S1.run_stage1(_record(n_ring2=3, n_off=2), data_horizon="test", washin_min=1.0)
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
    res = S1.run_stage1(_record(ring2_better=3.0, seed=3), data_horizon="test", washin_min=1.0)
    s = res.frozen.setting("Left")
    assert s.detail["left_contact"] == "L C+2-"
    assert any("L C+1-" in r and "L C+2-" in r for r in s.reasons)


# ---------------------------------------------------------------------------------------------
# a record without contacts is grouped exactly as before
# ---------------------------------------------------------------------------------------------
def test_a_record_without_contacts_is_grouped_by_pulse_widths_alone():
    d = _record().drop(columns=["cathode_Left", "cathode_Right"])
    res = S1.run_stage1(d, data_horizon="test", washin_min=1.0)
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
    res = S1.run_stage1(d, data_horizon="test", washin_min=1.0, pool_pulse_widths=True)
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
