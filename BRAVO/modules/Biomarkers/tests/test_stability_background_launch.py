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
    docker exec -w /usr/src/BRAVO bravo_pain-bravo-server-1 python3 -W ignore         modules/Biomarkers/tests/test_stability_background_launch.py

Merged here 2026-10-05: test_stability_answer_uses_grid_score.py, test_sweep_rows_carry_stability_answer.py, test_stability_intervals_clustered_on_report.py.
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


def test_the_sheet_ratings_switch_is_in_the_whitelist_and_in_the_closed_loop_keys():
    """Decision 186: the switch is in the sweep's key, so the background stability run and the
    Closed-Loop page's grid request must carry it or they key themselves to a grid the page never
    asks for -- the exact drift the whitelist test below exists to catch."""
    assert "IncludeClinicSheetRatings" in bs.STABILITY_GRID_SETTING_KEYS
    js_path = os.path.join(_BRAVO_ROOT, "..", "Client", "src", "views", "Reports", "ClosedLoopSim",
                           "useBandSweepGrid.js")
    if os.path.isfile(js_path):                  # the container mounts BRAVO/ alone; the host sees Client/
        assert '"IncludeClinicSheetRatings"' in open(js_path).read()


def test_the_setting_whitelist_covers_every_request_field_the_sweep_reads():
    """THE LOAD-BEARING TEST. Every setting `band_time_sweep_for_participant` and its four setting
    helpers read must either travel to the background run or be listed above as deliberately left
    behind. A new slider that is neither makes the page and the background answer key themselves
    differently, and the only visible symptom is a column that never fills in.
    """
    read = set()
    for fn in (bs.band_time_sweep_for_participant, bs._label_strategy_params,
               bs._match_tolerance_param, bs._sweep_match_direction, bs._resolve_biomarker_metric,
               bs._include_clinic_sheet_ratings_param):
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
               bs._match_tolerance_param, bs._sweep_match_direction, bs._resolve_biomarker_metric,
               bs._include_clinic_sheet_ratings_param):
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


def test_a_run_that_stopped_early_keeps_the_previous_answer_instead_of_replacing_it():
    """The store keeps ONE current entry per participant per kind, replaced whole. So writing a
    stopped-early grid over a good one would not narrow the stability column -- it would destroy the
    previous answer, and rows that had a real answer an hour ago would read "not yet computed".

    The batch policy carries on past a point that raises but stops after three in a row, so this is
    a state the code can genuinely reach, not a hypothetical.
    """
    from CacheStore import store as cs
    was_override = bs._SHARED_CACHE_DIR_OVERRIDE
    tmp = tempfile.mkdtemp(prefix="stability_partial_")
    real_sweep = bs.band_time_sweep_for_participant
    real_grid = bs.stability_grid_for_participant
    try:
        bs._SHARED_CACHE_DIR_OVERRIDE = tmp
        points = [("L", 8.5), ("L", 9.5), ("L", 10.5), ("L", 11.5)]
        bs.band_time_sweep_for_participant = lambda req: {
            "band_time_sweep": {"L": {"center_freqs_hz": [f for _, f in points]}},
            "band_width_hz": 5.0, "label_metric": "nrs",
            "sweep_key": {"signature_key": "sweepkeyone", "provenance": []}}

        # A complete previous answer, written the way the real computation writes one.
        good = {"kind": bs.STABILITY_GRID_KIND, "rule_version": bs.STABILITY_GRID_RULE_VERSION,
                "participant_uid": "abc", "band_width_hz": 5.0, "label_metric": "nrs",
                "n_points_requested": 4,
                "points": {f"L|{f:g}": {"available": True, "lrt_p": 0.1} for _, f in points}}
        sig = bs._stability_grid_sig_tuple("sweepkeyone", band_width_hz=5.0, points=points)
        assert cs.store(bs.STABILITY_GRID_KIND, "abc", sig, good, writer="biomarkers",
                        trigger="test", provenance=[], root=tmp)

        # Now a run that stopped after two of the four points.
        bs.stability_grid_for_participant = lambda uid, pts, **kw: {
            ("L", 8.5): {"available": True, "lrt_p": 0.2},
            ("L", 9.5): {"available": False, "reason": "raised"}}
        out = bs.compute_and_store_stability_grid("abc", force=True)

        assert out["stopped_early"] is True and out["attempted"] == 2
        assert out["stored"] is False, "a partial grid replaced a complete stored answer"
        assert "previous stored answer" in out["reason"], out["reason"]

        # The complete answer is still there, untouched.
        back, _ = cs.load_newest(bs.STABILITY_GRID_KIND, "abc", consumer="biomarkers", root=tmp)
        assert len(back["points"]) == 4
        assert back["points"]["L|8.5"]["lrt_p"] == 0.1, "the partial run's value overwrote it"

        # A COMPLETE run still replaces it -- the guard must not freeze the answer forever.
        bs.stability_grid_for_participant = lambda uid, pts, **kw: {
            p: {"available": True, "lrt_p": 0.3} for p in points}
        out2 = bs.compute_and_store_stability_grid("abc", force=True)
        assert out2["stopped_early"] is False and out2["stored"] is True, out2["reason"]
        back2, _ = cs.load_newest(bs.STABILITY_GRID_KIND, "abc", consumer="biomarkers", root=tmp)
        assert back2["points"]["L|8.5"]["lrt_p"] == 0.3
    finally:
        bs.band_time_sweep_for_participant = real_sweep
        bs.stability_grid_for_participant = real_grid
        bs._SHARED_CACHE_DIR_OVERRIDE = was_override


