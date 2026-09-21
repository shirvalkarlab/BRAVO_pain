"""The sensing pair must be the two contacts IMMEDIATELY flanking the stimulating contact on its
own lead (decision 217, the PI, 2026-09-20: "in monopolar stimulation mode such as Left C+2-,
sensing contact pair must be the adjacent contacts immediately above and below the active cathode
... for L C+1-2-, we have to use L 0-3+").

The device offers exactly three sensing/stimulation configurations per lead (Medtronic BrainSense
tip card p. 8: "Unipolar Stimulation Only; Two Sensing contacts on lead are needed; Cannot
stimulate on sensing contacts; Stimulation contacts must be between sensing contacts; Results in 3
Possible Sensing/Stimulation Configurations Per Lead", and the three lead pictograms on its p. 7
and the white paper p. 8, "3 possibilities"): stimulate on 1 and sense 0-2; stimulate on 2 and
sense 1-3; stimulate on 1 and 2 and sense 0-3. Stimulating on 0 or 3 leaves no flanking pair (A610
p. 36 sends such a lead to contralateral sensing). The readiness screen judged every pair on its
evidence alone and so offered L 0-2+ while the left stimulates on contact 2. Now the screen is told
which rings each lead stimulates on (the cathode in force) and a cell whose sensing pair is not the
flanking pair is refused with a plain reason. A lead with no stimulation in force applies no rule.
"""
import numpy as np
import pytest

from StimOptimizer.routines import lfp_evidence as EV
from StimOptimizer.routines import lfp_response as LR
from StimOptimizer import bravo_service as BS

CENTRES = [float(c) for c in range(10, 28)]


def _Res(responds, slope_p, sep_d, slope):
    return LR.ResponseResult(responds=responds, reason="fixture", direction_ok=responds,
                             separation_d=sep_d, slope_per_mA=slope, slope_p=slope_p)


class _Ev:
    def __init__(self, amps=(1.6, 4.0)):
        self.amplitude_mA = np.array(amps, float)
        self.era = np.array(["a", "b"])[:len(amps)]
        self.cluster = np.arange(len(amps))
        self.band_power = {(c, 5.0): np.full(len(amps), c) for c in CENTRES}

    def power_for(self, c, w):
        return self.band_power[(float(c), float(w))]


def _fn_negative_at(centres_negative):
    neg = {float(c) for c in centres_negative}

    def fn(power, amp, era=None, cluster=None):
        c = float(np.asarray(power).ravel()[0])
        return _Res(True, 0.001, 1.2, -0.2 if c in neg else +0.2)
    return fn


@pytest.mark.parametrize("pair,rings,ok", [
    ("ONE_THREE_LEFT", {2}, True),     # stimulate on 2: the flanking pair is 1-3
    ("ZERO_TWO_LEFT", {2}, False),     # contains the stimulating contact
    ("ZERO_THREE_LEFT", {2}, False),   # brackets it but is not the flanking pair
    ("ZERO_ONE_LEFT", {2}, False),
    ("TWO_THREE_LEFT", {2}, False),
    ("ZERO_TWO_LEFT", {1}, True),      # stimulate on 1: the flanking pair is 0-2
    ("ONE_THREE_LEFT", {1}, False),
    ("ZERO_THREE_LEFT", {1}, False),
    ("ZERO_THREE_LEFT", {1, 2}, True),   # stimulate on 1 and 2 (double monopolar): 0-3
    ("ONE_THREE_LEFT", {1, 2}, False),
    ("ZERO_TWO_LEFT", {1, 2}, False),
    ("ONE_THREE_LEFT", {0}, False),    # stimulating on 0: no pair flanks it
    ("ZERO_TWO_LEFT", {3}, False),     # stimulating on 3: no pair flanks it
])
def test_the_sensing_pair_must_be_the_contacts_immediately_flanking_the_stimulating_contact(pair, rings, ok):
    assert EV.pair_flanks_stimulation(pair, rings) is ok


@pytest.mark.parametrize("rings,expected", [({2}, (1, 3)), ({1}, (0, 2)), ({1, 2}, (0, 3)), ({0}, None), ({3}, None), ({2, 3}, None), (set(), None)])
def test_the_one_allowed_pair_for_a_stimulating_contact(rings, expected):
    assert EV.flanking_pair(rings) == expected


