"""The adaptive envelope on the two-stage path (2026-09-12).

The PI's instruction, verbatim: "don't recommend settings that adaptive cannot use unless there is
a scientific or physiological reason." What these tests hold: Stage 1's open-loop search never
freezes a rate below the device's 55 Hz adaptive minimum unless a stated reason lifts the
constraint; a stratum or cell the constraint kept out is NAMED with its reason, never silently
dropped; the frozen rate is the best cell INSIDE the envelope, not the best cell overall; an
override with a reason lifts the constraint and the reason and name travel on the frozen
configuration; an override with an empty reason changes nothing and is reported as ignored; when
no candidate at all lies inside the envelope the answer is "no adaptive-capable setting", which
the gate reads as a refusal; and the service response without the TwoStage flag is unchanged.

Stage 1 is run for real on hand-built matrices (the way `test_stage1.py` does). The service-level
tests stand the platform in the way `test_two_stage_wiring.py` does; the fixture is copied in
rather than imported, and the matrix carries a 40 Hz stratum so the envelope has something to
exclude.
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
from StimOptimizer.routines import adaptive_envelope as ENV
from StimOptimizer.routines import percept_adaptive as PA
from StimOptimizer.routines import stage_gate as GATE

st = BS._cache_store
prov = BS._provenance
_ledger = importlib.import_module(st.__name__.rsplit(".", 1)[0] + ".ledger")

UID = "PARTICIPANT"
MATCHED_KEY = st.product_key("therapy_pain_matched", UID, ("m", 1))
TILES_KEY = "raw_lsb_tiles/PARTICIPANT/t1"
STREAM_KEY = "therapy_settings/PARTICIPANT/s1"

MIN_RATE = float(PA.MIN_ADAPTIVE_RATE_HZ)


# ---------------------------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------------------------
def _matrix(n_per_cell=11, pw_levels=(100.0, 140.0), rates=(40.0, 165.0), seed=0, effect=1.0,
            service=False):
    """Pulse width aliased with rate, as on RCS08, and the FIRST stratum -- at 40 Hz, below the
    adaptive minimum -- carries a pain benefit of ``10 * effect`` points, so the unconstrained
    search prefers it and the envelope has something real to exclude."""
    rng = np.random.default_rng(seed)
    rows, ep = [], 0
    for i, pw in enumerate(pw_levels):
        rate = rates[i % len(rates)]
        for k in range(n_per_cell):
            ep += 1
            row = dict(
                epoch=float(ep), freq_hz=float(rate), pw_us_Left=float(pw),
                amp_mA_Left=float(1.0 + 0.2 * (k % 5)), amp_mA_Right=float(1.2 + 0.2 * (k % 4)),
                n=8.0, dur_h=200.0,
                left_leg_vas=float(50.0 - 10.0 * effect * (i == 0) + 3.0 * rng.standard_normal()),
                left_leg_vas_sd=8.0)
            if service:
                row.update(state="bilateral_active",
                           back_vas=float(40.0 + 3.0 * rng.standard_normal()), back_vas_sd=8.0)
            rows.append(row)
    d = pd.DataFrame(rows)
    d["t0"] = pd.date_range("2025-07-01", periods=len(d), freq="3D", tz="UTC")
    if service:
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
    def __init__(self, evidence=None):
        self.calls = []
        self.evidence = evidence

    def __call__(self, participant, **kw):
        self.calls.append(dict(kw))
        return PL.LiveEvidence(selected=self.evidence,
                               selected_key=("ONE_THREE_LEFT", "Left", float(kw.get("rate_hz"))),
                               selection_note="stubbed responding cell",
                               screen=pd.DataFrame({"deployable": [True]}), audit=pd.DataFrame())


@pytest.fixture
def bench(monkeypatch):
    root = tempfile.mkdtemp(prefix="bravo_so_envelope_")
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
    es = _matrix(service=True)
    monkeypatch.setattr(AD, "build_design_matrix", lambda p, rd=None, **kw: es.copy())
    monkeypatch.setattr(BS, "_tiles_key_for", lambda p: (TILES_KEY, None))
    monkeypatch.setattr(BS, "closed_loop_readiness",     # `**kw`: the `inputs=` pair, 2026-09-12
                        lambda p, es, include=True, **kw: {"available": False, "reason": "stubbed"})
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
REASON = "physiological reason: the 40 Hz response was seen on the clinic sheet of 2026-08-18"


def _run(d, **kw):
    return S1.run_stage1(d, hemispheres=("Left",), data_horizon="test", washin_min=1.0, **kw)


# FIT ONCE, ASSERT MANY (2026-09-12). Four tests below fitted `_run(_matrix())` -- the constraint
# on, no override, the default grid -- once each, at 3 to 4 s a fit, to assert four things about
# the one result. This module-scoped fixture fits it once. Every test whose arguments differ (the
# control with the constraint lifted, a stated override, an empty one, a grid with nothing in the
# envelope) still makes its own fit. No test writes to the result.
@pytest.fixture(scope="module")
def constrained_run():
    return _run(_matrix())


# ---------------------------------------------------------------------------------------------
# Stage 1: the constraint is applied before scoring
# ---------------------------------------------------------------------------------------------
def test_the_unconstrained_search_really_prefers_the_out_of_envelope_stratum():
    """The control: with the constraint lifted the fixture's 40 Hz stratum wins. Without this the
    tests below would be checking a constraint that had nothing to constrain."""
    res = _run(_matrix(), explore_outside_reason="control")
    assert res.frozen.setting("Left").rate_hz == 40.0


def test_a_stratum_below_the_adaptive_minimum_is_excluded_and_named_with_its_reason(constrained_run):
    res = constrained_run
    s = res.frozen.setting("Left")
    assert s.rate_hz >= MIN_RATE
    env = res.frozen.adaptive_envelope
    assert env["constrained"] is True and env["min_rate_hz"] == MIN_RATE
    assert env["grid_rates_excluded"] == [10.0, 20.0, 30.0, 40.0]
    assert "40 Hz excluded: below the 55 Hz adaptive minimum" in env["grid_rates_excluded_reason"]
    excl = env["exclusions"]["Left"]
    assert len(excl) == 1 and env["n_exclusions"] == 1
    x = excl[0]
    assert x["kind"] == "cell" and x["pw_us"] == 100.0
    assert x["unconstrained_rate_hz"] == 40.0
    assert x["reason"] == "40 Hz excluded: below the 55 Hz adaptive minimum"
    assert "40 Hz at" in x["what"] and "would have preferred" in x["what"]
    # the setting itself says what was excluded, so a reader of one side sees it there too
    assert any("ADAPTIVE ENVELOPE" in r and "40 Hz excluded" in r for r in s.reasons)
    assert s.detail["adaptive_envelope"]["unconstrained_optimum"]["rate_hz"] == 40.0
    assert "constrained to the adaptive envelope (rate >= 55 Hz" in env["statement"]
    assert "constrained to the adaptive envelope" in res.frozen.describe()
    assert "x EXCLUDED: 40 Hz" in res.frozen.describe()


def test_with_the_exclusion_the_frozen_rate_is_the_best_in_envelope_cell(constrained_run):
    """Not the incumbent, not the best cell overall: the lowest posterior mean among the cells
    that are safe AND at or above the minimum, read off the slice's own arrays."""
    res = constrained_run
    s = res.frozen.setting("Left")
    # The fixture carries no `pw_us_Right` column, so the Right side falls back to the Left
    # column and the joint stratum key is (pw, pw) -- the joint redesign's key shape.
    sl = res.slices[(s.pw_us, s.pw_us)]
    gx = sl.grid.grid_X()
    allowed = sl.safe & (gx[:, 0] >= MIN_RATE)
    assert allowed.any() and allowed.sum() < sl.safe.sum()
    i_best = int(np.argmin(np.where(allowed, sl.mu, np.inf)))
    assert sl.i_star == i_best
    assert s.rate_hz == float(gx[i_best, 0])
    assert sl.mu_star == float(sl.mu[i_best])
    # THE CURRENT ITSELF (2026-09-14) is no longer read off this pooled, 3-input cell: the
    # fixture's two pulse-width strata each carry only ONE rate of real data (40 Hz and 165 Hz),
    # so 55 Hz -- the constrained choice -- has no per-rate surface of its own on this stratum,
    # and honestly recommending nothing is the whole point of the per-rate redesign (a pooled
    # cell's amplitude at a rate with zero real data there is exactly what let the pooled model
    # recommend noise on RCS08; see stage1_openloop.py's module docstring). `gx[i_best, 1]` is
    # the pooled model's own (unreliable) answer and is asserted here as a control only, never
    # as what the module hands back.
    assert math.isnan(s.amp_star_mA)
    assert sl.rate_strata.get(55.0) is None, "the fixture must not deliver real 55 Hz data"
    joined = " ".join(s.reasons)
    assert "CURRENT:" in joined and "no rate-specific surface" in joined
    assert gx[i_best, 1] != 0.0, "sanity: the pooled cell's own amplitude is a real grid value"
    # and what the same surface would have chosen under `safe` alone is the excluded 40 Hz cell
    i_unc = int(np.argmin(np.where(sl.safe, sl.mu, np.inf)))
    assert sl.i_star_unconstrained == i_unc and float(gx[i_unc, 0]) == 40.0
    assert sl.optimum_moved_by_envelope is True
    # the summary table carries both, so the block shows them side by side
    row = res.summary.loc[res.summary["pw_us"] == s.pw_us].iloc[0]
    assert row["opt_rate_hz"] == s.rate_hz and row["opt_rate_hz_unconstrained"] == 40.0
    assert bool(row["optimum_moved_by_envelope"]) is True
    assert int(row["n_allowed"]) == int(allowed.sum())


