"""Shared helper for the pool and helper-process tests (2026-10-05: two files each had their own
copy, one using psutil and one reading /proc). Not a test file, and no name here starts with
`test_`, because the container runner calls every callable `test_*` a module holds."""
import os


def alive(pids):
    """The process ids in `pids` that are still running; a zombie (ended, not yet reaped) is not.

    psutil when it is installed; otherwise a signal-0 probe, with the zombie check read from /proc
    where there is one (a host without psutil and without /proc, such as a bare Mac, counts a
    zombie as running, which can only make a "has it stopped" check fail, never pass wrongly)."""
    try:
        import psutil
    except ImportError:
        psutil = None
    out = []
    for p in pids:
        if psutil is not None:
            try:
                if psutil.Process(p).status() != psutil.STATUS_ZOMBIE:
                    out.append(p)
            except psutil.NoSuchProcess:
                pass
            continue
        try:
            os.kill(p, 0)
        except OSError:
            continue
        try:
            with open(f"/proc/{p}/stat") as fh:
                if fh.read().split()[2] == "Z":
                    continue
        except OSError:
            pass
        out.append(p)
    return out
