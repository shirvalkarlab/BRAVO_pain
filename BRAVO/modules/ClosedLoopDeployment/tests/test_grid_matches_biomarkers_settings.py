"""The Closed-Loop "Choose a band" card reads the SAME stored grid the Biomarkers page shows.

WHY, 2026-09-11 (decision 131). The store keeps up to twelve calibrated grids per participant --
one per pain score and per combination of matching and split settings (decision 107) -- and
`adapter.band_sweep_grid_for_closed_loop` used to return the newest of them whatever it was built
under. The Biomarkers page shows the one for its own controls, so the two pages disagreed whenever
the daily precompute had written another score last. The reader now matches the newest entry
whose sidecar tag equals the tag of the request's settings, derived through the same Django-free
parsers the Biomarkers writer uses (`Biomarkers/routines/sweep_settings.py`).

These tests write real entries through the real store into a temporary directory (the
`grid_sandbox` fixture in conftest.py: clear while the override is set, decision 129). No build is ever triggered here: every case either finds its match or is one the reader must
refuse, and the build path needs Django.

Merged here 2026-10-05: test_grid_rule_in_force.py, test_daily_default_grid_kept.py,
test_tertile_key_ignores_leftover_sliders.py.
"""
import pathlib
import re
import shutil
import tempfile

import pytest

from CacheStore import provenance as prov
from CacheStore import store as st
from ClosedLoopDeployment import adapter
from Biomarkers.routines import sweep_settings
from Biomarkers.routines import sweep_settings as ss

MODULES_DIR = pathlib.Path(__file__).resolve().parents[2]
UID = "2e3c75c00d7f4f37b53a048d195f11da"


def _write(sig, r, *, request=None, tagged=True):
    tiles_key = st.product_key("raw_lsb_tiles", UID, ("tiles", 1))
    st.store("raw_lsb_tiles", UID, ("tiles", 1), {"tiles": [[0.0]]}, writer="biomarkers")
    report_key = st.product_key("redcap_reports", UID, ("reports", 1))
    st.store("redcap_reports", UID, ("reports", 1), {"pain": [1.0]},
             writer="biomarkers", trigger="fresh_fetch", provenance=[])
    chain = prov.flatten([prov.entry(tiles_key, kind="raw_lsb_tiles", writer="biomarkers"),
                          prov.entry(report_key, kind="redcap_reports", writer="biomarkers")])
    payload = {"metric_label": "label for " + str(sig),
               "band_time_sweep": {"ONE_THREE_LEFT": {
                   "band_width_hz": 5.0,
                   "best_correlation_rows": [{"band_center_hz": 12.5, "r": r}],
                   "best_auc_rows": [{"band_center_hz": 12.5, "auc": 0.5 + r}]}}}
    # the rule in force on the sidecar, as the Biomarkers writer stamps it (decision 317)
    extra = ({"sweep_settings": sweep_settings.sweep_settings_tag_from_request(request or {}),
              "rule_version": sweep_settings.GRID_RULE_VERSION}
             if tagged else None)
    assert st.store("biomarker_band_sweep", UID, sig, payload, writer="biomarkers",
                    trigger="band_time_sweep", provenance=chain, fmt="pickle", extra=extra)


def _r(got):
    return got["band_time_sweep"]["ONE_THREE_LEFT"]["best_correlation_rows"][0]["r"]


def test_the_requested_score_is_served_not_the_newest(grid_sandbox):
    """Two grids stored, the NRS one older: asking for NRS returns NRS, asking for VAS returns VAS."""
    _write(("sweep", "nrs"), 0.11, request={"SweepMetric": "nrs"})
    _write(("sweep", "vas"), 0.22, request={"SweepMetric": "vas"})        # newest
    got = adapter.band_sweep_grid_for_closed_loop(UID, {"SweepMetric": "nrs"})
    assert got["available"] is True and _r(got) == 0.11, got.get("reason")
    assert got["grid_settings"]["sweep_metric"] == "nrs"
    assert got["grid_settings"]["built_now"] is False
    got = adapter.band_sweep_grid_for_closed_loop(UID, {"SweepMetric": "vas"})
    assert _r(got) == 0.22 and got["grid_settings"]["sweep_metric"] == "vas"


