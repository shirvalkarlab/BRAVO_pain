"""Track A step 8: Stim Optimizer reads the store as itself and writes its outputs back.

What these tests hold: the request reads the newest amplitude-effect table as `stim_optimizer`
and reports which tile entry it describes; the four products and the response are written with
the chain of everything they derived from; a second request with the same inputs is served from
the store without fitting again; a stored response whose chain contains Stim Optimizer's own
ladder is refused, the refusal is reported, and the request computes fresh rather than going
blank; an amplitude table with the same flaw is reported as refused.

The pipeline fit, the design matrix and the platform lookups are stood in for. What runs for real
is the service's wiring, the store, and the provenance rules.
"""
import importlib
import json
import os
import shutil
import sys
import tempfile
import types

import numpy as np
import pandas as pd
import pytest

from StimOptimizer import adapter as AD
from StimOptimizer import bravo_service as BS

st = BS._cache_store
prov = BS._provenance
_ledger = importlib.import_module(st.__name__.rsplit(".", 1)[0] + ".ledger")

UID = "PARTICIPANT"
# the key the store itself would give the fixture's matched table, so it can be found by key
MATCHED_KEY = st.product_key("therapy_pain_matched", UID, ("m", 1))
TILES_KEY = "raw_lsb_tiles/PARTICIPANT/t1"


class _Arm:
    def __init__(self):
        self.site, self.hemisphere = "left_leg", "Left"
        # `rank` is the pipeline's own column, as on the live record; the first version of the
        # write-back inserted a second one and pandas refused the whole write.
        self.queue = pd.DataFrame({"rank": [1, 2], "freq_hz": [55.0, 110.0],
                                   "amp_mA": [2.0, 2.5], "score": [0.3, 0.2]})
        self.batch = self.queue.head(1).copy()
        self.meta = {"incumbent_mu": 0.4, "mu_star": -0.6, "sd_star": 0.9, "incumbent_sd": 0.9,
                     "x_star": [55.0, 2.0], "data_horizon": "h", "washin_min": 1.0,
                     "amp_col": "amp_mA_Left", "n_epochs_fitted": 10, "kernel": "rbf",
                     "safe_is_contiguous": True, "safe_contiguous_ceiling": float("nan")}
        self.ctx = types.SimpleNamespace(meta=self.meta)

    def surface_can_resolve_its_optimum(self, k=1.0):
        return False


class _Report:
    def __init__(self):
        self.arms = {"left_leg__Left": _Arm()}
        self.summary = pd.DataFrame({"arm": ["left_leg__Left"], "n_epochs": [10]})
        self.manifest = {"declared": "stub"}

    def recommendation_is_supported(self):
        return False


class _Runs:
    def __init__(self):
        self.calls = 0

    def __call__(self, es, **kw):
        self.calls += 1
        return _Report()


def _es():
    df = pd.DataFrame({"t0": pd.to_datetime(["2026-01-01", "2026-01-02"], utc=True),
                       "t_end": pd.to_datetime(["2026-01-02", "2026-01-03"], utc=True),
                       "n": [3, 4], "state": ["bilateral_active"] * 2,
                       "amp_mA_Left": [2.0, 2.5], "amp_mA_Right": [1.0, 1.0],
                       "freq_hz": [55.0, 55.0], "pw_us_Left": [60.0, 60.0],
                       "left_leg_vas": [4.0, 3.0], "back_vas": [5.0, 4.0]})
    df.attrs[st.STORE_KEY_ATTR] = MATCHED_KEY
    return df


