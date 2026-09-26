"""A stored heat-map grid is served to another page only when it was written under the grid rule in
force (decision 317, 2026-09-26).

WHY. The Closed-Loop "Choose a band" card and the Stim Optimizer find a stored Biomarkers grid by
its settings tag alone (decision 131). The grid's rule version is inside the entry's KEY, which is a
hash, so the Biomarkers page never serves an older-rule grid -- its own request computes a new key
-- but these readers, matching on the tag, went on serving a grid built under an older rule (for
example the chunk-shuffling chance test decision 315 replaced) under any settings the Biomarkers
page had not rebuilt. Decision 293(b) fixed the same fault for the stability answers.

Now every grid's sidecar names the rule it was written under (`extra["rule_version"]`), and a
reader serves a grid only when that is the rule in force; otherwise it behaves as for no stored
grid (the Closed-Loop card builds one, decision 131; the current-adjusted reader says none is
stored). A sidecar written before this change names no rule: its key is recomputed from what the
sidecar records, under the rule in force, and the grid is served only if the two keys are equal.

Real entries through the real store in a temporary directory (clear while the override is set,
decision 129). The build is always stood in for; it needs Django and the recordings.
"""
import pathlib
import re
import shutil
import sys
import tempfile

import pytest

MODULES_DIR = pathlib.Path(__file__).resolve().parents[2]
if str(MODULES_DIR) not in sys.path:
    sys.path.insert(0, str(MODULES_DIR))

from CacheStore import provenance as prov                                   # noqa: E402
from CacheStore import store as st                                          # noqa: E402
from ClosedLoopDeployment import adapter                                     # noqa: E402
from Biomarkers.routines import sweep_settings                               # noqa: E402

UID = "2e3c75c00d7f4f37b53a048d195f11da"
OLDER_RULE = "v23_correlation_by_recording_source"      # the grid rule before decision 315


@pytest.fixture
def sandbox():
    d = tempfile.mkdtemp(prefix="bravo_grid_rule_")
    prev_store, prev_adapter = st.DIR_OVERRIDE, adapter._SHARED_CACHE_DIR_OVERRIDE
    from CacheStore import ledger
    prev_ledger = ledger.ENABLED
    ledger.ENABLED = False
    st.DIR_OVERRIDE = d
    adapter._SHARED_CACHE_DIR_OVERRIDE = d
    try:
        yield d
    finally:
        st.clear()                       # while the override still points at the sandbox
        st.DIR_OVERRIDE = prev_store
        adapter._SHARED_CACHE_DIR_OVERRIDE = prev_adapter
        ledger.ENABLED = prev_ledger
        shutil.rmtree(d, ignore_errors=True)


def _inputs():
    """The two raw inputs every grid names in its chain, written for real; their keys."""
    st.store("raw_lsb_tiles", UID, ("tiles", 1), {"tiles": [[0.0]]}, writer="biomarkers")
    st.store("redcap_reports", UID, ("reports", 1), {"pain": [1.0]},
             writer="biomarkers", trigger="fresh_fetch", provenance=[])
    return (st.product_key("raw_lsb_tiles", UID, ("tiles", 1)),
            st.product_key("redcap_reports", UID, ("reports", 1)))


def _payload(r):
    return {"metric_label": "NRS (0–10)",
            "band_time_sweep": {"ONE_THREE_LEFT": {
                "band_width_hz": 5.0,
                "best_correlation_rows": [{"band_center_hz": 24.5, "r": r,
                                           "pearson_r_adjusted": r / 2}],
                "best_auc_rows": [{"band_center_hz": 24.5, "auc": 0.5 + r}]}}}


def _write(sig, r, *, rule, request=None, adjusted=False):
    """One grid written the way the Biomarkers writer writes it; ``rule=None`` leaves the rule out
    of the sidecar, as every sidecar written before decision 317 does."""
    tiles_key, report_key = _inputs()
    chain = prov.flatten([prov.entry(tiles_key, kind="raw_lsb_tiles", writer="biomarkers"),
                          prov.entry(report_key, kind="redcap_reports", writer="biomarkers")])
    extra = {"sweep_settings": sweep_settings.sweep_settings_tag_from_request(request or {}),
             "metric_label": "NRS (0–10)", "adjust_for_stim_current": bool(adjusted)}
    if rule is not None:
        extra["rule_version"] = rule
    assert st.store("biomarker_band_sweep", UID, sig, _payload(r), writer="biomarkers",
                    trigger="band_time_sweep", provenance=chain, fmt="pickle", extra=extra)