def test_matching_settings_beyond_the_score(grid_sandbox):
    """Same score, different match window / direction / split: each request gets its own grid,
    and the request's values are normalised the way the writer normalised them."""
    # grid "a" at the defaults, spelled from their one home (decision 331: 15 minutes, "nearest")
    _write(("a",), 0.1, request={"SweepMetric": "nrs",
                                 "MatchToleranceMin": sweep_settings.DEFAULT_MATCH_TOLERANCE_MIN,
                                 "MatchDirection": sweep_settings.DEFAULT_MATCH_DIRECTION,
                                 "LabelStrategy": "tertile"})
    # and one at the defaults before decision 331, which the defaults must no longer find
    _write(("old",), 0.9, request={"SweepMetric": "nrs", "MatchToleranceMin": 60,
                                   "MatchDirection": "pro_first", "LabelStrategy": "tertile"})
    _write(("b",), 0.2, request={"SweepMetric": "nrs", "MatchToleranceMin": 15,
                                 "MatchDirection": "prior", "LabelStrategy": "median"})
    got = adapter.band_sweep_grid_for_closed_loop(
        UID, {"LabelMetric": "nrs", "MatchToleranceMin": "15", "MatchDirection": "PRIOR",
              "LabelStrategy": "median", "PercentileLow": "33.3333", "PercentileHigh": "66.6667"})
    assert _r(got) == 0.2, got.get("reason")
    gs = got["grid_settings"]
    assert (gs["match_tolerance_min"], gs["match_direction"], gs["label_strategy"]) == (15.0, "prior", "median")
    got = adapter.band_sweep_grid_for_closed_loop(UID, {"SweepMetric": "nrs"})   # the defaults
    assert _r(got) == 0.1


def test_a_request_with_no_settings_means_the_defaults(grid_sandbox):
    """The Closed-Loop page with nothing persisted from the Biomarkers page asks for the defaults,
    which is what the daily precompute stores."""
    _write(("defaults",), 0.3, request={})
    _write(("other",), 0.4, request={"SweepMetric": "mpq_sum"})                # newest
    got = adapter.band_sweep_grid_for_closed_loop(UID, None)
    assert _r(got) == 0.3
    assert got["grid_settings"]["sweep_metric"] == sweep_settings.DEFAULT_BIOMARKER_METRIC


def test_an_untagged_entry_from_before_the_tag_is_never_served(grid_sandbox, monkeypatch):
    """An entry written before the tag existed says nothing about its settings, so it must not be
    served as if it matched: the reader goes to the build instead. The build is stood in for here
    (it needs Django and the recordings) and made to fail, so the card says so."""
    _write(("old",), 0.5, tagged=False)
    attempted = []

    def _no_build(uid, rd):
        attempted.append((uid, rd)); raise RuntimeError("no build in this test")
    monkeypatch.setattr(adapter, "_build_grid_through_biomarkers", _no_build)
    got = adapter.band_sweep_grid_for_closed_loop(UID, {"SweepMetric": "nrs"})
    assert got["available"] is False and attempted == [(UID, {"SweepMetric": "nrs"})]
    assert got["grid_settings"]["built_now"] is True         # a build was attempted, not a stale hit


def test_a_grid_built_on_demand_is_read_back_under_its_tag(grid_sandbox, monkeypatch):
    """Nothing stored under the requested settings: the reader builds through the Biomarkers
    sweep (stood in for by a writer that stores a tagged entry the way the real one does) and
    serves that entry, saying it was built now."""
    def _build(uid, rd):
        _write(("built",), 0.9, request=rd)
        return {"band_time_sweep": {}}
    monkeypatch.setattr(adapter, "_build_grid_through_biomarkers", _build)
    got = adapter.band_sweep_grid_for_closed_loop(UID, {"SweepMetric": "back_vas"})
    assert got["available"] is True and _r(got) == 0.9
    assert got["grid_settings"]["built_now"] is True
    assert got["grid_settings"]["sweep_metric"] == "back_vas"
    # and a second read finds it stored, with no build
    monkeypatch.setattr(adapter, "_build_grid_through_biomarkers",
                        lambda uid, rd: (_ for _ in ()).throw(AssertionError("built twice")))
    got = adapter.band_sweep_grid_for_closed_loop(UID, {"SweepMetric": "back_vas"})
    assert _r(got) == 0.9 and got["grid_settings"]["built_now"] is False


