"""Fixture builders shared by several Stim Optimizer test files (2026-10-05, the test consolidation).

Each was copied, near-verbatim, into three to six test files; one copy now lives here and every
file imports it. Arguments reproduce each file's old variant exactly (the defaults are the most
common one), so no test sees a different object than it did before.

  * `responding_lfp`   -- LFP evidence whose 13-17 Hz power is suppressed by current, so the gate's
                          band-response check passes (was `_responding_lfp` in six files);
  * `setting`, `frozen` -- a Stage 1 per-side setting and the frozen configuration around it (was
                          `_setting` / `_frozen` in the gate, Stage 2 and review files);
  * `StubArm`, `StubReport`, `LiveEvidenceStub` -- stand-ins for the flat pipeline's report and for
                          `pipeline.live_evidence`, as the service tests use them;
  * `service_bench`    -- the store sandbox every service-path test runs the request in.

Not a test file (no `test_` prefix), so pytest does not collect it.
"""
import contextlib
import shutil
import sys
import tempfile
import types

import numpy as np
import pandas as pd

from StimOptimizer import adapter as AD
from StimOptimizer import bravo_service as BS
from StimOptimizer import stage1_openloop as S1
from StimOptimizer.routines import stage_gate as GATE

st = BS._cache_store
prov = BS._provenance


