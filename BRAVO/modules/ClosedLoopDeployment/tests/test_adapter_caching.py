"""Does the caching actually avoid work, and does it actually notice when the data changes?

Every test here exists because of something that went wrong or could go wrong silently, and the
docstrings say which. Two properties are being defended and they pull in opposite directions:

  * a second identical request must do no arithmetic, and
  * a request whose underlying data has changed must do all of it again.

A cache that fails the first is merely slow. A cache that fails the second hands a clinician
figures computed from a testing sheet that has since been corrected, while reporting itself as
verified, and nobody goes looking for the problem because nothing raised. That asymmetry is why
several of these tests check that something RAISES rather than that it returns a marker.
"""
import numpy as np
import pandas as pd
import pytest

from ClosedLoopDeployment import adapter as AD


# ---------------------------------------------------------------------------------------------
# fixtures in the real shapes
# ---------------------------------------------------------------------------------------------
def _psd_frame(n=6):
    """One row per sample and channel, with a whole spectrum per row, as the real frame is."""
    t0 = pd.Timestamp("2026-01-01T00:00:00Z")
    f_set = np.arange(8.0, 31.0, 1.0)
    return pd.DataFrame([
        {"t": float((t0 + pd.Timedelta(minutes=5 * k)).timestamp()), "channel": "ZERO_THREE_LEFT",
         "source": "td", "log_psd": np.sin(f_set) + float(k), "freqs": f_set}
        for k in range(n)])


def _epoch_frame():
    t0 = pd.Timestamp("2026-01-01T00:00:00Z")
    return pd.DataFrame({"t_start": [t0], "t_end": [t0 + pd.Timedelta(hours=1)],
                         "amp_mA_Left": [2.0], "amp_mA_Right": [2.0], "freq_hz": [165.0],
                         "pw_us_Left": [60.0], "dur_h": [1.0], "epoch": [1.0]})


@pytest.fixture(autouse=True)
def _isolate_caches(tmp_path, monkeypatch):
    """Point the shared files at a directory of this test's own and empty every memo.

    Without this the tests would read and write the platform's real cache directory, which would
    make them depend on whatever the server had cached and would let one test's file satisfy
    another test's request. The default when Django is not configured is already "no directory",
    so this is belt and braces, but the tests that check the shared files need a real directory to
    look at.
    """
    monkeypatch.setattr(AD, "_SHARED_CACHE_DIR_OVERRIDE", str(tmp_path / "shared"))
    AD.clear_inputs_cache()
    AD.clear_joined_cache()
    AD.clear_response_cache()
    AD.clear_shared_cache()
    yield
    AD.clear_inputs_cache()
    AD.clear_joined_cache()
    AD.clear_response_cache()
    AD.clear_shared_cache()


# ---------------------------------------------------------------------------------------------
# the fingerprint must fail loudly rather than narrow quietly
# ---------------------------------------------------------------------------------------------
def test_a_column_that_is_not_on_the_frame_raises_instead_of_being_skipped():
    """The trap this whole file is built around, and it has already been fallen into once.

    The first version of the fingerprint skipped names it could not find. It was handed three
    column names that do not exist on the real spectral frame, so it hashed two columns instead of
    five, reported its own mode as "hashed", and then did not change when the spectra changed. The
    cache it keyed would have served figures computed from recordings that had since been decoded
    again, and would have looked verified while doing it.
    """
    psd = _psd_frame()
    with pytest.raises(AD.MissingFingerprintColumn) as e:
        AD._frame_fingerprint(psd, ("t", "channel", "log_power"))
    assert "log_power" in str(e.value), "the error must name the column that is missing"
    assert "freqs" in str(e.value), "and list what the frame does have, so the fix is obvious"
    # the same on a name that is merely mistyped, which is how this arises in practice
    with pytest.raises(AD.MissingFingerprintColumn):
        AD._frame_fingerprint(psd, ("t", "chanel"))


