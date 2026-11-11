"""A file repeated within one batch is ingested once (the PI, 2026-10-18, option c). The folder ingest
checked each file only against the exports already stored, before writing any, so two byte-identical
copies in one folder were both "new": the scratch re-ingest of the 615 Dropbox files stored 615
exports where live holds 598 (17 exact extra copies). CLAUDE.md section 11: drop only a bit-for-bit
duplicate; the result must not depend on the order files arrive. Plain `assert`, no arguments."""
import os

from modules.MedtronicPercept.ingest_batch import split_new_and_held

BRAVO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


def test_two_identical_copies_in_one_batch_are_ingested_once():
    new, held = split_new_and_held([("/in/a.json", "h1"), ("/in/b.json", "h1"), ("/in/c.json", "h2")],
                                   is_held=lambda h: False)
    assert new == [("/in/a.json", "h1"), ("/in/c.json", "h2")], new
    assert held == ["/in/b.json"], held


def test_which_copy_is_kept_does_not_depend_on_the_order_given():
    items = [("/in/b.json", "h1"), ("/in/a.json", "h1")]
    for order in (items, items[::-1]):
        new, held = split_new_and_held(order, is_held=lambda h: False)
        assert new == [("/in/a.json", "h1")] and held == ["/in/b.json"], (new, held)


def test_a_file_already_stored_is_not_new():
    new, held = split_new_and_held([("/in/a.json", "h1"), ("/in/b.json", "h2")], is_held=lambda h: h == "h1")
    assert new == [("/in/b.json", "h2")] and held == ["/in/a.json"], (new, held)


def test_two_different_files_are_both_new():
    new, held = split_new_and_held([("/in/a.json", "h1"), ("/in/b.json", "h2")], is_held=lambda h: False)
    assert [p for p, _ in new] == ["/in/a.json", "/in/b.json"] and held == [], (new, held)


def test_the_folder_ingest_uses_it():
    src = open(os.path.join(BRAVO, "Server", "management", "commands", "ingest_percept_folder.py")).read()
    assert "split_new_and_held(" in src
