"""The heat-map grid's per-pair statistics, as one function a worker process can run.

`band_time_sweep_from_power` does every shuffle, resample and fit for ONE contact pair, and draws
its random numbers from a generator it builds itself from the request's seed, so what it returns
depends only on its arguments, never on which process ran it or what ran before. That is what lets
`bravo_service._band_time_sweep_channels` hand each pair to the shared worker pool and put the
answers back in the pairs' own order with every value unchanged.

Kept in a module of its own so a worker imports the statistics and nothing else (no Django, no
database).
"""
from . import analytics


def sweep_stats_task(power, pain_values, kwargs):
    """``("ok", the pair's sweep)`` or ``("error", the message)``. Never raises, so one pair that
    breaks cannot take the others down with it; a pool that breaks does raise, in the caller."""
    try:
        return "ok", analytics.band_time_sweep_from_power(power, pain_values, **kwargs)
    except Exception as e:                                      # noqa: BLE001 -- reported per pair
        return "error", str(e)
