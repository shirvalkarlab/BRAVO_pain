"""The clinic epoch frame converts each step's instant to a California calendar day ONCE, not once
per setting and pain site (2026-10-02: on RCS08 `_rating_days` ran 2,432 times per frame, about
half of a 2.3 s build that runs twice per Stim Optimizer request on the Jetstream2 BRAVO).

Values, not shapes: every row's day lists equal the per-group conversion they replaced, including
steps with no time and a step either side of California midnight; and the conversion runs once.
"""
import numpy as np
import pandas as pd

from StimOptimizer import clinic_pain as CP


def _steps():
    rows = []
    # 06:30 UTC is the previous California day; 08:30 UTC the same day (summer, UTC-7)
    times = ["2026-07-01T06:30:00Z", "2026-07-01T08:30:00Z", "2026-07-03T20:00:00Z", None,
             "2026-08-10T12:00:00Z", "2026-08-10T23:59:00Z", "2026-08-11T07:30:00Z"]
    for i, t in enumerate(times):
        rows.append(dict(freq_hz=110.0 if i % 2 else 145.0, amp_mA_Left=1.0 + 0.5 * (i % 3),
                         amp_mA_Right=0.0, pw_us_Left=60.0, pw_us_Right=60.0,
                         contacts_raw="1a-1b-1c", t_utc=pd.Timestamp(t) if t else pd.NaT,
                         duration_s=60.0, setting="clinic" if i < 4 else "home",
                         visit_date="2026-07-01" if i < 4 else "2026-08-10",
                         side_effect_score=np.nan,
                         **{site: (float(i) if (i + k) % 3 else np.nan)
                            for k, site in enumerate(CP.ITEM_COL)}))
    rows += [dict(rows[1]), dict(rows[4])]            # repeated settings: groups with n = 2
    return pd.DataFrame(rows)


def _expected_days(steps, ep):
    """The per-group conversion the frame used to make, row by row of `ep`."""
    key = ["freq_hz", "amp_mA_Left", "amp_mA_Right", "pw_us_Left", "pw_us_Right"]
    out = []
    for _, r in ep.iterrows():
        sub = steps[np.logical_and.reduce([steps[c].round(CP._SETTING_NDIGITS) == round(r[c], CP._SETTING_NDIGITS)
                                           for c in key])]
        exp = {"rating_days": CP._rating_days(sub["t_utc"])}
        for site, col in CP.ITEM_COL.items():
            exp[f"rating_days_{col}"] = CP._rating_days(sub.loc[sub[site].notna(), "t_utc"])
        out.append(exp)
    return out


def test_every_rows_day_lists_equal_the_per_group_conversion():
    steps = _steps()
    ep = CP.epoch_frame_from_steps(steps)
    assert len(ep) == 6                     # steps 0 and 6 share a setting, as do the two copies
    for (_, r), exp in zip(ep.iterrows(), _expected_days(steps, ep)):
        for k, v in exp.items():
            assert r[k] == v, (k, r[k], v)
    assert any(len(d) == 2 for d in ep["rating_days"])           # a group across two days


def test_the_day_conversion_runs_once_per_frame(monkeypatch):
    import importlib
    calls = []
    mods = {}
    for name in ("modules.Biomarkers.routines.local_time", "Biomarkers.routines.local_time"):
        try:                                   # whichever spelling clinic_pain can import; the two
            m = importlib.import_module(name)  # can be one module object, so patch each once
        except ImportError:
            continue
        mods[id(m)] = m
    for m in mods.values():
        real = m.local_calendar_day

        def counted(x, _real=real):
            calls.append(1)
            return _real(x)

        monkeypatch.setattr(m, "local_calendar_day", counted)
    CP.epoch_frame_from_steps(_steps())
    assert len(calls) == 1
