"""A folder of exports is ingested one at a time in session order (CLAUDE.md section 11), not in
file-name order: the batch-ingest command sorted by name, and a name need not follow the session.

Pinned: files go oldest session first by the export's own SessionDate (the tablet's clock); a file
whose SessionDate cannot be read goes last, in name order, and is still ingested. Plain `assert`,
no arguments: container runner."""
import json
import os
import tempfile

from modules.MedtronicPercept.session_order import in_session_order


def _folder(entries):
    d = tempfile.mkdtemp()
    for name, body in entries:
        with open(os.path.join(d, name), "w") as fh:
            fh.write(body if isinstance(body, str) else json.dumps(body))
    return d


def test_exports_go_oldest_session_first_whatever_their_names():
    d = _folder([("a.json", {"SessionDate": "2026-10-02T17:00:00Z"}),
                 ("b.json", {"SessionDate": "2025-07-16T18:30:00Z"}),
                 ("c.json", {"SessionDate": "2026-01-05T19:20:00.000Z"})])
    got = [os.path.basename(p) for p in in_session_order([os.path.join(d, n) for n in ("a.json", "b.json", "c.json")])]
    assert got == ["b.json", "c.json", "a.json"], got


def test_a_file_without_a_readable_session_date_goes_last_and_is_kept():
    d = _folder([("z.json", {"SessionDate": "2026-01-05T19:20:00Z"}), ("x.json", "{not json"),
                 ("y.json", {"NoDate": 1})])
    got = [os.path.basename(p) for p in in_session_order([os.path.join(d, n) for n in ("x.json", "y.json", "z.json")])]
    assert got == ["z.json", "x.json", "y.json"], got
