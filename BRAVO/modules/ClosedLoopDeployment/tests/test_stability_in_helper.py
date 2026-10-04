"""The report's stability model runs in the worker's helper process, beside the rest of the report
(the PI, 2026-10-04, decision 427).

Pinned: the report hands the stability body to the helper before its other work and reads the
helper's answer where it used to compute it; the helper task applies the parent's store settings
(so a test sandbox or a scratch store stays one) and returns the three fields the report reads; a
helper that fails, or is switched off, leaves the report computing stability in-process as before.
"""
import inspect

from modules.ClosedLoopDeployment import adapter as AD, stability_helper as SH


def test_the_report_hands_stability_to_the_helper_before_its_other_work():
    src = inspect.getsource(AD.report_for_participant)
    sub = src.index("= _submit_stability(participant")
    run = src.index("rep = _pl.run(")
    use = src.index("_core = _stability_result(")
    assert sub < run < use


def test_the_helper_answer_is_used_and_a_failed_helper_falls_back(monkeypatch):
    class Done:
        def result(self, timeout=None):
            return {"available": True, "reason": None, "stim": {"x": 1}}

    class Broken:
        def result(self, timeout=None):
            raise RuntimeError("helper died")
    calls = []
    monkeypatch.setattr(AD, "_validate_band_core_here", lambda body: calls.append(body) or
                        {"available": True, "stim": {"x": 2}})
    assert AD._stability_result(Done(), {"b": 1})["stim"] == {"x": 1} and calls == []
    assert AD._stability_result(Broken(), {"b": 1})["stim"] == {"x": 2} and calls == [{"b": 1}]
    assert AD._stability_result(None, {"b": 2})["stim"] == {"x": 2}


def test_the_task_applies_the_parents_store_settings(monkeypatch):
    import os
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "BRAVO.settings")
    import django
    django.setup()
    from modules.CacheStore import store as ST, ledger as LG
    from modules.Biomarkers import bravo_service as BS
    seen = {}

    def fake_core(body):
        seen.update(store=ST.DIR_OVERRIDE, ledger=LG.ENABLED, bio=BS._SHARED_CACHE_DIR_OVERRIDE,
                    body=body)
        return {"available": True, "reason": None, "stim": {"ok": 1}, "pooled": "large"}
    monkeypatch.setattr(BS, "_validate_band_core", fake_core)
    old = (ST.DIR_OVERRIDE, LG.ENABLED, BS._SHARED_CACHE_DIR_OVERRIDE)
    try:
        out = SH.stability_core({"Channel": "X"}, {"store_dir": "/tmp/s", "ledger": False,
                                                    "biomarkers_dir": "/tmp/b", "env": {}})
    finally:
        ST.DIR_OVERRIDE, LG.ENABLED, BS._SHARED_CACHE_DIR_OVERRIDE = old
    assert seen == {"store": "/tmp/s", "ledger": False, "bio": "/tmp/b", "body": {"Channel": "X"}}
    assert out == {"available": True, "reason": None, "stim": {"ok": 1}}
