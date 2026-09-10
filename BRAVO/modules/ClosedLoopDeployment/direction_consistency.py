"""The consistency check: makes the closed-loop control law's implied direction explicit, instead
of assumed (PI request, 2026-09-08).

WHAT THIS CHECKS, AND WHY IT IS NOT REDUNDANT WITH EITHER INPUT ALONE. Closing the loop on a band
means adjusting stimulation CURRENT to move that band's POWER, in the hope of moving PAIN. That is
a two-step chain, and this project already computes both links separately, but nothing before this
check combined them:

  * the within-visit link, current -> power: does raising current raise or lower this band's power,
    tested within one stimulation-current ladder, pooled with a per-visit intercept across every
    visit this participant has (`amplitude_effect.pooled_shape_for_band`, decision 55/56).
  * the cross-visit link, power -> pain: does higher power on this band associate with higher or
    lower pain, from the calibrated band-by-length sweep's own best-of-ten-lengths correlation
    (`Biomarkers.routines.analytics.band_time_sweep_from_power`, decision 38/64).

Multiplying the two signs gives current -> pain: whether raising current on this contact is
expected to relieve or worsen pain through this one band. `stability.py`'s own docstring names the
risk this check exists to catch: **"closing the loop on a band whose relationship to pain is itself
contingent on the current stimulation setting risks the device confirming its own exploration
policy."** A band can look protective in a cross-visit correlation and still be one whose own power
current does not move at all, or moves the wrong way for the correlation to translate into
anything current can act on; this check is the place that would surface either failure.

WHAT THIS DOES NOT DO. It does not fit a new statistic -- both links already exist and are already
computed elsewhere; this only reads them and reports the sign combination. It is not a pass/fail
gate: like the deployment gates in `bravo_service.deployment_summary` (decision 9), the honest
default on missing or non-significant evidence is "not assessed", never a manufactured pass. It
answers one band and one sensing contact at a time -- pooling across contacts or bands is a
reader's step, not this module's.
"""
import numpy as np

#: The same two-sided significance bar the rest of this project's direction calls use
#: (`amplitude_effect._direction`, decision 38's `p_selection_aware`).
SIGNIFICANCE_P = 0.05

#: The three within-visit phrases that mean "there is nothing here to combine" -- copied verbatim
#: from `StimOptimizer.routines.within_visit.amplitude_response_shape_pooled`'s own vocabulary
#: rather than re-derived, so a caller passing that function's own output needs no translation.
_WITHIN_VISIT_NOT_MOVING = (
    "not assessed",
    "no straight-line movement detected across the currents tested",
)


def _f(v):
    try:
        x = float(v)
    except (TypeError, ValueError):
        return np.nan
    return x if np.isfinite(x) else np.nan


