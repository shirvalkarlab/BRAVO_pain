"""The cell drill-down for the TD-only and PSD-only maps (open item of decision 492; the PI,
2026-10-22: "Go").

Clicking a cell of the mixed map asks the server for that cell's (band power, pain score) pairs
(`bravo_service.band_time_sweep_cell_for_participant`). A `Source` of "td" or "psd" now asks for the
same cell of the TD-only or PSD-only grid, matched with the matcher modes those grids are built
with (decision 492). Held here on constructed recordings (the C4 test's: 72 reports, 0-23 own TD
only, 24-47 TD and a PSD snapshot, 48-71 a PSD snapshot only), through the real matcher:
  * a TD-only cell holds only TD-read reports, a PSD-only cell only PSD-read ones (a report with
    both is read from its PSD there), each point saying which;
  * each source cell's count is that grid's own count for the cell, at every band and length;
  * the default (no `Source`, or "mixed") is the mixed cell, field for field, with no new field;
  * an unknown source is refused with a message, nothing computed.

Run inside the container: pytest this file.
"""
import os
import sys
import unittest.mock as mock

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from modules.Biomarkers import bravo_service as B                       # noqa: E402
from modules.Biomarkers.routines import analytics as A                  # noqa: E402
from modules.Biomarkers.tests import test_td_psd_grids_apart as C4      # noqa: E402

CH = "ONE_THREE_LEFT"
REQ = {"ParticipantId": "uid", "BandTimeSweepCell": "1", "Channel": CH, "LabelStrategy": "tertile",
       "PercentileLow": 33.3333, "PercentileHigh": 66.6667, "MatchToleranceMin": 15,
       "MatchDirection": "prior", "AllowWindowReuse": False, "OutlierNMad": 0, "SweepMetric": "nrs"}


def _cell(pro, pain, cache, **req):
    """The endpoint on the constructed recordings: every loader replaced, the matcher and the
    labelling real (the chunk ceilings off, as in the C4 grid test)."""
    n = len(pro)
    patches = [
        mock.patch.object(B.models.Participant, "find", lambda **k: object()),
        mock.patch.object(B, "_recordings_setup_cached",
                          lambda uid: (["td"], [], [], [], [], [CH])),
        mock.patch.object(B, "_pain_reports_for_drilldown",
                          lambda rd, p: pd.DataFrame({"nrs": pain})),
        mock.patch.object(B, "_resolve_biomarker_metric", lambda rd, df: (df, "nrs", None)),
        mock.patch.object(B, "_pro_match_arrays",
                          lambda df, m: (np.asarray(pro, float), np.asarray(pain, float))),
        mock.patch.object(B, "_merge_clinic_sheet_ratings",
                          lambda uid, m, ml, t, v, rd: (t, v, np.zeros(n, dtype=bool),
                                                        {"included": False, "n_available": 0,
                                                         "n_added": 0, "reason": None})),
        mock.patch.object(B, "_stamp_td_product", lambda td: None),
        mock.patch.object(B, "_raw_lsb_cache_cached", lambda *a, **k: {CH: cache}),
        mock.patch.object(A, "chunk_upper_bounds",
                          lambda c, centers, family="td": [np.inf] * len(centers)),
    ]
    for p in patches:
        p.start()
    try:
        return B.band_time_sweep_cell_for_participant(dict(REQ, **req))
    finally:
        for p in patches:
            p.stop()


def _constructed():
    pro, pain, cache = C4._pair_cache(3)
    return pro, pain, cache


