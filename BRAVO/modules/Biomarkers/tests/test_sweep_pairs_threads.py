"""The heat-map grid's contact pairs are swept side by side in threads (2026-10-02, the Jetstream2
BRAVO). Each pair reads only its own cache; the answers come back in the pairs' own order and equal
the one-after-another answers. Values, not shapes: each pair's entry compared with the serial run,
the order of the pairs, and that more than one thread did the work.
"""
import os
import threading

from modules.Biomarkers import bravo_service as B
from modules.Biomarkers.routines import analytics


def _run(threads):
    seen = set()
    old_power, old_sweep, old_env = (B._band_time_sweep_power_by_seconds,
                                     analytics.band_time_sweep_from_power,
                                     os.environ.get("BIOMARKER_SWEEP_THREADS"))

    def power(pro_times, raw_cache, _x, **kw):
        seen.add(threading.get_ident())
        import time; time.sleep(0.05)
        return ([raw_cache["v"] * 2], {"10": {"n_pro": 3}}, [1.0], None, None, False)

    def sweep(power, pain_values, **kw):
        return {"grid": list(power), "channel": kw["channel"]}

    B._band_time_sweep_power_by_seconds = power
    analytics.band_time_sweep_from_power = sweep
    os.environ["BIOMARKER_SWEEP_THREADS"] = str(threads)
    try:
        out = B._band_time_sweep_channels(
            {"ZERO_TWO_LEFT": {"v": 1}, "ONE_THREE_LEFT": {"v": 2}, "EMPTY": {},
             "ZERO_TWO_RIGHT": {"v": 3}},
            [1.0, 2.0], tol_s=60, allow_window_reuse=False, pain_values=[1, 2],
            label_strategy="median", low_pct=33, high_pct=67, outlier_n_mad=5,
            outlier_scale=1.0, metric_key="m", metric_label="m")
    finally:
        B._band_time_sweep_power_by_seconds = old_power
        analytics.band_time_sweep_from_power = old_sweep
        if old_env is None:
            os.environ.pop("BIOMARKER_SWEEP_THREADS", None)
        else:
            os.environ["BIOMARKER_SWEEP_THREADS"] = old_env
    for v in out.values():
        v.pop("matched_seconds", None); v.pop("total_seconds", None)
    return out, seen


def test_pairs_swept_in_threads_equal_the_one_after_another_answers_in_the_same_order():
    serial, seen1 = _run(1)
    threaded, seen4 = _run(4)
    assert list(serial) == list(threaded) == ["ZERO_TWO_LEFT", "ONE_THREE_LEFT", "ZERO_TWO_RIGHT"]
    assert serial == threaded
    assert [serial[k]["grid"] for k in serial] == [[2], [4], [6]]
    assert len(seen1) == 1 and len(seen4) == 3
