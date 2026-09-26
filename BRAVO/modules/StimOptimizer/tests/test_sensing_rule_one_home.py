"""The Stim Optimizer's names for the device's sensing rule are delegations to its one home,
`DecodeCommon.sensing_rule` (moved there 2026-09-26 so the Biomarkers heat maps, which may not
import the Stim Optimizer, state the same rule). Every existing caller keeps its import; the
answer is the DecodeCommon function's, the same object where the signature is unchanged.
"""
from DecodeCommon import sensing_rule as SR
from StimOptimizer import bravo_service as BS
from StimOptimizer import titration_plan as TP
from StimOptimizer.routines import lfp_evidence as LE


def test_the_old_names_are_the_one_homes_functions():
    assert BS.stim_rings is SR.stim_rings
    assert LE.flanking_pair is SR.flanking_pair
    assert LE.pair_flanks_stimulation is SR.pair_flanks_stimulation
    assert LE.sensing_pair_rings is SR.sensing_pair_rings
    assert TP.stim_rings_for_sensing_pair is SR.stim_rings_for_sensing_pair


def test_the_readiness_block_is_the_one_homes_block_with_the_pages_labels():
    cells = [{"channel": "ONE_THREE_LEFT", "deployable": True}]
    got = BS.sensing_rule_block({"Left": {2}, "Right": {1, 2}}, cells=cells, n_screened=50,
                                n_usable=1)
    want = SR.sensing_rule_block({"Left": {2}, "Right": {1, 2}}, cells=cells, n_screened=50,
                                 n_usable=1,
                                 display_of=lambda ch: BS.sensing_display(ch).get("display_short"))
    assert got == want
    assert got["by_side"]["Left"]["allowed_display"] == "L 1⁻3⁺"
