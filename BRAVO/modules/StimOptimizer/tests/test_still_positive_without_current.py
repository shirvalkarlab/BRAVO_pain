"""The readiness table says, per band that rises with pain, whether it still does once the
stimulation current in force is taken out (panel C item 6, with the PI's ruling of 2026-09-22).

WHY. Decision 199's one-band rule counts a band as rising with pain off the stored Biomarkers grid.
On this participant's left lead every such band also rests on the current the stimulator was
delivering (decisions 232 and 234). The PI ruled (decision 233, answer 2) that "supported" does NOT
require a band to survive that adjustment: the adjusted value is reported beside the plain one and
never re-selects a band or moves a verdict. This is that report, on the readiness table.

WHERE THE ADJUSTED VALUE COMES FROM, AND WHERE IT MUST NOT. Decision 234 built the adjusted grid
behind a switch on the Biomarkers page. Building one here, on every Stim Optimizer request, would
put a whole grid build in front of the page. So the value is READ from a stored adjusted grid under
the same settings, and when none is stored the answer is "not assessed", with the reason and what
would produce one -- never a build, and never a guess.

THREE ANSWERS, NEVER TWO: yes, no, not assessed. A band whose adjusted value is missing, or whose
stored adjusted grid was built on a different record from the plain one, is "not assessed".
"""
import pathlib
import shutil
import sys
import tempfile

import pytest

MODULES_DIR = pathlib.Path(__file__).resolve().parents[2]
if str(MODULES_DIR) not in sys.path:
    sys.path.insert(0, str(MODULES_DIR))

from CacheStore import provenance as prov                                   # noqa: E402
from CacheStore import store as st                                          # noqa: E402
from ClosedLoopDeployment import adapter                                     # noqa: E402
from Biomarkers.routines import sweep_settings                               # noqa: E402
from StimOptimizer.routines import pain_relationship as PR                   # noqa: E402

UID = "2e3c75c00d7f4f37b53a048d195f11da"
CH = "ZERO_THREE_LEFT"


def _row(c, r, lo, *, r_adj="absent"):
    row = {"band_center_hz": c, "pearson_r": r, "pearson_r_low": lo,
           "pearson_r_high": r + 0.2, "answer": "not resolved"}
    if r_adj != "absent":
        row["pearson_r_adjusted"] = r_adj
    return row


def _grid(rows, *, adjusted=False):
    g = {"available": True, "band_time_sweep": {CH: {"best_correlation_rows": rows}},
         "grid_settings": {"sweep_metric": "nrs", "stored_utc": "2026-09-23T00:00:00Z"}}
    if adjusted:
        g["covariate_adjustment"] = {"available": True}
    return g


PLAIN = _grid([_row(24.5, 0.207, 0.05), _row(25.5, 0.18, 0.02), _row(12.5, -0.30, -0.45)])


# --- the per-band answer ------------------------------------------------------------------
def test_a_band_that_stays_positive_reads_yes_and_carries_both_values():
    adj = _grid([_row(24.5, 0.207, 0.05, r_adj=0.113), _row(25.5, 0.18, 0.02, r_adj=0.02),
                 _row(12.5, -0.30, -0.45, r_adj=-0.2)], adjusted=True)
    out = PR.still_positive_without_current(PLAIN, adj)
    b = {x["center_hz"]: x for x in out["by_channel"][CH]}
    assert set(b) == {24.5, 25.5}, "only bands that rise with pain are asked about"
    assert b[24.5]["answer"] == "yes"
    assert b[24.5]["pearson_r"] == 0.207 and b[24.5]["pearson_r_adjusted"] == 0.113


def test_a_band_that_falls_to_zero_or_below_reads_no():
    adj = _grid([_row(24.5, 0.207, 0.05, r_adj=-0.01), _row(25.5, 0.18, 0.02, r_adj=0.0)],
                adjusted=True)
    b = {x["center_hz"]: x for x in PR.still_positive_without_current(PLAIN, adj)["by_channel"][CH]}
    assert b[24.5]["answer"] == "no"
    assert b[25.5]["answer"] == "no", "zero is not positive"


def test_no_stored_adjusted_grid_is_not_assessed_and_says_what_would_produce_one():
    out = PR.still_positive_without_current(PLAIN, None)
    assert out["available"] is False
    for x in out["by_channel"][CH]:
        assert x["answer"] == "not assessed" and x["pearson_r_adjusted"] is None
    assert "switch" in out["reason"].lower()


def test_an_adjusted_grid_built_on_a_different_record_is_not_used():
    """The plain value under the adjusted grid differs from the plain grid's own, so the two were
    built on different ratings or recordings and the adjusted number cannot be read against it."""
    adj = _grid([_row(24.5, 0.25, 0.05, r_adj=0.113), _row(25.5, 0.18, 0.02, r_adj=0.02)],
                adjusted=True)
    b = {x["center_hz"]: x for x in PR.still_positive_without_current(PLAIN, adj)["by_channel"][CH]}
    assert b[24.5]["answer"] == "not assessed"
    assert "different record" in b[24.5]["why"]
    assert b[25.5]["answer"] == "yes"


def test_a_row_with_no_adjusted_value_is_not_assessed():
    adj = _grid([_row(24.5, 0.207, 0.05, r_adj=None), _row(25.5, 0.18, 0.02)], adjusted=True)
    b = {x["center_hz"]: x for x in PR.still_positive_without_current(PLAIN, adj)["by_channel"][CH]}
    assert b[24.5]["answer"] == "not assessed"
    assert b[25.5]["answer"] == "not assessed"