def test_a_stopped_early_run_is_kept_from_replacing_its_OWN_grids_answer_not_another_grids():
    """Since 2026-09-23 the store keeps one stability answer per grid (decision 248). The guard
    above asked for the NEWEST answer of any grid, so once any other grid had one, every stopped-
    early run for a grid with none of its own was thrown away and its rows read "not tested" --
    where, with nothing complete of its own to protect, it had always been written. The guard now
    asks for this grid's own answer."""
    from CacheStore import store as cs
    was_override = bs._SHARED_CACHE_DIR_OVERRIDE
    tmp = tempfile.mkdtemp(prefix="stability_partial_other_")
    real_sweep = bs.band_time_sweep_for_participant
    real_grid = bs.stability_grid_for_participant
    try:
        bs._SHARED_CACHE_DIR_OVERRIDE = tmp
        points = [("L", 8.5), ("L", 9.5), ("L", 10.5), ("L", 11.5)]
        # ANOTHER grid's complete answer is stored
        other = bs._stability_grid_sig_tuple("sweepkeyother", band_width_hz=5.0, points=points)
        assert cs.store(bs.STABILITY_GRID_KIND, "abc", other,
                        {"points": {f"L|{f:g}": {"available": True, "lrt_p": 0.1} for _, f in points}},
                        writer="biomarkers", trigger="test", provenance=[], root=tmp)
        bs.band_time_sweep_for_participant = lambda req: {
            "band_time_sweep": {"L": {"center_freqs_hz": [f for _, f in points]}},
            "band_width_hz": 5.0, "label_metric": "vas",
            "sweep_key": {"signature_key": "sweepkeymine", "provenance": []}}
        bs.stability_grid_for_participant = lambda uid, pts, **kw: {
            ("L", 8.5): {"available": True, "lrt_p": 0.2},
            ("L", 9.5): {"available": False, "reason": "raised"}}
        out = bs.compute_and_store_stability_grid("abc", force=True)
        assert out["stopped_early"] is True
        assert out["stored"] is True, f"another grid's answer blocked this grid's partial one: {out['reason']}"
        mine = bs._stability_grid_sig_tuple("sweepkeymine", band_width_hz=5.0, points=points)
        back = cs.load(bs.STABILITY_GRID_KIND, "abc", mine, consumer="biomarkers", root=tmp)
        assert back is not None and len(back["points"]) == 2
        assert cs.load(bs.STABILITY_GRID_KIND, "abc", other, consumer="biomarkers", root=tmp) is not None
    finally:
        bs.band_time_sweep_for_participant = real_sweep
        bs.stability_grid_for_participant = real_grid
        bs._SHARED_CACHE_DIR_OVERRIDE = was_override


