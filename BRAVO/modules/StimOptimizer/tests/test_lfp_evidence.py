"""Band power in the closed-loop module comes from the lab's calibrated tiles, not from a density.

WHAT THESE TESTS PROTECT. The Biomarkers module already computes band power on the device's own
number scale and stores it in three-second tiles, and it does the multiplication that puts it on
that scale inside itself, where it is calibrated. The closed-loop module used to ignore those tiles
and build its own band power by undoing a stored logarithm and integrating a power density, which
nobody had ever calibrated, so its numbers sat about two hundred times below the device's own while
being labelled as being in the device's units.

The change these tests cover is a change of RECIPE and not a change of a constant. There is no new
number anywhere in the closed-loop module, and one of the tests below asserts that by looking at
what the module actually holds rather than by taking anyone's word for it.

Three of the tests exist for one specific trap. The stored band centres sit one hertz apart and
each stored value already covers five hertz, so neighbouring stored values overlap each other by
four fifths of their width. Adding two of them together, or averaging them, would count almost the
same signal twice and would inflate the result while still returning something finite and
plausible. So there is a test that a returned band power is exactly the one stored column, a test
that asking for a wider band raises instead of combining columns, and a test that a centre sitting
between two stored centres is reported as unavailable rather than rounded onto the grid.
"""
import enum
import inspect
import sys
import types

import numpy as np
import pandas as pd
import pytest

from StimOptimizer import adapter as AD
from StimOptimizer.routines import lfp_evidence as EV


# =================================================================================================
# fixtures in the shape the real cache has
# =================================================================================================
#: The band centres the real cache stores inside the range a sensing band can be programmed in:
#: one hertz apart, each of them the centre of a band five hertz wide.
CENTERS = np.arange(8.5, 29.6, 1.0)

#: The moment the fixtures start, and the length of one tile, both matching the real record.
T0 = 1_760_000_000.0
TILE_S = 3.0

CHANNEL = "ZERO_TWO_LEFT"


def _tile_values(n_rows, centers=CENTERS):
    """Band power that is different in every cell, so a test can tell which cell it got back.

    Row i and centre j hold ``100 + 10*i + j``. Nothing about these numbers is physical; they exist
    so that reading the wrong column or the wrong row cannot pass silently.
    """
    i = np.arange(n_rows)[:, None]
    j = np.arange(len(centers))[None, :]
    return 100.0 + 10.0 * i + j


def _as_rows(mat):
    """A float matrix -> the cache's own list of lists, with None where a value is missing."""
    return [[None if not np.isfinite(v) else float(v) for v in row] for row in np.asarray(mat)]


def _cache_entry(*, td_t, td_lsb, td_ok=None, td_saturated=None,
                 psd_t=(), psd_lsb=None, psd_calibrated=None,
                 centers=CENTERS, half=2.5, window=TILE_S, channel=CHANNEL):
    """One sensing contact's entry, in exactly the keys ``raw_lsb_spectrum_cache`` returns."""
    n_td = len(td_t)
    n_psd = len(psd_t)
    return {
        "channel": channel,
        "centers_hz": [float(c) for c in centers],
        "window_s": float(window),
        "band_half_hz": float(half),
        "td": {"t": [float(t) for t in td_t],
               "lsb": _as_rows(td_lsb),
               "saturated": list(td_saturated if td_saturated is not None else [False] * n_td),
               "source": ["BrainSense streaming"] * n_td,
               "n_finite_s": [float(window)] * n_td,
               "ok": list(td_ok if td_ok is not None else [True] * n_td)},
        "psd": {"t": [float(t) for t in psd_t],
                "lsb": _as_rows(psd_lsb if psd_lsb is not None
                                else np.zeros((0, len(centers)))),
                "calibrated": [[bool(x) for x in row] for row in
                               (psd_calibrated if psd_calibrated is not None
                                else np.zeros((0, len(centers)), bool))],
                "source": ["Montage PSD"] * n_psd},
        "n_td_windows": n_td, "n_psd_windows": n_psd}


