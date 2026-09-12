"""The two-stage path (open-loop search -> gate -> closed-loop stage) wired into the service.

What these tests hold, 2026-09-12: a request WITHOUT `TwoStage: true` gets the response it always
got, with no `two_stage` key and the same fields; a request WITH the flag gets a `two_stage` block
carrying the gate's verdict with every condition named; a gate refusal is reported with its reasons
and Stage 2 is absent; the block's numbers equal a direct call of `pipeline.run_two_stage_live` on
the same inputs, field for field; Stage 2's policies are reported when the gate licenses it; and the
flag is in the response key but not in the four tables' key.

The platform lookups, the design matrix, the settings stream, the flat pipeline fit and the LFP
evidence builder are stood in for, the way `test_service_store.py` stands them in. What runs for
real is the service's wiring, the store, Stage 1's scikit-learn fit, the gate and Stage 2.
Nothing here imports another test file: the two fixtures it needs are copied in.
"""
import importlib
import math
import shutil
import sys
import tempfile
import types

import numpy as np
import pandas as pd
import pytest

from StimOptimizer import adapter as AD
from StimOptimizer import bravo_service as BS
from StimOptimizer import pipeline as PL
from StimOptimizer import stage1_openloop as S1
from StimOptimizer import stage2_closedloop as S2
from StimOptimizer.routines import stage_gate as GATE

st = BS._cache_store
prov = BS._provenance
_ledger = importlib.import_module(st.__name__.rsplit(".", 1)[0] + ".ledger")

UID = "PARTICIPANT"
MATCHED_KEY = st.product_key("therapy_pain_matched", UID, ("m", 1))
TILES_KEY = "raw_lsb_tiles/PARTICIPANT/t1"
STREAM_KEY = "therapy_settings/PARTICIPANT/s1"


# ---------------------------------------------------------------------------------------------
# Fixtures: a design matrix Stage 1 can fit, and LFP evidence that responds to amplitude
# ---------------------------------------------------------------------------------------------
def _matrix(n_per_cell=11, pw_levels=(100.0, 140.0), rates=(55.0, 165.0), seed=0, aliased=True):
    """A matrix with the structure of the real RCS08 record: pulse width aliased with rate, so
    Stage 1 cannot resolve its choice and the gate refuses on `openloop_choice_resolved`."""
    rng = np.random.default_rng(seed)
    rows, ep = [], 0
    for i, pw in enumerate(pw_levels):
        use = (rates[i % len(rates)],) if aliased else rates
        for rate in use:
            for k in range(n_per_cell):
                ep += 1
                rows.append(dict(
                    epoch=float(ep), freq_hz=float(rate), pw_us_Left=float(pw),
                    amp_mA_Left=float(1.0 + 0.2 * (k % 5)), amp_mA_Right=float(1.2 + 0.2 * (k % 4)),
                    n=8.0, dur_h=200.0, state="bilateral_active",
                    left_leg_vas=float(50.0 + 3.0 * rng.standard_normal()), left_leg_vas_sd=8.0,
                    back_vas=float(40.0 + 3.0 * rng.standard_normal()), back_vas_sd=8.0))
    d = pd.DataFrame(rows)
    d["t0"] = pd.date_range("2025-07-01", periods=len(d), freq="3D", tz="UTC")
    d["t_end"] = d["t0"] + pd.Timedelta(days=2)
    d.attrs[st.STORE_KEY_ATTR] = MATCHED_KEY
    return d


