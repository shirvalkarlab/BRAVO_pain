"""The refusal to consume a self-derived product, PROVEN BY CONSTRUCTING THE CYCLE.

WHY THIS FILE IS THE MOST IMPORTANT TEST IN THE STORE. The approved design has all three modules
writing their computed results back and reading each other's. Stim Optimizer decides which
stimulation settings still need exploring, and that decision determines which recordings come to
exist. If it then reads a ground-truth verdict computed from those same recordings and treats it as
independent evidence, its own exploration policy is confirming itself.

**That failure has no symptom.** Nothing crashes, no page errors, every number is internally
consistent, and the record looks like converging evidence when it is a loop.

So these tests do not check a hand-written chain against a rule. They **build the real cycle through
the real store** — Stim Optimizer's own output feeds a biomarker result, which feeds a closed-loop
verdict, which Stim Optimizer then asks for — and fail if the refusal does not fire. A test written
against a synthetic chain would keep passing while the real wiring leaked.

Every test also has its CONTROL: the same product derived from raw device recordings only must be
released, because a rule that refused everything would be trivially safe and useless.
"""
import pathlib
import shutil
import sys
import tempfile

import numpy as np

_BRAVO_ROOT = pathlib.Path(__file__).resolve().parents[3]
if str(_BRAVO_ROOT) not in sys.path:
    sys.path.insert(0, str(_BRAVO_ROOT))

from modules.CacheStore import provenance as prov
from modules.CacheStore import store as st

UID = "2e3c75c00d7f4f37b53a048d195f11da"


class _Sandbox:
    def __enter__(self):
        from modules.CacheStore import ledger
        self._dir = tempfile.mkdtemp(prefix="bravo_prov_test_")
        self._prev_dir, self._prev_ledger = st.DIR_OVERRIDE, ledger.ENABLED
        st.DIR_OVERRIDE, ledger.ENABLED = self._dir, False
        st.clear()
        return self._dir

    def __exit__(self, *exc):
        from modules.CacheStore import ledger
        st.DIR_OVERRIDE, ledger.ENABLED = self._prev_dir, self._prev_ledger
        shutil.rmtree(self._dir, ignore_errors=True)
        return False


def _build_the_cycle():
    """Write the three products that close the loop, through the store, and return their keys.

    1. Stim Optimizer writes the ladder of settings it chose to explore.
    2. Biomarker exploration computes a per-band result FROM THAT LADDER.
    3. Closed-loop deployment computes the ground-truth verdict FROM THAT RESULT.

    Step 3's product now transitively derives from step 1, which Stim Optimizer wrote.
    """
    settings_sig = ("settings", 1)
    settings_key = st.product_key("settings_stream", UID, settings_sig)
    st.store("settings_stream", UID, settings_sig,
             {"amplitude_ma": np.array([1.0, 2.0, 3.0])},
             writer="stim_optimizer", trigger="exploration_policy",
             provenance=prov.flatten([prov.entry(st.product_key("raw_lsb_tiles", UID, ("t", 1)),
                                                 kind="raw_lsb_tiles", writer="biomarkers")]))

    band_sig = ("bands", 1)
    band_key = st.product_key("biomarker_band_results", UID, band_sig)
    st.store("biomarker_band_results", UID, band_sig,
             {"center_hz": np.array([23.44])},
             writer="biomarkers", trigger="page_request",
             provenance=prov.flatten([
                 prov.entry(settings_key, kind="settings_stream", writer="stim_optimizer",
                            chain=st.read_stamp("settings_stream", UID, settings_sig)["provenance"]),
             ]))

    verdict_sig = ("verdict", 1)
    st.store("ground_truth_verdict", UID, verdict_sig,
             {"route": "device_native", "n_windows": 6},
             writer="closed_loop", trigger="page_request",
             provenance=prov.flatten([
                 prov.entry(band_key, kind="biomarker_band_results", writer="biomarkers",
                            chain=st.read_stamp("biomarker_band_results", UID,
                                                band_sig)["provenance"]),
             ]))
    return settings_sig, band_sig, verdict_sig


# --------------------------------------------------------------------------------------------
# the constructed cycle
# --------------------------------------------------------------------------------------------

def test_stim_optimizer_is_refused_the_verdict_that_derives_from_its_own_ladder():
    """THE PROOF. Built through the store, not asserted against a hand-written chain."""
    with _Sandbox():
        _settings_sig, _band_sig, verdict_sig = _build_the_cycle()

        # Anyone else may read it. The product is not poisoned; it is poisoned FOR ONE CONSUMER.
        assert st.load("ground_truth_verdict", UID, verdict_sig,
                       consumer="closed_loop") is not None
        assert st.load("ground_truth_verdict", UID, verdict_sig, consumer=None) is not None

        raised = None
        try:
            st.load("ground_truth_verdict", UID, verdict_sig, consumer="stim_optimizer")
        except prov.SelfDerivedProduct as exc:
            raised = exc
        assert raised is not None, \
            "THE CYCLE WAS NOT REFUSED. Stim Optimizer just read a verdict computed from the " \
            "recordings its own exploration policy chose to collect."
        # The reason names the module and the offending input, so whoever hits it can act.
        text = str(raised)
        assert "stim_optimizer" in text
        assert "settings_stream" in text