def _epochs():
    """Two exposure epochs at one stimulation rate and two delivered currents.

    Two currents is the minimum the response test can work with, and one rate is required because
    the stimulation artifact scales with rate, so the module refuses to pool them.
    """
    s = pd.to_datetime(T0, unit="s", utc=True)
    return pd.DataFrame([
        dict(t_start=s - pd.Timedelta(seconds=10), t_end=s + pd.Timedelta(seconds=100),
             amp_mA_Left=1.6, amp_mA_Right=2.0, freq_hz=55.0, pw_us_Left=60.0, visit=1),
        dict(t_start=s + pd.Timedelta(seconds=100), t_end=s + pd.Timedelta(seconds=300),
             amp_mA_Left=3.0, amp_mA_Right=2.0, freq_hz=55.0, pw_us_Left=60.0, visit=2)])


def _plain_cache(n_rows=20, **kw):
    """Twenty tiles, ten inside each exposure epoch, with no device readings at all."""
    t = T0 + np.arange(n_rows) * 10.0
    return {CHANNEL: _cache_entry(td_t=t, td_lsb=_tile_values(n_rows), **kw)}


def _frame(cache):
    return EV.frame_from_lsb_cache(cache)


def _build(cache, **kw):
    return EV.build_evidence(_frame(cache), _epochs(), channel=CHANNEL, hemisphere="Left",
                             rate_hz=55.0, era_col="visit", **kw)


# =================================================================================================
# the values are READ, not built
# =================================================================================================
def test_the_calibrated_values_are_read_and_nothing_is_integrated(monkeypatch):
    """The whole point of the change.

    Two things are asserted together. The band power handed to the response test is exactly the
    number the cache stored for that tile and that band centre, to the last bit. And the old routine
    that undoes a logarithm and integrates a density is never called at all -- it is replaced here
    by one that raises, so if any part of this path still reached for it the test would fail loudly
    rather than quietly producing a number on the wrong scale.
    """
    def _must_not_be_called(*a, **k):
        raise AssertionError("band power was integrated from a density instead of being read "
                             "from the calibrated cache")

    monkeypatch.setattr(EV, "band_power_linear", _must_not_be_called)

    ev, aud = _build(_plain_cache())
    assert ev is not None, aud.reason_unusable
    assert aud.band_power_source == EV.BAND_POWER_FROM_CALIBRATED_CACHE

    stored = _tile_values(20)
    j = int(np.flatnonzero(np.isclose(CENTERS, 10.5))[0])
    got = ev.power_for(10.5, 5.0)
    assert got is not None
    # Every row, exactly, in the order the tiles were stored.
    np.testing.assert_array_equal(got, stored[:, j])


def test_the_evidence_says_where_each_number_came_from():
    """A reader holding only the evidence object has to be able to tell which of the two routes
    produced any particular number, because they are two different measurements of the same thing.
    """
    ev, aud = _build(_plain_cache())
    assert getattr(ev, "band_power_source", None) == EV.BAND_POWER_FROM_CALIBRATED_CACHE
    tiers = getattr(ev, "band_power_tier", None)
    assert tiers, "the evidence carries no record of where its numbers came from"
    key = (10.5, 5.0)
    assert set(np.unique(tiers[key])) == {int(EV.BandPowerTier.TIME_DOMAIN_TRANSFORM)}
    # And the audit counts the same thing in words a reader can read without a lookup table.
    label = EV.TIER_LABELS[EV.BandPowerTier.TIME_DOMAIN_TRANSFORM]
    assert aud.values_by_tier[label] == 20 * 18


def test_band_power_linear_is_still_there_for_its_other_callers():
    """It stops being the route this module's evidence takes; it does not stop existing. Other
    callers and its own decibel-convention test use it and it is a correct primitive.
    """
    assert callable(EV.band_power_linear)
    got = EV.band_power_linear(np.array([[np.log10(2.0), np.log10(8.0)]]),
                               np.array([10.0, 11.0]), 10.5, 2.0, log_scale="log10")
    assert got[0] == pytest.approx(10.0)