def test_the_within_visit_batch_and_the_queue_never_propose_an_out_of_envelope_cell(constrained_run):
    res = constrained_run
    n_batch = 0
    for sl in res.slices.values():
        gx = sl.grid.grid_X()
        assert all(float(gx[int(i), 0]) >= MIN_RATE for i in sl.queue)
        for b in sl.batch:
            n_batch += 1
            assert float(b.freq_hz) >= MIN_RATE, b
    assert n_batch > 0, "the fixture must produce at least one batch member for this to test anything"


# ---------------------------------------------------------------------------------------------
# The override
# ---------------------------------------------------------------------------------------------
def test_an_override_with_a_reason_lifts_the_exclusion_and_the_reason_and_name_travel():
    res = _run(_matrix(), explore_outside_reason=REASON, explore_outside_by="Prasad Shirvalkar")
    s = res.frozen.setting("Left")
    assert s.rate_hz == 40.0
    env = res.frozen.adaptive_envelope
    assert env["constrained"] is False
    assert env["override"] == {"reason": REASON, "by": "Prasad Shirvalkar"}
    assert env["override_ignored"] is None
    # both sides are always modelled jointly now, so the (empty) exclusion list is reported
    # under both keys even though this fixture only requested a Left setting.
    assert env["exclusions"] == {"Left": [], "Right": []} and env["grid_rates_excluded"] == []
    assert env["statement"] == ("explored outside the adaptive envelope for the stated reason by "
                                f"Prasad Shirvalkar: {REASON}")
    assert any("OUTSIDE THE ADAPTIVE ENVELOPE" in r and REASON in r
               and "by Prasad Shirvalkar" in r for r in s.reasons)
    assert s.detail["adaptive_envelope"]["override"] == {"reason": REASON,
                                                         "by": "Prasad Shirvalkar"}
    assert "explored outside the adaptive envelope" in res.frozen.describe()