def test_a_group_of_alternative_spellings_needs_one_of_them_and_no_more():
    """Two spellings of the delivered current are real in this codebase, so one must satisfy the
    key; none must not."""
    eps = _epoch_frame().rename(columns={"amp_mA_Left": "amp_Left"})
    fp = AD._frame_fingerprint(eps, ("t_start",), either=(("amp_mA_Left", "amp_Left"),))
    assert dict(fp[2])["amp_Left"], "the spelling that IS present must be the one hashed"
    with pytest.raises(AD.MissingFingerprintColumn):
        AD._frame_fingerprint(eps, ("t_start",), either=(("nope_Left", "nope_Right"),))


def test_one_sided_implant_is_allowed_but_a_frame_with_no_current_at_all_is_not():
    """The distinction between "does not apply to this participant" and "missing".

    A participant implanted on one side has no right-hand current column and that is a normal
    state. A frame with no current column at all is the failure that once made the joined table
    come back with nothing in its current columns while raising nothing anywhere.
    """
    one_side = _epoch_frame().drop(columns=["amp_mA_Right"])
    fp = AD._frame_fingerprint(one_side, ("t_start",),
                               at_least_one=(("amp_mA_Left", "amp_mA_Right"),))
    assert [c for c, _ in fp[2]] == ["t_start", "amp_mA_Left"]
    with pytest.raises(AD.MissingFingerprintColumn):
        AD._frame_fingerprint(one_side.drop(columns=["amp_mA_Left"]), ("t_start",),
                              at_least_one=(("amp_mA_Left", "amp_mA_Right"),))


def test_an_optional_column_leaves_its_presence_or_absence_in_the_key():
    """Optional columns are still allowed, but an absence must now leave a trace.

    The old function's silence about absent columns is what made the original mistake invisible.
    Hashing pulse width when it is there and not when it is absent is fine; the two cases must
    simply not produce the same key, or a frame that has lost a column would be served the other
    one's cached result.
    """
    eps = _epoch_frame()
    with_pw = AD._frame_fingerprint(eps, ("t_start",), also=("pw_us_Left",))
    without_pw = AD._frame_fingerprint(eps.drop(columns=["pw_us_Left"]), ("t_start",),
                                       also=("pw_us_Left",))
    assert with_pw != without_pw, "losing an optional column must change the key"
    assert ("pw_us_Left", True) in with_pw[3]
    assert ("pw_us_Left", False) in without_pw[3]


def test_a_column_of_arrays_is_hashed_over_its_bytes_and_not_given_up_on():
    """Pandas cannot hash a column whose values are arrays; it raises.

    The spectral frame holds a whole spectrum per row, so this is not an unusual case here, it is
    the main case. Answering the exception by dropping the column would put the frame's shape in
    the key in place of the numbers, and a re-decoded recording keeps its shape.
    """
    psd = _psd_frame()
    fp = AD._frame_fingerprint(psd, ("t", "channel", "log_psd", "freqs"))
    assert fp[0] == "hashed", "not 'degraded' — the array columns must really have been hashed"
    assert len(fp[2]) == 4

    changed = psd.copy()
    changed.at[0, "log_psd"] = np.asarray(changed.at[0, "log_psd"], float) + 10.0
    assert AD._frame_fingerprint(changed, ("t", "channel", "log_psd", "freqs")) != fp, \
        "a change in the spectra alone must move the key"

    # every value is hashed, not merely the first: change the LAST row only
    tail = psd.copy()
    tail.at[len(tail) - 1, "log_psd"] = np.asarray(tail.at[len(tail) - 1, "log_psd"], float) + 3.0
    assert AD._frame_fingerprint(tail, ("t", "channel", "log_psd", "freqs")) != fp


def test_arrays_of_differing_lengths_are_still_hashed_value_by_value():
    """Spectra of unequal length cannot be stacked into one block, and the fallback must hash them
    rather than skip them. A montage recording at a different sampling rate produces exactly this.
    """
    ragged = pd.DataFrame({"t": [1.0, 2.0],
                           "log_psd": [np.arange(5.0), np.arange(9.0)]})
    fp = AD._frame_fingerprint(ragged, ("t", "log_psd"))
    assert fp[0] == "hashed"
    moved = ragged.copy()
    moved.at[1, "log_psd"] = np.arange(9.0) + 1.0
    assert AD._frame_fingerprint(moved, ("t", "log_psd")) != fp


