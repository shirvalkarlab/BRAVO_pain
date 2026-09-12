"""The Closed-Loop "Choose a band" card reads the SAME stored grid the Biomarkers page shows.

WHY, 2026-09-11 (decision 131). The store keeps up to twelve calibrated grids per participant --
one per pain score and per combination of matching and split settings (decision 107) -- and
`adapter.band_sweep_grid_for_closed_loop` used to return the newest of them whatever it was built
under. The Biomarkers page shows the one for its own controls, so the two pages disagreed whenever
the daily precompute had written another score last. The reader now matches the newest entry
whose sidecar tag equals the tag of the request's settings, derived through the same Django-free
parsers the Biomarkers writer uses (`Biomarkers/routines/sweep_settings.py`).

These tests write real entries through the real store into a temporary directory (the sandbox
pattern of `test_track_d_grid_stability_translation.py`: clear while the override is set, decision
129). No build is ever triggered here: every case either finds its match or is one the reader must
refuse, and the build path needs Django.
"""
import pathlib
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


@pytest.fixture
def sandbox():
    d = tempfile.mkdtemp(prefix="bravo_grid_match_")
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
    extra = ({"sweep_settings": sweep_settings.sweep_settings_tag_from_request(request or {})}
             if tagged else None)
    assert st.store("biomarker_band_sweep", UID, sig, payload, writer="biomarkers",
                    trigger="band_time_sweep", provenance=chain, fmt="pickle", extra=extra)


def _r(got):
    return got["band_time_sweep"]["ONE_THREE_LEFT"]["best_correlation_rows"][0]["r"]


def test_the_requested_score_is_served_not_the_newest(sandbox):
    """Two grids stored, the NRS one older: asking for NRS returns NRS, asking for VAS returns VAS."""
    _write(("sweep", "nrs"), 0.11, request={"SweepMetric": "nrs"})
    _write(("sweep", "vas"), 0.22, request={"SweepMetric": "vas"})        # newest
    got = adapter.band_sweep_grid_for_closed_loop(UID, {"SweepMetric": "nrs"})
    assert got["available"] is True and _r(got) == 0.11, got.get("reason")
    assert got["grid_settings"]["sweep_metric"] == "nrs"
    assert got["grid_settings"]["built_now"] is False
    got = adapter.band_sweep_grid_for_closed_loop(UID, {"SweepMetric": "vas"})
    assert _r(got) == 0.22 and got["grid_settings"]["sweep_metric"] == "vas"


def test_matching_settings_beyond_the_score(sandbox):
    """Same score, different match window / direction / split: each request gets its own grid,
    and the request's values are normalised the way the writer normalised them."""
    _write(("a",), 0.1, request={"SweepMetric": "nrs", "MatchToleranceMin": 60,
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


def test_a_request_with_no_settings_means_the_defaults(sandbox):
    """The Closed-Loop page with nothing persisted from the Biomarkers page asks for the defaults,
    which is what the daily precompute stores."""
    _write(("defaults",), 0.3, request={})
    _write(("other",), 0.4, request={"SweepMetric": "mpq_sum"})                # newest
    got = adapter.band_sweep_grid_for_closed_loop(UID, None)
    assert _r(got) == 0.3
    assert got["grid_settings"]["sweep_metric"] == sweep_settings.DEFAULT_BIOMARKER_METRIC


def test_an_untagged_entry_from_before_the_tag_is_never_served(sandbox, monkeypatch):
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


def test_a_grid_built_on_demand_is_read_back_under_its_tag(sandbox, monkeypatch):
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


def test_the_newest_matching_entry_wins_among_several_for_one_setting(sandbox):
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
