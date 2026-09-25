"""Speed-up item 1 (the PI, 2026-09-25): the three-second tiles are built in batches, with every value
identical to the piece-at-a-time build it replaces.

The reference below is the TD-tile loop exactly as it stood before the change (availability.py,
`raw_lsb_spectrum_cache`, 2026-09-24): one transform call and one Python row per 3 s piece. The
batched build must return the same tile times, the same rows (None where there is no value), the
same saturated / ok flags and the same finite-signal seconds, bit for bit, on constructed traces
that exercise every branch: gaps, a trace touching the rail, a trailing partial piece, missing-packet
flags, pieces with too little signal, and more pieces than one batch holds. Plain asserts; container suite.
"""
import numpy as np

from modules.Biomarkers.routines import analytics, availability as AV


def _reference(col, miss, fs, t0, centers, *, window_s=3.0, max_missing_frac=0.10,
               saturation_uv=AV.PRO_LSB_SATURATION_UV, half=2.5):
    out = {"t": [], "lsb": [], "saturated": [], "n_finite_s": [], "ok": []}
    nsamp = col.shape[0]; nC = centers.size
    win_tile = int(round(fs * window_s))
    step_sub = int(round(fs * analytics.TRANSFORM_STEP_SECONDS))
    min_finite = int(round(fs * analytics.TRANSFORM_WIN_SECONDS))
    for start in range(0, nsamp, win_tile):
        end = min(start + win_tile, nsamp)
        seg = col[start:end]
        seg_miss = miss[start:end] if miss is not None else None
        fin = np.isfinite(seg); n_fin = int(fin.sum())
        t_center = t0 + ((start + end) / 2.0) / fs
        row = [None] * nC; saturated = False; ok = False
        if n_fin >= min_finite:
            miss_frac = (float(np.mean(seg_miss)) if seg_miss is not None and seg_miss.size
                         else 1.0 - n_fin / max(seg.size, 1))
            if np.nanmax(np.abs(seg)) >= saturation_uv:
                saturated = True
            elif miss_frac <= max_missing_frac:
                bp = np.atleast_1d(analytics.td_transform_band_power(
                    seg, fs, centers, half_hz=half, step_samples=step_sub, agg="median"))
                lsb = np.where(np.isfinite(bp) & (bp > 0), analytics.LSB_PER_UV2_TRANSFORM * bp, np.nan)
                row = [float(v) if np.isfinite(v) else None for v in lsb]
                ok = any(v is not None for v in row)
        out["t"].append(float(t_center)); out["lsb"].append(row); out["saturated"].append(bool(saturated))
        out["n_finite_s"].append(round(n_fin / fs, 3)); out["ok"].append(bool(ok))
    return out


def _trace(seed, n):
    rng = np.random.default_rng(seed)
    col = rng.normal(0, 8, n)
    col[1000:1400] = np.nan                                  # a gap: a partly finite and a too-short piece
    col[5000:5003] = np.nan                                  # a few dropped samples inside one piece
    col[7000] = AV.PRO_LSB_SATURATION_UV + 1.0               # the rail
    miss = np.zeros(n, dtype=int); miss[9000:9200] = 1       # a dropped-packet span over the 10% limit
    return col, miss


def test_the_batched_tiles_equal_the_piece_at_a_time_tiles_bit_for_bit():
    centers = np.arange(2.5, 100.0, 1.0)
    for seed, n, with_miss in ((0, 12_345, True), (1, 750 * 5000 + 400, False)):   # the second: >4096 pieces
        col, miss = _trace(seed, n)
        m = miss if with_miss else None
        ref = _reference(col, m, 250.0, 1.75e9, centers)
        rec = {"ChannelNames": ["ZERO_TWO_LEFT"], "Data": col[:, None], "SamplingRate": 250.0,
               "StartTime": 1.75e9, "Missing": m}
        got = AV.raw_lsb_spectrum_cache("ZERO_TWO_LEFT", centers, td_recordings=[rec])["td"]
        for k in ("t", "saturated", "n_finite_s", "ok"):
            assert got[k] == ref[k], k
        assert len(got["lsb"]) == len(ref["lsb"])
        for a, b in zip(got["lsb"], ref["lsb"]):
            assert a == b
        assert any(ref["saturated"]) and not all(ref["ok"]) and any(ref["ok"])


def test_the_batched_transform_equals_the_single_call_on_every_row():
    rng = np.random.default_rng(5)
    S = rng.normal(0, 5, (300, 750))
    centers = np.arange(2.5, 100.0, 1.0)
    ref = np.array([analytics.td_transform_band_power(s, 250.0, centers, step_samples=125, agg="median") for s in S])
    got = analytics.td_transform_band_power_batch(S, 250.0, centers, step_samples=125)
    assert np.array_equal(ref, got)
