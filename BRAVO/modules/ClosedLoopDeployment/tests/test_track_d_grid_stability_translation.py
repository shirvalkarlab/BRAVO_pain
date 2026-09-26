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
from Biomarkers.routines import sweep_settings

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


def _write_real_band_sweep_entry(*, stability_raw=None, sig=("sweep", 1), center_hz=12.5,
                                 request=None, tagged=True, sweep_key=None):
    """Mirrors `Biomarkers.bravo_service._band_sweep_signature`'s real chain shape: flattened from
    the raw tile entry and the raw pain-report snapshot, nothing else -- and, since decision 131,
    the sidecar tag of the settings the grid was built under (`extra["sweep_settings"]`), which is
    what the Closed-Loop reader matches on. `tagged=False` writes an entry from before the tag
    existed, which the reader must never serve."""
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
    if sweep_key is not None:
        # The block the real sweep stores with its grid (`sweep_key_block`), naming the grid's own key.
        payload["sweep_key"] = {"signature_key": sweep_key, "provenance": []}
    extra = ({"sweep_settings": sweep_settings.sweep_settings_tag_from_request(request or {}),
              "metric_label": "NRS (0–10)"} if tagged else None)
    st.store("biomarker_band_sweep", UID, sig, payload, writer="biomarkers",
             trigger="band_time_sweep", provenance=chain, fmt="pickle", extra=extra)
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


def test_d1_reports_unavailable_with_no_stored_entry(sandbox, monkeypatch):
    """No stored entry and nothing buildable: the reader says so rather than inventing a grid.

    Since decision 131 the reader BUILDS a grid through the Biomarkers sweep when nothing is stored
    under the requested settings, and that build reads the live record. In a process where Django
    happens to be set up (the one-job run of every suite on 2026-09-12) this test spent 53 s
    building RCS08's real grid; in the host suite's own process the Biomarkers service cannot
    import and the build raised at once. Either way the assertion below was about the environment,
    not about the reader. The builder is stood in for -- `_build_grid_through_biomarkers` is its
    own function for exactly that (its docstring) -- so the test asserts what its name says with
    no live record and no clock: an empty store and no build give `available: False` with a reason.
    """
    monkeypatch.setattr(adapter, "_build_grid_through_biomarkers", lambda uid, rd: None)
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
    """The kind name the Biomarkers writer files the stability grid under is the one this reader
    looks for. One home since 2026-09-26 (`Biomarkers/routines/sweep_settings.py`, Django-free);
    `test_the_stability_rule_version_matches_the_one_biomarkers_writes` pins that both sides take it
    from there. Kept as its own test so a rename of the kind itself is named when it fails."""
    try:
        from Biomarkers.routines import sweep_settings as ss
    except ImportError:                                          # pragma: no cover
        from modules.Biomarkers.routines import sweep_settings as ss
    assert ss.STABILITY_GRID_KIND == "biomarker_band_stability_grid"
    assert adapter.STABILITY_GRID_KIND is ss.STABILITY_GRID_KIND


# --------------------------------------------------------------------------------------------
# The stability column reads the answer for ITS OWN grid (2026-09-23)
# --------------------------------------------------------------------------------------------

def _raw(verdict, lrt_p, lo, hi):
    return {"available": True, "lrt_p": lrt_p,
            "equivalence": {"verdict": verdict, "margin_log_or": _MARGIN,
                            "max_abs_diff_log_or": max(abs(lo), abs(hi)), "ci": [lo, hi],
                            "n_eras_compared": 3, "reason": "fixture"},
            "n": 240, "n_clusters": 9, "era_counts": {"OFF": 40, "LOW": 100, "HIGH": 100}}


def _write_stability_entry(grid_key, raw, *, center_hz=12.5, tagged=True, rule_version=None,
                           rule_in_sidecar=True):
    """One stored stability answer, as `compute_and_store_stability_grid` writes it: filed under a
    key built on the grid's key, carrying the rule it was computed under in its payload
    (`rule_version`, as the real writer has always done), and naming that grid -- and, since
    2026-09-25, that rule -- in its sidecar (`extra`). `rule_in_sidecar=False` writes an answer from
    before the sidecar named its rule; `rule_version` defaults to the rule in force."""
    rule = adapter.STABILITY_GRID_RULE_VERSION if rule_version is None else rule_version
    sig = (adapter.STABILITY_GRID_KIND, rule, grid_key, 5.0, (("ONE_THREE_LEFT", float(center_hz)),))
    extra = None
    if tagged:
        extra = {"sweep_key": grid_key}
        if rule_in_sidecar:
            extra["rule_version"] = rule
    st.store(adapter.STABILITY_GRID_KIND, UID, sig,
             {"rule_version": rule, "points": {f"ONE_THREE_LEFT|{center_hz:g}": raw}},
             writer="biomarkers", trigger="stability_grid", provenance=[], extra=extra)


