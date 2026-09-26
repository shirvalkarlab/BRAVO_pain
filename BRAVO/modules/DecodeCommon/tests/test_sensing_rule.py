"""The device's sensing-pair rule in ONE home (decisions 217, 243, 247; moved here 2026-09-26).

While a lead stimulates, BrainSense senses only on the two contacts immediately flanking the
stimulating contacts: stimulate on 1 and sense 0-2, on 2 and sense 1-3, on 1 and 2 and sense 0-3;
on 0 or 3 nothing (BrainSense tip card pp. 7-8, white paper p. 8, A610 p. 36). Three pages need it
-- the Stim Optimizer's readiness card, the Closed-Loop page's device rule D52, and now the
Biomarkers heat maps -- and Biomarkers may not import the Stim Optimizer (decision 234), so the
arithmetic and the block that states it live in DecodeCommon, which all three may import.

Runs on both suites, so no test takes arguments.
"""
import ast
import os
import re

import pandas as pd

try:
    from modules.DecodeCommon import sensing_rule as SR
except ImportError:
    from DecodeCommon import sensing_rule as SR

_MODULES = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))

#: RCS08's labels as the Biomarkers formatter prints them (decision 181: sensing pairs keep
#: superscripts); a stand-in so this file needs no Biomarkers import.
_LABELS = {"ONE_THREE_LEFT": "L 1⁻3⁺", "ZERO_THREE_RIGHT": "R 0⁻3⁺", "ZERO_TWO_LEFT": "L 0⁻2⁺"}


def test_the_pair_the_device_allows_for_each_set_of_stimulating_contacts():
    assert SR.flanking_pair({2}) == (1, 3)
    assert SR.flanking_pair({1}) == (0, 2)
    assert SR.flanking_pair({1, 2}) == (0, 3)
    assert SR.flanking_pair({0}) is None           # nothing flanks an end contact
    assert SR.flanking_pair({3}) is None
    assert SR.flanking_pair({1, 3}) is None        # not contiguous
    assert SR.flanking_pair(set()) is None
    assert SR.flanking_pair(None) is None


def test_the_programmed_cathode_is_read_as_ring_numbers():
    assert SR.stim_rings("2a-2b-2c") == {2}
    assert SR.stim_rings("1a-1b-1c-2a-2b-2c") == {1, 2}
    assert SR.stim_rings("1a-2b") == {1, 2}
    for nothing in (None, "", "none", "NaN", "case"):
        assert SR.stim_rings(nothing) == set()


def test_a_pair_is_judged_against_the_rings_and_the_rule_runs_backwards_too():
    assert SR.sensing_pair_rings("ZERO_TWO_LEFT") == (0, 2)
    assert SR.sensing_pair_rings("nonsense") is None
    assert SR.pair_flanks_stimulation("ONE_THREE_LEFT", {2}) is True
    assert SR.pair_flanks_stimulation("ZERO_THREE_LEFT", {2}) is False
    assert SR.pair_flanks_stimulation("ONE_THREE_LEFT", set()) is None
    assert SR.stim_rings_for_sensing_pair("ZERO_THREE_LEFT") == {1, 2}
    assert SR.stim_rings_for_sensing_pair("ZERO_ONE_LEFT") is None
    for ch in ("ZERO_TWO_LEFT", "ONE_THREE_RIGHT", "ZERO_THREE_LEFT"):
        assert SR.flanking_pair(SR.stim_rings_for_sensing_pair(ch)) == SR.sensing_pair_rings(ch)
    assert SR.channel_for_pair((1, 3), "Left") == "ONE_THREE_LEFT"
    assert SR.channel_for_pair((0, 3), "Right") == "ZERO_THREE_RIGHT"


def test_the_block_with_the_readiness_screens_count_reads_exactly_as_the_stim_optimizers_did():
    """The Stim Optimizer's sentence and fields, word for word (the refactor moves no value)."""
    cells = [{"channel": "ONE_THREE_LEFT", "deployable": False},
             {"channel": "ZERO_THREE_RIGHT", "deployable": False},
             {"channel": "ZERO_TWO_LEFT", "deployable": True}]
    blk = SR.sensing_rule_block({"Left": {2}, "Right": {1, 2}}, cells=cells, n_screened=50,
                                n_usable=1, display_of=_LABELS.get)
    assert blk["decision"] == 217
    assert blk["sentence"] == ("While today's contacts are stimulating, the device allows one "
                               "sensing pair per lead: L 1⁻3⁺ and R 0⁻3⁺. Neither has a usable "
                               "band, so 1 of 50 contact-and-rate combinations are usable for "
                               "closed loop.")
    left = blk["by_side"]["Left"]
    assert left == {"stim_rings": [2], "rule_applied": True, "allowed_pair": [1, 3],
                    "allowed_channel": "ONE_THREE_LEFT", "allowed_display": "L 1⁻3⁺",
                    "n_usable_on_allowed_pair": 0,
                    "why": "stimulating on contact(s) 2, the device senses only on the two "
                           "contacts flanking them"}
    assert set(blk) == {"by_side", "sentence", "decision"}


