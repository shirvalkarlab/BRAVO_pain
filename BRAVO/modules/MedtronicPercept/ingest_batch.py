"""Which files of a folder are new: not already stored, and not a bit-for-bit repeat of another file in
the same folder (the PI, 2026-10-18). Checking only against what is stored let two identical copies in
one folder both through. Of identical copies the first in name order is kept, so the result does not
depend on the order the files are listed in (CLAUDE.md section 11)."""
import os


def split_new_and_held(items, is_held):
    """`items`: (path, upload check value) pairs; `is_held(value)`: already stored. Returns
    (new [(path, value)], held [path]); new keeps one file per value, in name order."""
    new, held, seen = [], [], set()
    for path, value in sorted(items, key=lambda it: (os.path.basename(it[0]), it[0])):
        if value in seen or is_held(value):
            held.append(path)
        else:
            seen.add(value)
            new.append((path, value))
    return new, held
