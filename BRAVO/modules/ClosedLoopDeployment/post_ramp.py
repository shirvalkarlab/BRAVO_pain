"""THE SWITCH for the 20 s post-ramp margin on the three-source comparison (review hazard 1).

SETTLED OFF BY MEASUREMENT, 2026-09-17 (decision 196, the PI: "settle the issue for S7, remove
NO DATA since all is stable"). On the 2026-09-16 titration session at 55 Hz, 31 settings held
107-168 s on L 1-3+, the band power in the first 3 s after a current move is 1.000 of the same
setting's last-30 s level (95 % 0.86-1.16); on the record's 58 holds of 60 s or more, 0.98-1.02
at every window from 3 to 30 s. There is no transient to exclude at the pieces' 3 s resolution.
The switch stays False and is not to be turned on; it is kept only so the stored tables' rule
versions (`_off`) do not move. The history that follows is why it existed.

Two removed points flipping a verdict is his call, not the code's, so the margin ships OFF
(decision 144, 2026-09-12). It was switched ON for part of the evening of 2026-09-15 (decision
178, which records what that did: L 1-3+ went from "supported (provisional)" to blocked on a slope
of +17.31 from 11 points) and switched back the same night on his ruling, "let the next titration
decide, so wait on more data" (decision 179). The rule versions of every stored table derived from
the comparison carry the state, so a table built one way is never served as the other; the switch
is read at import, so flipping it means restarting the workers, after which the tables rebuild
under their own keys. `margin_becomes_available` is the condition for turning it on."""
try:
    from modules.StimOptimizer.routines.within_visit import RAMP_EXCLUDE_S as _RAMP_EXCLUDE_S
except ImportError:                                   # the host suite's root
    from modules.StimOptimizer.routines.within_visit import RAMP_EXCLUDE_S as _RAMP_EXCLUDE_S

USE_POST_RAMP_MARGIN = False



# Aditya canonical compatibility imports/constants.

def margin_s():
    """Seconds after a current move kept out of the settled window: 20 when on, 0 when off."""
    return float(_RAMP_EXCLUDE_S) if USE_POST_RAMP_MARGIN else 0.0


def version_tag():
    """The token every derived table's rule version carries, so the two states never share a key."""
    return "20s" if USE_POST_RAMP_MARGIN else "off"


def margin_becomes_available(runs, *, min_settled_settings=None):
    """Whether any single run in the stored per-run points table (`run_points.KIND`) has enough
    settled settings for the margin to be switched on without two removed points being able to
    flip a verdict -- the condition the PI's decision of 2026-09-12 evening set: the margin becomes
    a feature of the titration session the Stim Optimizer recommends (open item 30), and switches
    on once such a session has been recorded.

    ``runs`` is the per-run points frame (one row per route, band and setting of every run). A
    "settled setting" is a distinct current carrying a settled band-power value on the voltage-
    trace route; the count is per (run, sensing contact). The floor defaults to
    `amplitude_effect.MIN_POINTS_CURVATURE` (8, decision 55) so it is defined once. ``None`` or an
    empty frame means the table is not stored, and the answer says so rather than reporting False
    as though it had counted. Derived, never typed: the sentence on the page reads this.
    """
    if min_settled_settings is None:
        from .amplitude_effect import MIN_POINTS_CURVATURE as _floor   # lazy: amplitude_effect imports this module
        min_settled_settings = int(_floor)
    need = int(min_settled_settings)
    out = {"available": False, "min_settled_settings": need, "switch_on": bool(USE_POST_RAMP_MARGIN),
           "table_stored": runs is not None, "n_runs": 0,
           "max_settled_settings_in_one_run": None, "run": None, "sensing_contact": None,
           "runs_at_or_above_floor": []}
    if runs is None:
        out["note"] = "the per-run points table is not stored, so nothing was counted"
        return out
    try:
        from modules.StimOptimizer.titration_plan import settled_settings_per_run as _per_run
    except ImportError:
        from modules.StimOptimizer.titration_plan import settled_settings_per_run as _per_run
    per = _per_run(runs)
    if per.empty:
        out["note"] = "the per-run points table holds no settled voltage-trace value in any run"
        return out
    out["n_runs"] = int(per["run"].nunique())
    i = per["n_settled_settings"].idxmax()
    out["max_settled_settings_in_one_run"] = int(per.loc[i, "n_settled_settings"])
    out["run"] = str(per.loc[i, "run"])
    out["sensing_contact"] = str(per.loc[i, "sensing_contact"])
    hits = per[per["n_settled_settings"] >= need]
    out["runs_at_or_above_floor"] = [
        {"run": str(r["run"]), "sensing_contact": str(r["sensing_contact"]),
         "n_settled_settings": int(r["n_settled_settings"])} for _, r in hits.iterrows()]
    out["available"] = bool(len(hits) > 0)
    out["note"] = (f"{len(hits)} of {out['n_runs']} runs hold at least {need} settled settings"
                   if out["available"] else
                   f"no run holds {need} settled settings; the most in any one run is "
                   f"{out['max_settled_settings_in_one_run']} ({out['run']} on {out['sensing_contact']})")
    return out


# Retained active Aditya interfaces.
