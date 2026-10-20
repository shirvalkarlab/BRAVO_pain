"""TD and PSD values kept apart (wave 2, C4; the PI, 2026-10-18: "PSD-only results shown, cannot
choose").

The heat map's band power for each pain report comes from TD (the time-domain recording cut into
3 s pieces) whenever the report owns any TD piece, and from the device's PSD snapshots only when it
owns none: one grid mixing the two ("TD, PSD where no TD"). C4 adds, for every contact pair, a grid
on TD alone and a grid on PSD alone, each with its own shuffles and best rows
(`by_source_grid: {td, psd}`); the band is chosen from the TD grid only.

Held here, on values:
  * the matcher's TD-only mode is the mixed matcher with the PSD fill switched off (every TD value
    identical, every PSD-read report empty), and its PSD-only mode takes every report with a PSD
    snapshot in its window, ignoring TD (a report with both is read from its PSD);
  * the TD grid holds no PSD-read report and the PSD grid none read from TD;
  * HOW A REPORT WITH BOTH IS COUNTED: in the TD grid (from its TD) AND in the PSD grid (from its
    PSD), and once in the mixed grid (from its TD). So, cell by cell,
        mixed n = TD n + (PSD n over the reports that own no TD piece),
    which the grid states itself (`by_source_grid.counting`) and this test recomputes;
  * every best row says which grid it is from and whether it can choose a band: TD rows can, PSD-only
    and mixed rows cannot;
  * the mixed grid is unchanged: the same numbers as a sweep run without the two new grids.

Run inside the container: python3 _agent_bridge/_snr6_run.py Biomarkers/tests/test_td_psd_grids_apart.py
"""
import os
import sys
import unittest.mock as mock

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from modules.Biomarkers import bravo_service as B                       # noqa: E402
from modules.Biomarkers.routines import analytics as A, availability as av  # noqa: E402
from modules.Biomarkers.routines import sweep_settings as SW            # noqa: E402

T0 = 1_700_000_000.0
SMALL = [8.5, 12.5]


def _cache(td_t, psd_t, centers, td_vals=None, psd_vals=None):
    nC = len(centers)
    td_t, psd_t = [float(t) for t in td_t], [float(t) for t in psd_t]
    td_vals = td_vals if td_vals is not None else [[100.0 + j for j in range(nC)] for _ in td_t]
    psd_vals = psd_vals if psd_vals is not None else [[200.0 + j for j in range(nC)] for _ in psd_t]
    return {"channel": "ONE_THREE_LEFT", "centers_hz": [float(c) for c in centers],
            "window_s": 3.0, "band_half_hz": 2.5,
            "td": {"t": td_t, "lsb": [list(map(float, r)) for r in td_vals],
                   "saturated": [False] * len(td_t), "source": ["constructed"] * len(td_t),
                   "n_finite_s": [3.0] * len(td_t), "ok": [True] * len(td_t)},
            "psd": {"t": psd_t, "lsb": [list(map(float, r)) for r in psd_vals],
                    "calibrated": [[True] * nC] * len(psd_t), "source": ["constructed"] * len(psd_t)},
            "n_td_windows": len(td_t), "n_psd_windows": len(psd_t)}


def _match(pro, cache, sources, lengths=(3.0, 30.0)):
    return av.live_lsb_band_medians_by_length(
        pro, cache, tol_s=900.0, lengths_s=list(lengths), centers_hz=SMALL,
        band_ceilings=[np.inf] * len(SMALL), match_direction="prior", sources=sources)


def _four_reports():
    """R0 owns TD only, R1 PSD only, R2 both, R3 nothing."""
    pro = [T0 + 1000.0, T0 + 10_000.0, T0 + 20_000.0, T0 + 30_000.0]
    td = [T0 + 900.0 + 3 * k for k in range(10)] + [T0 + 19_900.0 + 3 * k for k in range(10)]
    psd = [T0 + 9_900.0, T0 + 19_800.0]
    return pro, _cache(td, psd, SMALL)


