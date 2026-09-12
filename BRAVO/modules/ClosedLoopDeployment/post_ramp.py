"""THE SWITCH for the 20 s post-ramp margin on the three-source comparison (review hazard 1).

Commit 790ed21 wrote a clip that keeps the first `within_visit.RAMP_EXCLUDE_S` (20 s) after a
current move out of the settled window; nothing in production called it until 2026-09-12, when the
code review's hazard 1 wired it into `three_source_response._tile_panel`. Measured the same day on
RCS08 (decision 141 and 144): it drops one whole run of rising current and two more settled points,
and on the band in the PI's browser, ONE_THREE_LEFT at 24.5 Hz, the pooled current-to-power slope
goes from -3.79 device units per mA (13 points, 4 runs; interval spanning zero) to +17.31 (11
points, 3 runs; interval +1.17 to +33.46, so "established") -- the wrong way for the control law,
and the D19 rule then BLOCKS the verdict where it was "unsupported" before.

Two removed points flipping a verdict is his call, not the code's, so the margin ships OFF and the
rule versions of every stored table derived from the comparison carry the state, so a table built
one way is never served as the other. To turn it on: set `USE_POST_RAMP_MARGIN = True` and restart
the workers (the versions are read at import); the tables rebuild under their own keys.
"""
try:
    from modules.StimOptimizer.routines.within_visit import RAMP_EXCLUDE_S as _RAMP_EXCLUDE_S
except ImportError:                                   # the host suite's root
    from StimOptimizer.routines.within_visit import RAMP_EXCLUDE_S as _RAMP_EXCLUDE_S

USE_POST_RAMP_MARGIN = False


def margin_s():
    """Seconds after a current move kept out of the settled window: 20 when on, 0 when off."""
    return float(_RAMP_EXCLUDE_S) if USE_POST_RAMP_MARGIN else 0.0


def version_tag():
    """The token every derived table's rule version carries, so the two states never share a key."""
    return "20s" if USE_POST_RAMP_MARGIN else "off"
