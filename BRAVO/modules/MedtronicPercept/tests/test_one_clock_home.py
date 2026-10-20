"""No module reads a Percept export except through the one converting loader.

Every dated field of a Percept export is on the implanted device's clock (TabletClock.py). The PI,
2026-09-26: "INS device time should not be used anywhere for any reason." So a raw export may be
opened only by `DataCurator.loadPerceptJSON`, which converts every time to the tablet's clock before
anyone reads it. This test reads the source of every module and fails if anything else calls or
hands on `loadCacheFile` -- the decrypting reader under it -- except the decoders of other file types
and the endpoints that hand the user their own file back unchanged, each named below.
The single raw-spectrum identity boundary additionally reads original arrays and clock identity,
then routes its compact event projection through the same TabletClock conversion before parsing;
the regression below verifies that exact sequence and the resulting tablet timestamp.
"""
import ast
import os

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))

#: (file relative to BRAVO/, enclosing function or Class.method) allowed to touch the raw reader.
ALLOWED = {
    ("modules/DataCurator.py", "loadCacheFile"),              # its own definition
    ("modules/DataCurator.py", "loadPerceptJSON"),            # THE converting loader
    # Exact source identity requires original values; the test below enforces canonical conversion.
    ("modules/DataCurator.py", "_event_source_index"),
    # decoders of file types that are not Percept session exports
    ("modules/DataCurator.py", "NeuroPacePersystDatDecoder"),
    ("modules/DataCurator.py", "EventCSVDecoder"),
    ("modules/DataCurator.py", "MATFileDecoder"),
    ("modules/DataCurator.py", "HPFCSVDecoder"),
    ("modules/DataCurator.py", "AlphaOmegaMPXDecoder"),
    ("modules/DataCurator.py", "UFMDATDecoder"),
    ("modules/DataCurator.py", "UFMDATv2Decoder"),
    ("modules/DataCurator.py", "UFMDATv3Decoder"),  # UFMDAT v3 container, not a Percept session export
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



def test_raw_event_identity_boundary_converts_before_parsing_and_returns_tablet_time(monkeypatch):
    """Allow only the identity boundary, not a second unconverted event reader."""
    import copy
    import json
    from modules.MedtronicPercept import BrainSenseEvent, Percept, TabletClock
    from .test_event_mysql_identity import helper_namespace, raw_document, source, L

    raw = raw_document()
    original = copy.deepcopy(raw)
    calls = []
    table = TabletClock.AnchorTable([TabletClock.export_anchor(raw)])
    namespace = helper_namespace()
    namespace["loadCacheFile"] = lambda source: json.dumps(raw).encode()
    namespace["clock_anchor_table"] = lambda **kwargs: table
    real_index = BrainSenseEvent.sourceEventIndex
    real_convert = TabletClock.convert_export
    real_extract = Percept.extractChronicLFP

    def index(document, anchors, clock, parser):
        assert document == original
        assert anchors is table and clock is TabletClock and parser is Percept
        calls.append("raw_identity_boundary")
        return real_index(document, anchors, clock, parser)

    def convert(document, anchors):
        assert document["DiagnosticData"]["LfpFrequencySnapshotEvents"][0]["DateTime"] == "2020-01-01T00:00:01Z"
        calls.append("canonical_clock_conversion")
        return real_convert(document, anchors)

    def extract(document, output):
        assert calls == ["raw_identity_boundary", "canonical_clock_conversion"]
        assert document["DiagnosticData"]["LfpFrequencySnapshotEvents"][0]["DateTime"] == "2019-12-31T23:59:40Z"
        calls.append("canonical_event_parser")
        return real_extract(document, output)

    monkeypatch.setattr(BrainSenseEvent, "sourceEventIndex", index)
    monkeypatch.setattr(TabletClock, "convert_export", convert)
    monkeypatch.setattr(Percept, "extractChronicLFP", extract)
    result = namespace["_event_source_index"](source("synthetic-clock-guard"), {})
    assert calls == ["raw_identity_boundary", "canonical_clock_conversion", "canonical_event_parser"]
    assert set(result) == {("Synthetic", 1577836780.0, L)}
    assert result[("Synthetic", 1577836780.0, L)][0]["block"]["FFTBinData"] == [0.1, 0.2, -1.0]
    assert raw == original
