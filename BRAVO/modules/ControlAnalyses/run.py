"""Run an explicitly scoped control analysis: ``python -m modules.ControlAnalyses.run <key|all> <participant>``.

Offline only. The participant must be selected explicitly; a page never starts one.
"""
import argparse
import os
import sys
from pathlib import Path


def parse_arguments(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("key", help="Control analysis key or all")
    parser.add_argument("participant", help="Exact participant UID")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_arguments(argv)
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "BRAVO.settings")
    import django
    django.setup()
    from modules.CacheStore import store as _cs
    _cs.store = lambda *a, **k: False  # control analyses write no cache entry
    from modules.ControlAnalyses import runners as R
    if args.key != "all" and args.key not in R.RUNNERS:
        raise SystemExit("Unknown control analysis key")
    for key in (list(R.RUNNERS) if args.key == "all" else [args.key]):
        rec = R.RUNNERS[key](args.participant)
        print(f"SAVED {key} run_at {rec['run_at']} data {rec['data_from']} to {rec['data_through']}")
        for line in rec["reading"]:
            print("   ", line)


if __name__ == "__main__":
    main()
