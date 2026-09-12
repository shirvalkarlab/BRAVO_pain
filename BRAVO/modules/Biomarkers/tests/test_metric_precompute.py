"""Precomputing every pain score off the request path (open item 7).

The grid answers ONE pain score per request, because the score is in its key (decision 38) -- a
different score is a different answer, not a cache miss to be avoided. So reading a second score has
always cost a whole rebuild on the request path.

The load-bearing tests here are the two guards, because both failures are silent:

  * a precompute run must start no further background work. Without that, one page load becomes a
    growing tree of processes: each of the five runs starts five more, and each also starts a
    whole-machine stability job of its own, since the stability key carries the pain score too.
    Nothing on any page would show it happening.
  * the score must never arrive as a setting. `--metrics` says which score to build; a `SweepMetric`
    carried in through the settings block would override it and store one score's grid under
    another score's name, which is the one kind of wrong answer nothing downstream can detect.
"""
import json
import pathlib
import sys

from .. import bravo_service as B

_CMD_DIR = pathlib.Path(__file__).resolve().parents[3] / "Server" / "management" / "commands"


def _command():
    """The management command, imported without Django's registry.

    Loaded by path rather than by `manage.py`, so this test needs no settings module and runs on
    the container runner like everything else here.
    """
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "precompute_band_sweeps_under_test", _CMD_DIR / "precompute_band_sweeps.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    cmd = mod.Command()
    cmd.stderr = _Sink()
    cmd.stdout = _Sink()
    return cmd


class _Sink:
    def __init__(self):
        self.lines = []

    def write(self, s):
        self.lines.append(str(s))


class _InPrecompute:
    def __enter__(self):
        self._prev = B._IN_BAND_SWEEP_PRECOMPUTE
        B._IN_BAND_SWEEP_PRECOMPUTE = True
        return self

    def __exit__(self, *exc):
        B._IN_BAND_SWEEP_PRECOMPUTE = self._prev
        return False


def test_a_precompute_run_starts_no_further_background_work():
    """THE FAN-OUT GUARD, on both launchers at once. Each is asked with arguments that would
    otherwise be perfectly launchable, so this fails if either guard is removed."""
    with _InPrecompute():
        other = B.launch_other_metrics_in_background(
            "u", {}, sweep_key="a-real-looking-key", done_metric="nrs")
        stability = B.launch_stability_grid_in_background(
            "u", {}, sweep_key="a-real-looking-key", points=[("ZERO_TWO_LEFT", 8.5)],
            band_width_hz=5.0)
    assert other["launched"] is False
    assert "precompute" in (other["reason"] or "")
    assert stability["launched"] is False
    assert "precompute" in (stability["reason"] or "")


def test_outside_a_precompute_run_the_guard_does_not_fire():
    """The control. A guard that refused everything would be trivially safe and useless, so this
    proves the refusal above is the flag's doing and not some other refusal further down.

    THE OFF SWITCH IS USED TO STOP IT HERE, and the first version of this test did not use it --
    which meant that on a runner whose store points at the production root (the container's does)
    the call went all the way through and REALLY STARTED background jobs for a participant called
    "u", leaving marker files in the live cache directory. That is decision 96's own finding
    reproduced one launcher later: a unit suite must not start whole-machine work. Switching the
    feature off gives a different, harmless refusal, which is all this control needs.
    """
    assert B._IN_BAND_SWEEP_PRECOMPUTE is False
    prev = B.BAND_SWEEP_PRECOMPUTE_BACKGROUND
    B.BAND_SWEEP_PRECOMPUTE_BACKGROUND = False
    try:
        out = B.launch_other_metrics_in_background(
            "u", {}, sweep_key="a-real-looking-key", done_metric="nrs")
    finally:
        B.BAND_SWEEP_PRECOMPUTE_BACKGROUND = prev
    assert out["launched"] is False
    assert "switched off" in (out["reason"] or ""), out["reason"]
    assert "precompute run" not in (out["reason"] or "")


def test_the_launcher_asks_for_every_score_except_the_one_just_built():
    """A pass that recomputed the score already on screen would pay for a seventh grid to learn
    nothing."""
    known = [m["key"] for m in B.BIOMARKER_METRICS]
    argv = B._band_sweep_precompute_argv("u", {}, [m for m in known if m != "nrs"])
    if argv is None:                      # manage.py is not beside the module in every checkout
        return
    metrics = argv[argv.index("--metrics") + 1].split(",")
    assert "nrs" not in metrics
    assert sorted(metrics) == sorted(m for m in known if m != "nrs")


def test_a_request_carrying_its_own_pain_reports_starts_nothing():
    """A separate process cannot reproduce reports that live only in this request body: it would
    fetch from REDCap, land on a different snapshot, and store answers under keys this page never
    looks up -- so the page would start another pass on every single load, forever."""
    for field in ("ProcessedPRO", "RedcapFieldMap"):
        out = B.launch_other_metrics_in_background(
            "u", {field: [{"anything": 1}]}, sweep_key="k", done_metric="nrs")
        assert out["launched"] is False
        assert "own pain reports" in (out["reason"] or ""), (field, out["reason"])