def test_the_refusal_survives_one_more_hop_of_indirection():
    """A cycle is rarely one step. The chain is flattened, so depth must not defeat the check."""
    with _Sandbox():
        _s, _b, verdict_sig = _build_the_cycle()
        verdict_key = st.product_key("ground_truth_verdict", UID, verdict_sig)
        far_sig = ("far", 1)
        st.store("amplitude_effect_by_band", UID, far_sig, {"slope": np.array([0.1])},
                 writer="closed_loop", trigger="derived",
                 provenance=prov.flatten([
                     prov.entry(verdict_key, kind="ground_truth_verdict", writer="closed_loop",
                                chain=st.read_stamp("ground_truth_verdict", UID,
                                                    verdict_sig)["provenance"]),
                 ]))
        raised = None
        try:
            st.load("amplitude_effect_by_band", UID, far_sig, consumer="stim_optimizer")
        except prov.SelfDerivedProduct as exc:
            raised = exc
        assert raised is not None, "a two-hop cycle was not refused"


def test_a_refusal_is_not_a_miss_so_it_cannot_be_rebuilt_around():
    """A silent miss would rebuild the same self-derived product and hand it over anyway."""
    with _Sandbox():
        _s, _b, verdict_sig = _build_the_cycle()
        raised = False
        try:
            st.store_if_absent("ground_truth_verdict", UID, verdict_sig,
                               lambda: {"rebuilt": True}, consumer="stim_optimizer")
        except prov.SelfDerivedProduct:
            raised = True
        assert raised, "the refusal was swallowed and the product would have been rebuilt"


# --------------------------------------------------------------------------------------------
# the controls: a rule that refused everything would be useless
# --------------------------------------------------------------------------------------------

def test_a_verdict_built_only_from_device_recordings_is_released_to_stim_optimizer():
    """THE CONTROL. This is the case the whole design exists to serve."""
    with _Sandbox():
        tiles_key = st.product_key("raw_lsb_tiles", UID, ("t", 1))
        sig = ("clean", 1)
        st.store("ground_truth_verdict", UID, sig, {"route": "device_native"},
                 writer="closed_loop", trigger="page_request",
                 provenance=prov.flatten([prov.entry(tiles_key, kind="raw_lsb_tiles",
                                                     writer="biomarkers")]))
        got = st.load("ground_truth_verdict", UID, sig, consumer="stim_optimizer")
        assert got is not None and got["route"] == "device_native"


def test_the_recordings_themselves_are_never_a_cycle():
    """The tiles are built with no knowledge of any analysis choice, rating or exploration
    decision, so they cannot carry one module's judgement into another's input."""
    with _Sandbox():
        sig = ("t", 1)
        st.store("raw_lsb_tiles", UID, sig, {"tiles": np.zeros((2, 2))}, writer="biomarkers")
        for consumer in prov.MODULES:
            assert st.load("raw_lsb_tiles", UID, sig, consumer=consumer) is not None


def test_a_module_may_always_read_its_own_raw_kinds_back():
    """Biomarkers reads its own tiles constantly. Exempting raw kinds is what makes that legal."""
    with _Sandbox():
        tiles_key = st.product_key("raw_lsb_tiles", UID, ("t", 1))
        sig = ("bands", 2)
        st.store("biomarker_band_results", UID, sig, {"center_hz": np.array([23.44])},
                 writer="biomarkers",
                 provenance=prov.flatten([prov.entry(tiles_key, kind="raw_lsb_tiles",
                                                     writer="biomarkers")]))
        assert st.load("biomarker_band_results", UID, sig, consumer="biomarkers") is not None


# --------------------------------------------------------------------------------------------
# the rules themselves
# --------------------------------------------------------------------------------------------

def test_an_unknown_consumer_name_is_refused_rather_than_waved_through():
    """A typo in a call site would otherwise exempt itself from every rule here."""
    chain = prov.flatten([prov.entry(st.product_key("settings_stream", UID, ("s", 1)),
                                     kind="settings_stream", writer="stim_optimizer")])
    assert prov.refusal_for("stimoptimizer", chain) is not None       # missing underscore
    assert prov.refusal_for("stim_optimizer", chain) is not None      # the real refusal
    assert prov.refusal_for("biomarkers", chain) is None


def test_flattening_collapses_a_repeated_input_rather_than_counting_it_twice():
    """The same tile entry legitimately feeds several inputs."""
    tiles = st.product_key("raw_lsb_tiles", UID, ("t", 1))
    chain = prov.flatten([
        prov.entry("a/x/1", kind="inputs", writer="closed_loop",
                   chain=[prov.entry(tiles, kind="raw_lsb_tiles", writer="biomarkers")]),
        prov.entry("b/x/1", kind="response", writer="closed_loop",
                   chain=[prov.entry(tiles, kind="raw_lsb_tiles", writer="biomarkers")]),
    ])
    keys = [c["key"] for c in chain]
    assert keys.count(tiles) == 1
    assert set(keys) == {"a/x/1", "b/x/1", tiles}


def test_the_writers_of_a_chain_exclude_the_raw_inputs():
    chain = prov.flatten([
        prov.entry(st.product_key("raw_lsb_tiles", UID, ("t", 1)),
                   kind="raw_lsb_tiles", writer="biomarkers"),
        prov.entry(st.product_key("settings_stream", UID, ("s", 1)),
                   kind="settings_stream", writer="stim_optimizer"),
    ])
    assert prov.writers_in(chain) == {"stim_optimizer"}