def test_a_column_that_cannot_be_hashed_says_so_in_the_key_itself():
    """If some column type defeats both paths, the weakening has to be visible in the key.

    A key that quietly falls back to a row count while still looking like a content hash is the
    condition that makes staleness undetectable, so the marker and the column name go into the key
    where anyone comparing two keys will see them.
    """
    # Lists of text look like array values, so they take the byte-hashing path, and text cannot be
    # cast to a float by either the stacked route or the value-by-value fallback.
    df = pd.DataFrame({"t": [1.0, 2.0], "odd": [["a"], ["b", "c"]]})
    fp = AD._frame_fingerprint(df, ("t",), also=("odd",))
    assert fp[0] == "degraded", "the key must announce that a column went unhashed"
    assert [c for c, _ in fp[3]] == ["odd"], "and name which column it was"
    assert fp[3][0][1] == "ValueError", "and what stopped it"
    # The rest of the frame is still hashed, so the key is weakened rather than useless.
    assert [c for c, _ in fp[2]] == ["t"]
    other = pd.DataFrame({"t": [1.0, 9.0], "odd": [["a"], ["b", "c"]]})
    assert AD._frame_fingerprint(other, ("t",), also=("odd",)) != fp


def test_a_fingerprint_over_no_columns_is_refused():
    """Naming nothing would produce a key that is a row count in disguise."""
    with pytest.raises(ValueError):
        AD._frame_fingerprint(_psd_frame(), ())


def test_a_frame_of_none_is_a_state_and_not_an_error():
    """No epoch frame at all is legitimate and must be distinguishable from every real frame."""
    assert AD._frame_fingerprint(None, ("t",)) == ("none",)


# ---------------------------------------------------------------------------------------------
# the joined table
# ---------------------------------------------------------------------------------------------
def test_the_joined_table_signature_survives_a_real_epoch_frame_and_a_one_sided_one():
    """The signature must not raise on the frames the platform actually produces.

    Requiring columns is only safe if the required ones are genuinely always there. The epoch
    builder guarantees the times and the rate; it does not guarantee both sides' currents, which is
    why those are named as a group rather than individually. If this test fails, the endpoint
    raises on a real participant, which is far worse than a slow one.
    """
    psd, eps = _psd_frame(), _epoch_frame()
    AD._joined_signature(psd, eps, (20.5,), 5.0)
    AD._joined_signature(psd, eps.drop(columns=["amp_mA_Right", "pw_us_Left"]), (20.5,), 5.0)
    AD._joined_signature(psd, eps.rename(columns={"amp_mA_Left": "amp_Left",
                                                  "amp_mA_Right": "amp_Right"}), (20.5,), 5.0)
    AD._joined_signature(psd, None, (20.5,), 5.0)


def test_a_second_identical_request_for_the_joined_table_does_no_work():
    psd, eps = _psd_frame(), _epoch_frame()
    first = AD.joined_table_cached(psd, eps)
    second = AD.joined_table_cached(psd, eps)
    assert first is second, "the very same object, so nothing was rebuilt"
    assert AD.joined_cache_stats()["entries"] == 1


def test_the_joined_table_is_rebuilt_when_a_value_changes_without_the_shape_changing():
    psd, eps = _psd_frame(), _epoch_frame()
    first = AD.joined_table_cached(psd, eps)
    corrected = eps.copy()
    corrected.loc[0, "amp_mA_Left"] = 2.5           # one corrected current, same row count
    assert AD.joined_table_cached(psd, corrected) is not first


def test_the_joined_table_memo_evicts_the_oldest_entry_and_stays_bounded():
    """Each entry is a frame of over a hundred thousand rows on the real record, so the memo has to
    stay small however many different inputs pass through it."""
    psd = _psd_frame()
    for k in range(AD._JOINED_MEMO_MAX + 3):
        eps = _epoch_frame()
        eps.loc[0, "amp_mA_Left"] = 1.0 + 0.25 * k
        AD.joined_table_cached(psd, eps)
    assert AD.joined_cache_stats()["entries"] == AD._JOINED_MEMO_MAX