@pytest.fixture
def bench(monkeypatch):
    root = tempfile.mkdtemp(prefix="bravo_so_store_")
    monkeypatch.setattr(BS, "_SHARED_CACHE_DIR_OVERRIDE", root)
    monkeypatch.setattr(AD, "_SHARED_CACHE_DIR_OVERRIDE", root)
    monkeypatch.setattr(_ledger, "ENABLED", False)
    monkeypatch.setattr(st, "ENABLED", True)
    models = types.ModuleType("Server.models")
    models.Participant = types.SimpleNamespace(find=lambda uid: types.SimpleNamespace(uid=uid))
    server = types.ModuleType("Server"); server.models = models
    monkeypatch.setitem(sys.modules, "Server", server)
    monkeypatch.setitem(sys.modules, "Server.models", models)
    stream = pd.DataFrame({"t": pd.to_datetime(["2026-01-01"], utc=True)})
    stream.attrs[st.STORE_KEY_ATTR] = "therapy_settings/PARTICIPANT/s1"
    monkeypatch.setattr(AD, "settings_stream", lambda p, **kw: stream)
    monkeypatch.setattr(AD, "build_design_matrix", lambda p, rd=None, **kw: _es())
    monkeypatch.setattr(BS, "_tiles_key_for", lambda p: (TILES_KEY, None))
    monkeypatch.setattr(BS, "closed_loop_readiness",
                        lambda p, es, include=True: {"available": False, "reason": "stubbed"})
    monkeypatch.setattr(BS, "_blockers", lambda rep, arms, observed=None: [])
    runs = _Runs()
    monkeypatch.setattr(BS.pipeline, "run", runs)
    # the matched table's own stamp, so the response can cite its chain
    st.store("therapy_pain_matched", UID, ("m", 1), _es().drop(columns=["t0", "t_end"]),
             writer="stim_optimizer", provenance=prov.flatten([
                 prov.entry("therapy_settings/PARTICIPANT/s1", kind="therapy_settings",
                            writer="stim_optimizer"),
                 prov.entry("redcap_reports/PARTICIPANT/r1", kind="redcap_reports",
                            writer="biomarkers")]), root=root)
    yield types.SimpleNamespace(root=root, runs=runs)
    shutil.rmtree(root, ignore_errors=True)


REQ = {"ParticipantId": UID, "Backend": "none"}


def _sidecar(root, kind):
    d = os.path.join(root, kind)
    metas = [f for f in os.listdir(d) if f.endswith(".meta.json")]
    assert len(metas) == 1, metas
    with open(os.path.join(d, metas[0])) as fh:
        return json.load(fh)


def _amplitude_table():
    rows = []
    for c in (10.5, 20.5, 26.5, 40.5):
        rows.append({"run_label": "r1", "visit_date": "2026-08-18", "ramped_side": "LEFT",
                     "sensing_contact": "ONE_THREE_LEFT", "stimulation_rate_hz": 55.0,
                     "band_center_hz": c, "n_currents_tested": 6, "current_min_mA": 1.0,
                     "current_max_mA": 3.5, "slope_p": (0.01 if c == 20.5 else 0.4),
                     "slope_stderr": 0.05, "p_curvature": np.nan, "fold_max_over_min": 1.1})
    return pd.DataFrame(rows)


def test_the_request_writes_four_products_and_the_response_with_the_chain_of_its_inputs(bench):
    out = BS.run_for_participant(dict(REQ))
    assert out["available"] and bench.runs.calls == 1
    assert out["store"]["served_from_store"] is False and out["store"]["refusal"] is None
    assert out["store"]["inputs"] == {"matched_table": MATCHED_KEY, "tiles": TILES_KEY,
                                      "amplitude_effect": None}
    written = out["store"]["written"]
    assert written == {BS.SUMMARY_KIND: True, BS.LADDER_KIND: True, BS.BATCH_KIND: True,
                       BS.MANIFEST_KIND: True, BS.RESPONSE_KIND: True}
    meta = _sidecar(bench.root, BS.RESPONSE_KIND)
    assert meta["writer"] == "stim_optimizer"
    keys = {c["kind"]: c["key"] for c in meta["provenance"]}
    assert keys["therapy_pain_matched"] == MATCHED_KEY and keys["raw_lsb_tiles"] == TILES_KEY
    assert "redcap_reports" in keys and "therapy_settings" in keys, \
        "the matched table's own chain must be flattened into the response's"
    assert out["amplitude_effect"]["available"] is False
    assert "closed-loop deployment page writes it" in out["amplitude_effect"]["reason"]
    ladder = _sidecar(bench.root, BS.LADDER_KIND)
    assert ladder["writer"] == "stim_optimizer" and ladder["kind"] == "exploration_ladder"
    table, _stamp = st.load_newest(BS.LADDER_KIND, UID, consumer="stim_optimizer", root=bench.root)
    assert list(table.columns).count("rank") == 1 and list(table["rank"]) == [1, 2]
    assert list(table.columns[:3]) == ["arm", "site", "hemisphere"]
    assert "write_error" not in out["store"]


