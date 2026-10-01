"""BRAVO's processes default the maths library to ONE thread (speed-up item A2, 2026-10-01).

The default lives in `BRAVO/maths_threads.py`, which `BRAVO/settings.py` imports before anything
else. Each web worker otherwise started as many BLAS/OpenMP threads as the machine has cores for
every small fit; decisions 140 and 268 measured 10-15x slower small fits under that contention, with
every value identical. Proof on RCS08 (2026-10-01): the heat-map grid, the Closed-Loop report and the
Stim Optimizer two-stage request differ from the default only in their timing fields.

Each check runs a fresh interpreter: the thread count is fixed when numpy first loads. The module
is imported on its own, so the check needs no Django settings (the host runner and CI set none).
"""
import os
import subprocess
import sys
from pathlib import Path

BRAVO_ROOT = Path(__file__).resolve().parents[3]          # .../BRAVO (holds BRAVO/maths_threads.py)
VARS = ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS")

PROBE = (
    "import os, sys; sys.path.insert(0, %r); import BRAVO.maths_threads; import numpy\n"
    "print(' '.join(os.environ.get(v, '-') for v in %r))\n"
    "try:\n"
    "    from threadpoolctl import threadpool_info\n"
    "    print(max([i['num_threads'] for i in threadpool_info() if i.get('user_api') == 'blas'] or [0]))\n"
    "except ImportError:\n"
    "    print('no-threadpoolctl')\n"
) % (str(BRAVO_ROOT), VARS)


def _run(extra_env):
    env = {k: v for k, v in os.environ.items() if k not in VARS}
    env.update(extra_env)
    out = subprocess.run([sys.executable, "-c", PROBE], env=env, capture_output=True, text=True,
                         timeout=120)
    assert out.returncode == 0, out.stderr[-2000:]
    return out.stdout.split("\n")


def test_the_default_is_one_maths_thread():
    lines = _run({})
    assert lines[0] == "1 1 1", lines
    if lines[1] != "no-threadpoolctl":
        assert lines[1] == "1", f"BLAS runs {lines[1]} threads after BRAVO.maths_threads"


def test_a_thread_count_already_in_the_environment_wins():
    lines = _run({"OPENBLAS_NUM_THREADS": "3"})
    assert lines[0].split()[0] == "3", lines


def test_settings_imports_it_before_anything_else():
    first = next(l for l in (BRAVO_ROOT / "BRAVO" / "settings.py").read_text().splitlines()
                 if l.startswith(("import ", "from ")))
    assert first.startswith("from BRAVO import maths_threads"), first


if __name__ == "__main__":
    test_the_default_is_one_maths_thread()
    test_a_thread_count_already_in_the_environment_wins()
    test_settings_imports_it_before_anything_else()
    print("ok")