# =================================================================================================
# the device's own reading wins
# =================================================================================================
def test_the_devices_own_reading_wins_over_the_modelled_one_for_the_same_tile_and_band():
    """The lab's own architecture decision, section 3.3: a modelled value never sets the number
    where the device's own reading exists. Here one device reading sits half a second from the
    fourth tile, and it is marked calibrated in one band only. That band must take the device's
    number; every other band on that tile must keep the number modelled from the raw samples; and
    every other tile must be untouched.
    """
    n = 20
    cache = _plain_cache(n)
    j = int(np.flatnonzero(np.isclose(CENTERS, 10.5))[0])
    cal = np.zeros((1, len(CENTERS)), bool)
    cal[0, j] = True
    device_value = 987654.0
    dev = np.full((1, len(CENTERS)), device_value)
    cache[CHANNEL] = _cache_entry(td_t=T0 + np.arange(n) * 10.0, td_lsb=_tile_values(n),
                                  psd_t=[T0 + 30.5], psd_lsb=dev, psd_calibrated=cal)

    ev, aud = _build(cache)
    stored = _tile_values(n)
    got = ev.power_for(10.5, 5.0)

    # The fourth tile is at T0+30 and the device read at T0+30.5, so they describe one moment.
    assert got[3] == device_value
    assert list(got[:3]) == list(stored[:3, j])
    assert list(got[4:]) == list(stored[4:, j])

    # A neighbouring band on that same tile was not marked calibrated, so it keeps its own value.
    j2 = int(np.flatnonzero(np.isclose(CENTERS, 11.5))[0])
    assert ev.power_for(11.5, 5.0)[3] == stored[3, j2]

    tiers = ev.band_power_tier[(10.5, 5.0)]
    assert tiers[3] == int(EV.BandPowerTier.DEVICE_ONBOARD_SPECTRUM)
    assert set(np.unique(np.delete(tiers, 3))) == {int(EV.BandPowerTier.TIME_DOMAIN_TRANSFORM)}

    # The reading described a tile, so it did not also become a row of its own: the row count is
    # still one per tile.
    assert aud.n_device_rows == 1
    assert aud.n_device_rows_merged_into_a_tile == 1
    assert aud.n_device_rows_standing_alone == 0
    assert len(got) == n


def test_a_device_reading_the_lab_does_not_mark_calibrated_never_sets_a_number():
    """Outside the range the lab validated, the device-spectrum route is exploratory rather than
    calibrated, and an exploratory value must not be the number a deployment decision rests on.
    """
    n = 20
    cal = np.zeros((1, len(CENTERS)), bool)          # calibrated nowhere
    cache = {CHANNEL: _cache_entry(td_t=T0 + np.arange(n) * 10.0, td_lsb=_tile_values(n),
                                   psd_t=[T0 + 30.2],
                                   psd_lsb=np.full((1, len(CENTERS)), 987654.0),
                                   psd_calibrated=cal)}
    ev, aud = _build(cache)
    stored = _tile_values(n)
    j = int(np.flatnonzero(np.isclose(CENTERS, 10.5))[0])
    np.testing.assert_array_equal(ev.power_for(10.5, 5.0), stored[:, j])
    assert aud.values_by_tier.get(
        EV.TIER_LABELS[EV.BandPowerTier.DEVICE_ONBOARD_SPECTRUM], 0) == 0


def test_a_device_reading_far_from_any_tile_is_kept_as_a_row_of_its_own():
    """It describes no tile, so it replaces nothing -- but throwing it away would discard exactly
    the measurement the preference rule says is preferred. It becomes its own row, carrying a value
    only in the bands it is calibrated for.
    """
    n = 20
    j = int(np.flatnonzero(np.isclose(CENTERS, 10.5))[0])
    cal = np.zeros((1, len(CENTERS)), bool)
    cal[0, j] = True
    cache = {CHANNEL: _cache_entry(td_t=T0 + np.arange(n) * 10.0, td_lsb=_tile_values(n),
                                   psd_t=[T0 + 55.0],       # five seconds from the nearest tile
                                   psd_lsb=np.full((1, len(CENTERS)), 987654.0),
                                   psd_calibrated=cal)}
    ev, aud = _build(cache)
    assert aud.n_device_rows_standing_alone == 1
    assert aud.n_device_rows_merged_into_a_tile == 0
    got = ev.power_for(10.5, 5.0)
    assert len(got) == n + 1
    assert 987654.0 in list(got)
    # In a band it is not calibrated for, that extra row holds no number rather than a modelled one.
    assert np.isnan(ev.power_for(11.5, 5.0)[list(got).index(987654.0)])


