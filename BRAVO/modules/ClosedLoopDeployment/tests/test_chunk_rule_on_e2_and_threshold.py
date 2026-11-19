"""The 7-MAD-above rule for single 3 s chunks on two Closed-Loop paths (the PI, 2026-10-03,
decision 412): the band-vs-pain AUC (E2) and the capture pair of threshold placement.

Decision 410 drops a chunk's value at a band when it sits more than 7 median absolute deviations
above that contact's own median at that band; decision 411 judges the device PSD snapshots against
their own bound. Until this change the Closed-Loop joined table (one row per chunk and band) kept
every chunk. The PI chose which Closed-Loop readings get the rule: E2 and the threshold placement
do; E1 (power against current), the device replays, the three-source panels and the Stim Optimizer
evidence do not. So the rule is applied to a copy of the joined table that only E2 and the capture
pair read, never inside the table itself.

The bound is built from every usable chunk of the contact (`analytics.chunk_upper_bounds`, the
heat maps' own population), never from the rows a caller happens to hold.
"""
import numpy as np
import pandas as pd

try:
    from modules.ClosedLoopDeployment import adapter as AD, pipeline as PL, edges as E
    from modules.ClosedLoopDeployment import authority as AU
    from modules.Biomarkers.routines import analytics as AN
    from modules.StimOptimizer.routines import lfp_evidence as EV
except ImportError:                                              # pragma: no cover - host spelling
    from ClosedLoopDeployment import adapter as AD, pipeline as PL, edges as E
    from ClosedLoopDeployment import authority as AU
    from Biomarkers.routines import analytics as AN
    from StimOptimizer.routines import lfp_evidence as EV

CH = "ZERO_TWO_LEFT"
CENTERS = [8.5, 12.5, 16.5, 20.5]
FC = 20.5
T0 = 1_750_000_000.0
N_EPOCHS = 12
EPOCH_S = 60.0
AMPS = [1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5]
PAIN = [6, 5, 5, 4, 3, 2, 7, 6, 4, 4, 2, 3]