def test_a_failed_write_back_is_reported_in_the_response_not_only_the_log(bench, monkeypatch):
    def boom(*a, **k):
        raise ValueError("cannot insert rank, already exists")
    monkeypatch.setattr(BS, "_write_outputs", boom)
    out = BS.run_for_participant(dict(REQ))
    assert out["available"] and "cannot insert rank" in out["store"]["write_error"]
    assert out["store"]["written"] is None


def test_the_same_inputs_are_served_from_the_store_without_fitting_again(bench):
    first = BS.run_for_participant(dict(REQ))
    second = BS.run_for_participant(dict(REQ))
    assert bench.runs.calls == 1, "the fit ran again although nothing feeding it changed"
    assert second["store"]["served_from_store"] is True and second["store"]["stored_utc"]
    for k in first:
        if k in ("store", "amplitude_effect"):
            continue
        assert second[k] == first[k], k


def test_a_changed_matched_table_is_a_fresh_fit(bench, monkeypatch):
    BS.run_for_participant(dict(REQ))
    st.store("therapy_pain_matched", UID, ("m", 2), _es().drop(columns=["t0", "t_end"]),
             writer="stim_optimizer", provenance=[], root=bench.root)
    es2 = _es(); es2.attrs[st.STORE_KEY_ATTR] = st.product_key("therapy_pain_matched", UID, ("m", 2))
    monkeypatch.setattr(AD, "build_design_matrix", lambda p, rd=None, **kw: es2)
    out = BS.run_for_participant(dict(REQ))
    assert bench.runs.calls == 2 and out["store"]["served_from_store"] is False


def test_the_amplitude_table_is_read_as_stim_optimizer_and_reported_with_its_inputs(bench):
    st.store(BS.AMPLITUDE_KIND, UID, ("amp", 1), _amplitude_table(), writer="closed_loop",
             provenance=prov.flatten([prov.entry(TILES_KEY, kind="raw_lsb_tiles",
                                                 writer="biomarkers")]), root=bench.root)
    out = BS.run_for_participant(dict(REQ))
    block = out["amplitude_effect"]
    assert block["available"] is True and block["read_as"] == "stim_optimizer"
    assert block["writer"] == "closed_loop" and block["describes_current_recordings"] is True
    summary = block["summary"]
    assert summary["n_rows_read"] == 4
    centres = sorted(r["band_center_hz"] for r in summary["rows"])
    assert centres == [10.5, 20.5, 26.5], "only bands inside the adaptive window are summarised"
    by = {r["band_center_hz"]: r for r in summary["rows"]}
    assert by[20.5]["any_detectable_movement"] is True and by[10.5]["any_detectable_movement"] is False
    flagged = summary["combinations_with_no_detectable_movement"]
    assert [u["band_center_hz"] for u in flagged] == [10.5, 26.5]
    assert flagged[0]["current_min_mA"] == 1.0 and flagged[0]["current_max_mA"] == 3.5
    assert flagged[0]["max_currents_tested"] == 6 and flagged[0]["min_slope_stderr"] == 0.05
    # the response's chain cites the table, and the table's own chain is flattened in
    keys = {c["kind"] for c in _sidecar(bench.root, BS.RESPONSE_KIND)["provenance"]}
    assert BS.AMPLITUDE_KIND in keys and "raw_lsb_tiles" in keys
    assert out["store"]["inputs"]["amplitude_effect"] == block["store_key"]


def test_an_amplitude_table_derived_from_the_ladder_is_refused_and_said_so(bench):
    st.store(BS.AMPLITUDE_KIND, UID, ("amp", 2), _amplitude_table(), writer="closed_loop",
             provenance=prov.flatten([prov.entry("exploration_ladder/PARTICIPANT/l1",
                                                 kind="exploration_ladder",
                                                 writer="stim_optimizer")]), root=bench.root)
    out = BS.run_for_participant(dict(REQ))
    assert out["available"]
    assert out["amplitude_effect"]["available"] is False and out["amplitude_effect"]["refused"]
    assert "refused by the store" in out["amplitude_effect"]["reason"]