def test_the_newest_matching_entry_wins_among_several_for_one_setting(grid_sandbox):
    """Two grids under the SAME settings (the Biomarkers page rebuilt for a new report): the newer
    one is served -- "the Biomarkers latest cache grid", in the PI's words."""
    _write(("t1",), 0.6, request={"SweepMetric": "nrs"})
    _write(("t2",), 0.7, request={"SweepMetric": "nrs"})
    got = adapter.band_sweep_grid_for_closed_loop(UID, {"SweepMetric": "nrs"})
    assert _r(got) == 0.7


def test_the_tag_is_one_definition_shared_by_writer_and_reader():
    """`bravo_service` binds the parsers and the tag from the same Django-free module the
    Closed-Loop reader imports -- read from the source, since importing bravo_service needs Django."""
    src = (MODULES_DIR / "Biomarkers" / "bravo_service.py").read_text()
    for name in ("_label_strategy_params = sweep_settings.label_strategy_params",
                 "_match_tolerance_param = sweep_settings.match_tolerance_param",
                 "_sweep_match_direction = sweep_settings.sweep_match_direction",
                 "sweep_settings_tag_from_request = sweep_settings.sweep_settings_tag_from_request"):
        assert name in src, name
    assert "def _label_strategy_params" not in src and "def _sweep_match_direction" not in src


# ------------------------------------------------------------------------------------------------
# Served only under the grid rule in force (from test_grid_rule_in_force.py, merged 2026-10-05)
# ------------------------------------------------------------------------------------------------
# A stored heat-map grid is served to another page only when it was written under the grid rule in
# force (decision 317, 2026-09-26).
#
# WHY. The Closed-Loop "Choose a band" card and the Stim Optimizer find a stored Biomarkers grid by
# its settings tag alone (decision 131). The grid's rule version is inside the entry's KEY, which is a
# hash, so the Biomarkers page never serves an older-rule grid -- its own request computes a new key
# -- but these readers, matching on the tag, went on serving a grid built under an older rule (for
# example the chunk-shuffling chance test decision 315 replaced) under any settings the Biomarkers
# page had not rebuilt. Decision 293(b) fixed the same fault for the stability answers.
#
# Now every grid's sidecar names the rule it was written under (`extra["rule_version"]`), and a
# reader serves a grid only when that is the rule in force; otherwise it behaves as for no stored
# grid (the Closed-Loop card builds one, decision 131; the current-adjusted reader says none is
# stored). A sidecar written before this change names no rule: its key is recomputed from what the
# sidecar records, under the rule in force, and the grid is served only if the two keys are equal.
#
# Real entries through the real store in a temporary directory (clear while the override is set,
# decision 129). The build is always stood in for; it needs Django and the recordings.

OLDER_RULE = "v23_correlation_by_recording_source"      # the grid rule before decision 315


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


def _write_ruled(sig, r, *, rule, request=None, adjusted=False):
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


def _refuse_build(monkeypatch, attempted):
    def _no_build(uid, rd):
        attempted.append((uid, dict(rd)))
        raise RuntimeError("no build in this test")
    monkeypatch.setattr(adapter, "_build_grid_through_biomarkers", _no_build)


# --- the Closed-Loop card and the Stim Optimizer's readiness table ----------------------------

def test_an_older_rule_grid_under_the_requested_settings_is_not_served(grid_sandbox, monkeypatch):
    """The only grid under the daily defaults was written under the rule before decision 315: the
    reader must not serve it, and goes to the build exactly as when nothing is stored."""
    _write_ruled(("sweep", "older"), 0.31, rule=OLDER_RULE)
    attempted = []
    _refuse_build(monkeypatch, attempted)
    got = adapter.band_sweep_grid_for_closed_loop(UID, {})
    assert got["available"] is False, "an older-rule grid was served: r = %r" % (
        got.get("band_time_sweep") and _r(got))
    assert attempted == [(UID, {})]
    assert got["grid_settings"]["built_now"] is True