def test_the_answer_says_it_has_no_interval_and_moves_no_verdict():
    adj = _grid([_row(24.5, 0.207, 0.05, r_adj=0.113), _row(25.5, 0.18, 0.02, r_adj=0.02)],
                adjusted=True)
    out = PR.still_positive_without_current(PLAIN, adj)
    s = out["note"].lower()
    assert "no interval" in s
    assert "moves no verdict" in s or "never" in s


def test_the_plain_rule_is_untouched_by_the_adjusted_grid():
    """Decision 233 answer 2: the qualifying bands are the plain grid's, whatever the adjustment."""
    adj = _grid([_row(24.5, 0.207, 0.05, r_adj=-0.5), _row(25.5, 0.18, 0.02, r_adj=-0.5)],
                adjusted=True)
    assert PR.pain_positive_centers_by_channel(PLAIN) == {CH: frozenset({24.5, 25.5})}
    PR.still_positive_without_current(PLAIN, adj)
    assert PR.pain_positive_centers_by_channel(PLAIN) == {CH: frozenset({24.5, 25.5})}


# --- reading a stored adjusted grid, read-only --------------------------------------------
@pytest.fixture
def sandbox():
    d = tempfile.mkdtemp(prefix="bravo_adjusted_grid_")
    prev_store, prev_adapter = st.DIR_OVERRIDE, adapter._SHARED_CACHE_DIR_OVERRIDE
    from CacheStore import ledger
    prev_ledger = ledger.ENABLED
    ledger.ENABLED = False
    st.DIR_OVERRIDE = d
    adapter._SHARED_CACHE_DIR_OVERRIDE = d
    try:
        yield d
    finally:
        st.clear()                       # while the override still points at the sandbox
        st.DIR_OVERRIDE = prev_store
        adapter._SHARED_CACHE_DIR_OVERRIDE = prev_adapter
        ledger.ENABLED = prev_ledger
        shutil.rmtree(d, ignore_errors=True)


def _write(sig, grid, *, adjusted, request=None):
    tiles_key = st.product_key("raw_lsb_tiles", UID, ("tiles", 1))
    st.store("raw_lsb_tiles", UID, ("tiles", 1), {"tiles": [[0.0]]}, writer="biomarkers")
    chain = prov.flatten([prov.entry(tiles_key, kind="raw_lsb_tiles", writer="biomarkers")])
    extra = {"sweep_settings": sweep_settings.sweep_settings_tag_from_request(request or {}),
             "adjust_for_stim_current": bool(adjusted),
             # the rule in force on the sidecar, as the Biomarkers writer stamps it (decision 317)
             "rule_version": sweep_settings.GRID_RULE_VERSION}
    assert st.store("biomarker_band_sweep", UID, sig, grid, writer="biomarkers",
                    trigger="band_time_sweep", provenance=chain, fmt="pickle", extra=extra)


def test_the_reader_returns_only_a_grid_stored_with_the_switch_on(sandbox, monkeypatch):
    monkeypatch.setattr(adapter, "_build_grid_through_biomarkers",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("must never build")))
    _write(("sweep", "adj"), _grid([_row(24.5, 0.207, 0.05, r_adj=0.1)], adjusted=True),
           adjusted=True)
    _write(("sweep", "plain"), PLAIN, adjusted=False)                   # newest, plain
    got = adapter.stored_current_adjusted_grid(UID, {}, consumer="stim_optimizer")
    assert got["available"] is True
    rows = got["band_time_sweep"][CH]["best_correlation_rows"]
    assert rows[0]["pearson_r_adjusted"] == 0.1
    assert got["stamp"]["signature_key"]


def test_the_reader_says_not_stored_rather_than_building(sandbox, monkeypatch):
    monkeypatch.setattr(adapter, "_build_grid_through_biomarkers",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("must never build")))
    _write(("sweep", "plain"), PLAIN, adjusted=False)
    got = adapter.stored_current_adjusted_grid(UID, {}, consumer="stim_optimizer")
    assert got["available"] is False
    assert "switch" in got["reason"].lower()


def test_the_reader_matches_the_settings_as_well_as_the_switch(sandbox):
    _write(("sweep", "vas_adj"), _grid([_row(24.5, 0.2, 0.05, r_adj=0.1)], adjusted=True),
           adjusted=True, request={"SweepMetric": "vas"})
    got = adapter.stored_current_adjusted_grid(UID, {"SweepMetric": "nrs"}, consumer="stim_optimizer")
    assert got["available"] is False


# --- the response key ---------------------------------------------------------------------
def test_the_response_key_is_unchanged_without_an_adjusted_grid_and_moves_with_one():
    from StimOptimizer import bravo_service as SVC
    plain = {"store_key": "biomarker_band_sweep:abc"}
    assert SVC._pain_relationship_key(None, plain) == ("grid", "biomarker_band_sweep:abc")
    none_adj = dict(plain, still_positive_without_current={"store_key": None})
    assert SVC._pain_relationship_key(None, none_adj) == ("grid", "biomarker_band_sweep:abc")
    with_adj = dict(plain, still_positive_without_current={"store_key": "biomarker_band_sweep:def"})
    assert SVC._pain_relationship_key(None, with_adj) == (
        "grid", "biomarker_band_sweep:abc", "adjusted", "biomarker_band_sweep:def")