def test_a_stored_response_derived_from_the_ladder_is_refused_reported_and_recomputed(bench):
    first = BS.run_for_participant(dict(REQ))
    kind, uid, _h = first["store"]["response_key"].split("/")
    d = os.path.join(bench.root, kind)
    meta_path = [os.path.join(d, f) for f in os.listdir(d) if f.endswith(".meta.json")][0]
    with open(meta_path) as fh:
        meta = json.load(fh)
    meta["provenance"].append({"key": "exploration_ladder/PARTICIPANT/l1",
                               "kind": "exploration_ladder", "writer": "stim_optimizer"})
    with open(meta_path, "w") as fh:
        json.dump(meta, fh)
    out = BS.run_for_participant(dict(REQ))
    assert bench.runs.calls == 2, "the refused response must be recomputed, not served"
    assert out["available"] and out["store"]["served_from_store"] is False
    assert "own output" in out["store"]["refusal"]
    assert out["store"]["replaced_refused_entry"] is True
    assert out["store"]["written"][BS.RESPONSE_KIND] is True
    # the clean recompute REPLACED the refused entry: the next request is served, not refused
    third = BS.run_for_participant(dict(REQ))
    assert bench.runs.calls == 2 and third["store"]["served_from_store"] is True
    assert third["store"]["refusal"] is None
    assert third["store"]["written"][BS.RESPONSE_KIND] is True


def test_the_four_tables_are_keyed_without_the_figure_backend(bench):
    BS.run_for_participant(dict(REQ))
    keys_none = {k: _sidecar(bench.root, k)["signature_key"]
                 for k in (BS.SUMMARY_KIND, BS.LADDER_KIND, BS.BATCH_KIND, BS.MANIFEST_KIND)}
    resp_none = _sidecar(bench.root, BS.RESPONSE_KIND)["signature_key"]
    out = BS.run_for_participant(dict(REQ, Backend="plotly"))
    assert out["store"]["served_from_store"] is False, "a different backend is a different response"
    keys_plotly = {k: _sidecar(bench.root, k)["signature_key"] for k in keys_none}
    assert keys_plotly == keys_none, "the tables do not depend on the backend, so one entry serves both"
    assert _sidecar(bench.root, BS.RESPONSE_KIND)["signature_key"] != resp_none


def test_a_response_computed_without_the_settings_census_is_not_stored(bench, monkeypatch):
    def down(p, **kw):
        raise RuntimeError("the stored files could not be read")
    monkeypatch.setattr(AD, "settings_stream", down)
    out = BS.run_for_participant(dict(REQ))
    assert out["available"] and out["store"]["written"] is None
    assert "settings stream was unavailable" in out["store"]["reason"]
    assert not os.path.isdir(os.path.join(bench.root, BS.RESPONSE_KIND)) or \
        not os.listdir(os.path.join(bench.root, BS.RESPONSE_KIND))
    BS.run_for_participant(dict(REQ))
    assert bench.runs.calls == 2, "a degraded response must never be served"


def test_a_missing_tile_key_is_reported_with_its_reason(bench, monkeypatch):
    monkeypatch.setattr(BS, "_tiles_key_for", lambda p: (None, "the tile key could not be built: X"))
    out = BS.run_for_participant(dict(REQ))
    assert out["available"] and out["store"]["written"] is None
    assert "no tile key" in out["store"]["reason"] and "could not be built: X" in out["store"]["reason"]


def test_the_real_tiles_key_helper_tries_both_spellings_and_reports_why(monkeypatch):
    fake = types.ModuleType("Biomarkers.bravo_service")
    fake._RAW_LSB_SHARED_KIND = "raw_lsb_tiles"
    fake._LSB_SPECTRUM_CENTERS = [8.5, 9.5]
    fake._raw_lsb_shared_signature = lambda uid, centres: ("tiles", uid, tuple(centres))
    pkg = types.ModuleType("Biomarkers"); pkg.bravo_service = fake
    # the container spelling is made to fail, so the helper must fall through to the host's
    monkeypatch.setitem(sys.modules, "modules.Biomarkers", None)
    monkeypatch.setitem(sys.modules, "modules.Biomarkers.bravo_service", None)
    monkeypatch.setitem(sys.modules, "Biomarkers", pkg)
    monkeypatch.setitem(sys.modules, "Biomarkers.bravo_service", fake)
    key, reason = BS._tiles_key_for(types.SimpleNamespace(uid=UID))
    assert reason is None, reason
    assert key.startswith("raw_lsb_tiles/PARTICIPANT/")
    fake._raw_lsb_shared_signature = lambda uid, centres: None
    key, reason = BS._tiles_key_for(types.SimpleNamespace(uid=UID))
    assert key is None and "no tile entry" in reason
    def boom(uid, centres):
        raise RuntimeError("no database")
    fake._raw_lsb_shared_signature = boom
    key, reason = BS._tiles_key_for(types.SimpleNamespace(uid=UID))
    assert key is None and "no database" in reason