def test_the_stored_answer_names_its_grid_and_its_rule_in_its_sidecar():
    """The Closed-Loop card cannot rebuild this answer's key (it has no Django), so it finds the
    answer by what the sidecar says it is for: the grid's key since 2026-09-23 and, since
    2026-09-25, the stability rule it was computed under. Without the rule it could only read the
    payload's own `rule_version` after loading, and an older rule's answer written last would
    shadow the current one."""
    from CacheStore import store as cs
    was_override = bs._SHARED_CACHE_DIR_OVERRIDE
    tmp = tempfile.mkdtemp(prefix="stability_sidecar_rule_")
    real_sweep = bs.band_time_sweep_for_participant
    real_grid = bs.stability_grid_for_participant
    try:
        bs._SHARED_CACHE_DIR_OVERRIDE = tmp
        points = [("L", 8.5), ("L", 9.5)]
        bs.band_time_sweep_for_participant = lambda req: {
            "band_time_sweep": {"L": {"center_freqs_hz": [f for _, f in points]}},
            "band_width_hz": 5.0, "label_metric": "nrs",
            "sweep_key": {"signature_key": "sweepkeyrule", "provenance": []}}
        bs.stability_grid_for_participant = lambda uid, pts, **kw: {
            p: {"available": True, "lrt_p": 0.3} for p in points}
        out = bs.compute_and_store_stability_grid("abc", force=True)
        assert out["stored"] is True, out["reason"]
        stamp = cs.newest_stamp(bs.STABILITY_GRID_KIND, "abc", root=tmp)
        extra = (stamp or {}).get("extra") or {}
        assert extra.get("sweep_key") == "sweepkeyrule", extra
        assert extra.get("rule_version") == bs.STABILITY_GRID_RULE_VERSION, extra
    finally:
        bs.band_time_sweep_for_participant = real_sweep
        bs.stability_grid_for_participant = real_grid
        bs._SHARED_CACHE_DIR_OVERRIDE = was_override


def test_the_daily_default_grids_answer_is_kept_however_many_others_are_written():
    """A grid at the daily defaults is kept on disk through a keep group (decision 318); its
    stability answer was not. Found rebuilding RCS08 for decision 331: six daily-default grids and
    twelve at the Biomarkers page's settings were built, the kind keeps twelve answers, and the six
    daily-default answers, written first, were the ones removed. The answer for a grid at the
    defaults now names the same keep group as its grid; one at other settings names none."""
    from CacheStore import store as cs
    was_override = bs._SHARED_CACHE_DIR_OVERRIDE
    tmp = tempfile.mkdtemp(prefix="stability_keep_group_")
    real_sweep = bs.band_time_sweep_for_participant
    real_grid = bs.stability_grid_for_participant
    try:
        bs._SHARED_CACHE_DIR_OVERRIDE = tmp
        points = [("L", 8.5), ("L", 9.5)]
        key = {"k": "sweepkeydefault"}
        bs.band_time_sweep_for_participant = lambda req: {
            "band_time_sweep": {"L": {"center_freqs_hz": [f for _, f in points]}},
            "band_width_hz": 5.0, "label_metric": "nrs",
            "sweep_key": {"signature_key": key["k"], "provenance": []}}
        bs.stability_grid_for_participant = lambda uid, pts, **kw: {
            p: {"available": True, "lrt_p": 0.3} for p in points}
        out = bs.compute_and_store_stability_grid("abc", request_data={"SweepMetric": "nrs"}, force=True)
        assert out["stored"] is True, out["reason"]
        default_sig = bs._stability_grid_sig_tuple("sweepkeydefault", band_width_hz=5.0, points=points)
        meta = cs.stamp_for_key(cs.product_key(bs.STABILITY_GRID_KIND, "abc", default_sig), root=tmp)
        assert ((meta or {}).get("extra") or {}).get("keep_group") == "default_settings:nrs", meta
        # thirteen answers at other settings written after it
        for i in range(13):
            key["k"] = f"sweepkeyother{i}"
            o = bs.compute_and_store_stability_grid(
                "abc", request_data={"SweepMetric": "nrs", "MatchToleranceMin": 30 + i}, force=True)
            assert o["stored"] is True, o["reason"]
        assert cs.load(bs.STABILITY_GRID_KIND, "abc", default_sig, consumer="biomarkers",
                       root=tmp) is not None, "the daily-default grid's answer was removed"
        other_sig = bs._stability_grid_sig_tuple("sweepkeyother12", band_width_hz=5.0, points=points)
        om = cs.stamp_for_key(cs.product_key(bs.STABILITY_GRID_KIND, "abc", other_sig), root=tmp)
        assert not ((om or {}).get("extra") or {}).get("keep_group"), om
    finally:
        bs.band_time_sweep_for_participant = real_sweep
        bs.stability_grid_for_participant = real_grid
        bs._SHARED_CACHE_DIR_OVERRIDE = was_override