# =================================================================================================
# quality flags
# =================================================================================================
def test_a_tile_at_the_converters_rail_is_dropped_and_counted():
    """A tile whose raw samples hit the rail is not a measurement of the brain, so it must be
    dropped rather than used, and the drop must be visible in the audit rather than silent.
    """
    n = 20
    sat = [False] * n
    sat[5] = True
    cache = _plain_cache(n, td_saturated=sat)
    ev, aud = _build(cache)
    stored = _tile_values(n)
    j = int(np.flatnonzero(np.isclose(CENTERS, 10.5))[0])
    got = ev.power_for(10.5, 5.0)
    assert aud.n_dropped_saturated_tile == 1
    assert len(got) == n - 1
    assert stored[5, j] not in list(got)


def test_a_tile_the_cache_could_not_score_is_dropped_and_counted():
    n = 20
    ok = [True] * n
    ok[7] = False
    ev, aud = _build(_plain_cache(n, td_ok=ok))
    assert aud.n_dropped_unusable_tile == 1
    assert aud.n_dropped_saturated_tile == 0
    assert len(ev.power_for(10.5, 5.0)) == n - 1


def test_a_bad_tile_cannot_swallow_the_devices_reading_for_that_moment():
    """The order matters. If bad tiles were dropped after the merge, a saturated tile would absorb
    the device's reading for that moment and the reading would disappear with it.
    """
    n = 20
    sat = [False] * n
    sat[3] = True
    j = int(np.flatnonzero(np.isclose(CENTERS, 10.5))[0])
    cal = np.zeros((1, len(CENTERS)), bool)
    cal[0, j] = True
    cache = {CHANNEL: _cache_entry(td_t=T0 + np.arange(n) * 10.0, td_lsb=_tile_values(n),
                                   td_saturated=sat, psd_t=[T0 + 30.4],
                                   psd_lsb=np.full((1, len(CENTERS)), 987654.0),
                                   psd_calibrated=cal)}
    ev, aud = _build(cache)
    assert aud.n_dropped_saturated_tile == 1
    assert aud.n_device_rows_standing_alone == 1
    assert 987654.0 in list(ev.power_for(10.5, 5.0))


def test_every_tile_being_bad_is_reported_rather_than_returning_an_empty_answer():
    ev, aud = _build(_plain_cache(20, td_ok=[False] * 20))
    assert ev is None
    assert "quality flags" in aud.reason_unusable


# =================================================================================================
# one stored column is one band, and neighbours are never combined
# =================================================================================================
def test_a_band_is_the_one_stored_column_and_never_a_sum_of_its_neighbours():
    """The trap this whole design is arranged around.

    The two bands either side of 10.5 Hz are loaded with a thousand while 10.5 itself holds seven.
    A recipe that summed the three neighbours would return about two thousand and seven, and one
    that averaged them would return about six hundred and seventy. The answer must be seven.
    """
    n = 20
    vals = _tile_values(n).astype(float)
    j = int(np.flatnonzero(np.isclose(CENTERS, 10.5))[0])
    vals[:, j - 1] = 1000.0
    vals[:, j] = 7.0
    vals[:, j + 1] = 1000.0
    ev, _ = _build({CHANNEL: _cache_entry(td_t=T0 + np.arange(n) * 10.0, td_lsb=vals)})
    got = ev.power_for(10.5, 5.0)
    assert set(np.unique(got)) == {7.0}


def test_asking_for_a_wider_band_raises_rather_than_combining_stored_columns():
    """Ten hertz cannot be served from five-hertz columns that overlap by four fifths of their
    width, so the request is refused with the reason rather than answered with an inflated number.
    """
    with pytest.raises(ValueError) as e:
        _build(_plain_cache(), bands=[(15.5, 10.0)])
    msg = str(e.value)
    assert "10 Hz wide" in msg and "5 Hz wide" in msg
    assert "neighbouring" in msg