def _r(got):
    return got["band_time_sweep"]["ONE_THREE_LEFT"]["best_correlation_rows"][0]["r"]


def _refuse_build(monkeypatch, attempted):
    def _no_build(uid, rd):
        attempted.append((uid, dict(rd)))
        raise RuntimeError("no build in this test")
    monkeypatch.setattr(adapter, "_build_grid_through_biomarkers", _no_build)


# --- the Closed-Loop card and the Stim Optimizer's readiness table ----------------------------

def test_an_older_rule_grid_under_the_requested_settings_is_not_served(sandbox, monkeypatch):
    """The only grid under the daily defaults was written under the rule before decision 315: the
    reader must not serve it, and goes to the build exactly as when nothing is stored."""
    _write(("sweep", "older"), 0.31, rule=OLDER_RULE)
    attempted = []
    _refuse_build(monkeypatch, attempted)
    got = adapter.band_sweep_grid_for_closed_loop(UID, {})
    assert got["available"] is False, "an older-rule grid was served: r = %r" % (
        got.get("band_time_sweep") and _r(got))
    assert attempted == [(UID, {})]
    assert got["grid_settings"]["built_now"] is True


def test_an_older_rule_grid_is_not_served_to_the_stim_optimizer_either(sandbox, monkeypatch):
    _write(("sweep", "older"), 0.31, rule=OLDER_RULE)
    attempted = []
    _refuse_build(monkeypatch, attempted)
    got = adapter.band_sweep_grid_for_closed_loop(UID, {}, consumer="stim_optimizer")
    assert got["available"] is False
    assert attempted == [(UID, {})]


def test_the_grid_written_under_the_rule_in_force_is_served(sandbox, monkeypatch):
    """An older-rule grid written LATER than the in-force one under the same settings: the in-force
    one is served, with no build."""
    _write(("sweep", "in_force"), 0.12, rule=sweep_settings.GRID_RULE_VERSION)
    _write(("sweep", "older"), 0.31, rule=OLDER_RULE)                        # newest
    monkeypatch.setattr(adapter, "_build_grid_through_biomarkers",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not build")))
    got = adapter.band_sweep_grid_for_closed_loop(UID, {})
    assert got["available"] is True and _r(got) == 0.12
    assert got["grid_settings"]["built_now"] is False


def test_a_grid_built_on_demand_under_the_rule_in_force_is_read_back(sandbox, monkeypatch):
    """The older-rule grid is refused, the build writes one under the rule in force (as the real
    writer now does), and that one is served."""
    _write(("sweep", "older"), 0.31, rule=OLDER_RULE)

    def _build(uid, rd):
        _write(("sweep", "rebuilt"), 0.44, rule=sweep_settings.GRID_RULE_VERSION, request=rd)
        return {"band_time_sweep": {}}
    monkeypatch.setattr(adapter, "_build_grid_through_biomarkers", _build)
    got = adapter.band_sweep_grid_for_closed_loop(UID, {})
    assert got["available"] is True and _r(got) == 0.44
    assert got["grid_settings"]["built_now"] is True


# --- the Stim Optimizer's current-adjusted reader (read-only) ----------------------------------

def test_an_older_rule_current_adjusted_grid_is_not_served(sandbox, monkeypatch):
    monkeypatch.setattr(adapter, "_build_grid_through_biomarkers",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("must never build")))
    _write(("sweep", "adj_older"), 0.2, rule=OLDER_RULE, adjusted=True)
    got = adapter.stored_current_adjusted_grid(UID, {}, consumer="stim_optimizer")
    assert got["available"] is False, "an older-rule current-adjusted grid was served"


def test_the_in_force_current_adjusted_grid_is_served(sandbox, monkeypatch):
    monkeypatch.setattr(adapter, "_build_grid_through_biomarkers",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("must never build")))
    _write(("sweep", "adj_now"), 0.2, rule=sweep_settings.GRID_RULE_VERSION, adjusted=True)
    _write(("sweep", "adj_older"), 0.3, rule=OLDER_RULE, adjusted=True)      # newest
    got = adapter.stored_current_adjusted_grid(UID, {}, consumer="stim_optimizer")
    assert got["available"] is True and _r(got) == 0.2


# --- sidecars written before decision 317 name no rule ----------------------------------------