def test_the_td_mode_is_the_mixed_matcher_with_the_psd_fill_off():
    pro, cache = _four_reports()
    mixed, mi, _ = _match(pro, cache, "both")
    td, ti, ts = _match(pro, cache, "td")
    assert mi["from_device_spectrum"] == [False, True, False, False]
    assert ti["from_device_spectrum"] == [False, False, False, False]
    for s in mixed:
        # TD values identical; the PSD-read report empty
        assert np.array_equal(td[s][[0, 2]], mixed[s][[0, 2]])
        assert np.isnan(td[s][[1, 3]]).all()
        assert ts[s]["n_pro_psd"] == 0
    assert ti["recording_times_s"][1] == []


def test_the_psd_mode_reads_every_report_with_a_snapshot_ignoring_td():
    pro, cache = _four_reports()
    psd, pi, ps = _match(pro, cache, "psd")
    assert pi["from_device_spectrum"] == [False, True, True, False]
    for s in psd:
        assert np.isnan(psd[s][[0, 3]]).all()
        # R2 owns TD and PSD; here its value is its PSD snapshot's, never its TD's
        assert psd[s][2].tolist() == [200.0, 201.0] and psd[s][1].tolist() == [200.0, 201.0]
        assert ps[s]["n_pro_td"] == 0
    assert pi["recording_times_s"][2] == [T0 + 19_800.0]


def test_the_default_mode_is_unchanged():
    pro, cache = _four_reports()
    a, ai, as_ = av.live_lsb_band_medians_by_length(
        pro, cache, tol_s=900.0, lengths_s=[3.0, 30.0], centers_hz=SMALL,
        band_ceilings=[np.inf] * len(SMALL), match_direction="prior")
    b, bi, bs_ = _match(pro, cache, "both")
    for s in a:
        assert np.array_equal(a[s], b[s], equal_nan=True)
    assert ai == bi and as_ == bs_


# ---- the whole grid, on constructed recordings with the real statistics -------------------------

N = 72
CENTERS = [float(c) for c in np.arange(8.5, 30.0, 1.0)]


def _pair_cache(seed):
    """72 hourly reports. Reports 0-47 own TD (10 pieces just before each); reports 24-71 own one
    PSD snapshot; so 24-47 own both, 0-23 TD only, 48-71 PSD only. Values are noise with one band
    tracking pain in each source (different bands), so the three grids differ."""
    rng = np.random.default_rng(seed)
    pro = [T0 + 3600.0 * i for i in range(N)]
    pain = np.clip(np.round(5 + rng.normal(0, 2, N)), 0, 10)
    td_t, td_v, psd_t, psd_v = [], [], [], []
    for i in range(N):
        if i < 48:
            for k in range(10):
                td_t.append(pro[i] - 60.0 + 3.0 * k)
                v = np.exp(rng.normal(0, 0.3, len(CENTERS))) * 100
                v[3] += 8 * pain[i]
                td_v.append(v)
        if i >= 24:
            psd_t.append(pro[i] - 120.0)
            v = np.exp(rng.normal(0, 0.3, len(CENTERS))) * 100
            v[15] += 8 * pain[i]
            psd_v.append(v)
    return pro, [float(p) for p in pain], _cache(td_t, psd_t, CENTERS, td_v, psd_v)


def _sweep(pro, pain, caches):
    old = os.environ.get("BIOMARKER_SWEEP_PROCESSES")
    os.environ["BIOMARKER_SWEEP_PROCESSES"] = "1"
    try:
        with mock.patch.object(A, "chunk_upper_bounds",
                               lambda cache, centers, family="td": [np.inf] * len(centers)):
            return B._band_time_sweep_channels(
                caches, pro, tol_s=900.0, allow_window_reuse=False, pain_values=pain,
                label_strategy="tertile", low_pct=33.3333, high_pct=66.6667, outlier_n_mad=0,
                outlier_scale="raw", metric_key="nrs", metric_label="NRS", n_perm=40, n_boot=40,
                match_direction="prior")
    finally:
        if old is None:
            os.environ.pop("BIOMARKER_SWEEP_PROCESSES", None)
        else:
            os.environ["BIOMARKER_SWEEP_PROCESSES"] = old


def _built():
    pro, pain, cache = _pair_cache(3)
    out = _sweep(pro, pain, {"ONE_THREE_LEFT": cache})
    return pro, pain, cache, out["ONE_THREE_LEFT"]