def _responding_lfp(n=120, seed=0):
    rng = np.random.default_rng(seed)
    amp = np.repeat([1.0, 3.0], n // 2)
    freqs = np.arange(4.0, 40.0, 0.5)
    mag = np.abs(rng.normal(1.0, 0.05, (n, freqs.size)))
    sel = (freqs >= 13.0) & (freqs <= 17.0)
    mag[:, sel] *= (np.exp(-0.9 * amp)[:, None] * 3.0)
    return GATE.LfpEvidence(amplitude_mA=amp, magnitude=mag, freqs=freqs,
                            era=np.tile(["a", "b"], n // 2), cluster=np.arange(n))


class _Arm:
    def __init__(self):
        self.site, self.hemisphere = "left_leg", "Left"
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


class _LiveEvidenceStub:
    """Stands in for `pipeline.live_evidence`: records the rate it was pinned to and hands back
    evidence that responds to amplitude, keyed on one sensing contact."""

    def __init__(self, evidence=None):
        self.calls = []
        self.evidence = evidence

    def __call__(self, participant, **kw):
        self.calls.append(dict(kw))
        if self.evidence is None:
            return PL.LiveEvidence(selected=None, selected_key=None,
                                   selection_note="no cell survived screening",
                                   screen=pd.DataFrame({"deployable": [False]}),
                                   audit=pd.DataFrame())
        return PL.LiveEvidence(selected=self.evidence,
                               selected_key=("ONE_THREE_LEFT", "Left", float(kw.get("rate_hz"))),
                               selection_note="stubbed responding cell",
                               screen=pd.DataFrame({"deployable": [True]}), audit=pd.DataFrame())


@pytest.fixture
def bench(monkeypatch):
    root = tempfile.mkdtemp(prefix="bravo_so_twostage_")
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
    stream.attrs[st.STORE_KEY_ATTR] = STREAM_KEY
    monkeypatch.setattr(AD, "settings_stream", lambda p, **kw: stream)
    es = _matrix()
    monkeypatch.setattr(AD, "build_design_matrix", lambda p, rd=None, **kw: es.copy())
    monkeypatch.setattr(BS, "_tiles_key_for", lambda p: (TILES_KEY, None))
    monkeypatch.setattr(BS, "closed_loop_readiness",
                        lambda p, es, include=True: {"available": False, "reason": "stubbed"})
    monkeypatch.setattr(BS, "_blockers", lambda rep, arms, observed=None: [])
    monkeypatch.setattr(BS.pipeline, "run", lambda es, **kw: _Report())
    live = _LiveEvidenceStub(_responding_lfp())
    monkeypatch.setattr(PL, "live_evidence", live)
    st.store("therapy_pain_matched", UID, ("m", 1), es.drop(columns=["t0", "t_end"]),
             writer="stim_optimizer", provenance=prov.flatten([
                 prov.entry(STREAM_KEY, kind="therapy_settings", writer="stim_optimizer"),
                 prov.entry("redcap_reports/PARTICIPANT/r1", kind="redcap_reports",
                            writer="biomarkers")]), root=root)
    yield types.SimpleNamespace(root=root, es=es, stream=stream, live=live)
    shutil.rmtree(root, ignore_errors=True)


REQ = {"ParticipantId": UID, "Backend": "none", "Hemispheres": ["Left"]}
REQ_FLAG = dict(REQ, TwoStage=True)

GATE_NAMES = ("rate_at_or_above_adaptive_minimum", "openloop_choice_resolved",
              "adaptive_band_passes_lfp_response",
              "amplitude_limits_inside_envelope_and_under_ceiling")


def _flatten(o, prefix="", out=None):
    out = {} if out is None else out
    if isinstance(o, dict):
        for k, v in o.items():
            _flatten(v, f"{prefix}.{k}" if prefix else str(k), out)
    elif isinstance(o, (list, tuple)):
        for i, v in enumerate(o):
            _flatten(v, f"{prefix}[{i}]", out)
    else:
        out[prefix] = o
    return out


def _same(a, b):
    if isinstance(a, float) and isinstance(b, float):
        return (math.isnan(a) and math.isnan(b)) or a == b
    return a == b


# ---------------------------------------------------------------------------------------------
# Off by default
# ---------------------------------------------------------------------------------------------
def test_without_the_flag_the_response_has_no_two_stage_key_and_the_path_is_never_run(bench, monkeypatch):
    def boom(*a, **k):
        raise AssertionError("two_stage_block must not be called when the flag is absent")
    monkeypatch.setattr(BS, "two_stage_block", boom)
    out = BS.run_for_participant(dict(REQ))
    assert out["available"] is True
    assert "two_stage" not in out
    assert bench.live.calls == [], "the LFP evidence builder must not run without the flag"
    assert sorted(out) == ["amplitude_effect", "arms", "available", "blockers", "cache_status",
                           "closed_loop", "design_matrix", "ground_truth", "manifest",
                           "participant", "recommendation_supported", "store", "summary",
                           "washin_min"]


def test_without_the_flag_every_field_equals_the_flag_on_response_outside_the_new_block(bench):
    """The flag adds the `two_stage` block and changes nothing else: every other field of the
    two responses is compared and must be equal, except the store's own key and timestamp, which
    differ BECAUSE the flag is in the key."""
    off = _flatten(BS.run_for_participant(dict(REQ)))
    on = _flatten(BS.run_for_participant(dict(REQ_FLAG)))
    bookkeeping = ("store.response_key", "store.stored_utc")
    on_rest = {k: v for k, v in on.items()
               if not k.startswith("two_stage") and not k.startswith("cache_status")
               and k not in bookkeeping}
    off_rest = {k: v for k, v in off.items()
                if not k.startswith("cache_status") and k not in bookkeeping}
    assert set(on_rest) == set(off_rest)
    differing = [k for k in off_rest if not _same(off_rest[k], on_rest[k])]
    assert differing == [], differing
    assert len(off_rest) > 50


# ---------------------------------------------------------------------------------------------
# With the flag
# ---------------------------------------------------------------------------------------------
def test_with_the_flag_the_block_carries_the_gate_verdict_with_every_condition_named(bench):
    out = BS.run_for_participant(dict(REQ_FLAG))
    two = out["two_stage"]
    assert two["available"] is True and two["requested"] is True
    assert "PyTorch" in two["backend"] and "not used" in two["backend"]
    assert isinstance(two["gate"]["passed"], bool)
    assert two["can_deploy_closed_loop"] == two["gate"]["passed"]
    names = [c["name"] for c in two["gate"]["conditions"]]
    assert tuple(names) == GATE_NAMES, "the four live conditions, and not the two 2026-09-02 snapshot ones"
    for c in two["gate"]["conditions"]:
        assert c["verdict"] in ("PASS", "FAIL", "NOT ASSESSED", "OVERRIDDEN")
        assert c["detail"], c["name"]
    fc = two["stage1"]["frozen_configuration"]
    assert [s["hemisphere"] for s in fc["settings"]] == ["Left"]
    s = fc["settings"][0]
    assert s["rate_hz"] in (55.0, 165.0) or isinstance(s["rate_hz"], float)
    assert s["pulse_width_us"] in (100.0, 140.0)
    assert s["amplitude_delivered_min_mA"] == 1.0 and s["amplitude_delivered_max_mA"] == 1.8
    assert fc["contacts"] is None and "does not choose or freeze" in fc["contacts_note"]
    # the evidence was pinned to the rate Stage 1 froze, not chosen before it
    assert bench.live.calls and bench.live.calls[0]["rate_hz"] == s["rate_hz"]
    assert two["lfp_evidence"]["pinned_rate_hz"] == s["rate_hz"]
    assert two["lfp_evidence"]["selected_key"] == ["ONE_THREE_LEFT", "Left", s["rate_hz"]]
    assert two["inputs"] == {"matched_table": MATCHED_KEY, "tiles": TILES_KEY,
                             "settings_stream": STREAM_KEY}
    for stage in ("stage1", "gate", "stage2"):
        assert two["provenance"][stage]
    assert MATCHED_KEY in two["provenance"]["stage1"]
    assert TILES_KEY in two["provenance"]["gate"]


def test_a_gate_refusal_is_reported_with_its_reasons_and_stage_2_is_absent(bench):
    """On the aliased matrix Stage 1 cannot resolve its choice, so the gate refuses on
    `openloop_choice_resolved`; the refusal is named, and no policies are reported."""
    two = BS.run_for_participant(dict(REQ_FLAG))["two_stage"]
    assert two["gate"]["passed"] is False
    refused = {r["condition"] for r in two["gate"]["refusals"]}
    assert "openloop_choice_resolved" in refused
    cond = next(c for c in two["gate"]["conditions"] if c["name"] == "openloop_choice_resolved")
    assert cond["passed"] is False and "NOT resolved" in cond["detail"]
    assert two["stage1"]["frozen_configuration"]["resolved"] is False
    s2 = two["stage2"]
    assert s2["started"] is False
    assert "policies" not in s2 and "best" not in s2
    assert {r["condition"] for r in s2["refusal_reasons"]} == refused
    assert all(r["reason"] for r in s2["refusal_reasons"])
    assert "did not start" in two["provenance"]["stage2"]


def test_the_block_equals_a_direct_call_of_run_two_stage_live_field_for_field(bench, monkeypatch):
    from StimOptimizer.routines import objective as OBJ
    out = BS.run_for_participant(dict(REQ_FLAG))
    two = out["two_stage"]
    participant = types.SimpleNamespace(uid=UID)
    rep = PL.run_two_stage_live(
        participant, design=bench.es.copy(), stream=bench.stream, request_data=dict(REQ_FLAG),
        washin_min=1.0, amp_ceiling=OBJ.AMP_HARD_LIMIT_MA, hemispheres=("Left",),
        primary_item="left_leg",
        data_horizon=two["stage1"]["frozen_configuration"]["data_horizon"])
    direct = BS._two_stage_payload(rep, inputs=two["inputs"], seconds=0.0)
    a, b = _flatten(two), _flatten(direct)
    a.pop("seconds"); b.pop("seconds")
    assert set(a) == set(b), (set(a) ^ set(b))
    differing = [k for k in a if not _same(a[k], b[k])]
    assert differing == [], differing[:20]
    assert len(a) > 100


def test_stage_2_policies_are_reported_when_the_gate_licenses_it():
    """The serialisation of a run the gate licensed: Stage 2's valid policies, its best row and
    its ranking basis are copied from the subsystem's own result."""
    cfg = S1.FrozenConfiguration(
        settings=(S1.HemisphereSetting(
            hemisphere="Left", rate_hz=130.0, pw_us=60.0, amp_star_mA=2.0,
            amp_delivered_min_mA=1.0, amp_delivered_max_mA=4.0, n_epochs_fitted=20,
            rate_resolved=True, pw_resolved=True, reasons=("fixture",)),),
        primary_item="left_leg", incumbent_epoch=1.0, incumbent_rate_hz=55.0,
        incumbent_pw_us=60.0, data_horizon="test", washin_min=1.0, n_epochs_total=40)
    lfp = _responding_lfp()
    gate = GATE.evaluate_gate(cfg, lfp=lfp, amp_limits={"Left": (1.5, 3.0)})
    assert gate.passed, gate.describe()
    s2 = S2.run_stage2(cfg, gate, lfp=lfp)
    assert s2.started and s2.n_valid > 0
    s1 = types.SimpleNamespace(frozen=cfg, slices={}, summary=pd.DataFrame(), audit={}, skipped={})
    rep = PL.TwoStageReport(stage1=s1, gate=gate, stage2=s2,
                            manifest={"gate_passed": True, "lfp_evidence": {"pinned_rate_hz": 130.0}})
    two = BS._two_stage_payload(rep, inputs={"matched_table": "m", "tiles": "t",
                                             "settings_stream": "s"}, seconds=0.1)
    assert two["gate"]["passed"] is True and two["can_deploy_closed_loop"] is True
    assert two["stage2"]["started"] is True
    assert two["stage2"]["n_valid_policies"] == s2.n_valid
    assert len(two["stage2"]["policies"]) == s2.n_valid
    best = s2.best()
    assert two["stage2"]["best"]["center_hz"] == float(best["center_hz"])
    assert two["stage2"]["best"]["rate_hz"] == 130.0 and two["stage2"]["best"]["pw_us"] == 60.0
    assert two["stage2"]["ranking_basis"] == s2.ranking_basis
    assert "enumerated closed-loop policies" in two["provenance"]["stage2"]


# ---------------------------------------------------------------------------------------------
# The store key
# ---------------------------------------------------------------------------------------------
def test_the_flag_is_in_the_response_key_and_the_four_tables_key_ignores_it():
    args = ("u", "m", "t", "a", "g")
    tail = (("left_leg",), ("Left",), 1.0, "none")
    off = BS._response_signature(*args, {}, *tail)
    on = BS._response_signature(*args, {"TwoStage": True}, *tail)
    reason = BS._response_signature(*args, {"TwoStage": True, "TwoStageOverrideReason": "x"}, *tail)
    assert off != on and on != reason
    assert BS._products_signature(off) == BS._products_signature(on) == BS._products_signature(reason)
    assert "none" not in BS._products_signature(off)


def test_a_flag_on_response_is_served_from_the_store_with_its_block_and_a_flag_off_one_without(bench):
    first = BS.run_for_participant(dict(REQ_FLAG))
    assert first["store"]["served_from_store"] is False and "two_stage" in first
    second = BS.run_for_participant(dict(REQ_FLAG))
    assert second["store"]["served_from_store"] is True
    assert second["two_stage"]["gate"] == first["two_stage"]["gate"]
    off = BS.run_for_participant(dict(REQ))
    assert "two_stage" not in off
    assert off["store"]["response_key"] != first["store"]["response_key"]
