"""The two figure-headline builders of the band-by-length sweep are gone, and with them the last
runtime wording that called the sweep's choice "best-of-ten".

`_sweep_headline_correlation` and `_sweep_headline_auc` built one-line headlines for the two
server-rendered heat-map figures. Decision 145 stopped drawing those figures (the page draws its own
heat maps from the grids), so from that day nothing but a test called either function; decision 170
then cut the sweep from ten lengths to nine, so the sentences they built were also wrong. Decision
174 named them; the PI asked for them deleted on 2026-09-15.

The guard reads the module's syntax tree rather than importing it, so it runs on both runners and
cannot be satisfied by a stub.
"""
import ast
import pathlib

SRC = pathlib.Path(__file__).resolve().parents[1] / "routines" / "analytics.py"


def _runtime_strings(tree):
    """Every string constant a running function could hand back: literals and f-string parts,
    with docstrings left out (a docstring may quote the retired wording as history)."""
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Module)):
            body = getattr(node, "body", [])
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
                    and isinstance(body[0].value.value, str):
                docstrings.add(id(body[0].value))
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docstrings:
            yield node.value


def test_the_two_sweep_headline_builders_are_gone():
    tree = ast.parse(SRC.read_text())
    names = sorted(n.name for n in ast.walk(tree)
                   if isinstance(n, ast.FunctionDef) and "sweep_headline" in n.name)
    assert names == [], f"dead headline builders still defined: {names}"


def test_no_runtime_string_in_analytics_calls_the_choice_best_of_ten():
    """The sweep tries nine lengths (decision 170); a sentence the page could print must not say ten."""
    tree = ast.parse(SRC.read_text())
    bad = sorted({s for s in _runtime_strings(tree)
                  if "best-of-ten" in s.lower() or "best of ten" in s.lower()})
    assert bad == [], f"runtime strings still say best-of-ten: {bad}"
