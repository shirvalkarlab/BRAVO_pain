"""Every `stage1_openloop.<Name>` the Stim Optimizer's own code and tests name is a real attribute
of that module (2026-09-26). Three comments and docstrings still named `stage1_openloop.SliceResult`
-- the name of the per-slice result before the search went joint -- for the method that now lives on
`JointStratum` (`sd_of_difference`, `resolves_its_optimum`), so a reader following them found
nothing. Names in prose are read out of the source; nothing is imported by that name."""
import pathlib
import re

from StimOptimizer import stage1_openloop

ROOT = pathlib.Path(__file__).resolve().parents[1]
PATTERN = re.compile(r"stage1_openloop\.([A-Z][A-Za-z0-9_]*)")


def test_every_name_the_module_is_cited_by_exists():
    missing = {}
    for f in sorted(ROOT.rglob("*.py")):
        if f.name == pathlib.Path(__file__).name:
            continue
        for name in PATTERN.findall(f.read_text()):
            if not hasattr(stage1_openloop, name):
                missing.setdefault(name, []).append(str(f.relative_to(ROOT)))
    assert not missing, f"names cited as stage1_openloop.<Name> that it does not define: {missing}"