def test_an_older_rule_grid_is_not_served_to_the_stim_optimizer_either(grid_sandbox, monkeypatch):
    _write_ruled(("sweep", "older"), 0.31, rule=OLDER_RULE)
    attempted = []
    _refuse_build(monkeypatch, attempted)
    got = adapter.band_sweep_grid_for_closed_loop(UID, {}, consumer="stim_optimizer")
    assert got["available"] is False
    assert attempted == [(UID, {})]


def test_the_grid_written_under_the_rule_in_force_is_served(grid_sandbox, monkeypatch):
    """An older-rule grid written LATER than the in-force one under the same settings: the in-force
    one is served, with no build."""
    _write_ruled(("sweep", "in_force"), 0.12, rule=sweep_settings.GRID_RULE_VERSION)
    _write_ruled(("sweep", "older"), 0.31, rule=OLDER_RULE)                        # newest
    monkeypatch.setattr(adapter, "_build_grid_through_biomarkers",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not build")))
    got = adapter.band_sweep_grid_for_closed_loop(UID, {})
    assert got["available"] is True and _r(got) == 0.12
    assert got["grid_settings"]["built_now"] is False


def test_a_grid_built_on_demand_under_the_rule_in_force_is_read_back(grid_sandbox, monkeypatch):
    """The older-rule grid is refused, the build writes one under the rule in force (as the real
    writer now does), and that one is served."""
    _write_ruled(("sweep", "older"), 0.31, rule=OLDER_RULE)

    def _build(uid, rd):
        _write_ruled(("sweep", "rebuilt"), 0.44, rule=sweep_settings.GRID_RULE_VERSION, request=rd)
        return {"band_time_sweep": {}}
    monkeypatch.setattr(adapter, "_build_grid_through_biomarkers", _build)
    got = adapter.band_sweep_grid_for_closed_loop(UID, {})
    assert got["available"] is True and _r(got) == 0.44
    assert got["grid_settings"]["built_now"] is True


# --- the Stim Optimizer's current-adjusted reader (read-only) ----------------------------------

def test_an_older_rule_current_adjusted_grid_is_not_served(grid_sandbox, monkeypatch):
    monkeypatch.setattr(adapter, "_build_grid_through_biomarkers",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("must never build")))
    _write_ruled(("sweep", "adj_older"), 0.2, rule=OLDER_RULE, adjusted=True)
    got = adapter.stored_current_adjusted_grid(UID, {}, consumer="stim_optimizer")
    assert got["available"] is False, "an older-rule current-adjusted grid was served"


def test_the_in_force_current_adjusted_grid_is_served(grid_sandbox, monkeypatch):
    monkeypatch.setattr(adapter, "_build_grid_through_biomarkers",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("must never build")))
    _write_ruled(("sweep", "adj_now"), 0.2, rule=sweep_settings.GRID_RULE_VERSION, adjusted=True)
    _write_ruled(("sweep", "adj_older"), 0.3, rule=OLDER_RULE, adjusted=True)      # newest
    got = adapter.stored_current_adjusted_grid(UID, {}, consumer="stim_optimizer")
    assert got["available"] is True and _r(got) == 0.2


# --- sidecars written before decision 317 name no rule ----------------------------------------

def _default_key_settings():
    """The settings dict the Biomarkers writer puts in the key for a request with no settings,
    spelled out here from its parts (`bravo_service.band_time_sweep_for_participant`), not taken
    from the function under test."""
    from Biomarkers.routines import analytics as A
    # the default window and direction since decision 331: 15 minutes (900 s), "nearest"
    return {"eligibility_radius_seconds": 900.0, "allow_window_reuse": False,
            "label_strategy": "tertile", "percentile_low": 33.3333, "percentile_high": 66.6667,
            "outlier_n_mad": float(A.OUTLIER_N_MAD), "outlier_scale": A.OUTLIER_SCALE,
            "match_direction": "nearest", "include_cross_setting_stability": False,
            "include_clinic_sheet_ratings": False, "adjust_for_stim_current": False}


def _real_signature(rule):
    tiles_key, report_key = _inputs()
    return sweep_settings.grid_signature(UID, tiles_key, report_key, "nrs",
                                         _default_key_settings(), rule_version=rule)