def _cache(seed=0):
    """One contact's tile cache: 20 TD chunks per setting, a few huge spikes, and PSD snapshots on
    their own (larger) scale, one of them a spike too."""
    rng = np.random.default_rng(seed)
    n = N_EPOCHS * 20
    td_t = [T0 + 1.5 + 3.0 * k for k in range(n)]
    lsb = []
    for k in range(n):
        amp = AMPS[k // 20]
        base = 400.0 - 40.0 * amp + 10.0 * PAIN[k // 20]
        lsb.append([float(base + j + rng.normal(0, 8.0)) for j in range(len(CENTERS))])
    for k in (5, 47, 101, 166, 230):                             # spikes far above the median
        lsb[k] = [v * 40.0 for v in lsb[k]]
    lsb[60][0] = -9000.0                                         # far BELOW: never dropped
    psd_t = [T0 + 10.0 + 30.0 * k for k in range(N_EPOCHS * 2)]
    psd = [[float(5000.0 + 20.0 * (k % 4) + j) for j in range(len(CENTERS))]
           for k in range(len(psd_t))]
    psd[3] = [v * 30.0 for v in psd[3]]
    return {"channel": CH, "centers_hz": [float(c) for c in CENTERS], "band_half_hz": 2.5,
            "window_s": 3.0,
            "td": {"t": td_t, "lsb": lsb, "saturated": [False] * n, "ok": [True] * n,
                   "source": ["constructed"] * n, "n_finite_s": [3.0] * n},
            "psd": {"t": psd_t, "lsb": psd, "calibrated": [[True] * len(CENTERS)] * len(psd_t),
                    "source": ["constructed_psd"] * len(psd_t)},
            "n_td_windows": n, "n_psd_windows": len(psd_t)}


def _epochs():
    t0 = pd.Timestamp(T0, unit="s", tz="UTC")
    return pd.DataFrame({
        "t_start": [t0 + pd.Timedelta(seconds=EPOCH_S * i) for i in range(N_EPOCHS)],
        "t_end": [t0 + pd.Timedelta(seconds=EPOCH_S * (i + 1)) for i in range(N_EPOCHS)],
        "amp_mA_Left": AMPS, "amp_mA_Right": [np.nan] * N_EPOCHS,
        "freq_hz": [55.0] * N_EPOCHS, "pw_us_Left": [60.0] * N_EPOCHS,
        "dur_h": [EPOCH_S / 3600.0] * N_EPOCHS, "epoch": [float(i + 1) for i in range(N_EPOCHS)]})


def _pro():
    return pd.DataFrame({"epoch": [float(i + 1) for i in range(N_EPOCHS)],
                         "report_id": [f"r{i}" for i in range(N_EPOCHS)],
                         "nrs": [float(p) for p in PAIN]})


def _frame(cache):
    return EV.frame_from_lsb_cache({CH: cache})


CAND = [{"channel": CH, "center_hz": FC, "band_width_hz": 5.0}]


def test_the_joined_table_carries_each_rows_family():
    T = AD.joined_table(_frame(_cache()), _epochs(), centers=(FC,))
    assert set(T["family"].unique()) == {EV.FAMILY_TIME_DOMAIN, EV.FAMILY_DEVICE_SPECTRUM}
    assert (T["family"] == EV.FAMILY_DEVICE_SPECTRUM).sum() == N_EPOCHS * 2


def test_the_bounds_are_the_heat_maps_own_for_each_family():
    cache = _cache()
    b = AD.chunk_bounds_for_candidates({CH: cache}, CAND)
    td = AN.chunk_upper_bounds(cache, [FC])[0]
    psd = AN.chunk_upper_bounds(cache, [FC], family="psd")[0]
    assert b[CH]["td"][FC] == td and b[CH]["psd"][FC] == psd
    assert td < 1000.0 < psd                                    # two scales, two bounds


def test_a_contact_with_no_cache_gets_no_bounds():
    assert AD.chunk_bounds_for_candidates({}, CAND) == {}
    assert AD.chunk_bounds_for_candidates({CH: _cache()}, [{"channel": None}]) == {}


def test_rows_above_their_own_familys_bound_are_dropped_and_low_rows_kept():
    cache = _cache()
    T = AD.joined_table(_frame(cache), _epochs(), centers=tuple(CENTERS))
    n_before = len(T)
    bounds = AD.chunk_bounds_for_candidates({CH: cache}, [{"channel": CH, "center_hz": c}
                                                         for c in CENTERS])
    K = AD.drop_chunks_above_bounds(T, bounds)
    assert len(T) == n_before, "the shared joined table is never changed in place"
    is_psd = T["family"] == EV.FAMILY_DEVICE_SPECTRUM
    bound = np.array([bounds[CH]["psd" if p else "td"][c] for p, c in zip(is_psd, T["center_hz"])])
    want_drop = T["power_linear"].to_numpy() > bound
    assert len(K) == n_before - int(want_drop.sum())
    # every TD spike at every band (5 chunks x 4 bands), the PSD spike at every band (4)
    assert int((want_drop & ~is_psd).sum()) == 20 and int((want_drop & is_psd).sum()) == 4
    assert (K["power_linear"] == -9000.0).sum() == 1, "a chunk far below the median stays"
    assert K.attrs["chunk_rule"]["n_td_rows_dropped"] == 20
    assert K.attrs["chunk_rule"]["n_psd_rows_dropped"] == 4
    # the PSD snapshots on their own scale stay: judged by the TD bound every one would go
    assert int(((K["family"] == EV.FAMILY_DEVICE_SPECTRUM)).sum()) == N_EPOCHS * 2 * 4 - 4


def test_a_contact_without_bounds_passes_untouched():
    T = AD.joined_table(_frame(_cache()), _epochs(), centers=(FC,))
    K = AD.drop_chunks_above_bounds(T, {"OTHER_CONTACT": {"td": {FC: 0.0}, "psd": {FC: 0.0}}})
    assert len(K) == len(T)


def _runs():
    cache = _cache()
    f, e = _frame(cache), _epochs()
    bounds = AD.chunk_bounds_for_candidates({CH: cache}, CAND)
    plain = PL.run("P", psd_frame=f, epochs=e, pro_frame=_pro(), candidates=CAND,
                   hemisphere="Left")
    ruled = PL.run("P", psd_frame=f, epochs=e, pro_frame=_pro(), candidates=CAND,
                   hemisphere="Left", chunk_bounds=bounds)
    T = AD.joined_table_cached(f, e, pro_frame=_pro(),
                               centers=tuple(sorted(set(AD.DEFAULT_BAND_CENTERS_HZ) | {FC})))
    return plain, ruled, T, AD.drop_chunks_above_bounds(T, bounds)


def test_e2_reads_the_table_after_the_rule():
    plain, ruled, T, K = _runs()
    want = E.state_edge(K, channel=CH, center_hz=FC, outcome="nrs", scale="power_linear",
                        adjust_for_column="amp_mA_Left")
    old = E.state_edge(T, channel=CH, center_hz=FC, outcome="nrs", scale="power_linear",
                       adjust_for_column="amp_mA_Left")
    got = ruled.edges["E2"]
    assert (got.estimate, got.ci, got.n) == (want.estimate, want.ci, want.n)
    assert got.n < old.n, "the dropped chunks are no longer samples"
    p = plain.edges["E2"]
    assert (p.estimate, p.ci, p.n) == (old.estimate, old.ci, old.n), "no bounds: as before"


def test_the_capture_pair_reads_the_table_after_the_rule():
    plain, ruled, T, K = _runs()
    full = T[(T.channel == CH) & np.isclose(T.center_hz, FC)].dropna(subset=["power_linear"])
    lo = full["amp_mA_Left"][full["amp_mA_Left"] > 0].min()
    hi = full["amp_mA_Left"].max()
    d = K[(K.channel == CH) & np.isclose(K.center_hz, FC)].dropna(subset=["power_linear"])
    amps = d["amp_mA_Left"].astype(float)
    want = AU.threshold_placement(d.loc[(amps > 0) & (amps <= lo), "power_linear"].to_numpy(),
                                  d.loc[(amps > 0) & (amps >= hi), "power_linear"].to_numpy(),
                                  amp_low=float(lo), amp_high=float(hi), expected_sign=-1,
                                  observed_series=d["power_linear"].to_numpy())
    assert (ruled.threshold.upper, ruled.threshold.lower) == (want.upper, want.lower)
    assert (ruled.threshold.upper, ruled.threshold.lower) != \
        (plain.threshold.upper, plain.threshold.lower), "a spike sits in a capture setting"


def test_e1_and_the_in_report_replay_are_not_given_the_rule():
    plain, ruled, _T, _K = _runs()
    a, b = plain.edges["E1"], ruled.edges["E1"]
    assert (a.estimate, a.ci, a.n) == (b.estimate, b.ci, b.n)
    # the replay runs on every row (the device has no outlier ceiling); only the thresholds it is
    # run against moved, so its input series is the same length
    assert plain.replay is not None and ruled.replay is not None


def test_the_counts_ride_on_the_manifest():
    _plain, ruled, _T, _K = _runs()
    cr = ruled.manifest["chunk_rule"]
    assert cr["n_td_rows_dropped"] == 5 and cr["n_psd_rows_dropped"] == 1
    assert cr["applies_to"] == ["E2", "threshold capture pair"]


def test_the_report_hands_the_bounds_to_the_run():
    import inspect
    src = inspect.getsource(AD)
    call = src[src.index("rep = _pl.run("):]
    call = call[:call.index(")\n")]
    assert "chunk_bounds=" in call
