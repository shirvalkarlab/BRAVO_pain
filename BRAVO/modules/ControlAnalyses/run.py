"""Run a control analysis and save it: `python3 -m modules.ControlAnalyses.run <key|all> [participant]`.

Offline only (the bridge or a shell in the container); a page never starts one."""
import os
import sys

if __name__ == "__main__":
    sys.path.insert(0, "/usr/src/BRAVO")
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "BRAVO.settings")
    import django
    django.setup()
    from modules.CacheStore import store as _cs
    _cs.store = lambda *a, **k: False                  # a control analysis writes no cache entry
    from modules.ControlAnalyses import runners as R
    key = sys.argv[1] if len(sys.argv) > 1 else "all"
    uid = sys.argv[2] if len(sys.argv) > 2 else "2e3c75c00d7f4f37b53a048d195f11da"
    for k in (list(R.RUNNERS) if key == "all" else [key]):
        rec = R.RUNNERS[k](uid)
        print(f"SAVED {k} run_at {rec['run_at']} data {rec['data_from']} to {rec['data_through']}")
        for line in rec["reading"]:
            print("   ", line)
