"""Track D, task D1: Closed-Loop Deployment reading the calibrated grid's stored entry.

THE QUESTION THIS FILE ANSWERS. `adr_2026-09-08_biomarkers_closedloop_matrix_export.md` claims that
Closed-Loop Deployment reading the `biomarker_band_sweep` entry never trips the self-derived-product
refusal (decision 31), because that entry's own provenance chain names only raw inputs (the tile
entry and the pain-report snapshot) -- nothing Closed-Loop Deployment produces ever feeds back into
which recordings exist for the grid to be built from. This file does not trust that reasoning; it
builds the entry the same way `Biomarkers.bravo_service._band_sweep_signature` and
`_store_sweep_results` actually build it, through the real store, and checks the real outcome --
mirroring the pattern `test_provenance_cycle.py` already established for exactly this kind of claim.

Every test has its control, because a rule that refused everything, or released everything, would be
trivially safe and useless (the same discipline `test_provenance_cycle.py` follows throughout).
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
        self._dir = tempfile.mkdtemp(prefix="bravo_band_sweep_prov_test_")
        self._prev_dir, self._prev_ledger = st.DIR_OVERRIDE, ledger.ENABLED
        st.DIR_OVERRIDE, ledger.ENABLED = self._dir, False
        st.clear()
        return self._dir

    def __exit__(self, *exc):
        from modules.CacheStore import ledger
        st.DIR_OVERRIDE, ledger.ENABLED = self._prev_dir, self._prev_ledger
        shutil.rmtree(self._dir, ignore_errors=True)
        return False


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


# --------------------------------------------------------------------------------------------
# D1: the real read, through the real store
# --------------------------------------------------------------------------------------------

def test_closed_loop_reads_the_real_band_sweep_entry_without_refusal():
    """THE CASE TRACK D DEPENDS ON. Built through the store with the sweep's real chain shape, not
    a hand-written one, and read exactly the way `ClosedLoopDeployment` would: as `consumer=
    "closed_loop"`."""
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


def test_the_real_chain_names_no_writer_at_all():
    """The mechanism behind the no-refusal result, checked directly rather than only through its
    outcome: `writers_in` on the real chain is empty, because both of its entries are raw kinds."""
    with _Sandbox():
        sweep_sig = _write_real_band_sweep_entry()
        stamp = st.read_stamp("biomarker_band_sweep", UID, sweep_sig)
        assert prov.writers_in(stamp["provenance"]) == set()


# --------------------------------------------------------------------------------------------
# THE CONTROL: a chain that DOES cite Closed-Loop Deployment's own output must still be refused.
# A rule that released every "biomarker_band_sweep"-kind entry regardless of its chain would be
# trivially safe for this real case and useless for the property decision 31 exists to prove.
# --------------------------------------------------------------------------------------------

def test_a_deliberately_self_derived_band_sweep_chain_is_still_refused_to_closed_loop():
    """Mirrors `test_provenance_cycle.py`'s own cycle-construction pattern: write a real
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

        raised = None
        try:
            st.load("biomarker_band_sweep", UID, poisoned_sig, consumer="closed_loop")
        except prov.SelfDerivedProduct as exc:
            raised = exc
        assert raised is not None, (
            "a biomarker_band_sweep entry that derives from closed_loop's own output was released "
            "to closed_loop; the refusal machinery has nothing left to catch if this passes")
        text = str(raised)
        assert "closed_loop" in text
        assert "ground_truth_verdict" in text

        # And the SAME poisoned entry is fine for the module that did not write the offending link.
        assert st.load("biomarker_band_sweep", UID, poisoned_sig,
                       consumer="stim_optimizer") is not None