# ---------------------------------------------------------------------------------------------
# the files that let the four worker processes share one result
# ---------------------------------------------------------------------------------------------
def test_no_directory_means_memory_only_and_not_a_failure(monkeypatch):
    """The unit tests and any script running without the platform configured have nowhere to write,
    and that must simply mean the files are not used.

    UPDATED 2026-09-10, the same correction the Biomarkers twin of this test received on
    2026-09-07 (`test_shared_raw_lsb_cache.test_no_directory_means_memory_only_and_is_not_an_error`).
    It used to create the condition by clearing this module's directory override and stubbing
    `shared_cache_dir` -- which only removes the override; the store's own resolver then falls
    through to Django's `DATASERVER_PATH`, so on a configured machine (the live container, where
    the host suite has been run since decision 84) the write really LANDED in the production
    cache and, worse, its cleanup step evicted a real participant's current entry (decision 84's
    own finding). It failed on every such run for that reason and passed only where Django had no
    path at all. The store carries an explicit off switch for exactly this condition; that is what
    the test now expresses, so it means the same thing on every machine and writes nothing anywhere.

    AND THE OVERRIDE IS DELIBERATELY LEFT ALONE. The old version also set this module's directory
    override to None, and that was the destructive half: pytest undoes a monkeypatch only AFTER the
    autouse fixture's teardown has run, and that teardown calls `clear_shared_cache()` -- so with
    the override at None it cleared the PRODUCTION cache root, deleting every closed-loop entry the
    page had stored, on every run of this suite inside the container. The ledger on 2026-09-10
    showed the page writing its `inputs` entry five times in one day and the directory empty each
    time the suite had run since. With the off switch alone, `shared_cache_dir()` is None for the
    duration of the test and the teardown's clear reaches nothing.
    """
    try:
        from modules.CacheStore import store as _cs
    except ImportError:
        from CacheStore import store as _cs
    monkeypatch.setattr(_cs, "ENABLED", False)
    assert AD.shared_cache_dir() is None
    assert AD._shared_store("inputs", ("k",), "v") is False
    assert AD._shared_load("inputs", ("k",)) is None


def test_the_stored_format_version_is_part_of_the_file_name():
    """So that code which changes what it stores never reads a file written by the older shape."""
    p1 = AD._shared_path("inputs", ("k",))
    assert f".v{AD._SHARED_CACHE_FORMAT}." in p1


def test_writing_one_participants_entry_does_not_evict_another_participants(monkeypatch):
    """The bug found while running the host suite inside the live container (decision 84/85): every
    call into `_shared_store`/`_shared_load` used to pass `participant_uid=None` regardless of which
    participant it was actually for, so the store's own cleanup step (`_sweep_superseded`, which
    groups by `participant_uid`, not by the signature it never sees) treated every participant's
    entry of a kind as interchangeable "shared" clutter -- a fresh build for one participant deleted
    every OTHER participant's still-current cached entry of the same kind.

    `evidence_inputs_cached`'s real call sites now pass the real participant_uid; this test pins the
    property directly on the lower-level `_shared_store`/`_shared_load` functions those calls go
    through, with two participants whose SIGNATURES differ (as real signatures always do, via
    `recording_set_signature`'s own embedded participant field) but who previously shared one
    eviction group regardless.
    """
    assert AD._shared_store("inputs", ("participant-A-sig",), "payload for A",
                            participant_uid="participant-A") is True
    assert AD._shared_store("inputs", ("participant-B-sig",), "payload for B",
                            participant_uid="participant-B") is True
    # Before the fix, writing B's entry would have swept A's away too -- both used the same
    # ".shared." marker regardless of the real participant. Confirm A survives B's write.
    assert AD._shared_load("inputs", ("participant-A-sig",), participant_uid="participant-A") \
        == "payload for A"
    assert AD._shared_load("inputs", ("participant-B-sig",), participant_uid="participant-B") \
        == "payload for B"
    # And a SECOND write for A (a real rebuild, e.g. after a new upload) still only sweeps A's own
    # stale entries, never touching B's.
    assert AD._shared_store("inputs", ("participant-A-sig-v2",), "payload for A, rebuilt",
                            participant_uid="participant-A") is True
    assert AD._shared_load("inputs", ("participant-B-sig",), participant_uid="participant-B") \
        == "payload for B", "participant A's rebuild must not evict participant B's entry"
    assert AD._shared_load("inputs", ("participant-A-sig",), participant_uid="participant-A") \
        is None, "participant A's OWN superseded entry should still be swept"


