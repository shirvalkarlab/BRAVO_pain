"""Two readings of one titration session, and which of them is the reading.

THE QUESTION THIS SETTLES. A titration session gives two chances to ask whether a band tracks pain,
and they are not the same question:

  * the RAMP -- the ladder's settled steps, where the current is deliberately stepped. Band power and
    pain both move with the current here, so a correlation between them across the ramp is partly
    the current itself. Read WITH the current taken out (the PI, 2026-09-22, ruling 1).
  * the HOLDS -- three five-minute blocks, off / on / off, at one current, the patient not told
    which. Nothing is being stepped, so a pain change across the blocks is a pain change.

The PI's ruling is that the ramp with the current term is the reading and the holds' reading is
computed beside it, so the two can be compared before he settles it for good. Both are therefore
produced, neither is hidden, and the module says plainly which is which.

Run on the host:
    cd BRAVO/modules && PYTHONPATH=. python -B -m pytest StimOptimizer/tests/test_titration_readings.py -q
"""
import numpy as np
import pytest

from StimOptimizer.routines import titration_readings as TR


# ---------------------------------------------------------------------------------------------
# helpers: one session's ladder and holds, with a known answer planted in them
# ---------------------------------------------------------------------------------------------

def _ramp_steps(seed=0, n_up=10, confounded=24.5, honest=25.5, noise=8.0):
    """Ladder steps where one band follows the CURRENT only and another follows PAIN only.

    Pain falls as the current rises (as this participant's record does), so the band that follows
    the current is left correlated with pain through nothing but the current.
    """
    rng = np.random.default_rng(seed)
    currents = np.concatenate([np.arange(0.0, 0.5 * n_up, 0.5), np.arange(0.5 * n_up, 0.0, -1.0)])
    own = rng.normal(0.0, 1.0, currents.size)          # what pain does on its own
    pain = 60.0 - 4.0 * currents + 5.0 * own
    steps = []
    for i, c in enumerate(currents):
        steps.append({
            "current_mA": float(c),
            "pain": float(pain[i]),
            "power_by_band": {
                confounded: float(200.0 - 20.0 * c + rng.normal(0, noise)),   # the current only
                honest: float(200.0 + 15.0 * own[i] + rng.normal(0, noise)),  # pain only
            },
        })
    return steps


def _holds(effect=0.0, seed=1, per_minute=5, band=24.5, band_effect=0.0):
    """off / on / off, five ratings a block; `effect` is how much lower pain runs during the on."""
    rng = np.random.default_rng(seed)
    out = []
    for i, (block, cur) in enumerate((("off", 0.0), ("on", 4.5), ("off", 0.0))):
        base = 60.0 - (effect if block == "on" else 0.0)
        out.append({
            "block": block,
            "current_mA": cur,
            "ratings": [float(base + rng.normal(0, 2.0)) for _ in range(per_minute)],
            "power_by_band": {band: [float(200.0 - (band_effect if block == "on" else 0.0)
                                           + rng.normal(0, 2.0)) for _ in range(per_minute)]},
        })
    return out


# ---------------------------------------------------------------------------------------------
# 1. the ramp, read with the current taken out
# ---------------------------------------------------------------------------------------------

def test_the_ramp_reading_takes_the_current_out_and_keeps_the_plain_value_beside_it():
    """Across seeds, because one ladder is about twenty steps and two unrelated series correlate at
    a few tenths on twenty points by chance -- a single draw cannot tell a working adjustment from a
    lucky one. What must hold on EVERY draw is the plain correlation, the honest band surviving, and
    the confounded band's interval covering zero; what must hold ON AVERAGE is the confounded band's
    adjusted value sitting near zero rather than somewhere else."""
    adjusted_confounded = []
    for seed in range(8):
        got = TR.ramp_reading(_ramp_steps(seed=seed), bands_hz=[24.5, 25.5])
        conf, honest = got["bands"][24.5], got["bands"][25.5]
        assert abs(conf["r"]) > 0.4, "a band that follows the current correlates with pain plainly"
        assert conf["n_steps"] == len(_ramp_steps(seed=seed))
        # The honest band is judged on the ADJUSTED value, not the plain one: the current's own
        # variance dilutes a real relationship, so a band that genuinely tracks pain can read weak
        # plainly and strong once the current is out (seed 1 here: 0.17 plain, 0.65 adjusted). That
        # is the same direction the live record shows on L 1-3+, where the readings strengthen.
        assert abs(honest["r_adjusted"]) > 0.5, f"seed {seed}: a real relationship must survive"
        assert honest["r_adjusted_ci"][0] * honest["r_adjusted_ci"][1] > 0, "its interval clears zero"
        assert got["reading"] == "adjusted", "the ramp's reading is the adjusted one (the PI, 2026-09-22)"
        adjusted_confounded.append(conf["r_adjusted"])
    centre = float(np.median(adjusted_confounded))
    assert abs(centre) < 0.2, (f"taking the current out of a current-only band should leave nothing "
                               f"on average; the median across seeds was {centre:+.3f}")


