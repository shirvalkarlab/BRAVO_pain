"""Step B of the contact-aware Stim Optimizer (the PI's go-ahead, 2026-10-01): one fit with a
shared pain surface over (rate, Left current, Right current) plus a deviation per Left contact
whose size the data estimate (`routines.contact_pooling`). Stretches with Left at 0 mA carry no
deviation: with no current the contact makes no difference (his ruling of 2026-10-01).

Values, not shapes, on constructed records where the answer is known: when ring 2 is truly
better, the contact share is large, the no-contact-effect test rejects, and the partial-pooling
fit predicts held-out days better than the old pooled fit; when the contacts are identical, the
share is near zero and the test does not reject.
"""
import numpy as np
import pandas as pd
import pytest

from StimOptimizer.routines import contact_pooling as CPL


def _record(effect, n_per=14, seed=0):
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
    return CPL.compare(_record(effect=1.5, seed=1))


@pytest.fixture(scope="module")
def same():
    return CPL.compare(_record(effect=0.0, seed=2))


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
    d = _record(effect=1.5, seed=3)
    m = CPL.PartialPoolingGP().fit(d)
    off = d[d["left_contact"] == CPL.LEFT_OFF].iloc[[0]]
    # predicting a Left-off stretch under either contact label gives the same answer
    a = m.predict(off.assign(left_contact="L C+1-").assign(amp_mA_Left=0.0))
    b = m.predict(off.assign(left_contact="L C+2-").assign(amp_mA_Left=0.0))
    assert a[0] == pytest.approx(b[0], abs=1e-9)


def test_one_contact_only_says_so_and_fits_nothing():
    d = _record(effect=0.0)
    d = d[d["left_contact"] != "L C+2-"]
    out = CPL.compare(d)
    assert out["available"] is False
    assert "one Left contact" in out["reason"]