def test_evidence_inputs_cached_stores_under_the_real_participant_not_shared(monkeypatch, live_inputs):
    """`evidence_inputs_cached` itself, not just the lower-level helpers, must pass the real
    participant through -- this is the actual call site the live container's cache-eviction side
    effect (decision 84) traced back to."""
    AD.evidence_inputs_cached("PARTICIPANT")
    d = AD.shared_cache_dir()
    import os
    files = [f for f in os.listdir(d) if f.endswith(".pkl")]
    assert files, "expected a stored inputs entry"
    assert any(".PARTICIPANT." in f for f in files), (
        f"expected the real participant id in the stored file name, got {files!r} -- "
        "a bare '.shared.' name here means the eviction bug is back")
    assert not any(".shared." in f for f in files)


# ---------------------------------------------------------------------------------------------
# THE PARTICIPANT'S STORED PERCEPT FILES ARE READ ONCE PER COLD BUILD, NOT TWICE
# ---------------------------------------------------------------------------------------------
#: WHY THESE TESTS EXIST. `evidence_inputs_cached` needs two things from StimOptimizer: the pair of
#: assembled spectra and exposure epochs, and the epoch-level design matrix. Each of those two calls
#: used to build the dated settings stream for itself, which means reading, decrypting and parsing
#: every stored Percept file the participant has. On participant RCS08 that is 1,136 files and about
#: 34 seconds, and it was happening twice on a genuinely cold build. This function now builds that
#: frame once and hands the same object to both calls. The tests below check the call count, and
#: separately check that the three things the function returns are unchanged by the sharing, because
#: a page that got faster while reporting a different estimate would be much worse than a slow page.
def _settings_stream_frame():
    """A settings stream in exactly the columns StimOptimizer.adapter.settings_stream returns."""
    rows = []
    for hours, amp, pw in ((0.0, 2.0, 60.0), (6.0, 3.0, 60.0), (12.0, 3.0, 90.0)):
        t = pd.Timestamp("2026-01-01T00:00:00Z") + pd.Timedelta(hours=hours)
        for hemi in ("Left", "Right"):
            rows.append({"t": t, "src": "history", "hemi": hemi, "amp": amp, "pw": pw,
                         "rate": 150.0, "upper": 5.0, "cathode": "1-2", "schema": "hemisphere"})
    return pd.DataFrame(rows)


def _pain_report_frame():
    t0 = pd.Timestamp("2026-01-01T00:00:00Z")
    return pd.DataFrame([{"t_utc": t0 + pd.Timedelta(hours=h), "nrs": v, "vas": v * 10.0}
                         for h, v in ((1.0, 7.0), (2.0, 6.0), (7.0, 4.0),
                                      (8.0, 5.0), (13.0, 3.0), (14.0, 2.0))])


