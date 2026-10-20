"""The matching defaults have one home, and the Closed-Loop report carries the matching settings the
Biomarkers page last ran (decision 331; the PI, 2026-09-26).

The ruling: a pain report and band power are matched within 15 minutes either side, for the
Biomarkers page and the daily defaults alike (was 5 on the PI's page and 60 by default), measured
on the tablet clock (`artifacts/analysis_2026-09-26_json_time_fields_and_matching.md`). Every place
that means "the default window" reads `Biomarkers/routines/sweep_settings.py`; the page's copy is
pinned to it by `Client/src/views/Reports/Biomarkers/matchingDefaults.test.js`.
"""
import inspect
import pathlib
import re
import sys

MODULES_DIR = pathlib.Path(__file__).resolve().parents[2]
if str(MODULES_DIR) not in sys.path:
    sys.path.insert(0, str(MODULES_DIR))

from Biomarkers.routines import sweep_settings as ss
from ClosedLoopDeployment import adapter as cla


def test_the_default_window_is_fifteen_minutes_either_side():
    assert ss.DEFAULT_MATCH_TOLERANCE_MIN == 15.0
    assert ss.match_tolerance_param({}) == 15.0
    assert ss.sweep_settings_tag_from_request({})["match_tolerance_min"] == 15.0


def test_the_default_direction_is_either_side_with_the_gap_applied():
    """"nearest": either side of the report, and the direction under which the minimum gap keeps
    two overlapping pieces of one press out of one report ("pro_first" ignores the gap)."""
    assert ss.DEFAULT_MATCH_DIRECTION == "nearest"
    assert ss.sweep_match_direction({}) == "nearest"
    assert ss.forecast_match_direction({}) == "nearest"
    # an unrecognised value still falls back as each reader always did
    assert ss.sweep_match_direction({"MatchDirection": "sideways"}) == "pro_first"
    assert ss.forecast_match_direction({"MatchDirection": "sideways"}) == "prior"


def test_the_kept_defaults_are_unchanged():
    """No measured basis for the cap, the gap or the TD length: they keep their values."""
    assert ss.per_rating_cap_params({}) == (3, 2.0)
    assert ss.per_rating_cap_params({"MaxPerRating": 99, "RefractoryMin": -4}) == (50, 0.0)
    assert ss.per_rating_cap_params({"MaxPerRating": "x"}) == (3, 2.0)
    assert ss.DEFAULT_MATCH_EXTENT_SEC == 30.0
    assert ss.DEFAULT_ALLOW_WINDOW_REUSE is False
    assert ss.DEFAULT_INCLUDE_CLINIC_SHEET_RATINGS is False
    assert ss.label_strategy_params({}) == ("tertile", 33.3333, 66.6667)


def test_the_daily_default_keep_group_follows_the_new_default():
    """Decision 318's keep group compares a grid's tag with the default: a grid at 15 minutes is
    the daily-default grid; one at the old 60 minutes is not, so it is never served as one."""
    for m in ("nrs", "left_leg_vas"):
        assert ss.default_settings_keep_group(
            ss.sweep_settings_tag_from_request({"SweepMetric": m})) == f"default_settings:{m}"
        assert ss.default_settings_keep_group(ss.sweep_settings_tag_from_request(
            {"SweepMetric": m, "MatchToleranceMin": 60})) is None


def test_the_offline_analyses_read_the_default_window():
    from ControlAnalyses import registry, runners
    assert runners._default_window_min() == 15.0
    for fn in (runners.run_current_explains, runners.run_band_detector_research,
               runners.run_band_detector_device):
        assert inspect.signature(fn).parameters["tol_min"].default is None, fn.__name__
    src = inspect.getsource(runners)
    assert "tol_s=3600.0" not in src and "matched_60min" not in src
    for key, entry in registry.ANALYSES.items():
        assert "60-minute" not in entry["what"], key
    assert "15-minute" in registry.ANALYSES["current_explains"]["what"]


def test_no_module_types_the_old_default_window():
    """No product module writes the old default window as a literal default."""
    pat = re.compile(r"(tol_min|tolerance_min)\s*=\s*60(\.0)?\b|\"pro_first\"\)\)\.lower")
    hits = []
    for p in MODULES_DIR.rglob("*.py"):
        if "tests" in p.parts or "_agent_bridge" in str(p):
            continue
        for i, line in enumerate(p.read_text(errors="ignore").splitlines(), 1):
            if pat.search(line):
                hits.append(f"{p.relative_to(MODULES_DIR)}:{i}: {line.strip()}")
    assert not hits, hits


def test_the_stability_card_takes_the_inherited_matching_settings():
    rd = {"MatchToleranceMin": 30, "MatchDirection": "pro_first", "MaxPerRating": 1,
          "RefractoryMin": 5, "IncludeClinicSheetRatings": "1", "LabelStrategy": "median",
          "AllowWindowReuse": "", "PainScore": "vas", "Candidates": [{"channel": "X"}]}
    body = cla.stability_request_body("uid", "ONE_THREE_LEFT", 24.5, 5.0, pain_score="vas",
                                      matching=rd)
    assert body["LabelMetric"] == "vas"
    for k in ("MatchToleranceMin", "MatchDirection", "MaxPerRating", "RefractoryMin",
              "IncludeClinicSheetRatings", "LabelStrategy", "AllowWindowReuse"):
        assert body[k] == rd[k], k
    assert "PainScore" not in body and "Candidates" not in body
    # nothing sent: the one-home defaults apply downstream, nothing is added here
    bare = cla.stability_request_body("uid", "ONE_THREE_LEFT", 24.5, 5.0, pain_score="nrs")
    assert set(bare) == {"ParticipantId", "Channel", "CenterHz", "BandWidthHz", "LabelMetric"}


def test_the_report_echoes_the_matching_it_was_computed_under():
    echo = cla.matching_applied({"MatchToleranceMin": 30, "IncludeClinicSheetRatings": "1",
                                 "MatchDirection": "prior"})
    assert echo["match_tolerance_min"] == 30.0
    assert echo["include_clinic_sheet_ratings"] is True
    assert echo["match_direction"] == "prior"
    assert cla.matching_applied({}) == ss.matching_applied({})
    assert cla.matching_applied({})["match_tolerance_min"] == 15.0
    src = inspect.getsource(cla.report_for_participant)
    assert 'out["matching"] = matching_applied(rd)' in src
    assert "matching=rd" in src