@pytest.mark.parametrize("empty", ["", "   ", None])
def test_an_override_with_an_empty_reason_is_ignored_and_said_to_be_ignored(empty):
    res = _run(_matrix(), explore_outside_reason=empty, explore_outside_by="somebody",
               explore_outside_requested=True)
    s = res.frozen.setting("Left")
    assert s.rate_hz >= MIN_RATE, "an empty reason must not lift the constraint"
    env = res.frozen.adaptive_envelope
    assert env["constrained"] is True and env["override"] is None
    assert env["override_ignored"] and "IGNORED" in env["override_ignored"]
    assert "without a reason" in env["override_ignored"]
    assert len(env["exclusions"]["Left"]) == 1
    assert "NOTE: an override to explore outside the adaptive envelope" in res.frozen.describe()


def test_no_override_asked_for_means_no_ignored_note(constrained_run):
    res = constrained_run
    assert res.frozen.adaptive_envelope["override_ignored"] is None


# ---------------------------------------------------------------------------------------------
# Nothing in the envelope at all
# ---------------------------------------------------------------------------------------------
def test_when_no_candidate_lies_inside_the_envelope_no_setting_is_recommended_and_the_gate_refuses():
    """A candidate grid with no rate at or above the minimum: the honest answer is NO rate, not
    the incumbent and not the best out-of-envelope cell; and the gate must read that as a
    refusal, because `nan < 55` is False and a NaN would otherwise pass the rate condition."""
    res = _run(_matrix(), freq_grid=[10, 20, 30, 40])
    s = res.frozen.setting("Left")
    assert math.isnan(s.rate_hz) and s.pw_us is None and math.isnan(s.amp_star_mA)
    assert s.rate_resolved is None and s.pw_resolved is None
    assert any("NO ADAPTIVE-CAPABLE SETTING CAN BE RECOMMENDED" in r for r in s.reasons)
    assert s.detail["adaptive_envelope"]["no_adaptive_capable_setting"] is True
    excl = res.frozen.adaptive_envelope["exclusions"]["Left"]
    assert {x["kind"] for x in excl} == {"stratum"} and len(excl) == 2
    assert all("no safe cell on this stratum" in x["reason"] for x in excl)
    assert "NO ADAPTIVE-CAPABLE RATE" in res.frozen.describe()
    cond = GATE.check_rate_floor(res.frozen)
    assert cond.passed is False
    assert "no adaptive-capable rate could be recommended on Left" in cond.detail
    assert cond.evidence["no_adaptive_capable_rate"] == ["Left"]
    gate = GATE.evaluate_gate(res.frozen, lfp=None)
    assert gate.passed is False
    assert "rate_at_or_above_adaptive_minimum" in gate.failed_names()


