"""The harmonic rule on the readiness screen is a WARNING, never a refusal (the PI, 2026-09-21:
"put a warning for the harmonic rule, but don't make it blocking").

Decision 199 left the titration card's harmonic rule (a band centre within 2.5 Hz of |250 - rate|,
rate/2, rate/4 or 3 rate/4 measures the stimulator, not the brain; decision 146) as information
beside each row and asked the PI whether the screen should apply it. His ruling: warn. So a row
that is usable ONLY through qualifying bands sitting on a stimulator harmonic carries a warning
sentence and a flag, the screen's summary counts such rows and says whether the selected best is
one of them, and `deployable` is never changed by any of it.
"""
import ast
import inspect

from StimOptimizer import bravo_service as BS
from StimOptimizer import titration_plan as TP


def test_usable_only_through_harmonic_bands_is_a_warning_not_a_refusal():
    # 27.5 Hz is half of 55 Hz: the one qualifying band is on a harmonic.
    h = TP.harmonic_warning(55.0, [27.5], usable=True)
    assert h["only_through_harmonics"] is True
    assert h["near_hz"] == [27.5] and h["clear_hz"] == []
    assert "half the rate" in h["notes"]["27.5"]
    w = h["warning"]
    assert "only through" in w and "27.5" in w and "stimulator" in w
    assert "usable" in w and "not" in w.lower()            # says it stays usable, not refused
    assert "2026-09-21" in w                               # the ruling's date


def test_a_clear_band_beside_a_harmonic_one_is_a_note_not_a_warning():
    h = TP.harmonic_warning(55.0, [24.5, 27.5], usable=True)
    assert h["only_through_harmonics"] is False
    assert h["near_hz"] == [27.5] and h["clear_hz"] == [24.5]
    assert h["warning"] is None
    assert "24.5" in h["note"] and "clear" in h["note"]


def test_a_cell_that_is_not_usable_gets_no_warning_and_no_false_clear_band():
    """Caught live on RCS08 (rule 11): a refused cell whose qualifying bands all sit on a harmonic
    was given the note "... Hz is clear" with no band named. The note must not claim a clear band
    that does not exist."""
    h = TP.harmonic_warning(55.0, [27.5], usable=False)
    assert h["only_through_harmonics"] is False and h["warning"] is None
    assert h["near_hz"] == [27.5] and h["clear_hz"] == []  # the information is still there
    assert "is clear" not in h["note"]
    assert "every qualifying band" in h["note"] and "27.5" in h["note"] and "not usable" in h["note"]


def test_no_qualifying_band_and_a_rate_with_every_centre_clear_give_nothing():
    assert TP.harmonic_warning(55.0, [], usable=True)["warning"] is None
    h = TP.harmonic_warning(145.0, [24.5, 27.5], usable=True)
    assert h["near_hz"] == [] and h["only_through_harmonics"] is False and h["warning"] is None


def test_the_row_fields_and_the_screen_summary():
    cells = [
        {"rate_hz": 55.0, "qualifying_centers_hz": [27.5], "deployable": True, "channel": "A", "hemisphere": "Left"},
        {"rate_hz": 55.0, "qualifying_centers_hz": [24.5, 27.5], "deployable": True, "channel": "B"},
        {"rate_hz": 110.0, "qualifying_centers_hz": [27.5], "deployable": False, "channel": "C"},
        {"rate_hz": 145.0, "qualifying_centers_hz": [24.5], "deployable": True, "channel": "D"},
    ]
    summary = BS.attach_harmonic_warnings(cells, selected={"channel": "A", "hemisphere": "Left", "rate_hz": 55.0})
    by = {c["channel"]: c for c in cells}
    # the row fields decision 199 added are unchanged in name and meaning
    assert by["A"]["qualifying_near_stim_harmonic_hz"] == [27.5]
    assert by["B"]["qualifying_clear_of_stim_harmonics_hz"] == [24.5]
    assert by["C"]["qualifying_near_stim_harmonic_hz"] == [27.5]      # 110/4
    # the new flag and sentence
    assert by["A"]["harmonic_only"] is True and by["A"]["harmonic_warning"]
    assert by["B"]["harmonic_only"] is False and by["B"]["harmonic_warning"] is None
    assert by["C"]["harmonic_only"] is False                          # not usable: nothing to warn about
    assert by["D"]["harmonic_only"] is False and by["D"]["harmonic_warning"] is None
    # nothing touched `deployable`
    assert [c["deployable"] for c in cells] == [True, True, False, True]
    # the summary
    assert summary["n_usable"] == 3
    assert summary["n_usable_only_through_harmonics"] == 1
    assert summary["cells_only_through_harmonics"] == [{"channel": "A", "hemisphere": "Left", "rate_hz": 55.0}]
    assert summary["selected_only_through_harmonics"] is True
    assert "1 of 3" in summary["sentence"] and "warning" in summary["sentence"].lower()
    assert "best" in summary["sentence"]                              # names that the selected one is affected


def test_the_summary_is_quiet_when_no_usable_cell_depends_on_a_harmonic():
    cells = [{"rate_hz": 145.0, "qualifying_centers_hz": [24.5], "deployable": True, "channel": "D"}]
    summary = BS.attach_harmonic_warnings(cells, selected=None)
    assert summary["n_usable_only_through_harmonics"] == 0 and summary["sentence"] is None
    assert summary["selected_only_through_harmonics"] is False


def test_the_readiness_screen_never_reassigns_deployable_from_the_harmonic_information():
    """Read off the source: inside the readiness assembly and the helper, `deployable` is read,
    never written, so the warning cannot become a refusal by accident."""
    for fn in (BS.closed_loop_readiness, BS.attach_harmonic_warnings):
        src = inspect.getsource(fn)
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for t in node.targets:
                    if isinstance(t, ast.Subscript) and isinstance(t.slice, ast.Constant):
                        assert t.slice.value != "deployable", "deployable is assigned in " + fn.__name__