def test_the_stability_column_reads_the_answer_for_its_own_grid_not_the_newest(sandbox):
    """Found live on 2026-09-23. The stability answer depends on the pain score the grid was built
    for (on RCS08, 3,123 of 5,148 stored values differ between the NRS grid's answer and the Left
    Leg VAS grid's), and the store now keeps one answer per grid. This card read the NEWEST answer
    whatever grid it belonged to, so it could print another pain score's answer beside its own
    grid. It must read the answer filed for the grid it shows, even when another is newer."""
    _write_real_band_sweep_entry(sweep_key="grid-shown")
    _write_stability_entry("grid-shown", _raw("stable", 0.72, -0.10, 0.30))
    _write_stability_entry("grid-other-score", _raw("inconclusive", 0.01, -0.52, 0.89))
    got = adapter.band_sweep_grid_for_closed_loop(UID)
    row = got["band_time_sweep"]["ONE_THREE_LEFT"]["best_correlation_rows"][0]
    assert row["cross_setting_stability"]["answer"] == "behaves the same", (
        "the card printed the newest stored answer, which belongs to another grid")
    assert got["cross_setting_stability_from_store"] == 2


def test_with_no_answer_for_its_own_grid_the_column_says_not_tested_rather_than_borrowing(sandbox):
    """Only another grid's answer is stored, or one written before the sidecar named its grid:
    the rows carry no stability answer (the card's "not tested"), never a borrowed one."""
    _write_real_band_sweep_entry(sweep_key="grid-shown")
    _write_stability_entry("grid-other-score", _raw("stable", 0.72, -0.10, 0.30))
    _write_stability_entry("grid-shown", _raw("stable", 0.72, -0.10, 0.30), tagged=False)
    got = adapter.band_sweep_grid_for_closed_loop(UID)
    row = got["band_time_sweep"]["ONE_THREE_LEFT"]["best_correlation_rows"][0]
    assert "cross_setting_stability" not in row
    assert got["cross_setting_stability_from_store"] == 0


def test_the_card_reads_the_grid_with_the_clinic_sheet_switch_the_biomarkers_page_used(sandbox):
    """Found live on 2026-09-23 while proving the stability fix above. The Closed-Loop page sends
    the Biomarkers page's clinic-sheet switch with the grid settings (`useBandSweepGrid.js`), but
    the server's list of settings it passes on left it out, so with sheets ON on the Biomarkers
    page this card matched the sheets-OFF grid -- a different set of ratings, and not the grid the
    Biomarkers page shows (decision 131). Two grids stored, same score, the switch differing: the
    card must read the one the request names, in either direction."""
    off = {"SweepMetric": "left_leg_vas", "LabelMetric": "left_leg_vas"}
    on = dict(off, IncludeClinicSheetRatings="1")
    _write_real_band_sweep_entry(sig=("sweep", "sheets-on"), request=on, center_hz=22.5)
    _write_real_band_sweep_entry(sig=("sweep", "sheets-off"), request=off, center_hz=12.5)
    got = adapter.band_sweep_grid_for_closed_loop(UID, on)
    assert got["grid_settings"]["include_clinic_sheet_ratings"] is True
    assert got["band_time_sweep"]["ONE_THREE_LEFT"]["best_correlation_rows"][0]["band_center_hz"] == 22.5, (
        "the card read the sheets-off grid while the request asked for sheets on")
    got_off = adapter.band_sweep_grid_for_closed_loop(UID, off)
    assert got_off["band_time_sweep"]["ONE_THREE_LEFT"]["best_correlation_rows"][0]["band_center_hz"] == 12.5


# --------------------------------------------------------------------------------------------
# The stability column reads only an answer computed under the rule in force (2026-09-25)
# --------------------------------------------------------------------------------------------

_OLD_RULE = "v4_sheet_ratings_in_setup"


