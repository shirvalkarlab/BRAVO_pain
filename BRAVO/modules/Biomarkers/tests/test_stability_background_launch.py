"""Tests for the background stability run started once the page's own calibrated grid has landed.

WHAT THESE PIN, AND WHY EACH ONE EXISTS.

The background run is the half of the stability column nobody watches. It writes to the store from
a process nobody is looking at, and every way it can go wrong is quiet: it can start a whole-machine
job on every single page load, it can key its answer to settings the page never asks for (so the
page finds nothing and starts another run, forever), or it can carry a participant's pain reports
onto a command line. None of those raises, and none of them shows up on the page. So each one has a
test here rather than a comment asking a future reader to be careful.

The first test is the one that matters most: it reads the sweep's OWN source and fails if the sweep
starts reading a setting the background run does not carry. Without it, adding a slider to the page
would silently split the two apart -- the page on one key, the background answer on another -- and
the only symptom would be a stability column that never fills in.

Run inside the container:
    docker exec -w /usr/src/BRAVO bravo_pain-bravo-server-1 python3 -W ignore \
        modules/Biomarkers/tests/test_stability_background_launch.py
"""
import inspect
import json
import os
import re
import sys
import tempfile

_BRAVO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
sys.path.insert(0, _BRAVO_ROOT)
sys.path.insert(0, os.path.join(_BRAVO_ROOT, "modules"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "BRAVO.settings")
try:
    import django  # noqa: E402
    django.setup()
except Exception:
    pass
from Biomarkers import bravo_service as bs  # noqa: E402


#: Request fields the sweep reads that are deliberately NOT carried into the background run, each
#: with the reason it is not. A field that belongs in neither this list nor
#: `STABILITY_GRID_SETTING_KEYS` is the failure the guard test below exists to catch.
NOT_CARRIED_ON_PURPOSE = {
    "ParticipantId": "passed as its own --participant argument",
    "IncludeCrossSettingStability": ("the background run must never take the slow inline path this "
                                     "flag turns on"),
    "ProcessedPRO": "a request carrying its own pain reports skips the launch entirely",
    "RedcapFieldMap": "same -- a report override a separate process cannot reproduce",
}


def _request_keys_read_by(fn):
    """Every request field a function reads, from its own source. Covers all three spellings this
    module uses: `request_data["X"]`, `request_data.get("X")`, and `_float_param(request_data,
    "X", ...)`, the last of which a naive search for `request_data` misses entirely."""
    src = inspect.getsource(fn)
    keys = set(re.findall(r"request_data(?:\[|\.get\()\s*[\"']([A-Za-z_]+)[\"']", src))
    keys |= set(re.findall(r"_float_param\(\s*request_data\s*,\s*[\"']([A-Za-z_]+)[\"']", src))
    return keys


def test_the_setting_whitelist_covers_every_request_field_the_sweep_reads():
    """THE LOAD-BEARING TEST. Every setting `band_time_sweep_for_participant` and its four setting
    helpers read must either travel to the background run or be listed above as deliberately left
    behind. A new slider that is neither makes the page and the background answer key themselves
    differently, and the only visible symptom is a column that never fills in.
    """
    read = set()
    for fn in (bs.band_time_sweep_for_participant, bs._label_strategy_params,
               bs._match_tolerance_param, bs._sweep_match_direction, bs._resolve_biomarker_metric):
        read |= _request_keys_read_by(fn)

    carried = set(bs.STABILITY_GRID_SETTING_KEYS)
    unaccounted = sorted(read - carried - set(NOT_CARRIED_ON_PURPOSE))
    assert not unaccounted, (
        f"the sweep reads {unaccounted}, which the background run neither carries nor names as "
        f"deliberately left behind -- so a page on that setting would key its grid one way and the "
        f"background answer another, and the stability column would never fill in. Either add it "
        f"to bravo_service.STABILITY_GRID_SETTING_KEYS or to NOT_CARRIED_ON_PURPOSE here.")


def test_the_whitelist_carries_nothing_the_sweep_does_not_read():
    """The other direction: a setting carried but never read is dead weight in the key, and would
    make two requests that are identical to the sweep look different to the background run."""
    read = set()
    for fn in (bs.band_time_sweep_for_participant, bs._label_strategy_params,
               bs._match_tolerance_param, bs._sweep_match_direction, bs._resolve_biomarker_metric):
        read |= _request_keys_read_by(fn)
    extra = sorted(set(bs.STABILITY_GRID_SETTING_KEYS) - read)
    assert not extra, f"the background run carries {extra}, which the sweep never reads"


def test_the_computation_takes_the_sweeps_key_and_never_derives_one_of_its_own():
    """THE TEST FOR THE DEFECT THAT ACTUALLY HAPPENED, written after it happened rather than before.

    The first version of this work had `compute_and_store_stability_grid` rebuild the sweep's key
    out of the response's echoed `settings_applied` block. That block is NOT the settings block the
    sweep keys itself on -- it carries the match tolerance and the pain score, and lacks the match
    direction and the inline-stability flag -- and it resolves the pain score without the sweep's own
    `SweepMetric` override. So the page asked for one key and the run it had just started wrote
    another (measured live on RCS08: `dc6cec1b...` asked for, `c02e9aca...` written), every page
    load started a fresh whole-machine job, none ever satisfied the page, and nothing raised.

    Every earlier test still passed through all of that, because they built a key by hand. This one
    checks the only thing that would have caught it: that the computation derives no key at all.
    """
    src = inspect.getsource(bs.compute_and_store_stability_grid)
    assert '"sweep_key"' in src, (
        "the computation no longer reads the sweep's own key off the response")
    for rederivation in ("_band_sweep_signature(", "settings_applied", "_resolve_biomarker_metric("):
        assert rederivation not in src, (
            f"the computation derives the sweep's key again through {rederivation!r} instead of "
            f"taking the one the sweep itself used -- which is exactly how the page and the "
            f"background run came to name two different keys for one grid")

    # And the sweep really puts it there, on both of its return paths.
    sweep_src = inspect.getsource(bs.band_time_sweep_for_participant)
    assert sweep_src.count("sweep_key_block(sweep_sig, sweep_prov)") == 2, (
        "the sweep no longer carries its own key on both return paths, so a grid served from the "
        "store would have no key for anything derived from it")


def test_the_key_tuple_has_exactly_one_definition():
    """Both the computation and the launcher build the stability key. One definition, or they drift
    the same way the sweep key just did."""
    for fn in (bs.compute_and_store_stability_grid, bs.launch_stability_grid_in_background):
        src = inspect.getsource(fn)
        assert "_stability_grid_sig_tuple(" in src, (
            f"{fn.__name__} no longer builds the stability key through the shared helper")
        # The tuple's own opening, not merely a mention of the rule version -- the payload written
        # by the computation legitimately carries that constant as one of its fields.
        assert "(STABILITY_GRID_KIND, STABILITY_GRID_RULE_VERSION" not in src, (
            f"{fn.__name__} builds the key tuple inline again, alongside the shared helper")


def test_the_same_sweep_key_gives_the_same_stability_key():
    """The property the whole fix rests on, stated directly rather than only through source reads."""
    a = bs._stability_grid_sig_tuple("abc123", band_width_hz=5.0, points=[("L", 12.5)])
    b = bs._stability_grid_sig_tuple("abc123", band_width_hz=5.0, points=[("L", 12.5)])
    assert a == b
    assert a != bs._stability_grid_sig_tuple("abc124", band_width_hz=5.0, points=[("L", 12.5)])
    assert a != bs._stability_grid_sig_tuple("abc123", band_width_hz=10.0, points=[("L", 12.5)])
    assert a != bs._stability_grid_sig_tuple("abc123", band_width_hz=5.0, points=[("L", 13.5)])
    # The order the grid happens to list its points in is not a difference in the grid.
    assert (bs._stability_grid_sig_tuple("abc123", band_width_hz=5.0,
                                         points=[("L", 12.5), ("R", 8.5)])
            == bs._stability_grid_sig_tuple("abc123", band_width_hz=5.0,
                                            points=[("R", 8.5), ("L", 12.5)]))


def test_the_key_block_carries_the_sweeps_own_signature_key():
    from CacheStore import store as cs
    sig = ("band_time_sweep_response", "v6", "tiles/x/y", "reports/x/y")
    block = bs.sweep_key_block(sig, ["tiles/x/y", "reports/x/y"])
    assert block["signature_key"] == cs.signature_key(sig)
    assert block["provenance"] == ["tiles/x/y", "reports/x/y"]
    assert bs.sweep_key_block(None, None) is None


def test_the_points_of_a_grid_are_read_the_same_way_everywhere():
    sweeps = {"ONE_THREE_LEFT": {"center_freqs_hz": [8.5, 12.5]},
              "ZERO_TWO_LEFT": {"center_freqs_hz": [8.5]},
              "EMPTY": {},
              "NONE_AT_ALL": None}
    assert sorted(bs.stability_grid_points(sweeps)) == [
        ("ONE_THREE_LEFT", 8.5), ("ONE_THREE_LEFT", 12.5), ("ZERO_TWO_LEFT", 8.5)]
    assert bs.stability_grid_points(None) == []
    assert bs.stability_grid_points({}) == []
    # And the computation reads them through the same function rather than its own copy.
    assert "stability_grid_points(" in inspect.getsource(bs.compute_and_store_stability_grid)


def test_the_command_line_carries_the_settings_and_nothing_else():
    """A command line is visible in the process list, so what goes on it is a privacy question as
    well as a correctness one. The whitelist is checked here against a request deliberately carrying
    a participant's own pain rows."""
    request = {"ParticipantId": "abc", "MatchDirection": "prior", "PercentileLow": 30,
               "OutlierNMad": 4.0, "AllowWindowReuse": "true",
               "IncludeCrossSettingStability": "true",
               "ProcessedPRO": [{"nrs": 7, "date_time_s1_daily": "2026-01-01 10:00"}],
               "RedcapFieldMap": {"nrs": "pain_now"}}
    argv = bs._stability_grid_command_argv("abc", request)
    assert argv is not None, "manage.py was not found from bravo_service.py's own location"
    assert argv[2:5] == ["compute_stability_grid", "--participant", "abc"]

    blob = argv[argv.index("--request-json") + 1]
    carried = json.loads(blob)
    assert carried == {"MatchDirection": "prior", "PercentileLow": 30, "OutlierNMad": 4.0,
                       "AllowWindowReuse": "true"}, carried
    # Stated separately from the equality above, so a failure says WHICH rule was broken.
    assert "IncludeCrossSettingStability" not in carried, (
        "the background run was told to compute the column inline, which is the slow path it "
        "exists to avoid")
    for forbidden in ("ProcessedPRO", "RedcapFieldMap", "nrs", "pain_now", "date_time"):
        assert forbidden not in blob, f"{forbidden!r} reached the command line"


def test_a_request_carrying_its_own_pain_reports_starts_nothing():
    """Those rows exist in this request body and nowhere else, so a separate process would fetch a
    different report set, key its answer differently, and be recomputed on every load forever."""
    points = [("ONE_THREE_LEFT", 12.5)]
    for override in ({"ProcessedPRO": [{"nrs": 7}]}, {"RedcapFieldMap": {"nrs": "pain_now"}}):
        got = bs.launch_stability_grid_in_background(
            "abc", dict(override, ParticipantId="abc"), sweep_key="sweepkeyone", points=points,
            band_width_hz=5.0)
        assert got["launched"] is False
        assert "pain reports" in got["reason"], got["reason"]


def test_the_switch_stops_every_launch():
    was = bs.STABILITY_GRID_BACKGROUND
    try:
        bs.STABILITY_GRID_BACKGROUND = False
        got = bs.launch_stability_grid_in_background(
            "abc", {}, sweep_key="sweepkeyone", points=[("ONE_THREE_LEFT", 12.5)], band_width_hz=5.0)
        assert got["launched"] is False
        assert "switched off" in got["reason"]
    finally:
        bs.STABILITY_GRID_BACKGROUND = was


def test_a_grid_with_no_key_or_no_points_starts_nothing():
    for key, points in ((None, [("A", 1.0)]), ("sweepkeyone", []), (None, []), ("", [("A", 1.0)])):
        got = bs.launch_stability_grid_in_background("abc", {}, sweep_key=key, points=points,
                                                     band_width_hz=5.0)
        assert got["launched"] is False
        assert "no key or no points" in got["reason"]


def test_the_cooldown_stops_a_second_launch_for_the_same_key():
    """FOUR GUNICORN WORKERS MEAN FOUR INDEPENDENT MEMORIES, so this guard has to be a file rather
    than a set in one process. Proven by launching twice through the real marker file, with only the
    spawn itself replaced -- so what is under test is the guard, not a stand-in for it."""
    started = []
    real_spawn = bs._spawn_detached
    was_override = bs._SHARED_CACHE_DIR_OVERRIDE
    tmp = tempfile.mkdtemp(prefix="stability_launch_")
    try:
        bs._SHARED_CACHE_DIR_OVERRIDE = tmp
        bs.STABILITY_GRID_LAUNCH_UNDER_OVERRIDE_ROOT = True
        bs._spawn_detached = lambda argv, log_path: started.append(argv)

        first = bs.launch_stability_grid_in_background(
            "abc", {"MatchDirection": "prior"}, sweep_key="sweepkeyone",
            points=[("ONE_THREE_LEFT", 12.5)], band_width_hz=5.0)
        assert first["launched"] is True, first["reason"]
        assert len(started) == 1
        assert first["store_key"] and first["store_key"].startswith(bs.STABILITY_GRID_KIND)

        second = bs.launch_stability_grid_in_background(
            "abc", {"MatchDirection": "prior"}, sweep_key="sweepkeyone",
            points=[("ONE_THREE_LEFT", 12.5)], band_width_hz=5.0)
        assert second["launched"] is False
        assert "cooldown" in second["reason"], second["reason"]
        assert len(started) == 1, "the cooldown let a second whole-machine job start"

        # A DIFFERENT KEY GETS ITS OWN COOLDOWN. Otherwise moving a slider would be locked out by
        # the previous setting's marker and its answer would never be computed at all.
        third = bs.launch_stability_grid_in_background(
            "abc", {"MatchDirection": "nearest"}, sweep_key="sweepkeytwo",
            points=[("ONE_THREE_LEFT", 12.5)], band_width_hz=5.0)
        assert third["launched"] is True, third["reason"]
        assert len(started) == 2
        assert third["store_key"] != first["store_key"]
    finally:
        bs._spawn_detached = real_spawn
        bs._SHARED_CACHE_DIR_OVERRIDE = was_override
        bs.STABILITY_GRID_LAUNCH_UNDER_OVERRIDE_ROOT = False


def test_a_launch_that_cannot_start_is_reported_rather_than_raised():
    """This runs at the very end of a page request. A page that could not start background work must
    still return the grid it already has."""
    real_spawn = bs._spawn_detached
    was_override = bs._SHARED_CACHE_DIR_OVERRIDE
    tmp = tempfile.mkdtemp(prefix="stability_launch_fail_")
    try:
        bs._SHARED_CACHE_DIR_OVERRIDE = tmp
        bs.STABILITY_GRID_LAUNCH_UNDER_OVERRIDE_ROOT = True

        def _boom(argv, log_path):
            raise OSError("no processes could be started")

        bs._spawn_detached = _boom
        got = bs.launch_stability_grid_in_background(
            "abc", {}, sweep_key="sweepkey99", points=[("ONE_THREE_LEFT", 12.5)],
            band_width_hz=5.0)
        assert got["launched"] is False
        assert "could not be started" in got["reason"]
        assert "no processes could be started" in got["reason"], (
            "the real reason was swallowed, so nobody could tell why nothing ran")
    finally:
        bs._spawn_detached = real_spawn
        bs._SHARED_CACHE_DIR_OVERRIDE = was_override
        bs.STABILITY_GRID_LAUNCH_UNDER_OVERRIDE_ROOT = False


def test_both_of_the_sweeps_return_paths_start_the_background_run():
    """A grid served from the store counts exactly as much as a freshly built one -- the reader is
    looking at a grid either way. Checked by reading the function's own source, so this needs no
    participant and no database."""
    src = inspect.getsource(bs.band_time_sweep_for_participant)
    assert src.count("launch_stability_grid_in_background(") == 2, (
        "the sweep no longer starts the background run from both of its return paths -- a grid "
        "served from the store would never get its stability column")
    assert src.count('out["stability_background"]') == 1
    assert 'stored["stability_background"]' in src


def test_by_default_nothing_is_started_while_the_store_is_pointed_at_a_test_root():
    """THE REGRESSION TEST FOR A REAL ONE. Before this guard existed the container suite reached the
    real spawn: `test_band_sweep_store`'s bench points the store at a temporary directory and calls
    the sweep for a made-up participant "u", and each such call started an actual
    `manage.py compute_stability_grid --participant u` process. A unit suite must not start
    whole-machine jobs, and an answer written into a temporary directory is read by nothing.

    The answer must also be the SAME on every call, because a test comparing a served response
    against a freshly built one compares this field too.
    """
    was_override = bs._SHARED_CACHE_DIR_OVERRIDE
    started = []
    real_spawn = bs._spawn_detached
    tmp = tempfile.mkdtemp(prefix="stability_launch_default_")
    try:
        bs._SHARED_CACHE_DIR_OVERRIDE = tmp
        assert bs.STABILITY_GRID_LAUNCH_UNDER_OVERRIDE_ROOT is False, (
            "the module ships with the launcher enabled under a test store root")
        bs._spawn_detached = lambda argv, log_path: started.append(argv)
        first = bs.launch_stability_grid_in_background(
            "abc", {}, sweep_key="sweepkeyone", points=[("L", 12.5)], band_width_hz=5.0)
        second = bs.launch_stability_grid_in_background(
            "abc", {}, sweep_key="sweepkeyone", points=[("L", 12.5)], band_width_hz=5.0)
        assert started == [], "a background job was started from a test store root"
        assert first["launched"] is False and "production" in first["reason"]
        assert first == second, ("the refusal must read the same on every call, or a served "
                                 "response stops matching a freshly built one")
        assert not os.listdir(tmp), "a marker was written under the test root"
    finally:
        bs._spawn_detached = real_spawn
        bs._SHARED_CACHE_DIR_OVERRIDE = was_override


if __name__ == "__main__":
    _fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    _passed = _failed = 0
    for _fn in _fns:
        try:
            _fn()
            _passed += 1
            print(f"PASS {_fn.__name__}")
        except Exception as exc:                                  # noqa: BLE001
            _failed += 1
            print(f"FAIL {_fn.__name__}: {exc!r}")
    print(f"\n{_passed} passed, {_failed} failed")
    sys.exit(1 if _failed else 0)