def implied_control_direction(within_visit_pooled, correlation_row):
    """Combine one band's pooled within-visit direction with its cross-visit pain correlation.

    ``within_visit_pooled`` is `amplitude_effect.pooled_shape_for_band`'s return value (or the
    dict `within_visit.amplitude_response_shape_pooled` itself returns -- the two share the same
    ``pooled_direction``/``pooled_slope_per_mA``/``pooled_slope_p`` keys). ``correlation_row`` is
    one row of `band_time_sweep_from_power`'s ``best_correlation_rows`` for the same band centre
    and sensing contact (a dict with ``pearson_r`` and ``p_selection_aware``), or ``None`` when no
    such row exists.

    Returns a dict, never raising: the two input directions, the combined ``implied_control_
    direction`` as a plain sentence, and a ``reason`` naming which input was missing or not
    significant when the answer is "not assessed".
    """
    within_visit_pooled = within_visit_pooled or {}
    wv_dir = str(within_visit_pooled.get("pooled_direction", "not assessed"))
    out = {
        "within_visit_direction": wv_dir,
        "within_visit_slope_per_mA": _f(within_visit_pooled.get("pooled_slope_per_mA")),
        "within_visit_slope_p": _f(within_visit_pooled.get("pooled_slope_p")),
        "within_visit_n_points": int(within_visit_pooled.get("n", 0) or 0),
        "within_visit_n_visits": int(within_visit_pooled.get("n_visits", 0) or 0),
        "cross_visit_pain_correlation_r": np.nan,
        "cross_visit_pain_correlation_p": np.nan,
        "cross_visit_pain_direction": "not assessed",
        "implied_control_direction": "not assessed",
        "reason": None,
    }

    if wv_dir in _WITHIN_VISIT_NOT_MOVING:
        out["reason"] = (
            "the pooled within-visit relationship between stimulation current and this band's "
            "power is not assessed" if wv_dir == "not assessed" else
            "no significant within-visit movement was detected between stimulation current and "
            "this band's power, pooled across every visit tested")
        return out

    if correlation_row is None:
        out["reason"] = ("no cross-visit correlation between this band's power and pain is "
                         "available for this sensing contact")
        return out

    r = _f(correlation_row.get("pearson_r"))
    p = _f(correlation_row.get("p_selection_aware"))
    out["cross_visit_pain_correlation_r"] = r
    out["cross_visit_pain_correlation_p"] = p
    if not (np.isfinite(r) and np.isfinite(p)):
        out["reason"] = ("the cross-visit correlation between this band's power and pain could "
                         "not be computed")
        return out
    if p > SIGNIFICANCE_P:
        out["reason"] = ("the cross-visit correlation between this band's power and pain is not "
                         "statistically significant")
        return out

    power_raises_pain = r > 0
    out["cross_visit_pain_direction"] = ("higher band power is associated with more pain"
                                         if power_raises_pain else
                                         "higher band power is associated with less pain")

    # Chain rule on signs: d(pain)/d(current) = d(pain)/d(power) * d(power)/d(current). The two
    # links agree in sign (raising current raises pain through this band) exactly when the two
    # booleans below match -- an XNOR, not a coincidence of naming.
    current_raises_power = wv_dir == "band power rises as current rises"
    current_raises_pain = current_raises_power == power_raises_pain
    out["implied_control_direction"] = (
        "raising stimulation current on this contact is expected to worsen pain through this band"
        if current_raises_pain else
        "raising stimulation current on this contact is expected to relieve pain through this "
        "band")
    return out


def correlation_row_for_band(band_sweep_grid, sensing_contact, band_center_hz, *, atol=1e-6):
    """The best-of-ten-lengths correlation row for one sensing contact and band centre, from
    `ClosedLoopDeployment.adapter.band_sweep_grid_for_closed_loop`'s own return shape
    (``{"available": bool, "band_time_sweep": {sensing_contact: {"best_correlation_rows": [...]}}}``).
    ``None`` when the grid is unavailable, the contact has no sweep, or the centre is not on the
    sweep's own grid -- never raises.
    """
    if not band_sweep_grid or not band_sweep_grid.get("available"):
        return None
    sweep = (band_sweep_grid.get("band_time_sweep") or {}).get(str(sensing_contact))
    if not sweep:
        return None
    target = float(band_center_hz)
    for row in sweep.get("best_correlation_rows", []) or []:
        centre = _f(row.get("band_center_hz"))
        if np.isfinite(centre) and abs(centre - target) <= atol:
            return row
    return None


def for_band(build, band_sweep_grid, sensing_contact, band_center_hz, *, min_points=8,
             pooled=None):
    """The full consistency check for one (sensing contact, band centre): pools the within-visit
    dose-response from ``build`` (`three_source_response.build_for_participant`'s output) and
    looks up the cross-visit correlation row from ``band_sweep_grid``
    (`adapter.band_sweep_grid_for_closed_loop`'s output), then combines them.
    """
    from . import amplitude_effect as _amp

    # `pooled` is the row from the STORED table, pooled from every run this participant has. Prefer
    # it whenever the caller has one: `build` on a page request is truncated to the runs the page
    # draws, and pooling over that slice answers from a fraction of the visits (measured on RCS08:
    # 13 points across 4 visits from a full build, 6 across 1 from the page's). Pooling from `build`
    # stays as the path for a caller that genuinely holds every run, and for the tests.
    within_visit_pooled = (
        pooled if pooled is not None
        else _amp.pooled_shape_for_band(build, band_center_hz, sensing_contact,
                                        min_points=min_points))
    correlation_row = correlation_row_for_band(band_sweep_grid, sensing_contact, band_center_hz)
    out = implied_control_direction(within_visit_pooled, correlation_row)
    out["sensing_contact"] = str(sensing_contact)
    out["band_center_hz"] = float(band_center_hz)
    return out