def _default_key_settings():
    """The settings dict the Biomarkers writer puts in the key for a request with no settings,
    spelled out here from its parts (`bravo_service.band_time_sweep_for_participant`), not taken
    from the function under test."""
    from Biomarkers.routines import analytics as A
    return {"eligibility_radius_seconds": 3600.0, "allow_window_reuse": False,
            "label_strategy": "tertile", "percentile_low": 33.3333, "percentile_high": 66.6667,
            "outlier_n_mad": float(A.OUTLIER_N_MAD), "outlier_scale": A.OUTLIER_SCALE,
            "match_direction": "pro_first", "include_cross_setting_stability": False,
            "include_clinic_sheet_ratings": False, "adjust_for_stim_current": False}


def _real_signature(rule):
    tiles_key, report_key = _inputs()
    return sweep_settings.grid_signature(UID, tiles_key, report_key, "nrs",
                                         _default_key_settings(), rule_version=rule)


def test_a_sidecar_with_no_rule_is_served_when_its_key_is_the_rule_in_force(sandbox, monkeypatch):
    """Every grid on disk on 2026-09-26 was written before sidecars named a rule. One whose key is
    the key the rule in force gives for what its sidecar records is served, with no build."""
    _write(_real_signature(sweep_settings.GRID_RULE_VERSION), 0.55, rule=None)
    monkeypatch.setattr(adapter, "_build_grid_through_biomarkers",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not build")))
    got = adapter.band_sweep_grid_for_closed_loop(UID, {})
    assert got["available"] is True and _r(got) == 0.55


def test_a_sidecar_with_no_rule_whose_key_is_an_older_rule_is_not_served(sandbox, monkeypatch):
    _write(_real_signature(OLDER_RULE), 0.66, rule=None)
    attempted = []
    _refuse_build(monkeypatch, attempted)
    got = adapter.band_sweep_grid_for_closed_loop(UID, {})
    assert got["available"] is False and attempted == [(UID, {})]


def test_a_sidecar_with_no_rule_and_a_key_from_nothing_it_records_is_not_served(sandbox, monkeypatch):
    """A key that cannot be recomputed from the sidecar (hand-built, or from settings the sidecar
    does not record) is refused: the reader can only under-report, never serve an unknown rule."""
    _write(("sweep", "no rule, no real key"), 0.77, rule=None)
    attempted = []
    _refuse_build(monkeypatch, attempted)
    got = adapter.band_sweep_grid_for_closed_loop(UID, {})
    assert got["available"] is False and attempted == [(UID, {})]


# --- one home -----------------------------------------------------------------------------------

def test_the_grid_rule_and_kind_have_one_home():
    """The rule string and the kind name are written once, in `routines/sweep_settings.py`; the
    Biomarkers writer and the Closed-Loop reader both bind them from there. Read from the sources,
    since importing `bravo_service` needs Django."""
    assert re.fullmatch(r"v\d+_\w+", sweep_settings.GRID_RULE_VERSION)
    assert sweep_settings.GRID_KIND == "biomarker_band_sweep"
    bs = (MODULES_DIR / "Biomarkers" / "bravo_service.py").read_text()
    assert re.search(r"^_BAND_SWEEP_RULE_VERSION\s*=\s*sweep_settings\.GRID_RULE_VERSION\b",
                     bs, re.MULTILINE), "bravo_service must bind the grid rule from sweep_settings"
    assert re.search(r"^_BAND_SWEEP_RESPONSE_KIND\s*=\s*sweep_settings\.GRID_KIND\b",
                     bs, re.MULTILINE), "bravo_service must bind the grid kind from sweep_settings"
    assert not re.search(r'^_BAND_SWEEP_RULE_VERSION\s*=\s*"', bs, re.MULTILINE)
    ad = (MODULES_DIR / "ClosedLoopDeployment" / "adapter.py").read_text()
    code = "\n".join(l for l in ad.splitlines() if not l.lstrip().startswith("#"))
    assert '"biomarker_band_sweep"' not in code, "the Closed-Loop reader spells the grid kind itself"
    assert not re.search(r'"v\d+_exact_rotation_null"|GRID_RULE_VERSION\s*=\s*"', code)
    ss = (MODULES_DIR / "Biomarkers" / "routines" / "sweep_settings.py").read_text()
    assert len(re.findall(r'^GRID_RULE_VERSION\s*=\s*"', ss, re.MULTILINE)) == 1