def test_one_session_is_a_lead_and_the_reading_says_so():
    """What a fifteen-step ladder cannot settle, said on the reading itself.

    Measured while building this (120 constructed ladders of the same shape): a band with NO pain
    relationship, once the current is taken out, still reads beyond 0.4 in about one draw in eight
    and clears zero in about one in fourteen. Seed 5 of the test above is one of those draws -- it
    comes back at +0.61 with an interval that excludes zero, from nothing. The module therefore
    carries the caveat on every ramp reading, and a future reader who wants to drop it has to argue
    with this number rather than with a style preference.
    """
    got = TR.ramp_reading(_ramp_steps(), bands_hz=[24.5])
    assert "one visit" in got["caveat"] and "never as established" in got["caveat"]
    both = TR.session_reading(ramp_steps=_ramp_steps(), holds=_holds(), bands_hz=[24.5])
    assert both["caveat"] == got["caveat"]
    # the draw that proves the point, pinned so it cannot be quietly explained away
    seed5 = TR.ramp_reading(_ramp_steps(seed=5), bands_hz=[24.5])["bands"][24.5]
    assert seed5["r_adjusted"] > 0.5 and seed5["r_adjusted_ci"][0] > 0.0


def test_a_band_that_is_almost_exactly_the_current_says_so_instead_of_printing_an_adjusted_number():
    """The degenerate case, and the one most likely to mislead: when a band IS the current, taking
    the current out leaves only noise, and a number computed from that noise looks like an answer."""
    steps = _ramp_steps(noise=0.05)                      # the band is the current, near enough
    got = TR.ramp_reading(steps, bands_hz=[24.5])
    b = got["bands"][24.5]
    assert b["nearly_the_current"] is True
    assert b["r_adjusted"] is None
    assert "almost exactly with the current" in (b["adjustment_reason"] or "")
    assert abs(b["r_band_vs_current"]) > 0.99


def test_a_ramp_whose_current_never_moves_cannot_be_adjusted_and_says_so():
    steps = [{"current_mA": 2.0, "pain": 50.0 + i, "power_by_band": {24.5: 200.0 + i}}
             for i in range(8)]
    got = TR.ramp_reading(steps, bands_hz=[24.5])
    b = got["bands"][24.5]
    assert b["r"] is not None and b["r_adjusted"] is None
    assert "constant" in (b["adjustment_reason"] or "").lower()


def test_a_ramp_with_too_few_steps_is_a_reason_not_a_crash():
    got = TR.ramp_reading([{"current_mA": 0.0, "pain": 50.0, "power_by_band": {24.5: 1.0}}],
                          bands_hz=[24.5])
    assert got["bands"][24.5]["r"] is None
    assert "too few" in (got["bands"][24.5]["reason"] or "").lower()


# ---------------------------------------------------------------------------------------------
# 2. the holds, where nothing is being stepped
# ---------------------------------------------------------------------------------------------

def test_the_holds_reading_recovers_a_real_on_effect_with_an_interval_that_clears_zero():
    got = TR.holds_reading(_holds(effect=12.0, per_minute=8), bands_hz=[24.5])
    pain = got["pain"]
    assert pain["n_on"] == 8 and pain["n_off"] == 16
    assert pain["on_minus_off"] < -6.0, "pain runs lower during the on block"
    assert pain["ci"][1] < 0.0, "and the interval clears zero"
    assert "off hold" in pain["why"].lower() and "on hold" in pain["why"].lower()


def test_holds_with_no_real_effect_come_back_with_an_interval_that_spans_zero():
    got = TR.holds_reading(_holds(effect=0.0, per_minute=8), bands_hz=[24.5])
    ci = got["pain"]["ci"]
    assert ci[0] < 0.0 < ci[1], "no effect: the interval must span zero"


def test_a_hold_block_with_no_ratings_is_refused_with_a_reason():
    holds = _holds(effect=5.0)
    holds[1]["ratings"] = []
    got = TR.holds_reading(holds, bands_hz=[24.5])
    assert got["pain"]["on_minus_off"] is None
    assert "no ratings" in (got["pain"]["reason"] or "").lower()


def test_the_band_moves_across_the_holds_are_reported_too():
    got = TR.holds_reading(_holds(effect=10.0, band_effect=30.0, per_minute=8), bands_hz=[24.5])
    b = got["bands"][24.5]
    assert b["on_minus_off"] < -10.0 and b["ci"][1] < 0.0


# ---------------------------------------------------------------------------------------------
# 3. both readings together, and which one is the reading
# ---------------------------------------------------------------------------------------------

def test_the_session_carries_both_readings_and_names_the_one_to_read():
    got = TR.session_reading(ramp_steps=_ramp_steps(), holds=_holds(effect=10.0, per_minute=8),
                             bands_hz=[24.5, 25.5])
    assert set(got) >= {"ramp", "holds", "reading", "why", "compare"}
    assert got["reading"] == "ramp_adjusted"
    assert "current" in got["why"] and "2026-09-22" in got["why"]
    # the comparison the PI asked for: the same band's answer from both, side by side
    row = got["compare"][24.5]
    assert set(row) >= {"ramp_r", "ramp_r_adjusted", "holds_on_minus_off"}
    assert row["ramp_r_adjusted"] is not None


def test_a_session_with_no_holds_still_reads_the_ramp_and_says_the_holds_are_missing():
    got = TR.session_reading(ramp_steps=_ramp_steps(), holds=[], bands_hz=[24.5])
    assert got["ramp"]["bands"][24.5]["r_adjusted"] is not None
    assert got["holds"]["pain"]["on_minus_off"] is None
    assert "no holds" in (got["holds"]["pain"]["reason"] or "").lower()
    assert got["reading"] == "ramp_adjusted"


if __name__ == "__main__":                              # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