# --------------------------------------------------------------------------------------------------
# merged from test_stability_answer_uses_grid_score.py
# A grid's stability answer is computed on the grid's own pain score (found 2026-09-26, decision 331).
#
# The daily precompute asks for a grid with `SweepMetric` only. The stability run passed that request
# on unchanged, and the per-point setup reads `LabelMetric`, which then fell back to NRS: on RCS08 the
# daily Left Leg VAS grid carried NRS stability answers (100 "cannot tell", 32 "behaves differently",
# identical to the NRS grid's). This pins that the run hands the per-point setup the grid's own score.
#
# Run inside the container:
#     python3 -W ignore modules/Biomarkers/tests/test_stability_answer_uses_grid_score.py


def _capture_setup_request(request_data):
    seen = {}
    saved = (bs.band_time_sweep_for_participant, bs.stability_grid_points, bs.stability_grid_for_participant)
    try:
        bs.band_time_sweep_for_participant = lambda req: {"band_time_sweep": {"X": {}}, "band_width_hz": 5.0,
                                                            "sweep_key": {"signature_key": "k", "provenance": []}}
        bs.stability_grid_points = lambda sweeps: [("X", 20.5)]

        def fake_grid(uid, points, **kw):
            seen.update(kw.get("request_data") or {})
            return None                                   # stop before anything is stored
        bs.stability_grid_for_participant = fake_grid
        bs.compute_and_store_stability_grid("participant-under-test", request_data=request_data, force=True)
    finally:
        (bs.band_time_sweep_for_participant, bs.stability_grid_points,
         bs.stability_grid_for_participant) = saved
    return seen


def test_a_sweep_metric_only_request_is_answered_on_that_score():
    seen = _capture_setup_request({"SweepMetric": "left_leg_vas"})
    assert seen.get("LabelMetric") == "left_leg_vas", seen


def test_an_explicit_label_metric_agrees_with_the_grid_score():
    seen = _capture_setup_request({"SweepMetric": "back_vas", "LabelMetric": "nrs"})
    assert seen.get("LabelMetric") == "back_vas", seen


# --------------------------------------------------------------------------------------------------
# merged from test_sweep_rows_carry_stability_answer.py
# B3 of the 2026-09-15 review (decision 185): the cross-setting stability answer -- "does this band
# still track pain under a different stimulation setting?" -- computed in the background for every
# stored grid (decisions 96-98) and drawn only on the Closed-Loop page's "Choose a band" card, now
# reaches the Biomarkers grid's own headline rows. Read from the store under THIS grid's own key
# (the same key the background run wrote), never the newest grid of any settings.
#
# The answer words are the Closed-Loop card's (`DecodeCommon.stability_answer`, one home): "behaves
# the same" / "behaves differently" / "cannot tell" / "not tested".


import django                                            # noqa: E402
django.setup()
from CacheStore import store as cs                      # noqa: E402
from DecodeCommon import stability_answer as SA         # noqa: E402


def _grid(points):
    rows = [{"band_center_hz": f, "pearson_r": 0.1} for _, f in points]
    return {"band_time_sweep": {"L": {"center_freqs_hz": [f for _, f in points],
                                      "best_correlation_rows": [dict(r) for r in rows],
                                      "best_auc_rows": [dict(r) for r in rows]}},
            "band_width_hz": 5.0, "label_metric": "nrs",
            "sweep_key": {"signature_key": "sweepkeyone", "provenance": []}}


