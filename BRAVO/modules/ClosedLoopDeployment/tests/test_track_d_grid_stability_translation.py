"""Track D, tasks D1 and D2(b): `adapter.band_sweep_grid_for_closed_loop`.

D1: reads the calibrated grid's existing stored entry as `consumer="closed_loop"` and must not
trip the self-derived-product refusal (decision 31) -- proven here by writing the entry through the
real store with the entry's real chain shape (raw tile + raw pain-report-snapshot inputs only, the
same chain `Biomarkers.bravo_service._band_sweep_signature` builds), then reading it back exactly
the way this module reads it.

D2(b): every row's `cross_setting_stability_raw` (Biomarkers' untranslated `_validate_band_core`
"stim" result) must come back translated to the honest four-valued answer, identical field for
field to calling `ClosedLoopDeployment.stability.finding_from_stability_result` directly on the
same raw result -- which is also exactly what `adapter.py`'s own single-candidate
`report_for_participant` snippet does inline for one point. This file is the equality proof for
that translation; `Biomarkers/tests/test_track_d_grid_export.py` is the equality proof for the raw
result Biomarkers computes in the first place. Together the two prove the whole column end to end
without either side importing the other in the wrong direction.
"""
import pathlib
import shutil
import sys
import tempfile

import pytest

MODULES_DIR = pathlib.Path(__file__).resolve().parents[2]
if str(MODULES_DIR) not in sys.path:
    sys.path.insert(0, str(MODULES_DIR))

from CacheStore import provenance as prov
from CacheStore import store as st
from ClosedLoopDeployment import adapter
from ClosedLoopDeployment import stability as stab

UID = "2e3c75c00d7f4f37b53a048d195f11da"


@pytest.fixture()
def sandbox():
    d = tempfile.mkdtemp(prefix="bravo_track_d_grid_test_")
    prev_dir = st.DIR_OVERRIDE
    prev_adapter_dir = adapter._SHARED_CACHE_DIR_OVERRIDE
    from CacheStore import ledger
    prev_ledger = ledger.ENABLED
    st.DIR_OVERRIDE = d
    adapter._SHARED_CACHE_DIR_OVERRIDE = d
    ledger.ENABLED = False
    st.clear()
    yield d
    st.DIR_OVERRIDE = prev_dir
    adapter._SHARED_CACHE_DIR_OVERRIDE = prev_adapter_dir
    ledger.ENABLED = prev_ledger
    shutil.rmtree(d, ignore_errors=True)


def _write_real_band_sweep_entry(*, stability_raw=None, sig=("sweep", 1), center_hz=12.5):
    """Mirrors `Biomarkers.bravo_service._band_sweep_signature`'s real chain shape: flattened from
    the raw tile entry and the raw pain-report snapshot, nothing else."""
    tiles_key = st.product_key("raw_lsb_tiles", UID, ("tiles", 1))
    st.store("raw_lsb_tiles", UID, ("tiles", 1), {"tiles": [[0.0]]}, writer="biomarkers")
    report_key = st.product_key("redcap_reports", UID, ("reports", 1))
    st.store("redcap_reports", UID, ("reports", 1), {"pain": [1.0]},
             writer="biomarkers", trigger="fresh_fetch", provenance=[])
    chain = prov.flatten([
        prov.entry(tiles_key, kind="raw_lsb_tiles", writer="biomarkers"),
        prov.entry(report_key, kind="redcap_reports", writer="biomarkers")])

    row = {"band_center_hz": float(center_hz), "r": 0.31}
    if stability_raw is not None:
        row["cross_setting_stability_raw"] = stability_raw
        row["device_rules_status"] = "not assessable from a band alone"
    payload = {
        "band_time_sweep": {
            "ONE_THREE_LEFT": {
                "band_width_hz": 5.0,
                "best_correlation_rows": [row],
                "best_auc_rows": [dict(row)],
            }
        },
    }
    st.store("biomarker_band_sweep", UID, sig, payload, writer="biomarkers",
             trigger="band_time_sweep", provenance=chain, fmt="pickle")
    return sig


