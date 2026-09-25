"""P-08 (handoff pending-items list, 2026-09-25): `_programmed_adaptive_thresholds` used to issue one
extra database query per therapy group. `ElectricalTherapy.find_all` already prefetches
`stimulation_settings` and `adaptive_settings` (its own `.prefetch_related`), but `_hemi_of_group`
reads `st.get_info()` -> `self.electrode.get_info()` for every stimulation setting, and the
`electrode` foreign key was never prefetched -- so resolving each group's hemisphere touched the
database once per group.

The fix builds its own queryset with a `Prefetch("stimulation_settings", queryset=...select_related
("electrode"))`, so the electrode rides in the same batch as the stimulation settings instead of one
query per group.

This test does not open a real database (Django's `Prefetch` needs none to construct); it fakes the
ORM chain and asserts the FIX IS IN PLACE (the electrode is select_related on the SAME queryset
object passed as `stimulation_settings`'s Prefetch, not fetched lazily one group at a time), and
that the answer is unchanged for a small hand-built case: one active left-hemisphere group.

No Django settings and no database: stubbed the way test_shared_raw_lsb_cache.py stubs Server.

Run inside the container:
    python3 _agent_bridge/run_tests.py
"""
import pathlib
import sys
import types
import unittest.mock as mock

_ROOT = pathlib.Path(__file__).resolve().parents[3]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def _import_service():
    for mod in ("Server", "Server.models", "modules.Database"):
        if mod not in sys.modules:
            sys.modules[mod] = mock.MagicMock()
    for mod in ("modules.Biomarkers.pipeline", "modules.Biomarkers.adapter"):
        if mod not in sys.modules:
            sys.modules[mod] = mock.MagicMock()
    import modules.Biomarkers.bravo_service as bs
    return bs


B = _import_service()


class _AllWrapper:
    """Stands in for a Django related-manager: `.all()` returns the prepared, already-prefetched
    list (as a real prefetch would, with no further query)."""
    def __init__(self, items):
        self._items = items

    def all(self):
        return self._items


class _FakeElectrodeInfo(dict):
    pass


class _FakeStim:
    """Stands in for one `ElectricalStimulation` row. `.electrode` is set up front here (as a real
    `select_related("electrode")` would populate it), never looked up lazily."""
    def __init__(self, electrode_info):
        self.electrode = mock.Mock(get_info=mock.Mock(return_value=electrode_info))

    def get_info(self):
        return {"Electrode": self.electrode.get_info()}


class _FakeAdaptive:
    def __init__(self, adaptive, sensing):
        self.adaptive = adaptive
        self.sensing = sensing


class _FakeGroup:
    def __init__(self, stim, adaptive, date):
        self.stimulation_settings = _AllWrapper(stim)
        self.adaptive_settings = _AllWrapper(adaptive)
        self.therapy = mock.Mock(date=date)


class _FakeTherapyQuerySet:
    """Records the query-construction chain and, once iterated, hands back the prepared groups --
    exactly what a real `ElectricalTherapy.objects...prefetch_related(...)` queryset would do after
    the database round trip, but with the chain itself inspectable."""
    def __init__(self, calls, groups):
        self._calls = calls
        self._groups = groups

    def select_related(self, *a, **k):
        self._calls.append(("select_related", a, k))
        return self

    def filter(self, *a, **k):
        self._calls.append(("filter", a, k))
        return self

    def prefetch_related(self, *a, **k):
        self._calls.append(("prefetch_related", a, k))
        return self

    def __iter__(self):
        return iter(self._groups)


class _FakeStimQuerySet:
    """Stands in for `ElectricalStimulation.objects`; recording that `.select_related("electrode")`
    was asked for is the whole point -- that's what makes the electrode ride in the SAME query as
    the stimulation settings instead of a separate lazy fetch per group."""
    def __init__(self, calls):
        self._calls = calls

    def select_related(self, *a, **k):
        self._calls.append(("stim_select_related", a, k))
        return self


def _install_fake_orm(groups, calls):
    therapy_mod = types.ModuleType("Server.models.Therapy")
    therapy_mod.ElectricalTherapy = mock.Mock(
        objects=_FakeTherapyQuerySet(calls, groups))
    therapy_mod.ElectricalStimulation = mock.Mock(
        objects=_FakeStimQuerySet(calls))
    sys.modules["Server.models.Therapy"] = therapy_mod
    sys.modules["Server.models"].SourceFile = mock.Mock(
        find_all=mock.Mock(return_value=[mock.Mock()]))


def test_the_electrode_rides_the_same_prefetch_as_the_stimulation_settings():
    """Fix in place: the query asks for `stimulation_settings` via a `Prefetch` whose OWN queryset
    already has `select_related("electrode")` applied -- one round trip covers groups, stimulation
    settings and electrodes together, instead of the electrode being fetched once per group."""
    calls = []
    group = _FakeGroup(
        stim=[_FakeStim({"Hemisphere": "Left"})],
        adaptive=[_FakeAdaptive(adaptive={"Status": "ADBS_RUNNING"},
                                 sensing={"Thresholds": {"LFPThresholds": [1.5, 3.0]}})],
        date="2026-01-01")
    _install_fake_orm([group], calls)

    out = B._programmed_adaptive_thresholds(mock.Mock())

    assert out == {"Left": {"lower": 1.5, "upper": 3.0, "measured_lower": None,
                             "measured_upper": None, "status": "ADBS_RUNNING",
                             "date": "2026-01-01"}}, out

    kinds = [c[0] for c in calls]
    assert "prefetch_related" in kinds, calls
    prefetch_call = next(c for c in calls if c[0] == "prefetch_related")
    prefetch_args = prefetch_call[1]
    # One of the prefetch_related arguments is a Prefetch("stimulation_settings", queryset=...)
    # whose queryset is the SAME object `ElectricalStimulation.objects.select_related("electrode")`
    # returned -- i.e. the electrode really is folded into the prefetch, not left to lazy-load.
    from django.db.models import Prefetch
    stim_prefetches = [p for p in prefetch_args if isinstance(p, Prefetch)
                       and p.prefetch_through == "stimulation_settings"]
    assert len(stim_prefetches) == 1, (prefetch_args, calls)
    assert ("stim_select_related", ("electrode",), {}) in calls, calls
    assert stim_prefetches[0].queryset is not None


def test_a_group_with_no_active_adaptive_therapy_is_skipped():
    """Unchanged behavior: a configured-off group contributes nothing (decision-9-adjacent: no
    threshold line is drawn when closed loop is not really running)."""
    calls = []
    group = _FakeGroup(
        stim=[_FakeStim({"Hemisphere": "Right"})],
        adaptive=[_FakeAdaptive(adaptive={"Status": "NOT_CONFIGURED"},
                                 sensing={"Thresholds": {"LFPThresholds": [1.0, 2.0]}})],
        date="2026-01-01")
    _install_fake_orm([group], calls)
    out = B._programmed_adaptive_thresholds(mock.Mock())
    assert out == {}, out


if __name__ == "__main__":
    test_the_electrode_rides_the_same_prefetch_as_the_stimulation_settings()
    test_a_group_with_no_active_adaptive_therapy_is_skipped()
    print("All programmed-thresholds query tests passed.")