def test_the_gate_reads_a_nan_rate_as_a_refusal_not_a_pass(monkeypatch):
    cfg = S1.FrozenConfiguration(
        settings=(S1.HemisphereSetting(
            hemisphere="Left", rate_hz=float("nan"), pw_us=None, amp_star_mA=float("nan"),
            amp_delivered_min_mA=1.0, amp_delivered_max_mA=4.0, n_epochs_fitted=0,
            rate_resolved=None, pw_resolved=None, reasons=("fixture",)),),
        primary_item="left_leg", incumbent_epoch=1.0, incumbent_rate_hz=40.0,
        incumbent_pw_us=100.0, data_horizon="test", washin_min=1.0, n_epochs_total=22)
    assert GATE.check_rate_floor(cfg).passed is False
    # and the live evidence step does not try to pin a NaN rate: the evidence builder must not
    # be reached at all when no side has a rate
    def boom(*a, **k):
        raise AssertionError("live_evidence must not be called with no adaptive-capable rate")
    monkeypatch.setattr(PL, "live_evidence", boom)
    rep = PL.run_two_stage_live(
        types.SimpleNamespace(uid="u"), design=_matrix(service=True), stream=None,
        washin_min=1.0, hemispheres=("Left",), primary_item="left_leg", data_horizon="t",
        stage1_kwargs=dict(freq_grid=[10, 20, 30, 40]))
    assert rep.gate.passed is False
    assert rep.manifest["lfp_evidence"]["pinned_rate_hz"] is None
    assert "no adaptive-capable rate" in rep.manifest["lfp_evidence"]["selection_note"]
    assert math.isnan(rep.stage1.frozen.setting("Left").rate_hz)


