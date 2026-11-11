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

Merged here 2026-10-05: test_closed_loop_reads_band_sweep.py (its section is at the end).
"""
import numpy as np

from modules.CacheStore import provenance as prov
from modules.CacheStore import store as st
from modules.CacheStore.tests._helpers import UID, Sandbox as _Sandbox, refused as _refused


def _build_the_cycle():
    """Write the three products that close the loop, through the store, and return their keys.

    1. Stim Optimizer writes the ladder of settings it chose to explore.
    2. Biomarker exploration computes a per-band result FROM THAT LADDER.
    3. Closed-loop deployment computes the ground-truth verdict FROM THAT RESULT.

    Step 3's product now transitively derives from step 1, which Stim Optimizer wrote.
    """
    settings_sig = ("settings", 1)
    settings_key = st.product_key("exploration_ladder", UID, settings_sig)
    st.store("exploration_ladder", UID, settings_sig,
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
                 prov.entry(settings_key, kind="exploration_ladder", writer="stim_optimizer",
                            chain=st.read_stamp("exploration_ladder", UID, settings_sig)["provenance"]),
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
    """THE PROOF. Built through the store, not asserted against a hand-written chain. The refusal
    holds one more hop of indirection on (a cycle is rarely one step; the chain is flattened, so
    depth must not defeat the check), and it is not a miss, so `store_if_absent` cannot rebuild
    the same self-derived product around it and hand it over anyway. (Merged 2026-10-05 with
    `test_the_refusal_survives_one_more_hop_of_indirection` and
    `test_a_refusal_is_not_a_miss_so_it_cannot_be_rebuilt_around`, which built the same cycle.)"""
    with _Sandbox():
        _settings_sig, _band_sig, verdict_sig = _build_the_cycle()

        # Anyone else may read it. The product is not poisoned; it is poisoned FOR ONE CONSUMER.
        assert st.load("ground_truth_verdict", UID, verdict_sig,
                       consumer="closed_loop") is not None
        assert st.load("ground_truth_verdict", UID, verdict_sig, consumer=None) is not None

        raised = _refused(st.load, "ground_truth_verdict", UID, verdict_sig,
                          consumer="stim_optimizer")
        assert raised is not None, \
            "THE CYCLE WAS NOT REFUSED. Stim Optimizer just read a verdict computed from the " \
            "recordings its own exploration policy chose to collect."
        # The reason names the module and the offending input, so whoever hits it can act.
        text = str(raised)
        assert "stim_optimizer" in text
        assert "exploration_ladder" in text

        # one more hop
        verdict_key = st.product_key("ground_truth_verdict", UID, verdict_sig)
        far_sig = ("far", 1)
        st.store("amplitude_effect_by_band", UID, far_sig, {"slope": np.array([0.1])},
                 writer="closed_loop", trigger="derived",
                 provenance=prov.flatten([
                     prov.entry(verdict_key, kind="ground_truth_verdict", writer="closed_loop",
                                chain=st.read_stamp("ground_truth_verdict", UID,
                                                    verdict_sig)["provenance"]),
                 ]))
        assert _refused(st.load, "amplitude_effect_by_band", UID, far_sig,
                        consumer="stim_optimizer") is not None, "a two-hop cycle was not refused"

        # a refusal is not a miss
        assert _refused(st.store_if_absent, "ground_truth_verdict", UID, verdict_sig,
                        lambda: {"rebuilt": True}, consumer="stim_optimizer") is not None, \
            "the refusal was swallowed and the product would have been rebuilt"


# --------------------------------------------------------------------------------------------
# the controls: a rule that refused everything would be useless
# --------------------------------------------------------------------------------------------

def test_the_recordings_and_what_is_built_only_from_them_are_released():
    """THE CONTROL. A verdict built only from device recordings reaches Stim Optimizer: the case
    the whole design exists to serve. The tiles themselves reach every module (they are built with
    no knowledge of any analysis choice, rating or exploration decision, so they cannot carry one
    module's judgement into another's input), and Biomarkers reads back a result built from its
    own tiles, which exempting raw kinds is what makes legal. (Merged 2026-10-05 from
    `test_a_verdict_built_only_from_device_recordings_is_released_to_stim_optimizer`,
    `test_the_recordings_themselves_are_never_a_cycle` and
    `test_a_module_may_always_read_its_own_raw_kinds_back`.)"""
    with _Sandbox():
        tiles_sig = ("t", 1)
        tiles_key = st.product_key("raw_lsb_tiles", UID, tiles_sig)
        st.store("raw_lsb_tiles", UID, tiles_sig, {"tiles": np.zeros((2, 2))}, writer="biomarkers")
        for consumer in prov.MODULES:
            assert st.load("raw_lsb_tiles", UID, tiles_sig, consumer=consumer) is not None, consumer

        sig = ("clean", 1)
        st.store("ground_truth_verdict", UID, sig, {"route": "device_native"},
                 writer="closed_loop", trigger="page_request",
                 provenance=prov.flatten([prov.entry(tiles_key, kind="raw_lsb_tiles",
                                                     writer="biomarkers")]))
        got = st.load("ground_truth_verdict", UID, sig, consumer="stim_optimizer")
        assert got is not None and got["route"] == "device_native"

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
    chain = prov.flatten([prov.entry(st.product_key("exploration_ladder", UID, ("s", 1)),
                                     kind="exploration_ladder", writer="stim_optimizer")])
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
        prov.entry(st.product_key("exploration_ladder", UID, ("s", 1)),
                   kind="exploration_ladder", writer="stim_optimizer"),
    ])
    assert prov.writers_in(chain) == {"stim_optimizer"}


# --------------------------------------------------------------------------------------------
# the matched table is raw-derived: written by Stim Optimizer's code, embodying no choice of its
# --------------------------------------------------------------------------------------------

def test_the_matched_table_is_released_to_every_module_while_the_chosen_ladder_is_still_refused():
    """Track A step 5. `therapy_pain_matched` is a deterministic join of the programmed settings
    and the pain reports; a product derived from it must reach Stim Optimizer, or the table step 5
    exists to give it is refused to it. The CONTROL in the same test: a product derived from the
    ladder Stim Optimizer CHOSE (`exploration_ladder`) is refused as before."""
    with _Sandbox():
        settings_key = st.product_key("therapy_settings", UID, ("files", 1))
        report_key = st.product_key("redcap_reports", UID, ("reports", 1))
        matched_sig = ("matched", 1)
        st.store("therapy_pain_matched", UID, matched_sig, {"epoch": np.array([1.0, 2.0])},
                 writer="stim_optimizer", trigger="design_matrix",
                 provenance=prov.flatten([
                     prov.entry(settings_key, kind="therapy_settings", writer="stim_optimizer"),
                     prov.entry(report_key, kind="redcap_reports", writer="biomarkers")]))
        matched_key = st.product_key("therapy_pain_matched", UID, matched_sig)
        # the table itself, to its own writer
        assert st.load("therapy_pain_matched", UID, matched_sig,
                       consumer="stim_optimizer") is not None
        # a biomarker result derived from it, back to Stim Optimizer
        derived_sig = ("from_matched", 1)
        st.store("biomarker_band_results", UID, derived_sig, {"center_hz": np.array([23.44])},
                 writer="biomarkers", trigger="page_request",
                 provenance=prov.flatten([prov.entry(
                     matched_key, kind="therapy_pain_matched", writer="stim_optimizer",
                     chain=st.read_stamp("therapy_pain_matched", UID, matched_sig)["provenance"])]))
        assert st.load("biomarker_band_results", UID, derived_sig,
                       consumer="stim_optimizer") is not None, \
            "a result built from the matched table was refused to Stim Optimizer"
        assert prov.writers_in(st.read_stamp("biomarker_band_results", UID,
                                             derived_sig)["provenance"]) == set()

        # THE CONTROL: the same shape of chain, but from the ladder Stim Optimizer chose.
        ladder_key = st.product_key("exploration_ladder", UID, ("ladder", 1))
        chosen_sig = ("from_ladder", 1)
        st.store("biomarker_band_results", UID, chosen_sig, {"center_hz": np.array([23.44])},
                 writer="biomarkers", trigger="page_request",
                 provenance=prov.flatten([prov.entry(ladder_key, kind="exploration_ladder",
                                                     writer="stim_optimizer")]))
        assert _refused(st.load, "biomarker_band_results", UID, chosen_sig,
                        consumer="stim_optimizer") is not None, \
            "a result built from Stim Optimizer's own chosen ladder was released"


# --------------------------------------------------------------------------------------------
# Track D, task D1: Closed-Loop Deployment reading the calibrated grid's stored entry
# (was test_closed_loop_reads_band_sweep.py)
#
# `adr_2026-09-08_biomarkers_closedloop_matrix_export.md` claims that Closed-Loop Deployment
# reading the `biomarker_band_sweep` entry never trips the self-derived-product refusal (decision
# 31), because that entry's own provenance chain names only raw inputs (the tile entry and the
# pain-report snapshot) -- nothing Closed-Loop Deployment produces ever feeds back into which
# recordings exist for the grid to be built from. These tests do not trust that reasoning; they
# build the entry the way `Biomarkers.bravo_service._band_sweep_signature` and
# `_store_sweep_results` build it, through the real store, and check the real outcome, each with
# its control.
# --------------------------------------------------------------------------------------------

def _write_real_band_sweep_entry(tiles_sig=("tiles", 1), report_sig=("reports", 1),
                                 sweep_sig=("sweep", 1)):
    """Write a `biomarker_band_sweep` entry with EXACTLY the chain shape
    `Biomarkers.bravo_service._band_sweep_signature` builds: flattened from the tile entry
    (`raw_lsb_tiles`) and the pain-report snapshot (`redcap_reports`), both raw kinds. This is not a
    hand-picked convenient chain; it is the real shape, reproduced from that function's own body
    rather than assumed.
    """
    tiles_key = st.product_key("raw_lsb_tiles", UID, tiles_sig)
    st.store("raw_lsb_tiles", UID, tiles_sig, {"tiles": np.zeros((2, 2))}, writer="biomarkers")
    report_key = st.product_key("redcap_reports", UID, report_sig)
    st.store("redcap_reports", UID, report_sig, {"pain": np.array([1.0, 2.0])},
             writer="biomarkers", trigger="fresh_fetch", provenance=[])

    chain = prov.flatten([
        prov.entry(tiles_key, kind="raw_lsb_tiles", writer="biomarkers"),
        prov.entry(report_key, kind="redcap_reports", writer="biomarkers")])

    # A minimal but representative payload: one channel's full grid -- every band centre crossed
    # with every length of signal -- which is what task D1 needed to confirm was already present.
    grid_payload = {
        "band_time_sweep": {
            "ZERO_TWO_LEFT": {
                "center_freqs_hz": [8.5, 13.5, 18.5],
                "integration_seconds_requested": [30.0, 300.0],
                "correlation_grid": [[0.1, 0.2, 0.3], [0.15, 0.25, 0.35]],
                "auc_grid": [[0.5, 0.6, 0.7], [0.55, 0.65, 0.75]],
                "best_correlation_rows": [{"band_center_hz": 8.5, "r": 0.15},
                                          {"band_center_hz": 13.5, "r": 0.25},
                                          {"band_center_hz": 18.5, "r": 0.35}],
                "best_auc_rows": [{"band_center_hz": 8.5, "auc": 0.55},
                                  {"band_center_hz": 13.5, "auc": 0.65},
                                  {"band_center_hz": 18.5, "auc": 0.75}],
            }
        },
        "served_from_store": False,
    }
    st.store("biomarker_band_sweep", UID, sweep_sig, grid_payload,
             writer="biomarkers", trigger="band_time_sweep", provenance=chain, fmt="pickle")
    return sweep_sig


def test_closed_loop_reads_the_real_band_sweep_entry_without_refusal():
    """THE CASE TRACK D DEPENDS ON. Built through the store with the sweep's real chain shape, not
    a hand-written one, and read exactly the way `ClosedLoopDeployment` would: as `consumer=
    "closed_loop"`. The mechanism is checked directly too, not only through its outcome:
    `writers_in` on the real chain is empty, because both of its entries are raw kinds. (Merged
    2026-10-05 with `test_the_real_chain_names_no_writer_at_all`.)"""
    with _Sandbox():
        sweep_sig = _write_real_band_sweep_entry()
        got = st.load("biomarker_band_sweep", UID, sweep_sig, consumer="closed_loop")
        assert got is not None
        grid = got["band_time_sweep"]["ZERO_TWO_LEFT"]
        # The full grid -- every band centre crossed with every length of signal -- is already
        # inside the entry `Biomarkers.bravo_service._store_sweep_results` writes; Track D did not
        # need to add a field for it.
        assert len(grid["center_freqs_hz"]) == 3
        assert len(grid["correlation_grid"]) == 2 and len(grid["correlation_grid"][0]) == 3
        assert len(grid["best_correlation_rows"]) == 3
        assert len(grid["best_auc_rows"]) == 3

        # Every other module may read it too, for the same reason: the chain names only raw kinds.
        assert st.load("biomarker_band_sweep", UID, sweep_sig, consumer="biomarkers") is not None
        assert st.load("biomarker_band_sweep", UID, sweep_sig,
                       consumer="stim_optimizer") is not None
        stamp = st.read_stamp("biomarker_band_sweep", UID, sweep_sig)
        assert prov.writers_in(stamp["provenance"]) == set()


# --------------------------------------------------------------------------------------------
# THE CONTROL: a chain that DOES cite Closed-Loop Deployment's own output must still be refused.
# A rule that released every "biomarker_band_sweep"-kind entry regardless of its chain would be
# trivially safe for this real case and useless for the property decision 31 exists to prove.
# --------------------------------------------------------------------------------------------

def test_a_deliberately_self_derived_band_sweep_chain_is_still_refused_to_closed_loop():
    """Mirrors this file's own cycle-construction pattern: write a real
    `ground_truth_verdict` (Closed-Loop Deployment's own kind), and construct a `biomarker_band_sweep`
    entry whose chain derives from it. Nothing in this project's real wiring builds such a chain
    today (the ADR's whole argument is that it cannot), but the refusal machinery must still catch
    it if it ever did -- otherwise the "no refusal" result proven above would mean nothing."""
    with _Sandbox():
        verdict_sig = ("verdict", 1)
        st.store("ground_truth_verdict", UID, verdict_sig,
                 {"route": "device_native", "n_windows": 6},
                 writer="closed_loop", trigger="page_request",
                 provenance=prov.flatten([prov.entry(
                     st.product_key("raw_lsb_tiles", UID, ("t", 1)),
                     kind="raw_lsb_tiles", writer="biomarkers")]))
        verdict_key = st.product_key("ground_truth_verdict", UID, verdict_sig)

        poisoned_sig = ("poisoned_sweep", 1)
        st.store("biomarker_band_sweep", UID, poisoned_sig,
                 {"band_time_sweep": {"ZERO_TWO_LEFT": {"best_correlation_rows": []}}},
                 writer="biomarkers", trigger="band_time_sweep",
                 provenance=prov.flatten([
                     prov.entry(verdict_key, kind="ground_truth_verdict", writer="closed_loop",
                                chain=st.read_stamp("ground_truth_verdict", UID,
                                                    verdict_sig)["provenance"])]))

        raised = _refused(st.load, "biomarker_band_sweep", UID, poisoned_sig, consumer="closed_loop")
        assert raised is not None, (
            "a biomarker_band_sweep entry that derives from closed_loop's own output was released "
            "to closed_loop; the refusal machinery has nothing left to catch if this passes")
        text = str(raised)
        assert "closed_loop" in text
        assert "ground_truth_verdict" in text

        # And the SAME poisoned entry is fine for the module that did not write the offending link.
        assert st.load("biomarker_band_sweep", UID, poisoned_sig,
                       consumer="stim_optimizer") is not None