def test_a_centre_between_two_stored_centres_is_reported_unavailable_not_rounded():
    """11.0 Hz sits exactly between the stored 10.5 and 11.5. Rounding it either way would answer a
    question that was not asked, and the two are equidistant so there is not even a nearest one.
    """
    ev, aud = _build(_plain_cache(), bands=[(10.5, 5.0), (11.0, 5.0)])
    assert aud.band_centres_unavailable == (11.0,)
    assert set(ev.band_power) == {(10.5, 5.0)}


def test_a_frame_cannot_be_built_for_a_centre_the_cache_does_not_hold():
    with pytest.raises(ValueError, match="not on the cache's grid"):
        EV.frame_from_lsb_cache(_plain_cache(), centers_hz=[11.0])


def test_the_default_bands_are_the_stored_centres_that_fit_inside_the_device_range():
    """A sensing band the device cannot place is not deployment evidence, so the default grid is
    every stored band lying entirely between 8 and 30 Hz -- eighteen of them, 10.5 to 27.5 Hz.
    """
    ev, _ = _build(_plain_cache())
    centres = sorted(c for c, _ in ev.band_power)
    assert centres == [float(c) for c in np.arange(10.5, 27.6, 1.0)]
    assert len(centres) == 18
    assert all(w == 5.0 for _, w in ev.band_power)


# =================================================================================================
# no new number anywhere
# =================================================================================================
def test_no_new_scale_constant_exists_in_either_file():
    """The constraint on this change, asserted against what the modules actually hold.

    A change of recipe was required and a change of a constant was forbidden, because each recipe
    has its own calibration and the lab has already calibrated the recipe the tiles use. So the two
    files touched here must hold no plain number that could be a scale factor. The check lists every
    plain number each module holds and requires the list to be exactly the three that were there
    for other reasons, which means any number added later has to be argued for here.
    """
    def plain_numbers(mod):
        out = {}
        for name in dir(mod):
            if name.startswith("__"):
                continue
            v = getattr(mod, name)
            if isinstance(v, bool) or isinstance(v, enum.IntEnum):
                continue
            if isinstance(v, (int, float)):
                out[name] = float(v)
        return out

    assert plain_numbers(EV) == {
        "DEFAULT_NATIVE_TOLERANCE_FRACTION_OF_TILE": 0.5,   # half a tile, not a scale
        "MIN_RESPONDING_BAND_FRACTION": 0.5,                # a majority of bands must respond
        "RECENT_ERAS_FOR_RESPONSE": 5.0}                    # how many recent eras to use
    assert plain_numbers(AD) == {}

    # The two calibration numbers belong to the Biomarkers module and are applied there. Neither
    # may appear here, and neither may the factor of about 215 that was measured and withdrawn.
    for mod in (EV, AD):
        for value in plain_numbers(mod).values():
            for forbidden in (352.62, 73.63123825433286, 215.0, 269.0, 100.0, 0.01):
                assert abs(value - forbidden) > 1e-6, (
                    f"{mod.__name__} holds {value}, which is the calibration number {forbidden}")
    assert not hasattr(EV, "DEVICE_UNITS_PER_INTEGRATED_BAND_POWER")

    # The decibel convention is a convention and not a calibration: ten is the base of the stored
    # logarithm, not a factor anyone measured.
    assert EV.LOG_SCALES == {"db10": 10.0, "log10": 1.0}


def test_the_calibration_numbers_are_only_ever_reached_through_the_cache():
    """Neither file may import the lab's calibration constants at all. The multiplication that puts
    band power on the device's scale happens inside the Biomarkers module; this module reads the
    result. Importing the numbers here would be the first step back to a second recipe.
    """
    for mod in (EV, AD):
        src = inspect.getsource(mod)
        for name in ("LSB_PER_UV2_TRANSFORM", "LSB_PER_DEVICE_PSD", "td_to_lsb",
                     "td_transform_band_power", "device_psd_band_power"):
            for line in src.splitlines():
                stripped = line.strip()
                if stripped.startswith("#") or name not in line:
                    continue
                assert not (stripped.startswith("import ") or stripped.startswith("from ")), (
                    f"{mod.__name__} imports {name}; the calibration must stay in Biomarkers")
                assert f"analytics.{name}" not in line and f"_an.{name}" not in line, (
                    f"{mod.__name__} calls {name} directly instead of reading the cache")


