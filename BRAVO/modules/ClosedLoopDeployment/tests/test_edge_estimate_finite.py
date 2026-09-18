"""Invalid estimate values never license a sign or a coherent edge triangle."""
import itertools
from decimal import Decimal
from fractions import Fraction

import numpy as np
import pytest

from modules.ClosedLoopDeployment.types import EdgeEstimate
from modules.ClosedLoopDeployment.consistency import signs_coherent


def edge(estimate, ci=(.2, .8), name='E1'):
    return EdgeEstimate(name=name, estimate=estimate, ci=ci, p=None, n=8,
                        cluster_unit='synthetic visit', n_clusters=4)


@pytest.mark.parametrize('estimate', [
    None, float('nan'), float('inf'), float('-inf'), np.float64('nan'),
    'invalid', '1.0', [], {}, True, False, 10**400,
    np.bool_(True), np.array([.5]), np.array(.5), complex(.5,0),
    Decimal('NaN'), Decimal('sNaN'), Decimal('Infinity'), Decimal('-Infinity'),
    np.complex64(.5), np.complex128(.5), np.complex64(.5+.2j), np.complex128(.5+.2j),
])
@pytest.mark.parametrize('position', [0, 1, 2])
def test_invalid_estimate_remains_unknown_through_real_coherence(estimate, position):
    # Every interval excludes zero: the point estimate itself is the invalid input.
    edges = [edge(-.5, (-.8,-.2), 'E1'), edge(.5, (.2,.8), 'E2'),
             edge(-.5, (-.8,-.2), 'E3')]
    bad = edge(estimate, (.2,.8))
    assert bad.sign is None
    assert bad.resolved is False
    edges[position] = bad
    assert signs_coherent(*edges) is None


@pytest.mark.parametrize('estimate,sign', [(-.5,-1), (.5,1), (0.,0), (-0.,0),
                                            (np.float64(.5),1),
    (Decimal('.5'),1), (Decimal('-.5'),-1), (Decimal('0'),0),
    (Fraction(1,2),1), (Fraction(-1,2),-1), (Fraction(0),0)])
@pytest.mark.parametrize('ci,resolved', [
    ((.2,.8), True), ((-.8,-.2), True), ((-.2,.2), False),
    ((0.,.2), False), ((-.2,0.), False), ((0.,0.), False), (None,False),
])
def test_finite_estimates_use_point_direction_with_separate_interval_evidence(estimate, sign, ci, resolved):
    result = edge(estimate, ci)
    assert result.sign == sign
    assert result.resolved is (sign != 0)
    assert result.statistically_established is resolved


@pytest.mark.parametrize('signs', list(itertools.product([-1,0,1], repeat=3)))
def test_finite_sign_triangle_is_unchanged_including_zero(signs):
    # PI policy requires a nonzero point direction; interval evidence stays separate.
    edges = [edge(float(sign), (.2,.8), f'E{i+1}') for i,sign in enumerate(signs)]
    expected = None if 0 in signs else (signs[0]*signs[1]) == signs[2]
    assert signs_coherent(*edges) is expected


def test_finite_estimate_with_crossing_interval_has_provisional_direction():
    assert signs_coherent(edge(-.5, (-.8,-.2)), edge(.5, (-.2,.8)),
                          edge(-.5, (-.8,-.2))) is True
    assert edge(.5, (-.2,.8)).statistically_established is False