def test_the_answer_words_have_one_home_and_map_the_biomarkers_verdicts():
    assert SA.answer_for_verdict("stable") == "behaves the same"
    assert SA.answer_for_verdict("stim-dependent") == "behaves differently"
    assert SA.answer_for_verdict("inconclusive") == "cannot tell"
    assert SA.answer_for_verdict("anything else") is None
    assert SA.ANSWERS == ("behaves the same", "behaves differently", "cannot tell", "not tested")


def test_rows_carry_the_stored_answer_for_this_grids_own_key_and_not_tested_where_absent():
    was = bs._SHARED_CACHE_DIR_OVERRIDE
    tmp = tempfile.mkdtemp(prefix="stability_rows_")
    try:
        bs._SHARED_CACHE_DIR_OVERRIDE = tmp
        points = [("L", 8.5), ("L", 9.5), ("L", 10.5)]
        stored = {"kind": bs.STABILITY_GRID_KIND, "rule_version": bs.STABILITY_GRID_RULE_VERSION,
                  "participant_uid": "abc", "band_width_hz": 5.0, "label_metric": "nrs",
                  "n_points_requested": 3,
                  "points": {"L|8.5": {"available": True, "lrt_p": 0.03,
                                       "stability_verdict": "stim-dependent",
                                       "equivalence": {"verdict": "stim-dependent", "reason": "the interaction test rejects"}},
                             "L|9.5": {"available": True, "lrt_p": 0.4,
                                       "stability_verdict": "inconclusive",
                                       "equivalence": {"verdict": "inconclusive", "reason": "interval wider than the margin"}},
                             "L|10.5": {"available": False, "reason": "too few eras"}}}
        sig = bs._stability_grid_sig_tuple("sweepkeyone", band_width_hz=5.0, points=points)
        assert cs.store(bs.STABILITY_GRID_KIND, "abc", sig, stored, writer="biomarkers",
                        trigger="test", provenance=[], root=tmp)

        out = bs.attach_stored_stability_answers(_grid(points), "abc")
        assert out["cross_setting_stability_from_store"] == 3
        for key in ("best_correlation_rows", "best_auc_rows"):
            rows = out["band_time_sweep"]["L"][key]
            by = {r["band_center_hz"]: r["cross_setting_stability"] for r in rows}
            assert by[8.5]["answer"] == "behaves differently" and by[8.5]["p_value"] == 0.03
            assert by[9.5]["answer"] == "cannot tell"
            assert by[10.5]["answer"] == "not tested" and "too few eras" in by[10.5]["reason"]
            assert all(r["cross_setting_stability"]["answers_possible"] == list(SA.ANSWERS) for r in rows)

        # A grid under ANOTHER key gets nothing from this entry: every row says not yet computed.
        other = _grid(points); other["sweep_key"] = {"signature_key": "sweepkeytwo", "provenance": []}
        out2 = bs.attach_stored_stability_answers(other, "abc")
        assert out2["cross_setting_stability_from_store"] == 0
        for r in out2["band_time_sweep"]["L"]["best_correlation_rows"]:
            assert r["cross_setting_stability"]["answer"] == "not tested"
            assert "not been computed" in r["cross_setting_stability"]["reason"]
        print("OK stability answers reach the Biomarkers rows under this grid's own key")
    finally:
        bs._SHARED_CACHE_DIR_OVERRIDE = was


def test_the_closed_loop_translation_uses_the_same_words():
    """The Closed-Loop card's translation (`ClosedLoopDeployment.stability`) and the Biomarkers
    rows must never disagree about a word: both read `DecodeCommon.stability_answer`."""
    try:
        from ClosedLoopDeployment import stability as CLS
    except ImportError:
        from modules.ClosedLoopDeployment import stability as CLS
    assert CLS.ANSWERS == SA.ANSWERS
    # one home: the Closed-Loop module carries no second copy of the words or the verdict map
    import inspect
    src = inspect.getsource(CLS)
    assert "stability_answer import" in src
    assert '"stable": "behaves the same"' not in src, "the verdict map is typed twice"
    assert 'ANSWERS = ("behaves' not in src, "the answer words are typed twice"
    raw = {"available": True, "lrt_p": 0.03, "stability_verdict": "stim-dependent",
           "equivalence": {"verdict": "stim-dependent", "reason": "r", "margin_log_or": CLS.STABILITY_EQUIVALENCE_MARGIN_LOG_OR}}
    assert CLS.finding_from_stability_result(raw, "L", 8.5).answer == SA.answer_for_verdict("stim-dependent")