def responding_lfp(n=120, low=1.0, high=3.0, suppression=0.9, band=(13.0, 17.0), seed=0,
                   hemisphere=None, channel="FIXTURE"):
    """LFP magnitude that IS suppressed by amplitude inside ``band``, so the response test passes.

    At the defaults, 19 of the gate's 35 default bands respond and carry a significant negative
    era-blocked slope (measured 2026-09-12). ``channel=None`` leaves the evidence without a
    channel name, as two of the old copies did; ``hemisphere`` is passed to `LfpEvidence` only
    when given."""
    rng = np.random.default_rng(seed)
    amp = np.repeat([low, high], n // 2)
    freqs = np.arange(4.0, 40.0, 0.5)
    mag = np.abs(rng.normal(1.0, 0.05, (n, freqs.size)))
    sel = (freqs >= band[0]) & (freqs <= band[1])
    mag[:, sel] *= (np.exp(-suppression * amp)[:, None] * 3.0)
    kw = {} if hemisphere is None else {"hemisphere": hemisphere}
    ev = GATE.LfpEvidence(amplitude_mA=amp, magnitude=mag, freqs=freqs,
                          era=np.tile(["a", "b"], n // 2), cluster=np.arange(n), **kw)
    if channel is not None:
        ev.channel = channel
    return ev


def setting(hemisphere="Left", rate_hz=130.0, pw_us=60.0, amp_star=2.0, amp_lo=1.0, amp_hi=3.0,
            rate_resolved=True, pw_resolved=True):
    return S1.HemisphereSetting(
        hemisphere=hemisphere, rate_hz=rate_hz, pw_us=pw_us, amp_star_mA=amp_star,
        amp_delivered_min_mA=amp_lo, amp_delivered_max_mA=amp_hi, n_epochs_fitted=20,
        rate_resolved=rate_resolved, pw_resolved=pw_resolved, reasons=("fixture",))


def frozen(*settings, override=None):
    """The frozen configuration around ``settings`` (one default `setting()` when none given)."""
    return S1.FrozenConfiguration(
        settings=tuple(settings or (setting(),)), primary_item="left_leg",
        incumbent_epoch=1.0, incumbent_rate_hz=55.0, incumbent_pw_us=60.0,
        data_horizon="test", washin_min=1.0, n_epochs_total=40, override=override)


class StubArm:
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


class StubReport:
    def __init__(self):
        self.arms = {"left_leg__Left": StubArm()}
        self.summary = pd.DataFrame({"arm": ["left_leg__Left"], "n_epochs": [10]})
        self.manifest = {"declared": "stub"}

    def recommendation_is_supported(self):
        return False


class LiveEvidenceStub:
    """Stands in for `pipeline.live_evidence`: records the rate it was pinned to and hands back
    evidence that responds to amplitude, keyed on one sensing contact (or, given no evidence, says
    no cell survived screening)."""

    def __init__(self, evidence=None):
        self.calls = []
        self.evidence = evidence

    def __call__(self, participant, **kw):
        from StimOptimizer import pipeline as PL
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


@contextlib.contextmanager
def service_bench(monkeypatch, es, *, uid, prefix, stream_key="therapy_settings/PARTICIPANT/s1",
                  tiles_key="raw_lsb_tiles/PARTICIPANT/t1", readiness=None):
    """A private store with the participant's inputs stubbed, for one service request.

    ``es`` is a zero-argument callable returning the matched table (with ``t0``/``t_end`` and the
    store key in ``attrs``); the matched table's own entry is written to the store with the chain
    of its two inputs. ``readiness`` replaces `closed_loop_readiness` (a stub that says
    "unavailable" when not given). Yields ``root``, ``stream``; the caller stubs the rest."""
    import importlib
    ledger = importlib.import_module(st.__name__.rsplit(".", 1)[0] + ".ledger")
    root = tempfile.mkdtemp(prefix=prefix)
    monkeypatch.setattr(BS, "_SHARED_CACHE_DIR_OVERRIDE", root)
    monkeypatch.setattr(AD, "_SHARED_CACHE_DIR_OVERRIDE", root)
    monkeypatch.setattr(ledger, "ENABLED", False)
    monkeypatch.setattr(st, "ENABLED", True)
    models = types.ModuleType("Server.models")
    models.Participant = types.SimpleNamespace(find=lambda uid: types.SimpleNamespace(uid=uid))
    server = types.ModuleType("Server"); server.models = models
    monkeypatch.setitem(sys.modules, "Server", server)
    monkeypatch.setitem(sys.modules, "Server.models", models)
    stream = pd.DataFrame({"t": pd.to_datetime(["2026-01-01"], utc=True)})
    stream.attrs[st.STORE_KEY_ATTR] = stream_key
    monkeypatch.setattr(AD, "settings_stream", lambda p, **kw: stream)
    monkeypatch.setattr(AD, "build_design_matrix", lambda p, rd=None, **kw: es())
    monkeypatch.setattr(BS, "_tiles_key_for", lambda p: (tiles_key, None))
    # `**kw`: the `inputs=` pair, 2026-09-12 (the evidence pair built once for this screen and the
    # two-stage path), so the stub takes and ignores keyword arguments.
    monkeypatch.setattr(BS, "closed_loop_readiness", readiness or (
        lambda p, es, include=True, **kw: {"available": False, "reason": "stubbed"}))
    # the matched table's own stamp, so the response can cite its chain
    st.store("therapy_pain_matched", uid, ("m", 1), es().drop(columns=["t0", "t_end"]),
             writer="stim_optimizer", provenance=prov.flatten([
                 prov.entry(stream_key, kind="therapy_settings", writer="stim_optimizer"),
                 prov.entry("redcap_reports/PARTICIPANT/r1", kind="redcap_reports",
                            writer="biomarkers")]), root=root)
    try:
        yield types.SimpleNamespace(root=root, stream=stream)
    finally:
        shutil.rmtree(root, ignore_errors=True)


# ---------------------------------------------------------------------------------------------
# The readiness screen's stubbed band evidence (was copied into test_one_band_rule.py and
# test_sandwich_rule.py): every band's power array is filled with its own centre, so a stub
# response function can tell which band it was handed whatever order the caller asks in.
# ---------------------------------------------------------------------------------------------
CENTRES = [float(c) for c in range(10, 28)]                # 18 bands, 10..27 Hz


def stub_result(responds, slope_p, sep_d, slope):
    from StimOptimizer.routines import lfp_response as LR
    return LR.ResponseResult(responds=responds, reason="fixture", direction_ok=responds,
                             separation_d=sep_d, slope_per_mA=slope, slope_p=slope_p)


class BandStubEvidence:
    def __init__(self, amps=(1.6, 4.0)):
        self.amplitude_mA = np.array(amps, float)
        self.era = np.array(["a", "b"])[:len(amps)]
        self.cluster = np.arange(len(amps))
        self.band_power = {(c, 5.0): np.full(len(amps), c) for c in CENTRES}

    def power_for(self, c, w):
        return self.band_power[(float(c), float(w))]


def fn_negative_at(centres_negative, *, slope_p=0.001):
    """Every band responds on capture; only `centres_negative` carry a significant NEGATIVE
    era-blocked slope, the rest a significant POSITIVE one. The band is read off its power
    array's first value (the fixtures fill each band's array with its centre)."""
    neg = {float(c) for c in centres_negative}

    def fn(power, amp, era=None, cluster=None):
        c = float(np.asarray(power).ravel()[0])
        return stub_result(True, slope_p, 1.2, -0.2 if c in neg else +0.2)
    return fn