def test_the_settings_carried_to_the_background_run_are_a_whitelist_and_exclude_the_score():
    """Two separate rules, both load-bearing. A command line shows up in the process list, so pain
    reports and a field map must never reach one; and the score is this command's own argument, so
    a score carried in as a setting would silently override `--metrics`."""
    request = {"MatchToleranceMin": 30, "OutlierScale": "log",
               "SweepMetric": "mpq_sum", "LabelMetric": "vas",
               "ProcessedPRO": [{"nrs": 7}], "RedcapFieldMap": {"a": "b"},
               "SomethingNobodyKnows": "x"}
    argv = B._band_sweep_precompute_argv("u", request, ["nrs"])
    if argv is None:
        return
    sent = json.loads(argv[argv.index("--request-json") + 1])
    assert sent == {"MatchToleranceMin": 30, "OutlierScale": "log"}, sent
    blob = " ".join(argv)
    for forbidden in ("ProcessedPRO", "RedcapFieldMap", "SweepMetric", "LabelMetric", "nrs\": 7"):
        assert forbidden not in blob, forbidden


def test_the_command_filters_the_same_way_on_arrival():
    """Filtered twice on purpose: the launcher builds the line and the command re-checks it, so a
    line typed by hand or edited by anything else gets the same treatment."""
    cmd = _command()
    got = cmd._request_data({"request_json": json.dumps({
        "MatchToleranceMin": 30, "SweepMetric": "mpq_sum", "ProcessedPRO": [{"nrs": 7}],
        "Nonsense": 1})})
    assert got == {"MatchToleranceMin": 30}, got


def test_a_malformed_settings_argument_falls_back_to_the_defaults_rather_than_failing():
    """A scheduled pass that produced nothing because one argument was mistyped would be worse than
    one that produced the default answer."""
    cmd = _command()
    assert cmd._request_data({"request_json": "{not json"}) == {}
    assert cmd._request_data({"request_json": "[1, 2, 3]"}) == {}
    assert cmd._request_data({"request_json": None}) == {}


def test_an_unknown_pain_score_is_reported_and_skipped_rather_than_silently_replaced():
    """Silently falling back to the default score would store the default's grid under the unknown
    score's name -- a wrong answer nothing downstream could detect."""
    cmd = _command()
    known = [m["key"] for m in B.BIOMARKER_METRICS]
    assert cmd._metrics({"metrics": None}) == known
    assert cmd._metrics({"metrics": "nrs,vas"}) == ["nrs", "vas"]
    assert cmd._metrics({"metrics": "nrs,not_a_score"}) == ["nrs"]
    assert any("not_a_score" in line for line in cmd.stderr.lines)


def test_the_precompute_flag_is_restored_even_when_the_grid_raises():
    """A flag left set would silently switch off every background launch this worker ever makes
    again, and nothing would report it."""
    real = B.band_time_sweep_for_participant

    def _boom(_request):
        assert B._IN_BAND_SWEEP_PRECOMPUTE is True     # set while the work runs
        raise RuntimeError("constructed failure")

    B.band_time_sweep_for_participant = _boom
    try:
        out = B.compute_and_store_band_sweep("u", "nrs")
    finally:
        B.band_time_sweep_for_participant = real
    assert B._IN_BAND_SWEEP_PRECOMPUTE is False
    assert out["stored"] is False
    assert "constructed failure" in (out["reason"] or "")


def test_a_grid_that_was_computed_and_not_stored_is_reported_as_a_failure():
    """The one outcome nothing on any page will ever show: the page rebuilds it on every request
    and looks entirely fine, so the scheduler is the only thing that can raise a hand."""
    real = B.band_time_sweep_for_participant
    B.band_time_sweep_for_participant = lambda _r: {
        "band_time_sweep": {"ZERO_TWO_LEFT": {}}, "store_written": {"response": False}}
    try:
        out = B.compute_and_store_band_sweep("u", "nrs")
    finally:
        B.band_time_sweep_for_participant = real
    assert out["n_channels"] == 1
    assert out["stored"] is False and out["already_current"] is False
    assert "rebuilt on every request" in (out["reason"] or "")

    # And an empty grid -- no recordings, no reports -- is NOT a failure, so a participant who has
    # simply not been recorded yet cannot train a reader to ignore the log.
    B.band_time_sweep_for_participant = lambda _r: {"band_time_sweep": {}, "message": "no reports"}
    try:
        empty = B.compute_and_store_band_sweep("u", "nrs")
    finally:
        B.band_time_sweep_for_participant = real
    assert empty["n_channels"] == 0 and empty["stored"] is False
    assert empty["reason"] == "no reports"