# =================================================================================================
# the adapter's contract
# =================================================================================================
def _fake_service(cache, *, offer_cache=True, channels=(CHANNEL,)):
    """A stand-in Biomarkers service holding only what ``evidence_inputs`` asks it for."""
    m = types.ModuleType("modules.Biomarkers.bravo_service")
    m.TIMEDOMAIN_TYPES = ["MedtronicBrainSenseTimeDomain"]
    m._cached_psd_matrix = lambda uid, force_refresh=None: {}
    if offer_cache:
        m._load_recordings = lambda uid, types_: [{"stand-in": True}]
        m._derive_chan_order = lambda td: list(channels)
        m._event_psd_lsb_blocks = lambda uid: []
        m._montage_psd_lsb_blocks = lambda uid: []
        m._raw_lsb_cache_cached = (lambda uid, chans, td, ev, montage_psd_blocks=None, **kw: cache)
    return m


def _install(monkeypatch, service, *, offer_range=True):
    """Put the stand-in service where ``evidence_inputs`` looks for it.

    The two frequency limits are installed as well, in the module the adapter reads them from,
    because the adapter must READ the lab's own limits rather than restate them and the test would
    otherwise exercise a path where they are absent.
    """
    analytics = types.ModuleType("modules.Biomarkers.routines.analytics")
    if offer_range:
        analytics.LSB_VALIDATED_HZ_LO = 7.8
        analytics.LSB_DEPLOYABLE_HZ_HI = 30.0
    routines = types.ModuleType("modules.Biomarkers.routines")
    routines.analytics = analytics
    pkg_b = types.ModuleType("modules.Biomarkers")
    pkg_b.bravo_service = service
    pkg_b.routines = routines
    pkg_m = types.ModuleType("modules")
    pkg_m.Biomarkers = pkg_b
    monkeypatch.setitem(sys.modules, "modules", pkg_m)
    monkeypatch.setitem(sys.modules, "modules.Biomarkers", pkg_b)
    monkeypatch.setitem(sys.modules, "modules.Biomarkers.bravo_service", service)
    monkeypatch.setitem(sys.modules, "modules.Biomarkers.routines", routines)
    monkeypatch.setitem(sys.modules, "modules.Biomarkers.routines.analytics", analytics)


def _stream():
    """A settings stream in the columns ``settings_stream`` returns, at one rate and two currents."""
    rows = []
    for hours, amp in ((0.0, 1.6), (2.0, 3.0)):
        t = pd.Timestamp("2026-01-01T00:00:00Z") + pd.Timedelta(hours=hours)
        for hemi in ("Left", "Right"):
            rows.append({"t": t, "src": "history", "hemi": hemi, "amp": amp, "pw": 60.0,
                         "rate": 55.0, "upper": 5.0, "cathode": "1-2", "schema": "hemisphere"})
    return pd.DataFrame(rows)


def test_evidence_inputs_still_returns_a_frame_and_the_epochs(monkeypatch):
    _install(monkeypatch, _fake_service(_plain_cache()))
    frame, epochs = AD.evidence_inputs("PARTICIPANT", stream=_stream())
    assert isinstance(frame, pd.DataFrame) and isinstance(epochs, pd.DataFrame)
    assert len(epochs) == 2
    assert EV._cal_center_columns(frame), "the frame carries no calibrated band power"
    assert set(frame["family"]) == {EV.FAMILY_TIME_DOMAIN}


def test_a_participant_with_no_sensing_gets_none_rather_than_an_exception(monkeypatch):
    """Settings but no sensing is a normal state, and the contract is to say so with None."""
    _install(monkeypatch, _fake_service({}, channels=()))
    frame, epochs = AD.evidence_inputs("PARTICIPANT", stream=_stream())
    assert frame is None and len(epochs) == 2


