"""Decision 336 (the PI, 2026-09-27): a "tertile" analysis is saved once, not twice under two
different keys, no matter where the percentile sliders were last left.

Before this fix, dragging the low/high sliders and then switching the strategy dropdown back to
"tertile" left the request carrying whatever numbers the sliders were dragged to
(`PercentileLow`/`PercentileHigh`), even though a tertile split always uses the fixed 33.3333/66.6667
percentiles and never reads them (`Biomarkers/routines/analytics.py`'s `_binarize_labels` and
`_pain_split` already force this: `lo_q = 33.3333 if strategy == "tertile" else float(low_pct)`).
`label_strategy_params` returned those leftover slider numbers unchanged, so two computationally
identical tertile requests produced two different settings tags (`sweep_settings_tag_from_request`)
and so two different stored entries under `KEEP_NEWEST_BY_KIND`'s per-kind cap: a wasted, duplicate
copy on disk for the same analysis.
"""
import pathlib
import sys

MODULES_DIR = pathlib.Path(__file__).resolve().parents[2]
if str(MODULES_DIR) not in sys.path:
    sys.path.insert(0, str(MODULES_DIR))

from Biomarkers.routines import sweep_settings as ss


def test_tertile_ignores_leftover_slider_positions():
    plain = ss.label_strategy_params({"LabelStrategy": "tertile"})
    dragged = ss.label_strategy_params(
        {"LabelStrategy": "tertile", "PercentileLow": 40.0, "PercentileHigh": 61.0})
    assert plain == ("tertile", 33.3333, 66.6667)
    assert dragged == plain


def test_tertile_settings_tag_is_the_same_no_matter_the_leftover_sliders():
    base = ss.sweep_settings_tag_from_request({"LabelStrategy": "tertile", "SweepMetric": "nrs"})
    dragged = ss.sweep_settings_tag_from_request(
        {"LabelStrategy": "tertile", "SweepMetric": "nrs",
         "PercentileLow": 12.0, "PercentileHigh": 88.0})
    assert base == dragged


def test_percentile_strategy_still_reads_the_sliders():
    """The fix touches only "tertile"; a real percentile split still uses its own cuts."""
    a = ss.label_strategy_params(
        {"LabelStrategy": "percentile", "PercentileLow": 20, "PercentileHigh": 80})
    b = ss.label_strategy_params(
        {"LabelStrategy": "percentile", "PercentileLow": 10, "PercentileHigh": 90})
    assert a == ("percentile", 20.0, 80.0)
    assert b == ("percentile", 10.0, 90.0)
    assert a != b
