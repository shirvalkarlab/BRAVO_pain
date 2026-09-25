"""Saved control analyses are records: every run is kept, the page reads the newest per analysis,
and a run's file is complete or absent (the PI, 2026-09-24). Plain asserts; runs in both suites."""
import json
import os
import tempfile

try:
    from modules.ControlAnalyses import snapshots as SN, registry as RG
except ImportError:
    from ControlAnalyses import snapshots as SN, registry as RG


def test_every_run_is_kept_and_the_page_gets_the_newest_of_each_of_its_analyses():
    with tempfile.TemporaryDirectory() as root:
        SN.save("uid/../1", "zero_ma_within_stretch", {"v": 1}, settings={"s": 1}, data_through="2026-09-01",
                run_at="2026-09-24T10:00:00Z", root=root)
        SN.save("uid/../1", "zero_ma_within_stretch", {"v": 2}, settings={"s": 1}, data_through="2026-09-23",
                run_at="2026-09-24T11:00:00Z", root=root)
        SN.save("uid/../1", "current_with_memory", {"v": 3}, settings={}, data_through="2026-09-23",
                run_at="2026-09-24T12:00:00Z", root=root)
        page = SN.page_payload("uid/../1", "biomarkers", root=root)
        keys = [e["key"] for e in page["analyses"]]
        assert "zero_ma_within_stretch" in keys and "current_with_memory" not in keys
        z = next(e for e in page["analyses"] if e["key"] == "zero_ma_within_stretch")
        assert z["snapshot"]["result"] == {"v": 2} and z["n_runs"] == 2
        assert z["literature"] and all(l["url"].startswith("https://") for l in z["literature"])
        for dirpath, _d, files in os.walk(root):                       # the uid never escapes the root
            assert os.path.abspath(dirpath).startswith(os.path.abspath(root))
            assert not any(f.endswith(".tmp") for f in files)


def test_an_analysis_never_run_is_listed_as_not_run_yet():
    with tempfile.TemporaryDirectory() as root:
        page = SN.page_payload("p", "stim_optimizer", root=root)
        memory = next(e for e in page["analyses"] if e["key"] == "current_with_memory")
        assert memory["snapshot"] is None and memory["n_runs"] == 0


def test_an_unknown_analysis_is_refused_by_name():
    with tempfile.TemporaryDirectory() as root:
        try:
            SN.save("p", "no_such_analysis", {}, settings={}, data_through="x", root=root)
        except KeyError as e:
            assert "no_such_analysis" in str(e)
        else:
            raise AssertionError("saved an analysis the registry does not know")


def test_every_registered_analysis_names_its_page_title_and_literature():
    for key, a in RG.ANALYSES.items():
        assert a["page"] in RG.PAGES and a["title"] and a["literature"], key