def test_a_service_that_cannot_supply_the_tiles_also_gets_none(monkeypatch):
    _install(monkeypatch, _fake_service({}, offer_cache=False))
    frame, epochs = AD.evidence_inputs("PARTICIPANT", stream=_stream())
    assert frame is None and len(epochs) == 2


def test_the_older_decibel_route_is_still_reachable_for_the_comparison(monkeypatch):
    """The before-and-after measurement of this change needs the frame the module used to build,
    so the old route stays available by name -- but it is no longer what a caller gets by default.
    """
    freqs = np.arange(1.0, 41.0, 1.0)
    service = _fake_service(_plain_cache())
    service._cached_psd_matrix = lambda uid, force_refresh=None: {
        "logX": np.full((4, freqs.size), -1.0), "t": T0 + np.arange(4) * 10.0,
        "channel": np.array([CHANNEL] * 4, dtype=object), "f_set": freqs}
    _install(monkeypatch, service)
    frame, _ = AD.evidence_inputs("PARTICIPANT", stream=_stream(),
                                  band_power=AD.BAND_POWER_DECIBEL_DENSITY)
    assert "log_psd" in frame.columns and not EV._cal_center_columns(frame)


def test_an_unknown_band_power_choice_raises_rather_than_picking_one(monkeypatch):
    _install(monkeypatch, _fake_service(_plain_cache()))
    with pytest.raises(ValueError, match="band_power must be"):
        AD.evidence_inputs("PARTICIPANT", stream=_stream(), band_power="whatever")


def test_the_stream_argument_still_stops_the_files_being_read_twice(monkeypatch):
    """The contract added earlier and which must survive this change: hand in the settings stream
    and the participant's stored files are not parsed again.
    """
    calls = []

    def _builder(participant, **kw):
        calls.append((participant, dict(kw)))
        return _stream()

    monkeypatch.setattr(AD, "settings_stream", _builder)
    _install(monkeypatch, _fake_service(_plain_cache()))

    AD.evidence_inputs("PARTICIPANT", stream=_stream())
    assert calls == []
    AD.evidence_inputs("PARTICIPANT")
    assert len(calls) == 1 and calls[0] == ("PARTICIPANT", {})

    p = inspect.signature(AD.evidence_inputs).parameters["stream"]
    assert p.default is None and p.kind is inspect.Parameter.KEYWORD_ONLY


def test_the_call_shapes_other_modules_use_still_bind():
    sig = inspect.signature(AD.evidence_inputs)
    sig.bind("PARTICIPANT")
    sig.bind("PARTICIPANT", force_refresh=None, sources=None)
    sig.bind("PARTICIPANT", stream=_stream())


def test_the_frame_only_carries_bands_the_device_could_actually_sense(monkeypatch):
    """Every stored centre from 2.5 to 99.5 Hz would be four times the frame, and nothing above
    30 Hz can be programmed as an adaptive sensing band, so the frame stops there.
    """
    wide = np.arange(2.5, 99.6, 1.0)
    cache = {CHANNEL: _cache_entry(td_t=T0 + np.arange(4) * 10.0,
                                   td_lsb=_tile_values(4, wide), centers=wide)}
    _install(monkeypatch, _fake_service(cache))
    frame, _ = AD.evidence_inputs("PARTICIPANT", stream=_stream())
    carried = [c for c, _, _ in EV._cal_center_columns(frame)]
    assert min(carried) >= 7.8 and max(carried) <= 30.0
    assert 10.5 in carried and 27.5 in carried


def test_a_hand_built_frame_without_the_quality_flags_is_refused():
    """The value columns alone are not enough. Without the quality flags and the band width, the
    dropping and the width check could not happen, so a frame like that must be refused by name
    rather than half-read.
    """
    frame = _frame(_plain_cache())
    stripped = frame.drop(columns=["tile_saturated", "band_half_hz"])
    with pytest.raises(KeyError) as e:
        EV.build_evidence(stripped, _epochs(), channel=CHANNEL, hemisphere="Left", rate_hz=55.0,
                          era_col="visit")
    assert "tile_saturated" in str(e.value) and "band_half_hz" in str(e.value)