# ---------------------------------------------------------------------------------------------
# The envelope module itself
# ---------------------------------------------------------------------------------------------
def test_the_envelope_reads_one_definition_of_the_minimum_and_enforces_no_invented_ceiling():
    assert ENV.MIN_RATE_HZ == PA.MIN_ADAPTIVE_RATE_HZ == 55.0
    assert ENV.MAX_RATE_HZ is None and ENV.MAX_PW_US is None
    assert ENV.rate_in_envelope(55.0) and ENV.rate_in_envelope(165.0)
    assert not ENV.rate_in_envelope(54.999) and not ENV.rate_in_envelope(float("nan"))
    assert not ENV.rate_in_envelope(None)
    c = ENV.make_constraint()
    assert not c.lifted and not c.requested and c.ignored_note is None
    c = ENV.make_constraint(reason="  ")
    assert not c.lifted and c.requested and "IGNORED" in c.ignored_note
    c = ENV.make_constraint(reason=" why ", by=" who ")
    assert c.lifted and c.reason == "why" and c.by == "who" and c.ignored_note is None
    assert ENV.exclusion_reason(40) == "40 Hz excluded: below the 55 Hz adaptive minimum"


def test_the_demonstrated_pair_annotation_never_excludes_and_never_raises():
    for args in ((55.0, 60.0, "Left"), (40.0, 100.0, "Left"), (None, None, "Left"),
                 (55.0, 60.0, "Nowhere")):
        out = ENV.brainsense_pair_demonstrated(*args)
        assert set(out) == {"demonstrated", "note"} and out["note"]
        assert out["demonstrated"] in (True, False, None)
    out = ENV.brainsense_pair_demonstrated(40.0, 100.0, "Left")
    if out["demonstrated"] is False:
        assert "not a device prohibition" in out["note"]


# ---------------------------------------------------------------------------------------------
# The service
# ---------------------------------------------------------------------------------------------
def test_the_flag_off_response_is_unchanged_and_never_runs_the_path(bench, monkeypatch):
    def boom(*a, **k):
        raise AssertionError("two_stage_block must not be called when the flag is absent")
    monkeypatch.setattr(BS, "two_stage_block", boom)
    out = BS.run_for_participant(dict(REQ))
    assert out["available"] is True and "two_stage" not in out
    assert bench.live.calls == []
    # `arms`, `blockers`, `manifest`, `recommendation_supported` and `summary` came from the flat
    # per-arm pipeline, which `run_for_participant` no longer calls (2026-09-14: the arm strip
    # and its chart are gone from the page; only the two-stage plan is served now).
    assert sorted(out) == ["amplitude_effect", "available", "cache_status",
                           "closed_loop", "current_map_schedule", "design_matrix", "ground_truth",
                           "in_force_by_side", "participant", "store",
                           "titration_plan", "washin_min"]
    # the explore-outside keys are only read with the flag on: with it off they change nothing
    out2 = BS.run_for_participant(dict(REQ, TwoStageExploreOutsideAdaptive=REASON))
    assert "two_stage" not in out2


