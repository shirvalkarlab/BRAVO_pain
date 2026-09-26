"""The heat-map grid at the daily default settings stays on disk (the PI, 2026-09-26).

Decision 317 found every one of the twelve grids kept for RCS08 built under the Biomarkers page's
own settings: the grid at the daily defaults, which the Stim Optimizer reads on every request
(`pain_relationship_block`, with an empty request), had aged out, so each of those requests rebuilt
it (10.4-10.7 s). Each grid written at the defaults now names a keep group in its sidecar, and the
store keeps the newest entry of each group whatever else is written (`test_keep_newest.py`).
"""
import pathlib
import shutil
import sys
import tempfile

MODULES_DIR = pathlib.Path(__file__).resolve().parents[2]
if str(MODULES_DIR) not in sys.path:
    sys.path.insert(0, str(MODULES_DIR))

from Biomarkers.routines import sweep_settings as ss
from CacheStore import store as st

UID = "2e3c75c00d7f4f37b53a048d195f11da"


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