def test_an_amplitude_entry_whose_payload_cannot_be_read_is_said_so_and_discarded(bench):
    st.store(BS.AMPLITUDE_KIND, UID, ("amp", 3), _amplitude_table(), writer="closed_loop",
             provenance=prov.flatten([prov.entry(TILES_KEY, kind="raw_lsb_tiles",
                                                 writer="biomarkers")]), root=bench.root)
    d = os.path.join(bench.root, BS.AMPLITUDE_KIND)
    payload = [f for f in os.listdir(d) if f.endswith(".parquet")][0]
    with open(os.path.join(d, payload), "wb") as fh:
        fh.write(b"not a parquet file")
    out = BS.run_for_participant(dict(REQ))
    block = out["amplitude_effect"]
    assert block["available"] is False and "could not be read and was discarded" in block["reason"]
    assert not [f for f in os.listdir(d) if f.endswith(".meta.json")], "the broken entry must go"
    assert out["available"]


def test_a_table_the_summary_cannot_read_does_not_take_the_request_down(bench):
    st.store(BS.AMPLITUDE_KIND, UID, ("amp", 4), _amplitude_table().drop(columns=["slope_p"]),
             writer="closed_loop", provenance=prov.flatten([prov.entry(
                 TILES_KEY, kind="raw_lsb_tiles", writer="biomarkers")]), root=bench.root)
    out = BS.run_for_participant(dict(REQ))
    block = out["amplitude_effect"]
    assert out["available"] and block["available"] is True and block["summary"] is None
    assert "slope_p" in block["summary_error"]


def test_summarise_amplitude_effect_counts_rather_than_judges():
    s = BS.summarise_amplitude_effect(_amplitude_table(), lo_hz=8.0, hi_hz=30.0)
    assert len(s["rows"]) == 3 and s["n_rows_read"] == 4 and s["n_rows_in_window"] == 3
    row = s["rows"][0]
    assert row["n_runs"] == 1 and row["max_currents_tested"] == 6
    assert row["current_min_mA"] == 1.0 and row["current_max_mA"] == 3.5
    assert row["visits"] == ["2026-08-18"] and row["any_curvature_assessed"] is False
    assert BS.summarise_amplitude_effect(None, lo_hz=8, hi_hz=30)["rows"] == []


def test_a_band_with_no_fitted_line_is_not_assessed_rather_than_without_movement():
    t = _amplitude_table()
    t.loc[t["band_center_hz"] == 26.5, "slope_p"] = np.nan          # no line could be fitted
    t.loc[t["band_center_hz"] == 26.5, "n_currents_tested"] = 2
    s = BS.summarise_amplitude_effect(t, lo_hz=8.0, hi_hz=30.0)
    by = {r["band_center_hz"]: r for r in s["rows"]}
    assert by[26.5]["any_detectable_movement"] is None and by[26.5]["n_runs_with_a_fitted_line"] == 0
    assert by[10.5]["any_detectable_movement"] is False and by[20.5]["any_detectable_movement"] is True
    assert [u["band_center_hz"] for u in s["combinations_with_no_detectable_movement"]] == [10.5]
    assert [u["band_center_hz"] for u in s["combinations_not_assessed"]] == [26.5]
    t.loc[t["band_center_hz"] == 10.5, "stimulation_rate_hz"] = np.nan   # a key the grouping drops
    s = BS.summarise_amplitude_effect(t, lo_hz=8.0, hi_hz=30.0)
    assert s["n_rows_not_grouped"] == 1 and len(s["rows"]) == 2