# --------------------------------------------------------------------------------------------------
# merged from test_stability_intervals_clustered_on_report.py
# The per-state odds-ratio intervals, and the "behaves the same" check that reads the same standard
# error, count each pain report once (the PI, 2026-09-25 night, the P-03 follow-up).
#
# Several neural samples are matched to one pain report, and every one of them carries that report's
# rating. The per-state logistic fit behind the odds ratio treated every sample as independent, so a
# report matched to ten samples counted ten times and the interval came out narrower than the data
# justify. The standard error is now CLUSTERED ON THE PAIN REPORT: the CR1 sandwich (the fit's own
# information matrix either side of the summed per-report score products, times the small-sample
# factor G/(G-1) * (N-1)/(N-K), G reports, N samples, K = 2 coefficients) -- statsmodels'
# `cov_type="cluster"` with its default correction, which is Stata's. The odds ratio itself does not
# move; only its standard error does.
#
# The first two tests need no R and run under both runners; the third needs the mixed model and is
# skipped (as a plain return) where R is absent.


import datetime as _dt
import numpy as np
import pandas as pd
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from Biomarkers.routines import analytics  # noqa: E402
Z975 = 1.959963984540054


def _frame(n_reports=40, per_report=1, seed=3):
    """One stimulation state, `n_reports` reports each matched to `per_report` IDENTICAL samples."""
    rng = np.random.default_rng(seed)
    x = rng.normal(0, 1, n_reports)
    p = 1 / (1 + np.exp(-(0.2 + 0.9 * x)))
    y = (rng.uniform(size=n_reports) < p).astype(int)
    rep = np.repeat(np.arange(n_reports), per_report)
    return pd.DataFrame({"pain_high": y[rep], "band_power": x[rep],
                         "stim_era": pd.Categorical(["OFF"] * rep.size,
                                                    categories=["OFF", "LOW", "HIGH"]),
                         "report": rep})


def _cr1_by_hand(df):
    """The CR1 sandwich for the slope, written out, so the test names the estimator exactly."""
    import statsmodels.api as sm
    X = sm.add_constant(df["band_power"].to_numpy())
    y = df["pain_high"].to_numpy()
    fit = sm.GLM(y, X, family=sm.families.Binomial()).fit()
    mu = fit.fittedvalues
    bread = np.linalg.inv((X * (mu * (1 - mu))[:, None]).T @ X)
    scores = X * (y - mu)[:, None]
    g = df["report"].to_numpy()
    meat = np.zeros((2, 2))
    for k in np.unique(g):
        s = scores[g == k].sum(axis=0)
        meat += np.outer(s, s)
    G, N, K = np.unique(g).size, len(y), 2
    cov = (G / (G - 1)) * ((N - 1) / (N - K)) * bread @ meat @ bread
    return float(fit.params[1]), float(np.sqrt(cov[1, 1])), float(fit.bse[1])


def test_the_state_slope_carries_the_cr1_standard_error_clustered_on_the_pain_report():
    df = _frame(n_reports=40, per_report=3)
    df.loc[df.index % 3 == 1, "band_power"] += 0.05       # samples of one report need not be identical
    tbl = analytics._era_slope_table(df, group_col="report")
    b, se_cr1, se_plain = _cr1_by_hand(df)
    got = tbl["OFF"]
    assert abs(got["slope_log_or"] - b) <= 1e-12, (got, b)
    assert abs(got["se"] - se_cr1) <= 1e-9 * se_cr1, (got["se"], se_cr1)
    assert abs(got["se_unclustered"] - se_plain) <= 1e-12, (got["se_unclustered"], se_plain)
    assert got["n"] == 120 and got["n_reports"] == 40, got
    assert "CR1" in got["se_method"] and "pain report" in got["se_method"], got["se_method"]
    assert tbl["LOW"] is None and tbl["HIGH"] is None