def test_the_block_without_a_screen_names_the_pairs_and_counts_nothing():
    """The heat maps have no readiness screen: the sentence names the allowed pairs and says what
    a band elsewhere means, and no per-pair count is invented (None, never 0)."""
    blk = SR.sensing_rule_block({"Left": {2}, "Right": {1, 2}}, display_of=_LABELS.get)
    assert blk["sentence"].startswith("While today's contacts are stimulating, the device allows "
                                      "one sensing pair per lead: L 1⁻3⁺ and R 0⁻3⁺.")
    assert not re.search(r"\d+ of \d+", blk["sentence"])
    for side in ("Left", "Right"):
        assert blk["by_side"][side]["n_usable_on_allowed_pair"] is None
    assert blk["by_side"]["Right"]["allowed_channel"] == "ZERO_THREE_RIGHT"


def test_a_label_the_formatter_cannot_give_falls_back_to_the_channel_name():
    blk = SR.sensing_rule_block({"Left": {1}, "Right": set()})
    assert blk["by_side"]["Left"]["allowed_display"] == "ZERO_TWO_LEFT"
    assert blk["by_side"]["Right"]["rule_applied"] is False
    assert "no rule is applied" in blk["by_side"]["Right"]["why"]


def test_extra_fields_per_side_ride_on_the_rows_and_never_replace_the_rules_own():
    blk = SR.sensing_rule_block({"Left": {2}}, display_of=_LABELS.get,
                                extra_by_side={"Left": {"stim_cathode_raw": "2a-2b-2c",
                                                        "allowed_channel": "WRONG"}})
    assert blk["by_side"]["Left"]["stim_cathode_raw"] == "2a-2b-2c"
    assert blk["by_side"]["Left"]["allowed_channel"] == "ONE_THREE_LEFT"


def test_the_contacts_in_force_are_the_newest_row_per_lead_of_the_settings_stream():
    t = pd.to_datetime(["2026-08-12 17:00", "2026-09-03 18:00", "2026-07-22 17:00",
                        "2026-09-03 18:00", "2026-01-05 10:00"], utc=True)
    df = pd.DataFrame({"t": t, "hemi": ["Left", "Left", "Right", "Right", "Left"],
                       "cathode": ["1a-1b-1c", "2a-2b-2c", "1a-1b-1c", "1a-1b-1c-2a-2b-2c",
                                   "0a-0b-0c"]})
    got = SR.rings_in_force_by_side(df)
    assert got["Left"]["rings"] == {2}
    assert got["Left"]["cathode"] == "2a-2b-2c"
    assert got["Right"]["rings"] == {1, 2}
    assert str(got["Left"]["newest_row_utc"]).startswith("2026-09-03")
    only_left = SR.rings_in_force_by_side(df[df["hemi"] == "Left"])
    assert only_left["Right"]["rings"] == set() and only_left["Right"]["cathode"] is None
    assert SR.rings_in_force_by_side(None)["Left"]["rings"] == set()


def _calls_outside_the_home():
    """(file, alias, name) for every call of a rule function in the three packages that use it."""
    names = ("stim_rings", "flanking_pair", "pair_flanks_stimulation", "sensing_pair_rings",
             "stim_rings_for_sensing_pair")
    out = []
    for pkg in ("ClosedLoopDeployment", "ControlAnalyses", "Biomarkers"):
        for root, dirs, files in os.walk(os.path.join(_MODULES, pkg)):
            dirs[:] = [d for d in dirs if d not in ("tests", "__pycache__")]
            for f in files:
                if not f.endswith(".py"):
                    continue
                path = os.path.join(root, f)
                with open(path, encoding="utf-8") as fh:
                    tree = ast.parse(fh.read())
                for node in ast.walk(tree):
                    if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                            and node.func.attr in names and isinstance(node.func.value, ast.Name)):
                        out.append((path, node.func.value.id, node.func.attr, tree))
    return out


def test_the_rule_is_defined_once_and_every_other_package_calls_it_from_here():
    """One definition of each function, in this module; the Closed-Loop, control-analysis and
    Biomarkers code call it through a name bound to THIS module, never through the Stim Optimizer
    (whose own names are delegations to this module)."""
    defs = {}
    for root, dirs, files in os.walk(_MODULES):
        dirs[:] = [d for d in dirs if d not in ("tests", "__pycache__")]
        for f in files:
            if f.endswith(".py"):
                with open(os.path.join(root, f), encoding="utf-8") as fh:
                    src = fh.read()
                for name in ("flanking_pair", "pair_flanks_stimulation", "sensing_pair_rings",
                             "stim_rings_for_sensing_pair", "stim_rings"):
                    if re.search(rf"^def {name}\(", src, flags=re.M):
                        defs.setdefault(name, []).append(os.path.relpath(os.path.join(root, f), _MODULES))
    for name, where in defs.items():
        assert where == [os.path.join("DecodeCommon", "sensing_rule.py")], (name, where)
    calls = _calls_outside_the_home()
    assert calls, "the Closed-Loop page's D52 calls the rule; the scan found nothing"
    for path, alias, name, tree in calls:
        bound = False
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and (node.module or "").endswith("DecodeCommon"):
                bound |= any(a.name == "sensing_rule" and (a.asname or a.name) == alias
                             for a in node.names)
        assert bound, f"{os.path.relpath(path, _MODULES)} calls {alias}.{name} not bound to DecodeCommon.sensing_rule"
