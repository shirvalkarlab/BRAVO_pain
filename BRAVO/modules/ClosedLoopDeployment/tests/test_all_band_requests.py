"""The server's copy of the Closed-Loop page's request builders (decision 463) equals the page's own.

`fixtures/all_band_requests.json` is written by the page test `allBandRequests.fixture.test.js`
from the page's real functions; both tests read it, so a change on either side fails one of them.
A saved answer is filed under its whole request, so any difference here means the work done ahead
is never found.
"""
import json
import pathlib
import sys

_BRAVO_ROOT = pathlib.Path(__file__).resolve().parents[3]
if str(_BRAVO_ROOT) not in sys.path:
    sys.path.insert(0, str(_BRAVO_ROOT))

from modules.ClosedLoopDeployment import all_band_requests as A

FIX = json.loads((pathlib.Path(__file__).parent / "fixtures" / "all_band_requests.json").read_text())


def _as_sent(o):
    """What Django hands the server: the page's JSON, parsed."""
    return json.loads(json.dumps(o))


def test_every_band_and_every_request_equals_the_pages():
    got = A.all_band_requests(FIX["uid"], FIX["grid"], FIX["settings"])
    assert [(b["channel"], b["centre"]) for b in got] == [(b["channel"], b["centre"]) for b in FIX["bands"]]
    for g, f in zip(got, FIX["bands"]):
        for k in ("report", "summary", "roc", "era"):
            assert _as_sent(g[k]) == f[k], (g["channel"], g["centre"], k)
            assert json.dumps(g[k], sort_keys=True) == json.dumps(f[k], sort_keys=True)   # 5 never 5.0
        lsb = A.lsb_body(g["lsb_template"], 1234.5)
        assert json.dumps(lsb, sort_keys=True) == json.dumps(f["lsb_at_cut_1234_5"], sort_keys=True)


def test_the_grid_request_equals_the_pages():
    assert json.dumps(A.grid_body(FIX["uid"], FIX["settings"]), sort_keys=True) == \
        json.dumps(FIX["grid_body"], sort_keys=True)


def test_settings_come_from_the_newest_report_the_page_sent_else_the_committed_band():
    committed = {"sweep_metric": "back_vas", "label_strategy": "percentile", "percentile_low": 30,
                 "percentile_high": 70, "match_tolerance_min": 20, "match_direction": "nearest",
                 "allow_window_reuse": True, "include_clinic_sheet_ratings": False}
    s, src = A.settings_from(remembered=[], committed_grid_settings=committed)
    assert src == "committed band" and s["LabelMetric"] == "back_vas" and s["MatchToleranceMin"] == 20
    assert s["AllowWindowReuse"] is True and s["MaxPerRating"] == 3       # the page's defaults fill the rest
    rep = {"kind": "closed_loop_report", "body": {"PainScore": "nrs", "MatchToleranceMin": 5,
           "MatchDirection": "prior", "AllowWindowReuse": "", "MaxPerRating": 2, "RefractoryMin": 1,
           "IncludeClinicSheetRatings": "1", "LabelStrategy": "tertile", "PercentileLow": 33.3333,
           "PercentileHigh": 66.6667}}
    s, src = A.settings_from(remembered=[rep], committed_grid_settings=committed)
    assert src == "page" and s["LabelMetric"] == "nrs" and s["MaxPerRating"] == 2
    assert s["AllowWindowReuse"] is False and s["IncludeClinicSheetRatings"] is True
