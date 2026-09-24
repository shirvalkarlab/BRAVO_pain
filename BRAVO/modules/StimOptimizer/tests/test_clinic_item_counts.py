"""A clinic setting counts only the ratings that carry the score being fitted (the PI, 2026-09-24).

A clinic step can score one pain site and not another. The epoch frame counted every step at a
setting as a rating of it (`n`, and the days behind it), and the fit kept only settings with a Left
Leg score whichever site it was fitting. So:

  * a setting with three steps and two Left Leg scores counted three Left Leg ratings;
  * the back site's fit dropped every setting scored on the back alone;
  * decision 239's merged coverage counted 36 epochs with no Left Leg score at all (255).

Now each setting carries, per site, how many steps scored it and on which days, and the fit keeps
the settings that carry ITS site's score and counts only those ratings -- the Left Leg for the leg
fit, the back for the back fit, the overall NRS for an NRS fit.
"""
import numpy as np
import pandas as pd

from StimOptimizer import clinic_pain as CP
from StimOptimizer import stage1_openloop as S1


def _step(i, amp, *, left_leg=np.nan, back=np.nan, overall=np.nan, day=0):
    return dict(visit_date="v1", setting="clinic", file="f", sha256="x", t_local=None,
                t_utc=pd.Timestamp("2026-01-05", tz="UTC") + pd.Timedelta(days=day, hours=18 + i % 3),
                amp_mA_Left=float(amp), amp_mA_Right=1.0, freq_hz=55.0, pw_us_Left=60.0,
                pw_us_Right=160.0, contacts_raw="c", duration_s=60.0, side_effect_score=np.nan,
                overall=overall, head=np.nan, back=back, left_leg=left_leg, left_foot=np.nan,
                right_leg=np.nan, right_foot=np.nan, notes=None, row_index=i)


STEPS = pd.DataFrame([
    _step(0, 1.0, left_leg=5.0, day=0), _step(1, 1.0, left_leg=4.0, day=1),
    _step(2, 1.0, back=6.0, day=2),                                   # back only, a third day
    _step(3, 2.0, back=3.0, day=0), _step(4, 2.0, back=4.0, day=1),   # a setting scored on the back alone
    _step(5, 3.0, left_leg=2.0, back=2.0, day=0),
])


def test_each_setting_carries_its_rating_count_and_days_per_site():
    ep = CP.epoch_frame_from_steps(STEPS).set_index("amp_mA_Left")
    assert ep.loc[1.0, "n"] == 3, "the step count is kept"
    assert ep.loc[1.0, "n_pain_Left_Leg"] == 2 and ep.loc[1.0, "n_pain_Back"] == 1
    assert len(ep.loc[1.0, "rating_days_pain_Left_Leg"]) == 2
    assert ep.loc[2.0, "n_pain_Left_Leg"] == 0 and ep.loc[2.0, "n_pain_Back"] == 2


def _frame_the_fit_is_given(monkeypatch, **kw):
    seen = []

    def _capture(frame, **k):
        seen.append(frame.copy())
        raise RuntimeError("stopped: the frame is what this test is about")
    monkeypatch.setattr(S1, "run_stage1", _capture)
    monkeypatch.setattr(CP, "load_clinic_steps", lambda *a, **k: (STEPS, {"signature_key": "k"}, None))
    out = CP.fit_clinic_rate_strata("uid", **kw)
    return (seen[0].set_index("amp_mA_Left") if seen else None), out


def test_the_leg_fit_counts_only_the_leg_ratings(monkeypatch):
    fr, _ = _frame_the_fit_is_given(monkeypatch)
    assert sorted(fr.index) == [1.0, 3.0], "the back-only setting has no leg score to fit"
    assert fr.loc[1.0, "n"] == 2, "three steps, two of them scored the leg"
    assert len(fr.loc[1.0, "rating_days"]) == 2


def test_the_back_fit_keeps_the_back_only_setting_and_counts_the_back_ratings(monkeypatch):
    fr, _ = _frame_the_fit_is_given(monkeypatch, primary_item="back")
    assert sorted(fr.index) == [1.0, 2.0, 3.0]
    assert fr.loc[1.0, "n"] == 1 and fr.loc[2.0, "n"] == 2


def test_a_site_with_too_few_scores_is_not_available_rather_than_fitted_on_another(monkeypatch):
    fr, out = _frame_the_fit_is_given(monkeypatch, primary_item="overall")   # no NRS on any step
    assert fr is None
    assert out["available"] is False
    assert "overall" in out["reason"].lower()


def test_ruling_five_coverage_counts_only_the_leg_ratings():
    ep = CP.epoch_frame_from_steps(STEPS)
    leg = CP.epochs_for_item(ep, "left_leg")
    inf = {"Left": {"rate_hz": 55.0, "pulse_width_us": 60.0, "amplitude_mA": 1.0},
           "Right": {"rate_hz": 55.0, "pulse_width_us": 160.0, "amplitude_mA": 1.0}}
    out = CP.next_session_coverage(leg, inf)
    assert out["n_epochs"] == 2
