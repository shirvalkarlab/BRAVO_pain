"""The Closed-Loop grid asks for its own "Same" column answer when none is stored (the PI,
2026-11-18).

Found on RCS08 the same day: every row of the column read "not tested". The NRS grid on screen
(built 23:42:12 UTC by the other-scores precompute, a minute after new recordings) had no stored
stability answer, because a precompute never starts one and the Closed-Loop page never asked. The
reader now starts the run through the Biomarkers launcher, which skips a stored answer and a run
inside its cooldown, and never from a test's own store root.
"""
import pathlib
import sys

import pytest

MODULES_DIR = pathlib.Path(__file__).resolve().parents[2]
if str(MODULES_DIR) not in sys.path:
    sys.path.insert(0, str(MODULES_DIR))

from ClosedLoopDeployment import adapter
from ClosedLoopDeployment.tests.test_track_d_grid_stability_translation import (
    UID, _write_real_band_sweep_entry, _write_stability_entry, _raw)


@pytest.fixture
def calls(monkeypatch):
    got = []

    def fake(uid, rd, payload):
        got.append((uid, dict(rd), (payload.get("sweep_key") or {}).get("signature_key"),
                    sorted(payload.get("band_time_sweep") or {})))
        return {"launched": True, "reason": None, "store_key": "k"}
    monkeypatch.setattr(adapter, "_launch_stability_through_biomarkers", fake)
    return got


def test_no_stored_answer_starts_one_run_for_the_grid_on_screen(grid_sandbox, calls, monkeypatch):
    monkeypatch.setattr(adapter, "STABILITY_LAUNCH_UNDER_OVERRIDE_ROOT", True)
    _write_real_band_sweep_entry(sweep_key="grid-A")
    got = adapter.band_sweep_grid_for_closed_loop(UID, {"SweepMetric": "nrs"})
    assert calls == [(UID, {"SweepMetric": "nrs"}, "grid-A", ["ONE_THREE_LEFT"])]
    assert got["stability_background"] == {"launched": True, "reason": None, "store_key": "k"}
    # this read still says not tested: the answer lands later
    assert got["cross_setting_stability_included"] is False


def test_a_stored_answer_for_the_grid_starts_nothing(grid_sandbox, calls, monkeypatch):
    monkeypatch.setattr(adapter, "STABILITY_LAUNCH_UNDER_OVERRIDE_ROOT", True)
    _write_real_band_sweep_entry(sweep_key="grid-A")
    _write_stability_entry("grid-A", _raw("stable", 0.72, -0.10, 0.30))
    got = adapter.band_sweep_grid_for_closed_loop(UID)
    assert got["cross_setting_stability_included"] is True
    assert calls == []
    assert "stability_background" not in got


def test_under_a_tests_own_store_root_no_run_is_started(grid_sandbox, calls):
    _write_real_band_sweep_entry(sweep_key="grid-A")
    got = adapter.band_sweep_grid_for_closed_loop(UID)
    assert calls == []
    assert got["stability_background"]["launched"] is False
    assert "own root" in got["stability_background"]["reason"]


def test_a_launch_that_raises_leaves_the_grid_served(grid_sandbox, monkeypatch):
    monkeypatch.setattr(adapter, "STABILITY_LAUNCH_UNDER_OVERRIDE_ROOT", True)

    def boom(*a, **k):
        raise RuntimeError("no manage.py")
    monkeypatch.setattr(adapter, "_launch_stability_through_biomarkers", boom)
    _write_real_band_sweep_entry(sweep_key="grid-A")
    got = adapter.band_sweep_grid_for_closed_loop(UID)
    assert got["available"] is True
    assert got["stability_background"]["launched"] is False
    assert "no manage.py" in got["stability_background"]["reason"]


def test_the_launcher_gets_the_grids_own_key_points_and_width(monkeypatch):
    """The arguments the Biomarkers page passes when it serves a grid (`band_time_sweep_for_
    participant`'s served path): the grid's key, `stability_grid_points` of its sweeps, its width."""
    try:                                     # needs Django: the container suite, not the host's
        import django
        django.setup()
        from Biomarkers import bravo_service as bio
    except Exception as exc:                 # noqa: BLE001
        pytest.skip(f"the Biomarkers service needs Django here ({exc!r})")
    seen = {}
    monkeypatch.setattr(bio, "launch_stability_grid_in_background",
                        lambda uid, rd, **kw: seen.update(uid=uid, rd=rd, **kw) or {"launched": True})
    sweeps = {"ZERO_THREE_LEFT": {"best_correlation_rows": [{"band_center_hz": 12.5}],
                                  "best_auc_rows": [{"band_center_hz": 12.5}]}}
    payload = {"sweep_key": {"signature_key": "grid-A"}, "band_time_sweep": sweeps,
               "band_width_hz": 5.0}
    adapter._launch_stability_through_biomarkers(UID, {"SweepMetric": "nrs"}, payload)
    assert seen["uid"] == UID and seen["rd"] == {"SweepMetric": "nrs"}
    assert seen["sweep_key"] == "grid-A"
    assert seen["points"] == bio.stability_grid_points(sweeps)
    assert seen["band_width_hz"] == 5.0
