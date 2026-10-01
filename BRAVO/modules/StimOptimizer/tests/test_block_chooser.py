"""Step C of the contact-aware Stim Optimizer (`routines.block_chooser`; the PI's go-ahead and
rulings of 2026-10-01): which (Left contact, rate) block to test at the next clinic visit.

His choices: the candidates are every Left contact that has carried current in either stream,
plus L C+1-2- (the only one that allows sensing on L 0-3); the blocks are ranked MOST PROMISING
FIRST, by the largest plausible improvement in pain over the setting in force (predicted
improvement + 2 SD) at a safe current pair under both sides' maxima. A block with no fitted
surface gets the same bound from the stream's own spread of J (prior mean: no change). Rates
below the closed-loop minimum are not offered. The session runs at the pulse-width pairing in
force (ruling 5 of decision 233).
"""
import numpy as np
import pytest

from StimOptimizer.routines import block_chooser as BC

AMPS = [0.0, 1.0, 2.0, 3.0, 4.0, 5.0]


def _surface(mu, sd, safe=None):
    n = len(AMPS)
    return {"amps_mA": AMPS, "mu": [[mu(i, j) for j in range(n)] for i in range(n)],
            "sd": [[sd(i, j) for j in range(n)] for i in range(n)],
            "safe": [[True if safe is None else safe(i, j) for j in range(n)] for i in range(n)]}


def _row(contact, rate, *, fitted, surface=None, n=10, pw=(100.0, 150.0)):
    return {"pw_us_left": pw[0], "pw_us_right": pw[1], "left_contact": contact, "rate_hz": rate,
            "fitted": fitted, "n_epochs": n, "surface": surface}


def _block(out, contact, rate=55.0):
    """The one block for this Left contact and rate (L C+1-2- is always a candidate too, so the
    block wanted is never assumed to be first)."""
    (b,) = [b for b in out["blocks"] if b["left_contact"] == contact and b["rate_hz"] == rate]
    return b


IN_FORCE = {"Left": {"contacts_short": "L C+2-", "pulse_width_us": 100.0, "rate_hz": 55.0},
            "Right": {"pulse_width_us": 150.0}}


def test_a_fitted_block_is_scored_by_its_best_plausible_improvement_at_a_safe_cell_under_the_maxima():
    # improvement = -mu; best plausible = -mu + 2 sd; the best cell is at (4, 4) mA but the Left
    # maximum is 3 mA, so the chooser must stop at Left 3 mA
    surf = _surface(mu=lambda i, j: -0.2 * i - 0.1 * j, sd=lambda i, j: 0.1)
    out = BC.rank_blocks([_row("L C+2-", 55.0, fitted=True, surface=surf)], in_force=IN_FORCE,
                         contacts_used=["L C+2-"], rates=[55.0], ceilings={"Left": 3.0, "Right": 4.0},
                         prior_sd=1.0)
    b = _block(out, "L C+2-")
    assert b["basis"] == "fitted surface"
    assert (b["amp_mA_left"], b["amp_mA_right"]) == (3.0, 4.0)
    assert b["optimistic_improvement"] == pytest.approx(0.2 * 3 + 0.1 * 4 + 2 * 0.1)
    assert b["predicted_improvement"] == pytest.approx(1.0)


def test_unsafe_cells_are_never_chosen():
    surf = _surface(mu=lambda i, j: -0.2 * i, sd=lambda i, j: 0.1, safe=lambda i, j: i <= 2)
    out = BC.rank_blocks([_row("L C+2-", 55.0, fitted=True, surface=surf)], in_force=IN_FORCE,
                         contacts_used=["L C+2-"], rates=[55.0], ceilings={"Left": 5.0, "Right": 5.0},
                         prior_sd=1.0)
    assert _block(out, "L C+2-")["amp_mA_left"] == 2.0


def test_a_block_with_no_surface_gets_the_prior_bound_and_says_so():
    out = BC.rank_blocks([], in_force=IN_FORCE, contacts_used=["L C+2-"], rates=[55.0],
                         ceilings={"Left": 4.5, "Right": 4.5}, prior_sd=0.8)
    b = _block(out, "L C+2-")
    assert b["basis"] == "no surface: the stream's own spread"
    assert b["optimistic_improvement"] == pytest.approx(1.6)
    assert b["predicted_improvement"] == 0.0


def test_c12_is_always_a_candidate_and_rates_below_the_closed_loop_minimum_are_not():
    out = BC.rank_blocks([], in_force=IN_FORCE, contacts_used=["L C+2-", "L C+1-"],
                         rates=[10.0, 55.0, 110.0], ceilings={"Left": 4.5, "Right": 4.5}, prior_sd=1.0)
    keys = {(b["left_contact"], b["rate_hz"]) for b in out["blocks"]}
    assert ("L C+1-2-", 55.0) in keys and ("L C+1-2-", 110.0) in keys
    assert all(r >= 55.0 for _, r in keys)
    assert len(keys) == 3 * 2
    assert out["rates_left_out"] == [10.0]


