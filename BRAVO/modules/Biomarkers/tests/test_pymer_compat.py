"""Real lme4 regression; run in the BRAVO appliance with pymer4/R installed."""

import os
import sys
import unittest

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from Biomarkers.routines.pymer_compat import fit_lmer


class TestPymerCompatibility(unittest.TestCase):
    def test_band_validation_succeeds_on_request_thread(self):
        from concurrent.futures import ThreadPoolExecutor
        from Biomarkers.routines import analytics
        # Import embedded R on the main thread, as the application does.
        from pymer4.models import Lmer  # noqa: F401

        rng = np.random.default_rng(917)
        power = rng.normal(size=480)
        labels = power + rng.normal(scale=2, size=480)
        detail = {"f_set": [19, 20, 21], "psd": np.repeat(power[:, None, None], 3, axis=2),
                  "labels": labels, "chan_order": ["ONE_THREE_LEFT"], "prelog": True,
                  "times": pd.date_range("2025-01-01", periods=480, freq="6h").astype(str).tolist()}
        with ThreadPoolExecutor(max_workers=1) as pool:
            result = pool.submit(analytics.band_mixedmodel_inference, detail,
                                 "ONE_THREE_LEFT", 20.0).result(timeout=60)
        self.assertTrue(result.get("available"), result)
        for key in ("odds_ratio", "or_lo", "or_hi", "p"):
            self.assertTrue(np.isfinite(result[key]), result)
        self.assertLessEqual(result["or_lo"], result["odds_ratio"])
        self.assertGreaterEqual(result["or_hi"], result["odds_ratio"])
        self.assertEqual(result["excluded_first_weeks"], 3)

    def test_real_binomial_fit_matches_unadapted_inference(self):
        # The unadapted pandas-3 fit fails only after computing these fixed-effect
        # statistics. Compare them to prove this repair changes formatting only.
        from pymer4.models import Lmer
        from rpy2.robjects import default_converter
        from rpy2.robjects.conversion import localconverter

        rng = np.random.default_rng(831)
        cluster = np.repeat(np.arange(16), 30)
        power = rng.normal(size=len(cluster))
        intercepts = rng.normal(scale=0.8, size=16)
        eta = 0.6 * power + intercepts[cluster]
        data = pd.DataFrame({"pain_high": rng.binomial(1, 1 / (1 + np.exp(-eta))),
                             "band_power": power, "cluster": cluster})
        original_columns = data.copy(deep=True)
        formula = "pain_high ~ band_power + (1|cluster)"
        original_fit = Lmer.fit
        original_bridge = original_fit.__globals__["R2pandas"]
        had_applymap = hasattr(pd.DataFrame, "applymap")
        with localconverter(default_converter):
            original = Lmer(formula, data=data, family="binomial")
            if had_applymap:
                original.fit(summarize=False)
            else:
                with self.assertRaisesRegex(AttributeError, "applymap"):
                    original.fit(summarize=False)
            repaired = Lmer(formula, data=data, family="binomial")
            fit_lmer(repaired, summarize=False)

        self.assertTrue(repaired.fitted)
        self.assertFalse(repaired.ranef_var.empty)
        fields = ["Estimate", "SE", "OR", "Z-stat", "P-val", "2.5_ci", "97.5_ci"]
        np.testing.assert_allclose(repaired.coefs[fields].to_numpy(dtype=float),
                                   original.coefs[fields].to_numpy(dtype=float),
                                   rtol=1e-12, atol=1e-12)
        self.assertTrue(np.isfinite(float(repaired.coefs.loc["band_power", "OR"])))
        self.assertIs(Lmer.fit, original_fit)
        self.assertIs(Lmer.fit.__globals__["R2pandas"], original_bridge)
        self.assertEqual(hasattr(pd.DataFrame, "applymap"), had_applymap)
        pd.testing.assert_frame_equal(data, original_columns)


if __name__ == "__main__":
    unittest.main()
