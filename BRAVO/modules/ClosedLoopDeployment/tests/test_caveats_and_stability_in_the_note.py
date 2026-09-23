"""Two things the Closed-Loop page owed its reader (panel D, 2026-09-22, items 5 and 3).

ITEM 5. The coherence note is where the page explains what the three edges together do and do not
show. The answer to "does this band mean the same thing about pain at every stimulation current?"
was computed, printed on its own card, and left out of that explanation, so a reader of the note
alone could take a coherent sign pattern for a settled finding while the band's meaning had never
been shown to hold still.

ITEM 3. The page prints numbers of two kinds: ones with an uncertainty interval and ones without.
Nothing said which was which. The caveats list is one flat list, assembled per request, naming
every number on the page that carries no interval today, plus the warnings the report already
holds and the point-sign caveat on the verdict.

Every case is pinned on the words and values produced, not on the shape of the answer.
"""
try:
    from modules.ClosedLoopDeployment import adapter as AD, consistency as C
except ImportError:                                              # pragma: no cover - host spelling
    from ClosedLoopDeployment import adapter as AD, consistency as C

from ClosedLoopDeployment.types import EdgeEstimate


def _edges():
    return (EdgeEstimate("E1", -7.31, (-47.3, 32.6), 0.72, 33, "run", 5),
            EdgeEstimate("E2", 0.059, (-0.08, 0.20), 0.45, 32069, "report_id", 32),
            EdgeEstimate("E3", -0.154, (-0.269, -0.039), 0.0086, 92, "epoch", 12))


# --- item 5: the stability answer inside the coherence note ------------------------------------
def test_cannot_tell_is_said_inside_the_coherence_note():
    e1, e2, e3 = _edges()
    rep = C.coherence_report(e1, e2, e3)
    out = C.note_with_stability(rep.note, {
        "answer": "cannot tell", "test_ran": True,
        "reason": "the interval on the largest difference is wider than the declared margin",
        "band_center_hz": 24.5,
    })
    assert "cannot tell" in out
    assert rep.note in out                       # the coherence wording itself is not disturbed
    assert "not a pass" in out.lower()


def test_behaves_differently_is_said_and_marked_as_the_serious_answer():
    e1, e2, e3 = _edges()
    note = C.note_with_stability(C.coherence_report(e1, e2, e3).note,
                                 {"answer": "behaves differently", "test_ran": True,
                                  "reason": "p 0.032, interval -1.238 to -0.104"})
    assert "behaves differently" in note
    assert "blocks nothing" in note.lower()


def test_a_missing_stability_answer_says_so_rather_than_saying_nothing():
    note = C.note_with_stability("base.", None)
    assert note.startswith("base.")
    assert "not tested" in note or "no answer" in note


def test_appending_twice_does_not_print_the_sentence_twice():
    """The adapter appends this after the report is serialised; a report re-serialised (a cached
    payload rebuilt, a test calling twice) must not grow a second copy."""
    once = C.note_with_stability("base.", {"answer": "cannot tell", "test_ran": True})
    twice = C.note_with_stability(once, {"answer": "cannot tell", "test_ran": True})
    assert once == twice


# --- item 3: the caveats list ------------------------------------------------------------------
def _payload():
    """A served payload of the shape `report_to_dict` produces, with the fields the list reads."""
    return {
        "available": True,
        "verdict": "supported (point signs only; 2 of 3 intervals span zero)",
        "verdict_detail": {
            "provisional": True, "n_edges_unestablished": 2, "n_edges": 3,
            "unestablished_edges": ["E1", "E2"],
            "warnings": ["D26: the two capture currents are 0.5 mA apart, which is less than the "
                         "rule asks for"],
        },
        "edges": {"E2": {"name": "E2", "estimate": 0.059, "ci": [-0.08, 0.20],
                         "adjusted": {"available": True, "auc": 0.52, "auc_low": 0.44,
                                      "auc_high": 0.61, "partial_r": -0.05,
                                      "adjusted_for": "amp_mA_Left"}}},
        "threshold": {"upper": 240.5, "lower": 190.5, "placement_rule": "record",
                      "warnings": [], "capture_verdicts": None},
        "prescription": {"mode": "dual", "fields": [
            {"parameter": "Onset", "value": 30.0, "units": "s", "origin": "record",
             "confidence": "medium"}]},
        "closed_loop_simulation": {"models": {"M0": {}, "M1": {}, "M3": {"intervals": {}}}},
    }


def test_every_caveat_names_its_card_and_its_severity():
    rows = AD.caveats_for_report(_payload())
    assert rows, "a live report always has at least the numbers printed without an interval"
    for r in rows:
        assert set(r) >= {"severity", "text", "card"}
        assert r["severity"] in ("high", "medium", "low")
        assert isinstance(r["card"], str) and r["card"]
        assert len(r["text"]) > 20


def test_the_report_s_own_warning_is_carried_word_for_word():
    rows = AD.caveats_for_report(_payload())
    texts = [r["text"] for r in rows]
    assert any("0.5 mA apart" in t for t in texts)


def test_the_point_sign_caveat_names_which_edges():
    rows = AD.caveats_for_report(_payload())
    hit = [r for r in rows if "point sign" in r["text"].lower()]
    assert hit and "E1" in hit[0]["text"] and "E2" in hit[0]["text"]
    assert hit[0]["severity"] == "high"


def test_the_thresholds_are_named_as_numbers_without_an_interval():
    rows = AD.caveats_for_report(_payload())
    hit = [r for r in rows if "240.5" in r["text"] or "threshold" in r["text"].lower()]
    assert hit, [r["text"] for r in rows]
    assert any("no interval" in r["text"].lower() or "without an interval" in r["text"].lower()
               for r in hit)


def test_the_replay_fractions_say_only_one_model_is_resampled():
    rows = AD.caveats_for_report(_payload())
    assert any("M3" in r["text"] for r in rows)


def test_a_report_that_is_not_available_produces_no_caveats_rather_than_raising():
    assert AD.caveats_for_report({"available": False}) == []
    assert AD.caveats_for_report(None) == []


def test_the_adjusted_reading_is_reported_as_a_caveat_on_the_plain_one():
    rows = AD.caveats_for_report(_payload())
    hit = [r for r in rows if "amp_mA_Left" in r["text"] or "current in force" in r["text"]]
    assert hit, [r["text"] for r in rows]