def test_a_pair_containing_the_stimulating_contact_is_refused_on_the_screen_with_the_reason():
    ev = {("ZERO_TWO_LEFT", "Left", 55.0): _Ev(), ("ONE_THREE_LEFT", "Left", 55.0): _Ev()}
    pain = {"ZERO_TWO_LEFT": {24.0}, "ONE_THREE_LEFT": {24.0}}
    screen, best = EV.screen_cells(ev, response_fn=_fn_negative_at([24.0]), pain_positive_by_channel=pain,
                                   stim_rings_by_side={"Left": {2}, "Right": {2}})
    rows = {r.channel: r for _, r in screen.iterrows()}
    assert bool(rows["ONE_THREE_LEFT"].deployable) is True and rows["ONE_THREE_LEFT"].blocking_reasons == ""
    assert bool(rows["ZERO_TWO_LEFT"].deployable) is False
    assert "stimulating on contact 2" in rows["ZERO_TWO_LEFT"].blocking_reasons
    assert "the only sensing pair the device allows is 1-3" in rows["ZERO_TWO_LEFT"].blocking_reasons
    assert bool(rows["ZERO_TWO_LEFT"].sensing_pair_flanks_stimulation) is False
    assert bool(rows["ONE_THREE_LEFT"].sensing_pair_flanks_stimulation) is True
    assert best == ("ONE_THREE_LEFT", "Left", 55.0)


def test_the_rule_reads_the_sensing_leads_own_stimulating_contact_not_the_cells_side():
    """A contralateral cell (sensing on the right, driving the left) is judged against the RIGHT
    lead's stimulating contact, because that is the lead the pair sits on."""
    ev = {("ZERO_TWO_RIGHT", "Left", 55.0): _Ev()}
    screen, _ = EV.screen_cells(ev, response_fn=_fn_negative_at([24.0]),
                                pain_positive_by_channel={"ZERO_TWO_RIGHT": {24.0}},
                                stim_rings_by_side={"Left": {2}, "Right": {1}})
    assert bool(screen.iloc[0].sensing_pair_flanks_stimulation) is True     # 0-2 flanks 1
    assert bool(screen.iloc[0].deployable) is True


def test_no_stimulation_in_force_on_a_lead_applies_no_rule_and_says_it_was_not_checked():
    ev = {("ZERO_TWO_LEFT", "Left", 55.0): _Ev()}
    screen, _ = EV.screen_cells(ev, response_fn=_fn_negative_at([24.0]),
                                pain_positive_by_channel={"ZERO_TWO_LEFT": {24.0}})
    assert screen.iloc[0].sensing_pair_flanks_stimulation is None
    assert bool(screen.iloc[0].deployable) is True
    screen2, _ = EV.screen_cells(ev, response_fn=_fn_negative_at([24.0]),
                                 pain_positive_by_channel={"ZERO_TWO_LEFT": {24.0}},
                                 stim_rings_by_side={"Left": set(), "Right": {2}})
    assert screen2.iloc[0].sensing_pair_flanks_stimulation is None


def test_stimulating_on_contact_0_or_3_refuses_every_pair_on_that_lead_and_says_why():
    ev = {("ONE_THREE_LEFT", "Left", 55.0): _Ev()}
    screen, _ = EV.screen_cells(ev, response_fn=_fn_negative_at([24.0]),
                                pain_positive_by_channel={"ONE_THREE_LEFT": {24.0}},
                                stim_rings_by_side={"Left": {3}, "Right": {2}})
    assert bool(screen.iloc[0].deployable) is False
    assert "no sensing pair flanks" in screen.iloc[0].blocking_reasons


def test_the_stimulating_rings_are_read_from_the_cathode_in_force():
    assert BS.stim_rings("2a-2b-2c") == {2}
    assert BS.stim_rings("1a-1b-1c-2a-2b-2c") == {1, 2}
    assert BS.stim_rings("1a-1b") == {1}
    assert BS.stim_rings(None) == set() and BS.stim_rings("none") == set()
    assert BS.stim_rings_by_side({"Left": {"contacts_raw": "2a-2b-2c"}, "Right": {"contacts_raw": "1a-1b-1c-2a-2b-2c"}}) \
        == {"Left": {2}, "Right": {1, 2}}