# --------------------------------------------------------------------------------------------
# D1: the real read
# --------------------------------------------------------------------------------------------

def test_d1_reads_the_real_stored_grid_without_refusal(sandbox):
    _write_real_band_sweep_entry()
    got = adapter.band_sweep_grid_for_closed_loop(UID)
    assert got["available"] is True
    assert "ONE_THREE_LEFT" in got["band_time_sweep"]
    grid = got["band_time_sweep"]["ONE_THREE_LEFT"]
    assert grid["best_correlation_rows"][0]["band_center_hz"] == 12.5


def test_d1_reports_unavailable_with_no_stored_entry(sandbox):
    got = adapter.band_sweep_grid_for_closed_loop(UID)
    assert got["available"] is False
    assert got["reason"]


# --------------------------------------------------------------------------------------------
# D2(b): the translation equality proof
# --------------------------------------------------------------------------------------------

_MARGIN = stab.STABILITY_EQUIVALENCE_MARGIN_LOG_OR


def test_d2b_translated_answer_is_identical_to_calling_finding_from_stability_result_directly(sandbox):
    raw = {"available": True, "lrt_p": 0.72,
           "equivalence": {"verdict": "stable", "margin_log_or": _MARGIN,
                           "max_abs_diff_log_or": 0.12, "ci": [-0.10, 0.30],
                           "n_eras_compared": 3, "reason": "within the declared margin"},
           "n": 240, "n_clusters": 9, "era_counts": {"OFF": 40, "LOW": 100, "HIGH": 100}}
    _write_real_band_sweep_entry(stability_raw=raw)

    got = adapter.band_sweep_grid_for_closed_loop(UID)
    got_row = got["band_time_sweep"]["ONE_THREE_LEFT"]["best_correlation_rows"][0]

    want_finding = stab.finding_from_stability_result(raw, "ONE_THREE_LEFT", 12.5, band_width_hz=5.0)
    want = want_finding.as_payload()

    assert got_row["cross_setting_stability"] == want, (
        f"translated grid row diverged from calling finding_from_stability_result directly: "
        f"{got_row['cross_setting_stability']} != {want}")
    assert got_row["cross_setting_stability"]["answer"] == "behaves the same"
    # the raw form must not leak through once translated
    assert "cross_setting_stability_raw" not in got_row


def test_d2b_the_documented_disagreement_case_translates_to_cannot_tell(sandbox):
    """ONE_THREE_LEFT at 17.5 Hz is the case `adapter.py`'s own comment names: the old two-valued
    flag would read True/"stable" while the honest answer is "cannot tell".

    THE NUMBERS BELOW ARE MEASURED, NOT INVENTED. They were read off RCS08 on 2026-09-09 at the
    calibrated grid's own settings (5 Hz band, pain split into thirds): the interaction test does
    not reject at p = 0.372, and the interval on the largest between-era difference runs from -0.52
    to +0.89 -- straddling zero and wider than the declared margin of 0.69.

    WHY THE CASE MOVED, which is the reason this docstring says the settings out loud. The example
    was 12.5 Hz until 2026-09-09, when re-measuring found that point reads "behaves differently"
    (p = 0.0323) -- a third value, not the "cannot tell" the comment claimed. This test kept passing
    throughout, because it builds its raw result by hand rather than from live data, so it proved
    the translation rule and never the example. That is the right division of labour for a test that
    must run with no database, but it does mean the name is only true while somebody keeps the
    fixture matched to a real point, which is what this change does.
    """
    raw = {"available": True, "lrt_p": 0.3722536926038036,
           "equivalence": {"verdict": "inconclusive", "margin_log_or": _MARGIN,
                           "max_abs_diff_log_or": 0.8945, "ci": [-0.5194, 0.8945],
                           "n_eras_compared": 3, "pair": "LOW vs OFF",
                           "reason": "wider than the declared margin"},
           "n": 421, "n_clusters": 37, "era_counts": {"OFF": 92, "LOW": 75, "HIGH": 254}}
    _write_real_band_sweep_entry(stability_raw=raw, center_hz=17.5)
    got = adapter.band_sweep_grid_for_closed_loop(UID)
    row = got["band_time_sweep"]["ONE_THREE_LEFT"]["best_correlation_rows"][0]
    assert row["band_center_hz"] == 17.5, "the fixture no longer writes the point this test names"
    assert row["cross_setting_stability"]["answer"] == "cannot tell", (
        "collapsing this into \"behaves the same\" is the exact error stability.py exists to "
        "prevent")
    # The half that makes the example worth documenting: the retired flag would have said "stable".
    assert raw["lrt_p"] >= 0.05, (
        "the example only illustrates the disagreement while the interaction test does NOT reject "
        "-- if this fires, the anchor point has moved again and the comments naming it are stale")