def test_a_source_label_from_the_other_frame_raises_instead_of_filtering_everything_away():
    """The two routes label their recordings differently. A caller passing labels from the
    assembled-spectra frame would otherwise get an empty answer with no indication why.
    """
    with pytest.raises(ValueError, match="labels its recordings differently"):
        EV.frame_from_lsb_cache(_plain_cache(), sources=["BrainSenseTimeDomain"])


# --- 2026-09-06: two tests were here and were REMOVED the same night -----------------------------
# They pinned a scale factor of 215 that I had added to lfp_evidence.py and then reverted, after
# HANDOFF_TD_LSB_calibration_2026-06-27.md showed the constant contradicted a written architecture
# decision (one recipe, k = 352.62, for both the exploration panels and this module) and that my
# measurement of it reproduced a pairing error rather than a device property. Recorded rather than
# deleted silently, so that a reader who finds the factor discussed elsewhere can see it was
# withdrawn on purpose. The replacement is to source band power from the calibrated route
# (Biomarkers.routines.analytics.td_to_lsb), which is a change of DSP and not a change of constant,
# and it needs its own tests when it lands.


# --- the shared tile-cache file serves ARRAYS, not lists (regression, 2026-09-06) --------------
def test_frame_from_lsb_cache_accepts_a_family_whose_spectra_are_one_array():
    """A family restored from the Biomarkers shared tile-cache file holds its spectra as ONE float
    array rather than a list of lists, because that file stores them that way -- its read is eleven
    times faster than rebuilding 29 million separate Python numbers.

    `if not rows` inside `_matrix` raised ValueError("The truth value of an array with more than one
    element is ambiguous") on such a family, so `frame_from_lsb_cache` failed for any participant
    whose tiles came from the file rather than from a fresh build. It failed QUIETLY: the calibrated
    band-power route came back empty while the endpoint still returned arms from the other route, so
    the page looked normal and carried a thinner answer. Live confirmation after the fix:
    evidence_inputs on the calibrated route returned 304,478 rows where it had raised.

    Built from `_plain_cache()` so the shape is the module's own known-good one, and asserts the
    array form gives the IDENTICAL frame to the list form -- a faster path that changes a number is
    a defect, not a speedup.
    """
    import copy as _copy

    as_lists = _plain_cache()
    as_array = _copy.deepcopy(as_lists)
    # Convert ONLY the voltage-trace spectra, which is what the shared file turns into an array
    # (`_RAW_LSB_MATRICES = ("lsb",)` in Biomarkers.bravo_service). The device-spectrum family is
    # left as the list it already is, because a mixed family is exactly what a restored entry looks
    # like when one route has readings and the other has none.
    as_array[CHANNEL]["td"]["lsb"] = np.asarray(as_array[CHANNEL]["td"]["lsb"], float)
    assert isinstance(as_array[CHANNEL]["td"]["lsb"], np.ndarray)
    assert as_array[CHANNEL]["td"]["lsb"].ndim == 2

    got_array = EV.frame_from_lsb_cache(as_array)
    got_lists = EV.frame_from_lsb_cache(as_lists)
    assert len(got_array) > 0, "the array-backed family produced no rows"
    assert got_array.equals(got_lists), "the array form and the list form disagree"

    # A family with NOTHING in it must yield an empty result rather than raising. Note what is NOT
    # asserted here and why: dropping `lsb` while leaving 20 timestamps in place raises
    # ValueError("All arrays must be of the same length"), and that is CORRECT -- such a family is
    # internally inconsistent and pandas is right to refuse it. Only a consistently empty family is
    # a real case.
    empty = _copy.deepcopy(as_array)
    for fam in ("td", "psd"):
        empty[CHANNEL][fam].update({"t": [], "ok": [], "saturated": [], "source": [],
                                    "lsb": None})
    empty[CHANNEL]["psd"]["calibrated"] = []
    EV.frame_from_lsb_cache(empty)           # must not raise

    holed = _copy.deepcopy(as_array)
    holed[CHANNEL]["td"]["lsb"][0, 0] = np.nan
    g = EV.frame_from_lsb_cache(holed)
    assert g["band_power"].isna().any(), "a missing value became a number"
