"""B3 of the 2026-09-15 review (decision 185): the cross-setting stability answer -- "does this band
still track pain under a different stimulation setting?" -- computed in the background for every
stored grid (decisions 96-98) and drawn only on the Closed-Loop page's "Choose a band" card, now
reaches the Biomarkers grid's own headline rows. Read from the store under THIS grid's own key
(the same key the background run wrote), never the newest grid of any settings.

The answer words are the Closed-Loop card's (`DecodeCommon.stability_answer`, one home): "behaves
the same" / "behaves differently" / "cannot tell" / "not tested".
"""
import os
import sys
import tempfile

_BRAVO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
sys.path.insert(0, _BRAVO_ROOT)
sys.path.insert(0, os.path.join(_BRAVO_ROOT, "modules"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "BRAVO.settings")
import django                                            # noqa: E402
django.setup()

from Biomarkers import bravo_service as bs               # noqa: E402
from CacheStore import store as cs                      # noqa: E402
from DecodeCommon import stability_answer as SA         # noqa: E402


def _grid(points):
    rows = [{"band_center_hz": f, "pearson_r": 0.1} for _, f in points]
    return {"band_time_sweep": {"L": {"center_freqs_hz": [f for _, f in points],
                                      "best_correlation_rows": [dict(r) for r in rows],
                                      "best_auc_rows": [dict(r) for r in rows]}},
            "band_width_hz": 5.0, "label_metric": "nrs",
            "sweep_key": {"signature_key": "sweepkeyone", "provenance": []}}


def test_the_answer_words_have_one_home_and_map_the_biomarkers_verdicts():
    assert SA.answer_for_verdict("stable") == "behaves the same"
    assert SA.answer_for_verdict("stim-dependent") == "behaves differently"
    assert SA.answer_for_verdict("inconclusive") == "cannot tell"
    assert SA.answer_for_verdict("anything else") is None
    assert SA.ANSWERS == ("behaves the same", "behaves differently", "cannot tell", "not tested")


def test_rows_carry_the_stored_answer_for_this_grids_own_key_and_not_tested_where_absent():
    was = bs._SHARED_CACHE_DIR_OVERRIDE
    tmp = tempfile.mkdtemp(prefix="stability_rows_")
    try:
        bs._SHARED_CACHE_DIR_OVERRIDE = tmp
        points = [("L", 8.5), ("L", 9.5), ("L", 10.5)]
        stored = {"kind": bs.STABILITY_GRID_KIND, "rule_version": bs.STABILITY_GRID_RULE_VERSION,
                  "participant_uid": "abc", "band_width_hz": 5.0, "label_metric": "nrs",
                  "n_points_requested": 3,
                  "points": {"L|8.5": {"available": True, "lrt_p": 0.03,
                                       "stability_verdict": "stim-dependent",
                                       "equivalence": {"verdict": "stim-dependent", "reason": "the interaction test rejects"}},
                             "L|9.5": {"available": True, "lrt_p": 0.4,
                                       "stability_verdict": "inconclusive",
                                       "equivalence": {"verdict": "inconclusive", "reason": "interval wider than the margin"}},
                             "L|10.5": {"available": False, "reason": "too few eras"}}}
        sig = bs._stability_grid_sig_tuple("sweepkeyone", band_width_hz=5.0, points=points)
        assert cs.store(bs.STABILITY_GRID_KIND, "abc", sig, stored, writer="biomarkers",
                        trigger="test", provenance=[], root=tmp)

        out = bs.attach_stored_stability_answers(_grid(points), "abc")
        assert out["cross_setting_stability_from_store"] == 3
        for key in ("best_correlation_rows", "best_auc_rows"):
            rows = out["band_time_sweep"]["L"][key]
            by = {r["band_center_hz"]: r["cross_setting_stability"] for r in rows}
            assert by[8.5]["answer"] == "behaves differently" and by[8.5]["p_value"] == 0.03
            assert by[9.5]["answer"] == "cannot tell"
            assert by[10.5]["answer"] == "not tested" and "too few eras" in by[10.5]["reason"]
            assert all(r["cross_setting_stability"]["answers_possible"] == list(SA.ANSWERS) for r in rows)

        # A grid under ANOTHER key gets nothing from this entry: every row says not yet computed.
        other = _grid(points); other["sweep_key"] = {"signature_key": "sweepkeytwo", "provenance": []}
        out2 = bs.attach_stored_stability_answers(other, "abc")
        assert out2["cross_setting_stability_from_store"] == 0
        for r in out2["band_time_sweep"]["L"]["best_correlation_rows"]:
            assert r["cross_setting_stability"]["answer"] == "not tested"
            assert "not been computed" in r["cross_setting_stability"]["reason"]
        print("OK stability answers reach the Biomarkers rows under this grid's own key")
    finally:
        bs._SHARED_CACHE_DIR_OVERRIDE = was


def test_the_closed_loop_translation_uses_the_same_words():
    """The Closed-Loop card's translation (`ClosedLoopDeployment.stability`) and the Biomarkers
    rows must never disagree about a word: both read `DecodeCommon.stability_answer`."""
    try:
        from ClosedLoopDeployment import stability as CLS
    except ImportError:
        from modules.ClosedLoopDeployment import stability as CLS
    assert CLS.ANSWERS == SA.ANSWERS
    # one home: the Closed-Loop module carries no second copy of the words or the verdict map
    import inspect
    src = inspect.getsource(CLS)
    assert "stability_answer import" in src
    assert '"stable": "behaves the same"' not in src, "the verdict map is typed twice"
    assert 'ANSWERS = ("behaves' not in src, "the answer words are typed twice"
    raw = {"available": True, "lrt_p": 0.03, "stability_verdict": "stim-dependent",
           "equivalence": {"verdict": "stim-dependent", "reason": "r", "margin_log_or": CLS.STABILITY_EQUIVALENCE_MARGIN_LOG_OR}}
    assert CLS.finding_from_stability_result(raw, "L", 8.5).answer == SA.answer_for_verdict("stim-dependent")