def test_the_service_block_excludes_the_out_of_envelope_stratum_by_default(bench):
    two = BS.run_for_participant(dict(REQ_FLAG))["two_stage"]
    fc = two["stage1"]["frozen_configuration"]
    s = fc["settings"][0]
    assert s["rate_hz"] >= MIN_RATE
    env = fc["adaptive_envelope"]
    assert env["constrained"] is True and env["override"] is None
    assert env["grid_rates_excluded"] == [10.0, 20.0, 30.0, 40.0]
    assert env["exclusions"]["Left"][0]["reason"] == "40 Hz excluded: below the 55 Hz adaptive minimum"
    assert "constrained to the adaptive envelope (rate >= 55 Hz" in env["statement"]
    assert "constrained to the adaptive envelope" in two["provenance"]["stage1"]
    assert "1 exclusion(s)" in two["provenance"]["stage1"]
    assert s["detail"]["adaptive_envelope"]["unconstrained_optimum"]["rate_hz"] == 40.0
    # the evidence was pinned to the IN-envelope rate, and the gate's rate condition passes
    assert bench.live.calls[0]["rate_hz"] == s["rate_hz"]
    rate_cond = next(c for c in two["gate"]["conditions"]
                     if c["name"] == "rate_at_or_above_adaptive_minimum")
    assert rate_cond["passed"] is True


def test_the_service_override_key_with_a_reason_returns_the_out_of_envelope_rate_with_the_reason(bench):
    req = dict(REQ_FLAG, TwoStageExploreOutsideAdaptive=REASON,
               TwoStageExploreOutsideAdaptiveBy="Prasad Shirvalkar")
    two = BS.run_for_participant(req)["two_stage"]
    fc = two["stage1"]["frozen_configuration"]
    assert fc["settings"][0]["rate_hz"] == 40.0
    env = fc["adaptive_envelope"]
    assert env["constrained"] is False
    assert env["override"] == {"reason": REASON, "by": "Prasad Shirvalkar"}
    assert env["exclusions"] == {"Left": [], "Right": []}
    assert "explored outside the adaptive envelope" in two["provenance"]["stage1"]
    assert REASON in two["provenance"]["stage1"]
    assert any(REASON in r for r in fc["settings"][0]["reasons"])
    # the gate still refuses the 40 Hz rate: the override lifts the SEARCH constraint, it does not
    # make the device able to program the rate
    rate_cond = next(c for c in two["gate"]["conditions"]
                     if c["name"] == "rate_at_or_above_adaptive_minimum")
    assert rate_cond["passed"] is False and "40 Hz" in rate_cond["detail"]


def test_the_service_override_key_with_an_empty_reason_is_ignored_and_said_to_be_ignored(bench):
    two = BS.run_for_participant(dict(REQ_FLAG, TwoStageExploreOutsideAdaptive="",
                                      TwoStageExploreOutsideAdaptiveBy="somebody"))["two_stage"]
    fc = two["stage1"]["frozen_configuration"]
    assert fc["settings"][0]["rate_hz"] >= MIN_RATE
    env = fc["adaptive_envelope"]
    assert env["constrained"] is True and env["override"] is None
    assert "IGNORED" in env["override_ignored"]
    assert "NOTE: an override to explore outside the adaptive envelope" in two["provenance"]["stage1"]


def test_the_override_is_in_the_response_key_absent_empty_and_stated_all_differ():
    args = ("u", "m", "t", "a", "g")
    tail = (("left_leg",), ("Left",), 1.0, "none")
    absent = BS._response_signature(*args, {"TwoStage": True}, *tail)
    empty = BS._response_signature(*args, {"TwoStage": True, "TwoStageExploreOutsideAdaptive": ""},
                                   *tail)
    stated = BS._response_signature(*args, {"TwoStage": True,
                                            "TwoStageExploreOutsideAdaptive": REASON}, *tail)
    assert len({absent, empty, stated}) == 3
    assert (BS._products_signature(absent) == BS._products_signature(empty)
            == BS._products_signature(stated))
    assert "none" not in BS._products_signature(absent)
    # 9 since review S11 (2026-09-12): the band range, the ClosedLoop flag, the two-stage flag,
    # the override reason and its name, the explore-outside override and its name, the backend.
    assert BS._RESPONSE_ONLY_KEY_TAIL == 9