@pytest.fixture
def live_inputs(monkeypatch):
    """Wire up a cold build that touches no database, and count the file reads.

    Three things stand in for the platform. The identity of the set of recordings, which normally
    asks the database, becomes a fixed value so the cache key is stable. The Biomarkers service,
    which the two StimOptimizer functions reach for by the name ``modules.Biomarkers.bravo_service``,
    becomes a small stand-in holding the three things they call. And the settings stream builder is
    replaced by a counter that hands back a fixed frame, which is what makes the duplicate read
    visible at all, since the frame that comes back is identical either way.

    Everything else is the real code: the real ``evidence_inputs``, the real ``build_design_matrix``,
    and the real caching in this module.
    """
    import sys
    import types

    from StimOptimizer import adapter as SA

    calls = []

    def counting_settings_stream(participant, **kwargs):
        calls.append((participant, dict(kwargs)))
        return _settings_stream_frame()

    bravo_service = types.ModuleType("modules.Biomarkers.bravo_service")
    bravo_service._cached_psd_matrix = lambda uid, force_refresh=None: {}
    bravo_service._load_pros = lambda request_data, participant: _pain_report_frame()
    bravo_service._pro_times_utc_series = lambda df: df["t_utc"]
    pkg_biomarkers = types.ModuleType("modules.Biomarkers")
    pkg_biomarkers.bravo_service = bravo_service
    pkg_modules = types.ModuleType("modules")
    pkg_modules.Biomarkers = pkg_biomarkers
    monkeypatch.setitem(sys.modules, "modules", pkg_modules)
    monkeypatch.setitem(sys.modules, "modules.Biomarkers", pkg_biomarkers)
    monkeypatch.setitem(sys.modules, "modules.Biomarkers.bravo_service", bravo_service)

    monkeypatch.setattr(SA, "settings_stream", counting_settings_stream)
    monkeypatch.setattr(AD, "recording_set_signature",
                        lambda participant: ("PARTICIPANT", 1, 1, "a fixed content hash"))
    return calls


def test_a_cold_build_reads_the_percept_files_only_once(live_inputs):
    """The saving itself. Two calls need the same settings stream and only one read happens."""
    AD.evidence_inputs_cached("PARTICIPANT")
    assert len(live_inputs) == 1, (
        "the participant's stored Percept files were read %d times in one cold build; "
        "the point of the change is that they are read once" % len(live_inputs))


def test_the_one_frame_that_is_built_is_asked_for_with_no_extra_arguments(live_inputs):
    """If this function asked for a different frame from the one the two StimOptimizer functions
    build for themselves, then sharing it would change what they saw."""
    AD.evidence_inputs_cached("PARTICIPANT")
    assert live_inputs == [("PARTICIPANT", {})]


def test_sharing_one_frame_gives_the_same_three_results_as_building_two(live_inputs, monkeypatch):
    """The result must be unchanged, not merely faster.

    The comparison is against the two functions called separately, each building its own frame,
    which is exactly what this module used to do.
    """
    from StimOptimizer import adapter as SA

    psd_shared, eps_shared, dm_shared = AD.evidence_inputs_cached("PARTICIPANT")
    n_after_shared = len(live_inputs)

    psd_apart, eps_apart = SA.evidence_inputs("PARTICIPANT")
    dm_apart = SA.build_design_matrix("PARTICIPANT")

    assert n_after_shared == 1
    assert len(live_inputs) == 3, "the two separate calls should each have read the files"
    assert psd_shared is None and psd_apart is None
    assert len(eps_shared) == 3, f"expected three exposure epochs, got {len(eps_shared)}"
    pd.testing.assert_frame_equal(eps_shared, eps_apart)
    assert len(dm_shared) == 3, f"expected three design matrix rows, got {len(dm_shared)}"
    pd.testing.assert_frame_equal(dm_shared, dm_apart)


def test_a_second_request_reads_nothing_at_all(live_inputs):
    """The file cache that was already in place, still working on top of the change."""
    AD.evidence_inputs_cached("PARTICIPANT")
    AD.evidence_inputs_cached("PARTICIPANT")
    AD.clear_inputs_cache()                     # forget this process's memory, keep the files
    AD.evidence_inputs_cached("PARTICIPANT")
    assert len(live_inputs) == 1


def test_asking_for_a_refresh_rebuilds_and_reads_once_not_twice(live_inputs):
    AD.evidence_inputs_cached("PARTICIPANT")
    AD.evidence_inputs_cached("PARTICIPANT", force_refresh=True)
    assert len(live_inputs) == 2