def test_the_td_grid_holds_no_psd_report_and_the_psd_grid_none_from_td():
    _pro, _pain, _cache_, sw = _built()
    td, psd = sw["by_source_grid"]["td"], sw["by_source_grid"]["psd"]
    assert td["n_pain_reports_from_device_spectrum"] == 0
    assert np.array(td["device_spectrum_n_grid"]).sum() == 0
    assert np.array(td["n_grid"]).max() == 48                      # reports 0-47
    # every report behind every PSD cell was read from a PSD snapshot
    assert np.array_equal(np.array(psd["device_spectrum_n_grid"]), np.array(psd["n_grid"]))
    assert np.array(psd["n_grid"]).max() == 48                     # reports 24-71
    assert psd["n_pain_reports_from_device_spectrum"] == 48


def test_td_count_plus_psd_count_without_td_equals_the_mixed_count_in_every_cell():
    pro, pain, cache, sw = _built()
    td, psd = sw["by_source_grid"]["td"], sw["by_source_grid"]["psd"]
    mixed_n, td_n = np.array(sw["n_grid"]), np.array(td["n_grid"])
    # recomputed here from the PSD-only matrices: PSD cells of reports that own no TD piece
    with mock.patch.object(A, "chunk_upper_bounds",
                           lambda c, centers, family="td": [np.inf] * len(centers)):
        power, *_ = B._band_time_sweep_power_by_seconds(
            pro, cache, None, tol_s=900.0, allow_window_reuse=False, match_direction="prior",
            sources="psd")
    no_td = np.arange(N) >= 48
    y = np.isfinite(np.asarray(pain))
    psd_no_td = np.array([[int((np.isfinite(power[s][:, c]) & no_td & y).sum())
                           for c in range(len(CENTERS))] for s in sw["integration_seconds_requested"]])
    assert np.array_equal(td_n + psd_no_td, mixed_n), "TD n + PSD-without-TD n != mixed n"
    # the grid states the same thing itself
    cnt = sw["by_source_grid"]["counting"]
    assert np.array_equal(np.array(cnt["psd_reports_without_td_n_grid"]), psd_no_td)
    assert cnt["n_cells"] == mixed_n.size and cnt["n_cells_adding_up"] == mixed_n.size
    assert "report with both" in cnt["rule"]
    # and a report with both is in both source grids, so they add to more than the mixed grid
    assert (td_n + np.array(psd["n_grid"]) > mixed_n).any()


def test_every_best_row_says_its_grid_and_only_td_rows_can_choose():
    _pro, _pain, _cache_, sw = _built()
    for key in ("best_correlation_rows", "best_auc_rows"):
        for r in sw[key]:
            assert r["grid_source"] == "td_psd_where_no_td" and r["can_choose_band"] is False
            assert r["cannot_choose_why"]
        for r in sw["by_source_grid"]["td"][key]:
            assert r["grid_source"] == "td" and r["can_choose_band"] is True
            assert "cannot_choose_why" not in r
        for r in sw["by_source_grid"]["psd"][key]:
            assert r["grid_source"] == "psd" and r["can_choose_band"] is False
            assert "PSD" in r["cannot_choose_why"]


def test_the_three_grids_have_their_own_answers():
    """Constructed so the TD band at 11.5 Hz and the PSD band at 23.5 Hz track pain: each source's
    own grid finds its own band, which the mixed grid's numbers could not tell apart."""
    _pro, _pain, _cache_, sw = _built()
    td_r = np.array(sw["by_source_grid"]["td"]["correlation_grid"], dtype=float)
    psd_r = np.array(sw["by_source_grid"]["psd"]["correlation_grid"], dtype=float)
    assert np.nanargmax(np.nanmean(td_r, axis=0)) == 3
    assert np.nanargmax(np.nanmean(psd_r, axis=0)) == 15


def test_the_mixed_grid_is_the_grid_without_the_two_source_grids():
    pro, pain, cache = _pair_cache(3)
    with_ = _sweep(pro, pain, {"ONE_THREE_LEFT": cache})["ONE_THREE_LEFT"]
    keep = SW.SOURCE_GRIDS
    try:
        SW.SOURCE_GRIDS = False
        without = _sweep(pro, pain, {"ONE_THREE_LEFT": cache})["ONE_THREE_LEFT"]
    finally:
        SW.SOURCE_GRIDS = keep
    assert "by_source_grid" not in without
    for k in ("correlation_grid", "auc_grid", "n_grid", "p_grid"):
        assert with_[k] == without[k], k
    for key in ("best_correlation_rows", "best_auc_rows"):
        for a, b in zip(with_[key], without[key]):
            a = {k: v for k, v in a.items() if k not in ("grid_source", "can_choose_band",
                                                       "cannot_choose_why")}
            assert a == b