def test_the_stability_rule_version_matches_the_one_biomarkers_writes():
    """ONE HOME since 2026-09-26: the rule version (and the kind name) live in the Biomarkers
    module's Django-free settings file (`Biomarkers/routines/sweep_settings.py`), which the writer
    (`bravo_service`) and this reader both import, so there is no second copy to drift. Pinned two
    ways: this module's constant IS that one, and the writer's source takes it from there rather
    than writing its own string (read out of the source, since importing `bravo_service` needs
    Django)."""
    import pathlib
    import re

    try:
        from Biomarkers.routines import sweep_settings as ss
    except ImportError:                                          # pragma: no cover
        from modules.Biomarkers.routines import sweep_settings as ss
    assert adapter.STABILITY_GRID_RULE_VERSION == ss.STABILITY_GRID_RULE_VERSION
    assert adapter.STABILITY_GRID_KIND == ss.STABILITY_GRID_KIND
    here = pathlib.Path(__file__).resolve().parents[1]
    own = (here / "adapter.py").read_text()
    assert not re.search(r'^STABILITY_GRID_RULE_VERSION\s*=\s*"', own, re.MULTILINE), (
        "adapter.py writes its own copy of the stability rule version again")
    assert not re.search(r'^STABILITY_GRID_KIND\s*=\s*"', own, re.MULTILINE), (
        "adapter.py writes its own copy of the stability grid kind again")
    src = (here.parent / "Biomarkers" / "bravo_service.py").read_text()
    assert re.search(r'^STABILITY_GRID_RULE_VERSION\s*=\s*sweep_settings\.STABILITY_GRID_RULE_VERSION',
                     src, re.MULTILINE), "the writer no longer takes the rule version from its one home"
    assert re.search(r'^STABILITY_GRID_KIND\s*=\s*sweep_settings\.STABILITY_GRID_KIND',
                     src, re.MULTILINE), "the writer no longer takes the kind name from its one home"


def test_an_answer_computed_under_an_older_stability_rule_reads_not_tested(sandbox):
    """Found by the P-03 work on 2026-09-25. The stability rule moved (one pain report counted in one
    stimulation state, `v5_one_block_per_report`), and the Biomarkers page keys its answers on the
    rule, but this card matched on the grid's key alone, so it kept printing the old rule's answers
    until the background job rebuilt them. An answer from an older rule is never served: the row
    reads "not tested"."""
    _write_real_band_sweep_entry(sweep_key="grid-shown")
    _write_stability_entry("grid-shown", _raw("stable", 0.72, -0.10, 0.30),
                           rule_version=_OLD_RULE, rule_in_sidecar=False)
    got = adapter.band_sweep_grid_for_closed_loop(UID)
    row = got["band_time_sweep"]["ONE_THREE_LEFT"]["best_correlation_rows"][0]
    assert "cross_setting_stability" not in row, (
        "the card printed an answer computed under an older stability rule")
    assert got["cross_setting_stability_from_store"] == 0


def test_the_current_rules_answer_is_read_even_when_an_older_rules_answer_is_newer(sandbox):
    """Both rules' answers stored for the same grid, the older rule's written LAST (an old worker
    finishing after the new one, say): the card reads the answer under the rule in force."""
    _write_real_band_sweep_entry(sweep_key="grid-shown")
    _write_stability_entry("grid-shown", _raw("stable", 0.72, -0.10, 0.30))
    import time as _t
    _t.sleep(0.01)
    _write_stability_entry("grid-shown", _raw("inconclusive", 0.01, -0.52, 0.89),
                           rule_version=_OLD_RULE)
    got = adapter.band_sweep_grid_for_closed_loop(UID)
    row = got["band_time_sweep"]["ONE_THREE_LEFT"]["best_correlation_rows"][0]
    assert row["cross_setting_stability"]["answer"] == "behaves the same", (
        "the card read the older rule's answer because it was written last")


def test_an_answer_under_the_current_rule_written_before_the_sidecar_named_its_rule_is_still_read(sandbox):
    """Answers written under the rule in force before 2026-09-25 name their grid in the sidecar but
    not their rule. The Biomarkers side finds them by their exact key and will not rewrite them, so
    refusing them here would leave the card on "not tested" until the rule next moves. They are
    read by the rule their payload carries."""
    _write_real_band_sweep_entry(sweep_key="grid-shown")
    _write_stability_entry("grid-shown", _raw("stable", 0.72, -0.10, 0.30), rule_in_sidecar=False)
    got = adapter.band_sweep_grid_for_closed_loop(UID)
    row = got["band_time_sweep"]["ONE_THREE_LEFT"]["best_correlation_rows"][0]
    assert row["cross_setting_stability"]["answer"] == "behaves the same"
    assert got["cross_setting_stability_from_store"] == 2