def test_blocks_are_ranked_most_promising_first():
    good = _surface(mu=lambda i, j: -1.0, sd=lambda i, j: 0.75)    # bound 1 + 1.5 = 2.5
    poor = _surface(mu=lambda i, j: 0.5, sd=lambda i, j: 0.2)      # bound -0.5 + 0.4 = -0.1
    rows = [_row("L C+2-", 55.0, fitted=True, surface=poor, n=12),
            _row("L C+1-", 55.0, fitted=True, surface=good, n=9)]
    out = BC.rank_blocks(rows, in_force=IN_FORCE, contacts_used=["L C+2-", "L C+1-"], rates=[55.0],
                         ceilings={"Left": 4.5, "Right": 4.5}, prior_sd=1.0)
    order = [(b["left_contact"], b["optimistic_improvement"]) for b in out["blocks"]]
    assert order[0] == ("L C+1-", pytest.approx(2.5))
    assert order[1][0] == "L C+1-2-"                # no surface: the prior bound, 2 x 1.0 = 2.0
    assert order[-1][0] == "L C+2-"
    assert [b["rank"] for b in out["blocks"]] == [1, 2, 3]


def test_only_the_pairing_in_force_is_read():
    other = _surface(mu=lambda i, j: -5.0, sd=lambda i, j: 0.1)
    rows = [_row("L C+2-", 55.0, fitted=True, surface=other, pw=(60.0, 160.0))]
    out = BC.rank_blocks(rows, in_force=IN_FORCE, contacts_used=["L C+2-"], rates=[55.0],
                         ceilings={"Left": 4.5, "Right": 4.5}, prior_sd=1.0)
    assert _block(out, "L C+2-")["basis"] == "no surface: the stream's own spread"
    assert out["pulse_widths_us"] == {"Left": 100.0, "Right": 150.0}


def test_the_top_block_comes_with_its_ladder_up_to_the_left_maximum():
    good = _surface(mu=lambda i, j: -2.0, sd=lambda i, j: 0.5)
    out = BC.rank_blocks([_row("L C+2-", 55.0, fitted=True, surface=good)], in_force=IN_FORCE,
                         contacts_used=["L C+2-"], rates=[55.0],
                         ceilings={"Left": 2.5, "Right": 3.0}, prior_sd=1.0)
    lad = out["next_block"]["ladder"]
    assert lad["steps_mA"][0] == 0.0 and lad["top_mA"] == 2.5 and lad["steps_mA"][-1] == 0.0


def test_a_tie_goes_to_the_block_with_fewer_stretches():
    tied = _surface(mu=lambda i, j: 0.0, sd=lambda i, j: 1.0)       # bound 2.0, as the prior's
    rows = [_row("L C+2-", 55.0, fitted=True, surface=tied, n=12)]
    out = BC.rank_blocks(rows, in_force=IN_FORCE, contacts_used=["L C+2-"], rates=[55.0],
                         ceilings={"Left": 4.5, "Right": 4.5}, prior_sd=1.0)
    assert [b["left_contact"] for b in out["blocks"]] == ["L C+1-2-", "L C+2-"]


def test_the_service_offers_contacts_from_both_streams_and_takes_the_prior_from_the_clinic_spread():
    import types
    import pandas as pd
    from StimOptimizer import bravo_service as BS
    s1c = types.SimpleNamespace(
        D=pd.DataFrame({"J": [0.0, 1.0, 2.0, 3.0], "feasible": [True, True, True, False]}),
        audit={"left_contacts": [{"left_contact": "L 1+2-", "n_epochs": 5},
                                 {"left_contact": "off (Left 0 mA)", "n_epochs": 2}]})
    rows = [_row("L 1+2-", 110.0, fitted=False, n=5)]
    out = BS._next_blocks_block(rows, s1c, in_force=IN_FORCE,
                                ceilings={"Left": (4.5, "PI"), "Right": (4.5, "PI")},
                                home_left_contacts=[{"left_contact": "L C+1-", "n_epochs": 19}])
    contacts = {b["left_contact"] for b in out["blocks"]}
    assert contacts == {"L 1+2-", "L C+1-", "L C+2-", "L C+1-2-"}   # clinic, home, in force, C+1-2-
    assert {b["rate_hz"] for b in out["blocks"]} == {55.0, 110.0}     # the rows' rates and the rate in force
    assert out["prior_sd"] == pytest.approx(float(np.std([0.0, 1.0, 2.0])))   # feasible J only


def test_a_tie_at_the_top_is_said_and_no_single_block_is_offered_as_the_models_pick():
    # no surfaces at all: every block has the same prior bound, so the model cannot rank them
    out = BC.rank_blocks([], in_force=IN_FORCE, contacts_used=["L C+2-", "L C+1-"],
                         rates=[55.0, 110.0], ceilings={"Left": 4.5, "Right": 4.5}, prior_sd=1.0)
    assert out["n_tied_at_top"] == 6
    assert out["next_block"] is None
    assert "cannot rank" in out["ranking_note"] and "6" in out["ranking_note"]


def test_a_clear_winner_is_offered_with_its_ladder_and_no_tie_note():
    good = _surface(mu=lambda i, j: -2.0, sd=lambda i, j: 0.5)      # bound 3.0 > prior 2.0
    out = BC.rank_blocks([_row("L C+2-", 55.0, fitted=True, surface=good)], in_force=IN_FORCE,
                         contacts_used=["L C+2-"], rates=[55.0], ceilings={"Left": 4.5, "Right": 4.5},
                         prior_sd=1.0)
    assert out["n_tied_at_top"] == 1
    assert out["next_block"]["left_contact"] == "L C+2-"
    assert out["ranking_note"] is None