def test_each_rating_counts_once_however_many_samples_it_matched():
    """The point of the change. Copy every report's one sample six times: the unclustered standard
    error shrinks by the square root of six (the fit thinks it has six times the data); the one
    clustered on the report stays where the one-sample-per-report fit put it."""
    one = analytics._era_slope_table(_frame(per_report=1), group_col="report")["OFF"]
    six = analytics._era_slope_table(_frame(per_report=6), group_col="report")["OFF"]
    assert abs(six["slope_log_or"] - one["slope_log_or"]) <= 1e-6
    assert abs(six["se_unclustered"] * np.sqrt(6) - one["se_unclustered"]) <= 1e-4 * one["se_unclustered"]  # the fit stops at its own tolerance
    ratio = six["se"] / one["se_unclustered"]
    assert 0.75 < ratio < 1.35, ratio
    assert six["se"] > 2.0 * six["se_unclustered"], (six["se"], six["se_unclustered"])


def test_a_state_resting_on_one_pain_report_has_no_standard_error():
    df = _frame(n_reports=1, per_report=8)
    df["pain_high"] = [0, 1] * 4                          # both classes, one report
    assert analytics._era_slope_table(df, group_col="report")["OFF"] is None


def test_without_a_report_column_the_fit_says_it_counted_samples():
    tbl = analytics._era_slope_table(_frame(per_report=2))
    got = tbl["OFF"]
    assert got["se"] == got["se_unclustered"]
    assert "not clustered" in got["se_method"], got["se_method"]


# --- the stability test itself (needs R for its mixed-model comparison) ----------------------
_T0 = 1_750_000_000.0
_H, _M = 3600.0, 60.0


def _iso(ep):
    return _dt.datetime.utcfromtimestamp(ep).isoformat(sep=" ")


def _detail(seed=0, per_report=4):
    rng = np.random.default_rng(seed)
    n = 90
    t, rg = [], []
    for r in range(n):
        for k in range(per_report):
            t.append(_T0 + r * 6 * _H + (k - per_report / 2) * 10 * _M)
            rg.append(r)
    t, rg = np.asarray(t), np.asarray(rg)
    pain = rng.normal(5, 2, n)
    F = 60
    f = np.linspace(0.95, 100, F)
    psd = np.abs(rng.normal(1, 0.2, (t.size, 1, F)))
    band = (f >= 17.5) & (f <= 22.5)
    psd[:, 0, band] *= (1 + 0.15 * (pain[rg] - pain.mean()))[:, None]
    detail = {"f_set": f, "psd": psd, "labels": pain[rg], "rating_group": rg,
              "chan_order": ["ZERO_TWO_LEFT"], "times": [_iso(x) for x in t]}
    # the current steps three hours before reports 30 and 60, so no report straddles a step
    stim = {"t": [_T0 - 10 * _H, _T0 + (30 * 6 - 3) * _H, _T0 + (60 * 6 - 3) * _H],
            "y": [0.0, 0.7, 2.5]}
    return detail, stim


def test_the_stability_test_reads_the_clustered_error_for_intervals_and_the_verdict():
    detail, stim = _detail()
    out = analytics.band_stim_stability(detail, "ZERO_TWO_LEFT", 20.0, stim_series=stim,
                                        strategy="median")
    if not out.get("available"):
        assert "unavailable" in out.get("reason", ""), out
        return
    assert "clustered on the pain report" in out["or_by_era_interval"], out["or_by_era_interval"]
    for tag in ("OFF", "LOW", "HIGH"):
        sl, ci = out["slope_by_era"][tag], out["or_by_era_ci"][tag]
        assert sl["n_reports"] == 30 and sl["n"] == 120, (tag, sl)
        assert sl["se"] != sl["se_unclustered"], (tag, sl)
        assert abs(ci[0] - np.exp(sl["slope_log_or"] - Z975 * sl["se"])) <= 1e-12 * ci[0]
        assert abs(ci[1] - np.exp(sl["slope_log_or"] + Z975 * sl["se"])) <= 1e-12 * ci[1]
        assert out["or_by_era_n_reports"][tag] == 30
    eq = out["equivalence"]
    a, b = eq["pair"].split(" vs ")
    se = np.sqrt(out["slope_by_era"][a]["se"] ** 2 + out["slope_by_era"][b]["se"] ** 2)
    half = (eq["ci"][1] - eq["ci"][0]) / 2.0
    assert abs(half - 1.6448536269514722 * se) <= 1e-9, (half, se)
