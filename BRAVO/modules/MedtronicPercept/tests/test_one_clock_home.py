"""No module reads a Percept export except through the one converting loader.

Every dated field of a Percept export is on the implanted device's clock (TabletClock.py). The PI,
2026-09-26: "INS device time should not be used anywhere for any reason." So a raw export may be
opened only by `DataCurator.loadPerceptJSON`, which converts every time to the tablet's clock before
anyone reads it. This test reads the source of every module and fails if anything else calls or
hands on `loadCacheFile` -- the decrypting reader under it -- except the decoders of other file types
and the endpoints that hand the user their own file back unchanged, each named below.
"""
import ast
import os

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))

#: (file relative to BRAVO/, enclosing function or Class.method) allowed to touch the raw reader.
ALLOWED = {
    ("modules/DataCurator.py", "loadCacheFile"),              # its own definition
    ("modules/DataCurator.py", "loadPerceptJSON"),            # THE converting loader
    # decoders of file types that are not Percept session exports
    ("modules/DataCurator.py", "NeuroPacePersystDatDecoder"),
    ("modules/DataCurator.py", "EventCSVDecoder"),
    ("modules/DataCurator.py", "MATFileDecoder"),
    ("modules/DataCurator.py", "HPFCSVDecoder"),
    ("modules/DataCurator.py", "AlphaOmegaMPXDecoder"),
    ("modules/DataCurator.py", "UFMDATDecoder"),
    ("modules/DataCurator.py", "UFMDATv2Decoder"),
    ("modules/DataCurator.py", "BRAVORecordingBinaryDecoder"),
    ("modules/DataCurator.py", "ImportBRAVOExport"),
    ("modules/DataCurator.py", "ImportBRAVOStructure"),
    # the user's own file handed back byte for byte (image models, scenes, the raw download)
    ("Server/APIs/DataHandler.py", "DataDownloadHandler.get"),
    ("Server/APIs/DataHandler.py", "DataDownloadHandler.post"),
    ("Server/APIs/DataHandler.py", "DataSourceFileHandler.get"),
}


def _uses(path):
    """(enclosing name, line) for every mention of `loadCacheFile` in the file."""
    tree = ast.parse(open(path, encoding="utf-8").read())
    out = []

    def visit(node, scope):
        for child in ast.iter_child_nodes(node):
            s = scope
            if isinstance(child, ast.ClassDef):
                s = child.name
            elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                s = (scope + "." + child.name) if scope and "." not in scope and scope[:1].isupper() else child.name
                if child.name == "loadCacheFile" and scope == "":
                    out.append(("loadCacheFile", child.lineno))
            if isinstance(child, ast.Attribute) and child.attr == "loadCacheFile":
                out.append((scope, child.lineno))
            elif isinstance(child, ast.Name) and child.id == "loadCacheFile":
                out.append((scope, child.lineno))
            visit(child, s)

    visit(tree, "")
    return out


def test_every_reader_of_a_percept_export_goes_through_the_converting_loader():
    bad = []
    for top in ("modules", "Server"):
        for dirpath, dirnames, files in os.walk(os.path.join(ROOT, top)):
            dirnames[:] = [d for d in dirnames if d not in ("tests", "__pycache__", "migrations")]
            for f in files:
                if not f.endswith(".py"):
                    continue
                p = os.path.join(dirpath, f)
                rel = os.path.relpath(p, ROOT)
                for scope, line in _uses(p):
                    if (rel, scope) not in ALLOWED:
                        bad.append(f"{rel}:{line} in {scope or '<module>'}")
    assert not bad, "a raw Percept export is read outside DataCurator.loadPerceptJSON: " + "; ".join(bad)