def test_d2b_grid_row_never_carries_a_bare_stim_stable_boolean(sandbox):
    raw = {"available": True, "lrt_p": 0.72,
           "equivalence": {"verdict": "stable", "margin_log_or": _MARGIN,
                           "max_abs_diff_log_or": 0.12, "ci": [-0.10, 0.30],
                           "n_eras_compared": 3, "reason": "ok"},
           "n": 240, "n_clusters": 9, "era_counts": {}}
    _write_real_band_sweep_entry(stability_raw=raw)
    got = adapter.band_sweep_grid_for_closed_loop(UID)
    row = got["band_time_sweep"]["ONE_THREE_LEFT"]["best_correlation_rows"][0]
    assert "stim_stable" not in row
    assert "stable" not in row
    assert row["cross_setting_stability"]["answer"] in stab.ANSWERS


def test_d2b_a_row_with_no_raw_result_at_all_is_left_alone_not_faked(sandbox):
    """A grid built before Track D's opt-in flag was ever passed (`cross_setting_stability_raw`
    absent, the default) must not be given a fabricated translation, and
    `cross_setting_stability_included` must say so."""
    _write_real_band_sweep_entry(stability_raw=None)
    got = adapter.band_sweep_grid_for_closed_loop(UID)
    row = got["band_time_sweep"]["ONE_THREE_LEFT"]["best_correlation_rows"][0]
    assert "cross_setting_stability" not in row
    assert "cross_setting_stability_raw" not in row
    assert got["cross_setting_stability_included"] is False


def test_the_stability_grid_kind_matches_the_name_biomarkers_actually_writes():
    """`adapter.STABILITY_GRID_KIND` duplicates the kind name
    `Biomarkers.bravo_service.STABILITY_GRID_KIND` writes, instead of importing it -- importing
    `bravo_service` pulls in `Server.models`, which raises `AppRegistryNotReady` in this suite
    because it does not configure Django, and reading one extra column must not decide whether
    `band_sweep_grid_for_closed_loop` can run at all.

    A duplicated constant drifts unless something checks it, so this is that check: it reads the
    name out of the Biomarkers SOURCE rather than importing the module, so it needs no Django.
    A rename on either side fails here.
    """
    import pathlib
    import re

    here = pathlib.Path(__file__).resolve()
    bravo_service = here.parents[2] / "Biomarkers" / "bravo_service.py"
    assert bravo_service.is_file(), f"expected Biomarkers/bravo_service.py beside this module: {bravo_service}"

    found = re.search(r'^STABILITY_GRID_KIND\s*=\s*"([^"]+)"',
                      bravo_service.read_text(), re.MULTILINE)
    assert found, "bravo_service no longer defines STABILITY_GRID_KIND at module level"
    assert found.group(1) == adapter.STABILITY_GRID_KIND, (
        f"the writer's kind is {found.group(1)!r} but this module reads "
        f"{adapter.STABILITY_GRID_KIND!r} -- the stored stability grid would never be found")