def test_choosing_grid_keeps_labels_but_never_falls_back_to_psd(monkeypatch):
    monkeypatch.setattr(SW, 'CHOOSING_GRID', 'td')
    td = {'center_freqs_hz': [10], 'best_correlation_rows': [{'pearson_r': 0.5}]}
    sweep = {'grid_source': 'td_psd_where_no_td', 'display_short': 'synthetic contact', 'best_correlation_rows': [{'pearson_r': 0.9}],
             'correlation_by_recording_source': {}, 'by_source_grid': {'td': td, 'psd': td}}
    chosen = SW.choosing_sweep(sweep)
    assert chosen['best_correlation_rows'] == td['best_correlation_rows']
    assert chosen['display_short'] == sweep['display_short'] and chosen['choosing_grid'] == 'td'
    assert chosen['grid_source'] == 'td'
    assert 'by_source_grid' not in chosen and 'correlation_by_recording_source' not in chosen
    missing = SW.choosing_sweep({'by_source_grid': {'psd': td}, 'best_correlation_rows': [1]})
    assert missing['best_correlation_rows'] == [] and missing['choosing_grid'] == 'none'
    assert missing['grid_source'] == 'none'
    assert SW.choosing_sweep(None) is None and SW.choosing_grid(None) is None
    assert SW.choosing_grid({'band_time_sweep': None}) == {'band_time_sweep': None}
    payload = {'band_time_sweep': {'pair': sweep}}
    assert SW.choosing_grid(payload)['band_time_sweep']['pair'] == chosen
    assert 'by_source_grid' in payload['band_time_sweep']['pair']
    monkeypatch.setattr(SW, 'CHOOSING_GRID', 'mixed')
    assert SW.choosing_sweep(sweep)['best_correlation_rows'] == sweep['best_correlation_rows']


def test_source_tables_keep_counts_and_values_separate():
    from modules.Biomarkers.routines import band_results_tables as BT
    grid = {'center_freqs_hz': [10], 'integration_seconds_requested': [3],
            'correlation_grid': [[0.5]], 'auc_grid': [[0.75]], 'best_correlation_rows': [],
            'best_auc_rows': []}
    sweep = dict(grid, by_source_grid={'td': dict(grid), 'psd': dict(grid)})
    for builder, value, field in ((BT.correlation_table, 'pearson_r', 'correlation_grid'),
                                  (BT.discrimination_table, 'auc', 'auc_grid')):
        table = builder({'pair': sweep})
        assert len(table) == 3
        assert table['can_choose_band'].tolist() == [False, True, False]
        for source in (None, 'td', 'psd'):
            assert BT.count_matches(table, {'pair': sweep}, value, field, grid_source=source) == (1, 0)
    assert list(BT._each_grid({'center_freqs_hz': [], 'by_source_grid': {'td': None}})) == []


def test_invalid_recording_source_is_rejected():
    import pytest
    pro, cache = _four_reports()
    with pytest.raises(ValueError, match='sources must'):
        _match(pro, cache, 'invalid')


def test_both_source_modes_invalidate_prior_numeric_cache_versions(monkeypatch):
    import runpy
    rules = []
    for value in ('1', '0'):
        monkeypatch.setenv('BRAVO_SOURCE_GRIDS', value)
        settings = runpy.run_path(SW.__file__)
        assert settings['SOURCE_GRIDS'] is (value == '1')
        assert 'per_window_null_products' in settings['GRID_RULE_VERSION']
        assert settings['GRID_RULE_VERSION'] not in ('v28_per_window_null_products',
                                                     'v29_current_removed_check', 'v30_td_psd_apart')
        rules.append(settings['GRID_RULE_VERSION'])
    assert len(set(rules)) == 2


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); print("PASS", name)
            except Exception as exc:                            # noqa: BLE001
                fails += 1; print("FAIL", name, repr(exc))
    sys.exit(1 if fails else 0)