def test_a_sidecar_with_no_rule_is_served_when_its_key_is_the_rule_in_force(grid_sandbox, monkeypatch):
    """Every grid on disk on 2026-09-26 was written before sidecars named a rule. One whose key is
    the key the rule in force gives for what its sidecar records is served, with no build."""
    _write_ruled(_real_signature(sweep_settings.GRID_RULE_VERSION), 0.55, rule=None)
    monkeypatch.setattr(adapter, "_build_grid_through_biomarkers",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not build")))
    got = adapter.band_sweep_grid_for_closed_loop(UID, {})
    assert got["available"] is True and _r(got) == 0.55


def test_a_sidecar_with_no_rule_whose_key_is_an_older_rule_is_not_served(grid_sandbox, monkeypatch):
    _write_ruled(_real_signature(OLDER_RULE), 0.66, rule=None)
    attempted = []
    _refuse_build(monkeypatch, attempted)
    got = adapter.band_sweep_grid_for_closed_loop(UID, {})
    assert got["available"] is False and attempted == [(UID, {})]


def test_a_sidecar_with_no_rule_and_a_key_from_nothing_it_records_is_not_served(grid_sandbox, monkeypatch):
    """A key that cannot be recomputed from the sidecar (hand-built, or from settings the sidecar
    does not record) is refused: the reader can only under-report, never serve an unknown rule."""
    _write_ruled(("sweep", "no rule, no real key"), 0.77, rule=None)
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


# ------------------------------------------------------------------------------------------------
# The grid at the daily default settings stays on disk (from test_daily_default_grid_kept.py,
# merged 2026-10-05)
# ------------------------------------------------------------------------------------------------
# The heat-map grid at the daily default settings stays on disk (the PI, 2026-09-26).
#
# Decision 317 found every one of the twelve grids kept for RCS08 built under the Biomarkers page's
# own settings: the grid at the daily defaults, which the Stim Optimizer reads on every request
# (`pain_relationship_block`, with an empty request), had aged out, so each of those requests rebuilt
# it (10.4-10.7 s). Each grid written at the defaults now names a keep group in its sidecar, and the
# store keeps the newest entry of each group whatever else is written (`test_keep_newest.py`).


def test_the_stim_optimizers_grid_is_in_a_keep_group():
    """The tag the Stim Optimizer asks for (an empty request) names a group; plain and
    current-adjusted grids are separate groups, since each is read on its own."""
    tag = ss.sweep_settings_tag_from_request({})
    assert ss.default_settings_keep_group(tag) == "default_settings:nrs"
    assert ss.default_settings_keep_group(tag, adjust_for_stim_current=True) == (
        "default_settings:nrs:current_adjusted")


def test_every_pain_score_at_the_defaults_has_its_own_group():
    """The daily pass builds every score at the defaults; each keeps its own newest grid."""
    groups = {ss.default_settings_keep_group(
        ss.sweep_settings_tag_from_request({"SweepMetric": m["key"]})) for m in ss.BIOMARKER_METRICS}
    assert len(groups) == len(ss.BIOMARKER_METRICS) and None not in groups


def test_a_grid_at_any_other_setting_is_in_no_group():
    """Only the defaults are protected, or the protection would keep everything."""
    for rd in ({"MatchToleranceMin": 5}, {"IncludeClinicSheetRatings": "1"},
               {"LabelStrategy": "median"}, {"MatchDirection": "prior"}, {"AllowWindowReuse": "1"}):
        assert ss.default_settings_keep_group(ss.sweep_settings_tag_from_request(rd)) is None, rd
    assert ss.default_settings_keep_group(None) is None


def test_the_grid_writer_names_the_group():
    """The Biomarkers writer needs Django, so this reads its source: the sidecar's `extra` for the
    grid kinds must carry the group from the one helper, not a string of its own."""
    src = (MODULES_DIR / "Biomarkers" / "bravo_service.py").read_text(encoding="utf8")
    assert '"keep_group": default_settings_keep_group(' in src or \
        '"keep_group": sweep_settings.default_settings_keep_group(' in src


def test_the_daily_default_grid_is_served_after_twelve_page_grids():
    """End to end through the store and the Closed-Loop reader: a default grid, then twelve grids
    at the page's settings, and the Stim Optimizer's read still finds the default one without
    building."""
    from ClosedLoopDeployment import adapter as cl
    d = tempfile.mkdtemp(prefix="bravo_default_grid_")
    prev = cl._SHARED_CACHE_DIR_OVERRIDE
    cl._SHARED_CACHE_DIR_OVERRIDE = d
    built = []
    prev_build = cl._build_grid_through_biomarkers
    cl._build_grid_through_biomarkers = lambda uid, rd: built.append(rd) or {}
    try:
        def _put(rd, label):
            tag = ss.sweep_settings_tag_from_request(rd)
            st.store(ss.GRID_KIND, UID, (ss.GRID_KIND, label), {"band_time_sweep": {}, "which": label},
                     writer="biomarkers", provenance=[], root=d,
                     extra={"sweep_settings": tag, "rule_version": ss.GRID_RULE_VERSION,
                            "adjust_for_stim_current": False,
                            "keep_group": ss.default_settings_keep_group(tag)})
        _put({}, "daily-nrs")
        for i in range(st.KEEP_NEWEST_BY_KIND[ss.GRID_KIND]):
            _put({"MatchToleranceMin": 5 + i, "SweepMetric": "left_leg_vas",
                  "IncludeClinicSheetRatings": "1"}, f"page-{i}")
        got = cl.band_sweep_grid_for_closed_loop(UID, {}, consumer="stim_optimizer")
        assert not built, "the daily-default grid was rebuilt: it had been evicted"
        assert got.get("available") is not False
    finally:
        cl._SHARED_CACHE_DIR_OVERRIDE = prev
        cl._build_grid_through_biomarkers = prev_build
        shutil.rmtree(d, ignore_errors=True)


# ------------------------------------------------------------------------------------------------
# A tertile split is saved once (from test_tertile_key_ignores_leftover_sliders.py, merged
# 2026-10-05)
# ------------------------------------------------------------------------------------------------
# Decision 336 (the PI, 2026-09-27): a "tertile" analysis is saved once, not twice under two
# different keys, no matter where the percentile sliders were last left.
#
# Before this fix, dragging the low/high sliders and then switching the strategy dropdown back to
# "tertile" left the request carrying whatever numbers the sliders were dragged to
# (`PercentileLow`/`PercentileHigh`), even though a tertile split always uses the fixed 33.3333/66.6667
# percentiles and never reads them (`Biomarkers/routines/analytics.py`'s `_binarize_labels` and
# `_pain_split` already force this: `lo_q = 33.3333 if strategy == "tertile" else float(low_pct)`).
# `label_strategy_params` returned those leftover slider numbers unchanged, so two computationally
# identical tertile requests produced two different settings tags (`sweep_settings_tag_from_request`)
# and so two different stored entries under `KEEP_NEWEST_BY_KIND`'s per-kind cap: a wasted, duplicate
# copy on disk for the same analysis.


def test_tertile_ignores_leftover_slider_positions():
    plain = ss.label_strategy_params({"LabelStrategy": "tertile"})
    dragged = ss.label_strategy_params(
        {"LabelStrategy": "tertile", "PercentileLow": 40.0, "PercentileHigh": 61.0})
    assert plain == ("tertile", 33.3333, 66.6667)
    assert dragged == plain


def test_tertile_settings_tag_is_the_same_no_matter_the_leftover_sliders():
    base = ss.sweep_settings_tag_from_request({"LabelStrategy": "tertile", "SweepMetric": "nrs"})
    dragged = ss.sweep_settings_tag_from_request(
        {"LabelStrategy": "tertile", "SweepMetric": "nrs",
         "PercentileLow": 12.0, "PercentileHigh": 88.0})
    assert base == dragged


def test_percentile_strategy_still_reads_the_sliders():
    """The fix touches only "tertile"; a real percentile split still uses its own cuts."""
    a = ss.label_strategy_params(
        {"LabelStrategy": "percentile", "PercentileLow": 20, "PercentileHigh": 80})
    b = ss.label_strategy_params(
        {"LabelStrategy": "percentile", "PercentileLow": 10, "PercentileHigh": 90})
    assert a == ("percentile", 20.0, 80.0)
    assert b == ("percentile", 10.0, 90.0)
    assert a != b