def test_a_td_cell_holds_only_td_read_reports_and_a_psd_cell_only_psd_read_ones():
    pro, pain, cache = _constructed()
    td = _cell(pro, pain, cache, BandCenterHz=11.5, IntegrationSeconds=30, Source="td")
    psd = _cell(pro, pain, cache, BandCenterHz=11.5, IntegrationSeconds=30, Source="psd")
    tdc, psdc = td["band_time_sweep_cell"], psd["band_time_sweep_cell"]
    assert td["message"] is None and psd["message"] is None
    assert tdc["grid_source"] == "td" and psdc["grid_source"] == "psd"
    assert tdc["grid_source_label"] == "TD only" and psdc["grid_source_label"] == "PSD only"
    assert tdc["n_points"] == 48 and psdc["n_points"] == 48         # reports 0-47; 24-71
    assert not any(p["from_device_spectrum"] for p in tdc["points"])
    assert all(p["from_device_spectrum"] for p in psdc["points"])
    assert (tdc["n_points_from_device_spectrum"], tdc["n_points_from_td"]) == (0, 48)
    assert (psdc["n_points_from_device_spectrum"], psdc["n_points_from_td"]) == (48, 0)
    # the reports owning both (24-47) are in both, read from TD in one and from PSD in the other
    pt = {p["pain"] for p in tdc["points"]} & {p["pain"] for p in psdc["points"]}
    assert pt                                                       # some pain values shared
    mixed = _cell(pro, pain, cache, BandCenterHz=11.5, IntegrationSeconds=30)["band_time_sweep_cell"]
    assert mixed["n_points"] == 72                                  # TD 0-47, PSD 48-71


def test_each_source_cells_count_is_that_grids_own_count_in_every_cell():
    pro, pain, cache = _constructed()
    sw = C4._sweep(pro, pain, {CH: cache})[CH]
    for name in ("td", "psd"):
        g = sw["by_source_grid"][name]
        secs, centres = g["integration_seconds_requested"], g["center_freqs_hz"]
        for t in (0, len(secs) - 1):
            for c in (3, 15, len(centres) - 1):
                cell = _cell(pro, pain, cache, BandCenterHz=centres[c], IntegrationSeconds=secs[t],
                             Source=name)["band_time_sweep_cell"]
                assert cell["n_points"] == int(g["n_grid"][t][c]), (name, secs[t], centres[c])
                x = np.array([p["power"] for p in cell["points"]])
                y = np.array([p["pain"] for p in cell["points"]])
                if x.size > 2 and np.std(x) > 0:
                    r = float(np.corrcoef(x, y)[0, 1])
                    assert abs(r - float(g["correlation_grid"][t][c])) < 1e-9, (name, t, c)
    # and the mixed cell is the mixed grid's
    secs, centres = sw["integration_seconds_requested"], sw["center_freqs_hz"]
    cell = _cell(pro, pain, cache, BandCenterHz=centres[15], IntegrationSeconds=secs[0])["band_time_sweep_cell"]
    assert cell["n_points"] == int(sw["n_grid"][0][15])


def test_the_default_mixed_cell_is_unchanged_field_for_field():
    pro, pain, cache = _constructed()
    calls = []
    real = B._band_time_sweep_power_by_seconds

    def _spy(*a, **k):
        calls.append(k.get("sources", "<not passed>"))
        return real(*a, **k)

    with mock.patch.object(B, "_band_time_sweep_power_by_seconds", _spy):
        a = _cell(pro, pain, cache, BandCenterHz=11.5, IntegrationSeconds=30)
        b = _cell(pro, pain, cache, BandCenterHz=11.5, IntegrationSeconds=30, Source="mixed")
        c = _cell(pro, pain, cache, BandCenterHz=11.5, IntegrationSeconds=30, Source="")
    assert calls == ["<not passed>"] * 3                            # the mixed call, as before
    assert a == b == c
    cell = a["band_time_sweep_cell"]
    assert set(cell) == {"clinic_sheet", "channel", "band_center_hz", "integration_seconds",
                         "metric_key", "metric_label", "points", "n_points", "n_high", "n_low",
                         "low_cut", "high_cut", "split_why"}
    assert all(set(p) == {"pain", "power", "label", "from_clinic_sheet"} for p in cell["points"])


def test_an_unknown_source_is_refused_with_a_message():
    pro, pain, cache = _constructed()
    out = _cell(pro, pain, cache, BandCenterHz=11.5, IntegrationSeconds=30, Source="chronic")
    assert out["band_time_sweep_cell"] is None
    assert out["message"].startswith('Source must be "td", "psd" or left out for the mixed grid')
